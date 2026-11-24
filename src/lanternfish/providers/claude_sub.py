"""Claude subscription limits, read with the OAuth token Claude Code keeps in the Keychain.

Unofficial endpoint: GET https://api.anthropic.com/api/oauth/usage
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime

from .base import ProviderError, TokenExpired, Usage, Window, get_json

URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
RELOGIN = "run `claude` to sign in again"


def read_token() -> tuple[str, str | None]:
    """Return (access token, subscription type) from Claude Code's Keychain entry."""
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ProviderError(f"no Claude Code login; {RELOGIN}") from exc
    try:
        oauth = json.loads(raw)["claudeAiOauth"]
        token = oauth["accessToken"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProviderError("unreadable Claude Code credentials") from exc
    expires_ms = oauth.get("expiresAt")
    if isinstance(expires_ms, (int, float)) and expires_ms / 1000 < time.time():
        raise TokenExpired(f"token expired; {RELOGIN}")
    return token, oauth.get("subscriptionType")


def token_ready() -> bool:
    """Whether the Keychain now holds an unexpired token; no network request."""
    try:
        read_token()
    except ProviderError:
        return False
    return True


def parse(data: dict, plan: str | None = None) -> Usage:
    usage = Usage(name="Claude", short="C", plan=plan)
    for key, label in (("five_hour", "5-hour"), ("seven_day", "Weekly")):
        block = data.get(key)
        if not isinstance(block, dict) or block.get("utilization") is None:
            continue
        resets = block.get("resets_at")
        usage.windows.append(Window(
            label=label,
            used_percent=float(block["utilization"]),
            resets_at=datetime.fromisoformat(resets) if resets else None,
        ))
    if not usage.windows:
        raise ProviderError("no usage windows in response")
    return usage


def fetch() -> Usage:
    token, plan = read_token()
    data = get_json(URL, {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    return parse(data, plan)
