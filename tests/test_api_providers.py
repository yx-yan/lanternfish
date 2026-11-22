"""API spend providers. Fixtures follow the documented response examples (no real account data)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lanternfish.format import money, report, title
from lanternfish.providers import anthropic_api, deepseek_api, openai_api
from lanternfish.providers.base import Money, NotConfigured, ProviderError, Usage

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 22, 6, 30, tzinfo=timezone.utc)


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_month_start_is_utc_midnight_on_the_first():
    assert anthropic_api.month_start(NOW) == datetime(2026, 11, 1, tzinfo=timezone.utc)


def test_anthropic_rows_are_cents():
    assert anthropic_api.parse_rows([{"currency": "USD", "amount": "1234.5"}, {"amount": "65.5"}]) == 13.0


def test_anthropic_rejects_other_currency():
    with pytest.raises(ProviderError):
        anthropic_api.parse_rows([{"currency": "EUR", "amount": "1"}])


def test_anthropic_fetch_follows_pages(monkeypatch):
    pages = [load("anthropic_cost_page1.json"), load("anthropic_cost_page2.json")]
    seen = []

    def fake_get(url, headers):
        seen.append((url, headers))
        return pages[len(seen) - 1]

    monkeypatch.setattr(anthropic_api.keychain, "get", lambda account: "sk-ant-admin-test")
    monkeypatch.setattr(anthropic_api, "get_json", fake_get)
    usage = anthropic_api.fetch(NOW)
    assert usage.money == [Money("This month", 42.5, "USD")]
    assert usage.short is None
    assert "starting_at=2026-11-01T00%3A00%3A00Z" in seen[0][0]
    assert "page=page_abc" in seen[1][0]
    assert seen[0][1]["anthropic-beta"] == "analytics-usage-cost-2026-08-24"


def test_openai_sums_every_bucket():
    assert openai_api.parse_buckets(load("openai_costs.json")["data"]) == pytest.approx(1.31)


def test_openai_fetch_params(monkeypatch):
    seen = []
    monkeypatch.setattr(openai_api.keychain, "get", lambda account: "sk-admin-test")
    monkeypatch.setattr(openai_api, "get_json", lambda url, headers: seen.append(url) or load("openai_costs.json"))
    usage = openai_api.fetch(NOW)
    assert usage.money[0].amount == pytest.approx(1.31)
    assert f"start_time={int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())}" in seen[0]


def test_deepseek_parse():
    usage = deepseek_api.parse(load("deepseek_balance.json"))
    assert usage.money == [Money("Balance", 110.0, "CNY")]
    assert usage.error is None


def test_deepseek_unavailable_is_flagged():
    data = {"is_available": False, "balance_infos": [{"currency": "CNY", "total_balance": "0.00"}]}
    assert deepseek_api.parse(data).error == "balance too low to make calls"


@pytest.mark.parametrize("module", [anthropic_api, openai_api, deepseek_api])
def test_missing_key_is_not_configured(monkeypatch, module):
    monkeypatch.setattr(module.keychain, "get", lambda account: None)
    with pytest.raises(NotConfigured):
        module.fetch()


def test_money_formatting():
    assert money(Money("x", 1234.5, "USD")) == "$1,234.50"
    assert money(Money("x", 110, "CNY")) == "¥110.00"
    assert money(Money("x", 3, "JPY")) == "3.00 JPY"


def test_api_rows_stay_out_of_the_title_but_show_in_report():
    usages = [Usage("Codex", "X"), Usage("DeepSeek API", None, money=[Money("Balance", 110, "CNY")])]
    assert title(usages) == "X —"
    assert "Balance  ¥110.00" in report(usages)
