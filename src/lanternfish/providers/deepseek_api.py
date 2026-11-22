"""DeepSeek API balance, via GET https://api.deepseek.com/user/balance. Needs a normal API key."""

from __future__ import annotations

from .. import keychain
from .base import Money, NotConfigured, ProviderError, Usage, get_json

URL = "https://api.deepseek.com/user/balance"
ACCOUNT = "deepseek"


def parse(data: dict) -> Usage:
    infos = data.get("balance_infos") or []
    if not infos:
        raise ProviderError("no balance in response")
    usage = Usage(name="DeepSeek API", short=None)
    for info in infos:
        usage.money.append(Money("Balance", float(info.get("total_balance") or 0), info.get("currency", "?")))
    if data.get("is_available") is False:
        usage.error = "balance too low to make calls"
    return usage


def fetch() -> Usage:
    key = keychain.get(ACCOUNT)
    if not key:
        raise NotConfigured
    return parse(get_json(URL, {"Authorization": f"Bearer {key}"}))
