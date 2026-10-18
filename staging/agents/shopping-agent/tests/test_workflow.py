from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shopping_agent import (  # noqa: E402
    DiscoveryRequest,
    ProviderCall,
    ProviderError,
    ProviderUsage,
    ShoppingConfig,
    ShoppingProviders,
    extract_product_offers,
    parse_constraints,
    run_shopping_workflow,
)


def product_page(
    *,
    length: str | None = "2",
    stock: str | None = "InStock",
    item_price: str | None = "20.00",
    shipping: str | None = "5.00",
    shipping_postcode: str = "2000",
    name: str = "Garden hose",
) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "additionalProperty": (
            [{"@type": "PropertyValue", "name": "Length", "value": length, "unitText": "m"}]
            if length is not None
            else []
        ),
        "offers": {
            "@type": "Offer",
            "availability": f"https://schema.org/{stock}" if stock else None,
            "price": item_price,
            "priceCurrency": "AUD" if item_price is not None else "USD",
            "shippingDetails": (
                [
                    {
                        "@type": "OfferShippingDetails",
                        "shippingRate": {"@type": "MonetaryAmount", "value": shipping, "priceCurrency": "AUD"},
                        "eligibleRegion": {"@type": "DefinedRegion", "postalCode": shipping_postcode},
                    }
                ]
                if shipping is not None
                else []
            ),
        },
    }
    return '<script type="application/ld+json">' + json.dumps(product) + "</script>"


def shopping_task() -> str:
    return "Find an exactly 2 m garden hose under AUD 50, postcode 2000"


def providers_for_pages(pages: dict[str, str], candidates: list[dict[str, str]]):
    searches: list[DiscoveryRequest] = []
    fetches: list[str] = []

    def search(request: DiscoveryRequest) -> ProviderCall:
        searches.append(request)
        return ProviderCall(candidates if len(searches) == 1 else [])

    def fetch(url: str) -> ProviderCall:
        fetches.append(url)
        return ProviderCall(pages[url])

    return ShoppingProviders(google_shopping_search=search, fetch_product_page=fetch), searches, fetches


def test_constraint_parser_reads_exact_length_postcode_and_aud_budget():
    constraints = parse_constraints("Find a hose exactly 200 cm, under AUD 60, postcode 2000")

    assert constraints.required_length_m == Decimal("2.00")
    assert constraints.postcode == "2000"
    assert constraints.budget_aud == Decimal("60")
    assert not constraints.clarification_questions


def test_missing_postcode_and_ambiguous_dollar_budget_request_clarification():
    constraints = parse_constraints("Find a 2 m hose under $50")

    assert constraints.required_length_m == Decimal("2")
    assert constraints.budget_aud is None
    assert len(constraints.clarification_questions) == 2


def test_google_shopping_is_only_discovery_and_shortlist_is_top_three_passes():
    urls = [f"https://retailer{i}.example/products/hose" for i in range(4)]
    candidates = [{"title": f"Hose {i}", "link": url} for i, url in enumerate(urls)]
    pages = {
        url: product_page(item_price=str(30 - i * 5), name=f"Hose {i}")
        for i, url in enumerate(urls)
    }
    providers, searches, fetches = providers_for_pages(pages, candidates)

    result = run_shopping_workflow(
        shopping_task(),
        providers,
        ShoppingConfig(additional_discovery_queries=("2 m garden hose", "garden hose postcode 2000")),
        request_id="request-1",
        run_id="run-1",
    )

    assert len(searches) == 3
    assert all(request.engine == "google_shopping" for request in searches)
    assert len(fetches) == 4
    assert len(result["recommendations"]) == 3
    assert all(row["classification"] == "PASS" for row in result["recommendations"])
    assert [row["delivered_price_aud"] for row in result["recommendations"]] == ["20.00", "25.00", "30.00"]
    telemetry = result["telemetry"]
    assert telemetry["request_id"] == "request-1"
    assert telemetry["run_id"] == "run-1"
    assert telemetry["search_call_count"] == telemetry["api_call_count"] == 3
    assert telemetry["page_fetch_count"] == 4
    assert telemetry["component_counts"] == {
        "parse_constraints": 1,
        "google_shopping_discovery": 1,
        "direct_retailer_verification": 1,
        "rank_verified_options": 1,
    }
    assert telemetry["llm_call_count"] == 0
    assert telemetry["input_tokens"] is None
    assert telemetry["usage_availability"]["llm_tokens"].startswith("unavailable")


@pytest.mark.parametrize(
    ("page", "expected", "reason"),
    [
        (product_page(length=None), "UNVERIFIED", "exact_length"),
        (product_page(stock=None), "UNVERIFIED", "stock_status"),
        (product_page(item_price=None), "UNVERIFIED", "item_price_aud"),
        (product_page(shipping=None), "UNVERIFIED", "postcode_specific_shipping_aud"),
        (product_page(shipping_postcode="2001"), "UNVERIFIED", "postcode_specific_shipping_aud"),
        (product_page(length="1"), "FAIL", "length_mismatch"),
        (product_page(stock="OutOfStock"), "FAIL", "out_of_stock"),
        (product_page(item_price="49", shipping="5"), "FAIL", "over_budget"),
    ],
)
def test_missing_or_mismatched_mandatory_evidence_fails_closed(page, expected, reason):
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages({url: page}, [{"title": "Hose", "link": url}])

    result = run_shopping_workflow(shopping_task(), providers)

    assert result["candidates"][0]["classification"] == expected
    assert reason in result["candidates"][0]["reasons"]
    assert result["recommendations"] == []


def test_limit_exhaustion_returns_partial_verified_results_and_counts_usage():
    urls = ["https://retailer.example/a", "https://retailer.example/b"]
    search_calls: list[DiscoveryRequest] = []
    fetch_calls: list[str] = []

    def search(request: DiscoveryRequest) -> ProviderCall:
        search_calls.append(request)
        index = len(search_calls)
        return ProviderCall([{"title": f"Hose {index}", "link": urls[index - 1]}])

    def fetch(url: str) -> ProviderCall:
        fetch_calls.append(url)
        return ProviderCall(product_page())

    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(google_shopping_search=search, fetch_product_page=fetch),
        ShoppingConfig(
            max_search_calls=2,
            max_page_fetches=1,
            additional_discovery_queries=("query two", "query three"),
        ),
    )

    assert len(search_calls) == 2
    assert len(fetch_calls) == 1
    assert result["status"] == "budget_exhausted"
    assert result["telemetry"]["stop_reason"] == "budget_exhausted"
    assert result["telemetry"]["budget_exhausted_metric"] == "page_fetch_count"
    assert result["telemetry"]["search_call_count"] == 2
    assert result["telemetry"]["page_fetch_count"] == 1
    assert [item["classification"] for item in result["candidates"]] == ["PASS", "UNVERIFIED"]
    assert result["recommendations"][0]["classification"] == "PASS"


def test_browser_fallback_runs_only_when_needed_and_with_explicit_limits():
    url = "https://retailer.example/products/hose"
    browser_requests = []

    def search(_: DiscoveryRequest) -> ProviderCall:
        return ProviderCall([{"title": "Hose", "link": url}])

    def fetch(_: str) -> ProviderCall:
        return ProviderCall(product_page(shipping=None))

    def browser(request) -> ProviderCall:
        browser_requests.append(request)
        return ProviderCall(product_page(), usage=ProviderUsage(browser_pages=1, browser_actions=1))

    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(google_shopping_search=search, fetch_product_page=fetch, browser_inspect_product=browser),
        ShoppingConfig(max_browser_pages=1, max_browser_actions=2),
    )

    assert len(browser_requests) == 1
    assert browser_requests[0].missing_facts == ("postcode_specific_shipping_aud",)
    assert browser_requests[0].max_actions == 2
    assert result["recommendations"][0]["classification"] == "PASS"
    assert result["telemetry"]["browser_page_count"] == 1
    assert result["telemetry"]["browser_action_count"] == 1


def test_browser_fallback_is_not_used_without_configured_page_and_action_limits():
    url = "https://retailer.example/products/hose"
    browser_calls = []
    providers = ShoppingProviders(
        google_shopping_search=lambda _: ProviderCall([{"title": "Hose", "link": url}]),
        fetch_product_page=lambda _: ProviderCall(product_page(shipping=None)),
        browser_inspect_product=lambda _: browser_calls.append(True) or ProviderCall(product_page(), usage=ProviderUsage(browser_pages=1, browser_actions=1)),
    )

    result = run_shopping_workflow(shopping_task(), providers)

    assert browser_calls == []
    assert result["candidates"][0]["classification"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "task",
    [
        "Find a hose length 2 m, postcode 2000; buy it for me",
        "Checkout the hose",
        "Change my account address to postcode 2000",
        "Cancel my order for the hose",
    ],
)
def test_purchase_checkout_and_account_or_order_changes_are_refused(task):
    calls = []
    providers = ShoppingProviders(google_shopping_search=lambda _: calls.append(True) or ProviderCall([]))

    result = run_shopping_workflow(task, providers)

    assert result["status"] == "refused"
    assert result["recommendations"] == []
    assert calls == []


def test_google_redirect_candidates_are_not_fetched_and_secrets_are_redacted():
    secret = "never-log-this-token"
    result = run_shopping_workflow(
        f"Find a length 2 m hose, postcode 2000, token={secret}",
        ShoppingProviders(
            google_shopping_search=lambda _: ProviderCall(
                [{"title": "Hose", "link": "https://www.google.com/aclk?token=private"}]
            ),
            fetch_product_page=lambda _: pytest.fail("Google discovery URL must not be fetched"),
        ),
    )

    rendered = json.dumps(result)
    assert secret not in rendered
    assert "private" not in rendered
    assert result["candidates"] == []
    assert result["telemetry"]["search_call_count"] == 1


def test_retailer_variant_link_is_preserved_while_sensitive_query_is_removed():
    raw_url = "https://retailer.example/products/hose?variant=sku-2&token=private-value"
    fetched = []

    def fetch(url: str) -> ProviderCall:
        fetched.append(url)
        return ProviderCall(product_page())

    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(
            google_shopping_search=lambda _: ProviderCall([{"title": "Hose", "link": raw_url}]),
            fetch_product_page=fetch,
        ),
    )

    assert fetched == ["https://retailer.example/products/hose?variant=sku-2"]
    assert result["recommendations"][0]["product_url"] == fetched[0]
    assert "private-value" not in json.dumps(result)


def test_configured_cost_limit_fails_closed_without_a_cost_estimator():
    calls = []
    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(google_shopping_search=lambda _: calls.append(True) or ProviderCall([])),
        ShoppingConfig(max_estimated_cost_usd=Decimal("1")),
    )

    assert calls == []
    assert result["status"] == "budget_exhausted"
    assert result["telemetry"]["budget_exhausted_metric"] == "estimated_cost_usd"


def test_provider_errors_are_counted_without_logging_raw_error_text():
    url = "https://retailer.example/products/hose"
    search_calls = []

    def search(_: DiscoveryRequest) -> ProviderCall:
        return ProviderCall([{"title": "Hose", "link": url}])

    def fetch(_: str) -> ProviderCall:
        raise ProviderError("secret-cookie=do-not-log")

    result = run_shopping_workflow(
        shopping_task(), ShoppingProviders(google_shopping_search=search, fetch_product_page=fetch)
    )

    rendered = json.dumps(result)
    assert "secret-cookie" not in rendered
    assert result["telemetry"]["error_count"] == 1
    assert result["telemetry"]["calls"][-1]["error_type"] == "ProviderError"
    assert result["candidates"][0]["classification"] == "UNVERIFIED"


def test_product_offer_extraction_uses_exact_postcode_shipping():
    url = "https://retailer.example/products/hose"
    evidence = extract_product_offers(product_page(), url, "2000")

    assert evidence[0].length_m == Decimal("2")
    assert evidence[0].in_stock is True
    assert evidence[0].item_price_aud == Decimal("20.00")
    assert evidence[0].shipping_price_aud == Decimal("5.00")
    assert evidence[0].shipping_postcode == "2000"
    assert extract_product_offers(product_page(shipping_postcode="2001"), url, "2000")[0].shipping_price_aud is None


def test_variant_group_without_leaf_product_offer_does_not_prove_exact_variant():
    url = "https://retailer.example/products/hose"
    parent = json.loads(product_page().split(">", 1)[1].rsplit("<", 1)[0])
    parent["hasVariant"] = [{"@type": "Product", "name": "Hose variants"}]
    providers, _, _ = providers_for_pages(
        {url: '<script type="application/ld+json">' + json.dumps(parent) + "</script>"},
        [{"title": "Hose", "link": url}],
    )

    result = run_shopping_workflow(shopping_task(), providers)

    assert result["candidates"][0]["classification"] == "UNVERIFIED"
    assert result["recommendations"] == []


def test_provider_usage_and_warning_thresholds_are_reported():
    url = "https://retailer.example/products/hose"

    def search(_: DiscoveryRequest) -> ProviderCall:
        return ProviderCall(
            [{"title": "Hose", "link": url}],
            usage=ProviderUsage(estimated_cost_usd=Decimal("0.01"), input_tokens=3, retry_count=1),
        )

    def fetch(_: str) -> ProviderCall:
        return ProviderCall(
            product_page(),
            usage=ProviderUsage(estimated_cost_usd=Decimal("0.02"), output_tokens=4, retry_count=1),
        )

    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(
            google_shopping_search=search,
            fetch_product_page=fetch,
            estimate_cost_usd=lambda _: Decimal("0.02"),
        ),
        ShoppingConfig(
            max_estimated_cost_usd=Decimal("0.05"),
            max_retries=2,
            warning_thresholds={"estimated_cost_usd": Decimal("0.02")},
        ),
    )

    assert result["telemetry"]["estimated_cost_usd"] == "0.03"
    assert result["telemetry"]["estimated_cost_complete"] is True
    assert result["telemetry"]["retry_count"] == 2
    assert result["telemetry"]["calls"][0]["input_tokens_when_available"] == 3
    assert result["telemetry"]["calls"][1]["output_tokens_when_available"] == 4
    assert result["telemetry"]["warnings"]
