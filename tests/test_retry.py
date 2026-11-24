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
