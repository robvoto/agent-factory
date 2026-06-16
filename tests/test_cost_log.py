"""Tests for LLM usage and cost logging."""

import json
from pathlib import Path

import pytest

from agent_factory.cost_log import UsageSnapshot, get_usage_summary, record_llm_run


def _write_catalog(path: Path, models: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_at": "2026-06-15T00:00:00+10:00",
                "source": {"url": "https://openai.com/api/pricing/"},
                "models": models,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_record_llm_run_estimates_cost_and_updates_summary(tmp_path):
    catalog = tmp_path / "llm_costs.json"
    usage_log = tmp_path / "llm_usage.json"
    _write_catalog(
        catalog,
        {
            "gpt-5.4-mini": {
                "input_per_1m": 0.75,
                "cached_input_per_1m": 0.075,
                "output_per_1m": 4.5,
            }
        },
    )

    record = record_llm_run(
        operation="invoke_factory_brain",
        request_kind="thread-turn",
        requested_model="openai:gpt-5.4-mini",
        effective_model="openai:gpt-5.4-mini",
        status="ok",
        duration_seconds=1.234567,
        usage_by_model={
            "openai:gpt-5.4-mini": UsageSnapshot(
                input_tokens=2000,
                output_tokens=1000,
                total_tokens=3000,
                cached_input_tokens=500,
            )
        },
        thread_id="thread-1",
        usage_log_path=usage_log,
        cost_catalog_path=catalog,
    )

    assert record["cost"]["status"] == "estimated"
    assert record["cost"]["known_usd"] == pytest.approx(0.005663, abs=1e-6)
    assert record["duration_ms"] == pytest.approx(1234.567, abs=1e-6)

    summary = get_usage_summary(usage_log)
    assert summary["totals"]["calls"] == 1
    assert summary["totals"]["ok_runs"] == 1
    assert summary["totals"]["input_tokens"] == 2000
    assert summary["totals"]["output_tokens"] == 1000
    assert summary["totals"]["known_cost_usd"] == pytest.approx(0.005663, abs=1e-6)
    assert summary["by_model"]["gpt-5.4-mini"]["calls"] == 1
    assert summary["recent_runs"][-1]["operation"] == "invoke_factory_brain"


def test_record_llm_run_keeps_unknown_costs_obvious(tmp_path):
    catalog = tmp_path / "llm_costs.json"
    usage_log = tmp_path / "llm_usage.json"
    _write_catalog(
        catalog,
        {
            "gpt-4.1-mini": {
                "status": "unknown",
                "notes": "Pricing not verified in this snapshot.",
            }
        },
    )

    record = record_llm_run(
        operation="resume_factory_brain",
        request_kind="resume",
        requested_model="openai:gpt-4.1-mini",
        effective_model="openai:gpt-4.1-mini",
        status="ok",
        duration_seconds=0.5,
        usage_by_model={
            "openai:gpt-4.1-mini": UsageSnapshot(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            )
        },
        thread_id="thread-2",
        usage_log_path=usage_log,
        cost_catalog_path=catalog,
    )

    assert record["cost"]["status"] == "unknown"
    assert record["cost"]["known_usd"] is None

    summary = get_usage_summary(usage_log)
    assert summary["totals"]["unknown_cost_runs"] == 1
    assert summary["by_model"]["gpt-4.1-mini"]["unknown_cost_runs"] == 1
