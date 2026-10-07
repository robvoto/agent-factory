"""Small, JSON-safe data contracts for the Shopping Agent MVP.

The discovery provider is deliberately not authoritative.  A candidate only
becomes a recommendation after direct retailer evidence has supplied every
mandatory field in ``RetailerEvidence``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

CandidateStatus = Literal["PASS", "FAIL", "UNVERIFIED"]
BudgetOperator = Literal["lt", "lte"]


def money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


@dataclass(frozen=True)
class ShoppingConstraints:
    original_request: str
    product_terms: str
    exact_length_feet: Decimal
    max_delivered_price_aud: Decimal
    budget_operator: BudgetOperator
    destination_country: str
    destination_postcode: str
    requires_delivery: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_request": self.original_request,
            "product_terms": self.product_terms,
            "exact_length_feet": str(self.exact_length_feet),
            "max_delivered_price_aud": money(self.max_delivered_price_aud),
            "budget_operator": self.budget_operator,
            "destination_country": self.destination_country,
            "destination_postcode": self.destination_postcode,
            "requires_delivery": self.requires_delivery,
        }


@dataclass(frozen=True)
class DiscoveryCandidate:
    candidate_id: str
    title: str
    merchant: str | None
    discovery_url: str | None
    direct_url: str | None
    discovery_price_text: str | None
    discovery_delivery_text: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "merchant": self.merchant,
            "discovery_url": self.discovery_url,
            "direct_url": self.direct_url,
            "discovery_price": self.discovery_price_text,
            "discovery_delivery": self.discovery_delivery_text,
            "source": self.source,
        }


@dataclass(frozen=True)
class RetailerEvidence:
    retailer_url: str | None = None
    checked_at: str | None = None
    exact_length_feet: Decimal | None = None
    stock: bool | None = None
    item_price_aud: Decimal | None = None
    shipping_cost_aud: Decimal | None = None
    shipping_postcode: str | None = None
    shipping_country: str | None = None
    delivered_price_aud: Decimal | None = None
    evidence_quality: str = "none"
    limitation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retailer_url": self.retailer_url,
            "checked_at": self.checked_at,
            "exact_length_feet": (
                str(self.exact_length_feet) if self.exact_length_feet is not None else None
            ),
            "stock": self.stock,
            "item_price_aud": money(self.item_price_aud),
            "shipping_cost_aud": money(self.shipping_cost_aud),
            "shipping_postcode": self.shipping_postcode,
            "shipping_country": self.shipping_country,
            "delivered_price_aud": money(self.delivered_price_aud),
            "evidence_quality": self.evidence_quality,
            "limitation": self.limitation,
        }


@dataclass(frozen=True)
class VerifiedCandidate:
    candidate: DiscoveryCandidate
    status: CandidateStatus
    reasons: tuple[str, ...]
    evidence: RetailerEvidence

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.candidate.to_dict(),
            "status": self.status,
            "reasons": list(self.reasons),
            "retailer_evidence": self.evidence.to_dict(),
        }


@dataclass
class CallTelemetry:
    call_type: str
    provider_or_tool: str
    status: str
    duration_ms: int
    safe_domain_or_url: str | None = None
    error_type: str | None = None
    run_id: str | None = None
    phase_or_node: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase_or_node": self.phase_or_node,
            "call_type": self.call_type,
            "provider_or_tool": self.provider_or_tool,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "safe_domain_or_url": self.safe_domain_or_url,
            "error_type": self.error_type,
        }


@dataclass
class RunTelemetry:
    request_id: str
    run_id: str
    started_at: str
    _started_monotonic: float
    finished_at: str | None = None
    duration_ms: int | None = None
    stop_reason: str | None = None
    candidate_discovered_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    unverified_count: int = 0
    llm_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens_when_available: int = 0
    estimated_cost_usd: str = "0.00"
    search_call_count: int = 0
    api_call_count: int = 0
    page_fetch_count: int = 0
    browser_page_count: int = 0
    browser_action_count: int = 0
    retry_count: int = 0
    error_count: int = 0
    budget_exhausted_events: list[dict[str, int | str]] = field(default_factory=list)
    calls: list[CallTelemetry] = field(default_factory=list)

    def record_call(self, call: CallTelemetry) -> None:
        if call.run_id is None:
            call.run_id = self.run_id
        self.calls.append(call)
        if call.call_type == "search":
            self.search_call_count += 1
            self.api_call_count += 1
        elif call.call_type == "api":
            self.api_call_count += 1
        elif call.call_type == "page_fetch":
            self.page_fetch_count += 1
        elif call.call_type == "browser_page":
            self.browser_page_count += 1
        elif call.call_type == "browser_action":
            self.browser_action_count += 1
        if call.status == "error":
            self.error_count += 1

    def record_budget_exhausted(self, metric: str, limit: int, observed: int) -> None:
        self.budget_exhausted_events.append(
            {"metric": metric, "limit": limit, "observed": observed}
        )

    def finish(self, *, stop_reason: str, now_iso: str, monotonic_now: float) -> None:
        self.finished_at = now_iso
        self.duration_ms = max(0, int((monotonic_now - self._started_monotonic) * 1000))
        self.stop_reason = stop_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "stop_reason": self.stop_reason,
            "candidate_discovered_count": self.candidate_discovered_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "unverified_count": self.unverified_count,
            "llm_call_count": self.llm_call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens_when_available": self.cached_tokens_when_available,
            "estimated_cost_usd": self.estimated_cost_usd,
            "search_call_count": self.search_call_count,
            "api_call_count": self.api_call_count,
            "page_fetch_count": self.page_fetch_count,
            "browser_page_count": self.browser_page_count,
            "browser_action_count": self.browser_action_count,
            "retry_count": self.retry_count,
            "error_count": self.error_count,
            "budget_exhausted_events": self.budget_exhausted_events,
            "calls": [call.to_dict() for call in self.calls],
        }
