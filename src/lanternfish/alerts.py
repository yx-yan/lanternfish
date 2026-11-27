"""Decide when to notify: as a usage window runs low, and when it resets after that."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .format import left, percent, until
from .providers.base import Usage, Window

LEVELS = (20, 10, 5, 0)   # percent left; one notification each per window
STATE_FILE = Path.home() / "Library" / "Application Support" / "Lanternfish" / "alerts.json"
# The endpoints report a slightly different reset time on every call;
# only a clearly later one means a new window.
NEW_WINDOW = timedelta(hours=1)


def level_of(window: Window) -> int | None:
    """The lowest level reached, judged on the rounded percentage shown to the user."""
    reached = [level for level in LEVELS if round(left(window)) <= level]
    return min(reached) if reached else None


class AlertTracker:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path   # None keeps the state in memory only
        # "provider|window label" -> (lowest level notified, reset time of that window)
        self._sent: dict[str, tuple[int, datetime | None]] = self._load()

    def check(self, usages: list[Usage]) -> list[tuple[str, str]]:
        """Return (title, message) for every window that reached a new level or reset."""
        alerts = []
        before = dict(self._sent)
        for usage in usages:
            for window in usage.windows:
                key = f"{usage.name}|{window.label}"
                name = f"{usage.name} {window.label}"
                level = level_of(window)
                sent_level, sent_reset = self._sent.get(key, (None, None))
                was_reset = sent_level is not None and _is_new_window(window, sent_reset, level)
                if was_reset:
                    del self._sent[key]
                    sent_level = sent_reset = None
                if level is not None and (sent_level is None or level < sent_level):
                    # One alert even if several levels, or a reset too, were passed since the last fetch.
                    alerts.append((f"{name}: {percent(left(window))} left",
                                   f"Resets in {until(window.resets_at)}." if window.resets_at else ""))
                    self._sent[key] = (level, window.resets_at or sent_reset)
                elif was_reset:
                    alerts.append((f"{name}: reset, {percent(left(window))} left",
                                   f"Next reset in {until(window.resets_at)}." if window.resets_at else "Ready to use."))
                elif sent_level is not None and sent_reset is None and window.resets_at:
                    self._sent[key] = (sent_level, window.resets_at)
        if self._sent != before:
            self._save()
        return alerts

    def _load(self) -> dict[str, tuple[int, datetime | None]]:
        if self._path is None:
            return {}
        try:
            sent = {}
            for key, (level, reset) in json.loads(self._path.read_text()).items():
                when = datetime.fromisoformat(reset) if reset is not None else None
                if level not in LEVELS or (when and when.tzinfo is None):
                    return {}
                sent[key] = (level, when)
            return sent
        except (OSError, ValueError, TypeError, AttributeError):
            return {}   # missing or damaged: at worst one repeated alert

    def _save(self) -> None:
        if self._path is None:
            return
        data = {key: [level, reset.isoformat() if reset else None] for key, (level, reset) in self._sent.items()}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data))
        except OSError as exc:
            print(f"could not save alert state: {exc}")


def _is_new_window(window: Window, sent_reset: datetime | None, level: int | None) -> bool:
    if window.resets_at is None or sent_reset is None:
        return level is None   # no times to compare: being above every level again means it reset
    return window.resets_at - sent_reset >= NEW_WINDOW
