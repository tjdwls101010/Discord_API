import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional


DCE_BIN = "/opt/dce/DiscordChatExporter.Cli"


def _mask(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def export_json(
    token: str,
    channel_id: str,
    start_at: str,
    end_at: str,
    *,
    media: bool = False,
    filter_expr: Optional[str] = None,
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    """Run DCE and return parsed JSON payload.

    Raises RuntimeError on non-zero exit.
    """
    if not os.path.exists(DCE_BIN):
        raise RuntimeError("DiscordChatExporter CLI not found at /opt/dce. Check Dockerfile install step.")

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "out.json")
        # Optional: treat provided token as bot token when configured
        token_value = token
        if os.environ.get("DISCORD_IS_BOT", "").lower() in {"1", "true", "yes"}:
            if not token_value.startswith("Bot "):
                token_value = f"Bot {token_value}"
        cmd: List[str] = [
            DCE_BIN,
            "export",
            "-t",
            token_value,
            "-c",
            channel_id,
            "--after",
            start_at,
            "--before",
            end_at,
            "-f",
            "Json",
            "-o",
            out_file,
        ]
        if media:
            cmd.append("--media")
        if filter_expr:
            cmd.extend(["--filter", filter_expr])

        # Do not print raw token in logs
        safe_cmd = [w if w != token_value else _mask(token_value) for w in cmd]
        print({"dce_cmd": safe_cmd})

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            raise RuntimeError(f"DCE failed rc={proc.returncode} stderr={stderr[:500]} stdout={stdout[:500]}")

        if not os.path.exists(out_file):
            raise RuntimeError("DCE did not produce output file")

        with open(out_file, "r", encoding="utf-8") as f:
            return json.load(f)


