from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agent_factory.agent_catalog import AgentCatalogConflictError, promote_agent
from agent_factory.build_result import (
    BuildResultConsumptionError,
    BuildResultValidationError,
    consume_agent_build_result,
)
from agent_factory.build_task import (
    AgentBuildTask,
    build_task_correlation_id,
    build_task_reference,
    load_staged_manifest,
)
from agent_factory.storage import (
    get_build_task,
    list_build_tasks_for_agent_manifest,
    list_build_tasks_for_reference,
    record_build_task,
)


def _manifest() -> dict:
    return {
        "id": "test-agent",
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


def _setup(tmp_path: Path, *, status: str = "approved") -> tuple[Path, Path, AgentBuildTask, Path]:
    root = tmp_path
    package = root / "staging" / "agents" / "test-agent"
    package.mkdir(parents=True)
    (package / "src").mkdir()
    (package / "src" / "app.py").write_text("pass\n", encoding="utf-8")
    (package / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    _raw, _parsed, digest = load_staged_manifest(package, "test-agent")
    controls = {
        "agent_id": "test-agent",
        "permitted_paths": ["staging/agents/test-agent/src/**"],
        "acceptance_criteria": ["The staged package implements the approved capability."],
        "test_commands": ["uv run pytest tests -q"],
        "relevant_docs": ["docs/agent-contract.md"],
        "relevant_skills": ["skills/agent-authoring/SKILL.md"],
        "token_budget": 120,
        "time_budget_seconds": 180,
        "stop_conditions": ["Stop when evidence is unavailable."],
    }
    task = AgentBuildTask.model_validate(
        {
            **controls,
            "agent_version": "1.0.0",
            "manifest_schema_version": 1,
            "manifest_sha256": digest,
            "staging_target": "staging/agents/test-agent",
            "runtime_pattern": "deterministic_workflow",
            "runtime_pattern_reason": _manifest()["design"]["runtime_pattern_reason"],
            "thread_id": "factory-thread-1",
            "correlation_id": build_task_correlation_id(
                AgentBuildTask.model_construct(
                    schema_version=1,
                    **controls,
                    agent_version="1.0.0",
                    manifest_schema_version=1,
                    manifest_sha256=digest,
                    staging_target="staging/agents/test-agent",
                    runtime_pattern="deterministic_workflow",
                    runtime_pattern_reason=_manifest()["design"]["runtime_pattern_reason"],
                    thread_id="factory-thread-1",
                    correlation_id="placeholder",
                )
            ),
        }
    )
    # The correlation helper excludes only the correlation itself, so the
    # model above is the same canonical task body Factory prepared.
    task_path = package / "BUILD_TASK.json"
    task_path.write_text(task.model_dump_json(indent=2) + "\n", encoding="utf-8")
    db = root / "factory.sqlite3"
    record_build_task(
        thread_id=task.thread_id,
        artifact_reference=build_task_reference(task),
        correlation_id=task.correlation_id,
        agent_id=task.agent_id,
        agent_version=task.agent_version,
        manifest_sha256=task.manifest_sha256,
        status=status,
        db_path=db,
    )
    return root, package, task, db


def _git_lifecycle() -> dict:
    return {
        "enabled": True,
        "preflight_status": "task_worktree",
        "preflight_branch": "atl/task",
        "preflight_head": "base",
        "preflight_dirty_paths": [],
        "preflight_reason": "Worktree is ready.",
        "task_canonical_root": "/repo",
        "task_worktree": "/tmp/task",
        "task_branch": "atl/task",
        "task_base_sha": "base",
        "task_tip_sha": "tip",
        "task_commit_sha": "commit",
        "branch_pushed": True,
        "main_status": "MAIN STATUS: NOT IN MAIN — pushed branch atl/task",
        "main_sha": "",
        "integration_status": "not_requested",
        "integration_reason": "Factory promotion remains separate.",
    }


def _result(task: AgentBuildTask, **overrides: object) -> dict:
    result = {
        "schema_version": 1,
        "status": "success",
        "changed_files": [f"{task.staging_target}/src/app.py"],
        "tests_run": [
            {"command": task.test_commands[0], "status": "passed", "output": "1 passed"}
        ],
        "validation_evidence": {
            "diff_summary": "src/app.py | 1 +",
            "validation_command": task.test_commands[0],
            "validation_passed": True,
            "validation_output_tail": "1 passed",
            "out_of_scope_paths": [],
            "verification_status": "complete",
            "verification_reason": "Acceptance criteria satisfied.",
            "independent_review": None,
            "git_lifecycle": _git_lifecycle(),
        },
        "token_usage": {
            "scope": "ai_tech_lead_orchestrator",
            "availability": "available",
            "calls": 3,
            "tokens_in": 70,
            "tokens_out": 30,
            "tokens_total": 100,
            "backend_usage": {
                "availability": "available",
                "scope": "coding_agent_backend",
                "tokens": 20,
                "reason": "Measured provider usage in the approved-budget ledger.",
            },
        },
        "estimated_cost_usd": None,
        "estimated_cost_scope": "ai_tech_lead_orchestrator",
        "estimated_cost_source": "No provider cost was supplied.",
        "errors": [],
        "stop_reason": "validated_task_branch_not_in_main",
        "duration_seconds": 12.5,
    }
    for key, value in overrides.items():
        result[key] = value
    return result


def _consume(root: Path, task: AgentBuildTask, db: Path, result: dict) -> dict:
    return consume_agent_build_result(
        task.thread_id,
        build_task_reference(task),
        result,
        project_root=root,
        db_path=db,
    )


def test_successful_exact_result_persists_and_validates(tmp_path: Path) -> None:
    root, package, task, db = _setup(tmp_path)

    result = _consume(root, task, db, _result(task))

    assert result["status"] == "validated"
    assert result["correlation_id"] == task.correlation_id
    persisted = json.loads((package / "BUILD_RESULT.json").read_text(encoding="utf-8"))
    assert persisted["build_result"]["status"] == "success"
    assert get_build_task(
        build_task_reference(task),
        thread_id=task.thread_id,
        correlation_id=task.correlation_id,
        db_path=db,
    )["status"] == "validated"


def test_identical_result_is_idempotent_and_different_result_rejected(tmp_path: Path) -> None:
    root, _package, task, db = _setup(tmp_path)
    exact = _result(task)
    first = _consume(root, task, db, exact)
    second = _consume(root, task, db, json.loads(json.dumps(exact)))
    assert first == second
    with pytest.raises(BuildResultConsumptionError, match="different BuildResult"):
        _consume(root, task, db, {**exact, "stop_reason": "different"})


@pytest.mark.parametrize(
    "override",
    [
        {"status": "failed", "errors": ["coding failed"]},
        {"status": "stopped", "errors": ["stopped"]},
        {"errors": ["unexpected error"]},
    ],
)
def test_non_success_or_error_result_is_failed_and_non_promotable(tmp_path: Path, override: dict) -> None:
    root, _package, task, db = _setup(tmp_path)
    payload = _result(task, **override)
    with pytest.raises(BuildResultConsumptionError):
        _consume(root, task, db, payload)
    row = get_build_task(
        build_task_reference(task), thread_id=task.thread_id, correlation_id=task.correlation_id, db_path=db
    )
    assert row["status"] == "failed"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda result, task: result["tests_run"].__setitem__(0, {"command": task.test_commands[0], "status": "failed", "output": "fail"}),
        lambda result, task: result["tests_run"].__setitem__(0, {"command": "other", "status": "passed", "output": "ok"}),
        lambda result, task: result["validation_evidence"].__setitem__("validation_passed", False),
    ],
)
def test_missing_or_failed_required_validation_fails_closed(tmp_path: Path, mutate) -> None:
    root, _package, task, db = _setup(tmp_path)
    payload = _result(task)
    mutate(payload, task)
    with pytest.raises(BuildResultConsumptionError):
        _consume(root, task, db, payload)
    assert list_build_tasks_for_reference(build_task_reference(task), db_path=db)[0]["status"] == "failed"


@pytest.mark.parametrize(
    "path",
    [
        "staging/agents/other-agent/src/app.py",
        "staging/agents/test-agent/src/../secret.py",
        "staging/agents/test-agent/BUILD_TASK.json",
        "staging/agents/test-agent/BUILD_RESULT.json",
        "/tmp/app.py",
        "staging\\agents\\test-agent\\src\\app.py",
    ],
)
def test_changed_paths_are_exactly_scoped_and_safe(tmp_path: Path, path: str) -> None:
    root, _package, task, db = _setup(tmp_path)
    with pytest.raises(BuildResultConsumptionError):
        _consume(root, task, db, _result(task, changed_files=[path]))
    assert list_build_tasks_for_reference(build_task_reference(task), db_path=db)[0]["status"] == "failed"


def test_budget_and_duration_are_enforced_without_fabricating_backend_usage(tmp_path: Path) -> None:
    root, package, task, db = _setup(tmp_path)
    too_many_tokens = _result(task)
    too_many_tokens["token_usage"] = {**too_many_tokens["token_usage"], "tokens_total": 121, "tokens_out": 51}
    with pytest.raises(BuildResultConsumptionError, match="token usage"):
        _consume(root, task, db, too_many_tokens)
    assert not (package / "BUILD_RESULT.json").exists()

    root, package, task, db = _setup(tmp_path / "duration")
    too_long = _result(task, duration_seconds=180.1)
    with pytest.raises(BuildResultConsumptionError, match="duration"):
        _consume(root, task, db, too_long)
    assert not (package / "BUILD_RESULT.json").exists()

    root, _package, task, db = _setup(tmp_path / "backend")
    result = _result(task)
    result["token_usage"]["backend_usage"].update(availability="unavailable", tokens=None)
    with pytest.raises(BuildResultConsumptionError, match="measured coding-backend"):
        _consume(root, task, db, result)


def test_combined_usage_and_exact_budget_boundary(tmp_path: Path) -> None:
    root, _package, task, db = _setup(tmp_path / "combined")
    result = _result(task)
    result["token_usage"]["backend_usage"]["tokens"] = 21
    with pytest.raises(BuildResultConsumptionError, match="whole-job token usage"):
        _consume(root, task, db, result)
    root, _package, task, db = _setup(tmp_path / "boundary")
    assert _consume(root, task, db, _result(task))["status"] == "validated"


def test_wrong_thread_reference_and_stale_manifest_do_not_validate(tmp_path: Path) -> None:
    root, package, task, db = _setup(tmp_path)
    with pytest.raises(BuildResultConsumptionError):
        consume_agent_build_result("other-thread", build_task_reference(task), _result(task), project_root=root, db_path=db)
    with pytest.raises(BuildResultConsumptionError):
        consume_agent_build_result(task.thread_id, "staging/agents/test-agent/../BUILD_TASK.json", _result(task), project_root=root, db_path=db)
    changed = _manifest()
    changed["version"] = "2.0.0"
    (package / "agent.json").write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(BuildResultConsumptionError):
        _consume(root, task, db, _result(task))
    assert list_build_tasks_for_reference(build_task_reference(task), db_path=db)[0]["status"] == "failed"


def test_strict_wire_schema_rejects_extra_fields_and_unbounded_values(tmp_path: Path) -> None:
    root, _package, task, db = _setup(tmp_path)
    extra = _result(task)
    extra["unexpected"] = True
    with pytest.raises(BuildResultValidationError):
        _consume(root, task, db, extra)
    root, _package, task, db = _setup(tmp_path / "long")
    long_value = _result(task)
    long_value["estimated_cost_source"] = "x" * 2_001
    with pytest.raises(BuildResultValidationError):
        _consume(root, task, db, long_value)


def test_promotion_requires_latest_current_task_validated_and_excludes_controls(tmp_path: Path) -> None:
    root, package, task, db = _setup(tmp_path)
    (package / "BUILD_RESULT.json").write_text("not runtime\n", encoding="utf-8")
    with pytest.raises(AgentCatalogConflictError, match="not validated"):
        promote_agent("test-agent", project_root=root, db_path=db)
    _consume(root, task, db, _result(task))
    message = promote_agent("test-agent", project_root=root, db_path=db)
    assert "released at agents/test-agent/" in message
    assert not (root / "agents" / "test-agent" / "BUILD_TASK.json").exists()
    assert not (root / "agents" / "test-agent" / "BUILD_RESULT.json").exists()
    assert (root / "agents" / "test-agent" / "src" / "app.py").exists()


@pytest.mark.parametrize("new_status", ["prepared", "approved", "failed"])
def test_newer_non_validated_task_blocks_old_validated_result(tmp_path: Path, new_status: str) -> None:
    root, package, task, db = _setup(tmp_path)
    _consume(root, task, db, _result(task))
    changed_task = task.model_copy(
        update={
            "acceptance_criteria": ["A newer implementation attempt."],
            "correlation_id": "placeholder",
        }
    )
    changed_task = changed_task.model_copy(update={"correlation_id": build_task_correlation_id(changed_task)})
    (package / "BUILD_TASK.json").write_text(changed_task.model_dump_json(indent=2) + "\n", encoding="utf-8")
    record_build_task(
        thread_id=changed_task.thread_id,
        artifact_reference=build_task_reference(changed_task),
        correlation_id=changed_task.correlation_id,
        agent_id=changed_task.agent_id,
        agent_version=changed_task.agent_version,
        manifest_sha256=changed_task.manifest_sha256,
        status=new_status,
        db_path=db,
    )
    with pytest.raises(AgentCatalogConflictError, match="not validated"):
        promote_agent("test-agent", project_root=root, db_path=db)


def test_package_with_no_build_task_remains_promotable(tmp_path: Path) -> None:
    root = tmp_path
    package = root / "staging" / "agents" / "test-agent"
    package.mkdir(parents=True)
    (package / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    assert "released at agents/test-agent/" in promote_agent(
        "test-agent", project_root=root, db_path=root / "factory.sqlite3"
    )


def test_current_schema_migration_preserves_all_previous_status_rows(tmp_path: Path) -> None:
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
            status TEXT NOT NULL CHECK (status IN ('prepared', 'approved', 'rejected', 'stale', 'superseded')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decision_reason TEXT
        );
        """
    )
    statuses = ["prepared", "approved", "rejected", "stale", "superseded"]
    for index, status in enumerate(statuses, start=1):
        conn.execute(
            "INSERT INTO build_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (index, "thread", f"staging/agents/a-{index}/BUILD_TASK.json", f"corr-{index}", "test-agent", "1.0.0", "a" * 64, status, "now", "now", status),
        )
    conn.commit()
    conn.close()

    rows = list_build_tasks_for_agent_manifest("test-agent", "a" * 64, db_path=db)
    assert [row["status"] for row in rows] == statuses
    record_build_task(
        thread_id="thread",
        artifact_reference="staging/agents/test-agent/BUILD_TASK.json",
        correlation_id="new",
        agent_id="test-agent",
        agent_version="1.0.0",
        manifest_sha256="a" * 64,
        status="validated",
        db_path=db,
    )
    assert list_build_tasks_for_agent_manifest("test-agent", "a" * 64, db_path=db)[-1]["status"] == "validated"
