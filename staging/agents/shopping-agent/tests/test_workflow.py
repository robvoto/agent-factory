from __future__ import annotations

from decimal import Decimal

from src.budgets import BudgetLimits
from src.models import (
    CandidateStatus,
    DiscoveryCandidate,
    PageResponse,
    ProviderUsage,
    SearchResponse,
    ShoppingRequest,
    StructuredEvidence,
)
from src.telemetry import redact_log_payload
from src.workflow import ShoppingWorkflow


class MockSearch:
    provider_id = "serpapi"
    is_api = True

    def __init__(self, candidates, *, reported_api_calls=None):
        self.candidates = candidates
        self.reported_api_calls = reported_api_calls
        self.calls = []
        self.constraints = []

    def search(self, query, constraints, *, max_api_calls, max_retries):
        assert max_api_calls == 1
        assert max_retries == 0
        self.calls.append(query)
        self.constraints.append(constraints.as_dict())
        return SearchResponse(
            (self.candidates[len(self.calls) - 1],),
            ProviderUsage(
                input_tokens=2,
                output_tokens=1,
                cached_tokens=0,
                estimated_cost_usd=Decimal("0.01"),
                api_calls=self.reported_api_calls,
            ),
        )


class MockPages:
    provider_id = "retailer-page-fetch"
    is_api = False

    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def fetch(self, candidate, constraints, *, max_api_calls, max_retries):
        assert max_api_calls == 0
        assert max_retries == 0
        self.calls.append(candidate.candidate_id)
        return PageResponse(
            StructuredEvidence(candidate.url, "retailer_page", self.documents[candidate.candidate_id]),
            ProviderUsage(estimated_cost_usd=Decimal("0.02")),
        )


class MockBrowser:
    provider_id = "offline-browser-fixture"
    is_api = False

    def __init__(self, document, *, pages=1, actions=1):
        self.document = document
        self.pages = pages
        self.actions = actions
        self.bounds = []

    def inspect(self, candidate, constraints, *, max_pages, max_actions, max_api_calls, max_retries):
        self.bounds.append((max_pages, max_actions))
        return PageResponse(
            StructuredEvidence(candidate.url, "browser_page", self.document),
            ProviderUsage(
                browser_pages=self.pages,
                browser_actions=self.actions,
                estimated_cost_usd=Decimal("0.03"),
            ),
        )


def all_limits(**overrides):
    values = {
        "max_llm_calls": 0,
        "max_total_tokens": 100,
        "max_estimated_cost_usd": Decimal("10"),
        "max_search_calls": 10,
        "max_api_calls": 10,
        "max_page_fetches": 10,
        "max_browser_pages": 10,
        "max_browser_actions": 10,
        "max_retries": 0,
    }
    values.update(overrides)
    return BudgetLimits(**values)


def test_constraints_propagate_and_serpapi_is_capped_at_three(retailer_jsonld):
    candidates = tuple(DiscoveryCandidate(str(i), f"https://shop{i}.example/item") for i in range(5))
    search = MockSearch(candidates)
    pages = MockPages({str(i): retailer_jsonld(price=str(100 + i)) for i in range(5)})
    request = ShoppingRequest(
        "camera",
        hard_constraints={"product.color": "Blue"},
        preferences={"brand": "Acme"},
        discovery_queries=("q1", "q2", "q3", "q4", "q5"),
    )

    result = ShoppingWorkflow(budgets=all_limits(), search_provider=search, page_fetcher=pages).run(request)

    assert len(search.calls) == 3
    assert all(item["hard"] == {"product.color": "Blue"} for item in search.constraints)
    assert all(item["preferences"] == {"brand": "Acme"} for item in search.constraints)
    assert len(result.recommendations) == 3
    assert [item.delivered_price for item in result.recommendations] == [Decimal("105"), Decimal("106"), Decimal("107")]
    assert result.telemetry.search_call_count == 3
    assert result.telemetry.api_call_count == 3
    assert result.telemetry.estimated_cost_usd == Decimal("0.09")
    assert result.telemetry.input_tokens is None
    assert result.telemetry.output_tokens is None
    assert result.telemetry.provider_usage["serpapi"]["input_tokens"] == 6
    assert result.telemetry.provider_usage["serpapi"]["output_tokens"] == 3


def test_only_fully_verified_pass_candidates_are_recommended(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    search = MockSearch((candidate,))
    result = ShoppingWorkflow(
        budgets=all_limits(), search_provider=search, page_fetcher=None
    ).run(ShoppingRequest("camera"))

    assert result.candidates[0].status is CandidateStatus.UNVERIFIED
    assert result.recommendations == ()


def test_provider_that_exceeds_its_api_call_bound_is_stopped():
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    search = MockSearch((candidate,), reported_api_calls=2)
    result = ShoppingWorkflow(budgets=all_limits(), search_provider=search).run(ShoppingRequest("camera"))

    assert result.telemetry.stop_reason == "provider_limit_violation"
    assert result.telemetry.exhausted_metric == "max_api_calls"
    assert result.telemetry.api_call_count == 2
    assert result.recommendations == ()


@pytest.mark.parametrize(
    ("limits", "usage", "expected_metric"),
    (
        (
            all_limits(max_total_tokens=100, max_estimated_cost_usd=None),
            ProviderUsage(input_tokens=1, output_tokens=None, estimated_cost_usd=Decimal("0.01"), api_calls=1),
            "max_total_tokens",
        ),
        (
            all_limits(max_total_tokens=None, max_estimated_cost_usd=Decimal("1")),
            ProviderUsage(input_tokens=1, output_tokens=1, estimated_cost_usd=None, api_calls=1),
            "max_estimated_cost_usd",
        ),
    ),
)
def test_missing_usage_under_configured_hard_cap_stops_further_calls(limits, usage, expected_metric):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")

    class IncompleteUsageSearch:
        provider_id = "serpapi"
        is_api = True

        def __init__(self):
            self.calls = []

        def search(self, query, constraints, *, max_api_calls, max_retries):
            self.calls.append(query)
            return SearchResponse((candidate,), usage)

    search = IncompleteUsageSearch()
    result = ShoppingWorkflow(budgets=limits, search_provider=search).run(
        ShoppingRequest("camera", discovery_queries=("first query", "second query"))
    )

    assert search.calls == ["first query"]
    assert result.telemetry.stop_reason == "usage_unavailable"
    assert result.telemetry.exhausted_metric == expected_metric
    assert result.telemetry.api_call_count == 1
    assert result.recommendations == ()


def test_provider_exceptions_keep_reserved_api_calls_in_telemetry(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")

    class RaisingApiSearch:
        provider_id = "raising-search-api"
        is_api = True

        def search(self, query, constraints, *, max_api_calls, max_retries):
            raise RuntimeError("private provider details")

    search_error = ShoppingWorkflow(budgets=all_limits(), search_provider=RaisingApiSearch()).run(
        ShoppingRequest("camera")
    )
    assert search_error.telemetry.api_call_count == 1
    assert search_error.telemetry.provider_usage["raising-search-api"]["api_call_count"] == 1

    class RaisingApiPages:
        provider_id = "raising-page-api"
        is_api = True

        def fetch(self, candidate, constraints, *, max_api_calls, max_retries):
            raise RuntimeError("private provider details")

    page_error = ShoppingWorkflow(
        budgets=all_limits(),
        search_provider=MockSearch((candidate,)),
        page_fetcher=RaisingApiPages(),
    ).run(ShoppingRequest("camera"))
    assert page_error.telemetry.api_call_count == 2
    assert page_error.telemetry.provider_usage["raising-page-api"]["api_call_count"] == 1

    class EmptyPages:
        provider_id = "retailer-page-fetch"
        is_api = False

        def fetch(self, candidate, constraints, *, max_api_calls, max_retries):
            return PageResponse(
                None,
                ProviderUsage(
                    input_tokens=0,
                    output_tokens=0,
                    estimated_cost_usd=Decimal("0.01"),
                ),
            )

    class RaisingApiBrowser:
        provider_id = "raising-browser-api"
        is_api = True

        def inspect(self, candidate, constraints, *, max_pages, max_actions, max_api_calls, max_retries):
            raise RuntimeError("private provider details")

    browser_error = ShoppingWorkflow(
        budgets=all_limits(),
        search_provider=MockSearch((candidate,)),
        page_fetcher=EmptyPages(),
        browser_verifier=RaisingApiBrowser(),
    ).run(ShoppingRequest("camera"))
    assert browser_error.telemetry.api_call_count == 2
    assert browser_error.telemetry.provider_usage["raising-browser-api"]["api_call_count"] == 1


def test_hard_page_fetch_budget_returns_partial_verified_results(retailer_jsonld):
    candidates = (
        DiscoveryCandidate("first", "https://one.example/item"),
        DiscoveryCandidate("second", "https://two.example/item"),
    )
    search = MockSearch(candidates)
    pages = MockPages({"first": retailer_jsonld(price="50"), "second": retailer_jsonld(price="60")})
    result = ShoppingWorkflow(
        budgets=all_limits(max_page_fetches=1), search_provider=search, page_fetcher=pages
    ).run(ShoppingRequest("camera", discovery_queries=("one", "two")))

    assert result.telemetry.stop_reason == "budget_exhausted"
    assert result.telemetry.exhausted_metric == "max_page_fetches"
    assert result.candidates[0].status is CandidateStatus.PASS
    assert result.candidates[1].status is CandidateStatus.UNVERIFIED
    assert [item.candidate.candidate_id for item in result.recommendations] == ["first"]
    assert result.telemetry.page_fetch_count == 1


def test_browser_fallback_receives_and_reports_explicit_bounds(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    search = MockSearch((candidate,))
    pages = MockPages({"camera": None})
    browser = MockBrowser(retailer_jsonld())
    result = ShoppingWorkflow(
        budgets=all_limits(max_browser_pages=1, max_browser_actions=1),
        search_provider=search,
        page_fetcher=pages,
        browser_verifier=browser,
    ).run(ShoppingRequest("camera"))

    assert browser.bounds == [(1, 1)]
    assert result.candidates[0].status is CandidateStatus.PASS
    assert result.telemetry.browser_page_count == 1
    assert result.telemetry.browser_action_count == 1
    assert result.telemetry.calls[-1].safe_domain_or_url == "shop.example"


def test_unconfigured_browser_limit_disables_fallback(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    search = MockSearch((candidate,))
    pages = MockPages({"camera": None})
    browser = MockBrowser(retailer_jsonld())
    result = ShoppingWorkflow(
        budgets=all_limits(max_browser_pages=None),
        search_provider=search,
        page_fetcher=pages,
        browser_verifier=browser,
    ).run(ShoppingRequest("camera"))

    assert browser.bounds == []
    assert result.candidates[0].status is CandidateStatus.UNVERIFIED
    assert "operation_disabled_limit_not_configured:max_browser_pages" in result.telemetry.warnings


def test_unconfigured_api_and_page_limits_disable_calls(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    api_search = MockSearch((candidate,))
    no_api_limit = ShoppingWorkflow(
        budgets=all_limits(max_api_calls=None), search_provider=api_search
    ).run(ShoppingRequest("camera"))
    assert api_search.calls == []
    assert no_api_limit.telemetry.stop_reason == "limit_not_configured"
    assert no_api_limit.telemetry.exhausted_metric == "max_api_calls"

    search = MockSearch((candidate,))
    pages = MockPages({"camera": retailer_jsonld()})
    no_page_limit = ShoppingWorkflow(
        budgets=all_limits(max_page_fetches=None), search_provider=search, page_fetcher=pages
    ).run(ShoppingRequest("camera"))
    assert pages.calls == []
    assert no_page_limit.candidates[0].status is CandidateStatus.UNVERIFIED
    assert "operation_disabled_limit_not_configured:max_page_fetches" in no_page_limit.telemetry.warnings


def test_browser_provider_overrun_is_reported_and_not_recommended(retailer_jsonld):
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    search = MockSearch((candidate,))
    pages = MockPages({"camera": None})
    browser = MockBrowser(retailer_jsonld(), pages=2)
    result = ShoppingWorkflow(
        budgets=all_limits(max_browser_pages=1, max_browser_actions=1),
        search_provider=search,
        page_fetcher=pages,
        browser_verifier=browser,
    ).run(ShoppingRequest("camera"))

    assert result.telemetry.stop_reason == "provider_limit_violation"
    assert result.telemetry.browser_page_count == 2
    assert result.telemetry.error_count == 1
    assert result.recommendations == ()


def test_prohibited_actions_are_refused_before_provider_calls():
    candidate = DiscoveryCandidate("camera", "https://shop.example/item")
    for query, action in (
        ("Buy this camera", "shopping_research"),
        ("buy camera", "shopping_research"),
        ("purchase camera", "shopping_research"),
        ("Please checkout", "shopping_research"),
        ("Cancel my order", "shopping_research"),
        ("Place an order", "shopping_research"),
        ("Change my password", "shopping_research"),
        ("Compare cameras", "purchase"),
        ("Update my account", "shopping_research"),
    ):
        search = MockSearch((candidate,))
        result = ShoppingWorkflow(budgets=all_limits(), search_provider=search).run(
            ShoppingRequest(query, requested_action=action)
        )
        assert search.calls == []
        assert result.telemetry.stop_reason == "prohibited_action_refused"
        assert result.recommendations == ()


def test_log_redaction_and_allowlisted_telemetry():
    payload = {
        "authorization": "Bearer super-secret",
        "X-API-Key": "header-secret",
        "account_data": {"name": "private name"},
        "url": "https://shop.example/item?token=secret-value",
        "input_tokens": 12,
        "status": "success",
    }
    safe = redact_log_payload(payload)

    assert safe["authorization"] == "[REDACTED]"
    assert safe["X-API-Key"] == "[REDACTED]"
    assert safe["account_data"] == "[REDACTED]"
    assert safe["url"] == "https://shop.example"
    assert safe["input_tokens"] == 12
    assert safe["status"] == "success"
