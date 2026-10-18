"""Configurable operation limits. Missing limits disable the relevant operation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping


class BudgetExceeded(RuntimeError):
    def __init__(self, metric: str):
        super().__init__(metric)
        self.metric = metric


class LimitNotConfigured(RuntimeError):
    def __init__(self, metric: str):
        super().__init__(metric)
        self.metric = metric


@dataclass(frozen=True)
class BudgetLimits:
    max_llm_calls: int | None = None
    max_total_tokens: int | None = None
    max_estimated_cost_usd: Decimal | None = None
    max_search_calls: int | None = None
    max_api_calls: int | None = None
    max_page_fetches: int | None = None
    max_browser_pages: int | None = None
    max_browser_actions: int | None = None
    max_retries: int | None = None
    warning_thresholds: Mapping[str, int | Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "max_llm_calls",
            "max_total_tokens",
            "max_search_calls",
            "max_api_calls",
            "max_page_fetches",
            "max_browser_pages",
            "max_browser_actions",
            "max_retries",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.max_estimated_cost_usd is not None and (
            not isinstance(self.max_estimated_cost_usd, Decimal) or self.max_estimated_cost_usd < 0
        ):
            raise ValueError("max_estimated_cost_usd must be a non-negative Decimal or None")
        for name, value in self.warning_thresholds.items():
            if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or value < 0:
                raise ValueError(f"warning threshold {name!r} must be non-negative")


class BudgetTracker:
    """Tracks actual use and provides a pre-call reservation for count limits."""

    _COUNT_LIMITS = {
        "llm_calls": "max_llm_calls",
        "total_tokens": "max_total_tokens",
        "search_calls": "max_search_calls",
        "api_calls": "max_api_calls",
        "page_fetches": "max_page_fetches",
        "browser_pages": "max_browser_pages",
        "browser_actions": "max_browser_actions",
        "retries": "max_retries",
    }

    def __init__(self, limits: BudgetLimits):
        self.limits = limits
        self.counts: dict[str, int] = {name: 0 for name in self._COUNT_LIMITS}
        self.estimated_cost_usd = Decimal("0")
        self.warnings: list[str] = []

    def reserve(self, metric: str, amount: int = 1, *, provider_id: str | None = None) -> None:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("reservation amount must be a positive integer")
        limit_name = self._COUNT_LIMITS[metric]
        limit = getattr(self.limits, limit_name)
        if metric == "search_calls" and provider_id and provider_id.casefold() == "serpapi":
            # The workflow-wide hard ceiling is three, even if configuration is higher.
            limit = 3 if limit is None else min(limit, 3)
        if limit is None:
            raise LimitNotConfigured(limit_name)
        if self.counts[metric] + amount > limit:
            raise BudgetExceeded(limit_name)
        self.counts[metric] += amount
        self._warn_if_needed(limit_name, self.counts[metric])

    def record_usage(self, *, usage_tokens: int = 0, cost_usd: Decimal | None = None) -> None:
        if not isinstance(usage_tokens, int) or isinstance(usage_tokens, bool) or usage_tokens < 0:
            raise ValueError("usage_tokens must be a non-negative integer")
        if cost_usd is not None and (not isinstance(cost_usd, Decimal) or cost_usd < 0):
            raise ValueError("cost_usd must be a non-negative Decimal or None")
        if usage_tokens:
            self.counts["total_tokens"] += usage_tokens
            limit = self.limits.max_total_tokens
            self._warn_if_needed("max_total_tokens", self.counts["total_tokens"])
            if limit is not None and self.counts["total_tokens"] > limit:
                raise BudgetExceeded("max_total_tokens")
        if cost_usd is not None:
            self.estimated_cost_usd += cost_usd
            limit_cost = self.limits.max_estimated_cost_usd
            self._warn_if_needed("max_estimated_cost_usd", self.estimated_cost_usd)
            if limit_cost is not None and self.estimated_cost_usd > limit_cost:
                raise BudgetExceeded("max_estimated_cost_usd")

    def note_unconfigured(self, metric: str) -> None:
        warning = f"operation_disabled_limit_not_configured:{metric}"
        if warning not in self.warnings:
            self.warnings.append(warning)

    def _warn_if_needed(self, metric: str, current: int | Decimal) -> None:
        threshold = self.limits.warning_thresholds.get(metric)
        if threshold is not None and current >= threshold:
            warning = f"warning_threshold_reached:{metric}"
            if warning not in self.warnings:
                self.warnings.append(warning)
