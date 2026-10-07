from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from shopping_agent.constraints import parse_request
from shopping_agent.models import DiscoveryCandidate
from shopping_agent.providers import SerpApiDiscovery
from shopping_agent.settings import ShoppingBudget, ShoppingConfig
from shopping_agent.verification import PageFetchResult, RetailerVerifier
from shopping_agent.workflow import WorkflowDependencies, new_telemetry, run_shopping


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


def _config() -> ShoppingConfig:
    return ShoppingConfig(
        serpapi_api_key_env="SHOPPING_TEST_PROVIDER_KEY",
        destination_postcode="2155",
        budget=ShoppingBudget(
            max_search_calls=3,
            max_api_calls=3,
            max_page_fetches=6,
            max_browser_pages=0,
            max_browser_actions=0,
            max_retries=0,
        ),
    )


def _product_page(
    *,
    name: str,
    availability: str,
    price: str = "20.00",
    shipping: str | None = "5.00",
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
        document["offers"]["shippingDetails"] = {
            "shippingRate": {"value": float(shipping), "currency": "AUD"},
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
) -> tuple[WorkflowDependencies, FakeTransport, FakePages]:
    config = _config()
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
    env["PYTHONPATH"] = "staging/agents/shopping-agent/runtime"
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
