import json
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lanternfish import providers
from lanternfish.format import report, title, until
from lanternfish.providers import base, claude_sub, codex_sub
from lanternfish.providers.base import ProviderError, Usage

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


# --- Claude -----------------------------------------------------------------

def test_claude_parse_real_response():
    usage = claude_sub.parse(load("claude_usage.json"), plan="max")
    assert [w.label for w in usage.windows] == ["5-hour", "Weekly"]
    assert usage.windows[0].used_percent == 13.0
    assert usage.windows[1].used_percent == 20.0
    assert usage.windows[0].resets_at.tzinfo is not None
    assert usage.plan == "max"


def test_claude_parse_skips_missing_windows():
    usage = claude_sub.parse({"five_hour": None, "seven_day": {"utilization": 7, "resets_at": None}})
    assert [(w.label, w.used_percent, w.resets_at) for w in usage.windows] == [("Weekly", 7.0, None)]


def test_claude_parse_empty_response_is_error():
    with pytest.raises(ProviderError):
        claude_sub.parse({"five_hour": None, "seven_day": None})


def test_claude_expired_token(monkeypatch):
    blob = json.dumps({"claudeAiOauth": {"accessToken": "t", "expiresAt": (time.time() - 60) * 1000}})

    class Done:
        stdout = blob

    monkeypatch.setattr(claude_sub.subprocess, "run", lambda *a, **k: Done)
    with pytest.raises(ProviderError, match="expired"):
        claude_sub.read_token()


def test_claude_missing_keychain_entry(monkeypatch):
    def fail(*a, **k):
        raise claude_sub.subprocess.CalledProcessError(44, "security")

    monkeypatch.setattr(claude_sub.subprocess, "run", fail)
    with pytest.raises(ProviderError, match="no Claude Code login"):
        claude_sub.read_token()


# --- Codex ------------------------------------------------------------------

def test_codex_parse_real_response():
    usage = codex_sub.parse(load("codex_usage.json"))
    assert [w.label for w in usage.windows] == ["5-hour", "Weekly"]
    assert usage.windows[0].used_percent == 58.0
    assert usage.windows[1].used_percent == 13.0
    assert usage.plan == "plus"


def test_codex_unknown_window_length_uses_fallback_label():
    data = {"rate_limit": {"primary_window": {"used_percent": 1, "limit_window_seconds": 3600, "reset_at": None}}}
    assert codex_sub.parse(data).windows[0].label == "Short"


def test_codex_missing_auth_file(tmp_path):
    with pytest.raises(ProviderError, match="no Codex login"):
        codex_sub.read_token(tmp_path / "auth.json")


def test_codex_auth_file_read(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"tokens": {"access_token": "abc", "account_id": "acc"}}))
    assert codex_sub.read_token(path) == ("abc", "acc")


# --- HTTP errors --------------------------------------------------------------

@pytest.mark.parametrize("exc, message", [
    (urllib.error.HTTPError("u", 401, "no", {}, None), "auth rejected"),
    (urllib.error.HTTPError("u", 500, "boom", {}, None), "HTTP 500"),
    (urllib.error.URLError("down"), "network error"),
    (TimeoutError(), "network error"),
])
def test_get_json_errors(monkeypatch, exc, message):
    def raise_(*a, **k):
        raise exc

    monkeypatch.setattr(base.urllib.request, "urlopen", raise_)
    with pytest.raises(ProviderError, match=message):
        base.get_json("https://example.invalid", {})


# --- Isolation and formatting -------------------------------------------------

def test_one_failing_provider_does_not_hide_the_other(monkeypatch):
    def broken():
        raise ProviderError("token expired")

    def crashing():
        raise KeyError("shape changed")

    ok = codex_sub.parse(load("codex_usage.json"))
    monkeypatch.setattr(providers, "PROVIDERS", [
        ("Claude", "C", broken), ("Codex", "X", lambda: ok), ("Other", "O", crashing),
    ])
    usages = providers.fetch_all()
    assert usages[0].error == "token expired"
    assert usages[1].error is None
    assert usages[2].error == "unexpected error: KeyError"
    assert title(usages) == "C — · X 58% · O —"


def test_until():
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    assert until(now + timedelta(hours=4, minutes=32), now) == "4h 32m"
    assert until(now + timedelta(days=2, hours=5), now) == "2d 5h"
    assert until(now + timedelta(minutes=12, seconds=30), now) == "12m"
    assert until(now - timedelta(minutes=1), now) == "now"
    assert until(None, now) == "?"


def test_report_shows_errors():
    text = report([Usage(name="Claude", short="C", error="token expired")])
    assert "Claude" in text and "token expired" in text
