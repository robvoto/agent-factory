from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_factory.incubation_test import IncubationTestError, run_staged_agent_test
from agent_factory.storage import list_incubation_test_runs


def _manifest(*, network: bool = False, tools: list[str] | None = None) -> dict:
    return {
        "id": "incubating-agent",
        "version": "1.0.0",
        "manifest_schema_version": 1,
        "name": "Incubating Agent",
        "purpose": (
            "Primary responsibility: Run an isolated test workflow.\n"
            "Select for: A direct request to test the incubating workflow.\n"
            "Do not select for: Production routing or unrelated requests."
        ),
        "aliases": ["incubating"],
        "tools": tools or [],
        "permissions": {
            "network": network,
            "filesystem": "none",
            "shell": False,
            "requires_approval": True,
        },
        "memory": {"scope": "none", "retention": "none"},
        "design": {
            "runtime_pattern": "deterministic_workflow",
            "runtime_pattern_reason": "A fixed workflow is appropriate for this test fixture.",
        },
        "runtime": {
            "mode": "subprocess",
            "entrypoint": "python src/run_agent.py",
            "working_directory": "/ignored/released/path",
            "input_arg": "--input-json",
            "output_arg": "--output-json",
            "default_execution_mode": "execute",
        },
        "output_contract": {
            "status_values": ["success", "needs_clarification", "waiting_decision", "failed"],
            "status_contract": {
                "success": {"terminal": True, "caller_action": "consume_result"},
                "needs_clarification": {"terminal": False, "caller_action": "clarify"},
                "waiting_decision": {"terminal": False, "caller_action": "decide"},
                "failed": {"terminal": True, "caller_action": "inspect_failure"},
            },
        },
    }


def _stage(root: Path, *, network: bool = False, tools: list[str] | None = None) -> Path:
    package = root / "staging" / "agents" / "incubating-agent"
    (package / "src").mkdir(parents=True)
    (package / "agent.json").write_text(
        json.dumps(_manifest(network=network, tools=tools)), encoding="utf-8"
    )
    (package / "src" / "run_agent.py").write_text(
        "import json, pathlib, sys\n"
        "args = sys.argv\n"
        "input_path = pathlib.Path(args[args.index('--input-json') + 1])\n"
        "output_path = pathlib.Path(args[args.index('--output-json') + 1])\n"
        "payload = json.loads(input_path.read_text(encoding='utf-8'))\n"
        "pathlib.Path('test-side-effect.txt').write_text('only in the temporary copy')\n"
        "output_path.write_text(json.dumps({'status': 'success', 'summary': payload['task']}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    return package


def test_runs_only_staged_copy_and_logs_metadata_without_payload(tmp_path: Path) -> None:
    package = _stage(tmp_path)
    result = run_staged_agent_test(
        "incubating-agent",
        {"task": "secret input text"},
        approved=True,
        project_root=tmp_path,
        db_path=tmp_path / "factory.sqlite3",
    )

    assert result["status"] == "success"
    assert result["result"]["summary"] == "secret input text"
    assert not (package / "test-side-effect.txt").exists()
    assert not (tmp_path / "config" / "agents").exists()
    assert not (tmp_path / "agents").exists()
    rows = list_incubation_test_runs(db_path=tmp_path / "factory.sqlite3")
    assert rows[0]["status"] == "success"
    assert rows[0]["agent_id"] == "incubating-agent"
    assert rows[0]["input_sha256"]
    assert rows[0]["manifest_sha256"] and rows[0]["package_sha256"]
    assert "secret input text" not in repr(rows[0])
    assert "summary" not in rows[0]


def test_declared_network_permission_requires_explicit_risk_approval(tmp_path: Path) -> None:
    _stage(tmp_path, network=True)
    db = tmp_path / "factory.sqlite3"

    with pytest.raises(IncubationTestError, match="--approve-risk"):
        run_staged_agent_test(
            "incubating-agent",
            {"task": "test"},
            approved=True,
            project_root=tmp_path,
            db_path=db,
        )

    rows = list_incubation_test_runs(db_path=db)
    assert rows[0]["status"] == "blocked"
    assert rows[0]["risk_approved"] == 0
    assert json.loads(rows[0]["permission_flags"]) == ["network"]


def test_approved_network_capability_is_recorded_for_one_run(tmp_path: Path) -> None:
    _stage(tmp_path, network=True)
    db = tmp_path / "factory.sqlite3"
    result = run_staged_agent_test(
        "incubating-agent",
        {"task": "test"},
        approved=True,
        approve_risk=True,
        project_root=tmp_path,
        db_path=db,
    )

    assert result["status"] == "success"
    row = list_incubation_test_runs(db_path=db)[0]
    assert row["risk_approved"] == 1
    assert json.loads(row["permission_flags"]) == ["network"]


def test_declared_nonterminal_status_is_a_valid_test_outcome(tmp_path: Path) -> None:
    package = _stage(tmp_path)
    script = package / "src" / "run_agent.py"
    script.write_text(
        script.read_text(encoding="utf-8").replace("'success'", "'needs_clarification'"),
        encoding="utf-8",
    )

    result = run_staged_agent_test(
        "incubating-agent",
        {"task": "test"},
        approved=True,
        project_root=tmp_path,
        db_path=tmp_path / "factory.sqlite3",
    )

    assert result["status"] == "needs_clarification"
    assert list_incubation_test_runs(db_path=tmp_path / "factory.sqlite3")[0]["status"] == "needs_clarification"


def test_only_named_environment_values_are_passed_after_risk_approval(tmp_path: Path, monkeypatch) -> None:
    package = _stage(tmp_path, network=True)
    monkeypatch.setenv("EXPOSED_TEST_VALUE", "visible")
    monkeypatch.setenv("UNEXPOSED_TEST_VALUE", "must-not-arrive")
    script = package / "src" / "run_agent.py"
    script.write_text(
        "import json, os, pathlib, sys\n"
        "args = sys.argv\n"
        "out = pathlib.Path(args[args.index('--output-json') + 1])\n"
        "out.write_text(json.dumps({'status': 'success', 'summary': os.getenv('EXPOSED_TEST_VALUE'), 'hidden': os.getenv('UNEXPOSED_TEST_VALUE')}), encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = run_staged_agent_test(
        "incubating-agent",
        {"task": "test"},
        approved=True,
        approve_risk=True,
        exposed_environment=("EXPOSED_TEST_VALUE",),
        project_root=tmp_path,
        db_path=tmp_path / "factory.sqlite3",
    )

    assert result["result"]["summary"] == "visible"
    assert result["result"]["hidden"] is None
    row = list_incubation_test_runs(db_path=tmp_path / "factory.sqlite3")[0]
    assert json.loads(row["exposed_environment"]) == ["EXPOSED_TEST_VALUE"]


def test_tool_capabilities_fail_closed_even_with_risk_approval(tmp_path: Path) -> None:
    _stage(tmp_path, tools=["external_tool"])
    db = tmp_path / "factory.sqlite3"

    with pytest.raises(IncubationTestError, match="does not supply declared tools or MCP"):
        run_staged_agent_test(
            "incubating-agent",
            {"task": "test"},
            approved=True,
            approve_risk=True,
            project_root=tmp_path,
            db_path=db,
        )

    assert list_incubation_test_runs(db_path=db)[0]["status"] == "blocked"


def test_operator_approval_is_required_by_service(tmp_path: Path) -> None:
    _stage(tmp_path)
    with pytest.raises(IncubationTestError, match="pass --approve"):
        run_staged_agent_test(
            "incubating-agent",
            {"task": "test"},
            approved=False,
            project_root=tmp_path,
            db_path=tmp_path / "factory.sqlite3",
        )
    assert list_incubation_test_runs(db_path=tmp_path / "factory.sqlite3") == []


def test_released_or_registered_agent_is_not_an_incubation_test_target(tmp_path: Path) -> None:
    _stage(tmp_path)
    registered = tmp_path / "config" / "agents" / "incubating-agent" / "agent.json"
    registered.parent.mkdir(parents=True)
    registered.write_text("{}", encoding="utf-8")

    with pytest.raises(IncubationTestError, match="already released or registered"):
        run_staged_agent_test(
            "incubating-agent",
            {"task": "test"},
            approved=True,
            project_root=tmp_path,
            db_path=tmp_path / "factory.sqlite3",
        )


def test_only_in_package_python_script_entrypoints_are_accepted(tmp_path: Path) -> None:
    package = _stage(tmp_path)
    manifest = _manifest()
    manifest["runtime"]["entrypoint"] = "python -c 'print(1)'"
    (package / "agent.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(IncubationTestError, match="no shell or extra arguments"):
        run_staged_agent_test(
            "incubating-agent",
            {"task": "test"},
            approved=True,
            project_root=tmp_path,
            db_path=tmp_path / "factory.sqlite3",
        )


def test_secret_files_block_test_execution(tmp_path: Path) -> None:
    package = _stage(tmp_path)
    (package / ".env.local").write_text("PRIVATE=secret", encoding="utf-8")

    with pytest.raises(IncubationTestError, match="secret-like files"):
        run_staged_agent_test(
            "incubating-agent",
            {"task": "test"},
            approved=True,
            project_root=tmp_path,
            db_path=tmp_path / "factory.sqlite3",
        )


def test_cli_requires_approval_and_emits_test_result(tmp_path: Path, monkeypatch, capsys) -> None:
    package = _stage(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"task": "CLI test"}), encoding="utf-8")

    from agent_factory import cli, storage

    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "configure_logging", lambda _level=None: None)
    monkeypatch.setattr(cli, "logger", type("QuietLogger", (), {"info": lambda *_args: None, "warning": lambda *_args: None})())
    monkeypatch.setattr(storage, "_DEFAULT_DB_PATH", tmp_path / "factory.sqlite3")
    exit_code = cli.main(["test", "incubating-agent", "--input-json", str(input_path), "--approve"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["result"]["summary"] == "CLI test"
    assert not (package / "test-side-effect.txt").exists()
    assert cli.main(["test-runs", "incubating-agent"]) == 0
    assert "incubating-agent" in capsys.readouterr().out
