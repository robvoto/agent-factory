"""Run a deliberately requested test against one Factory-staged subprocess agent.

This is a local execution harness, not an operating-system sandbox. It never
loads a staged package into the enabled registry and always uses the staged
directory as the package root and working directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .agent_spec import VALID_ID_PATTERN, AgentPermissions
from .build_task import BuildTaskError, load_staged_manifest
from .storage import finish_incubation_test_run, start_incubation_test_run


class IncubationTestError(ValueError):
    """The staged package cannot be run through the test-only harness."""


def run_staged_agent_test(
    agent_id: str,
    payload: dict[str, Any],
    *,
    approved: bool,
    approve_risk: bool = False,
    exposed_environment: tuple[str, ...] = (),
    project_root: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Invoke the current staged subprocess and persist a metadata-only audit row."""
    if not approved:
        raise IncubationTestError("Operator approval is required: pass --approve to run a staged agent.")
    if not isinstance(payload, dict):
        raise IncubationTestError("Test input must be a JSON object.")
    if not VALID_ID_PATTERN.fullmatch(agent_id):
        raise IncubationTestError("Agent ID must be a valid lowercase Factory identifier.")

    root = (project_root or Path(__file__).parents[2]).resolve()
    try:
        staging_root = (root / "staging" / "agents").resolve(strict=True)
        package_dir = (staging_root / agent_id).resolve(strict=True)
    except OSError as exc:
        raise IncubationTestError(f"No accessible staged package found for {agent_id!r}.") from exc
    if not package_dir.is_relative_to(staging_root):
        raise IncubationTestError("Staged package resolves outside staging/agents.")
    if not agent_id or package_dir.name != agent_id:
        raise IncubationTestError("Agent ID does not match the staged package directory.")

    enabled_paths = (
        root / "config" / "agents" / f"{agent_id}.json",
        root / "config" / "agents" / agent_id / "agent.json",
        root / "agents" / agent_id / "agent.json",
    )
    if any(path.exists() for path in enabled_paths):
        raise IncubationTestError(
            f"{agent_id!r} is already released or registered; this command accepts incubating packages only."
        )

    try:
        _raw, manifest, manifest_sha256 = load_staged_manifest(package_dir, agent_id)
    except (BuildTaskError, OSError, ValueError) as exc:
        raise IncubationTestError(f"Could not validate staged agent manifest: {exc}") from exc

    runtime = manifest.runtime
    if runtime.get("mode") != "subprocess":
        raise IncubationTestError(
            f"Staged agent runtime mode {runtime.get('mode')!r} is not executable by this harness."
        )
    entrypoint = runtime.get("entrypoint")
    input_arg = runtime.get("input_arg")
    output_arg = runtime.get("output_arg")
    if not entrypoint or not input_arg or not output_arg:
        raise IncubationTestError("Subprocess runtime must declare entrypoint, input_arg, and output_arg.")
    if not input_arg.startswith("--") or not output_arg.startswith("--") or input_arg == output_arg:
        raise IncubationTestError("Subprocess input_arg and output_arg must be distinct named options.")
    command = _python_script(entrypoint, package_dir)

    risk_flags = AgentPermissions.model_validate(manifest.permissions).risk_flags()
    if manifest.tools:
        risk_flags.append("tools")
    if manifest.mcp_servers:
        risk_flags.append("mcp")
    risk_flags = sorted(set(risk_flags))
    exposed_environment = tuple(dict.fromkeys(exposed_environment))
    if exposed_environment:
        risk_flags.append("environment_access")
    unsupported_capabilities = sorted(set(risk_flags).intersection({"tools", "mcp"}))
    unknown_environment = [name for name in exposed_environment if name not in os.environ]
    if unknown_environment:
        raise IncubationTestError(
            "Requested environment variables are not set: " + ", ".join(unknown_environment)
        )
    if exposed_environment and not approve_risk:
        raise IncubationTestError("Exposing environment variables requires --approve-risk.")
    _assert_no_secret_files(package_dir)

    run_id = str(uuid.uuid4())
    input_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    package_sha256 = _package_sha256(package_dir)
    started = time.monotonic()
    start_incubation_test_run(
        run_id=run_id,
        agent_id=agent_id,
        manifest_sha256=manifest_sha256,
        package_sha256=package_sha256,
        input_sha256=hashlib.sha256(input_bytes).hexdigest(),
        permission_flags=risk_flags,
        exposed_environment=list(exposed_environment),
        risk_approved=approve_risk,
        db_path=db_path,
    )

    if risk_flags and not approve_risk:
        finish_incubation_test_run(
            run_id,
            status="blocked",
            duration_ms=0,
            exit_code=None,
            failure_code="risk_approval_required",
            db_path=db_path,
        )
        raise IncubationTestError(
            f"Test blocked for declared capabilities: {', '.join(risk_flags)}. "
            f"Review the package and rerun with --approve-risk if you approve these capabilities. Run ID: {run_id}"
        )
    if unsupported_capabilities:
        finish_incubation_test_run(
            run_id,
            status="blocked",
            duration_ms=0,
            exit_code=None,
            failure_code="test_harness_capability_unavailable",
            db_path=db_path,
        )
        raise IncubationTestError(
            "This local harness does not supply declared tools or MCP capabilities; "
            f"the test was blocked. Run ID: {run_id}"
        )

    environment = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    for name in exposed_environment:
        environment[name] = os.environ[name]

    with tempfile.TemporaryDirectory(prefix=f"agent-factory-test-{agent_id}-") as temp_dir:
        temp_root = Path(temp_dir)
        execution_root = temp_root / "package"
        shutil.copytree(package_dir, execution_root)
        script = execution_root / command.relative_to(package_dir)
        input_path = temp_root / "input.json"
        output_path = temp_root / "output.json"
        input_path.write_bytes(input_bytes)
        argv = [
            sys.executable,
            str(script),
            input_arg,
            str(input_path),
            output_arg,
            str(output_path),
        ]
        try:
            completed = subprocess.run(
                argv,
                cwd=execution_root,
                env=environment,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            result = _read_result(output_path, manifest.output_contract["status_values"])
            success = completed.returncode == 0 and result["status"] != "failed"
            finish_incubation_test_run(
                run_id,
                status=result["status"] if success else "failed",
                duration_ms=elapsed_ms,
                exit_code=completed.returncode,
                failure_code=None if success else "agent_result_failed",
                db_path=db_path,
            )
            return {
                "run_id": run_id,
                "agent_id": agent_id,
                "status": result["status"] if success else "failed",
                "exit_code": completed.returncode,
                "result": result,
            }
        except (OSError, IncubationTestError) as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            finish_incubation_test_run(
                run_id,
                status="failed",
                duration_ms=elapsed_ms,
                exit_code=None,
                failure_code="test_execution_failed",
                db_path=db_path,
            )
            if isinstance(exc, IncubationTestError):
                raise
            raise IncubationTestError(f"Could not execute staged agent: {exc}") from exc


def _python_script(entrypoint: str, package_dir: Path) -> Path:
    """Allow exactly one in-package Python script; do not interpret shell syntax."""
    try:
        parts = shlex.split(entrypoint, posix=True)
    except ValueError as exc:
        raise IncubationTestError("runtime.entrypoint is not a valid argument list.") from exc
    if len(parts) != 2 or parts[0] not in {"python", "python3"}:
        raise IncubationTestError(
            "Test harness supports only `python <relative-script.py>` entrypoints; no shell or extra arguments."
        )
    candidate = (package_dir / parts[1]).resolve(strict=True)
    if not candidate.is_relative_to(package_dir) or not candidate.is_file() or candidate.suffix != ".py":
        raise IncubationTestError("runtime.entrypoint must name an existing Python file inside the staged package.")
    return candidate


def _package_sha256(package_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package_dir.rglob("*")):
        if path.is_symlink():
            raise IncubationTestError("Staged package contains a symlink; test execution is blocked.")
        if path.is_file():
            digest.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _assert_no_secret_files(package_dir: Path) -> None:
    forbidden = []
    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if (name.startswith(".env") and name != ".env.example") or name in {
            "credentials.json",
            "token.json",
            "secrets.json",
        }:
            forbidden.append(path.relative_to(package_dir).as_posix())
    if forbidden:
        raise IncubationTestError(
            "Staged package contains secret-like files that must be removed before testing: "
            + ", ".join(sorted(forbidden))
        )


def _read_result(path: Path, allowed_statuses: list[str]) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncubationTestError("Staged agent did not produce valid output JSON.") from exc
    if not isinstance(result, dict) or result.get("status") not in allowed_statuses:
        raise IncubationTestError("Staged agent result violates its declared output status contract.")
    return result
