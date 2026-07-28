from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

from agent_factory import factory_tools
from agent_factory.agent_spec import AgentPackageSpec


def _output_contract() -> dict:
    return {
        "status_values": [
            "success",
            "needs_clarification",
            "waiting_decision",
            "failed",
        ],
        "status_contract": {
            "success": {"terminal": True, "caller_action": "consume_result"},
            "needs_clarification": {
                "terminal": False,
                "caller_action": "provide_clarification",
            },
            "waiting_decision": {
                "terminal": False,
                "caller_action": "provide_decision",
            },
            "failed": {"terminal": True, "caller_action": "inspect_failure"},
        },
    }


def _spec(adapter: str, agent_id: str) -> dict:
    return {
        "id": agent_id,
        "name": f"{adapter} Agent",
        "purpose": "Primary responsibility: Test optional progress generation.\nSelect for: Tests of generated progress adapters.\nDo not select for: Unrelated runtime behavior.",
        "aliases": [agent_id.replace("-agent", "")],
        "runtime": {
            "mode": "subprocess",
            "entrypoint": f"uv run {agent_id} run-agent-task",
            "working_directory": f"/tmp/{agent_id}",
            "input_arg": "--input-json",
            "output_arg": "--output-json",
            "default_execution_mode": "instruction_only",
            "progress": {
                "enabled": True,
                "hub_callable": True,
                "long_running": False,
                "adapter": adapter,
                "schema_version": 1,
                "transport": "stdout_jsonl",
            },
        },
        "output_contract": _output_contract(),
    }


def test_progress_is_rejected_when_not_hub_callable_or_long_running() -> None:
    raw = _spec("simple_agent", "bad-progress-agent")
    raw["runtime"]["progress"]["hub_callable"] = False

    with pytest.raises(ValueError, match="hub_callable"):
        AgentPackageSpec.model_validate(raw)


@pytest.mark.parametrize(
    ("adapter", "agent_id"),
    [
        ("deterministic_workflow", "deterministic-agent"),
        ("simple_agent", "simple-agent"),
        ("deep_agent", "deep-agent"),
    ],
)
def test_generated_progress_adapter_is_optional_and_self_contained(
    adapter: str,
    agent_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(
        factory_tools,
        "_PROGRESS_TEMPLATE_DIR",
        repo_root / "templates" / "progress-adapter",
    )

    result = factory_tools.create_staged_agent_package.invoke(
        {"spec_json": json.dumps(_spec(adapter, agent_id))}
    )

    package = staging / agent_id
    module_path = package / "runtime" / "progress_events.py"
    assert "Staged agent package created" in result
    assert module_path.is_file()
    assert (package / "PROGRESS.md").is_file()
    manifest = json.loads((package / "agent.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["progress"]["adapter"] == adapter

    spec = importlib.util.spec_from_file_location(f"{agent_id}_progress", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stream = io.StringIO()
    reporter = module.ProgressReporter(
        module.StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name=manifest["name"],
    )
    reporter.started()
    if adapter == "deterministic_workflow":
        reporter.phase("validation", "Running deterministic validation.")
    elif adapter == "simple_agent":
        reporter.handle_simple_agent_event({"event": "tool_start", "secret": "hidden"})
    else:
        reporter.handle_deep_agent_event(("updates", {"tools": {"name": "search_memory"}}))

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert all(event["schema_version"] == 1 for event in events)
    assert all(event["run_id"] == "run-1" for event in events)
    assert "hidden" not in stream.getvalue()


def test_manual_short_agent_does_not_receive_progress_adapter(tmp_path, monkeypatch) -> None:
    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)

    result = factory_tools.create_staged_agent_package.invoke(
        {
            "spec_json": json.dumps(
                {
                    "id": "manual-agent",
                    "name": "Manual Agent",
                    "purpose": "Primary responsibility: Perform short standalone work.\nSelect for: Small bounded standalone requests.\nDo not select for: Long-running or unrelated work.",
                    "aliases": ["manual"],
                }
            )
        }
    )

    assert "Staged agent package created" in result
    assert not (staging / "manual-agent" / "runtime" / "progress_events.py").exists()


def test_progress_template_matches_reviewed_factory_adapter() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert (
        repo_root / "src" / "agent_factory" / "progress_events.py"
    ).read_text(encoding="utf-8") == (
        repo_root / "templates" / "progress-adapter" / "runtime" / "progress_events.py"
    ).read_text(encoding="utf-8")


def test_missing_progress_template_fails_before_creating_partial_package(
    tmp_path, monkeypatch
) -> None:
    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(
        factory_tools,
        "_PROGRESS_TEMPLATE_DIR",
        tmp_path / "missing-progress-template",
    )

    result = factory_tools.create_staged_agent_package.invoke(
        {"spec_json": json.dumps(_spec("deep_agent", "missing-template-agent"))}
    )

    assert "Progress adapter template is missing" in result
    assert not (staging / "missing-template-agent").exists()
