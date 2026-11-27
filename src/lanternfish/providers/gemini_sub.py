"""Google AI (Gemini) subscription limits in Antigravity, read with the OAuth token
Antigravity CLI (`agy`) keeps in the Keychain (service "gemini", account "antigravity").

Unofficial endpoints on https://daily-cloudcode-pa.googleapis.com:
POST v1internal:loadCodeAssist (plan and project), then
POST v1internal:fetchAvailableModels (remainingFraction and resetTime per model).
"""

from __future__ import annotations

import base64
import json
import subprocess
from datetime import datetime, timezone

from .base import NotConfigured, ProviderError, TokenExpired, Usage, Window, post_json

BASE = "https://daily-cloudcode-pa.googleapis.com/v1internal:"
KEYCHAIN_SERVICE = "gemini"
KEYCHAIN_ACCOUNT = "antigravity"
PREFIX = "go-keyring-base64:"
RELOGIN = "open `agy` to renew it"
# Without Antigravity's user agent the server answers as if the account had no plan.
USER_AGENT = "antigravity"

# Window label -> model id prefixes it covers; each window shows its lowest model.
GROUPS = (("Gemini", ("gemini",)), ("Claude & GPT", ("claude", "gpt")))

def read_token() -> str:
    """Return the access token from Antigravity's Keychain entry."""
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise NotConfigured from exc
    try:
        if raw.startswith(PREFIX):
            raw = base64.b64decode(raw[len(PREFIX):]).decode()
        token = json.loads(raw)["token"]
        access = token["access_token"]
        expiry = token.get("expiry")
        expires = datetime.fromisoformat(expiry) if expiry else None
    except (ValueError, KeyError, TypeError) as exc:
        raise ProviderError("unreadable Antigravity credentials") from exc
    if expires and expires <= datetime.now(timezone.utc):
        raise TokenExpired(f"token expired; {RELOGIN}")
    return access


def token_ready() -> bool:
    """Whether the Keychain now holds an unexpired token; no network request."""
    try:
        read_token()
    except (ProviderError, NotConfigured):
        return False
    return True


def plan_name(data: dict) -> str | None:
    tier = data.get("paidTier") or data.get("currentTier") or {}
    name = tier.get("name") if isinstance(tier, dict) else None
    return name.removeprefix("Google AI ") if name else None


def parse(data: dict, plan: str | None = None) -> Usage:
    usage = Usage(name="Gemini", short="G", plan=plan)
    models = data.get("models") or {}
    for label, prefixes in GROUPS:
        lowest = None
        for model_id, info in models.items():
            quota = info.get("quotaInfo") if isinstance(info, dict) else None
            if (not model_id.startswith(prefixes) or not info.get("displayName")
                    or not isinstance(quota, dict) or quota.get("remainingFraction") is None):
                continue
            if lowest is None or quota["remainingFraction"] < lowest["remainingFraction"]:
                lowest = quota
        if lowest is None:
            continue
        resets = lowest.get("resetTime")
        usage.windows.append(Window(
            label=label,
            used_percent=(1 - float(lowest["remainingFraction"])) * 100,
            resets_at=datetime.fromisoformat(resets.replace("Z", "+00:00")) if resets else None,
        ))
    if not usage.windows:
        raise ProviderError("no model quotas in response")
    return usage


def fetch() -> Usage:
    headers = {"Authorization": f"Bearer {read_token()}", "User-Agent": USER_AGENT}
    try:
        assist = post_json(BASE + "loadCodeAssist",
                           {"metadata": {"ideType": "ANTIGRAVITY"}}, headers)
        project = assist.get("cloudaicompanionProject")
        if not project:
            raise ProviderError("no Antigravity project; open `agy` to finish setup")
        data = post_json(BASE + "fetchAvailableModels",
                         {"project": project}, headers)
    except ProviderError as exc:
        if "auth rejected" in str(exc):
            raise ProviderError(f"token rejected; {RELOGIN}") from exc
        raise
    return parse(data, plan_name(assist))
