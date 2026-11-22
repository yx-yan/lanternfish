"""Anthropic API spend this month (UTC), via the Usage and Cost Analytics API (beta).

Needs an Admin API key (sk-ant-admin...). Data lands within about 4 hours, so today's spend lags.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

from .. import keychain
from .base import Money, NotConfigured, ProviderError, Usage, get_json

URL = "https://api.anthropic.com/v1/organizations/analytics/cost"
ACCOUNT = "anthropic-admin"
MAX_PAGES = 20


def month_start(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def parse_rows(rows: list[dict]) -> float:
    """Sum row amounts (decimal strings in cents) into dollars."""
    cents = 0.0
    for row in rows:
        if row.get("currency", "USD") != "USD":
            raise ProviderError(f"unexpected currency {row.get('currency')}")
        cents += float(row.get("amount") or 0)
    return cents / 100


def fetch(now: datetime | None = None) -> Usage:
    key = keychain.get(ACCOUNT)
    if not key:
        raise NotConfigured
    start = month_start(now or datetime.now(timezone.utc))
    # No group_by and no bucket width: one row totalling the whole range.
    params = {"starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ")}
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "analytics-usage-cost-2026-08-24",
    }
    rows: list[dict] = []
    for _ in range(MAX_PAGES):
        data = get_json(f"{URL}?{urllib.parse.urlencode(params)}", headers)
        rows.extend(data.get("data") or [])
        if not data.get("has_more") or not data.get("next_page"):
            break
        params["page"] = data["next_page"]
    return Usage(name="Anthropic API", short=None, money=[Money("This month", parse_rows(rows), "USD")])
