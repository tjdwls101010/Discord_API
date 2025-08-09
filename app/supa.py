import os
from typing import Any, Dict, List, Optional
from supabase import Client, create_client


def get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Supabase credentials are not configured")
    return create_client(url, key)


def insert_export(client: Client, job: Dict[str, Any]) -> None:
    client.table("exports").insert(job).execute()


def update_export(client: Client, job_id: str, patch: Dict[str, Any]) -> None:
    client.table("exports").update(patch).eq("job_id", job_id).execute()


def get_export(client: Client, job_id: str) -> Optional[Dict[str, Any]]:
    res = client.table("exports").select("*").eq("job_id", job_id).single().execute()
    return res.data if res is not None else None


def insert_messages(client: Client, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    # Use upsert to emulate ON CONFLICT DO NOTHING
    resp = client.table("messages").upsert(rows, on_conflict="message_id", ignore_duplicates=True).execute()
    # supabase-py may not return affected rows count reliably; compute from input
    return len(rows)


def count_messages_for_job(client: Client, job_id: str) -> int:
    res = client.table("messages").select("message_id", count="exact").eq("job_id", job_id).execute()
    try:
        # supabase-py returns count on response
        count_val = getattr(res, "count", None)
        if isinstance(count_val, int):
            return count_val
    except Exception:
        pass
    data = getattr(res, "data", None)
    return len(data) if isinstance(data, list) else 0


def list_recent_exports(client: Client, limit: int = 20) -> List[Dict[str, Any]]:
    res = (
        client.table("exports")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


