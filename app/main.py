import os
import time
import uuid
from datetime import timezone
from zoneinfo import ZoneInfo
from typing import Optional

from dateutil.parser import isoparse
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator, model_validator

from . import dce, supa, metrics


class ExportCreate(BaseModel):
    start_at: str
    end_at: str
    format: Optional[str] = "Json"
    media: Optional[bool] = False
    filter: Optional[str] = None
    timezone: Optional[str] = "UTC"  # e.g., "Asia/Seoul"

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"Json", "PlainText", "HtmlDark", "HtmlLight", "Csv"}
        if v not in allowed:
            raise ValueError("invalid format")
        return v

    @model_validator(mode="after")
    def validate_range(self):
        # Parse with support for explicit tz or provided timezone (default UTC)
        try:
            s_dt = isoparse(self.start_at)
        except Exception:
            raise ValueError("start_at must be ISO8601")
        try:
            e_dt = isoparse(self.end_at)
        except Exception:
            raise ValueError("end_at must be ISO8601")

        tz_name = self.timezone or "UTC"
        try:
            tz_obj = ZoneInfo(tz_name)
        except Exception:
            raise ValueError("invalid timezone")

        if s_dt.tzinfo is None:
            s_dt = s_dt.replace(tzinfo=tz_obj)
        if e_dt.tzinfo is None:
            e_dt = e_dt.replace(tzinfo=tz_obj)

        s = s_dt.astimezone(timezone.utc)
        e = e_dt.astimezone(timezone.utc)

        if not (s < e):
            raise ValueError("start_at must be before end_at")
        # Normalize stored strings to UTC Z
        self.start_at = s.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.end_at = e.strftime("%Y-%m-%dT%H:%M:%SZ")
        return self


app = FastAPI(title="Discord Message Archiver API")


@app.get("/health")
def health():
    return {"ok": True}


@app.middleware("http")
async def json_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        print({
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        })
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        print({
            "event": "http_error",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error": str(e)[:200],
            "duration_ms": duration_ms,
        })
        raise


def run_job(job_id: str, payload: ExportCreate) -> None:
    client = supa.get_client()
    start_ms = time.time()
    supa.update_export(client, job_id, {"status": "running"})

    try:
        token = os.environ["DISCORD_TOKEN"]
        channel_id = os.environ.get("DEFAULT_CHANNEL_ID")
        if not channel_id:
            raise RuntimeError("DEFAULT_CHANNEL_ID not configured")

        data = dce.export_json(
            token=token,
            channel_id=channel_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            media=bool(payload.media),
            filter_expr=payload.filter,
        )
        messages = data.get("messages", data)
        # Normalize minimal shape for DB insert
        rows = []
        for m in messages:
            rows.append(
                {
                    "message_id": str(m.get("id")),
                    "channel_id": channel_id,
                    "author_id": str((m.get("author") or {}).get("id")) if m.get("author") else None,
                    "author_name": (m.get("author") or {}).get("name") if m.get("author") else None,
                    "content": m.get("content"),
                    "timestamp": m.get("timestamp"),
                    "attachments": m.get("attachments"),
                    "embeds": m.get("embeds"),
                    "raw": m,
                    "job_id": job_id,
                }
            )

        # Insert rows (ignore duplicates by message_id)
        supa.insert_messages(client, rows)
        # Compute integrity considering pre-existing messages in DB
        existing = supa.count_existing_messages_by_ids(client, [r["message_id"] for r in rows])
        inserted_count = len(rows)  # requested
        message_count = len(rows)   # exported
        effective_inserted = message_count - existing
        duration_ms = int((time.time() - start_ms) * 1000)
        if effective_inserted != message_count:
            supa.update_export(
                client,
                job_id,
                {
                    "status": "failed",
                    "message_count": message_count,
                    "inserted_count": effective_inserted,
                    "duration_ms": duration_ms,
                    "error": "integrity_mismatch (duplicates pre-existed)",
                },
            )
        else:
            supa.update_export(
                client,
                job_id,
                {
                    "status": "completed",
                    "message_count": message_count,
                    "inserted_count": effective_inserted,
                    "duration_ms": duration_ms,
                    "error": None,
                },
            )
    except Exception as e:
        duration_ms = int((time.time() - start_ms) * 1000)
        supa.update_export(
            client,
            job_id,
            {
                "status": "failed",
                "duration_ms": duration_ms,
                "error": str(e)[:1000],
            },
        )


@app.post("/exports", status_code=202)
def create_export(req: ExportCreate, bg: BackgroundTasks):
    metrics.inc_http_requests()
    if not metrics.allow_export_now():
        raise HTTPException(status_code=429, detail="rate_limited")
    if not os.environ.get("DISCORD_TOKEN"):
        raise HTTPException(status_code=500, detail="Server not configured: missing DISCORD_TOKEN")
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_KEY"):
        raise HTTPException(status_code=500, detail="Server not configured: missing Supabase credentials")

    if req.format is not None and req.format != "Json":
        # MVP supports only Json end-to-end pipeline
        raise HTTPException(status_code=400, detail="Only Json format is supported")

    job_id = str(uuid.uuid4())
    client = supa.get_client()
    supa.insert_export(
        client,
        {
            "job_id": job_id,
            "channel_id": os.environ.get("DEFAULT_CHANNEL_ID"),
            "start_at": req.start_at,
            "end_at": req.end_at,
            "status": "pending",
        },
    )
    bg.add_task(run_job, job_id, req)
    metrics.inc_exports()
    return {"job_id": job_id}


@app.get("/exports/{job_id}")
def get_export(job_id: str):
    metrics.inc_http_requests()
    client = supa.get_client()
    data = supa.get_export(client, job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Not found")
    return data


@app.get("/status")
def list_status(limit: int = 20):
    metrics.inc_http_requests()
    client = supa.get_client()
    rows = supa.list_recent_exports(client, limit=limit)
    return {"items": rows}


@app.get("/metrics")
def get_metrics():
    body = metrics.render_prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.exception_handler(HTTPException)
def http_error_handler(_: Request, exc: HTTPException):
    metrics.inc_http_errors()
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.exception_handler(Exception)
def unhandled_error_handler(_: Request, __: Exception):
    # Do not expose internal error details
    metrics.inc_http_errors()
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal server error"}},
    )


