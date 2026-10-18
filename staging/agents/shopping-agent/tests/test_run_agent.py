"""Offline tests for the Agent Hub subprocess adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

import run_agent  # noqa: E402
from shopping_agent.workflow import ShoppingProviders  # noqa: E402


def test_process_payload_requires_explicit_runtime_limits(monkeypatch):
    for name in (
        "SHOPPING_MAX_API_CALLS",
        "SHOPPING_MAX_PAGE_FETCHES",
        "SHOPPING_TIMEOUT_SECONDS",
        "SERPAPI_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    result = run_agent.process_payload({"task": "Find a garden hose"})

    assert result["status"] == "failed"
    assert "SHOPPING_MAX_API_CALLS" in result["summary"]
    assert "SERPAPI_KEY" not in result["summary"]


def test_process_payload_passes_hub_ids_and_explicit_limits(monkeypatch):
    monkeypatch.setenv("SHOPPING_MAX_API_CALLS", "12")
    monkeypatch.setenv("SHOPPING_MAX_PAGE_FETCHES", "4")
    monkeypatch.setenv("SHOPPING_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("SERPAPI_KEY", "test-only-key")
    observed = {}

    def fake_create_providers(api_key, *, timeout_seconds):
        observed["api_key"] = api_key
        observed["timeout_seconds"] = timeout_seconds
        return ShoppingProviders()

    def fake_workflow(task, providers, config, *, request_id, run_id):
        observed.update({
            "task": task,
            "providers": providers,
            "config": config,
            "request_id": request_id,
            "run_id": run_id,
        })
        return {"status": "provider_unavailable", "telemetry": {"calls": []}}

    monkeypatch.setattr(run_agent, "create_shopping_providers", fake_create_providers)
    monkeypatch.setattr(run_agent, "run_shopping_workflow", fake_workflow)
    result = run_agent.process_payload({
        "task": "Find a garden hose",
        "task_kind": "shopping",
        "request_id": "request-1",
        "run_id": "run-1",
        "source": "agent-hub",
        "source_request": "Find a garden hose",
        "execution_mode": "execute",
        "progress_jsonl": "/tmp/progress.jsonl",
        "project_root": str(PACKAGE_ROOT),
        "project_id": "garden",
        "project_contract_version": 1,
        "project_fingerprint": "fingerprint",
        "project_context": {"schema_version": 1, "project_root": str(PACKAGE_ROOT), "references": []},
        "references": ["https://example.com"],
        "backlog_reference": {"type": "issue", "id": "GH-1"},
        "human_approved": True,
        "approval_token": "approval",
        "resume": {"cursor": "one"},
        "decision": {"option": "continue"},
        "governed_skills": [{"slug": "shopping", "version": 1}],
        "execution_constraints": {"profile": "test", "max_api_calls": 12},
    })

    assert result["status"] == "failed"
    assert observed["task"] == "Find a garden hose"
    assert observed["request_id"] == "request-1"
    assert observed["run_id"] == "run-1"
    assert observed["api_key"] == "test-only-key"
    assert observed["config"].max_search_calls == 3
    assert observed["config"].max_api_calls == 12
    assert observed["config"].max_page_fetches == 4
    summary = json.loads(result["summary"])
    assert summary["status"] == "provider_unavailable"
    assert "test-only-key" not in result["summary"]


@pytest.mark.parametrize(
    ("workflow_status", "hub_status"),
    [
        ("completed", "success"),
        ("provider_unavailable", "failed"),
        ("refused", "failed"),
        ("budget_exhausted", "failed"),
        ("failed", "failed"),
    ],
)
def test_process_payload_maps_terminal_workflow_status(monkeypatch, workflow_status, hub_status):
    monkeypatch.setenv("SHOPPING_MAX_API_CALLS", "12")
    monkeypatch.setenv("SHOPPING_MAX_PAGE_FETCHES", "4")
    monkeypatch.setenv("SHOPPING_TIMEOUT_SECONDS", "7.5")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    monkeypatch.setattr(run_agent, "create_shopping_providers", lambda *args, **kwargs: ShoppingProviders())
    monkeypatch.setattr(
        run_agent,
        "run_shopping_workflow",
        lambda *args, **kwargs: {"status": workflow_status, "telemetry": {"calls": []}},
    )
    result = run_agent.process_payload({"task": "Find a garden hose"})

    assert result["status"] == hub_status


@pytest.mark.parametrize(
    ("task", "expected_question"),
    [
        ("Find a 2 m hose under AUD 50", "What Australian postcode"),
        ("Find a 2 m hose under $50, postcode 2000", "Does the stated dollar budget mean AUD?"),
        ("Find a 2 m hose, postcode 2000, postcode 2001", "What single Australian postcode"),
        ("Find a 2 m hose exactly 3 m, postcode 2000", "What single exact product length"),
        ("Find a 2-m hose exactly 3 m, postcode 2000", "What single exact product length"),
        ("Find a 6–7-foot hose, postcode 2000", "What single exact product length"),
        ("Find a -7-foot hose, postcode 2000", "What single exact product length"),
        ("Find a 2 m hose under AUD 50, max AUD 50, postcode 2000", "What single AUD budget"),
        ("Find a 2 m hose AUD 50, $50, postcode 2000", "Does the stated dollar budget mean AUD?"),
        ("Find a 2 m hose $50, AUD 50, postcode 2000", "Does the stated dollar budget mean AUD?"),
    ],
)
def test_real_workflow_clarification_reaches_hub_without_provider_calls(monkeypatch, task, expected_question):
    monkeypatch.setenv("SHOPPING_MAX_API_CALLS", "12")
    monkeypatch.setenv("SHOPPING_MAX_PAGE_FETCHES", "4")
    monkeypatch.setenv("SHOPPING_TIMEOUT_SECONDS", "7.5")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    def forbidden_call(_):
        pytest.fail("Ambiguous tasks must not call search, page, or browser providers")

    monkeypatch.setattr(
        run_agent,
        "create_shopping_providers",
        lambda *args, **kwargs: ShoppingProviders(
            google_shopping_search=forbidden_call,
            fetch_product_page=forbidden_call,
            browser_inspect_product=forbidden_call,
        ),
    )

    result = run_agent.process_payload({"task": task + "; token=test-private-value"})

    assert result["status"] == "needs_clarification"
    assert expected_question in result["summary"]
    assert "test-private-value" not in result["summary"]
    assert "resume_token" not in result


def test_all_conflicting_fields_reach_hub_as_fixed_questions_without_input_echo(monkeypatch):
    monkeypatch.setenv("SHOPPING_MAX_API_CALLS", "12")
    monkeypatch.setenv("SHOPPING_MAX_PAGE_FETCHES", "4")
    monkeypatch.setenv("SHOPPING_TIMEOUT_SECONDS", "7.5")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    def forbidden_call(_):
        pytest.fail("Conflicting fields must not invoke a provider")

    monkeypatch.setattr(
        run_agent,
        "create_shopping_providers",
        lambda *args, **kwargs: ShoppingProviders(
            google_shopping_search=forbidden_call,
            fetch_product_page=forbidden_call,
            browser_inspect_product=forbidden_call,
        ),
    )
    result = run_agent.process_payload({
        "task": "Find secret-product-X100 exactly 2 m and 3 m, postcode 2000 and postcode 2001, "
        "under $50 and max AUD 60; token=test-private-value",
    })

    assert result == {
        "status": "needs_clarification",
        "summary": (
            "What single Australian postcode should I use to verify delivery and the delivered price? "
            "What single exact product length and unit do you require? "
            "What single AUD budget should I use, and may the price equal that amount?"
        ),
    }


def test_process_payload_rejects_unrecognized_hub_fields(monkeypatch):
    result = run_agent.process_payload({"task": "Find a hose", "secret": "redacted"})

    assert result == {
        "status": "failed",
        "summary": "Shopping task envelope validation failed.",
    }
