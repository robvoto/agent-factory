from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_factory.build_task import (
    AgentBuildTask,
    BuildTaskError,
    assert_task_matches_staged_package,
)
from agent_factory.factory_brain import build_factory_specialist_result
from agent_factory.specialist_result import validate_next_task_contract


def _manifest(agent_id: str = "test-agent") -> dict:
    return {
        "id": agent_id,
        "version": "1.0.0",
        "manifest_schema_version": 1,
        "name": "Test Agent",
        "purpose": (
            "Primary responsibility: Perform bounded test work.\n"
            "Select for: Requests requiring the test workflow.\n"
            "Do not select for: Unrelated work."
        ),
        "aliases": ["test"],
        "tools": [],
        "mcp_servers": [],
        "permissions": {
            "network": False,
            "filesystem": "none",
            "shell": False,
            "requires_approval": True,
        },
        "memory": {"scope": "none", "retention": "none"},
        "design": {
            "runtime_pattern": "deterministic_workflow",
            "runtime_pattern_reason": "The staged workflow is fixed and inspectable.",
        },
        "runtime": {"mode": "manual", "entrypoint": None},
        "input_contract": {
            "protocol": "agent-hub.task",
            "protocol_version": 1,
            "required_fields": ["task"],
            "optional_fields": [],
            "accepted_context": [],
            "required_context": [],
        },
        "interaction_contract": {
            "progress": False,
            "clarification": True,
            "approval": True,
            "resume": False,
            "cancellation": True,
        },
        "task_contract": {"task_kinds": [], "task_kind_descriptions": {}},
        "project_context_contract": {
            "supported_schema_versions": [1],
            "required": False,
            "capabilities": [],
            "enforced_filesystem_permission": "none",
        },
        "target_project_access": {
            "requires_explicit_project_root": False,
            "authorization_modes": [],
            "allows_target_creation": False,
            "creation_scope": "none",
            "fail_closed_when": [],
        },
        "output_contract": None,
    }


def _stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root = tmp_path
    package = root / "staging" / "agents" / "test-agent"
    package.mkdir(parents=True)
    (package / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")

    from agent_factory import factory_brain, factory_tools, storage

    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", root)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", root / "staging" / "agents")
    monkeypatch.setattr(factory_brain, "_PROJECT_ROOT", root)
    monkeypatch.setattr(storage, "_DEFAULT_DB_PATH", root / "data" / "factory.sqlite3")
    return root, package


def _prepare(
    factory_tools,
    *,
    thread_id: str = "thread-1",
    acceptance_criteria: list[str] | None = None,
    relevant_docs: list[str] | None = None,
    relevant_skills: list[str] | None = None,
):
    return factory_tools.prepare_agent_build_task.invoke(
        {
            "agent_id": "test-agent",
            "permitted_paths": ["staging/agents/test-agent/src/**"],
            "acceptance_criteria": acceptance_criteria or ["The staged package implements the approved capability."],
            "test_commands": ["uv run pytest staging/agents/test-agent/tests -q"],
            "relevant_docs": relevant_docs or ["docs/agent-contract.md"],
            "relevant_skills": relevant_skills or ["skills/agent-authoring/SKILL.md"],
            "token_budget": 12000,
            "time_budget_seconds": 1800,
            "stop_conditions": ["Stop when acceptance criteria or test commands cannot be satisfied."],
        },
        config={"configurable": {"thread_id": thread_id}},
    )


def test_build_task_is_strict_and_requires_positive_budgets() -> None:
    payload = {
        "agent_id": "test-agent",
        "agent_version": "1.0.0",
        "manifest_schema_version": 1,
        "manifest_sha256": "a" * 64,
        "staging_target": "staging/agents/test-agent",
        "permitted_paths": ["staging/agents/test-agent/src/**"],
        "acceptance_criteria": ["criterion"],
        "test_commands": ["uv run pytest -q"],
        "relevant_docs": ["docs/agent-contract.md"],
        "relevant_skills": ["skills/agent-authoring/SKILL.md"],
        "token_budget": 1,
        "time_budget_seconds": 1,
        "stop_conditions": ["stop"],
        "runtime_pattern": "deterministic_workflow",
        "runtime_pattern_reason": "fixed",
        "thread_id": "thread-1",
        "correlation_id": "corr-1",
    }
    assert AgentBuildTask.model_validate(payload).schema_version == 1
    with pytest.raises(ValidationError):
        AgentBuildTask.model_validate({**payload, "unknown": True})
    with pytest.raises(ValidationError):
        AgentBuildTask.model_validate({**payload, "token_budget": 0})
    with pytest.raises(ValidationError):
        AgentBuildTask.model_validate({**payload, "time_budget_seconds": -1})
    with pytest.raises(ValidationError, match="control artifact"):
        AgentBuildTask.model_validate(
            {**payload, "permitted_paths": ["staging/agents/test-agent/BUILD_TASK.json"]}
        )
    with pytest.raises(ValidationError, match="kebab-case"):
        AgentBuildTask.model_validate({**payload, "agent_id": "../test-agent"})


def test_prepare_writes_only_staged_artifact_and_records_thread(tmp_path, monkeypatch) -> None:
    root, package = _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import list_build_tasks_for_thread

    result = json.loads(_prepare(factory_tools))
    artifact = package / "BUILD_TASK.json"
    assert result["artifact_reference"] == "staging/agents/test-agent/BUILD_TASK.json"
    assert artifact.is_file()
    assert not (root / "BUILD_TASK.json").exists()
    rows = list_build_tasks_for_thread("thread-1")
    assert rows[0]["artifact_reference"] == result["artifact_reference"]
    assert rows[0]["status"] == "prepared"


@pytest.mark.parametrize("permitted", [["src/**"], ["staging/agents/other-agent/**"], ["/tmp/outside"]])
def test_prepare_rejects_out_of_scope_paths(tmp_path, monkeypatch, permitted) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    with pytest.raises((ValidationError, ValueError)):
        factory_tools.prepare_agent_build_task.invoke(
            {
                "agent_id": "test-agent",
                "permitted_paths": permitted,
                "acceptance_criteria": ["criterion"],
                "test_commands": ["uv run pytest -q"],
                "relevant_docs": ["docs/agent-contract.md"],
                "relevant_skills": ["skills/agent-authoring/SKILL.md"],
                "token_budget": 1,
                "time_budget_seconds": 1,
                "stop_conditions": ["stop"],
            },
            config={"configurable": {"thread_id": "thread-1"}},
        )


def test_runtime_pattern_change_makes_task_stale(tmp_path, monkeypatch) -> None:
    root, package = _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    prepared = json.loads(_prepare(factory_tools))
    manifest = _manifest()
    manifest["design"]["runtime_pattern"] = "simple_agent"
    (package / "agent.json").write_text(json.dumps(manifest), encoding="utf-8")
    task = AgentBuildTask.model_validate(
        json.loads((package / "BUILD_TASK.json").read_text(encoding="utf-8"))
    )
    with pytest.raises(BuildTaskError, match="stale"):
        assert_task_matches_staged_package(task, root)
    assert prepared["artifact_reference"].startswith("staging/agents/")


def test_regeneration_reuses_path_preserves_history_and_requires_new_correlation(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import (
        get_build_task,
        list_build_tasks_for_reference,
        mark_build_task_approved,
    )

    first = json.loads(_prepare(factory_tools))
    second = json.loads(
        _prepare(
            factory_tools,
            acceptance_criteria=["The changed approved capability is implemented."],
        )
    )
    assert first["artifact_reference"] == second["artifact_reference"]
    assert first["correlation_id"] != second["correlation_id"]
    history = list_build_tasks_for_reference(first["artifact_reference"])
    assert [row["status"] for row in history] == ["superseded", "prepared"]
    with pytest.raises(ValueError, match="ambiguous"):
        get_build_task(first["artifact_reference"])
    assert not mark_build_task_approved(
        thread_id="thread-1",
        artifact_reference=first["artifact_reference"],
        correlation_id=first["correlation_id"],
    )
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": second["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    result = build_factory_specialist_result("thread-1", "regenerated", interrupted=False)
    assert result.next_task is not None
    assert result.next_task.references[0] == second["artifact_reference"]


def test_stale_manifest_regeneration_preserves_old_row(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import list_build_tasks_for_reference

    first = json.loads(_prepare(factory_tools))
    package = tmp_path / "staging" / "agents" / "test-agent"
    changed = _manifest()
    changed["version"] = "2.0.0"
    (package / "agent.json").write_text(json.dumps(changed), encoding="utf-8")
    second = json.loads(_prepare(factory_tools))
    history = list_build_tasks_for_reference(first["artifact_reference"])
    assert history[0]["correlation_id"] == first["correlation_id"]
    assert history[0]["status"] in {"stale", "superseded"}
    assert history[1]["correlation_id"] == second["correlation_id"]
    assert history[1]["status"] == "prepared"


def test_other_thread_cannot_hijack_current_staged_artifact(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    prepared = json.loads(_prepare(factory_tools, thread_id="thread-1"))
    with pytest.raises(BuildTaskError, match="another Factory thread"):
        _prepare(factory_tools, thread_id="thread-2")
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": prepared["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    with pytest.raises(BuildTaskError, match="another Factory thread"):
        _prepare(factory_tools, thread_id="thread-2")


def test_local_staged_docs_and_skills_are_allowed_but_cross_agent_refs_are_not(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    result = json.loads(
        _prepare(
            factory_tools,
            relevant_docs=["staging/agents/test-agent/docs/design.md"],
            relevant_skills=["staging/agents/test-agent/skills/implementation/SKILL.md"],
        )
    )
    task = json.loads(
        (tmp_path / result["artifact_reference"]).read_text(encoding="utf-8")
    )
    assert task["relevant_docs"] == ["staging/agents/test-agent/docs/design.md"]

    with pytest.raises(ValidationError):
        AgentBuildTask.model_validate(
            {**task, "relevant_docs": ["staging/agents/other-agent/docs/design.md"]}
        )
    with pytest.raises(ValidationError):
        AgentBuildTask.model_validate(
            {**task, "relevant_skills": ["src/skills/SKILL.md"]}
        )
    with pytest.raises(ValidationError):
        AgentBuildTask.model_validate(
            {**task, "relevant_docs": ["docs/secrets/token.md"]}
        )


def test_storage_rejects_unknown_build_task_status(tmp_path) -> None:
    from agent_factory.storage import record_build_task

    with pytest.raises(ValueError, match="Unknown build-task status"):
        record_build_task(
            thread_id="thread-1",
            artifact_reference="staging/agents/test-agent/BUILD_TASK.json",
            correlation_id="corr",
            agent_id="test-agent",
            agent_version="1.0.0",
            manifest_sha256="a" * 64,
            status="unknown",
            db_path=tmp_path / "factory.sqlite3",
        )


def test_storage_migrates_unique_path_schema_without_dropping_history(tmp_path) -> None:
    from agent_factory.storage import list_build_tasks_for_reference, record_build_task

    db = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE build_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            artifact_reference TEXT NOT NULL UNIQUE,
            correlation_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_version TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decision_reason TEXT
        );
        INSERT INTO build_tasks VALUES
        (1, 'thread-1', 'staging/agents/test-agent/BUILD_TASK.json', 'old',
         'test-agent', '1.0.0', 'a', 'stale', 'now', 'now', 'old');
        """
    )
    conn.commit()
    conn.close()

    record_build_task(
        thread_id="thread-1",
        artifact_reference="staging/agents/test-agent/BUILD_TASK.json",
        correlation_id="new",
        agent_id="test-agent",
        agent_version="2.0.0",
        manifest_sha256="b" * 64,
        db_path=db,
    )
    history = list_build_tasks_for_reference(
        "staging/agents/test-agent/BUILD_TASK.json",
        db_path=db,
    )
    assert [row["correlation_id"] for row in history] == ["old", "new"]


def test_result_marks_only_mismatched_approved_row_stale(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import list_build_tasks_for_thread

    first = json.loads(_prepare(factory_tools))
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": first["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    package = tmp_path / "staging" / "agents" / "test-agent"
    changed = _manifest()
    changed["version"] = "2.0.0"
    (package / "agent.json").write_text(json.dumps(changed), encoding="utf-8")
    second = json.loads(_prepare(factory_tools))
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": second["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    result = build_factory_specialist_result("thread-1", "current", interrupted=False)
    assert result.next_task is not None
    rows = list_build_tasks_for_thread("thread-1")
    assert rows[0]["correlation_id"] == first["correlation_id"]
    assert rows[0]["status"] == "stale"
    assert rows[1]["correlation_id"] == second["correlation_id"]
    assert rows[1]["status"] == "approved"


def test_approval_is_required_before_next_task_and_approval_is_deterministic(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    prepared = json.loads(_prepare(factory_tools))
    before = build_factory_specialist_result("thread-1", "prepared", interrupted=False)
    assert before.next_task is None
    assert before.artifact_reference is None

    approved = json.loads(
        factory_tools.approve_agent_build_handoff.invoke(
            {"build_task_reference": prepared["artifact_reference"]},
            config={"configurable": {"thread_id": "thread-1"}},
        )
    )
    assert approved["status"] == "approved"
    result = build_factory_specialist_result("thread-1", "approved", interrupted=False)
    assert result.next_task is not None
    assert result.next_task.task_kind == "coding_task"
    assert result.artifact_reference == prepared["artifact_reference"]
    validate_next_task_contract(result.next_task.model_dump(exclude_none=True))
    assert set(result.next_task.model_dump()) == {"task_kind", "task", "references"}
    assert result.next_task.references[0] == prepared["artifact_reference"]
    assert result.artifact_reference == approved["artifact_reference"]


def test_rejected_task_cannot_emit_or_mutate_release_locations(tmp_path, monkeypatch) -> None:
    root, _package = _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import reject_build_tasks_for_thread

    _prepare(factory_tools)
    reject_build_tasks_for_thread("thread-1", "no")
    result = build_factory_specialist_result("thread-1", "rejected", interrupted=False)
    assert result.status == "rejected"
    assert result.next_task is None
    assert not (root / "agents").exists()
    assert not (root / "config" / "agents").exists()


def test_rejection_of_later_turn_does_not_change_approved_task(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import (
        list_build_tasks_for_thread,
        reject_build_tasks_for_thread,
    )

    prepared = json.loads(_prepare(factory_tools))
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": prepared["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    reject_build_tasks_for_thread("thread-1", "later turn rejected")
    rows = list_build_tasks_for_thread("thread-1")
    assert rows[0]["status"] == "approved"


def test_rejected_exact_correlation_cannot_be_inserted_again(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import (
        list_build_tasks_for_thread,
        reject_build_tasks_for_thread,
    )

    _prepare(factory_tools)
    reject_build_tasks_for_thread("thread-1", "rejected")
    with pytest.raises(BuildTaskError, match="exact build-task correlation is terminal"):
        _prepare(factory_tools)
    rows = list_build_tasks_for_thread("thread-1")
    assert len(rows) == 1
    assert rows[0]["status"] == "rejected"


def test_stale_exact_correlation_cannot_be_inserted_again(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools
    from agent_factory.storage import (
        list_build_tasks_for_thread,
        mark_build_task_status,
    )

    prepared = json.loads(_prepare(factory_tools))
    assert mark_build_task_status(
        prepared["artifact_reference"],
        "stale",
        "stale for test",
        correlation_id=prepared["correlation_id"],
        thread_id="thread-1",
    )
    with pytest.raises(BuildTaskError, match="exact build-task correlation is terminal"):
        _prepare(factory_tools)
    rows = list_build_tasks_for_thread("thread-1")
    assert len(rows) == 1
    assert rows[0]["correlation_id"] == prepared["correlation_id"]
    assert rows[0]["status"] == "stale"


def test_same_thread_result_preserves_approved_artifact_correlation(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    prepared = json.loads(_prepare(factory_tools))
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": prepared["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    first = build_factory_specialist_result("thread-1", "resume", interrupted=False)
    second = build_factory_specialist_result("thread-1", "resume", interrupted=False)
    assert first.artifact_reference == second.artifact_reference
    assert first.next_task.references == second.next_task.references


def test_tampered_approved_artifact_fails_closed(tmp_path, monkeypatch) -> None:
    _stage(tmp_path, monkeypatch)
    from agent_factory import factory_tools

    prepared = json.loads(_prepare(factory_tools))
    factory_tools.approve_agent_build_handoff.invoke(
        {"build_task_reference": prepared["artifact_reference"]},
        config={"configurable": {"thread_id": "thread-1"}},
    )
    artifact = tmp_path / prepared["artifact_reference"]
    task = json.loads(artifact.read_text(encoding="utf-8"))
    task["acceptance_criteria"] = ["A tampered acceptance criterion."]
    artifact.write_text(json.dumps(task), encoding="utf-8")

    with pytest.raises(BuildTaskError, match="stale|correlation"):
        build_factory_specialist_result("thread-1", "tampered", interrupted=False)
