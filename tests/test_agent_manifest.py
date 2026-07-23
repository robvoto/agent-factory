from __future__ import annotations

import json

import agent_factory.cli as cli_module
from agent_factory.agent_manifest import MANIFEST_COMMAND, build_factory_manifest, render_factory_manifest


def test_build_factory_manifest_contains_core_fields() -> None:
    manifest = build_factory_manifest(include_live=False)

    assert manifest["manifest_schema_version"] == 2
    assert manifest["agent_id"] == "agent-factory"
    assert manifest["agent_name"] == "Agent Factory"
    assert manifest["entrypoints"]["manifest"] == "manifest"
    assert manifest["entrypoints"]["cli"] == "agent-factory"
    assert manifest["entrypoints"]["setup"] == "setup"
    assert manifest["entrypoints"]["doctor"] == "doctor"
    assert manifest["purpose"] == (
        "Primary responsibility: Design and govern new specialist agent packages.\n"
        "Select for: Creating, configuring, validating, staging, approving, rejecting, or "
        "promoting a specialist agent package as the requested deliverable.\n"
        "Do not select for: Implementing backlog items, fixing bugs, changing documentation, "
        "or modifying source code in the existing Agent Factory repository or any other "
        "existing software project."
    )
    assert "one_line" not in manifest
    assert "capabilities" not in manifest
    assert "boundaries" not in manifest
    assert manifest["registry"]["enabled_agents_dir"] == "config/agents"
    assert len(manifest["manifest_hash"]) == 64
    assert manifest["progress_contract"]["schema_version"] == 1
    assert manifest["progress_contract"]["transport"] == "stdout_jsonl"
    assert manifest["progress_contract"]["log_transport"] == "stderr"
    assert manifest["progress_contract"]["generated_adapters"] == [
        "deterministic_workflow",
        "simple_agent",
        "deep_agent",
    ]
    assert "backlog_url" in manifest
    assert "army_integration" in manifest
    assert manifest["army_integration"]["approval_required_before_registry_entry"] is True


def test_build_factory_manifest_live_registry() -> None:
    manifest = build_factory_manifest(include_live=True)

    assert "live_registry" in manifest
    lr = manifest["live_registry"]
    assert "as_of" in lr
    assert "enabled_agents" in lr
    assert isinstance(lr["enabled_count"], int)
    assert isinstance(lr["staged_count"], int)
    # pending_approval_count may be -1 if DB unavailable
    assert isinstance(lr["pending_approval_count"], int)


def test_build_factory_manifest_enabled_agent_fields() -> None:
    """Enabled agents include the fields Army needs for routing."""
    manifest = build_factory_manifest(include_live=True)

    for agent in manifest["live_registry"]["enabled_agents"]:
        assert "id" in agent
        assert "name" in agent
        assert "purpose" in agent
        assert "aliases" in agent


def test_manifest_hash_excludes_live_registry() -> None:
    """Hash must be stable across calls regardless of live counts."""
    m1 = build_factory_manifest(include_live=False)
    m2 = build_factory_manifest(include_live=True)

    assert m1["manifest_hash"] == m2["manifest_hash"]


def test_render_factory_manifest_compact_is_single_line_json() -> None:
    rendered = render_factory_manifest(compact=True, include_live=False)
    manifest = json.loads(rendered)

    assert "\n" not in rendered
    assert rendered.startswith("{")
    assert manifest["agent_id"] == "agent-factory"
    assert manifest["manifest_hash"]
    assert MANIFEST_COMMAND == "uv run agent-factory manifest"


def test_cli_manifest_command_prints_compact_handshake(capsys) -> None:
    exit_code = cli_module.main(["manifest"])

    captured = capsys.readouterr()
    manifest = json.loads(captured.out)

    assert exit_code == 0
    assert "\n" not in captured.out.strip()
    assert manifest["agent_id"] == "agent-factory"
    assert manifest["manifest_hash"]
    assert "live_registry" in manifest


def test_factory_manifest_advertises_universal_specialist_protocol() -> None:
    manifest = build_factory_manifest(include_live=False)

    assert manifest["specialist_protocol"]["protocol"] == "agent-hub.task"
    assert manifest["specialist_protocol"]["protocol_version"] == 1
    assert manifest["specialist_protocol"]["required_fields"] == ["task"]
