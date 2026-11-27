"""Decides when to fetch again before the regular refresh, after a failure that may clear soon."""

from __future__ import annotations

from datetime import datetime, timezone

from .providers.base import Usage

NETWORK_DELAYS = (5, 10, 20, 40)   # seconds; afterwards only the regular refresh tries again
TOKEN_CHECK_SECONDS = 15
REFRESH_SECONDS = 5 * 60   # regular refresh; a later Retry-After just waits for it


class RetrySchedule:
    """Times are seconds on a monotonic clock, passed in by the caller."""

    def __init__(self) -> None:
        self._attempts = 0
        self._network_at: float | None = None
        self._token_at: float | None = None
        self._rate_at: float | None = None

    def update(self, usages: list[Usage], now: float) -> None:
        """Plan the next retry from the results of a fetch."""
        if not any(u.network_error for u in usages):
            self._network_at = None
            self._attempts = 0   # the next outage gets the full series again
        elif self._network_at is None and self._attempts < len(NETWORK_DELAYS):
            # A retry already planned stays put, so an extra fetch does not push it back.
            self._network_at = now + NETWORK_DELAYS[self._attempts]
            self._attempts += 1
        expired = any(u.token_expired for u in usages)
        self._token_at = now + TOKEN_CHECK_SECONDS if expired else None
        self._rate_at = None
        waits = [rate_wait(u) for u in usages if u.rate_limited]
        if any(w is not None for w in waits):
            self._rate_at = now + max(w for w in waits if w is not None)

    def rate_due(self, now: float) -> bool:
        """True once when a Retry-After shorter than the regular refresh has passed."""
        if self._rate_at is None or now < self._rate_at:
            return False
        self._rate_at = None
        return True

    def network_due(self, now: float) -> bool:
        """True once per planned network retry."""
        if self._network_at is None or now < self._network_at:
            return False
        self._network_at = None
        return True

    def token_due(self, now: float) -> bool:
        """True every TOKEN_CHECK_SECONDS while a token is expired."""
        if self._token_at is None or now < self._token_at:
            return False
        self._token_at = now + TOKEN_CHECK_SECONDS
        return True


def rate_wait(usage: Usage, now: datetime | None = None) -> float | None:
    """Seconds until a rate-limited provider may be asked again, when sooner than the
    regular refresh; None means wait for the regular refresh."""
    if usage.retry_at is None:
        return None
    wait = max((usage.retry_at - (now or datetime.now(timezone.utc))).total_seconds(), 0)
    return wait if wait < REFRESH_SECONDS else None
