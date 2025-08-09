from typing import Dict
import time

_http_counts: Dict[str, int] = {"requests_total": 0, "errors_total": 0}
_export_counts: Dict[str, int] = {"exports_total": 0}

# Simple fixed-window rate limiter (global)
_rl_window_started_ms: int = 0
_rl_count: int = 0
_rl_limit: int = 10
_rl_window_ms: int = 60_000


def inc_http_requests() -> None:
    _http_counts["requests_total"] += 1


def inc_http_errors() -> None:
    _http_counts["errors_total"] += 1


def inc_exports() -> None:
    _export_counts["exports_total"] += 1


def render_prometheus() -> str:
    lines = [
        "# HELP requests_total Total HTTP requests",
        "# TYPE requests_total counter",
        f"requests_total {_http_counts['requests_total']}",
        "# HELP errors_total Total HTTP errors",
        "# TYPE errors_total counter",
        f"errors_total {_http_counts['errors_total']}",
        "# HELP exports_total Total export jobs accepted",
        "# TYPE exports_total counter",
        f"exports_total {_export_counts['exports_total']}",
        f"# scraped_at_ms {int(time.time() * 1000)}",
    ]
    return "\n".join(lines) + "\n"


def set_rate_limit(limit_per_minute: int) -> None:
    global _rl_limit
    _rl_limit = max(1, limit_per_minute)


def allow_export_now(current_ms: int | None = None) -> bool:
    """Return True if allowed under global 1-min window; else False."""
    global _rl_window_started_ms, _rl_count
    now = int((current_ms if current_ms is not None else time.time() * 1000))
    if _rl_window_started_ms == 0:
        _rl_window_started_ms = now
        _rl_count = 0
    # Reset window if expired
    if now - _rl_window_started_ms >= _rl_window_ms:
        _rl_window_started_ms = now
        _rl_count = 0
    if _rl_count >= _rl_limit:
        return False
    _rl_count += 1
    return True


