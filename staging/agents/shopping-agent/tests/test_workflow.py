from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shopping_agent import (
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
from shopping_agent.workflow import classify_evidence


def product_page(
    *,
    length: str | None = "2",
    stock: str | None = "InStock",
    item_price: str | None = "20.00",
    shipping: str | None = "5.00",
    shipping_postcode: str = "2000",
    shipping_country: object = "AU",
    name: str = "Garden hose",
    item_condition: str | None = None,
    offer_item_condition: str | None = None,
) -> str:
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "itemCondition": f"https://schema.org/{item_condition}" if item_condition else None,
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
            "itemCondition": f"https://schema.org/{offer_item_condition}" if offer_item_condition else None,
            "shippingDetails": (
                [
                    {
                        "@type": "OfferShippingDetails",
                        "shippingRate": {"@type": "MonetaryAmount", "value": shipping, "priceCurrency": "AUD"},
                        "shippingDestination": {
                            "@type": "DefinedRegion",
                            "postalCode": shipping_postcode,
                            "addressCountry": shipping_country,
                        },
                    }
                ]
                if shipping is not None
                else []
            ),
        },
    }
    return '<script type="application/ld+json">' + json.dumps(product) + "</script>"


def shopping_task() -> str:
    return "Find an exactly 2 m hose under AUD 50, postcode 2000"


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
    assert constraints.budget_aud == Decimal(60)
    assert constraints.budget_is_strict is True
    assert not constraints.clarification_questions


@pytest.mark.parametrize(
    ("budget_phrase", "strict"),
    [
        ("under AUD 30", True),
        ("below A$30", True),
        ("LESS THAN 30 AUD", True),
        ("maximum AUD 30", False),
        ("max AUD 30", False),
        ("up to AUD 30", False),
        ("at most AUD 30", False),
        ("AUD 30", False),
    ],
)
@pytest.mark.parametrize("delivered_price", ["29.99", "30.00", "30.01"])
def test_workflow_preserves_explicit_budget_comparison(budget_phrase, strict, delivered_price):
    task = f"Find a hose exactly 2 m, {budget_phrase}, postcode 2000"
    parsed = parse_constraints(task)
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(item_price=delivered_price, shipping="0.00")},
        [{"title": "Garden hose", "link": url}],
    )

    result = run_shopping_workflow(task, providers)

    assert parsed.budget_aud == Decimal("30")
    assert parsed.budget_is_strict is strict
    assert parsed.required_product_terms == ("hose",)
    price = Decimal(delivered_price)
    within_budget = price < Decimal("30") if strict else price <= Decimal("30")
    candidate = result["candidates"][0]
    assert candidate["classification"] == ("PASS" if within_budget else "FAIL")
    assert ("over_budget" in candidate["reasons"]) is (not within_budget)
    assert len(result["recommendations"]) == int(within_budget)


@pytest.mark.parametrize("operator", ["under", "at most"])
@pytest.mark.parametrize("item_price", ["24.99", "25.00", "25.01"])
@pytest.mark.parametrize("item_only", [False, True])
def test_budget_comparison_keeps_item_only_and_delivered_basis(operator, item_price, item_only):
    suffix = ", item price only" if item_only else ""
    constraints = parse_constraints(
        f"Find a hose exactly 2 m, {operator} AUD 25, postcode 2000{suffix}"
    )
    evidence = extract_product_offers(
        product_page(item_price=item_price, shipping="5.00"),
        "https://retailer.example/products/hose",
        "2000",
    )[0]

    status, reasons, delivered = classify_evidence(evidence, constraints, "retailer.example")

    price_basis = Decimal(item_price) if item_only else Decimal(item_price) + Decimal("5.00")
    within_budget = price_basis < Decimal("25") if operator == "under" else price_basis <= Decimal("25")
    assert constraints.budget_item_only is item_only
    assert delivered == Decimal(item_price) + Decimal("5.00")
    assert status == ("PASS" if within_budget else "FAIL")
    assert ("over_budget" in reasons) is (not within_budget)


def test_constraint_parser_preserves_explicit_model_and_variant_tokens():
    constraints = parse_constraints("Find a cordless drill model X100 18 V, postcode 2000")

    assert constraints.required_variant_tokens == ("x100", "18v", "cordless")


@pytest.mark.parametrize(
    ("clauses", "field", "question"),
    [
        (("exactly 2 m", "AUD 50", "postcode 2000", "post code 2001"), "postcode",
         "What single Australian postcode should I use to verify delivery and the delivered price?"),
        (("exactly 2 m", "3 m", "AUD 50", "postcode 2000"), "required_length_m",
         "What single exact product length and unit do you require?"),
        (("length 200 cm", "exactly 3 m", "AUD 50", "postcode 2000"), "required_length_m",
         "What single exact product length and unit do you require?"),
        (("exactly 2 m", "under AUD 50", "below A$60", "postcode 2000"), "budget_aud",
         "What single AUD budget should I use, and may the price equal that amount?"),
        (("exactly 2 m", "under AUD 50", "max AUD 50", "postcode 2000"), "budget_aud",
         "What single AUD budget should I use, and may the price equal that amount?"),
        (("exactly 2 m", "$50", "AUD 50", "postcode 2000"), "budget_aud",
         "Does the stated dollar budget mean AUD?"),
        (("exactly 2 m", "under $50", "at most AUD 60", "postcode 2000"), "budget_aud",
         "What single AUD budget should I use, and may the price equal that amount?"),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_constraints_stop_before_provider_calls_in_either_order(clauses, field, question, reverse):
    ordered_clauses = reversed(clauses) if reverse else clauses
    task = "Find a blue hose model X100, " + ", ".join(ordered_clauses)

    def forbidden_call(_):
        pytest.fail("Conflicting or ambiguous constraints must not invoke a provider")

    parsed = parse_constraints(task)
    result = run_shopping_workflow(
        task,
        ShoppingProviders(
            google_shopping_search=forbidden_call,
            fetch_product_page=forbidden_call,
            browser_inspect_product=forbidden_call,
        ),
    )

    assert getattr(parsed, field) is None
    assert parsed.clarification_questions == (question,)
    assert parsed.required_product_terms == ("blue", "hose", "x100")
    assert parsed.required_variant_tokens == ("x100", "blue")
    assert result["status"] == "needs_clarification"
    assert result["clarification_questions"] == [question]
    assert result["recommendations"] == []
    assert result["telemetry"]["calls"] == []
    assert result["telemetry"]["api_call_count"] == 0


@pytest.mark.parametrize(
    ("bounds", "strict"),
    [
        ("under AUD 50, below A$50.00, less than 50 AUD", True),
        ("max AUD 50, maximum A$50.00, at most 50 AUD, up to AUD 50, AUD 50", False),
    ],
)
def test_equivalent_repeated_constraints_allow_verification_and_preserve_product_identity(bounds, strict):
    task = (
        f"Find a blue hose model X100, exactly 2 m, length 200 cm, {bounds}, "
        "postcode 2000, post code 2000"
    )
    url = "https://retailer.example/products/hose"
    providers, searches, fetches = providers_for_pages(
        {url: product_page(name="Blue hose X100")},
        [{"title": "Blue hose X100", "link": url}],
    )

    parsed = parse_constraints(task)
    result = run_shopping_workflow(task, providers)

    assert parsed.required_length_m == Decimal("2")
    assert parsed.postcode == "2000"
    assert parsed.budget_aud == Decimal("50")
    assert parsed.budget_is_strict is strict
    assert parsed.clarification_questions == ()
    assert parsed.required_product_terms == ("blue", "hose", "x100")
    assert parsed.required_variant_tokens == ("x100", "blue")
    assert result["status"] == "completed"
    assert result["recommendations"][0]["classification"] == "PASS"
    assert len(searches) == len(fetches) == 1


def test_masking_all_constraint_spans_does_not_remove_an_identical_numeric_model():
    parsed = parse_constraints(
        "Find a blue hose model 2000, exactly 2 m, length 200 cm, "
        "max AUD 50, at most A$50, postcode 2000, post code 2000"
    )

    assert parsed.clarification_questions == ()
    assert parsed.required_product_terms == ("blue", "hose")
    assert parsed.required_variant_tokens == ("2000", "blue")


def test_ascii_hyphenated_length_is_normalized_to_existing_metres():
    parsed = parse_constraints("Find a hose length 2-m, AUD 50, postcode 2000")

    assert parsed.required_length_m == Decimal("2")
    assert parsed.clarification_questions == ()


def test_unicode_unit_separator_is_not_silently_normalized():
    parsed = parse_constraints("Find a hose length 7–foot, AUD 50, postcode 2000")

    assert parsed.required_length_m is None
    assert parsed.clarification_questions == ("What exact product length and unit do you require?",)


@pytest.mark.parametrize("requested_length", ["7-foot", "7-ft", "7 - foot"])
@pytest.mark.parametrize(
    ("evidence_length", "expected_classification"),
    [("2.1336", "PASS"), ("1.8288", "FAIL"), (None, "UNVERIFIED")],
)
def test_hyphenated_request_still_requires_exact_structured_length_evidence(requested_length, evidence_length, expected_classification):
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(length=evidence_length, name="7-foot hose")},
        [{"title": "7-foot hose", "link": url}],
    )

    task = f"Find a {requested_length} hose, AUD 50, postcode 2000"
    parsed = parse_constraints(task)
    result = run_shopping_workflow(task, providers)

    assert parsed.required_length_m == Decimal("2.1336")
    assert parsed.required_product_terms == ("hose",)
    candidate = result["candidates"][0]
    assert candidate["classification"] == expected_classification
    assert len(result["recommendations"]) == int(expected_classification == "PASS")
    if expected_classification == "FAIL":
        assert "length_mismatch" in candidate["reasons"]
    elif expected_classification == "UNVERIFIED":
        assert "exact_length" in candidate["reasons"]


@pytest.mark.parametrize("hyphenated", ["2-m", "0.5-m"])
def test_hyphenated_and_plain_equivalent_lengths_do_not_conflict(hyphenated):
    centimetres = "200" if hyphenated == "2-m" else "50"
    parsed = parse_constraints(
        f"Find a hose {hyphenated}, exactly {centimetres} cm, AUD 50, postcode 2000"
    )

    assert parsed.required_length_m == Decimal(centimetres) / Decimal("100")
    assert parsed.clarification_questions == ()
    assert parsed.required_product_terms == ("hose",)
    assert parsed.required_variant_tokens == ()


@pytest.mark.parametrize(
    "unsupported_length",
    [
        "6-7-foot", "6 – 7-foot", "6—7ft", "6−7-foot", "6 to 7-foot", "6to7ft",
        "-7-foot", "−7-foot", "- 7ft", "exactly -7ft", "6–7-foot, exactly 2 m",
    ],
)
def test_range_and_negative_lengths_request_one_exact_length_before_providers(unsupported_length):
    task = f"Find a hose {unsupported_length}, AUD 50, postcode 2000"

    def forbidden_call(_):
        pytest.fail("Ranges and negative lengths must not invoke providers")

    parsed = parse_constraints(task)
    result = run_shopping_workflow(
        task,
        ShoppingProviders(
            google_shopping_search=forbidden_call,
            fetch_product_page=forbidden_call,
            browser_inspect_product=forbidden_call,
        ),
    )

    assert parsed.required_length_m is None
    assert parsed.clarification_questions == ("What single exact product length and unit do you require?",)
    assert parsed.required_product_terms == ("hose",)
    assert parsed.required_variant_tokens == ()
    assert result["status"] == "needs_clarification"
    assert result["telemetry"]["calls"] == []
    assert result["recommendations"] == []


@pytest.mark.parametrize("model", ["X100-7-foot", "X100-6-7-foot"])
def test_hyphenated_model_identity_is_not_reinterpreted_as_a_request_length(model):
    parsed = parse_constraints(f"Find a hose model {model}, exactly 2 m, AUD 50, postcode 2000")

    assert parsed.required_length_m == Decimal("2")
    assert parsed.clarification_questions == ()
    assert model.casefold() in parsed.required_variant_tokens
    assert "x100" in parsed.required_product_terms
    assert "foot" in parsed.required_product_terms


@pytest.mark.parametrize("label", ["model", "version", "variant", "colour", "color", "material", "finish", "style"])
def test_labeled_numeric_identity_is_not_reclassified_as_an_additional_length(label):
    parsed = parse_constraints(
        f"Find a blue hose {label} 2000 in stock, exactly 2 m, AUD 50, postcode 2000"
    )

    assert parsed.required_length_m == Decimal("2")
    assert parsed.clarification_questions == ()
    assert parsed.required_product_terms == ("blue", "hose", "stock")
    assert parsed.required_variant_tokens == ("2000", "blue")


def test_literal_numeric_model_and_following_colour_are_verified_separately():
    task = "Find a hose model 2000 red exactly 2 m, AUD 50, postcode 2000"
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Red hose model 2000")},
        [{"title": "Red hose model 2000", "link": url}],
    )

    parsed = parse_constraints(task)
    result = run_shopping_workflow(task, providers)

    assert parsed.required_variant_tokens == ("2000", "red")
    assert parsed.required_product_terms == ("hose", "red")
    assert parsed.clarification_questions == ()
    assert result["recommendations"][0]["classification"] == "PASS"


@pytest.mark.parametrize(
    ("discovered_name", "direct_name"),
    [
        ("Red hose model 2000", "Red hose model 2001"),
        ("Red hose model 2000", "Red hose"),
        ("Red hose model 2000", "Red hose 2000"),
        ("Red hose model 2001", "Red hose model 2000"),
        ("Red hose", "Red hose model 2000"),
    ],
)
def test_missing_or_different_explicit_numeric_model_is_not_verified(discovered_name, direct_name):
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(name=direct_name)},
        [{"title": discovered_name, "link": url}],
    )

    result = run_shopping_workflow(
        "Find a hose model 2000 red exactly 2 m, AUD 50, postcode 2000", providers,
    )

    assert result["candidates"][0]["classification"] == "UNVERIFIED"
    assert "requested_variant" in result["candidates"][0]["reasons"]
    assert result["recommendations"] == []


@pytest.mark.parametrize(
    ("stock", "classification", "reason"),
    [("OutOfStock", "FAIL", "out_of_stock"), (None, "UNVERIFIED", "stock_status")],
)
def test_numeric_model_identity_does_not_bypass_direct_stock_evidence(stock, classification, reason):
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Red hose model 2000", stock=stock)},
        [{"title": "Red hose model 2000", "link": url}],
    )

    result = run_shopping_workflow(
        "Find a hose model 2000 red exactly 2 m, AUD 50, postcode 2000", providers,
    )

    assert result["candidates"][0]["classification"] == classification
    assert reason in result["candidates"][0]["reasons"]
    assert result["recommendations"] == []


def test_multiple_literal_identity_values_keep_their_original_positions_during_normalization():
    parsed = parse_constraints(
        "Find a hose model 2000 red version 3000 blue, exactly 2 m, AUD 50, postcode 2000"
    )

    assert parsed.required_variant_tokens == ("2000", "3000", "red", "blue")
    assert parsed.required_product_terms == ("blue", "hose", "red")


@pytest.mark.parametrize("label", ["", "size ", "capacity "])
def test_unlabeled_and_measurement_label_number_unit_normalization_is_unchanged(label):
    parsed = parse_constraints(f"Find a cordless drill {label}18 V, postcode 2000")

    assert parsed.required_variant_tokens == ("18v", "cordless")
    assert parsed.clarification_questions == ()


@pytest.mark.parametrize("model", ["X100", "X100-7-foot", "X100-2000"])
def test_alphanumeric_and_hyphenated_identity_values_remain_literal(model):
    parsed = parse_constraints(f"Find a hose model {model} red exactly 2 m, AUD 50, postcode 2000")

    assert model.casefold() in parsed.required_variant_tokens
    assert parsed.required_length_m == Decimal("2")
    assert parsed.clarification_questions == ()


def test_literal_in_stock_model_identifier_is_preserved():
    parsed = parse_constraints("Find a hose model in-stock exactly 2 m, AUD 50, postcode 2000")

    assert "in-stock" in parsed.required_variant_tokens
    assert "stock" in parsed.required_product_terms
    assert parsed.clarification_questions == ()


@pytest.mark.parametrize("label", ["size", "capacity"])
def test_existing_size_and_capacity_measurements_still_participate_in_length_conflicts(label):
    parsed = parse_constraints(f"Find a hose {label} 2 m, exactly 3 m, AUD 50, postcode 2000")

    assert parsed.required_length_m is None
    assert parsed.clarification_questions == ("What single exact product length and unit do you require?",)


def test_numeric_identity_value_is_not_stolen_by_following_currency_marker():
    parsed = parse_constraints("Find a blue hose version 2000, AUD 50, postcode 2000, exactly 2 m")

    assert parsed.budget_aud == Decimal("50")
    assert parsed.clarification_questions == ()
    assert parsed.required_variant_tokens == ("2000", "blue")


def test_explicit_money_amount_is_not_also_read_as_a_length():
    parsed = parse_constraints("Find a hose exactly 2 m, under AUD 50 in stock, postcode 2000")

    assert parsed.required_length_m == Decimal("2")
    assert parsed.budget_aud == Decimal("50")
    assert parsed.budget_is_strict is True
    assert parsed.clarification_questions == ()


def test_explicit_postcode_is_not_also_read_as_a_length():
    parsed = parse_constraints("Find a hose postcode 2000 in stock, exactly 2 m, AUD 50")

    assert parsed.required_length_m == Decimal("2")
    assert parsed.postcode == "2000"
    assert parsed.budget_aud == Decimal("50")
    assert parsed.clarification_questions == ()
    assert "2000in" not in parsed.required_variant_tokens


def test_constraint_parser_preserves_explicit_color_variant():
    constraints = parse_constraints("Find a blue garden hose exactly 2 m, postcode 2000")

    assert "blue" in constraints.required_variant_tokens


def test_constraint_parser_preserves_material_feature_and_labeled_numeric_size():
    constraints = parse_constraints("Find a waterproof leather boot size 10, postcode 2000")

    assert {"waterproof", "leather", "10"} <= set(constraints.required_variant_tokens)


def test_constraint_parser_preserves_all_meaningful_product_terms():
    constraints = parse_constraints("Find Adidas running shoes for men under AUD 100, postcode 2000")

    assert {"adidas", "running", "shoes", "men"} <= set(constraints.required_product_terms)


def test_color_variant_mismatch_in_direct_product_evidence_is_unverified():
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Red garden hose")},
        [{"title": "Blue garden hose", "link": url}],
    )

    result = run_shopping_workflow(
        "Find a blue garden hose exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    candidate = result["candidates"][0]
    assert candidate["classification"] == "UNVERIFIED"
    assert "requested_variant" in candidate["reasons"]
    assert result["recommendations"] == []


def test_missing_postcode_and_ambiguous_dollar_budget_request_clarification():
    constraints = parse_constraints("Find a 2 m hose under $50")

    assert constraints.required_length_m == Decimal(2)
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


def test_browser_fallback_warns_before_call_and_enforces_page_limit(caplog):
    url = "https://retailer.example/products/hose"
    browser_requests = []

    def search(_: DiscoveryRequest) -> ProviderCall:
        return ProviderCall([{"title": "Hose", "link": url}])

    def fetch(_: str) -> ProviderCall:
        return ProviderCall(product_page(shipping=None))

    def browser(request) -> ProviderCall:
        assert "browser_page_count may reach configured warning threshold 1" in caplog.text
        browser_requests.append(request)
        return ProviderCall(product_page(), usage=ProviderUsage(browser_pages=1, browser_actions=100))

    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(google_shopping_search=search, fetch_product_page=fetch, browser_inspect_product=browser),
        ShoppingConfig(max_browser_pages=2, warning_thresholds={"browser_page_count": 1}),
    )

    assert len(browser_requests) == 1
    assert browser_requests[0].missing_facts == ("postcode_specific_shipping_aud",)
    assert browser_requests[0].max_pages == 2
    assert result["recommendations"][0]["classification"] == "PASS"
    assert result["telemetry"]["browser_page_count"] == 1
    assert result["telemetry"]["browser_action_count"] == 100


def test_browser_fallback_is_not_used_without_configured_page_limit():
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


@pytest.mark.parametrize("task", ["buy camera", "purchase camera", "order camera"])
def test_direct_purchase_verbs_without_object_article_are_refused(task):
    calls = []
    providers = ShoppingProviders(google_shopping_search=lambda _: calls.append(True) or ProviderCall([]))

    result = run_shopping_workflow(task, providers)

    assert result["status"] == "refused"
    assert result["recommendations"] == []
    assert calls == []


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


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/item",
        "https://printer.local/item",
        "https://service.internal/item",
        "https://127.0.0.1/item",
        "https://127.1/item",
        "https://2130706433/item",
        "https://0x7f000001/item",
        "https://0177.0.0.1/item",
        "https://10.0.0.7/item",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/item",
    ],
)
def test_local_and_non_global_retailer_urls_are_not_fetched(url):
    fetched = []
    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(
            google_shopping_search=lambda _: ProviderCall([{"title": "Hose", "link": url}]),
            fetch_product_page=lambda value: fetched.append(value) or ProviderCall(product_page()),
        ),
    )

    assert fetched == []
    assert result["candidates"] == []
    assert result["recommendations"] == []


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


def test_provider_errors_are_counted_without_logging_raw_error_text():
    url = "https://retailer.example/products/hose"

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

    assert evidence[0].length_m == Decimal(2)
    assert evidence[0].in_stock is True
    assert evidence[0].item_price_aud == Decimal("20.00")
    assert evidence[0].shipping_price_aud == Decimal("5.00")
    assert evidence[0].shipping_postcode == "2000"
    assert extract_product_offers(product_page(shipping_postcode="2001"), url, "2000")[0].shipping_price_aud is None


@pytest.mark.parametrize(
    "country",
    [
        "AU", "au", "AUS", "Australia",
        {"@type": "Country", "identifier": "AU"},
        {"@type": "Country", "name": "Australia"},
        {"@type": "Country", "identifier": "AUS", "name": "Australia"},
    ],
)
def test_explicit_australian_shipping_country_allows_verified_delivery(country):
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(shipping_country=country)},
        [{"title": "Garden hose", "link": url}],
    )

    result = run_shopping_workflow(shopping_task(), providers)

    assert result["candidates"][0]["classification"] == "PASS"
    assert result["recommendations"][0]["delivered_price_aud"] == "25.00"


@pytest.mark.parametrize(
    "country",
    [
        None, "", "US", "NZ", "unknown",
        {"@type": "Country"},
        {"@type": "Country", "identifier": "NZ"},
        {"@type": "Country", "identifier": "AU", "name": "New Zealand"},
        {"@type": "Country", "identifier": "unknown", "name": "Australia"},
        {"name": "Australia"},
    ],
)
def test_unproven_australian_shipping_country_never_ranks_a_candidate(country):
    url = "https://retailer.example/products/hose"
    page = product_page(shipping_country=country, shipping="0.00")
    evidence = extract_product_offers(page, url, "2000")[0]
    providers, _, _ = providers_for_pages(
        {url: page}, [{"title": "Garden hose", "link": url}],
    )

    result = run_shopping_workflow(shopping_task(), providers)

    assert evidence.shipping_price_aud is None
    assert evidence.shipping_postcode is None
    assert result["candidates"][0]["classification"] == "UNVERIFIED"
    assert "postcode_specific_shipping_aud" in result["candidates"][0]["reasons"]
    assert result["recommendations"] == []


@pytest.mark.parametrize(
    ("destinations", "eligible", "extra"),
    [
        ({"postalCode": "2000"}, [], {}),
        ([{"addressCountry": "AU", "postalCode": "2001"}, {"addressCountry": "NZ", "postalCode": "2000"}], [], {}),
        ({"addressCountry": "AU", "postalCode": "2001"}, {"addressCountry": "NZ", "postalCode": "2000"}, {}),
        ({"postalCode": "2000"}, {"addressCountry": "AU", "postalCode": "2001"}, {}),
        ({"addressCountry": "NZ", "postalCode": "2000"}, [], {"addressCountry": "AU"}),
        ({"addressCountry": "NZ", "postalCode": "2000"}, [], {"shippingOrigin": {"addressCountry": "AU", "postalCode": "2000"}}),
        ({"addressCountry": "AU", "address": {"addressCountry": "NZ", "postalCode": "2000"}}, [], {}),
    ],
)
def test_shipping_country_and_postcode_must_belong_to_same_destination(destinations, eligible, extra):
    page = json.loads(product_page().split(">", 1)[1].rsplit("<", 1)[0])
    page["offers"]["shippingDetails"] = {
        "@type": "OfferShippingDetails",
        "shippingDestination": destinations,
        "eligibleRegion": eligible,
        "shippingRate": {"priceCurrency": "AUD", "value": "0.00"},
        **extra,
    }
    page["offers"]["seller"] = {"address": {"addressCountry": "AU", "postalCode": "2000"}}

    evidence = extract_product_offers(page, "https://retailer.example/products/hose", "2000")[0]

    assert evidence.shipping_price_aud is None
    assert evidence.shipping_postcode is None


def test_eligible_region_requires_its_own_explicit_australian_country():
    page = json.loads(product_page().split(">", 1)[1].rsplit("<", 1)[0])
    detail = page["offers"]["shippingDetails"][0]
    detail["eligibleRegion"] = detail.pop("shippingDestination")

    evidence = extract_product_offers(page, "https://retailer.example/products/hose", "2000")[0]

    assert evidence.shipping_price_aud == Decimal("5.00")
    assert evidence.shipping_postcode == "2000"


@pytest.mark.parametrize("other_country", ["NZ", "AU"])
@pytest.mark.parametrize("reverse", [False, True])
def test_shipping_rate_ambiguity_uses_only_proven_australian_destinations(other_country, reverse):
    page = json.loads(product_page().split(">", 1)[1].rsplit("<", 1)[0])
    detail = page["offers"]["shippingDetails"][0]
    other_detail = {
        "@type": "OfferShippingDetails",
        "shippingDestination": {"addressCountry": other_country, "postalCode": "2000"},
        "shippingRate": {"priceCurrency": "AUD", "value": "0.00"},
    }
    page["offers"]["shippingDetails"] = [other_detail, detail] if reverse else [detail, other_detail]

    evidence = extract_product_offers(page, "https://retailer.example/products/hose", "2000")[0]

    assert evidence.shipping_price_aud == (None if other_country == "AU" else Decimal("5.00"))
    assert evidence.shipping_postcode == (None if other_country == "AU" else "2000")


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


def test_provider_usage_and_warning_thresholds_are_reported_before_next_call(caplog):
    url = "https://retailer.example/products/hose"
    search_requests: list[DiscoveryRequest] = []

    def search(request: DiscoveryRequest) -> ProviderCall:
        if search_requests:
            assert "search_call_count reached configured warning threshold 1" in caplog.text
        search_requests.append(request)
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
        ),
        ShoppingConfig(
            max_search_calls=2,
            warning_thresholds={"search_call_count": 1},
            additional_discovery_queries=("another garden hose",),
        ),
    )

    assert result["telemetry"]["estimated_cost_usd"] == "0.04"
    assert result["telemetry"]["estimated_cost_complete"] is True
    assert result["telemetry"]["retry_count"] == 3
    assert result["telemetry"]["calls"][0]["input_tokens_when_available"] == 3
    assert result["telemetry"]["calls"][2]["output_tokens_when_available"] == 4
    assert result["telemetry"]["warnings"]
    assert result["status"] == "completed"
    assert len(search_requests) == 2


def test_missing_provider_cost_keeps_the_aggregate_unknown():
    url = "https://retailer.example/products/hose"
    providers = ShoppingProviders(
        google_shopping_search=lambda _: ProviderCall(
            [{"title": "Hose", "link": url}],
            usage=ProviderUsage(estimated_cost_usd=Decimal("0.01")),
        ),
        fetch_product_page=lambda _: ProviderCall(product_page()),
    )

    result = run_shopping_workflow(shopping_task(), providers)

    assert result["telemetry"]["estimated_cost_usd"] is None
    assert result["telemetry"]["estimated_cost_complete"] is False
    assert result["telemetry"]["calls"][0]["estimated_cost_usd_when_available"] == "0.01"
    assert result["telemetry"]["calls"][1]["estimated_cost_usd_when_available"] is None


def test_provider_search_exception_is_counted_and_redacted():
    secret_text = "provider failed with api_key=do-not-log"

    def search(_: DiscoveryRequest) -> ProviderCall:
        raise RuntimeError(secret_text)

    result = run_shopping_workflow(
        shopping_task(),
        ShoppingProviders(google_shopping_search=search),
    )

    telemetry = result["telemetry"]
    assert telemetry["search_call_count"] == 1
    assert telemetry["api_call_count"] == 1
    assert telemetry["error_count"] == 1
    assert telemetry["calls"][0]["status"] == "error"
    assert telemetry["calls"][0]["error_type"] == "RuntimeError"
    assert secret_text not in json.dumps(telemetry)
    assert telemetry["estimated_cost_usd"] is None
    assert telemetry["usage_availability"]["provider_cost"] == "partial or unavailable"


def test_no_provider_calls_report_cost_as_unavailable():
    result = run_shopping_workflow(shopping_task(), ShoppingProviders())

    assert result["telemetry"]["calls"] == []
    assert result["telemetry"]["estimated_cost_usd"] is None
    assert result["telemetry"]["usage_availability"]["provider_cost"] == "unavailable"


@pytest.mark.parametrize(
    "field",
    ["max_retries", "max_llm_calls", "max_total_tokens", "max_estimated_cost_usd", "max_browser_actions"],
)
def test_config_rejects_prohibited_per_run_and_action_ceilings(field):
    with pytest.raises(TypeError):
        ShoppingConfig(**{field: 1})


def test_product_evidence_must_match_the_discovered_product():
    url = "https://retailer.example/products/hose"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Garden hose")},
        [{"title": "Cordless drill", "link": url}],
    )

    result = run_shopping_workflow(shopping_task(), providers)

    assert result["candidates"][0]["classification"] == "UNVERIFIED"
    assert "requested_product_identity" in result["candidates"][0]["reasons"]
    assert result["recommendations"] == []


def test_numeric_variant_mismatch_cannot_be_recommended():
    url = "https://retailer.example/products/drill"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Cordless drill X100 12V")},
        [{"title": "Cordless drill X100 18V", "link": url}],
    )

    result = run_shopping_workflow(
        "Find a cordless drill model X100 18 V, postcode 2000",
        providers,
    )

    assert result["candidates"][0]["classification"] == "UNVERIFIED"
    assert "requested_product_identity" in result["candidates"][0]["reasons"]
    assert "requested_variant" in result["candidates"][0]["reasons"]
    assert result["recommendations"] == []


def test_search_query_redacts_credentials_and_private_identifiers_before_provider_call():
    secret = "never-send-this-token"
    prose_secret = "never-send-prose-secret"
    bearer_secret = "standalone.secret.token"
    email = "private.person@example.com"
    phone = "0412 345 678"
    requests: list[DiscoveryRequest] = []

    def search(request: DiscoveryRequest) -> ProviderCall:
        requests.append(request)
        return ProviderCall([])

    run_shopping_workflow(
        f"Find a garden hose, postcode 2000, token={secret}, password is {prose_secret}, "
        f"Bearer {bearer_secret}, contact={email}, phone {phone}",
        ShoppingProviders(google_shopping_search=search),
    )

    assert len(requests) == 1
    assert "garden hose" in requests[0].query.casefold()
    assert secret not in requests[0].query
    assert prose_secret not in requests[0].query
    assert bearer_secret not in requests[0].query
    assert email not in requests[0].query
    assert phone not in requests[0].query


def test_material_mismatch_in_direct_product_evidence_is_unverified():
    url = "https://retailer.example/products/wallet"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Synthetic wallet for men")},
        [{"title": "Leather wallet for men", "link": url}],
    )

    result = run_shopping_workflow(
        "Find a leather wallet for men exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    candidate = result["candidates"][0]
    assert candidate["classification"] == "UNVERIFIED"
    assert "requested_variant" in candidate["reasons"]
    assert result["recommendations"] == []


def test_brand_mismatch_in_direct_product_evidence_is_unverified():
    url = "https://retailer.example/products/shoes"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Puma running shoes for men")},
        [{"title": "Adidas running shoes for men", "link": url}],
    )

    result = run_shopping_workflow(
        "Find Adidas running shoes for men exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    candidate = result["candidates"][0]
    assert candidate["classification"] == "UNVERIFIED"
    assert "requested_product_terms" in candidate["reasons"]
    assert result["recommendations"] == []


def test_new_product_request_rejects_used_product_evidence():
    url = "https://retailer.example/products/shoes"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Used New Balance running shoes", item_condition="UsedCondition")},
        [{"title": "New running shoes", "link": url}],
    )

    result = run_shopping_workflow(
        "Find new running shoes exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    candidate = result["candidates"][0]
    assert candidate["classification"] == "UNVERIFIED"
    assert "requested_product_condition" in candidate["reasons"]
    assert result["recommendations"] == []


def test_new_balance_brand_does_not_prove_new_product_condition():
    url = "https://retailer.example/products/shoes"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="New Balance shoes")},
        [{"title": "New Balance shoes", "link": url}],
    )

    result = run_shopping_workflow(
        "Find new shoes exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    candidate = result["candidates"][0]
    assert candidate["classification"] == "UNVERIFIED"
    assert "requested_product_condition" in candidate["reasons"]
    assert result["recommendations"] == []


def test_new_balance_brand_with_explicit_new_condition_is_verified():
    url = "https://retailer.example/products/shoes"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="New Balance running shoes", item_condition="NewCondition")},
        [{"title": "New running shoes", "link": url}],
    )

    result = run_shopping_workflow(
        "Find new running shoes exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    assert result["candidates"][0]["classification"] == "PASS"
    assert len(result["recommendations"]) == 1


def test_new_product_request_accepts_explicit_offer_new_condition():
    url = "https://retailer.example/products/shoes"
    providers, _, _ = providers_for_pages(
        {url: product_page(name="Running shoes", offer_item_condition="NewCondition")},
        [{"title": "Running shoes", "link": url}],
    )

    result = run_shopping_workflow(
        "Find new running shoes exactly 2 m under AUD 50, postcode 2000",
        providers,
    )

    assert result["candidates"][0]["classification"] == "PASS"
    assert len(result["recommendations"]) == 1
