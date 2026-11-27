import urllib.error

import pytest

from lanternfish import providers
from lanternfish.providers import Provider, base, claude_sub
from lanternfish.providers.base import ProviderError, TokenExpired, Usage
from lanternfish.retry import RetrySchedule

OFFLINE = [Usage("Codex", "X", error="network error", network_error=True)]
EXPIRED = [Usage("Claude", "C", error="token expired", token_expired=True)]
OK = [Usage("Claude", "C")]


def test_network_retries_back_off_then_stop():
    retry, now = RetrySchedule(), 0.0
    for delay in (5, 10, 20, 40):
        retry.update(OFFLINE, now)
        assert not retry.network_due(now + delay - 1)
        now += delay
        assert retry.network_due(now)
        assert not retry.network_due(now)  # once per plan
    retry.update(OFFLINE, now)
    assert not retry.network_due(now + 10_000)


def test_extra_failed_fetch_does_not_delay_a_planned_retry():
    retry = RetrySchedule()
    retry.update(OFFLINE, 0)
    retry.update(OFFLINE, 1)  # startup fetches twice; so can a manual refresh
    assert retry.network_due(5)


def test_success_cancels_and_resets_the_backoff():
    retry = RetrySchedule()
    retry.update(OFFLINE, 0)
    retry.update(OFFLINE, 5)
    retry.update(OK, 6)
    assert not retry.network_due(1000)
    retry.update(OFFLINE, 1000)
    assert retry.network_due(1005)


def test_expired_token_is_checked_every_15_seconds_until_renewed():
    retry = RetrySchedule()
    retry.update(EXPIRED, 0)
    assert not retry.token_due(14)
    assert retry.token_due(15)
    assert not retry.token_due(29)
    assert retry.token_due(30)
    assert not retry.network_due(1000)
    retry.update(OK, 31)
    assert not retry.token_due(1000)


def test_other_errors_are_not_retried_early():
    retry = RetrySchedule()
    retry.update([Usage("Codex", "X", error="HTTP 500")], 0)
    assert not retry.network_due(1000) and not retry.token_due(1000)


def test_fetch_all_marks_retryable_failures(monkeypatch):
    def offline(*a, **k):
        raise urllib.error.URLError("down")

    def expired():
        raise TokenExpired("token expired")

    def rejected():
        raise ProviderError("token rejected")

    monkeypatch.setattr(base.urllib.request, "urlopen", offline)
    monkeypatch.setattr(providers, "PROVIDERS", [
        Provider("A", "A", lambda: base.get_json("https://example.invalid", {})),
        Provider("B", "B", expired), Provider("C", "C", rejected),
    ])
    flags = [(u.network_error, u.token_expired) for u in providers.fetch_all()]
    assert flags == [(True, False), (False, True), (False, False)]


@pytest.mark.parametrize("ready", [True, False])
def test_token_renewed_only_asks_expired_providers(monkeypatch, ready):
    monkeypatch.setattr(providers, "PROVIDERS", [
        Provider("Claude", "C", lambda: None, token_ready=lambda: ready)])
    assert providers.token_renewed(EXPIRED) is ready
    assert providers.token_renewed(OK) is False


def test_claude_token_ready(monkeypatch):
    monkeypatch.setattr(claude_sub, "read_token", lambda: ("t", "max"))
    assert claude_sub.token_ready()

    def expired():
        raise TokenExpired("token expired")

    monkeypatch.setattr(claude_sub, "read_token", expired)
    assert not claude_sub.token_ready()


# --- rate limits (HTTP 429) -------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from lanternfish.format import error_line  # noqa: E402
from lanternfish.providers.base import Window  # noqa: E402
from lanternfish.retry import rate_wait  # noqa: E402


def _http_error(code, headers):
    return urllib.error.HTTPError("https://x", code, "msg", headers, None)


def test_429_becomes_rate_limited_with_retry_after(monkeypatch):
    def fail(*a, **k):
        raise _http_error(429, {"Retry-After": "90"})

    monkeypatch.setattr(base.urllib.request, "urlopen", fail)
    with pytest.raises(base.RateLimited) as caught:
        base.get_json("https://x", {})
    assert caught.value.retry_after == 90


def test_retry_after_parsing():
    assert base.retry_after("120") == 120
    assert base.retry_after(None) is None
    assert base.retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert base.retry_after("-5") is None
    assert base.retry_after("0") is None   # sent while still limited: no immediate retry


def test_fetch_all_marks_rate_limited(monkeypatch):
    def limited():
        raise base.RateLimited(retry_after=60)

    monkeypatch.setattr(providers, "PROVIDERS", [Provider("Claude", "C", limited)])
    [usage] = providers.fetch_all()
    assert usage.rate_limited and not usage.network_error and usage.error == "rate limited"
    assert timedelta(seconds=55) < usage.retry_at - datetime.now(timezone.utc) <= timedelta(seconds=60)


def test_rate_limited_provider_keeps_last_good_numbers():
    last_good = {}
    good = Usage("Claude", "C", windows=[Window("5-hour", 30.0, None)], plan="pro")
    providers.keep_last_good([good], last_good)
    [shown] = providers.keep_last_good([Usage("Claude", "C", error="rate limited", rate_limited=True)], last_good)
    assert shown.rate_limited and shown.windows == good.windows and shown.plan == "pro"
    assert shown.stale_at is not None
    # Other errors still show nothing, so a broken token is not hidden behind old numbers.
    [broken] = providers.keep_last_good([Usage("Claude", "C", error="HTTP 500")], last_good)
    assert broken.windows == []


def test_rate_limited_note():
    now = datetime(2026, 11, 27, 4, 0, tzinfo=timezone.utc)
    stale = datetime(2026, 11, 27, 3, 50, tzinfo=timezone.utc)
    shown = Usage("Claude", "C", error="rate limited", rate_limited=True, stale_at=stale,
                  windows=[Window("5-hour", 30.0, None)])
    assert error_line(shown, now) == (
        f"rate limited; retrying at next refresh  ·  data from {stale.astimezone().strftime('%H:%M')}")
    soon = Usage("Claude", "C", error="rate limited", rate_limited=True, retry_at=now + timedelta(minutes=2))
    assert error_line(soon, now) == "— rate limited; retrying in 2m"
    due = Usage("Claude", "C", error="rate limited", rate_limited=True, retry_at=now)
    assert error_line(due, now) == "— rate limited; retrying now"
    assert error_line(Usage("Codex", "X", error="network error")) == "— network error"


def test_retry_after_shorter_than_refresh_is_honoured():
    now_utc = datetime.now(timezone.utc)
    retry = RetrySchedule()
    retry.update([Usage("Claude", "C", error="rate limited", rate_limited=True,
                        retry_at=now_utc + timedelta(seconds=60))], 0)
    assert not retry.rate_due(50)
    assert retry.rate_due(61)
    assert not retry.rate_due(62)   # once
    # A Retry-After beyond the regular refresh just waits for it.
    long = Usage("Claude", "C", error="rate limited", rate_limited=True, retry_at=now_utc + timedelta(hours=1))
    assert rate_wait(long) is None
    retry.update([long], 0)
    assert not retry.rate_due(10_000)
