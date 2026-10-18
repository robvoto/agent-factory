"""Deterministic LangGraph shopping workflow with injected, offline-testable providers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from time import perf_counter
from typing import Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .budgets import BudgetExceeded, BudgetLimits, BudgetTracker, LimitNotConfigured
from .models import (
    CandidateStatus,
    ClassifiedCandidate,
    ConstraintLedger,
    DiscoveryCandidate,
    PageResponse,
    ProviderUsage,
    SearchResponse,
    ShoppingRequest,
    StructuredEvidence,
)
from .telemetry import RunTelemetry, TelemetryBuilder, utc_now
from .verification import classify_candidate, validate_constraint_keys

_PROHIBITED_ACTION_PATTERNS = (
    re.compile(r"\b(?:buy|purchase|order)\s+(?:me\s+)?[\w-]+\b", re.I),
    re.compile(r"\b(?:checkout|check\s+out)\b", re.I),
    re.compile(r"\bplace\s+(?:an?|the)\s+order\b", re.I),
    re.compile(r"\b(?:pay\s+for|complete|submit)\s+(?:(?:the|an?)\s+)?(?:checkout|order|purchase|item)\b", re.I),
    re.compile(r"\b(?:change|modify|cancel|update|delete)\s+(?:my\s+)?(?:account|order|purchase|address|password|profile|payment\s+details)\b", re.I),
)


class SearchProvider(Protocol):
    provider_id: str
    is_api: bool

    def search(
        self,
        query: str,
        constraints: ConstraintLedger,
        *,
        max_api_calls: int,
        max_retries: int,
    ) -> SearchResponse: ...


class PageFetcher(Protocol):
    provider_id: str
    is_api: bool

    def fetch(
        self,
        candidate: DiscoveryCandidate,
        constraints: ConstraintLedger,
        *,
        max_api_calls: int,
        max_retries: int,
    ) -> PageResponse: ...


class BrowserVerifier(Protocol):
    provider_id: str
    is_api: bool

    def inspect(
        self,
        candidate: DiscoveryCandidate,
        constraints: ConstraintLedger,
        *,
        max_pages: int,
        max_actions: int,
        max_api_calls: int,
        max_retries: int,
    ) -> PageResponse: ...


@dataclass(frozen=True)
class WorkflowResult:
    candidates: tuple[ClassifiedCandidate, ...]
    recommendations: tuple[ClassifiedCandidate, ...]
    constraints: ConstraintLedger
    telemetry: RunTelemetry

    def as_dict(self) -> dict[str, Any]:
        return {
            "constraints": self.constraints.as_dict(),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "recommendations": [candidate.as_dict() for candidate in self.recommendations],
            "telemetry": self.telemetry.as_dict(),
        }


@dataclass
class _RunContext:
    request: ShoppingRequest
    limits: BudgetLimits
    budget: BudgetTracker
    telemetry: TelemetryBuilder
    search_provider: SearchProvider | None
    page_fetcher: PageFetcher | None
    browser_verifier: BrowserVerifier | None
    ledger: ConstraintLedger | None = None
    discovered: list[DiscoveryCandidate] | None = None
    classified: list[ClassifiedCandidate] | None = None
    stop_reason: str = "completed"
    exhausted_metric: str | None = None
    verification_stopped: bool = False

    def set_stop(self, reason: str, metric: str | None = None) -> None:
        if self.stop_reason == "completed":
            self.stop_reason = reason
            self.exhausted_metric = metric


class _GraphState(TypedDict):
    context: _RunContext
    recommendations: list[ClassifiedCandidate]


class ShoppingWorkflow:
    """Build a four-node deterministic graph; all external I/O is supplied by adapters."""

    def __init__(
        self,
        *,
        budgets: BudgetLimits,
        search_provider: SearchProvider | None = None,
        page_fetcher: PageFetcher | None = None,
        browser_verifier: BrowserVerifier | None = None,
    ):
        self.budgets = budgets
        self.search_provider = search_provider
        self.page_fetcher = page_fetcher
        self.browser_verifier = browser_verifier
        graph = StateGraph(_GraphState)
        graph.add_node("capture_constraints", self._capture_constraints)
        graph.add_node("bounded_discovery", self._bounded_discovery)
        graph.add_node("direct_verification", self._direct_verification)
        graph.add_node("rank_shortlist", self._rank_shortlist)
        graph.add_edge(START, "capture_constraints")
        graph.add_edge("capture_constraints", "bounded_discovery")
        graph.add_edge("bounded_discovery", "direct_verification")
        graph.add_edge("direct_verification", "rank_shortlist")
        graph.add_edge("rank_shortlist", END)
        self._graph = graph.compile()

    def run(self, request: ShoppingRequest) -> WorkflowResult:
        started_at = utc_now()
        request_id = request.request_id or str(uuid4())
        run_id = request.run_id or str(uuid4())
        context = _RunContext(
            request=request,
            limits=self.budgets,
            budget=BudgetTracker(self.budgets),
            telemetry=TelemetryBuilder(request_id, run_id, started_at),
            search_provider=self.search_provider,
            page_fetcher=self.page_fetcher,
            browser_verifier=self.browser_verifier,
            discovered=[],
            classified=[],
        )
        state = self._graph.invoke({"context": context, "recommendations": []})
        context = state["context"]
        finished_at = utc_now()
        classifications = tuple(context.classified or ())
        counts = {status: sum(item.status is status for item in classifications) for status in CandidateStatus}
        telemetry = context.telemetry.finish(
            finished_at=finished_at,
            stop_reason=context.stop_reason,
            candidate_discovered_count=len(context.discovered or ()),
            pass_count=counts[CandidateStatus.PASS],
            fail_count=counts[CandidateStatus.FAIL],
            unverified_count=counts[CandidateStatus.UNVERIFIED],
            exhausted_metric=context.exhausted_metric,
            warnings=tuple(context.budget.warnings),
            browser_page_count=context.telemetry.browser_page_count,
            browser_action_count=context.telemetry.browser_action_count,
        )
        return WorkflowResult(
            candidates=classifications,
            recommendations=tuple(state.get("recommendations", [])),
            constraints=context.ledger or ConstraintLedger.capture(request),
            telemetry=telemetry,
        )

    def _capture_constraints(self, state: _GraphState) -> dict[str, _RunContext]:
        context = state["context"]
        context.ledger = ConstraintLedger.capture(context.request)
        if context.request.requested_action != "shopping_research" or any(
            pattern.search(context.request.query) for pattern in _PROHIBITED_ACTION_PATTERNS
        ):
            context.set_stop("prohibited_action_refused")
            return {"context": context}
        try:
            validate_constraint_keys(context.request.hard_constraints)
        except ValueError:
            context.set_stop("invalid_explicit_constraints")
        return {"context": context}

    def _bounded_discovery(self, state: _GraphState) -> dict[str, _RunContext]:
        context = state["context"]
        if context.stop_reason != "completed" or context.search_provider is None:
            return {"context": context}
        assert context.ledger is not None
        queries = context.request.discovery_queries or (context.request.query,)
        deduped: dict[str, DiscoveryCandidate] = {}
        for query in queries:
            provider = context.search_provider
            started = perf_counter()
            api_calls = 0
            try:
                context.budget.reserve("search_calls", provider_id=provider.provider_id)
                provider_is_api = provider.is_api or provider.provider_id.casefold() == "serpapi"
                if provider_is_api:
                    context.budget.reserve("api_calls")
                    api_calls = 1
                response = provider.search(
                    query,
                    context.ledger,
                    max_api_calls=1 if provider_is_api else 0,
                    max_retries=context.limits.max_retries or 0,
                )
                api_calls = self._resolve_api_calls(context, response.usage, api_calls)
                self._record_usage(context, provider.provider_id, response.usage)
                call_status = "error" if context.stop_reason == "provider_limit_violation" else "success"
                self._record_call(context, "bounded_discovery", "search", provider.provider_id, started, call_status, None, response.usage, api_calls)
                for candidate in response.candidates:
                    deduped.setdefault(candidate.url, candidate)
                if context.stop_reason != "completed":
                    break
            except LimitNotConfigured as exc:
                context.set_stop("limit_not_configured", exc.metric)
                break
            except BudgetExceeded as exc:
                context.set_stop("budget_exhausted", exc.metric)
                break
            except Exception:  # Provider boundary: error details may contain sensitive provider data.
                self._record_call(
                    context, "bounded_discovery", "search", provider.provider_id, started,
                    "error", None, ProviderUsage(), api_calls,
                )
                context.set_stop("provider_error")
                break
        context.discovered = list(deduped.values())
        return {"context": context}

    def _direct_verification(self, state: _GraphState) -> dict[str, _RunContext]:
        context = state["context"]
        candidates = context.discovered or []
        context.classified = []
        assert context.ledger is not None
        discovery_budget_stopped = context.stop_reason == "budget_exhausted" and context.exhausted_metric in {
            "max_search_calls",
            "max_api_calls",
        }
        if context.stop_reason != "completed" and (not discovery_budget_stopped or context.verification_stopped):
            context.classified.extend(_unverified(candidate, "verification_skipped_after_stop") for candidate in candidates)
            return {"context": context}
        for index, candidate in enumerate(candidates):
            context.verification_stopped = False
            evidence: StructuredEvidence | None = None
            if context.page_fetcher is not None:
                evidence = self._fetch_page(context, candidate)
            classified = classify_candidate(candidate, evidence, context.ledger.hard)
            if not context.verification_stopped and classified.status is CandidateStatus.UNVERIFIED and context.browser_verifier is not None:
                browser_evidence = self._browser_fallback(context, candidate)
                if browser_evidence is not None:
                    classified = classify_candidate(candidate, browser_evidence, context.ledger.hard)
            context.classified.append(classified)
            if context.verification_stopped:
                context.classified.extend(
                    _unverified(rest, "verification_skipped_after_stop") for rest in candidates[index + 1 :]
                )
                break
        return {"context": context}

    def _fetch_page(self, context: _RunContext, candidate: DiscoveryCandidate) -> StructuredEvidence | None:
        provider = context.page_fetcher
        assert provider is not None and context.ledger is not None
        started = perf_counter()
        api_calls = 0
        try:
            context.budget.reserve("page_fetches")
            if provider.is_api:
                context.budget.reserve("api_calls")
                api_calls = 1
            response = provider.fetch(
                candidate,
                context.ledger,
                max_api_calls=1 if provider.is_api else 0,
                max_retries=context.limits.max_retries or 0,
            )
            api_calls = self._resolve_api_calls(context, response.usage, api_calls)
            self._record_usage(context, provider.provider_id, response.usage)
            call_status = "error" if context.stop_reason == "provider_limit_violation" else "success"
            self._record_call(context, "direct_verification", "page_fetch", provider.provider_id, started, call_status, candidate.url, response.usage, api_calls)
            return response.evidence
        except LimitNotConfigured as exc:
            context.budget.note_unconfigured(exc.metric)
            return None
        except BudgetExceeded as exc:
            context.set_stop("budget_exhausted", exc.metric)
            context.verification_stopped = True
            return None
        except Exception:  # A failed retailer fetch may use the separately bounded browser fallback.
            self._record_call(
                context, "direct_verification", "page_fetch", provider.provider_id, started,
                "error", candidate.url, ProviderUsage(), api_calls,
            )
            return None

    def _browser_fallback(self, context: _RunContext, candidate: DiscoveryCandidate) -> StructuredEvidence | None:
        provider = context.browser_verifier
        assert provider is not None and context.ledger is not None
        started = perf_counter()
        api_calls = 0
        try:
            # One candidate page and one navigation action per bounded adapter call.
            context.budget.reserve("browser_pages")
            context.budget.reserve("browser_actions")
            if provider.is_api:
                context.budget.reserve("api_calls")
                api_calls = 1
            response = provider.inspect(
                candidate,
                context.ledger,
                max_pages=1,
                max_actions=1,
                max_api_calls=1 if provider.is_api else 0,
                max_retries=context.limits.max_retries or 0,
            )
            api_calls = self._resolve_api_calls(context, response.usage, api_calls)
            pages, actions = response.usage.browser_pages, response.usage.browser_actions
            if pages is None or actions is None or pages > 1 or actions > 1:
                self._record_call(context, "direct_verification.browser_fallback", "browser", provider.provider_id, started, "error", candidate.url, response.usage, api_calls)
                context.set_stop("provider_limit_violation", "max_browser_pages_or_actions")
                context.verification_stopped = True
                return None
            context.budget.counts["browser_pages"] -= 1 - pages
            context.budget.counts["browser_actions"] -= 1 - actions
            call_status = "error" if context.stop_reason == "provider_limit_violation" else "success"
            self._record_call(context, "direct_verification.browser_fallback", "browser", provider.provider_id, started, call_status, candidate.url, response.usage, api_calls)
            self._record_usage(context, provider.provider_id, response.usage)
            # An adapter may return evidence after loading only the one host page it was given.
            return response.evidence if pages == 1 and actions == 1 else None
        except LimitNotConfigured as exc:
            context.budget.note_unconfigured(exc.metric)
            return None
        except BudgetExceeded as exc:
            context.set_stop("budget_exhausted", exc.metric)
            context.verification_stopped = True
            return None
        except Exception:
            self._record_call(
                context, "direct_verification.browser_fallback", "browser", provider.provider_id,
                started, "error", candidate.url, ProviderUsage(), api_calls,
            )
            return None

    def _rank_shortlist(self, state: _GraphState) -> dict[str, _RunContext]:
        context = state["context"]
        ranked = sorted(
            (item for item in (context.classified or ()) if item.status is CandidateStatus.PASS),
            key=lambda item: (
                item.delivered_price if item.delivered_price is not None else Decimal("Infinity"),
                item.candidate.url.casefold(),
            ),
        )[:3]
        return {"context": context, "recommendations": ranked}

    @staticmethod
    def _record_usage(context: _RunContext, provider: str, usage: ProviderUsage) -> None:
        tokens = (
            usage.input_tokens + usage.output_tokens
            if usage.input_tokens is not None and usage.output_tokens is not None
            else None
        )
        if context.limits.max_total_tokens is not None and tokens is None:
            context.set_stop("usage_unavailable", "max_total_tokens")
            context.verification_stopped = True
        if context.limits.max_estimated_cost_usd is not None and usage.estimated_cost_usd is None:
            context.set_stop("usage_unavailable", "max_estimated_cost_usd")
            context.verification_stopped = True
        try:
            if usage.retries:
                context.budget.reserve("retries", usage.retries)
            context.budget.record_usage(usage_tokens=tokens or 0, cost_usd=usage.estimated_cost_usd)
        except BudgetExceeded as exc:
            context.set_stop("budget_exhausted", exc.metric)
            context.verification_stopped = True
        except LimitNotConfigured as exc:
            context.set_stop("limit_not_configured", exc.metric)
            context.verification_stopped = True

    @staticmethod
    def _resolve_api_calls(context: _RunContext, usage: ProviderUsage, reserved: int) -> int:
        if usage.api_calls is None:
            return reserved
        actual = usage.api_calls
        if actual < 0:
            context.set_stop("provider_limit_violation", "api_call_count")
            context.verification_stopped = True
            return reserved
        if actual > reserved:
            context.budget.counts["api_calls"] += actual - reserved
            context.set_stop("provider_limit_violation", "max_api_calls")
            context.verification_stopped = True
        elif actual < reserved:
            context.budget.counts["api_calls"] -= reserved - actual
        return actual

    @staticmethod
    def _record_call(
        context: _RunContext,
        phase: str,
        call_type: str,
        provider: str,
        started: float,
        status: str,
        url: str | None,
        usage: ProviderUsage,
        api_calls: int,
    ) -> None:
        context.telemetry.record_call(
            phase=phase,
            call_type=call_type,
            provider=provider,
            duration_ms=_elapsed_ms(started),
            status=status,
            url=url,
            usage=usage,
            api_calls=api_calls,
        )


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _unverified(candidate: DiscoveryCandidate, reason: str) -> ClassifiedCandidate:
    return ClassifiedCandidate(candidate, CandidateStatus.UNVERIFIED, (reason,))
