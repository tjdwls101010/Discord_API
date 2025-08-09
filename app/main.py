import os
import time
import uuid
from datetime import timezone
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

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"Json", "PlainText", "HtmlDark", "HtmlLight", "Csv"}
        if v not in allowed:
            raise ValueError("invalid format")
        return v

    @field_validator("start_at", "end_at")
    @classmethod
    def validate_iso8601_utc(cls, v: str) -> str:
        try:
            dt = isoparse(v)
        except Exception:
            raise ValueError("must be ISO8601")
        if dt.tzinfo is None:
            raise ValueError("timezone required (UTC)")
        # Normalize to UTC Z
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @model_validator(mode="after")
    def validate_range(self):
        s = isoparse(self.start_at)
        e = isoparse(self.end_at)
        if not (s < e):
            raise ValueError("start_at must be before end_at")
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
        # Count rows actually inserted for this job
        inserted_count = supa.count_messages_for_job(client, job_id)
        duration_ms = int((time.time() - start_ms) * 1000)
        if inserted_count != len(rows):
            supa.update_export(
                client,
                job_id,
                {
                    "status": "failed",
                    "message_count": len(rows),
                    "inserted_count": inserted_count,
                    "duration_ms": duration_ms,
                    "error": "integrity_mismatch",
                },
            )
        else:
            supa.update_export(
                client,
                job_id,
                {
                    "status": "completed",
                    "message_count": len(rows),
                    "inserted_count": inserted_count,
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


