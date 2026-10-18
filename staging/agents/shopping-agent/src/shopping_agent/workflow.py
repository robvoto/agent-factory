"""Fail-closed, provider-injected Shopping Agent workflow.

This module contains no network client. Runtime adapters are injected by the
caller, which keeps credentials outside workflow state and makes the stages
fully testable offline.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any, Callable, Mapping, TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from langgraph.graph import END, START, StateGraph


MAX_DISCOVERY_REQUESTS = 3
_LENGTH_UNITS_TO_METRES = {
    "mm": Decimal("0.001"),
    "millimeter": Decimal("0.001"),
    "millimeters": Decimal("0.001"),
    "millimetre": Decimal("0.001"),
    "millimetres": Decimal("0.001"),
    "cm": Decimal("0.01"),
    "centimeter": Decimal("0.01"),
    "centimeters": Decimal("0.01"),
    "centimetre": Decimal("0.01"),
    "centimetres": Decimal("0.01"),
    "m": Decimal("1"),
    "meter": Decimal("1"),
    "meters": Decimal("1"),
    "metre": Decimal("1"),
    "metres": Decimal("1"),
    "in": Decimal("0.0254"),
    "inch": Decimal("0.0254"),
    "inches": Decimal("0.0254"),
    "ft": Decimal("0.3048"),
    "foot": Decimal("0.3048"),
    "feet": Decimal("0.3048"),
}
_SCHEMA_LENGTH_UNITS = {
    "MMT": "mm",
    "CMT": "cm",
    "MTR": "m",
    "INH": "in",
    "FOT": "ft",
}
_UNAVAILABLE_VALUES = {"outofstock", "soldout", "discontinued", "preorder"}
_IN_STOCK_VALUES = {"instock", "limitedavailability"}
_PURCHASE_ACTION = re.compile(
    r"\b(?:checkout|check\s*out|place\s+(?:the\s+)?order|"
    r"add\s+to\s+(?:my\s+)?cart|complete\s+(?:the\s+)?purchase|"
    r"change\s+(?:my\s+)?account|update\s+(?:my\s+)?account|"
    r"cancel\s+(?:my\s+)?order|change\s+(?:my\s+)?order|"
    r"(?:buy|purchase|order)\s+(?:it|this|that|the|a|an|me|for\s+me)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ShoppingConstraints:
    request: str
    postcode: str | None
    required_length_m: Decimal | None
    length_was_mentioned: bool
    budget_aud: Decimal | None
    budget_item_only: bool
    clarification_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveryRequest:
    query: str
    engine: str = "google_shopping"
    postcode: str | None = None


@dataclass(frozen=True)
class BrowserRequest:
    product_url: str
    postcode: str
    missing_facts: tuple[str, ...]
    max_pages: int | None
    max_actions: int | None


@dataclass(frozen=True)
class ProviderUsage:
    estimated_cost_usd: Decimal | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    browser_pages: int | None = None
    browser_actions: int | None = None
    retry_count: int = 0

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "cached_tokens", "browser_pages", "browser_actions", "retry_count"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.estimated_cost_usd is not None:
            if not isinstance(self.estimated_cost_usd, Decimal) or self.estimated_cost_usd < 0:
                raise ValueError("estimated_cost_usd must be a non-negative Decimal or None")


@dataclass(frozen=True)
class ProviderCall:
    value: Any
    usage: ProviderUsage = field(default_factory=ProviderUsage)


@dataclass(frozen=True)
class ShoppingProviders:
    """Injected adapters. Each callable performs one attempt and returns usage."""

    google_shopping_search: Callable[[DiscoveryRequest], ProviderCall] | None = None
    fetch_product_page: Callable[[str], ProviderCall] | None = None
    browser_inspect_product: Callable[[BrowserRequest], ProviderCall] | None = None
    estimate_cost_usd: Callable[[str], Decimal | None] | None = None


@dataclass(frozen=True)
class ShoppingConfig:
    """Optional runtime controls. None means no configured limit."""

    max_search_calls: int | None = None
    max_api_calls: int | None = None
    max_page_fetches: int | None = None
    max_browser_pages: int | None = None
    max_browser_actions: int | None = None
    max_retries: int | None = None
    max_llm_calls: int | None = None
    max_total_tokens: int | None = None
    max_estimated_cost_usd: Decimal | None = None
    warning_thresholds: Mapping[str, int | Decimal] = field(default_factory=dict)
    additional_discovery_queries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "max_search_calls",
            "max_api_calls",
            "max_page_fetches",
            "max_browser_pages",
            "max_browser_actions",
            "max_retries",
            "max_llm_calls",
            "max_total_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.max_estimated_cost_usd is not None:
            if not isinstance(self.max_estimated_cost_usd, Decimal) or self.max_estimated_cost_usd < 0:
                raise ValueError("max_estimated_cost_usd must be a non-negative Decimal or None")
        for metric, threshold in self.warning_thresholds.items():
            if metric == "estimated_cost_usd":
                threshold = Decimal(str(threshold))
                if threshold < 0:
                    raise ValueError(f"warning threshold for {metric} must be non-negative")
            elif not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0:
                raise ValueError(f"warning threshold for {metric} must be a non-negative integer")
            limit_name = {
                "search_call_count": "max_search_calls",
                "api_call_count": "max_api_calls",
                "page_fetch_count": "max_page_fetches",
                "browser_page_count": "max_browser_pages",
                "browser_action_count": "max_browser_actions",
                "retry_count": "max_retries",
                "llm_call_count": "max_llm_calls",
                "input_tokens": "max_total_tokens",
                "estimated_cost_usd": "max_estimated_cost_usd",
            }.get(metric)
            if limit_name is None:
                raise ValueError(f"unsupported warning metric: {metric}")
            limit = getattr(self, limit_name)
            if limit_name == "max_estimated_cost_usd" and limit is not None:
                limit = Decimal(str(limit))
            if metric == "search_call_count":
                limit = MAX_DISCOVERY_REQUESTS if limit is None else min(MAX_DISCOVERY_REQUESTS, limit)
            if limit is not None and threshold >= limit and threshold > 0:
                raise ValueError(f"warning threshold for {metric} must be below its hard limit")
        if len(self.additional_discovery_queries) > MAX_DISCOVERY_REQUESTS - 1:
            raise ValueError("at most two additional discovery queries may be configured")


class ProviderError(RuntimeError):
    """A provider adapter failed without exposing its raw error text to telemetry."""


class WorkflowState(TypedDict, total=False):
    task: str
    request_id: str
    run_id: str
    started_at: str
    started_clock: float
    parsed: dict[str, Any]
    refusal_reason: str | None
    discoveries: list[dict[str, Any]]
    candidate_results: list[dict[str, Any]]
    warnings: list[str]
    telemetry: dict[str, Any]
    output: dict[str, Any]
    stop_reason: str | None
    exhausted_metric: str | None
    provider_unavailable: bool


@dataclass(frozen=True)
class ProductOfferEvidence:
    product_name: str
    page_url: str
    retailer: str
    length_m: Decimal | None
    in_stock: bool | None
    item_price_aud: Decimal | None
    shipping_price_aud: Decimal | None
    shipping_postcode: str | None
    checked_at: str
    schema_product: bool = True
    schema_offer: bool = True


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_jsonld = False
        self._parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "script" and "ld+json" in (values.get("type") or "").lower():
            self._inside_jsonld = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_jsonld:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._inside_jsonld:
            self.documents.append("".join(self._parts))
            self._parts = []
            self._inside_jsonld = False


def parse_constraints(task: str) -> ShoppingConstraints:
    """Read explicit length, Australian postcode, and AUD budget wording."""

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    normalized = task.strip()
    postcode_match = re.search(r"\bpost\s*code\s*[:#-]?\s*(\d{4})\b", normalized, re.I)
    postcode = postcode_match.group(1) if postcode_match else None

    length_pattern = re.compile(
        r"\b(?:exact(?:ly)?\s+|(?:exact\s+)?length(?:\s+(?:of|is))?\s*[:=]?\s*(?:exactly\s+)?|"
        r"long\s+)(\d+(?:\.\d+)?)\s*"
        r"(millimetres?|millimeters?|mm|centimetres?|centimeters?|cm|"
        r"metres?|meters?|m|inches?|inch|in|feet|foot|ft)\b",
        re.I,
    )
    length_match = length_pattern.search(normalized)
    if length_match is None:
        length_match = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(millimetres?|millimeters?|mm|centimetres?|centimeters?|cm|"
            r"metres?|meters?|m|inches?|inch|in|feet|foot|ft)\b",
            normalized,
            re.I,
        )
    length_m = None
    if length_match:
        amount = Decimal(length_match.group(1))
        unit = length_match.group(2).lower()
        length_m = amount * _LENGTH_UNITS_TO_METRES[unit]
    length_was_mentioned = bool(re.search(r"\blength\b", normalized, re.I))

    budget_pattern = re.compile(
        r"(?:(AUD|A\$|\$)\s*(\d[\d,]*(?:\.\d{1,2})?)|"
        r"(\d[\d,]*(?:\.\d{1,2})?)\s*(AUD))",
        re.I,
    )
    budget_match = budget_pattern.search(normalized)
    budget = None
    budget_currency_ambiguous = False
    if budget_match:
        currency = (budget_match.group(1) or budget_match.group(4) or "").upper()
        value = budget_match.group(2) or budget_match.group(3)
        if currency in {"AUD", "A$"}:
            budget = Decimal(value.replace(",", ""))
        elif currency == "$":
            budget_currency_ambiguous = True

    item_only = bool(
        re.search(r"\b(?:item\s+price\s+only|excluding\s+(?:delivery|shipping)|before\s+shipping)\b", normalized, re.I)
    )
    questions: list[str] = []
    if postcode is None:
        questions.append("What Australian postcode should I use to verify delivery and the delivered price?")
    if length_was_mentioned and length_m is None:
        questions.append("What exact product length and unit do you require?")
    if budget_currency_ambiguous:
        questions.append("Does the stated dollar budget mean AUD?")
    return ShoppingConstraints(
        request=normalized,
        postcode=postcode,
        required_length_m=length_m,
        length_was_mentioned=length_was_mentioned,
        budget_aud=budget,
        budget_item_only=item_only,
        clarification_questions=tuple(questions),
    )


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _types(value: Any) -> set[str]:
    raw = value.get("@type", []) if isinstance(value, dict) else []
    if isinstance(raw, str):
        raw = [raw]
    return {str(entry).rsplit("/", 1)[-1].casefold() for entry in raw}


def _walk_json(value: Any):
    if isinstance(value, list):
        for child in value:
            yield from _walk_json(child)
    elif isinstance(value, dict):
        yield value
        for key in ("@graph", "mainEntity", "itemListElement", "hasVariant"):
            if key in value:
                yield from _walk_json(value[key])


def _schema_length_m(product: Mapping[str, Any]) -> Decimal | None:
    properties = product.get("additionalProperty", [])
    if isinstance(properties, Mapping):
        properties = [properties]
    for prop in properties if isinstance(properties, list) else []:
        if not isinstance(prop, Mapping) or str(prop.get("name", "")).strip().casefold() not in {
            "length",
            "product length",
            "overall length",
        }:
            continue
        value = _decimal(prop.get("value"))
        unit = str(prop.get("unitText") or prop.get("unitCode") or "").strip()
        if unit.upper() in _SCHEMA_LENGTH_UNITS:
            unit = _SCHEMA_LENGTH_UNITS[unit.upper()]
        factor = _LENGTH_UNITS_TO_METRES.get(unit.lower())
        if value is not None and value > 0 and factor is not None:
            return value * factor
    direct_length = product.get("length")
    if isinstance(direct_length, Mapping):
        value = _decimal(direct_length.get("value"))
        unit = str(direct_length.get("unitText") or direct_length.get("unitCode") or "").strip()
        if unit.upper() in _SCHEMA_LENGTH_UNITS:
            unit = _SCHEMA_LENGTH_UNITS[unit.upper()]
        factor = _LENGTH_UNITS_TO_METRES.get(unit.lower())
        if value is not None and value > 0 and factor is not None:
            return value * factor
    return None


def _stock(offer: Mapping[str, Any]) -> bool | None:
    value = str(offer.get("availability", "")).rsplit("/", 1)[-1].casefold()
    if value in _IN_STOCK_VALUES:
        return True
    if value in _UNAVAILABLE_VALUES:
        return False
    return None


def _postal_codes(region: Any) -> set[str]:
    if isinstance(region, list):
        result: set[str] = set()
        for part in region:
            result.update(_postal_codes(part))
        return result
    if isinstance(region, str):
        return {region} if re.fullmatch(r"\d{4}", region) else set()
    if isinstance(region, Mapping):
        value = region.get("postalCode") or region.get("postalCodeRange")
        if isinstance(value, str) and re.fullmatch(r"\d{4}", value):
            return {value}
        if isinstance(region.get("address"), Mapping):
            return _postal_codes(region["address"])
    return set()


def _shipping_for_postcode(offer: Mapping[str, Any], postcode: str) -> Decimal | None:
    details = offer.get("shippingDetails", [])
    if isinstance(details, Mapping):
        details = [details]
    matches: set[Decimal] = set()
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, Mapping):
            continue
        destinations = detail.get("shippingDestination", [])
        eligible = detail.get("eligibleRegion", [])
        if isinstance(destinations, Mapping):
            destinations = [destinations]
        destination_codes = _postal_codes(destinations)
        eligible_codes = _postal_codes(eligible)
        if postcode not in destination_codes | eligible_codes:
            continue
        rate = detail.get("shippingRate")
        if not isinstance(rate, Mapping) or str(rate.get("priceCurrency", "")).upper() != "AUD":
            continue
        amount = _decimal(rate.get("price", rate.get("value")))
        if amount is not None and amount >= 0:
            matches.add(amount)
    return next(iter(matches)) if len(matches) == 1 else None


def extract_product_offers(
    page: str | Mapping[str, Any], page_url: str, postcode: str | None = None
) -> list[ProductOfferEvidence]:
    """Extract only explicit schema.org Product/Offer evidence for a direct page."""

    if isinstance(page, str):
        parser = _JsonLdParser()
        parser.feed(page)
        roots = []
        for raw in parser.documents:
            try:
                roots.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    elif isinstance(page, Mapping):
        roots = [page]
    else:
        return []

    host = _safe_host(page_url)
    if host is None:
        return []
    checked_at = _utc_now()
    results: list[ProductOfferEvidence] = []
    for root in roots:
        for node in _walk_json(root):
            if "product" not in _types(node):
                continue
            if node.get("hasVariant"):
                continue
            offers = node.get("offers", [])
            if isinstance(offers, Mapping):
                offers = [offers]
            if not isinstance(offers, list):
                continue
            product_name = str(node.get("name") or "").strip()
            length_m = _schema_length_m(node)
            for offer in offers:
                if not isinstance(offer, Mapping) or "offer" not in _types(offer):
                    continue
                currency = str(offer.get("priceCurrency", "")).upper()
                item_price = _decimal(offer.get("price")) if currency == "AUD" else None
                if item_price is not None and item_price < 0:
                    item_price = None
                results.append(
                    ProductOfferEvidence(
                        product_name=product_name,
                        page_url=page_url,
                        retailer=host,
                        length_m=length_m,
                        in_stock=_stock(offer),
                        item_price_aud=item_price,
                        shipping_price_aud=_shipping_for_postcode(offer, postcode) if postcode else None,
                        shipping_postcode=postcode if postcode and _shipping_for_postcode(offer, postcode) is not None else None,
                        checked_at=checked_at,
                    )
                )
    return results


def _extract_for_postcode(page: Any, page_url: str, postcode: str) -> list[ProductOfferEvidence]:
    return extract_product_offers(page, page_url, postcode)


def classify_evidence(
    evidence: ProductOfferEvidence,
    constraints: ShoppingConstraints,
    expected_host: str,
) -> tuple[str, tuple[str, ...], Decimal | None]:
    """Return PASS, FAIL, or UNVERIFIED from direct Product/Offer facts only."""

    failures: list[str] = []
    unknown: list[str] = []
    if not evidence.schema_product or not evidence.schema_offer:
        unknown.append("direct_product_offer_evidence")
    if _safe_host(evidence.page_url) != expected_host or evidence.retailer != expected_host:
        unknown.append("direct_retailer_page_identity")

    if evidence.length_m is None:
        unknown.append("exact_length")
    elif constraints.required_length_m is not None and evidence.length_m != constraints.required_length_m:
        failures.append("length_mismatch")
    if evidence.in_stock is False:
        failures.append("out_of_stock")
    elif evidence.in_stock is None:
        unknown.append("stock_status")
    if evidence.item_price_aud is None:
        unknown.append("item_price_aud")
    if evidence.shipping_postcode != constraints.postcode or evidence.shipping_price_aud is None:
        unknown.append("postcode_specific_shipping_aud")

    delivered = None
    if evidence.item_price_aud is not None and evidence.shipping_price_aud is not None:
        delivered = evidence.item_price_aud + evidence.shipping_price_aud
    if delivered is None:
        unknown.append("delivered_price_aud")
    elif constraints.budget_aud is not None:
        budget_basis = evidence.item_price_aud if constraints.budget_item_only else delivered
        if budget_basis is not None and budget_basis > constraints.budget_aud:
            failures.append("over_budget")

    if failures:
        return "FAIL", tuple(dict.fromkeys(failures)), delivered
    if unknown:
        return "UNVERIFIED", tuple(dict.fromkeys(unknown)), delivered
    return "PASS", (), delivered


def _safe_host(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            return None
        if re.search(r"(^|\.)google\.[a-z.]+$", host) or re.search(r"(^|\.)googleusercontent\.com$", host):
            return None
        return host
    except ValueError:
        return None


def _safe_url(url: str) -> str | None:
    host = _safe_host(url)
    if host is None:
        return None
    parsed = urlsplit(url)
    safe_query_keys = {"variant", "sku", "size", "length", "color", "colour", "option"}
    safe_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.casefold() in safe_query_keys and re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value)
    ]
    return urlunsplit(("https", host, parsed.path or "/", urlencode(safe_query), ""))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _candidate_from_result(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    title = str(raw.get("title") or raw.get("name") or "").strip()
    raw_url = raw.get("link") or raw.get("product_link") or raw.get("url")
    if not title or not isinstance(raw_url, str):
        return None
    safe_url = _safe_url(raw_url)
    host = _safe_host(raw_url)
    if safe_url is None or host is None:
        return None
    return {"name": title, "url": safe_url, "request_url": safe_url, "host": host}


def _missing_facts(evidence: ProductOfferEvidence | None, postcode: str) -> tuple[str, ...]:
    if evidence is None:
        return ("direct_product_offer_evidence", "exact_length", "stock", "item_price_aud", "shipping_aud")
    missing: list[str] = []
    if evidence.length_m is None:
        missing.append("exact_length")
    if evidence.in_stock is None:
        missing.append("stock")
    if evidence.item_price_aud is None:
        missing.append("item_price_aud")
    if evidence.shipping_postcode != postcode or evidence.shipping_price_aud is None:
        missing.append("postcode_specific_shipping_aud")
    return tuple(missing)


def _build_workflow(providers: ShoppingProviders, config: ShoppingConfig):
    def parse_node(state: WorkflowState) -> dict[str, Any]:
        _increment(state["telemetry"], "component_counts", "parse_constraints")
        task = state["task"]
        if _PURCHASE_ACTION.search(task):
            return {
                "refusal_reason": "purchase_or_account_change_out_of_scope",
                "stop_reason": "purchase_or_account_change_out_of_scope",
                "telemetry": state["telemetry"],
            }
        constraints = parse_constraints(task)
        return {
            "parsed": {**constraints.__dict__, "clarification_questions": list(constraints.clarification_questions)},
            "stop_reason": "needs_clarification" if constraints.clarification_questions else None,
            "telemetry": state["telemetry"],
        }

    def discovery_node(state: WorkflowState) -> dict[str, Any]:
        telemetry = state["telemetry"]
        _increment(telemetry, "component_counts", "google_shopping_discovery")
        parsed = state["parsed"]
        if providers.google_shopping_search is None:
            return {"discoveries": [], "provider_unavailable": True, "stop_reason": "google_shopping_provider_unavailable", "telemetry": telemetry}
        queries = [parsed["request"]]
        for query in config.additional_discovery_queries:
            trimmed = query.strip()
            if trimmed and trimmed not in queries and len(queries) < MAX_DISCOVERY_REQUESTS:
                queries.append(trimmed)
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in queries:
            blocked = _check_budget(telemetry, config, "search_call_count", "max_search_calls")
            if blocked:
                telemetry["warnings"].append(blocked)
                _mark_budget(telemetry, "search_call_count")
                return {"discoveries": found, "stop_reason": "budget_exhausted", "exhausted_metric": "search_call_count", "telemetry": telemetry}
            blocked = _check_budget(telemetry, config, "api_call_count", "max_api_calls")
            if blocked:
                telemetry["warnings"].append(blocked)
                _mark_budget(telemetry, "api_call_count")
                return {"discoveries": found, "stop_reason": "budget_exhausted", "exhausted_metric": "api_call_count", "telemetry": telemetry}
            if not _cost_preflight(providers, config, "google_shopping", telemetry):
                _mark_budget(telemetry, "estimated_cost_usd")
                return {"discoveries": found, "stop_reason": "budget_exhausted", "exhausted_metric": "estimated_cost_usd", "telemetry": telemetry}
            _increment(telemetry, "search_call_count")
            _increment(telemetry, "api_call_count")
            call_start = time.perf_counter()
            try:
                response = providers.google_shopping_search(
                    DiscoveryRequest(query=query, postcode=parsed["postcode"])
                )
            except ProviderError as exc:
                _record_call(telemetry, state["run_id"], "discovery", "google_shopping_search", "serpapi-google-shopping", call_start, "error", type(exc).__name__)
                if _cost_limit_reached(config, telemetry):
                    _mark_budget(telemetry, "estimated_cost_usd")
                    return {"discoveries": found, "stop_reason": "budget_exhausted", "exhausted_metric": "estimated_cost_usd", "telemetry": telemetry}
                continue
            if not isinstance(response, ProviderCall):
                raise TypeError("google_shopping_search must return ProviderCall")
            _record_call(telemetry, state["run_id"], "discovery", "google_shopping_search", "serpapi-google-shopping", call_start, "ok", usage=response.usage)
            rows = response.value if isinstance(response.value, list) else []
            for raw in rows:
                candidate = _candidate_from_result(raw)
                if candidate is None or candidate["url"] in seen:
                    continue
                seen.add(candidate["url"])
                found.append(candidate)
            if _cost_limit_reached(config, telemetry):
                _mark_budget(telemetry, "estimated_cost_usd")
                return {"discoveries": found, "stop_reason": "budget_exhausted", "exhausted_metric": "estimated_cost_usd", "telemetry": telemetry}
        return {"discoveries": found, "telemetry": telemetry}

    def verification_node(state: WorkflowState) -> dict[str, Any]:
        telemetry = state["telemetry"]
        _increment(telemetry, "component_counts", "direct_retailer_verification")
        parsed = state["parsed"]
        postcode = parsed["postcode"]
        results: list[dict[str, Any]] = []
        discoveries = state.get("discoveries", [])
        verification_stopped = False
        if providers.browser_inspect_product is None:
            telemetry["browser_fallback_status"] = "not_configured"
        elif config.max_browser_pages is None or config.max_browser_actions is None:
            telemetry["browser_fallback_status"] = "disabled_missing_limits"
        else:
            telemetry["browser_fallback_status"] = "not_needed"
        for candidate_index, candidate in enumerate(discoveries):
            evidence_list: list[ProductOfferEvidence] = []
            evidence: ProductOfferEvidence | None = None
            direct_available = providers.fetch_product_page is not None
            if direct_available:
                blocked = _check_budget(telemetry, config, "page_fetch_count", "max_page_fetches")
                if blocked:
                    results.append(_unverified_result(candidate, "page_fetch_budget_exhausted"))
                    state["stop_reason"] = "budget_exhausted"
                    state["exhausted_metric"] = "page_fetch_count"
                    _mark_budget(telemetry, "page_fetch_count")
                    verification_stopped = True
                    results.extend(_unverified_result(other, "verification_not_attempted_after_budget_stop") for other in discoveries[candidate_index + 1 :])
                    break
                if not _cost_preflight(providers, config, "retailer_page", telemetry):
                    results.append(_unverified_result(candidate, "provider_cost_budget_exhausted"))
                    state["stop_reason"] = "budget_exhausted"
                    state["exhausted_metric"] = "estimated_cost_usd"
                    _mark_budget(telemetry, "estimated_cost_usd")
                    verification_stopped = True
                    results.extend(_unverified_result(other, "verification_not_attempted_after_budget_stop") for other in discoveries[candidate_index + 1 :])
                    break
                _increment(telemetry, "page_fetch_count")
                call_start = time.perf_counter()
                try:
                    response = providers.fetch_product_page(candidate["request_url"])
                except ProviderError as exc:
                    _record_call(telemetry, state["run_id"], "verification", "page_fetch", "retailer-page-fetch", call_start, "error", type(exc).__name__, candidate["url"])
                    if _cost_limit_reached(config, telemetry):
                        state["stop_reason"] = "budget_exhausted"
                        state["exhausted_metric"] = "estimated_cost_usd"
                        _mark_budget(telemetry, "estimated_cost_usd")
                        verification_stopped = True
                else:
                    if not isinstance(response, ProviderCall):
                        raise TypeError("fetch_product_page must return ProviderCall")
                    value = response.value
                    page = value.get("html", value.get("evidence")) if isinstance(value, Mapping) else value
                    final_url = value.get("final_url", candidate["request_url"]) if isinstance(value, Mapping) else candidate["request_url"]
                    final_host = _safe_host(final_url) if isinstance(final_url, str) else None
                    if final_host == candidate["host"]:
                        evidence_list = _extract_for_postcode(page, final_url, postcode)
                        evidence = evidence_list[0] if evidence_list else None
                    _record_call(telemetry, state["run_id"], "verification", "page_fetch", "retailer-page-fetch", call_start, "ok", usage=response.usage, url=candidate["url"])
                    if _cost_limit_reached(config, telemetry):
                        state["stop_reason"] = "budget_exhausted"
                        state["exhausted_metric"] = "estimated_cost_usd"
                        _mark_budget(telemetry, "estimated_cost_usd")
                        verification_stopped = True

            missing = tuple(
                dict.fromkeys(
                    fact
                    for item in (evidence_list or [evidence])
                    for fact in _missing_facts(item, postcode)
                )
            )
            if missing and providers.browser_inspect_product is not None:
                limits_configured = config.max_browser_pages is not None and config.max_browser_actions is not None
                if limits_configured:
                    if _check_budget(telemetry, config, "browser_page_count", "max_browser_pages"):
                        state["stop_reason"] = "budget_exhausted"
                        state["exhausted_metric"] = "browser_page_count"
                        _mark_budget(telemetry, "browser_page_count")
                        verification_stopped = True
                    elif _check_budget(telemetry, config, "browser_action_count", "max_browser_actions"):
                        state["stop_reason"] = "budget_exhausted"
                        state["exhausted_metric"] = "browser_action_count"
                        _mark_budget(telemetry, "browser_action_count")
                        verification_stopped = True
                    elif _cost_preflight(providers, config, "browser", telemetry):
                        remaining_pages = config.max_browser_pages - telemetry["browser_page_count"]
                        remaining_actions = config.max_browser_actions - telemetry["browser_action_count"]
                        call_start = time.perf_counter()
                        try:
                            response = providers.browser_inspect_product(
                                BrowserRequest(candidate["request_url"], postcode, missing, remaining_pages, remaining_actions)
                            )
                        except ProviderError as exc:
                            _record_call(telemetry, state["run_id"], "verification", "browser_fallback", "browser", call_start, "error", type(exc).__name__, candidate["url"])
                            telemetry["browser_page_count"] = None
                            telemetry["browser_action_count"] = None
                            telemetry["browser_fallback_status"] = "usage_unavailable"
                            state["stop_reason"] = "budget_exhausted"
                            state["exhausted_metric"] = "browser_usage"
                            _mark_budget(telemetry, "browser_usage")
                            verification_stopped = True
                        else:
                            if not isinstance(response, ProviderCall):
                                raise TypeError("browser_inspect_product must return ProviderCall")
                            _record_call(telemetry, state["run_id"], "verification", "browser_fallback", "browser", call_start, "ok", usage=response.usage, url=candidate["url"])
                            if response.usage.browser_pages is None or response.usage.browser_actions is None:
                                telemetry["browser_page_count"] = None
                                telemetry["browser_action_count"] = None
                                state["stop_reason"] = "budget_exhausted"
                                state["exhausted_metric"] = "browser_usage"
                                _mark_budget(telemetry, "browser_usage")
                                verification_stopped = True
                                telemetry["browser_fallback_status"] = "usage_unavailable"
                            else:
                                _increment(telemetry, "browser_page_count", response.usage.browser_pages)
                                _increment(telemetry, "browser_action_count", response.usage.browser_actions)
                                if telemetry["browser_page_count"] > config.max_browser_pages or telemetry["browser_action_count"] > config.max_browser_actions:
                                    state["stop_reason"] = "budget_exhausted"
                                    state["exhausted_metric"] = (
                                        "browser_page_count"
                                        if telemetry["browser_page_count"] > config.max_browser_pages
                                        else "browser_action_count"
                                    )
                                    _mark_budget(telemetry, state["exhausted_metric"])
                                    verification_stopped = True
                                    telemetry["browser_fallback_status"] = "budget_exhausted"
                                else:
                                    telemetry["browser_fallback_status"] = "used"
                                    browser_value = response.value
                                    browser_page = browser_value.get("html", browser_value.get("evidence")) if isinstance(browser_value, Mapping) else browser_value
                                    browser_url = browser_value.get("final_url", candidate["request_url"]) if isinstance(browser_value, Mapping) else candidate["request_url"]
                                    if _safe_host(browser_url) == candidate["host"]:
                                        extra = _extract_for_postcode(browser_page, browser_url, postcode)
                                        if extra:
                                            evidence_list = extra
                                            evidence = extra[0]
                    else:
                        state["stop_reason"] = "budget_exhausted"
                        state["exhausted_metric"] = "estimated_cost_usd"
                        _mark_budget(telemetry, "estimated_cost_usd")
                        verification_stopped = True
                else:
                    telemetry["warnings"].append("browser fallback disabled because page and action limits are unset")

            if evidence_list:
                for item in evidence_list:
                    classification, reasons, delivered = classify_evidence(item, _constraints_from_dict(parsed), candidate["host"])
                    results.append(_verified_result(candidate, item, classification, reasons, delivered))
            else:
                results.append(_unverified_result(candidate, "direct_product_offer_facts_unavailable"))
            if verification_stopped:
                remaining = discoveries[candidate_index + 1 :]
                results.extend(_unverified_result(other, "verification_not_attempted_after_budget_stop") for other in remaining)
                break
        return {
            "candidate_results": results,
            "telemetry": telemetry,
            "stop_reason": state.get("stop_reason"),
            "exhausted_metric": state.get("exhausted_metric"),
        }

    def ranking_node(state: WorkflowState) -> dict[str, Any]:
        telemetry = state["telemetry"]
        _increment(telemetry, "component_counts", "rank_verified_options")
        results = state.get("candidate_results", [])
        passed = [item for item in results if item["classification"] == "PASS"]
        passed.sort(key=lambda item: (Decimal(item["delivered_price_aud"]), item["name"].casefold(), item["retailer"]))
        telemetry.update(
            {
                "finished_at": _utc_now(),
                "duration_ms": max(0, int((time.perf_counter() - state["started_clock"]) * 1000)),
                "candidate_discovered_count": len(state.get("discoveries", [])),
                "pass_count": sum(item["classification"] == "PASS" for item in results),
                "fail_count": sum(item["classification"] == "FAIL" for item in results),
                "unverified_count": sum(item["classification"] == "UNVERIFIED" for item in results),
                "stop_reason": state.get("stop_reason") or ("budget_exhausted" if state.get("exhausted_metric") else state.get("refusal_reason") or "completed"),
                "budget_exhausted_metric": state.get("exhausted_metric"),
                "budget_exhausted_metrics": list(telemetry["budget_exhausted_metrics"]),
                "browser_fallback_status": telemetry["browser_fallback_status"],
                "provider_unavailable": bool(state.get("provider_unavailable", False)),
            }
        )
        if state.get("refusal_reason"):
            status = "refused"
        elif state["parsed"].get("clarification_questions"):
            status = "needs_clarification"
        elif state.get("provider_unavailable"):
            status = "provider_unavailable"
        elif state.get("exhausted_metric"):
            status = "budget_exhausted"
        else:
            status = "completed"
        output = {
            "status": status,
            "refusal_reason": state.get("refusal_reason"),
            "clarification_questions": state.get("parsed", {}).get("clarification_questions", []),
            "recommendations": passed[:3],
            "candidates": results,
            "telemetry": telemetry,
        }
        return {"output": output}

    def route_after_parse(state: WorkflowState) -> str:
        if state.get("refusal_reason") or state.get("parsed", {}).get("clarification_questions"):
            return "rank"
        return "discover"

    graph = StateGraph(WorkflowState)
    graph.add_node("parse_constraints", parse_node)
    graph.add_node("google_shopping_discovery", discovery_node)
    graph.add_node("direct_retailer_verification", verification_node)
    graph.add_node("rank_verified_options", ranking_node)
    graph.add_edge(START, "parse_constraints")
    graph.add_conditional_edges("parse_constraints", route_after_parse, {"discover": "google_shopping_discovery", "rank": "rank_verified_options"})
    graph.add_edge("google_shopping_discovery", "direct_retailer_verification")
    graph.add_edge("direct_retailer_verification", "rank_verified_options")
    graph.add_edge("rank_verified_options", END)
    return graph.compile()


def _constraints_from_dict(value: Mapping[str, Any]) -> ShoppingConstraints:
    return ShoppingConstraints(
        request=value["request"],
        postcode=value.get("postcode"),
        required_length_m=value.get("required_length_m"),
        length_was_mentioned=bool(value.get("length_was_mentioned")),
        budget_aud=value.get("budget_aud"),
        budget_item_only=bool(value.get("budget_item_only")),
        clarification_questions=tuple(value.get("clarification_questions", [])),
    )


def _increment(telemetry: dict[str, Any], key: str, amount: int | str = 1) -> None:
    if key == "component_counts":
        component = str(amount)
        telemetry[key][component] = telemetry[key].get(component, 0) + 1
    elif telemetry[key] is None:
        raise ValueError(f"cannot increment unavailable metric {key}")
    else:
        telemetry[key] += amount


def _mark_budget(telemetry: dict[str, Any], metric: str) -> None:
    if metric not in telemetry["budget_exhausted_metrics"]:
        telemetry["budget_exhausted_metrics"].append(metric)
    telemetry["budget_exhausted_metric"] = metric


def _check_budget(telemetry: dict[str, Any], config: ShoppingConfig, counter: str, limit_name: str) -> str | None:
    limit = getattr(config, limit_name)
    if counter == "search_call_count":
        limit = MAX_DISCOVERY_REQUESTS if limit is None else min(MAX_DISCOVERY_REQUESTS, limit)
    current = telemetry[counter]
    if limit is not None and current is None:
        return f"budget unavailable: {counter} cannot be measured"
    if limit is not None and current >= limit:
        return f"budget warning: {counter} reached its configured limit"
    return None


def _cost_preflight(
    providers: ShoppingProviders,
    config: ShoppingConfig,
    provider_kind: str,
    telemetry: dict[str, Any],
) -> bool:
    cap = config.max_estimated_cost_usd
    if cap is None:
        return True
    if providers.estimate_cost_usd is None:
        telemetry["budget_exhausted_metric"] = "estimated_cost_usd"
        return False
    try:
        estimate = providers.estimate_cost_usd(provider_kind)
    except ProviderError:
        telemetry["budget_exhausted_metric"] = "estimated_cost_usd"
        return False
    if not isinstance(estimate, Decimal) or estimate < 0 or telemetry["estimated_cost_usd"] is None:
        telemetry["budget_exhausted_metric"] = "estimated_cost_usd"
        return False
    if telemetry["estimated_cost_usd"] + estimate > cap:
        telemetry["budget_exhausted_metric"] = "estimated_cost_usd"
        return False
    return True


def _cost_limit_reached(config: ShoppingConfig, telemetry: Mapping[str, Any]) -> bool:
    cap = config.max_estimated_cost_usd
    if cap is None:
        return False
    spent = telemetry.get("estimated_cost_usd")
    return spent is None or spent > cap


def _record_call(
    telemetry: dict[str, Any],
    run_id: str,
    phase: str,
    call_type: str,
    provider: str,
    started: float,
    status: str,
    error_type: str | None = None,
    url: str | None = None,
    usage: ProviderUsage | None = None,
) -> None:
    usage = usage or ProviderUsage()
    telemetry["provider_counts"][provider] = telemetry["provider_counts"].get(provider, 0) + 1
    if usage.estimated_cost_usd is not None:
        current = telemetry["estimated_cost_usd"]
        telemetry["estimated_cost_usd"] = usage.estimated_cost_usd if current is None else current + usage.estimated_cost_usd
    else:
        if not telemetry["calls"]:
            telemetry["estimated_cost_usd"] = None
        telemetry["estimated_cost_complete"] = False
    if usage.retry_count:
        telemetry["retry_count"] += usage.retry_count
    if status == "error":
        telemetry["error_count"] += 1
    domain = _safe_host(url) if url else None
    telemetry["calls"].append(
        {
            "run_id": run_id,
            "phase_or_node": phase,
            "call_type": call_type,
            "provider_or_tool": provider,
            "model_id_when_llm": None,
            "input_tokens_when_available": usage.input_tokens,
            "output_tokens_when_available": usage.output_tokens,
            "cached_tokens_when_available": usage.cached_tokens,
            "estimated_cost_usd_when_available": _as_decimal_string(usage.estimated_cost_usd),
            "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
            "status": status,
            "safe_domain": domain,
            "error_type": error_type,
        }
    )
def _base_telemetry(request_id: str, run_id: str, started_at: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": None,
        "stop_reason": None,
        "candidate_discovered_count": 0,
        "pass_count": 0,
        "fail_count": 0,
        "unverified_count": 0,
        "llm_call_count": 0,
        "input_tokens": None,
        "output_tokens": None,
        "cached_tokens": None,
        "estimated_cost_usd": Decimal("0"),
        "estimated_cost_complete": True,
        "search_call_count": 0,
        "api_call_count": 0,
        "page_fetch_count": 0,
        "browser_page_count": 0,
        "browser_action_count": 0,
        "retry_count": 0,
        "error_count": 0,
        "provider_counts": {},
        "component_counts": {
            "parse_constraints": 0,
            "google_shopping_discovery": 0,
            "direct_retailer_verification": 0,
            "rank_verified_options": 0,
        },
        "calls": [],
        "warnings": [],
        "budget_exhausted_metric": None,
        "budget_exhausted_metrics": [],
        "browser_fallback_status": "not_evaluated",
        "provider_unavailable": False,
    }


def _unverified_result(candidate: Mapping[str, str], reason: str) -> dict[str, Any]:
    return {
        "name": candidate["name"],
        "product_url": candidate["url"],
        "retailer": candidate["host"],
        "classification": "UNVERIFIED",
        "reasons": [reason],
        "length_m": None,
        "in_stock": None,
        "item_price_aud": None,
        "shipping_price_aud": None,
        "shipping_postcode": None,
        "delivered_price_aud": None,
        "checked_at": _utc_now(),
    }


def _verified_result(
    candidate: Mapping[str, str],
    evidence: ProductOfferEvidence,
    classification: str,
    reasons: tuple[str, ...],
    delivered: Decimal | None,
) -> dict[str, Any]:
    return {
        "name": evidence.product_name or candidate["name"],
        "product_url": candidate["url"],
        "retailer": candidate["host"],
        "classification": classification,
        "reasons": list(reasons),
        "length_m": _as_decimal_string(evidence.length_m),
        "in_stock": evidence.in_stock,
        "item_price_aud": _as_decimal_string(evidence.item_price_aud),
        "shipping_price_aud": _as_decimal_string(evidence.shipping_price_aud),
        "shipping_postcode": evidence.shipping_postcode,
        "delivered_price_aud": _as_decimal_string(delivered),
        "checked_at": evidence.checked_at,
    }


def run_shopping_workflow(
    task: str,
    providers: ShoppingProviders,
    config: ShoppingConfig | None = None,
    *,
    request_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run parse → discovery → direct verification → deterministic ranking."""

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    if not isinstance(providers, ShoppingProviders):
        raise TypeError("providers must be ShoppingProviders")
    config = config or ShoppingConfig()
    started_at = _utc_now()
    started_clock = time.perf_counter()
    req_id = request_id or str(uuid4())
    run_id_value = run_id or str(uuid4())
    telemetry = _base_telemetry(req_id, run_id_value, started_at)
    state = {
        "task": task.strip(),
        "request_id": req_id,
        "run_id": run_id_value,
        "started_at": started_at,
        "started_clock": started_clock,
        "telemetry": telemetry,
        "warnings": [],
    }
    graph = _build_workflow(providers, config)
    final_state = graph.invoke(state)
    output = final_state["output"]
    output["telemetry"]["budget_exhausted_metric"] = final_state.get("exhausted_metric") or telemetry.get("budget_exhausted_metric")
    for name, threshold in config.warning_thresholds.items():
        metric_value = output["telemetry"].get(name)
        if name == "estimated_cost_usd":
            metric_value = Decimal(str(metric_value)) if metric_value is not None else None
            threshold = Decimal(str(threshold))
        if isinstance(metric_value, int) and metric_value >= threshold and threshold > 0:
            output["telemetry"]["warnings"].append(f"{name} reached configured warning threshold {threshold}")
        elif isinstance(metric_value, Decimal) and metric_value >= threshold and threshold > 0:
            output["telemetry"]["warnings"].append(f"{name} reached configured warning threshold {threshold}")
    if output["telemetry"]["estimated_cost_usd"] is not None:
        output["telemetry"]["estimated_cost_usd"] = _as_decimal_string(output["telemetry"]["estimated_cost_usd"])
    else:
        output["telemetry"]["estimated_cost_usd"] = None
    output["telemetry"]["usage_availability"] = {
        "component_counts": "measured",
        "provider_counts": "measured for invoked adapters",
        "llm_tokens": "unavailable; this workflow makes no LLM calls",
        "provider_cost": "complete" if output["telemetry"]["estimated_cost_complete"] else "partial or unavailable",
        "browser_pages_and_actions": (
            "unavailable" if output["telemetry"]["browser_page_count"] is None or output["telemetry"]["browser_action_count"] is None else "measured"
        ),
    }
    output["telemetry"]["provider_availability"] = {
        "serpapi_google_shopping": providers.google_shopping_search is not None,
        "direct_retailer_page": providers.fetch_product_page is not None,
        "browser_fallback": providers.browser_inspect_product is not None,
    }
    return output
