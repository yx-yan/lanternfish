"""Decides when to fetch again before the regular refresh, after a failure that may clear soon."""

from __future__ import annotations

from .providers.base import Usage

NETWORK_DELAYS = (5, 10, 20, 40)   # seconds; afterwards only the regular refresh tries again
TOKEN_CHECK_SECONDS = 15


class RetrySchedule:
    """Times are seconds on a monotonic clock, passed in by the caller."""

    def __init__(self) -> None:
        self._attempts = 0
        self._network_at: float | None = None
        self._token_at: float | None = None

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
