"""Decide when to notify: once per usage window, when it first reaches the threshold."""

from __future__ import annotations

from .format import left, percent, until
from .providers.base import Usage

THRESHOLD = 80.0


class AlertTracker:
    def __init__(self, threshold: float = THRESHOLD) -> None:
        self.threshold = threshold
        # (provider, window label, reset time) already notified; a new reset time is a new window.
        self._sent: set[tuple[str, str, str]] = set()

    def check(self, usages: list[Usage]) -> list[tuple[str, str]]:
        """Return (title, message) for every window that newly crossed the threshold."""
        alerts = []
        for usage in usages:
            for window in usage.windows:
                if window.used_percent < self.threshold:
                    continue
                key = (usage.name, window.label, window.resets_at.isoformat() if window.resets_at else "")
                if key in self._sent:
                    continue
                self._sent.add(key)
                alerts.append((
                    f"{usage.name} {window.label}: {percent(left(window))} left",
                    f"Resets in {until(window.resets_at)}.",
                ))
        return alerts
