import json
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lanternfish import providers
from lanternfish.format import report, title, until
from lanternfish.providers import Provider, base, claude_sub, codex_sub
from lanternfish.providers.base import NotConfigured, ProviderError, Usage

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
    def unconfigured():
        raise NotConfigured

    monkeypatch.setattr(providers, "PROVIDERS", [
        Provider("Claude", "C", broken), Provider("Codex", "X", lambda: ok),
        Provider("Other", "O", crashing), Provider("DeepSeek API", None, unconfigured, "deepseek"),
    ])
    usages = providers.fetch_all()
    assert usages[0].error == "token expired"
    assert usages[1].error is None
    assert usages[2].error == "unexpected error: KeyError"
    assert len(usages) == 3  # the unconfigured provider is left out
    assert title(usages) == "C — · X 42% · O —"


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


# --- Gemini (Antigravity) ---------------------------------------------------

from lanternfish.providers import gemini_sub  # noqa: E402


def _keychain(monkeypatch, token):
    blob = "go-keyring-base64:" + __import__("base64").b64encode(json.dumps({"token": token}).encode()).decode()

    class Done:
        stdout = blob + "\n"

    monkeypatch.setattr(gemini_sub.subprocess, "run", lambda *a, **k: Done)


def test_gemini_parse_real_response():
    usage = gemini_sub.parse(load("gemini_models.json"), plan="Pro")
    assert [w.label for w in usage.windows] == ["Gemini"]
    assert all(w.used_percent == 0 for w in usage.windows)
    assert usage.windows[0].resets_at.tzinfo is not None
    assert (usage.name, usage.short, usage.plan) == ("Gemini", "G", "Pro")


def test_gemini_parse_shows_lowest_gemini_model():
    data = {"models": {
        "gemini-3-flash": {"displayName": "Flash", "quotaInfo": {"remainingFraction": 0.8}},
        "gemini-pro": {"displayName": "Pro", "quotaInfo": {"remainingFraction": 0.25,
                                                           "resetTime": "2026-11-27T09:22:05Z"}},
        "tab_flash": {"quotaInfo": {"remainingFraction": 0}},          # no displayName: internal
        "claude-opus": {"displayName": "Opus", "quotaInfo": {"remainingFraction": 0.1}},  # other pool
    }}
    usage = gemini_sub.parse(data)
    assert [(w.label, w.used_percent) for w in usage.windows] == [("Gemini", 75.0)]
    assert usage.windows[0].resets_at == datetime(2026, 11, 27, 9, 22, 5, tzinfo=timezone.utc)


def test_gemini_parse_empty_response_is_error():
    with pytest.raises(ProviderError):
        gemini_sub.parse({"models": {}})


def test_gemini_plan_name():
    assert gemini_sub.plan_name({"paidTier": {"name": "Google AI Pro"}}) == "Pro"
    assert gemini_sub.plan_name({}) is None


def test_gemini_reads_token(monkeypatch):
    later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _keychain(monkeypatch, {"access_token": "t", "expiry": later})
    assert gemini_sub.read_token() == "t"
    assert gemini_sub.token_ready()


def test_gemini_expired_token(monkeypatch):
    earlier = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    _keychain(monkeypatch, {"access_token": "t", "expiry": earlier})
    with pytest.raises(base.TokenExpired):
        gemini_sub.read_token()
    assert not gemini_sub.token_ready()


def test_gemini_without_antigravity_is_hidden(monkeypatch):
    def fail(*a, **k):
        raise gemini_sub.subprocess.CalledProcessError(44, "security")

    monkeypatch.setattr(gemini_sub.subprocess, "run", fail)
    with pytest.raises(NotConfigured):
        gemini_sub.read_token()


def test_gemini_limits_from_local_summary():
    usage = gemini_sub.parse(load("gemini_models.json"), plan="Pro",
                             summary=load("gemini_local_quota_summary.json"))
    assert [w.label for w in usage.windows] == [
        "Gemini 5-hour", "Gemini weekly", "Claude & GPT 5-hour", "Claude & GPT weekly"]
    assert all(w.used_percent == 0 for w in usage.windows)
    assert usage.windows[1].resets_at - usage.windows[0].resets_at > timedelta(days=6)
    assert [w.resets_at for w in usage.windows[2:]] == [None, None]   # not given for this group
    assert usage.primary.label == "Gemini 5-hour"   # menu bar title


def test_gemini_falls_back_to_pool_without_gemini_group():
    assert [w.label for w in gemini_sub.parse(load("gemini_models.json")).windows] == ["Gemini"]
    only_3p = {"response": {"groups": [{"displayName": "Claude and GPT models",
                                        "buckets": [{"window": "5h", "remainingFraction": 0.2}]}]}}
    usage = gemini_sub.parse(load("gemini_models.json"), summary=only_3p)
    assert [(w.label, round(w.used_percent)) for w in usage.windows] == [
        ("Gemini", 0), ("Claude & GPT 5-hour", 80)]


def test_gemini_group_name():
    assert gemini_sub.group_name("Gemini Models") == "Gemini"
    assert gemini_sub.group_name("Claude and GPT models") == "Claude & GPT"


def test_window_without_reset_time_text():
    from lanternfish.format import resets_text, window_line
    window = base.Window("Claude & GPT weekly", 25.0, None)
    assert resets_text(window) == "Reset time not given"
    assert window_line(window) == "Claude & GPT weekly  75% left"


def test_gemini_local_summary_skips_stale_and_missing_daemons(tmp_path, monkeypatch):
    assert gemini_sub.local_summary(tmp_path / "missing") is None
    (tmp_path / "hub_1.json").write_text(json.dumps({"pid": 999999, "httpPort": 1, "csrfToken": "x"}))
    (tmp_path / "hub_2.json").write_text("not json")
    opened = []
    monkeypatch.setattr(gemini_sub.urllib.request, "urlopen", lambda *a, **k: opened.append(a))
    monkeypatch.setattr(gemini_sub.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    assert gemini_sub.local_summary(tmp_path) is None
    assert opened == []   # no request to a daemon that has exited


def test_gemini_local_limits_when_cloud_unavailable(monkeypatch):
    summary = load("gemini_local_quota_summary.json")
    monkeypatch.setattr(gemini_sub, "local_summary", lambda: summary)
    monkeypatch.setattr(gemini_sub, "_last_plan", "Pro")

    def expired():
        raise base.TokenExpired("token expired; open `agy` to renew it")

    monkeypatch.setattr(gemini_sub, "_fetch_cloud", expired)
    usage = gemini_sub.fetch()
    assert usage.error is None and usage.plan == "Pro"
    assert usage.primary.label == "Gemini 5-hour"
    # Without agy's local server the expiry still shows.
    monkeypatch.setattr(gemini_sub, "local_summary", lambda: None)
    with pytest.raises(base.TokenExpired):
        gemini_sub.fetch()
