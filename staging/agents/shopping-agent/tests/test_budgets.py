from __future__ import annotations

from decimal import Decimal

import pytest

from src.budgets import BudgetExceeded, BudgetLimits, BudgetTracker, LimitNotConfigured


@pytest.mark.parametrize(
    ("metric", "limit_name"),
    [
        ("llm_calls", "max_llm_calls"),
        ("search_calls", "max_search_calls"),
        ("api_calls", "max_api_calls"),
        ("page_fetches", "max_page_fetches"),
        ("browser_pages", "max_browser_pages"),
        ("browser_actions", "max_browser_actions"),
        ("retries", "max_retries"),
    ],
)
def test_each_count_guardrail_stops_at_its_configured_limit(metric, limit_name):
    tracker = BudgetTracker(BudgetLimits(**{limit_name: 1}))
    tracker.reserve(metric)

    with pytest.raises(BudgetExceeded, match=limit_name):
        tracker.reserve(metric)


def test_searchapi_cap_is_three_even_when_configuration_is_higher():
    tracker = BudgetTracker(BudgetLimits(max_search_calls=9))
    for _ in range(3):
        tracker.reserve("search_calls", provider_id="SerpApi")

    with pytest.raises(BudgetExceeded, match="max_search_calls"):
        tracker.reserve("search_calls", provider_id="SerpApi")


def test_unconfigured_page_api_and_browser_limits_do_not_guess_defaults():
    tracker = BudgetTracker(BudgetLimits())
    for metric in ("api_calls", "page_fetches", "browser_pages"):
        with pytest.raises(LimitNotConfigured):
            tracker.reserve(metric)


def test_token_cost_guardrails_and_warning_thresholds():
    tracker = BudgetTracker(
        BudgetLimits(
            max_total_tokens=5,
            max_estimated_cost_usd=Decimal("0.10"),
            warning_thresholds={"max_total_tokens": 4, "max_estimated_cost_usd": Decimal("0.05")},
        )
    )
    tracker.record_usage(usage_tokens=4, cost_usd=Decimal("0.05"))
    assert tracker.warnings == [
        "warning_threshold_reached:max_total_tokens",
        "warning_threshold_reached:max_estimated_cost_usd",
    ]
    with pytest.raises(BudgetExceeded, match="max_total_tokens"):
        tracker.record_usage(usage_tokens=2)

    cost_tracker = BudgetTracker(BudgetLimits(max_estimated_cost_usd=Decimal("0.10")))
    with pytest.raises(BudgetExceeded, match="max_estimated_cost_usd"):
        cost_tracker.record_usage(cost_usd=Decimal("0.11"))
