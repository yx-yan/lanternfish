"""Turn Usage objects into menu bar and menu text."""

from __future__ import annotations

from datetime import datetime, timezone

from .providers.base import Usage, Window

MISSING = "—"


def percent(value: float) -> str:
    return f"{round(value)}%"


def until(when: datetime | None, now: datetime | None = None) -> str:
    """Compact countdown: '4h 32m', '2d 5h', '12m', 'now'."""
    if when is None:
        return "?"
    now = now or datetime.now(timezone.utc)
    minutes = int((when - now).total_seconds() // 60)
    if minutes <= 0:
        return "now"
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def title(usages: list[Usage]) -> str:
    """Menu bar title, e.g. 'C 13% · X 58%' (the shortest window of each provider)."""
    parts = []
    for usage in usages:
        window = usage.primary
        parts.append(f"{usage.short} {percent(window.used_percent) if window else MISSING}")
    return " · ".join(parts)


def window_line(window: Window, now: datetime | None = None) -> str:
    return f"{window.label}  {percent(window.used_percent)}  ·  resets in {until(window.resets_at, now)}"


def header_line(usage: Usage) -> str:
    return f"{usage.name} ({usage.plan})" if usage.plan else usage.name


def report(usages: list[Usage], now: datetime | None = None) -> str:
    """Plain-text report for the CLI."""
    lines = []
    for usage in usages:
        lines.append(header_line(usage))
        if usage.error:
            lines.append(f"  {MISSING} {usage.error}")
        for window in usage.windows:
            lines.append(f"  {window_line(window, now)}")
    return "\n".join(lines)
