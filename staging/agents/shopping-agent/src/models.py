"""Typed contracts shared by the shopping workflow and provider adapters."""

from __future__ import annotations

import ipaddress
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class CandidateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class ShoppingRequest:
    """Explicit request data; this type does not infer constraints from prose."""

    query: str
    hard_constraints: Mapping[str, Any] = field(default_factory=dict)
    preferences: Mapping[str, Any] = field(default_factory=dict)
    discovery_queries: tuple[str, ...] = ()
    requested_action: str = "shopping_research"
    request_id: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(self.hard_constraints, Mapping):
            raise ValueError("hard_constraints must be a mapping")
        if not isinstance(self.preferences, Mapping):
            raise ValueError("preferences must be a mapping")
        if not isinstance(self.discovery_queries, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.discovery_queries
        ):
            raise ValueError("discovery_queries must contain non-empty strings")
        if self.request_id is not None and not isinstance(self.request_id, str):
            raise ValueError("request_id must be a string or None")
        if self.run_id is not None and not isinstance(self.run_id, str):
            raise ValueError("run_id must be a string or None")
        if not isinstance(self.requested_action, str) or self.requested_action not in {
            "shopping_research",
            "purchase",
            "checkout",
            "account_change",
            "order_change",
        }:
            raise ValueError("requested_action must be an explicit supported action")


@dataclass(frozen=True)
class ConstraintLedger:
    hard: Mapping[str, Any]
    preferences: Mapping[str, Any]

    @classmethod
    def capture(cls, request: ShoppingRequest) -> "ConstraintLedger":
        # Copy once and expose read-only mappings so adapters cannot mutate the request.
        hard = deepcopy(dict(request.hard_constraints))
        preferences = deepcopy(dict(request.preferences))
        return cls(MappingProxyType(hard), MappingProxyType(preferences))

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {"hard": deepcopy(dict(self.hard)), "preferences": deepcopy(dict(self.preferences))}


@dataclass(frozen=True)
class DiscoveryCandidate:
    candidate_id: str
    url: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        if not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("candidate url must be a non-empty string")
        from urllib.parse import urlsplit

        try:
            parsed = urlsplit(self.url)
        except ValueError as exc:
            raise ValueError("candidate url must be a valid public page URL") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("candidate url must be a public HTTP(S) page without embedded credentials")
        hostname = parsed.hostname.rstrip(".").casefold()
        if "%" in hostname or hostname == "localhost" or hostname.endswith(
            (".localhost", ".local", ".internal", ".lan", ".home.arpa")
        ):
            raise ValueError("candidate url must use a public host")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            if "." not in hostname:
                raise ValueError("candidate url must use a public host")
        else:
            if not address.is_global:
                raise ValueError("candidate url must use a public IP address")


@dataclass(frozen=True)
class StructuredEvidence:
    """Structured data extracted from a retailer page, never from a search result."""

    source_url: str
    source_kind: str
    json_ld: Any

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, str) or self.source_kind not in {"retailer_page", "browser_page"}:
            raise ValueError("evidence source_kind must identify a direct retailer page")


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None
    api_calls: int | None = None
    retries: int = 0
    browser_pages: int | None = None
    browser_actions: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "api_calls",
            "retries",
            "browser_pages",
            "browser_actions",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.estimated_cost_usd is not None and (
            not isinstance(self.estimated_cost_usd, Decimal) or self.estimated_cost_usd < 0
        ):
            raise ValueError("estimated_cost_usd must be a non-negative Decimal or None")


@dataclass(frozen=True)
class SearchResponse:
    candidates: tuple[DiscoveryCandidate, ...]
    usage: ProviderUsage = ProviderUsage()


@dataclass(frozen=True)
class PageResponse:
    evidence: StructuredEvidence | None
    usage: ProviderUsage = ProviderUsage()


@dataclass(frozen=True)
class ClassifiedCandidate:
    candidate: DiscoveryCandidate
    status: CandidateStatus
    reasons: tuple[str, ...]
    product_name: str | None = None
    seller_name: str | None = None
    price: Decimal | None = None
    shipping_cost: Decimal | None = None
    delivered_price: Decimal | None = None
    currency: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "url": self.candidate.url,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "product_name": self.product_name,
            "seller_name": self.seller_name,
            "price": _decimal_text(self.price),
            "shipping_cost": _decimal_text(self.shipping_cost),
            "delivered_price": _decimal_text(self.delivered_price),
            "currency": self.currency,
        }


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")
