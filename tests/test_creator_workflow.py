import json
from pathlib import Path

import pytest

from agent_factory import cli, creator_workflow


def point_workflow_at_tmp(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(creator_workflow, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(creator_workflow, "TEMPLATE_DIR", repo_root / "templates" / "agent-package")
    monkeypatch.setattr(creator_workflow, "STAGING_DIR", tmp_path / "staging" / "agents")


def test_create_staged_agent_package_writes_files(monkeypatch, tmp_path):
    point_workflow_at_tmp(monkeypatch, tmp_path)

    state = creator_workflow.create_staged_agent_package("Create a docs reviewer agent")

    package_dir = tmp_path / "staging" / "agents" / state["agent_id"]
    manifest = json.loads((package_dir / "agent.json").read_text(encoding="utf-8"))
    review = (package_dir / "REVIEW.md").read_text(encoding="utf-8")
    agents = (package_dir / "AGENTS.md").read_text(encoding="utf-8")
    skills_index = (package_dir / "skills" / "INDEX.md").read_text(encoding="utf-8")

    assert state["status"] == "staged"
    assert package_dir.is_dir()
    assert manifest["id"] == state["agent_id"]
    assert manifest["name"] == state["agent_name"]
    assert manifest["permissions"]["requires_approval"] is True
    assert manifest["runtime"]["mode"] == "manual"
    assert "Status: staged draft only." in review
    assert "Do not copy this agent into `config/agents` until approved." in review
    assert "Read `AGENTS.md`" in (package_dir / "README.md").read_text(encoding="utf-8")
    assert "smallest change" in agents
    assert "does not define agent-specific skills yet" in skills_index
    assert any("staging/agents/" in path for path in state["created_files"])
    assert any(path.endswith("AGENTS.md") for path in state["created_files"])
    assert any(path.endswith("skills/INDEX.md") for path in state["created_files"])
    assert any(path.endswith("agent.json") for path in state["created_files"])
    assert any(path.endswith("REVIEW.md") for path in state["created_files"])


def test_create_staged_agent_package_reuses_existing_package(monkeypatch, tmp_path):
    point_workflow_at_tmp(monkeypatch, tmp_path)

    first = creator_workflow.create_staged_agent_package("Create a docs reviewer agent")
    second = creator_workflow.create_staged_agent_package("Create a docs reviewer agent")

    assert first["agent_id"] == second["agent_id"]
    assert first["package_dir"] == second["package_dir"]
    assert first["status"] == "staged"
    assert second["status"] == "reused"
    assert sorted(first["created_files"]) == sorted(second["created_files"])


def test_create_command_outputs_json(monkeypatch, tmp_path, capsys):
    point_workflow_at_tmp(monkeypatch, tmp_path)

    exit_code = cli.main(["create", "Create a docs reviewer agent"])
    output = capsys.readouterr().out
    state = json.loads(output)

    assert exit_code == 0
    assert state["status"] == "staged"
    assert Path(state["package_dir"]).is_dir()
