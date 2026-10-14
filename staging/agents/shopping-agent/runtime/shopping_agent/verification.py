"""Direct retailer-page verification for the Shopping Agent MVP.

The MVP accepts structured ``Product``/``Offer`` JSON-LD as authoritative
page evidence.  Search-provider price or delivery fields are retained only as
discovery context.  Missing structured facts remain UNVERIFIED; the verifier
does not guess from snippets or aggregator text.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import (
    CallTelemetry,
    DiscoveryCandidate,
    RetailerEvidence,
    RunTelemetry,
    ShoppingConstraints,
    VerifiedCandidate,
)
from .settings import ShoppingConfig
from .urls import UnsafeRetailerUrlError, safe_hostname, validate_http_url


class RetailerFetchError(RuntimeError):
    """A retailer page could not be retrieved safely."""


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class PageFetchResult:
    url: str
    html: str
    checked_at: str


class RetailerPageFetcher(Protocol):
    def fetch(self, url: str, timeout: float) -> PageFetchResult:
        ...


class BrowserFallback(Protocol):
    def fetch(self, url: str, timeout: float) -> PageFetchResult:
        ...


class HttpRetailerPageFetcher:
    def __init__(self, *, max_bytes: int = 2_000_000, max_redirects: int = 3) -> None:
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects

    def fetch(self, url: str, timeout: float) -> PageFetchResult:
        try:
            current_url = validate_http_url(url, resolve_dns=True).geturl()
        except UnsafeRetailerUrlError as exc:
            raise RetailerFetchError(str(exc)) from exc
        opener = build_opener(_RejectRedirectHandler())
        for _ in range(self.max_redirects + 1):
            request = Request(
                current_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "shopping-agent-mvp/0.1",
                },
                method="GET",
            )
            try:
                response = opener.open(request, timeout=timeout)
            except HTTPError as exc:
                if 300 <= exc.code < 400:
                    location = exc.headers.get("Location")
                    if not location:
                        raise RetailerFetchError("Retailer redirect had no location.") from exc
                    try:
                        current_url = validate_http_url(
                            urljoin(current_url, location), resolve_dns=True
                        ).geturl()
                    except UnsafeRetailerUrlError as redirect_exc:
                        raise RetailerFetchError(str(redirect_exc)) from redirect_exc
                    continue
                raise RetailerFetchError("Retailer page fetch failed: HTTPError.") from exc
            except (URLError, TimeoutError, OSError) as exc:
                raise RetailerFetchError(f"Retailer page fetch failed: {type(exc).__name__}.") from exc
            with response:
                body = response.read(self.max_bytes + 1)
                final_url = response.geturl()
            if len(body) > self.max_bytes:
                raise RetailerFetchError("Retailer page exceeded the configured size limit.")
            html = body.decode("utf-8", errors="replace")
            return PageFetchResult(
                url=final_url,
                html=html,
                checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        raise RetailerFetchError("Retailer redirect limit was exceeded.")


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_json_ld = False
        self._buffer: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attributes = {key.lower(): value or "" for key, value in attrs}
        if attributes.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_json_ld:
            document = "".join(self._buffer).strip()
            if document:
                self.documents.append(document)
            self._in_json_ld = False
            self._buffer = []


def _json_ld_documents(html: str) -> list[Any]:
    parser = _JsonLdParser()
    parser.feed(html)
    documents: list[Any] = []
    for raw in parser.documents:
        try:
            documents.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return documents


def _objects(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        result = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            result.extend(item for item in graph if isinstance(item, Mapping))
        return result
    if isinstance(value, list):
        result: list[Mapping[str, Any]] = []
        for item in value:
            result.extend(_objects(item))
        return result
    return []


def _types(value: Mapping[str, Any]) -> set[str]:
    raw = value.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return {str(item).split("/")[-1].lower() for item in values if item}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, (int, float, Decimal)):
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
    elif isinstance(value, str):
        cleaned = re.sub(r"[^0-9.,-]", "", value).replace(",", "")
        if not cleaned:
            return None
        try:
            parsed = Decimal(cleaned)
        except InvalidOperation:
            return None
    else:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _explicit_lengths(values: list[str]) -> set[Decimal]:
    pattern = re.compile(
        r"(?<!\w)(\d+(?:\.\d+)?)\s*(?:-\s*)?(?:foot|feet|ft)\b", re.IGNORECASE
    )
    lengths: set[Decimal] = set()
    for value in values:
        for match in pattern.finditer(value):
            parsed = _parse_decimal(match.group(1))
            if parsed is not None:
                lengths.add(parsed)
    return lengths


def _product_text_fields(product: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("name", "description", "sku", "model"):
        value = product.get(key)
        if isinstance(value, str):
            values.append(value)
    for prop in _as_list(product.get("additionalProperty")):
        if not isinstance(prop, Mapping):
            continue
        for key in ("name", "value", "valueReference"):
            value = prop.get(key)
            if isinstance(value, str):
                values.append(value)
    return values


def _offer(product: Mapping[str, Any]) -> Mapping[str, Any] | None:
    offers = [value for value in _as_list(product.get("offers")) if isinstance(value, Mapping)]
    if not offers:
        return None
    for candidate in offers:
        availability = str(candidate.get("availability", "")).lower()
        if availability.endswith("instock"):
            return candidate
    return offers[0]


def _availability(offer: Mapping[str, Any] | None) -> bool | None:
    if offer is None:
        return None
    value = str(offer.get("availability", "")).lower().split("/")[-1]
    if value == "instock":
        return True
    if value in {"outofstock", "soldout", "discontinued", "temporarilyunavailable"}:
        return False
    return None


def _shipping_details(
    product: Mapping[str, Any],
    offer: Mapping[str, Any] | None,
    *,
    postcode: str,
    country: str,
) -> tuple[Decimal | None, str | None, str | None]:
    details: list[Mapping[str, Any]] = []
    for parent in (offer, product):
        if not isinstance(parent, Mapping):
            continue
        details.extend(item for item in _as_list(parent.get("shippingDetails")) if isinstance(item, Mapping))
    for detail in details:
        destinations = _as_list(detail.get("shippingDestination"))
        for destination in destinations or [{}]:
            if not isinstance(destination, Mapping):
                continue
            destination_postcode = destination.get("postalCode")
            destination_country = destination.get("addressCountry")
            if isinstance(destination_country, Mapping):
                destination_country = destination_country.get("value") or destination_country.get("name")
            if str(destination_postcode or "") != postcode:
                continue
            if not isinstance(destination_country, str):
                continue
            if destination_country.strip().upper() != country.upper():
                continue
            rate = detail.get("shippingRate")
            if isinstance(rate, Mapping):
                amount = _parse_decimal(rate.get("value"))
                currency = rate.get("currency")
            else:
                amount = _parse_decimal(detail.get("shippingCost"))
                currency = detail.get("currency")
            if (
                amount is not None
                and isinstance(currency, str)
                and currency.strip().upper() == "AUD"
            ):
                return amount, postcode, country.upper()
    return None, None, None


def _retailer_evidence(
    candidate: DiscoveryCandidate,
    page: PageFetchResult,
    constraints: ShoppingConstraints,
) -> RetailerEvidence:
    product = _select_product(
        _json_ld_documents(page.html), constraints.exact_length_feet
    )
    if product is None:
        return RetailerEvidence(
            retailer_url=page.url,
            checked_at=page.checked_at,
            evidence_quality="retailer_page_without_product_json_ld",
            limitation="No unambiguous structured Product evidence proved the requested variant.",
        )
    lengths = _explicit_lengths(_product_text_fields(product))
    exact_length = next(iter(lengths)) if len(lengths) == 1 else None
    offer = _offer(product)
    stock = _availability(offer)
    currency = str(offer.get("priceCurrency", "")).upper() if offer else ""
    item_price = _parse_decimal(offer.get("price")) if offer and currency == "AUD" else None
    shipping_cost, shipping_postcode, shipping_country = _shipping_details(
        product,
        offer,
        postcode=constraints.destination_postcode,
        country=constraints.destination_country,
    )
    delivered = item_price + shipping_cost if item_price is not None and shipping_cost is not None else None
    return RetailerEvidence(
        retailer_url=page.url,
        checked_at=page.checked_at,
        exact_length_feet=exact_length,
        stock=stock,
        item_price_aud=item_price,
        shipping_cost_aud=shipping_cost,
        shipping_postcode=shipping_postcode,
        shipping_country=shipping_country,
        delivered_price_aud=delivered,
        evidence_quality="retailer_json_ld",
    )


def _select_product(
    documents: list[Any], requested_length: Decimal
) -> Mapping[str, Any] | None:
    matches: list[Mapping[str, Any]] = []
    for document in documents:
        for obj in _objects(document):
            types = _types(obj)
            if "productgroup" in types:
                variants = [
                    item for item in _as_list(obj.get("hasVariant")) if isinstance(item, Mapping)
                ]
                matches.extend(
                    variant
                    for variant in variants
                    if _explicit_lengths(_product_text_fields(variant)) == {requested_length}
                )
            elif "product" in types and len(_explicit_lengths(_product_text_fields(obj))) == 1:
                matches.append(obj)
    return matches[0] if len(matches) == 1 else None


class RetailerVerifier:
    def __init__(
        self,
        config: ShoppingConfig,
        telemetry: RunTelemetry,
        *,
        fetcher: RetailerPageFetcher | None = None,
        browser_fallback: BrowserFallback | None = None,
    ) -> None:
        self.config = config
        self.telemetry = telemetry
        self.fetcher = fetcher or HttpRetailerPageFetcher()
        self.browser_fallback = browser_fallback

    def verify(self, candidate: DiscoveryCandidate, constraints: ShoppingConstraints) -> VerifiedCandidate:
        if not candidate.direct_url:
            return VerifiedCandidate(
                candidate,
                "UNVERIFIED",
                ("No direct retailer URL was supplied by discovery.",),
                RetailerEvidence(
                    retailer_url=None,
                    evidence_quality="discovery_only",
                    limitation="Aggregator result cannot establish retailer availability or delivered price.",
                ),
            )
        if self.telemetry.page_fetch_count >= self.config.budget.max_page_fetches:
            self.telemetry.record_budget_exhausted(
                "max_page_fetches",
                self.config.budget.max_page_fetches,
                self.telemetry.page_fetch_count,
            )
            return VerifiedCandidate(
                candidate,
                "UNVERIFIED",
                ("Retailer page-fetch budget exhausted.",),
                RetailerEvidence(retailer_url=candidate.direct_url, evidence_quality="budget_limited"),
            )

        started = time.perf_counter()
        try:
            page = self.fetcher.fetch(candidate.direct_url, self.config.request_timeout_seconds)
            self.telemetry.record_call(
                CallTelemetry(
                    call_type="page_fetch",
                    provider_or_tool="direct_retailer_page",
                    status="success",
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    safe_domain_or_url=safe_hostname(candidate.direct_url),
                    phase_or_node="verify",
                )
            )
        except (RetailerFetchError, TimeoutError, URLError, OSError, TypeError, ValueError) as exc:
            self.telemetry.record_call(
                CallTelemetry(
                    call_type="page_fetch",
                    provider_or_tool="direct_retailer_page",
                    status="error",
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    safe_domain_or_url=safe_hostname(candidate.direct_url),
                    error_type=type(exc).__name__,
                    phase_or_node="verify",
                )
            )
            if (
                self.browser_fallback is not None
                and self.telemetry.browser_page_count < self.config.budget.max_browser_pages
            ):
                browser_started = time.perf_counter()
                try:
                    page = self.browser_fallback.fetch(
                        candidate.direct_url,
                        self.config.request_timeout_seconds,
                    )
                except (
                    RetailerFetchError,
                    TimeoutError,
                    URLError,
                    OSError,
                    TypeError,
                    ValueError,
                ) as browser_exc:
                    self.telemetry.record_call(
                        CallTelemetry(
                            call_type="browser_page",
                            provider_or_tool="bounded_browser_fallback",
                            status="error",
                            duration_ms=max(0, int((time.perf_counter() - browser_started) * 1000)),
                            safe_domain_or_url=safe_hostname(candidate.direct_url),
                            error_type=type(browser_exc).__name__,
                            phase_or_node="browser_fallback",
                        )
                    )
                    return VerifiedCandidate(
                        candidate,
                        "UNVERIFIED",
                        ("Direct retailer page and bounded browser fallback were unavailable.",),
                        RetailerEvidence(
                            retailer_url=candidate.direct_url,
                            evidence_quality="fetch_failed",
                            limitation="Retailer evidence could not be retrieved.",
                        ),
                    )
                self.telemetry.record_call(
                    CallTelemetry(
                        call_type="browser_page",
                        provider_or_tool="bounded_browser_fallback",
                        status="success",
                        duration_ms=max(0, int((time.perf_counter() - browser_started) * 1000)),
                        safe_domain_or_url=safe_hostname(candidate.direct_url),
                        phase_or_node="browser_fallback",
                    )
                )
            else:
                if (
                    self.browser_fallback is not None
                    and self.telemetry.browser_page_count >= self.config.budget.max_browser_pages
                ):
                    self.telemetry.record_budget_exhausted(
                        "max_browser_pages",
                        self.config.budget.max_browser_pages,
                        self.telemetry.browser_page_count,
                    )
                return VerifiedCandidate(
                    candidate,
                    "UNVERIFIED",
                    ("Direct retailer page could not be retrieved.",),
                    RetailerEvidence(
                        retailer_url=candidate.direct_url,
                        evidence_quality="fetch_failed",
                        limitation="Browser fallback is disabled or budget-exhausted.",
                    ),
                )

        evidence = _retailer_evidence(candidate, page, constraints)
        reasons: list[str] = []
        if evidence.exact_length_feet is None:
            reasons.append("Exact requested length is not explicitly proven on the retailer page.")
        elif evidence.exact_length_feet != constraints.exact_length_feet:
            reasons.append("Retailer evidence proves a different product length.")
        if evidence.stock is False:
            reasons.append("Retailer evidence marks the seller or item unavailable.")
        elif evidence.stock is None:
            reasons.append("Current retailer stock is not explicitly proven.")
        if evidence.item_price_aud is None:
            reasons.append("Direct AUD item price is not explicitly proven.")
        if evidence.shipping_postcode != constraints.destination_postcode:
            reasons.append("Shipping cost to the requested postcode is not explicitly proven.")
        if evidence.delivered_price_aud is None:
            reasons.append("Delivered AUD price cannot be calculated from direct evidence.")
        elif (
            evidence.delivered_price_aud >= constraints.max_delivered_price_aud
            if constraints.budget_operator == "lt"
            else evidence.delivered_price_aud > constraints.max_delivered_price_aud
        ):
            reasons.append("Direct delivered price exceeds the maximum budget.")

        if evidence.stock is False or (
            evidence.delivered_price_aud is not None
            and (
                evidence.delivered_price_aud >= constraints.max_delivered_price_aud
                if constraints.budget_operator == "lt"
                else evidence.delivered_price_aud > constraints.max_delivered_price_aud
            )
        ) or (
            evidence.exact_length_feet is not None
            and evidence.exact_length_feet != constraints.exact_length_feet
        ):
            status = "FAIL"
        elif reasons:
            status = "UNVERIFIED"
        else:
            status = "PASS"
        return VerifiedCandidate(candidate, status, tuple(reasons), evidence)
