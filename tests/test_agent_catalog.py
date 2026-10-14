"""Tests for the shared agent catalog and reuse helpers."""

import json

import pytest

from agent_factory.agent_catalog import (
    AgentCatalogConflictError,
    build_agent_catalog,
    plan_package_reuse,
    promote_agent,
    preview_agent_promotion,
    preview_agent_rollback,
    rollback_agent,
)
from agent_factory.agent_spec import AgentPackageSpec


def _manifest() -> dict:
    return {
        "id": "alpha-agent",
        "version": "1.0.0",
        "manifest_schema_version": 1,
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
        "task_contract": {
            "task_kinds": [],
        },
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


def _spec() -> AgentPackageSpec:
    return AgentPackageSpec.model_validate(
        {
            "id": "alpha-agent",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
        }
    )


def _approve_promotion(agent_id: str, root, db_path=None):
    preview = preview_agent_promotion(agent_id, project_root=root, db_path=db_path)
    return promote_agent(
        agent_id,
        expected_staged_sha256=preview.staged_sha256,
        expected_active_sha256=preview.active_sha256,
        project_root=root,
        db_path=db_path,
    )


def test_build_agent_catalog_accepts_configured_tools_by_default(tmp_path, monkeypatch):
    """A real enabled agent (e.g. ai-tech-lead) declares tools it's actually
    configured to use. build_agent_catalog must check those against the real
    config/tools.json allowlist, not silently treat the allowlist as empty —
    which would reject every enabled agent with any declared tool at all, as
    happened live when list_known_agents/request_agent_promotion inspected
    the inventory."""
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    manifest = _manifest()
    manifest["tools"] = ["run_agent_task"]
    (enabled / "alpha-agent.json").write_text(json.dumps(manifest), encoding="utf-8")

    tools_file = tmp_path / "tools.json"
    tools_file.write_text(json.dumps({"tools": ["run_agent_task"]}), encoding="utf-8")

    import agent_factory.cli as cli_module

    monkeypatch.setattr(cli_module, "DEFAULT_TOOLS_FILE", tools_file)
    catalog = build_agent_catalog(enabled_dir=enabled, staging_dir=tmp_path / "staging")

    assert list(catalog["alpha-agent"].manifest.tools) == ["run_agent_task"]


def test_build_agent_catalog_rejects_tool_outside_configured_allowlist(tmp_path):
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    manifest = _manifest()
    manifest["tools"] = ["not_a_real_tool"]
    (enabled / "alpha-agent.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(Exception, match="unknown tools: not_a_real_tool"):
        build_agent_catalog(
            enabled_dir=enabled,
            staging_dir=tmp_path / "staging",
            allowed_tool_ids=["run_agent_task"],
        )


def test_build_agent_catalog_merges_staged_and_enabled(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    enabled = tmp_path / "config" / "agents"
    staging.mkdir(parents=True)
    enabled.mkdir(parents=True)

    payload = json.dumps(_manifest())
    (staging / "agent.json").write_text(payload, encoding="utf-8")
    enabled_manifest = enabled / "alpha-agent" / "agent.json"
    enabled_manifest.parent.mkdir()
    enabled_manifest.write_text(payload, encoding="utf-8")

    catalog = build_agent_catalog(enabled_dir=enabled, staging_dir=tmp_path / "staging")
    entry = catalog["alpha-agent"]

    assert entry.id == "alpha-agent"
    assert entry.manifest.design is None  # legacy manifests remain readable
    assert set(entry.statuses) == {"staged", "enabled"}
    assert any(location.endswith("staging/agents/alpha-agent") for location in entry.locations)
    assert any(location.endswith("config/agents/alpha-agent/agent.json") for location in entry.locations)


def test_build_agent_catalog_ignores_promoted_staging_snapshot_when_enabled_manifest_evolves(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    enabled = tmp_path / "config" / "agents"
    staging.mkdir(parents=True)
    enabled.mkdir(parents=True)

    old_manifest = _manifest()
    new_manifest = _manifest()
    new_manifest["purpose"] = (
        "Primary responsibility: Perform evolved alpha work.\n"
        "Select for: Requests that require the evolved alpha workflow.\n"
        "Do not select for: Requests unrelated to evolved alpha work."
    )
    (staging / "agent.json").write_text(json.dumps(old_manifest), encoding="utf-8")
    (enabled / "alpha-agent.json").write_text(json.dumps(new_manifest), encoding="utf-8")

    from agent_factory.storage import record_staged_agent, update_staged_agent_status

    db_path = tmp_path / "factory.sqlite3"
    record_staged_agent("alpha-agent", staging, db_path=db_path)
    update_staged_agent_status("alpha-agent", "enabled", db_path=db_path)

    catalog = build_agent_catalog(
        enabled_dir=enabled,
        staging_dir=tmp_path / "staging",
        db_path=db_path,
    )

    entry = catalog["alpha-agent"]
    assert entry.manifest.purpose == new_manifest["purpose"]
    assert entry.statuses == ("enabled",)
    assert all("staging/agents/alpha-agent" not in location for location in entry.locations)


def test_plan_package_reuse_reuses_existing_enabled_agent(tmp_path):
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    (enabled / "alpha-agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")

    decision = plan_package_reuse(_spec(), enabled_dir=enabled, staging_dir=tmp_path / "staging")

    assert decision.action == "reuse"
    assert decision.entry is not None
    assert decision.entry.id == "alpha-agent"


def test_plan_package_reuse_rejects_explicit_design_against_legacy_manifest(tmp_path):
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    (enabled / "alpha-agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    spec = AgentPackageSpec.model_validate(
        {
            **_spec().model_dump(),
            "design": {
                "runtime_pattern": "simple_agent",
                "runtime_pattern_reason": "The bounded capability choice is sufficient.",
            },
        }
    )

    with pytest.raises(AgentCatalogConflictError, match="active released package is missing"):
        plan_package_reuse(spec, enabled_dir=enabled, staging_dir=tmp_path / "staging")


def test_plan_package_reuse_allows_only_newer_version_for_enabled_agent(tmp_path):
    enabled = tmp_path / "config" / "agents" / "alpha-agent"
    released = tmp_path / "agents" / "alpha-agent"
    enabled.mkdir(parents=True)
    released.mkdir(parents=True)
    payload = json.dumps(_manifest())
    (enabled / "agent.json").write_text(payload, encoding="utf-8")
    (released / "agent.json").write_text(payload, encoding="utf-8")
    spec = AgentPackageSpec.model_validate({**_spec().model_dump(), "version": "1.1.0"})

    decision = plan_package_reuse(
        spec,
        enabled_dir=enabled.parent,
        staging_dir=tmp_path / "staging" / "agents",
    )

    assert decision.action == "upgrade"
    assert decision.entry is not None
    assert decision.entry.manifest.version == "1.0.0"


def test_promotion_rejects_a_version_that_is_not_newer(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    released = tmp_path / "agents" / "alpha-agent"
    enabled = tmp_path / "config" / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    released.mkdir(parents=True)
    enabled.mkdir(parents=True)
    payload = json.dumps(_manifest())
    (staging / "agent.json").write_text(payload, encoding="utf-8")
    (released / "agent.json").write_text(payload, encoding="utf-8")
    (enabled / "agent.json").write_text(payload, encoding="utf-8")

    with pytest.raises(AgentCatalogConflictError, match="must be newer"):
        preview_agent_promotion("alpha-agent", project_root=tmp_path)


def test_promote_agent_releases_full_package_and_registry_comes_from_release(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    (staging / "agent.json").write_text(json.dumps(_manifest(), indent=2), encoding="utf-8")
    (staging / "README.md").write_text("released package", encoding="utf-8")
    (staging / "docs").mkdir()
    (staging / "docs" / "INDEX.md").write_text("# Docs", encoding="utf-8")

    _approve_promotion("alpha-agent", tmp_path, db_path=tmp_path / "factory.sqlite3")

    released = tmp_path / "agents" / "alpha-agent"
    registry = tmp_path / "config" / "agents" / "alpha-agent" / "agent.json"
    assert (released / "README.md").read_text(encoding="utf-8") == "released package"
    assert registry.read_text(encoding="utf-8") == (released / "agent.json").read_text(encoding="utf-8")

    # A retained staged snapshot is not authoritative after promotion.
    (staging / "agent.json").write_text(
        json.dumps({**_manifest(), "purpose": "Primary responsibility: Changed.\nSelect for: Changed.\nDo not select for: Changed."}),
        encoding="utf-8",
    )
    catalog = build_agent_catalog(
        enabled_dir=tmp_path / "config" / "agents",
        staging_dir=tmp_path / "staging" / "agents",
        released_dir=tmp_path / "agents",
        db_path=tmp_path / "factory.sqlite3",
    )
    assert catalog["alpha-agent"].manifest.purpose == _manifest()["purpose"]
    assert all("staging/agents/alpha-agent" not in location for location in catalog["alpha-agent"].locations)


def test_first_promotion_preserves_staged_version_and_enables_registry(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    (staging / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    (staging / "README.md").write_text("first approved release", encoding="utf-8")

    _approve_promotion("alpha-agent", tmp_path)

    released = tmp_path / "agents" / "alpha-agent"
    registry = tmp_path / "config" / "agents" / "alpha-agent" / "agent.json"
    assert json.loads((released / "agent.json").read_text())["version"] == "1.0.0"
    assert json.loads(registry.read_text())["version"] == "1.0.0"
    assert (released / "README.md").read_text() == "first approved release"


def test_update_shows_diff_pins_approval_and_keeps_one_previous_release(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    (staging / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    (staging / "README.md").write_text("version one", encoding="utf-8")
    _approve_promotion("alpha-agent", tmp_path)

    manifest = {**_manifest(), "version": "1.1.0", "purpose": "Primary responsibility: Perform improved alpha work.\nSelect for: Requests that require the improved alpha workflow.\nDo not select for: Requests unrelated to alpha work."}
    (staging / "agent.json").write_text(json.dumps(manifest), encoding="utf-8")
    (staging / "README.md").write_text("version two", encoding="utf-8")
    preview = preview_agent_promotion("alpha-agent", project_root=tmp_path)
    assert preview.active_version == "1.0.0"
    assert preview.staged_version == "1.1.0"
    assert "enabled/README.md" in preview.diff
    assert "version one" in preview.diff and "version two" in preview.diff

    with pytest.raises(AgentCatalogConflictError, match="changed after approval"):
        promote_agent(
            "alpha-agent",
            expected_staged_sha256="stale-approval",
            expected_active_sha256=preview.active_sha256,
            project_root=tmp_path,
        )
    assert json.loads((tmp_path / "config/agents/alpha-agent/agent.json").read_text())["version"] == "1.0.0"

    promote_agent(
        "alpha-agent",
        expected_staged_sha256=preview.staged_sha256,
        expected_active_sha256=preview.active_sha256,
        project_root=tmp_path,
    )
    assert json.loads((tmp_path / "config/agents/alpha-agent/agent.json").read_text())["version"] == "1.1.0"
    assert json.loads((tmp_path / "agents/.previous/alpha-agent/agent.json").read_text())["version"] == "1.0.0"
    assert (tmp_path / "agents/alpha-agent/README.md").read_text() == "version two"


def test_rollback_reactivates_previous_version_and_retains_displaced_release(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    (staging / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    (staging / "README.md").write_text("version one", encoding="utf-8")
    _approve_promotion("alpha-agent", tmp_path)
    (staging / "agent.json").write_text(json.dumps({**_manifest(), "version": "1.1.0"}), encoding="utf-8")
    (staging / "README.md").write_text("version two", encoding="utf-8")
    _approve_promotion("alpha-agent", tmp_path)

    preview = preview_agent_rollback("alpha-agent", project_root=tmp_path)
    assert preview["active_version"] == "1.1.0"
    assert preview["previous_version"] == "1.0.0"
    result = rollback_agent(
        "alpha-agent",
        expected_active_sha256=preview["active_sha256"],
        expected_previous_sha256=preview["previous_sha256"],
        project_root=tmp_path,
    )

    assert "rolled back from 1.1.0 to 1.0.0" in result
    assert json.loads((tmp_path / "config/agents/alpha-agent/agent.json").read_text())["version"] == "1.0.0"
    assert (tmp_path / "agents/alpha-agent/README.md").read_text() == "version one"
    assert json.loads((tmp_path / "agents/.previous/alpha-agent/agent.json").read_text())["version"] == "1.1.0"


def test_promote_agent_fails_when_released_package_conflicts(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    released = tmp_path / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    released.mkdir(parents=True)
    (staging / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    (released / "agent.json").write_text(
        json.dumps({**_manifest(), "name": "Different Agent"}), encoding="utf-8"
    )

    with pytest.raises(AgentCatalogConflictError, match="disagree"):
        preview_agent_promotion("alpha-agent", project_root=tmp_path, db_path=tmp_path / "factory.sqlite3")

    assert not (tmp_path / "config" / "agents" / "alpha-agent" / "agent.json").exists()


def test_promotion_rejects_incompatible_manifest_schema(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    staging.mkdir(parents=True)
    (staging / "agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    _approve_promotion("alpha-agent", tmp_path)

    incompatible = {**_manifest(), "version": "1.1.0", "manifest_schema_version": 2}
    (staging / "agent.json").write_text(json.dumps(incompatible), encoding="utf-8")
    with pytest.raises(AgentCatalogConflictError, match="incompatible schema version"):
        preview_agent_promotion("alpha-agent", project_root=tmp_path)

    registry = tmp_path / "config" / "agents" / "alpha-agent" / "agent.json"
    assert json.loads(registry.read_text(encoding="utf-8"))["version"] == "1.0.0"


def test_plan_package_reuse_detects_runtime_contract_mismatch(tmp_path):
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    manifest = _manifest()
    manifest["runtime"] = {
        "mode": "subprocess",
        "entrypoint": "uv run alpha run-agent-task",
        "working_directory": "/tmp/alpha",
        "input_arg": "--input-json",
        "output_arg": "--output-json",
        "default_execution_mode": "execute",
    }
    manifest["output_contract"] = {
        "status_values": [
            "success",
            "needs_clarification",
            "waiting_decision",
            "failed",
        ],
        "status_contract": {
            "success": {"terminal": True, "caller_action": "consume_result"},
            "needs_clarification": {"terminal": False, "caller_action": "provide_clarification"},
            "waiting_decision": {"terminal": False, "caller_action": "provide_decision"},
            "failed": {"terminal": True, "caller_action": "inspect_failure"},
        },
    }
    (enabled / "alpha-agent.json").write_text(json.dumps(manifest), encoding="utf-8")

    spec = AgentPackageSpec.model_validate(
        {
            "id": "alpha-agent",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
            "runtime": {
                "mode": "subprocess",
                "entrypoint": "uv run alpha run-agent-task",
                "working_directory": "/tmp/alpha",
                "input_arg": "--input-json",
                "output_arg": "--output-json",
                "default_execution_mode": "instruction_only",
            },
            "output_contract": manifest["output_contract"],
        }
    )

    with pytest.raises(AgentCatalogConflictError):
        plan_package_reuse(spec, enabled_dir=enabled, staging_dir=tmp_path / "staging")


def test_plan_package_reuse_detects_target_project_access_mismatch(tmp_path):
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    manifest = _manifest()
    manifest["input_contract"] = {
        "accepted_context": ["project_root"],
        "required_context": [],
    }
    manifest["task_contract"] = {
        "task_kinds": ["coding_task"],
        "default_task_kind": "coding_task",
    }
    manifest["target_project_access"] = {
        "requires_explicit_project_root": True,
        "authorization_modes": ["registered_target"],
        "registry_source": "settings.project_registry",
        "allows_target_creation": False,
        "creation_scope": "none",
        "fail_closed_when": ["location_unavailable"],
    }
    (enabled / "alpha-agent.json").write_text(json.dumps(manifest), encoding="utf-8")

    spec = AgentPackageSpec.model_validate(
        {
            "id": "alpha-agent",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
            "input_contract": {"accepted_context": ["project_root"]},
            "task_contract": {
                "task_kinds": ["coding_task"],
                "default_task_kind": "coding_task",
            },
            "target_project_access": {
                "requires_explicit_project_root": True,
                "authorization_modes": ["registered_target", "unregistered_with_approval"],
                "registry_source": "settings.project_registry",
                "allows_target_creation": False,
                "creation_scope": "none",
                "fail_closed_when": ["location_unavailable"],
            },
        }
    )

    with pytest.raises(AgentCatalogConflictError):
        plan_package_reuse(spec, enabled_dir=enabled, staging_dir=tmp_path / "staging")
