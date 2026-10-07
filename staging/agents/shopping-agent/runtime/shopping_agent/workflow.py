"""Deterministic LangGraph workflow for the staged Shopping Agent MVP."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .constraints import ParsedRequest, parse_request, query_plan
from .models import (
    DiscoveryCandidate,
    RunTelemetry,
    ShoppingConstraints,
    VerifiedCandidate,
)
from .providers import ProviderError, SearchBudgetExceeded, SerpApiDiscovery
from .settings import MissingCredentialError, ShoppingConfig
from .verification import RetailerVerifier


class ShoppingState(TypedDict, total=False):
    task: str
    request_id: str
    run_id: str
    destination_postcode: str | None
    constraints: ShoppingConstraints | None
    clarification_question: str | None
    discovered: list[DiscoveryCandidate]
    verified: list[VerifiedCandidate]
    shortlist: list[VerifiedCandidate]
    unverified: list[VerifiedCandidate]
    status: str
    stop_reason: str
    summary: str
    telemetry: RunTelemetry


@dataclass(frozen=True)
class WorkflowDependencies:
    config: ShoppingConfig
    discovery: SerpApiDiscovery
    verifier: RetailerVerifier


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_telemetry(request_id: str, run_id: str) -> RunTelemetry:
    return RunTelemetry(
        request_id=request_id,
        run_id=run_id,
        started_at=_now_iso(),
        _started_monotonic=time.perf_counter(),
    )


def _build_graph(dependencies: WorkflowDependencies):
    def parse_node(state: ShoppingState) -> dict[str, Any]:
        parsed: ParsedRequest = parse_request(
            state["task"],
            destination_postcode=state.get("destination_postcode")
            or dependencies.config.destination_postcode,
            destination_country=dependencies.config.destination_country,
        )
        if parsed.constraints is None:
            return {
                "constraints": None,
                "clarification_question": parsed.clarification_question,
                "status": "needs_clarification",
                "stop_reason": "clarification_required",
            }
        return {
            "constraints": parsed.constraints,
            "clarification_question": None,
            "status": "running",
            "stop_reason": "",
        }

    def route_after_parse(state: ShoppingState) -> str:
        return "render" if state.get("status") == "needs_clarification" else "discover"

    def discover_node(state: ShoppingState) -> dict[str, Any]:
        constraints = state["constraints"]
        assert constraints is not None
        candidates: list[DiscoveryCandidate] = []
        try:
            queries = query_plan(
                constraints,
                max_queries=dependencies.config.budget.max_search_calls,
            )
            for query in queries:
                call = dependencies.discovery.search(query, constraints)
                candidates.extend(call.candidates)
        except MissingCredentialError:
            return {
                "status": "failed",
                "stop_reason": "missing_provider_credential",
                "summary": "SerpApi is not configured; no discovery request was sent.",
            }
        except SearchBudgetExceeded:
            return {
                "status": "failed",
                "stop_reason": "budget_exhausted",
                "summary": "The configured SerpApi search budget was exhausted.",
            }
        except ProviderError:
            return {
                "status": "failed",
                "stop_reason": "provider_error",
                "summary": "SerpApi discovery failed; no unverified result was promoted.",
            }

        unique: list[DiscoveryCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidates:
            key = (
                candidate.title.lower(),
                (candidate.merchant or "").lower(),
                (candidate.direct_url or candidate.discovery_url or "").lower(),
            )
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        telemetry = state["telemetry"]
        telemetry.candidate_discovered_count = len(unique)
        if not unique:
            return {
                "discovered": [],
                "status": "success",
                "stop_reason": "no_candidates",
                "summary": "SerpApi returned no product candidates for the bounded query plan.",
            }
        return {"discovered": unique, "status": "running", "stop_reason": ""}

    def route_after_discover(state: ShoppingState) -> str:
        return "render" if state.get("status") != "running" else "verify"

    def verify_node(state: ShoppingState) -> dict[str, Any]:
        constraints = state["constraints"]
        assert constraints is not None
        verified = [
            dependencies.verifier.verify(candidate, constraints)
            for candidate in state.get("discovered", [])
        ]
        telemetry = state["telemetry"]
        telemetry.pass_count = sum(item.status == "PASS" for item in verified)
        telemetry.fail_count = sum(item.status == "FAIL" for item in verified)
        telemetry.unverified_count = sum(item.status == "UNVERIFIED" for item in verified)
        return {"verified": verified, "status": "running", "stop_reason": ""}

    def rank_node(state: ShoppingState) -> dict[str, Any]:
        verified = state.get("verified", [])
        passes = [item for item in verified if item.status == "PASS"]
        passes.sort(
            key=lambda item: (
                item.evidence.delivered_price_aud is None,
                item.evidence.delivered_price_aud or 0,
                item.candidate.title.lower(),
            )
        )
        return {
            "shortlist": passes[:3],
            "unverified": [item for item in verified if item.status == "UNVERIFIED"][:3],
            "status": "success",
            "stop_reason": "completed",
        }

    def render_node(state: ShoppingState) -> dict[str, Any]:
        status = state.get("status", "failed")
        if status == "needs_clarification":
            summary = state.get("clarification_question") or "Please clarify the shopping constraints."
            stop_reason = "clarification_required"
        elif status == "failed":
            summary = state.get("summary") or "Shopping run failed safely before producing recommendations."
            stop_reason = state.get("stop_reason", "failed")
        else:
            shortlist = state.get("shortlist", [])
            if shortlist:
                lines = ["Verified options:"]
                for index, item in enumerate(shortlist, start=1):
                    evidence = item.evidence
                    lines.append(
                        f"{index}. {item.candidate.title} — "
                        f"A${evidence.delivered_price_aud:.2f} delivered; "
                        f"{item.candidate.merchant or 'retailer'}"
                    )
                summary = "\n".join(lines)
            else:
                summary = (
                    "No fully verified options found. Discovery candidates were not recommended "
                    "because direct exact-variant, stock, or delivered-price evidence was incomplete."
                )
            stop_reason = state.get("stop_reason", "completed")
        telemetry = state["telemetry"]
        telemetry.finish(
            stop_reason=stop_reason,
            now_iso=_now_iso(),
            monotonic_now=time.perf_counter(),
        )
        return {"summary": summary, "stop_reason": stop_reason, "status": status}

    graph = StateGraph(ShoppingState)
    graph.add_node("parse_constraints", parse_node)
    graph.add_node("discover", discover_node)
    graph.add_node("verify", verify_node)
    graph.add_node("rank", rank_node)
    graph.add_node("render", render_node)
    graph.add_edge(START, "parse_constraints")
    graph.add_conditional_edges(
        "parse_constraints",
        route_after_parse,
        {"discover": "discover", "render": "render"},
    )
    graph.add_conditional_edges(
        "discover",
        route_after_discover,
        {"verify": "verify", "render": "render"},
    )
    graph.add_edge("verify", "rank")
    graph.add_edge("rank", "render")
    graph.add_edge("render", END)
    return graph.compile()


def run_shopping(
    task: str,
    *,
    dependencies: WorkflowDependencies,
    request_id: str | None = None,
    run_id: str | None = None,
    destination_postcode: str | None = None,
    telemetry: RunTelemetry | None = None,
) -> dict[str, Any]:
    request_id = request_id or str(uuid.uuid4())
    run_id = run_id or str(uuid.uuid4())
    telemetry = telemetry or new_telemetry(request_id, run_id)
    for component in (dependencies.discovery, dependencies.verifier):
        if hasattr(component, "telemetry"):
            component.telemetry = telemetry
    state: ShoppingState = {
        "task": task,
        "request_id": request_id,
        "run_id": run_id,
        "destination_postcode": destination_postcode,
        "constraints": None,
        "clarification_question": None,
        "discovered": [],
        "verified": [],
        "shortlist": [],
        "unverified": [],
        "status": "running",
        "stop_reason": "",
        "summary": "",
        "telemetry": telemetry,
    }
    result = _build_graph(dependencies).invoke(state)
    return {
        "status": result.get("status", "failed"),
        "result_kind": "shopping_result",
        "summary": result.get("summary", ""),
        "constraints": result.get("constraints").to_dict()
        if result.get("constraints") is not None
        else None,
        "shortlist": [item.to_dict() for item in result.get("shortlist", [])],
        "unverified_candidates": [
            item.to_dict() for item in result.get("unverified", [])
        ],
        "failed_candidates": [
            item.to_dict()
            for item in result.get("verified", [])
            if item.status == "FAIL"
        ],
        "telemetry": telemetry.to_dict(),
    }


def default_dependencies(
    config: ShoppingConfig,
    telemetry: RunTelemetry,
    *,
    env: dict[str, str] | None = None,
) -> WorkflowDependencies:
    discovery = SerpApiDiscovery(config, telemetry, env=env)
    verifier = RetailerVerifier(config, telemetry)
    return WorkflowDependencies(config=config, discovery=discovery, verifier=verifier)
