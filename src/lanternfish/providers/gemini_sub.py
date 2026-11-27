"""Google AI (Gemini) subscription limits in Antigravity, read with the OAuth token
Antigravity CLI (`agy`) keeps in the Keychain (service "gemini", account "antigravity").

Unofficial endpoints on https://daily-cloudcode-pa.googleapis.com:
POST v1internal:loadCodeAssist (plan and project), then
POST v1internal:fetchAvailableModels (remainingFraction and resetTime per model), and
POST v1internal:retrieveUserQuotaSummary (shared 5-hour and weekly limits per model group,
without reset times; for now it only lists the Claude and GPT models' group).
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


WINDOWS = {"5h": "5-hour", "weekly": "weekly"}


def parse(data: dict, plan: str | None = None, summary: dict | None = None) -> Usage:
    """A Gemini window for the Gemini models' pool (its lowest model), then each group's
    5-hour and weekly limits from the quota summary, labelled with the group name
    ("Claude & GPT 5-hour") so they are not mistaken for the Claude and Codex rows.
    """
    lowest = None
    for model_id, info in (data.get("models") or {}).items():
        quota = info.get("quotaInfo") if isinstance(info, dict) else None
        if (not model_id.startswith("gemini") or not info.get("displayName")
                or not isinstance(quota, dict) or quota.get("remainingFraction") is None):
            continue
        if lowest is None or quota["remainingFraction"] < lowest["remainingFraction"]:
            lowest = quota
    if lowest is None:
        raise ProviderError("no Gemini quota in response")
    resets = lowest.get("resetTime")
    usage = Usage(name="Gemini", short="G", plan=plan, windows=[Window(
        label="Gemini",
        used_percent=(1 - float(lowest["remainingFraction"])) * 100,
        resets_at=datetime.fromisoformat(resets.replace("Z", "+00:00")) if resets else None,
    )])
    usage.windows += group_windows(summary or {})
    return usage


def group_name(display_name: str) -> str:
    """'Claude and GPT models' -> 'Claude & GPT'."""
    return display_name.removesuffix(" models").replace(" and ", " & ")


def group_windows(summary: dict) -> list[Window]:
    windows = []
    for group in summary.get("groups") or []:
        if not isinstance(group, dict) or not group.get("displayName"):
            continue
        buckets = {b.get("window"): b for b in group.get("buckets") or [] if isinstance(b, dict)}
        for key, label in WINDOWS.items():
            bucket = buckets.get(key)
            if not bucket or bucket.get("remainingFraction") is None:
                continue
            resets = bucket.get("resetTime")
            windows.append(Window(
                label=f"{group_name(group['displayName'])} {label}",
                used_percent=(1 - float(bucket["remainingFraction"])) * 100,
                resets_at=datetime.fromisoformat(resets.replace("Z", "+00:00")) if resets else None,
            ))
    return windows


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
        try:
            summary = post_json(BASE + "retrieveUserQuotaSummary", {"project": project}, headers)
        except ProviderError:   # only extra windows; the Gemini window still shows
            summary = None
    except ProviderError as exc:
        if "auth rejected" in str(exc):
            raise ProviderError(f"token rejected; {RELOGIN}") from exc
        raise
    return parse(data, plan_name(assist), summary)
