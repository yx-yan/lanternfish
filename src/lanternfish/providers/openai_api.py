"""OpenAI API spend this month (UTC), via GET /v1/organization/costs. Needs an Admin key."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

from .. import keychain
from .anthropic_api import month_start
from .base import Money, NotConfigured, ProviderError, Usage, get_json

URL = "https://api.openai.com/v1/organization/costs"
ACCOUNT = "openai-admin"
MAX_PAGES = 10


def parse_buckets(buckets: list[dict]) -> float:
    """Sum amount.value (dollars) over every result in every daily bucket."""
    total = 0.0
    for bucket in buckets:
        for result in bucket.get("results") or []:
            amount = result.get("amount") or {}
            if str(amount.get("currency", "usd")).lower() != "usd":
                raise ProviderError(f"unexpected currency {amount.get('currency')}")
            total += float(amount.get("value") or 0)
    return total


def fetch(now: datetime | None = None) -> Usage:
    key = keychain.get(ACCOUNT)
    if not key:
        raise NotConfigured
    start = month_start(now or datetime.now(timezone.utc))
    params = {"start_time": int(start.timestamp()), "bucket_width": "1d", "limit": 31}
    buckets: list[dict] = []
    for _ in range(MAX_PAGES):
        data = get_json(f"{URL}?{urllib.parse.urlencode(params)}", {"Authorization": f"Bearer {key}"})
        buckets.extend(data.get("data") or [])
        if not data.get("has_more") or not data.get("next_page"):
            break
        params["page"] = data["next_page"]
    return Usage(name="OpenAI API", short=None, money=[Money("This month", parse_buckets(buckets), "USD")])
