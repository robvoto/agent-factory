"""Bounded SerpApi discovery client.

Only safe, discovery-level fields are retained.  Google Shopping prices and
delivery text are never used as final checkout evidence.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from .models import CallTelemetry, DiscoveryCandidate, RunTelemetry, ShoppingConstraints
from .settings import ShoppingConfig


class ProviderError(RuntimeError):
    """A provider call failed without exposing provider payloads or secrets."""


class SearchBudgetExceeded(ProviderError):
    """The configured search/API budget was reached."""


class JsonTransport(Protocol):
    def get_json(self, url: str, params: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
        ...


class UrllibJsonTransport:
    def get_json(self, url: str, params: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
        query = urlencode(params)
        parsed = urlparse(url)
        request = Request(
            urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)),
            headers={"Accept": "application/json", "User-Agent": "shopping-agent-mvp/0.1"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
        except (HTTPError, URLError, HTTPException, TimeoutError, OSError, ValueError) as exc:
            raise ProviderError(f"SerpApi request failed: {type(exc).__name__}.") from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("SerpApi returned a non-object JSON response.")
        return payload


@dataclass(frozen=True)
class DiscoveryCall:
    query: str
    candidates: tuple[DiscoveryCandidate, ...]


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value.strip()


def _safe_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return parsed.netloc.lower() or None


def _direct_url(result: Mapping[str, Any]) -> str | None:
    for key in ("link", "merchant_link", "url", "product_url"):
        direct = _safe_url(result.get(key))
        if direct:
            return direct
    return None


def _candidate_from_result(result: Mapping[str, Any], position: int) -> DiscoveryCandidate | None:
    title = result.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    discovery_url = _safe_url(result.get("product_link"))
    source = result.get("source") or result.get("merchant")
    merchant = source.strip() if isinstance(source, str) and source.strip() else None
    price = result.get("price")
    delivery = result.get("delivery")
    return DiscoveryCandidate(
        candidate_id=f"serpapi-{position}",
        title=title.strip(),
        merchant=merchant,
        discovery_url=discovery_url,
        direct_url=_direct_url(result),
        discovery_price_text=price.strip() if isinstance(price, str) else None,
        discovery_delivery_text=delivery.strip() if isinstance(delivery, str) else None,
        source="serpapi.google_shopping",
    )


def _deduplicate(candidates: list[DiscoveryCandidate]) -> list[DiscoveryCandidate]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[DiscoveryCandidate] = []
    for candidate in candidates:
        key = (
            (candidate.direct_url or "").lower(),
            (candidate.title or "").lower(),
            (candidate.merchant or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


class SerpApiDiscovery:
    """Configurable Google Shopping discovery with explicit call budgets."""

    def __init__(
        self,
        config: ShoppingConfig,
        telemetry: RunTelemetry,
        *,
        transport: JsonTransport | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.config = config
        self.telemetry = telemetry
        self.transport = transport or UrllibJsonTransport()
        self.env = env

    def search(self, query: str, constraints: ShoppingConstraints) -> DiscoveryCall:
        budget = self.config.budget
        if self.telemetry.search_call_count >= budget.max_search_calls:
            raise SearchBudgetExceeded("Shopping search-call budget exhausted.")
        if self.telemetry.api_call_count >= budget.max_api_calls:
            raise SearchBudgetExceeded("Shopping API-call budget exhausted.")
        api_key = self.config.api_key(self.env)

        params = {
            "engine": "google_shopping",
            "q": query,
            "location": self.config.serpapi_location,
            "google_domain": self.config.serpapi_google_domain,
            "gl": self.config.serpapi_country,
            "hl": self.config.serpapi_language,
            "api_key": api_key,
        }
        started = time.perf_counter()
        try:
            payload = self.transport.get_json(
                self.config.serpapi_endpoint,
                params,
                self.config.request_timeout_seconds,
            )
        except (ProviderError, TypeError, ValueError) as exc:
            self.telemetry.record_call(
                CallTelemetry(
                    call_type="search",
                    provider_or_tool="serpapi.google_shopping",
                    status="error",
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    safe_domain_or_url=_safe_domain(self.config.serpapi_endpoint),
                    error_type=type(exc).__name__,
                )
            )
            raise ProviderError("SerpApi discovery failed.") from exc

        if payload.get("error"):
            self.telemetry.record_call(
                CallTelemetry(
                    call_type="search",
                    provider_or_tool="serpapi.google_shopping",
                    status="error",
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    safe_domain_or_url=_safe_domain(self.config.serpapi_endpoint),
                    error_type="ProviderResponseError",
                )
            )
            raise ProviderError("SerpApi returned an error response.")
        self.telemetry.record_call(
            CallTelemetry(
                call_type="search",
                provider_or_tool="serpapi.google_shopping",
                status="success",
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                safe_domain_or_url=_safe_domain(self.config.serpapi_endpoint),
            )
        )
        raw_results = payload.get("shopping_results", [])
        if not isinstance(raw_results, list):
            raise ProviderError("SerpApi returned an invalid shopping_results field.")
        candidates = [
            candidate
            for position, result in enumerate(raw_results, start=1)
            if isinstance(result, Mapping)
            for candidate in [_candidate_from_result(result, position)]
            if candidate is not None
        ]
        return DiscoveryCall(query=query, candidates=tuple(_deduplicate(candidates)))
