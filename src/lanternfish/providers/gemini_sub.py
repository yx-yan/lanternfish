"""Google AI (Gemini) subscription limits in Antigravity, read with the OAuth token
Antigravity CLI (`agy`) keeps in the Keychain (service "gemini", account "antigravity").

Unofficial endpoints on https://daily-cloudcode-pa.googleapis.com:
POST v1internal:loadCodeAssist (plan and project), then
POST v1internal:fetchAvailableModels (remainingFraction and resetTime per model).

The 5-hour and weekly limits Antigravity's model picker shows come only from agy's local
language server (RetrieveUserQuotaSummary, found through ~/.gemini/antigravity/daemon/hub_*.json);
the cloud endpoint leaves the Gemini group out. Without agy running, the Gemini models'
pool from fetchAvailableModels is shown instead.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .base import NotConfigured, ProviderError, TokenExpired, Usage, Window, post_json

BASE = "https://daily-cloudcode-pa.googleapis.com/v1internal:"
KEYCHAIN_SERVICE = "gemini"
KEYCHAIN_ACCOUNT = "antigravity"
PREFIX = "go-keyring-base64:"
RELOGIN = "open `agy` to renew it"
# Without Antigravity's user agent the server answers as if the account had no plan.
USER_AGENT = "antigravity"

DAEMON_DIR = Path.home() / ".gemini" / "antigravity" / "daemon"
LOCAL_RPC = "/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
LOCAL_TIMEOUT_SECONDS = 3
WINDOWS = {"5h": "5-hour", "weekly": "Weekly"}

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


def _iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def pool_window(data: dict) -> Window:
    """The Gemini models' pool from fetchAvailableModels, showing its lowest model."""
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
    return Window(label="Gemini", used_percent=(1 - float(lowest["remainingFraction"])) * 100,
                  resets_at=_iso(lowest.get("resetTime")))


def limit_windows(summary: dict) -> list[Window]:
    """The Gemini group's 5-hour and weekly limits from the local quota summary.

    Other groups (Antigravity's Claude and GPT models) are left out so they are not
    mistaken for the Claude and Codex subscriptions.
    """
    windows = []
    for group in (summary.get("response") or summary).get("groups") or []:
        if not isinstance(group, dict) or not str(group.get("displayName", "")).startswith("Gemini"):
            continue
        buckets = {b.get("window"): b for b in group.get("buckets") or [] if isinstance(b, dict)}
        for key, label in WINDOWS.items():
            bucket = buckets.get(key)
            if bucket and bucket.get("remainingFraction") is not None:
                windows.append(Window(label=label,
                                      used_percent=(1 - float(bucket["remainingFraction"])) * 100,
                                      resets_at=_iso(bucket.get("resetTime"))))
    return windows


def parse(data: dict, plan: str | None = None, summary: dict | None = None) -> Usage:
    windows = limit_windows(summary) if summary else []
    return Usage(name="Gemini", short="G", plan=plan, windows=windows or [pool_window(data)])


def local_summary(daemon_dir: Path = DAEMON_DIR) -> dict | None:
    """Ask a running agy language server for its quota summary; None if none answers."""
    try:
        files = sorted(daemon_dir.glob("hub_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for path in files:
        try:
            hub = json.loads(path.read_text())
            os.kill(int(hub["pid"]), 0)   # skip files left by an agy that has exited
            request = urllib.request.Request(
                f"http://127.0.0.1:{int(hub['httpPort'])}{LOCAL_RPC}", data=b"{}",
                headers={"Content-Type": "application/json", "Connect-Protocol-Version": "1",
                         "X-Codeium-Csrf-Token": hub["csrfToken"]})
            with urllib.request.urlopen(request, timeout=LOCAL_TIMEOUT_SECONDS) as response:
                return json.load(response)
        except Exception:   # stale file, agy busy or changed: try the next one, then fall back
            continue
    return None


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
    return parse(data, plan_name(assist), local_summary())
