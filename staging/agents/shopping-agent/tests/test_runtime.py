from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from shopping_agent.constraints import parse_request
from shopping_agent.models import DiscoveryCandidate
from shopping_agent.providers import SerpApiDiscovery
from shopping_agent.settings import ShoppingBudget, ShoppingConfig
from shopping_agent.urls import safe_hostname, safe_url
from shopping_agent.verification import (
    HttpRetailerPageFetcher,
    PageFetchResult,
    RetailerFetchError,
    RetailerVerifier,
)
from shopping_agent.workflow import WorkflowDependencies, new_telemetry, run_shopping
from specialist_contract import adapt_universal_task


class FakeTransport:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, Mapping[str, str], float]] = []

    def get_json(self, url: str, params: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
        self.calls.append((url, params, timeout))
        return self.payload


class FakePages:
    def __init__(self, pages: Mapping[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, timeout: float) -> PageFetchResult:
        self.calls.append(url)
        return PageFetchResult(url=url, html=self.pages[url], checked_at="2026-10-07T00:00:00+00:00")


class FailingPages:
    def fetch(self, url: str, timeout: float) -> PageFetchResult:
        raise RetailerFetchError("fixture fetch failure")


def _config() -> ShoppingConfig:
    return ShoppingConfig(
        serpapi_api_key_env="SHOPPING_TEST_PROVIDER_KEY",
        destination_postcode="2155",
        budget=ShoppingBudget(
            max_search_calls=3,
            max_api_calls=3,
            max_page_fetches=6,
            max_browser_pages=0,
        ),
    )


def _product_page(
    *,
    name: str,
    availability: str,
    price: str = "20.00",
    shipping: str | None = "5.00",
    shipping_currency: str | None = "AUD",
) -> str:
    document = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "offers": {
            "@type": "Offer",
            "price": price,
            "priceCurrency": "AUD",
            "availability": availability,
        },
    }
    if shipping is not None:
        shipping_rate: dict[str, Any] = {"value": float(shipping)}
        if shipping_currency is not None:
            shipping_rate["currency"] = shipping_currency
        document["offers"]["shippingDetails"] = {
            "shippingRate": shipping_rate,
            "shippingDestination": {"postalCode": "2155", "addressCountry": "AU"},
        }
    encoded = json.dumps(document)
    return f'<html><script type="application/ld+json">{encoded}</script></html>'


def _candidate_payload() -> dict[str, Any]:
    return {
        "shopping_results": [
            {
                "title": "ZacJac 7ft Surfboard Leash Cord",
                "source": "ZacJac Surf",
                "price": "A$16.00",
                "delivery": "Free delivery",
                "product_link": "https://www.google.com/shopping/product/zacjac",
                "link": "https://zacjac.example/products/7ft-leash",
            },
            {
                "title": "Ocean & Earth 7ft Regular Leash",
                "source": "Australian Surf Shop",
                "price": "A$20.00",
                "delivery": "Delivery calculated at checkout",
                "product_link": "https://www.google.com/shopping/product/ocean-earth",
                "link": "https://retailer.example/products/ocean-earth-7ft",
            },
        ]
    }


def _dependencies(
    *,
    pages: Mapping[str, str],
    payload: Mapping[str, Any] | None = None,
    env: dict[str, str] | None = None,
    budget: ShoppingBudget | None = None,
) -> tuple[WorkflowDependencies, FakeTransport, FakePages]:
    config = replace(_config(), budget=budget) if budget is not None else _config()
    telemetry = new_telemetry("request-test", "run-test")
    transport = FakeTransport(payload or _candidate_payload())
    provider_env = {"SHOPPING_TEST_PROVIDER_KEY": "fixture-key"} if env is None else env
    discovery = SerpApiDiscovery(config, telemetry, transport=transport, env=provider_env)
    pages_client = FakePages(pages)
    verifier = RetailerVerifier(config, telemetry, fetcher=pages_client)
    return WorkflowDependencies(config=config, discovery=discovery, verifier=verifier), transport, pages_client


def test_parser_requires_postcode_and_preserves_explicit_constraints() -> None:
    parsed = parse_request(
        "Find me a 7-foot surf leash under $30 delivered to my house.",
        destination_postcode="2155",
    )
    assert parsed.constraints is not None
    assert parsed.constraints.exact_length_feet == Decimal(7)
    assert parsed.constraints.max_delivered_price_aud == Decimal(30)
    assert parsed.constraints.budget_operator == "lt"
    assert parsed.constraints.destination_postcode == "2155"

    missing_postcode = parse_request(
        "Find me a 7-foot surf leash under $30 delivered to my house.",
        destination_postcode=None,
    )
    assert missing_postcode.constraints is None
    assert "postcode" in (missing_postcode.clarification_question or "").lower()


def test_serpapi_discovery_is_configurable_and_redacts_key_from_telemetry() -> None:
    config = _config()
    telemetry = new_telemetry("request-test", "run-test")
    transport = FakeTransport(_candidate_payload())
    client = SerpApiDiscovery(
        config,
        telemetry,
        transport=transport,
        env={"SHOPPING_TEST_PROVIDER_KEY": "fixture-key"},
    )
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    result = client.search("7ft surf leash Australia", parsed.constraints)
    assert result.candidates[0].title.startswith("ZacJac")
    assert transport.calls[0][1]["engine"] == "google_shopping"
    assert transport.calls[0][1]["gl"] == "au"
    assert "fixture-key" not in json.dumps(telemetry.to_dict())


def test_workflow_rejects_stale_unavailable_zacjac_and_recommends_direct_pass() -> None:
    pages = {
        "https://zacjac.example/products/7ft-leash": _product_page(
            name="ZacJac 7ft Surfboard Leash Cord",
            availability="https://schema.org/OutOfStock",
            price="16.00",
            shipping="0.00",
        ),
        "https://retailer.example/products/ocean-earth-7ft": _product_page(
            name="Ocean & Earth 7ft Regular Leash",
            availability="https://schema.org/InStock",
            price="20.00",
            shipping="5.00",
        ),
    }
    dependencies, transport, pages_client = _dependencies(pages=pages)
    result = run_shopping(
        "Find me a 7-foot surf leash under $30 delivered to my house.",
        dependencies=dependencies,
        request_id="request-test",
        run_id="run-test",
        destination_postcode="2155",
    )
    assert result["status"] == "success"
    assert [item["title"] for item in result["shortlist"]] == ["Ocean & Earth 7ft Regular Leash"]
    assert result["shortlist"][0]["retailer_evidence"]["delivered_price_aud"] == "25.00"
    assert result["failed_candidates"][0]["merchant"] == "ZacJac Surf"
    assert "unavailable" in " ".join(result["failed_candidates"][0]["reasons"]).lower()
    assert result["telemetry"]["search_call_count"] == 3
    assert result["telemetry"]["api_call_count"] == 3
    assert result["telemetry"]["page_fetch_count"] == 2
    assert result["telemetry"]["estimated_cost_usd"] is None
    assert "llm_call_count" not in result["telemetry"]
    assert "input_tokens" not in result["telemetry"]
    assert "browser_action_count" not in result["telemetry"]
    assert "retry_count" not in result["telemetry"]
    assert all(call["run_id"] == "run-test" for call in result["telemetry"]["calls"])
    assert {call["phase_or_node"] for call in result["telemetry"]["calls"]} == {
        "discover",
        "verify",
    }
    assert len(transport.calls) == 3
    assert set(pages_client.calls) == set(pages)


def test_missing_shipping_is_unverified_and_never_recommended() -> None:
    pages = {
        "https://retailer.example/products/ocean-earth-7ft": _product_page(
            name="Ocean & Earth 7ft Regular Leash",
            availability="https://schema.org/InStock",
            price="20.00",
            shipping=None,
        )
    }
    payload = {
        "shopping_results": [
            {
                "title": "Ocean & Earth 7ft Regular Leash",
                "source": "Australian Surf Shop",
                "price": "A$20.00",
                "delivery": "Free delivery",
                "product_link": "https://www.google.com/shopping/product/ocean-earth",
                "link": "https://retailer.example/products/ocean-earth-7ft",
            }
        ]
    }
    dependencies, _, _ = _dependencies(pages=pages, payload=payload)
    result = run_shopping(
        "Find me a 7-foot surf leash under $30 delivered to my house.",
        dependencies=dependencies,
        destination_postcode="2155",
    )
    assert result["shortlist"] == []
    assert result["unverified_candidates"][0]["status"] == "UNVERIFIED"
    assert "shipping" in " ".join(result["unverified_candidates"][0]["reasons"]).lower()


def test_search_budget_preserves_candidates_and_records_exhaustion() -> None:
    pages = {
        "https://zacjac.example/products/7ft-leash": _product_page(
            name="ZacJac 7ft Surfboard Leash Cord",
            availability="https://schema.org/OutOfStock",
            price="16.00",
            shipping="0.00",
        ),
        "https://retailer.example/products/ocean-earth-7ft": _product_page(
            name="Ocean & Earth 7ft Regular Leash",
            availability="https://schema.org/InStock",
            price="20.00",
            shipping="5.00",
        ),
    }
    dependencies, transport, _ = _dependencies(
        pages=pages,
        budget=ShoppingBudget(
            max_search_calls=3,
            max_api_calls=1,
            max_page_fetches=6,
            max_browser_pages=0,
        ),
    )
    result = run_shopping(
        "Find me a 7-foot surf leash under $30 delivered to my house.",
        dependencies=dependencies,
        destination_postcode="2155",
    )
    assert result["status"] == "success"
    assert result["shortlist"][0]["title"] == "Ocean & Earth 7ft Regular Leash"
    assert result["telemetry"]["stop_reason"] == "budget_exhausted"
    assert result["telemetry"]["budget_exhausted_events"] == [
        {"metric": "max_api_calls", "limit": 1, "observed": 1}
    ]
    assert len(transport.calls) == 1


def test_page_budget_is_fail_closed_and_recorded() -> None:
    candidate = DiscoveryCandidate(
        "candidate-page-budget",
        "Ocean & Earth 7ft Regular Leash",
        "merchant",
        None,
        "https://retailer.example/products/ocean-earth-7ft",
        None,
        None,
        "fixture",
    )
    config = replace(
        _config(),
        budget=ShoppingBudget(
            max_search_calls=3,
            max_api_calls=3,
            max_page_fetches=0,
            max_browser_pages=0,
        ),
    )
    telemetry = new_telemetry("request-test", "run-test")
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verified = RetailerVerifier(
        config,
        telemetry,
        fetcher=FakePages({}),
    ).verify(candidate, parsed.constraints)
    assert verified.status == "UNVERIFIED"
    assert telemetry.budget_exhausted_events == [
        {"metric": "max_page_fetches", "limit": 0, "observed": 0}
    ]


def test_browser_page_budget_is_bounded_and_recorded() -> None:
    candidate = DiscoveryCandidate(
        "candidate-browser-budget",
        "Ocean & Earth 7ft Regular Leash",
        "merchant",
        None,
        "https://retailer.example/products/ocean-earth-7ft",
        None,
        None,
        "fixture",
    )
    config = replace(
        _config(),
        budget=ShoppingBudget(
            max_search_calls=3,
            max_api_calls=3,
            max_page_fetches=2,
            max_browser_pages=1,
        ),
    )
    telemetry = new_telemetry("request-test", "run-test")
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verifier = RetailerVerifier(
        config,
        telemetry,
        fetcher=FailingPages(),
        browser_fallback=FakePages(
            {
                candidate.direct_url: _product_page(
                    name="Ocean & Earth 7ft Regular Leash",
                    availability="https://schema.org/InStock",
                    price="20.00",
                    shipping="5.00",
                )
            }
        ),
    )
    assert verifier.verify(candidate, parsed.constraints).status == "PASS"
    assert verifier.verify(candidate, parsed.constraints).status == "UNVERIFIED"
    assert telemetry.budget_exhausted_events == [
        {"metric": "max_browser_pages", "limit": 1, "observed": 1}
    ]


def test_missing_shipping_currency_is_unverified() -> None:
    page = _product_page(
        name="Ocean & Earth 7ft Regular Leash",
        availability="https://schema.org/InStock",
        shipping_currency=None,
    )
    candidate = DiscoveryCandidate(
        "candidate-currency",
        "Ocean & Earth 7ft Regular Leash",
        "merchant",
        None,
        "https://retailer.example/products/ocean-earth-7ft",
        None,
        None,
        "fixture",
    )
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verified = RetailerVerifier(
        _config(),
        new_telemetry("request-test", "run-test"),
        fetcher=FakePages({candidate.direct_url: page}),
    ).verify(candidate, parsed.constraints)
    assert verified.status == "UNVERIFIED"


def test_negative_item_price_is_unverified() -> None:
    page = _product_page(
        name="Ocean & Earth 7ft Regular Leash",
        availability="https://schema.org/InStock",
        price="-1.00",
    )
    candidate = DiscoveryCandidate(
        "candidate-negative",
        "Ocean & Earth 7ft Regular Leash",
        "merchant",
        None,
        "https://retailer.example/products/ocean-earth-7ft",
        None,
        None,
        "fixture",
    )
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verified = RetailerVerifier(
        _config(),
        new_telemetry("request-test", "run-test"),
        fetcher=FakePages({candidate.direct_url: page}),
    ).verify(candidate, parsed.constraints)
    assert verified.status == "UNVERIFIED"


def test_private_retailer_urls_are_rejected_before_fetch() -> None:
    assert safe_url("http://127.0.0.1:8080/internal") is None
    assert safe_url("http://[::1") is None
    assert safe_hostname("https://user:password@example.com/path") == "example.com"
    with pytest.raises(RetailerFetchError, match="non-public"):
        HttpRetailerPageFetcher().fetch("http://127.0.0.1:8080/internal", timeout=1)


def test_direct_length_mismatch_is_fail_not_unverified() -> None:
    page = _product_page(
        name="Ocean & Earth 6ft Regular Leash",
        availability="https://schema.org/InStock",
        price="20.00",
        shipping="5.00",
    )
    candidate = DiscoveryCandidate(
        candidate_id="candidate-1",
        title="Ocean & Earth 6ft Regular Leash",
        merchant="Australian Surf Shop",
        discovery_url="https://www.google.com/shopping/product/ocean-earth",
        direct_url="https://retailer.example/products/ocean-earth-7ft",
        discovery_price_text="A$20.00",
        discovery_delivery_text="Free delivery",
        source="fixture",
    )
    config = _config()
    telemetry = new_telemetry("request-test", "run-test")
    verifier = RetailerVerifier(config, telemetry, fetcher=FakePages({candidate.direct_url: page}))
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verified = verifier.verify(candidate, parsed.constraints)
    assert verified.status == "FAIL"
    assert "different product length" in " ".join(verified.reasons)


def test_under_budget_rejects_exact_boundary() -> None:
    page = _product_page(
        name="Ocean & Earth 7ft Regular Leash",
        availability="https://schema.org/InStock",
        price="30.00",
        shipping="0.00",
    )
    candidate = DiscoveryCandidate(
        candidate_id="candidate-boundary",
        title="Ocean & Earth 7ft Regular Leash",
        merchant="Australian Surf Shop",
        discovery_url=None,
        direct_url="https://retailer.example/products/ocean-earth-7ft",
        discovery_price_text=None,
        discovery_delivery_text=None,
        source="fixture",
    )
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verified = RetailerVerifier(
        _config(),
        new_telemetry("request-test", "run-test"),
        fetcher=FakePages({candidate.direct_url: page}),
    ).verify(candidate, parsed.constraints)
    assert verified.status == "FAIL"


def test_product_group_without_exact_variant_offer_is_unverified() -> None:
    document = {
        "@context": "https://schema.org",
        "@type": "ProductGroup",
        "name": "7ft Surf Leash",
        "hasVariant": [{"@type": "Product", "name": "6ft Surf Leash"}],
        "offers": {
            "@type": "Offer",
            "price": "20.00",
            "priceCurrency": "AUD",
            "availability": "https://schema.org/InStock",
        },
    }
    page = f'<script type="application/ld+json">{json.dumps(document)}</script>'
    candidate = DiscoveryCandidate(
        "candidate-group",
        "7ft Surf Leash",
        "merchant",
        None,
        "https://retailer.example/products/leash",
        None,
        None,
        "fixture",
    )
    parsed = parse_request("7ft surf leash under $30 Australia", destination_postcode="2155")
    assert parsed.constraints is not None
    verified = RetailerVerifier(
        _config(),
        new_telemetry("request-test", "run-test"),
        fetcher=FakePages({candidate.direct_url: page}),
    ).verify(candidate, parsed.constraints)
    assert verified.status == "UNVERIFIED"


def test_universal_task_adapter_rejects_unsupported_fields() -> None:
    with pytest.raises(ValueError, match="Unsupported task fields"):
        adapt_universal_task({"task": "7ft leash", "agent_id": "shopping-agent"})


def test_missing_provider_key_stops_before_any_search() -> None:
    dependencies, transport, _ = _dependencies(pages={}, env={})
    result = run_shopping(
        "Find me a 7-foot surf leash under $30 delivered to my house.",
        dependencies=dependencies,
        destination_postcode="2155",
    )
    assert result["status"] == "failed"
    assert result["telemetry"]["search_call_count"] == 0
    assert transport.calls == []
    assert "not configured" in result["summary"]


def test_subprocess_entrypoint_returns_protocol_result_without_a_key(tmp_path: Path) -> None:
    output_path = tmp_path / "result.json"
    env = dict(os.environ)
    env.pop("SERPAPI_API_KEY", None)
    env["PYTHONPATH"] = "staging/agents/shopping-agent:staging/agents/shopping-agent/runtime"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "shopping_agent",
            "--task",
            "Find me a 7-foot surf leash under $30 delivered to my house.",
            "--postcode",
            "2155",
            "--output-json",
            str(output_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["telemetry"]["search_call_count"] == 0
    assert "SERPAPI_API_KEY" not in completed.stdout
    assert "SERPAPI_API_KEY" not in completed.stderr
