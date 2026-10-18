from __future__ import annotations

import json
from decimal import Decimal

import pytest

from src.models import CandidateStatus, DiscoveryCandidate, StructuredEvidence
from src.verification import classify_candidate, extract_json_ld_scripts, validate_constraint_keys


def test_exact_variant_and_delivered_price_are_verified(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    evidence = StructuredEvidence(candidate.url, "retailer_page", retailer_jsonld())
    result = classify_candidate(
        candidate,
        evidence,
        {"product.color": "Blue", "product.model": "X-1", "offer.delivered_price_max": "110", "delivery.country": "US"},
    )

    assert result.status is CandidateStatus.PASS
    assert result.delivered_price == Decimal("105")


def test_wrong_exact_variant_fails(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    result = classify_candidate(
        candidate,
        StructuredEvidence(candidate.url, "retailer_page", retailer_jsonld(color="Black")),
        {"product.color": "Blue"},
    )

    assert result.status is CandidateStatus.FAIL
    assert "constraint_mismatch:product.color" in result.reasons


def test_unavailable_retailer_offer_fails(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    result = classify_candidate(
        candidate,
        StructuredEvidence(candidate.url, "retailer_page", retailer_jsonld(availability="https://schema.org/OutOfStock")),
        {},
    )

    assert result.status is CandidateStatus.FAIL
    assert "offer_not_in_stock" in result.reasons


def test_unknown_seller_or_shipping_cannot_pass(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    no_seller = classify_candidate(candidate, StructuredEvidence(candidate.url, "retailer_page", retailer_jsonld(seller=None)), {})
    no_shipping = classify_candidate(
        candidate,
        StructuredEvidence(candidate.url, "retailer_page", retailer_jsonld(include_shipping=False)),
        {},
    )

    assert no_seller.status is CandidateStatus.UNVERIFIED
    assert "offer_seller_unknown" in no_seller.reasons
    assert no_shipping.status is CandidateStatus.UNVERIFIED
    assert "shipping_cost_unknown" in no_shipping.reasons


def test_discovery_and_cross_host_data_are_not_verification(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    no_direct_page = classify_candidate(candidate, None, {})
    cross_host = classify_candidate(
        candidate,
        StructuredEvidence("https://search.example/result", "retailer_page", retailer_jsonld()),
        {},
    )

    assert no_direct_page.status is CandidateStatus.UNVERIFIED
    assert cross_host.status is CandidateStatus.UNVERIFIED


def test_evidence_contract_rejects_search_result_sources():
    with pytest.raises(ValueError, match="direct retailer page"):
        StructuredEvidence("https://shop.example/item", "search_result", {})


@pytest.mark.parametrize(
    "url",
    (
        "http://localhost/item",
        "http://router.local/item",
        "http://127.0.0.1/item",
        "http://10.0.0.1/item",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/item",
    ),
)
def test_discovery_candidate_rejects_local_and_non_global_hosts(url):
    with pytest.raises(ValueError, match="public"):
        DiscoveryCandidate("camera", url)


def test_discovery_candidate_accepts_public_hostname():
    assert DiscoveryCandidate("camera", "https://shop.example/item").url == "https://shop.example/item"


def test_product_without_schema_offer_is_unverified(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    document = retailer_jsonld()
    document["offers"]["@type"] = "ShoppingResult"
    result = classify_candidate(candidate, StructuredEvidence(candidate.url, "retailer_page", document), {})

    assert result.status is CandidateStatus.UNVERIFIED
    assert "direct_offer_evidence_missing" in result.reasons


def test_json_ld_is_extracted_from_retrieved_page_markup(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/camera")
    page_html = (
        "<html><script type='application/ld+json'>"
        + json.dumps(retailer_jsonld())
        + "</script></html>"
    )
    documents = extract_json_ld_scripts(page_html)
    result = classify_candidate(
        candidate,
        StructuredEvidence(candidate.url, "retailer_page", documents),
        {},
    )

    assert result.status is CandidateStatus.PASS


def test_malformed_json_ld_fails_closed():
    with pytest.raises(ValueError, match="malformed JSON-LD"):
        extract_json_ld_scripts("<script type='application/ld+json'>{broken}</script>")


def test_constraint_contract_rejects_unknown_or_ambiguous_fields():
    with pytest.raises(ValueError, match="Unsupported explicit"):
        validate_constraint_keys({"cheap": True})
    with pytest.raises(ValueError, match="non-empty string"):
        validate_constraint_keys({"product.color": " "})
    with pytest.raises(ValueError, match="numeric shopping constraint"):
        validate_constraint_keys({"offer.price_max": "free"})
