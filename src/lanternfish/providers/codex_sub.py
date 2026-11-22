"""ChatGPT / Codex subscription limits, read with the token Codex CLI keeps in ~/.codex/auth.json.

Unofficial endpoint: GET https://chatgpt.com/backend-api/wham/usage
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .base import ProviderError, Usage, Window, get_json

URL = "https://chatgpt.com/backend-api/wham/usage"
AUTH_FILE = Path.home() / ".codex" / "auth.json"
RELOGIN = "run `codex login` to sign in again"


def read_token(path: Path = AUTH_FILE) -> tuple[str, str | None]:
    """Return (access token, account id) from Codex CLI's auth file."""
    try:
        tokens = json.loads(path.read_text())["tokens"]
        return tokens["access_token"], tokens.get("account_id")
    except FileNotFoundError as exc:
        raise ProviderError(f"no Codex login; {RELOGIN}") from exc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProviderError("unreadable Codex credentials") from exc


def _label(seconds: object, fallback: str) -> str:
    if seconds == 18000:
        return "5-hour"
    if seconds == 604800:
        return "Weekly"
    return fallback


def parse(data: dict) -> Usage:
    usage = Usage(name="Codex", short="X", plan=data.get("plan_type"))
    limits = data.get("rate_limit") or {}
    for key, fallback in (("primary_window", "Short"), ("secondary_window", "Long")):
        block = limits.get(key)
        if not isinstance(block, dict) or block.get("used_percent") is None:
            continue
        reset_at = block.get("reset_at")
        usage.windows.append(Window(
            label=_label(block.get("limit_window_seconds"), fallback),
            used_percent=float(block["used_percent"]),
            resets_at=datetime.fromtimestamp(reset_at, timezone.utc) if reset_at else None,
        ))
    if not usage.windows:
        raise ProviderError("no usage windows in response")
    return usage


def fetch() -> Usage:
    token, account_id = read_token()
    headers = {"Authorization": f"Bearer {token}"}
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    try:
        data = get_json(URL, headers)
    except ProviderError as exc:
        if "auth rejected" in str(exc):
            raise ProviderError(f"token rejected; {RELOGIN}") from exc
        raise
    return parse(data)
