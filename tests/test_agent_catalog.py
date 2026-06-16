"""Tests for the shared agent catalog and reuse helpers."""

import json

from agent_factory.agent_catalog import build_agent_catalog, plan_package_reuse, promote_agent
from agent_factory.agent_spec import AgentPackageSpec


def _manifest() -> dict:
    return {
        "id": "alpha-agent",
        "name": "Alpha Agent",
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
    }


def _spec() -> AgentPackageSpec:
    return AgentPackageSpec.model_validate(
        {
            "id": "alpha-agent",
            "name": "Alpha Agent",
            "purpose": "Alpha does the alpha work.",
            "aliases": ["alpha"],
        }
    )


def test_build_agent_catalog_merges_staged_and_enabled(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    enabled = tmp_path / "config" / "agents"
    staging.mkdir(parents=True)
    enabled.mkdir(parents=True)

    payload = json.dumps(_manifest())
    (staging / "agent.json").write_text(payload, encoding="utf-8")
    (enabled / "alpha-agent.json").write_text(payload, encoding="utf-8")

    catalog = build_agent_catalog(enabled_dir=enabled, staging_dir=tmp_path / "staging")
    entry = catalog["alpha-agent"]

    assert entry.id == "alpha-agent"
    assert set(entry.statuses) == {"staged", "enabled"}
    assert any(location.endswith("staging/agents/alpha-agent") for location in entry.locations)
    assert any(location.endswith("config/agents/alpha-agent.json") for location in entry.locations)


def test_plan_package_reuse_reuses_existing_enabled_agent(tmp_path):
    enabled = tmp_path / "config" / "agents"
    enabled.mkdir(parents=True)
    (enabled / "alpha-agent.json").write_text(json.dumps(_manifest()), encoding="utf-8")

    decision = plan_package_reuse(_spec(), enabled_dir=enabled, staging_dir=tmp_path / "staging")

    assert decision.action == "reuse"
    assert decision.entry is not None
    assert decision.entry.id == "alpha-agent"


def test_promote_agent_reuses_existing_enabled_agent(tmp_path):
    staging = tmp_path / "staging" / "agents" / "alpha-agent"
    enabled = tmp_path / "config" / "agents"
    staging.mkdir(parents=True)
    enabled.mkdir(parents=True)

    payload = json.dumps(_manifest())
    (staging / "agent.json").write_text(payload, encoding="utf-8")
    (enabled / "alpha-agent.json").write_text(payload, encoding="utf-8")

    result = promote_agent("alpha-agent", project_root=tmp_path, db_path=tmp_path / "factory.sqlite3")

    assert "already enabled" in result
    assert (enabled / "alpha-agent.json").read_text(encoding="utf-8") == payload
