"""Tests for factory_tools — bounded tools exposed to the Factory Brain."""

import json
import tempfile
from pathlib import Path

import pytest

from agent_factory.agent_spec import AgentPackageSpec


def _spec_json(**overrides) -> str:
    base = {
        "id": "test-agent",
        "name": "Test Agent",
        "purpose": "Primary responsibility: Perform safe test-agent work.\nSelect for: Requests that exercise the test agent.\nDo not select for: Production work or unrelated agent tasks.",
        "aliases": ["test"],
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# list_staged_agents
# ---------------------------------------------------------------------------

def test_list_staged_agents_empty(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", tmp_path / "staging" / "agents")
    result = factory_tools.list_staged_agents.invoke({})
    assert "No staged" in result


def test_list_staged_agents_with_entries(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    (staging / "alpha-agent").mkdir(parents=True)
    (staging / "beta-agent").mkdir(parents=True)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)

    result = factory_tools.list_staged_agents.invoke({})
    assert "alpha-agent" in result
    assert "beta-agent" in result


# ---------------------------------------------------------------------------
# list_known_agents
# ---------------------------------------------------------------------------

def test_list_known_agents_merges_staged_and_enabled(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    enabled = tmp_path / "config" / "agents"
    staging.mkdir(parents=True)
    enabled.mkdir(parents=True)

    manifest = {
        "id": "alpha-agent",
        "name": "Alpha Agent",
        "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
        "aliases": ["alpha"],
        "tools": [],
        "permissions": {
            "network": False,
            "filesystem": "none",
            "shell": False,
            "requires_approval": True,
        },
        "memory": {
            "scope": "none",
            "retention": "none",
        },
        "runtime": {
            "mode": "manual",
        },
        "output_contract": None,
    }
    (staging / "agent.json").write_text(json.dumps(manifest), encoding="utf-8")
    (enabled / "alpha-agent.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", tmp_path / "staging" / "agents")

    result = factory_tools.list_known_agents.invoke({})

    assert "alpha-agent" in result
    assert "staged" in result
    assert "enabled" in result
    assert "staging/agents/alpha-agent" in result
    assert "config/agents/alpha-agent.json" in result


# ---------------------------------------------------------------------------
# create_staged_agent_package (end-to-end)
# ---------------------------------------------------------------------------

def test_create_staged_agent_package_success(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    result = factory_tools.create_staged_agent_package.invoke(
        {"spec_json": _spec_json()}
    )

    assert "test-agent" in result
    assert "Files created" in result

    pkg = staging / "test-agent"
    assert (pkg / "agent.json").exists()
    assert (pkg / "SYSTEM.md").exists()
    assert (pkg / "REVIEW.md").exists()
    assert (pkg / "tools.json").exists()
    assert (pkg / "permissions.json").exists()
    assert (pkg / "memory.json").exists()
    assert (pkg / "README.md").exists()
    assert (pkg / "tests" / ".gitkeep").exists()
    manifest = json.loads((pkg / "agent.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["mode"] == "manual"
    assert manifest["output_contract"] is None
    assert manifest["manifest_schema_version"] == 1
    assert manifest["task_contract"] == {"task_kinds": []}
    assert manifest["project_context_contract"]["required"] is False
    assert manifest["project_context_contract"]["supported_schema_versions"] == [1]
    assert manifest["target_project_access"] == {
        "requires_explicit_project_root": False,
        "authorization_modes": [],
        "allows_target_creation": False,
        "creation_scope": "none",
        "fail_closed_when": [],
    }

    specialist_contract = (pkg / "specialist_contract.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT_REQUIRED = False" in specialist_contract

    from agent_factory.storage import get_staged_agent_record
    row = get_staged_agent_record("test-agent", db_path=db)
    assert row is not None
    assert row["status"] == "staged"


def test_create_staged_agent_package_renders_project_root_required(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    result = factory_tools.create_staged_agent_package.invoke(
        {
            "spec_json": _spec_json(
                project_context_contract={
                    "required": True,
                    "capabilities": ["read"],
                    "enforced_filesystem_permission": "read",
                },
                input_contract={"required_context": ["project_root"]},
            )
        }
    )

    assert "Files created" in result

    pkg = staging / "test-agent"
    specialist_contract = (pkg / "specialist_contract.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT_REQUIRED = True" in specialist_contract
    # Rendered output must be valid, importable Python — not a leftover placeholder.
    compile(specialist_contract, "specialist_contract.py", "exec")


def test_create_staged_agent_package_writes_extensions_verbatim(tmp_path, monkeypatch):
    """Specialist-owned metadata Factory has no defined meaning for (e.g. a
    backlog pointer) is written through unchanged — Factory neither validates
    nor interprets its contents beyond rejecting core-field collisions."""
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    result = factory_tools.create_staged_agent_package.invoke(
        {
            "spec_json": _spec_json(
                extensions={"backlog_sheet_id": "some-sheet-id"},
            )
        }
    )

    assert "test-agent" in result
    manifest = json.loads(
        (staging / "test-agent" / "agent.json").read_text(encoding="utf-8")
    )
    assert manifest["backlog_sheet_id"] == "some-sheet-id"


def test_create_staged_agent_package_writes_task_and_target_contracts(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    result = factory_tools.create_staged_agent_package.invoke(
        {
            "spec_json": _spec_json(
                input_contract={"accepted_context": ["project_root"]},
                task_contract={
                    "task_kinds": ["coding_task", "project_creation"],
                    "default_task_kind": "coding_task",
                },
                target_project_access={
                    "requires_explicit_project_root": True,
                    "authorization_modes": ["registered_target"],
                    "registry_source": "settings.project_registry",
                    "allows_target_creation": True,
                    "creation_scope": "registered_parent",
                    "fail_closed_when": [
                        "platform_unavailable",
                        "credentials_unavailable",
                        "location_unavailable",
                    ],
                },
            )
        }
    )

    assert "test-agent" in result
    manifest = json.loads(
        (staging / "test-agent" / "agent.json").read_text(encoding="utf-8")
    )
    assert manifest["task_contract"]["task_kinds"] == ["coding_task", "project_creation"]
    assert manifest["target_project_access"]["creation_scope"] == "registered_parent"


def test_create_staged_agent_package_invalid_json(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", tmp_path / "staging")

    result = factory_tools.create_staged_agent_package.invoke(
        {"spec_json": "not json at all"}
    )
    assert "Invalid JSON" in result


def test_create_staged_agent_package_invalid_spec(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", tmp_path / "staging")

    result = factory_tools.create_staged_agent_package.invoke(
        {"spec_json": json.dumps({"id": "BAD-ID", "name": "x", "purpose": "x", "aliases": ["x"]})}
    )
    assert "Invalid agent spec" in result


def test_create_staged_agent_package_risky_permissions_flagged(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    spec = _spec_json(
        id="risky-agent",
        aliases=["risky"],
        permissions={"network": True, "filesystem": "none", "shell": False, "requires_approval": True},
    )
    result = factory_tools.create_staged_agent_package.invoke({"spec_json": spec})

    assert "network" in result
    review = (staging / "risky-agent" / "REVIEW.md").read_text()
    assert "network" in review


def test_create_staged_agent_package_duplicate_fails(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    first = factory_tools.create_staged_agent_package.invoke({"spec_json": _spec_json()})
    result = factory_tools.create_staged_agent_package.invoke({"spec_json": _spec_json()})

    assert "test-agent" in first
    assert "already exists" in result
    assert "No duplicate package was created" in result


def test_create_staged_agent_package_requires_subprocess_output_contract(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", tmp_path / "staging")

    result = factory_tools.create_staged_agent_package.invoke(
        {
            "spec_json": _spec_json(
                runtime={
                    "mode": "subprocess",
                    "entrypoint": "uv run test-agent run-agent-task",
                    "working_directory": "/tmp/test-agent",
                    "input_arg": "--input-json",
                    "output_arg": "--output-json",
                    "default_execution_mode": "execute",
                }
            )
        }
    )

    assert "output_contract" in result


def test_create_staged_agent_package_writes_subprocess_output_contract(tmp_path, monkeypatch):
    from agent_factory import factory_tools

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "test.sqlite3"

    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)

    import agent_factory.storage as storage_mod

    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", db)

    spec = _spec_json(
        id="subprocess-agent",
        aliases=["subprocess"],
        runtime={
            "mode": "subprocess",
            "entrypoint": "uv run subprocess-agent run-agent-task",
            "working_directory": "/tmp/subprocess-agent",
            "input_arg": "--input-json",
            "output_arg": "--output-json",
            "default_execution_mode": "execute",
        },
        output_contract={
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
        },
    )
    result = factory_tools.create_staged_agent_package.invoke({"spec_json": spec})

    assert "subprocess-agent" in result
    manifest = json.loads((staging / "subprocess-agent" / "agent.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["mode"] == "subprocess"
    assert manifest["input_contract"]["protocol"] == "agent-hub.task"
    assert manifest["input_contract"]["protocol_version"] == 1
    assert manifest["interaction_contract"]["clarification"] is True
    assert (staging / "subprocess-agent" / "specialist_contract.py").is_file()
    assert manifest["output_contract"]["status_values"] == [
        "success",
        "needs_clarification",
        "waiting_decision",
        "failed",
    ]
