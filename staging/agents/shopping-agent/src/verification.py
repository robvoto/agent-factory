"""Fail-closed verification of direct retailer Product and Offer evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from .models import CandidateStatus, ClassifiedCandidate, DiscoveryCandidate, StructuredEvidence

_PRODUCT_FIELDS = {
    "name",
    "brand",
    "model",
    "sku",
    "mpn",
    "gtin",
    "gtin8",
    "gtin12",
    "gtin13",
    "gtin14",
    "color",
    "size",
    "material",
    "category",
}
_CONSTRAINT_KEYS = {
    *(f"product.{name}" for name in _PRODUCT_FIELDS),
    "offer.seller_name",
    "offer.currency",
    "offer.availability",
    "offer.price_max",
    "delivery.price_max",
    "delivery.country",
    "offer.delivered_price_max",
}


class _JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.documents: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value for name, value in attrs}
        if tag.casefold() == "script" and (attributes.get("type") or "").split(";", 1)[0].strip().casefold() == "application/ld+json":
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._current is not None:
            self.documents.append("".join(self._current))
            self._current = None


def extract_json_ld_scripts(html: str) -> tuple[Any, ...]:
    """Parse JSON-LD script blocks from one already-retrieved retailer page."""

    if not isinstance(html, str):
        raise ValueError("retailer page HTML must be text")
    parser = _JsonLdScriptParser()
    parser.feed(html)
    parser.close()
    parsed: list[Any] = []
    for block in parser.documents:
        try:
            value = json.loads(block)
        except json.JSONDecodeError as exc:
            raise ValueError("retailer page contains malformed JSON-LD") from exc
        if not isinstance(value, (dict, list)):
            raise ValueError("retailer page JSON-LD must contain an object or array")
        parsed.append(value)
    return tuple(parsed)


@dataclass(frozen=True)
class _OfferFacts:
    product: Mapping[str, str]
    seller_name: str | None
    price: Decimal | None
    currency: str | None
    availability: str | None
    shipping_cost: Decimal | None
    shipping_currency: str | None
    shipping_country: str | None


def validate_constraint_keys(constraints: Mapping[str, Any]) -> None:
    if any(not isinstance(key, str) for key in constraints):
        raise ValueError("Shopping constraint keys must be strings")
    unknown = sorted(set(constraints).difference(_CONSTRAINT_KEYS))
    if unknown:
        raise ValueError("Unsupported explicit shopping constraints: " + ", ".join(unknown))
    for key, value in constraints.items():
        if key.endswith("_max"):
            _decimal(value)
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must have an explicit non-empty string value")


def classify_candidate(
    candidate: DiscoveryCandidate,
    evidence: StructuredEvidence | None,
    constraints: Mapping[str, Any],
) -> ClassifiedCandidate:
    """Return PASS only when every mandatory fact comes from a same-host retailer page."""

    validate_constraint_keys(constraints)
    if evidence is None:
        return _result(candidate, CandidateStatus.UNVERIFIED, ("direct_product_offer_evidence_missing",))
    if not _same_host(candidate.url, evidence.source_url):
        return _result(candidate, CandidateStatus.UNVERIFIED, ("evidence_not_from_candidate_retailer_host",))

    product = _find_product(evidence.json_ld)
    if product is None:
        return _result(candidate, CandidateStatus.UNVERIFIED, ("direct_product_evidence_missing",))
    product_facts = _product_facts(product)
    product_mismatch, product_unknown = _check_product_constraints(product_facts, constraints)
    if product_mismatch:
        return _result(candidate, CandidateStatus.FAIL, tuple(product_mismatch), product_name=product_facts.get("name"))
    if product_unknown:
        return _result(candidate, CandidateStatus.UNVERIFIED, tuple(product_unknown), product_name=product_facts.get("name"))

    offers = _as_items(product.get("offers"))
    if not offers:
        return _result(candidate, CandidateStatus.UNVERIFIED, ("direct_offer_evidence_missing",), product_name=product_facts.get("name"))

    outcomes: list[ClassifiedCandidate] = []
    for offer in offers:
        if not isinstance(offer, Mapping) or not _has_type(offer.get("@type"), "Offer"):
            outcomes.append(_result(candidate, CandidateStatus.UNVERIFIED, ("direct_offer_evidence_missing",), product_name=product_facts.get("name")))
            continue
        facts = _offer_facts(product_facts, offer)
        outcomes.append(_classify_offer(candidate, facts, constraints))
    passing = [item for item in outcomes if item.status is CandidateStatus.PASS]
    if passing:
        return min(passing, key=lambda item: (item.delivered_price or Decimal("Infinity"), item.seller_name or ""))
    if all(item.status is CandidateStatus.FAIL for item in outcomes):
        reasons = sorted({reason for item in outcomes for reason in item.reasons})
        return _result(candidate, CandidateStatus.FAIL, tuple(reasons), product_name=product_facts.get("name"))
    reasons = sorted({reason for item in outcomes if item.status is CandidateStatus.UNVERIFIED for reason in item.reasons})
    return _result(candidate, CandidateStatus.UNVERIFIED, tuple(reasons), product_name=product_facts.get("name"))


def _classify_offer(
    candidate: DiscoveryCandidate,
    facts: _OfferFacts,
    constraints: Mapping[str, Any],
) -> ClassifiedCandidate:
    failures: list[str] = []
    unknown: list[str] = []
    if facts.availability == "out_of_stock":
        failures.append("offer_not_in_stock")
    elif facts.availability != "in_stock":
        unknown.append("offer_availability_unknown")
    if not facts.seller_name:
        unknown.append("offer_seller_unknown")
    if facts.price is None:
        unknown.append("offer_price_unknown")
    if not facts.currency:
        unknown.append("offer_currency_unknown")
    if facts.shipping_cost is None or facts.shipping_currency is None:
        unknown.append("shipping_cost_unknown")
    elif facts.currency and facts.shipping_currency.casefold() != facts.currency.casefold():
        unknown.append("shipping_currency_mismatch")

    delivered = None
    if facts.price is not None and facts.shipping_cost is not None and facts.currency and facts.shipping_currency:
        if facts.currency.casefold() == facts.shipping_currency.casefold():
            delivered = facts.price + facts.shipping_cost

    exact_fields = {
        "offer.seller_name": facts.seller_name,
        "offer.currency": facts.currency,
        "offer.availability": facts.availability,
        "delivery.country": facts.shipping_country,
    }
    for key, observed in exact_fields.items():
        if key not in constraints:
            continue
        if observed is None:
            unknown.append(f"required_fact_unknown:{key}")
        elif _normal(observed) != _normal(constraints[key]):
            failures.append(f"constraint_mismatch:{key}")

    numeric_fields = {
        "offer.price_max": facts.price,
        "delivery.price_max": facts.shipping_cost,
        "offer.delivered_price_max": delivered,
    }
    for key, observed in numeric_fields.items():
        if key not in constraints:
            continue
        maximum = _decimal(constraints[key])
        if observed is None:
            unknown.append(f"required_fact_unknown:{key}")
        elif observed > maximum:
            failures.append(f"constraint_exceeded:{key}")

    if failures:
        return _result(candidate, CandidateStatus.FAIL, tuple(sorted(set(failures))), facts=facts, delivered=delivered)
    if unknown:
        return _result(candidate, CandidateStatus.UNVERIFIED, tuple(sorted(set(unknown))), facts=facts, delivered=delivered)
    return _result(candidate, CandidateStatus.PASS, ("all_hard_constraints_and_purchase_facts_verified",), facts=facts, delivered=delivered)


def _find_product(document: Any) -> Mapping[str, Any] | None:
    found: list[Mapping[str, Any]] = []
    for item in _walk(document):
        if isinstance(item, Mapping) and _has_type(item.get("@type"), "Product"):
            found.append(item)
    return found[0] if len(found) == 1 else None


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _has_type(value: Any, expected: str) -> bool:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, str) and item.rsplit("/", 1)[-1].casefold() == expected.casefold():
            return True
    return False


def _product_facts(product: Mapping[str, Any]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for name in _PRODUCT_FIELDS:
        value = product.get(name)
        if name == "brand" and isinstance(value, Mapping):
            value = value.get("name")
        if isinstance(value, str) and value.strip():
            facts[name] = value.strip()
    return facts


def _offer_facts(product: Mapping[str, str], offer: Mapping[str, Any]) -> _OfferFacts:
    seller = offer.get("seller")
    if isinstance(seller, Mapping):
        seller = seller.get("name")
    availability_raw = offer.get("availability")
    availability = None
    if isinstance(availability_raw, str):
        tail = availability_raw.rsplit("/", 1)[-1].casefold()
        if tail == "instock":
            availability = "in_stock"
        elif tail in {"outofstock", "soldout", "discontinued", "presale"}:
            availability = "out_of_stock"

    price = _decimal_or_none(offer.get("price"))
    currency = _string_or_none(offer.get("priceCurrency"))
    shipping = _shipping_facts(offer.get("shippingDetails"))
    return _OfferFacts(
        product=product,
        seller_name=_string_or_none(seller),
        price=price,
        currency=currency,
        availability=availability,
        shipping_cost=shipping[0],
        shipping_currency=shipping[1],
        shipping_country=shipping[2],
    )


def _shipping_facts(value: Any) -> tuple[Decimal | None, str | None, str | None]:
    details = _as_items(value)
    if len(details) != 1:
        return None, None, None
    detail = details[0]
    if not isinstance(detail, Mapping):
        return None, None, None
    rate = detail.get("shippingRate")
    if isinstance(rate, list):
        if len(rate) != 1:
            return None, None, None
        rate = rate[0]
    if not isinstance(rate, Mapping):
        return None, None, None
    country = detail.get("shippingDestination")
    if isinstance(country, list):
        if len(country) != 1:
            country = None
        else:
            country = country[0]
    if isinstance(country, Mapping):
        country = country.get("addressCountry")
    if isinstance(country, Mapping):
        country = country.get("name")
    return _decimal_or_none(rate.get("value")), _string_or_none(rate.get("currency")), _string_or_none(country)


def _as_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        return [value]
    return []


def _check_product_constraints(
    product: Mapping[str, str], constraints: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    unknown: list[str] = []
    for key, expected in constraints.items():
        if not key.startswith("product."):
            continue
        name = key.split(".", 1)[1]
        observed = product.get(name)
        if observed is None:
            unknown.append(f"required_fact_unknown:{key}")
        elif _normal(observed) != _normal(expected):
            failures.append(f"constraint_mismatch:{key}")
    return failures, unknown


def _same_host(candidate_url: str, evidence_url: str) -> bool:
    try:
        candidate = urlsplit(candidate_url)
        evidence = urlsplit(evidence_url)
    except ValueError:
        return False
    if candidate.scheme not in {"http", "https"} or evidence.scheme not in {"http", "https"}:
        return False
    if candidate.username or candidate.password or evidence.username or evidence.password:
        return False
    return bool(candidate.hostname and evidence.hostname and candidate.hostname.casefold() == evidence.hostname.casefold())


def _normal(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).casefold()
    return " ".join(str(value).split()).casefold()


def _decimal(value: Any) -> Decimal:
    parsed = _decimal_or_none(value)
    if parsed is None:
        raise ValueError("numeric shopping constraint must be a finite non-negative number")
    return parsed


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _result(
    candidate: DiscoveryCandidate,
    status: CandidateStatus,
    reasons: tuple[str, ...],
    *,
    product_name: str | None = None,
    seller_name: str | None = None,
    price: Decimal | None = None,
    shipping_cost: Decimal | None = None,
    currency: str | None = None,
    facts: _OfferFacts | None = None,
    delivered: Decimal | None = None,
) -> ClassifiedCandidate:
    if facts is not None:
        product_name = facts.product.get("name")
        seller_name = facts.seller_name
        price = facts.price
        shipping_cost = facts.shipping_cost
        currency = facts.currency
    return ClassifiedCandidate(
        candidate=candidate,
        status=status,
        reasons=reasons,
        product_name=product_name,
        seller_name=seller_name,
        price=price,
        shipping_cost=shipping_cost,
        delivered_price=delivered,
        currency=currency,
    )
