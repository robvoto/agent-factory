"""Factory-owned consumer for AI Tech Lead BuildResult v1.

This module mirrors the caller-facing wire contract without importing AI Tech
Lead code.  The wire payload is evidence only; Factory still resolves the
approved task, rechecks the staged package, and applies its own promotion
rules before persisting validation.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from .agent_spec import VALID_ID_PATTERN
from .build_task import (
    BUILD_TASK_FILENAME,
    AgentBuildTask,
    BuildTaskError,
    assert_task_matches_staged_package,
    build_task_reference,
)

BUILD_RESULT_SCHEMA_VERSION = 1
BUILD_RESULT_FILENAME = "BUILD_RESULT.json"
BUILD_RESULT_REFERENCE_NAME = BUILD_RESULT_FILENAME

_MAX_TEXT_CHARS = 2_000
_MAX_ERROR_CHARS = 500
_MAX_PATH_CHARS = 4_096
_MAX_LIST_ITEMS = 256
_MAX_ERRORS = 20
_MAX_COUNTER = 10**12
_CONTROL_ARTIFACTS = frozenset({BUILD_TASK_FILENAME, BUILD_RESULT_FILENAME})
_TOKEN_SCOPE = "ai_tech_lead_orchestrator"


class BuildResultValidationError(BuildTaskError):
    """A BuildResult v1 payload or its evidence is invalid."""


class BuildResultConsumptionError(BuildResultValidationError):
    """A BuildResult cannot be accepted or would violate promotion safety."""

    status = "failed"


def _exact_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise BuildResultValidationError(f"{field} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise BuildResultValidationError(f"{field} has invalid fields ({'; '.join(detail)})")
    return value


def _text(value: Any, field: str, *, limit: int = _MAX_TEXT_CHARS, non_empty: bool = False) -> str:
    if type(value) is not str:
        raise BuildResultValidationError(f"{field} must be a string")
    if len(value) > limit:
        raise BuildResultValidationError(f"{field} exceeds the {limit}-character limit")
    if non_empty and not value.strip():
        raise BuildResultValidationError(f"{field} must be non-empty")
    return value


def _boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise BuildResultValidationError(f"{field} must be a boolean")
    return value


def _integer(value: Any, field: str, *, maximum: int = _MAX_COUNTER) -> int:
    if type(value) is not int:
        raise BuildResultValidationError(f"{field} must be an integer")
    if value < 0 or value > maximum:
        raise BuildResultValidationError(f"{field} must be between 0 and {maximum}")
    return value


def _number(value: Any, field: str) -> int | float:
    if type(value) not in {int, float}:
        raise BuildResultValidationError(f"{field} must be a number")
    if not math.isfinite(float(value)) or value < 0:
        raise BuildResultValidationError(f"{field} must be finite and non-negative")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if type(value) is not list:
        raise BuildResultValidationError(f"{field} must be a list")
    if len(value) > _MAX_LIST_ITEMS:
        raise BuildResultValidationError(f"{field} contains too many items")
    return value


def _text_list(
    value: Any,
    field: str,
    *,
    limit: int = _MAX_TEXT_CHARS,
    item_limit: int | None = None,
) -> list[str]:
    values = _list(value, field)
    return [
        _text(item, f"{field}[{index}]", limit=item_limit or limit)
        for index, item in enumerate(values)
    ]


def _parse_test(value: Any, index: int) -> dict[str, str]:
    item = _exact_keys(value, {"command", "status", "output"}, f"tests_run[{index}]")
    command = _text(item["command"], f"tests_run[{index}].command", non_empty=True)
    status = _text(item["status"], f"tests_run[{index}].status", non_empty=True)
    if status not in {"passed", "failed", "not_run"}:
        raise BuildResultValidationError(
            f"tests_run[{index}].status must be passed, failed, or not_run"
        )
    output = _text(item["output"], f"tests_run[{index}].output")
    return {"command": command, "status": status, "output": output}


def _parse_validation_evidence(value: Any) -> dict[str, Any]:
    item = _exact_keys(
        value,
        {
            "diff_summary",
            "validation_command",
            "validation_passed",
            "validation_output_tail",
            "out_of_scope_paths",
            "verification_status",
            "verification_reason",
            "independent_review",
            "git_lifecycle",
        },
        "validation_evidence",
    )
    passed = item["validation_passed"]
    if passed is not None:
        _boolean(passed, "validation_evidence.validation_passed")
    review = item["independent_review"]
    if review is not None:
        review = _exact_keys(
            review,
            {"status", "reviewer", "findings"},
            "validation_evidence.independent_review",
        )
        _text(review["status"], "validation_evidence.independent_review.status")
        if review["reviewer"] is not None:
            _text(review["reviewer"], "validation_evidence.independent_review.reviewer")
        review = {
            "status": review["status"],
            "reviewer": review["reviewer"],
            "findings": _text_list(
                review["findings"],
                "validation_evidence.independent_review.findings",
            ),
        }

    lifecycle = _exact_keys(
        item["git_lifecycle"],
        {
            "enabled",
            "preflight_status",
            "preflight_branch",
            "preflight_head",
            "preflight_dirty_paths",
            "preflight_reason",
            "task_canonical_root",
            "task_worktree",
            "task_branch",
            "task_base_sha",
            "task_tip_sha",
            "task_commit_sha",
            "branch_pushed",
            "main_status",
            "main_sha",
            "integration_status",
            "integration_reason",
        },
        "validation_evidence.git_lifecycle",
    )
    _boolean(lifecycle["enabled"], "validation_evidence.git_lifecycle.enabled")
    _boolean(lifecycle["branch_pushed"], "validation_evidence.git_lifecycle.branch_pushed")
    lifecycle = {
        "enabled": _boolean(
            lifecycle["enabled"], "validation_evidence.git_lifecycle.enabled"
        ),
        "preflight_status": _text(
            lifecycle["preflight_status"],
            "validation_evidence.git_lifecycle.preflight_status",
        ),
        "preflight_branch": _text(
            lifecycle["preflight_branch"],
            "validation_evidence.git_lifecycle.preflight_branch",
        ),
        "preflight_head": _text(
            lifecycle["preflight_head"],
            "validation_evidence.git_lifecycle.preflight_head",
        ),
        "preflight_dirty_paths": _text_list(
            lifecycle["preflight_dirty_paths"],
            "validation_evidence.git_lifecycle.preflight_dirty_paths",
            limit=_MAX_PATH_CHARS,
        ),
        "preflight_reason": _text(
            lifecycle["preflight_reason"],
            "validation_evidence.git_lifecycle.preflight_reason",
        ),
        "task_canonical_root": _text(
            lifecycle["task_canonical_root"],
            "validation_evidence.git_lifecycle.task_canonical_root",
        ),
        "task_worktree": _text(
            lifecycle["task_worktree"],
            "validation_evidence.git_lifecycle.task_worktree",
        ),
        "task_branch": _text(
            lifecycle["task_branch"],
            "validation_evidence.git_lifecycle.task_branch",
        ),
        "task_base_sha": _text(
            lifecycle["task_base_sha"],
            "validation_evidence.git_lifecycle.task_base_sha",
        ),
        "task_tip_sha": _text(
            lifecycle["task_tip_sha"],
            "validation_evidence.git_lifecycle.task_tip_sha",
        ),
        "task_commit_sha": _text(
            lifecycle["task_commit_sha"],
            "validation_evidence.git_lifecycle.task_commit_sha",
        ),
        "branch_pushed": _boolean(
            lifecycle["branch_pushed"],
            "validation_evidence.git_lifecycle.branch_pushed",
        ),
        "main_status": _text(
            lifecycle["main_status"], "validation_evidence.git_lifecycle.main_status"
        ),
        "main_sha": _text(lifecycle["main_sha"], "validation_evidence.git_lifecycle.main_sha"),
        "integration_status": _text(
            lifecycle["integration_status"],
            "validation_evidence.git_lifecycle.integration_status",
        ),
        "integration_reason": _text(
            lifecycle["integration_reason"],
            "validation_evidence.git_lifecycle.integration_reason",
        ),
    }
    return {
        "diff_summary": _text(item["diff_summary"], "validation_evidence.diff_summary"),
        "validation_command": _text(
            item["validation_command"], "validation_evidence.validation_command"
        ),
        "validation_passed": passed,
        "validation_output_tail": _text(
            item["validation_output_tail"], "validation_evidence.validation_output_tail"
        ),
        "out_of_scope_paths": _text_list(
            item["out_of_scope_paths"],
            "validation_evidence.out_of_scope_paths",
            limit=_MAX_PATH_CHARS,
        ),
        "verification_status": _text(
            item["verification_status"], "validation_evidence.verification_status"
        ),
        "verification_reason": _text(
            item["verification_reason"], "validation_evidence.verification_reason"
        ),
        "independent_review": review,
        "git_lifecycle": lifecycle,
    }


def _parse_token_usage(value: Any) -> dict[str, Any]:
    item = _exact_keys(
        value,
        {"scope", "availability", "calls", "tokens_in", "tokens_out", "tokens_total", "backend_usage"},
        "token_usage",
    )
    scope = _text(item["scope"], "token_usage.scope", non_empty=True)
    if scope != _TOKEN_SCOPE:
        raise BuildResultValidationError(
            f"token_usage.scope must be { _TOKEN_SCOPE!r} for BuildResult v1"
        )
    if item["availability"] != "available":
        raise BuildResultValidationError("token_usage.availability must be available")
    calls = _integer(item["calls"], "token_usage.calls")
    tokens_in = _integer(item["tokens_in"], "token_usage.tokens_in")
    tokens_out = _integer(item["tokens_out"], "token_usage.tokens_out")
    tokens_total = _integer(item["tokens_total"], "token_usage.tokens_total")
    if tokens_total != tokens_in + tokens_out:
        raise BuildResultValidationError(
            "token_usage.tokens_total must equal tokens_in plus tokens_out"
        )
    backend = _exact_keys(
        item["backend_usage"],
        {"availability", "scope", "tokens", "reason"},
        "token_usage.backend_usage",
    )
    if backend["availability"] != "unavailable" or backend["tokens"] is not None:
        raise BuildResultValidationError(
            "coding-backend usage must be explicitly unavailable with tokens=null"
        )
    backend_scope = _text(backend["scope"], "token_usage.backend_usage.scope", non_empty=True)
    backend_reason = _text(backend["reason"], "token_usage.backend_usage.reason", non_empty=True)
    return {
        "scope": scope,
        "availability": "available",
        "calls": calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_total,
        "backend_usage": {
            "availability": "unavailable",
            "scope": backend_scope,
            "tokens": None,
            "reason": backend_reason,
        },
    }


def _parse_wire_result(value: Any) -> dict[str, Any]:
    item = _exact_keys(
        value,
        {
            "schema_version",
            "status",
            "changed_files",
            "tests_run",
            "validation_evidence",
            "token_usage",
            "estimated_cost_usd",
            "estimated_cost_scope",
            "estimated_cost_source",
            "errors",
            "stop_reason",
            "duration_seconds",
        },
        "build_result",
    )
    if type(item["schema_version"]) is not int or item["schema_version"] != BUILD_RESULT_SCHEMA_VERSION:
        raise BuildResultValidationError("build_result.schema_version must be 1")
    status = _text(item["status"], "build_result.status", non_empty=True)
    if status not in {"success", "failed", "stopped"}:
        raise BuildResultValidationError("build_result.status must be success, failed, or stopped")
    changed_files = _text_list(
        item["changed_files"], "build_result.changed_files", limit=_MAX_PATH_CHARS
    )
    tests = [
        _parse_test(test, index)
        for index, test in enumerate(_list(item["tests_run"], "build_result.tests_run"))
    ]
    errors = _text_list(
        item["errors"], "build_result.errors", limit=_MAX_ERROR_CHARS
    )
    if len(errors) > _MAX_ERRORS:
        raise BuildResultValidationError(f"build_result.errors contains more than {_MAX_ERRORS} items")
    duration = _number(item["duration_seconds"], "build_result.duration_seconds")
    cost = item["estimated_cost_usd"]
    if cost is not None:
        cost = _number(cost, "build_result.estimated_cost_usd")
    cost_scope = _text(item["estimated_cost_scope"], "build_result.estimated_cost_scope", non_empty=True)
    cost_source = _text(item["estimated_cost_source"], "build_result.estimated_cost_source", non_empty=True)
    stop_reason = _text(item["stop_reason"], "build_result.stop_reason", non_empty=True)
    if status == "success" and errors:
        raise BuildResultValidationError("successful build_result.errors must be empty")
    if status in {"failed", "stopped"} and not errors:
        raise BuildResultValidationError("failed or stopped build_result.errors must be non-empty")
    return {
        "schema_version": BUILD_RESULT_SCHEMA_VERSION,
        "status": status,
        "changed_files": changed_files,
        "tests_run": tests,
        "validation_evidence": _parse_validation_evidence(item["validation_evidence"]),
        "token_usage": _parse_token_usage(item["token_usage"]),
        "estimated_cost_usd": cost,
        "estimated_cost_scope": cost_scope,
        "estimated_cost_source": cost_source,
        "errors": errors,
        "stop_reason": stop_reason,
        "duration_seconds": duration,
    }


def _canonical_reference(reference: Any) -> str:
    if type(reference) is not str or not reference:
        raise BuildResultConsumptionError("artifact_reference must be a non-empty string")
    path = PurePosixPath(reference)
    if (
        str(path) != reference
        or path.parts[:2] != ("staging", "agents")
        or len(path.parts) != 4
        or path.parts[3] != BUILD_TASK_FILENAME
        or not VALID_ID_PATTERN.fullmatch(path.parts[2])
    ):
        raise BuildResultConsumptionError(
            "artifact_reference must be the canonical staged BUILD_TASK.json reference"
        )
    return reference


def _changed_path_is_allowed(path_text: str, task: AgentBuildTask) -> None:
    if (
        not path_text
        or len(path_text) > _MAX_PATH_CHARS
        or "\x00" in path_text
        or "\\" in path_text
        or any(character in path_text for character in "*?[]")
    ):
        raise BuildResultValidationError(f"changed_files contains unsafe path: {path_text!r}")
    path = PurePosixPath(path_text)
    if (
        str(path) != path_text
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or len(path.parts) <= 3
        or path.parts[:3] != tuple(task.staging_target.split("/"))
        or path_text.rsplit("/", 1)[-1] in _CONTROL_ARTIFACTS
        or any(part == "secrets" or part == ".env" or part.startswith(".env.") for part in path.parts)
    ):
        raise BuildResultValidationError(f"changed_files contains unsafe or out-of-scope path: {path_text!r}")
    allowed = False
    for permitted in task.permitted_paths:
        base = permitted.removesuffix("/**")
        if path_text == base or path_text.startswith(base + "/"):
            allowed = True
            break
    if not allowed:
        raise BuildResultValidationError(
            f"changed_files path is outside permitted_paths: {path_text!r}"
        )


def _validate_for_task(result: dict[str, Any], task: AgentBuildTask) -> None:
    if result["status"] != "success":
        raise BuildResultConsumptionError(
            f"BuildResult status {result['status']!r} is not promotable"
        )
    if result["validation_evidence"]["validation_passed"] is not True:
        raise BuildResultConsumptionError("BuildResult validation_evidence.validation_passed is not true")
    if result["validation_evidence"]["out_of_scope_paths"]:
        raise BuildResultConsumptionError("BuildResult reports out-of-scope changed paths")
    if result["errors"]:
        raise BuildResultConsumptionError("successful BuildResult contains errors")
    if not result["tests_run"]:
        raise BuildResultConsumptionError("BuildResult must contain at least one ATL-run test or validation item")
    for test in result["tests_run"]:
        if test["status"] != "passed":
            raise BuildResultConsumptionError(
                f"BuildResult contains a {test['status']} test item: {test['command']!r}"
            )
    for required in task.test_commands:
        matching = [test for test in result["tests_run"] if test["command"] == required]
        if not matching or any(test["status"] != "passed" for test in matching):
            raise BuildResultConsumptionError(
                f"required test command was not represented as passed: {required!r}"
            )
    if result["token_usage"]["tokens_total"] > task.token_budget:
        raise BuildResultConsumptionError(
            "BuildResult ATL orchestrator token usage exceeds the AgentBuildTask token budget"
        )
    if result["duration_seconds"] > task.time_budget_seconds:
        raise BuildResultConsumptionError(
            "BuildResult measured coding-agent execution duration exceeds the AgentBuildTask time budget"
        )
    for path_text in result["changed_files"]:
        _changed_path_is_allowed(path_text, task)


def _result_digest(result: dict[str, Any]) -> str:
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _result_reference(task: AgentBuildTask) -> str:
    return f"{task.staging_target}/{BUILD_RESULT_REFERENCE_NAME}"


def _load_task(artifact_path: Path, reference: str) -> AgentBuildTask:
    try:
        task = AgentBuildTask.model_validate(json.loads(artifact_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BuildResultConsumptionError(f"invalid BUILD_TASK.json: {reference}") from exc
    if build_task_reference(task) != reference:
        raise BuildResultConsumptionError("BUILD_TASK.json does not resolve to artifact_reference")
    return task


def _load_persisted_result(path: Path, task: AgentBuildTask, reference: str) -> dict[str, Any]:
    try:
        wrapper = _exact_keys(
            json.loads(path.read_text(encoding="utf-8")),
            {
                "artifact_reference",
                "agent_id",
                "agent_version",
                "correlation_id",
                "factory_thread_id",
                "manifest_sha256",
                "build_result_sha256",
                "build_result",
            },
            "BUILD_RESULT.json",
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BuildResultConsumptionError("persisted BUILD_RESULT.json is invalid") from exc
    if any(
        wrapper[field] != expected
        for field, expected in {
            "artifact_reference": reference,
            "agent_id": task.agent_id,
            "agent_version": task.agent_version,
            "correlation_id": task.correlation_id,
            "manifest_sha256": task.manifest_sha256,
        }.items()
    ):
        raise BuildResultConsumptionError("persisted BUILD_RESULT.json identity is invalid")
    persisted = _parse_wire_result(wrapper["build_result"])
    if wrapper["build_result_sha256"] != _result_digest(persisted):
        raise BuildResultConsumptionError("persisted BUILD_RESULT.json digest is invalid")
    return persisted


def _raise_failed(
    message: str,
    *,
    row: dict[str, Any] | None,
    reference: str,
    task: AgentBuildTask | None,
    db_path: Path | None,
) -> None:
    if row and task is not None and row["status"] == "approved":
        from .storage import mark_build_task_status

        mark_build_task_status(
            reference,
            "failed",
            message,
            correlation_id=task.correlation_id,
            thread_id=task.thread_id,
            db_path=db_path,
        )
    raise BuildResultConsumptionError(message)


def consume_agent_build_result(
    thread_id: str,
    artifact_reference: str,
    build_result: dict[str, Any],
    *,
    project_root: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Consume one ATL BuildResult under the exact approved Factory task.

    v1 enforces the AgentBuildTask token budget against metered ATL
    orchestrator usage.  Coding-backend token/cost usage remains explicitly
    unavailable when the backend exposes no measurements; it is never treated
    as zero or as proof that a total backend budget was met.  The time budget
    covers the measured coding-agent execution duration.
    """

    if type(thread_id) is not str or not thread_id.strip():
        raise BuildResultConsumptionError("thread_id must be a non-empty string")
    thread_id = thread_id.strip()
    reference = _canonical_reference(artifact_reference)
    root = (project_root or Path(__file__).parents[2]).resolve()
    artifact_path = (root / PurePosixPath(reference)).resolve()
    try:
        artifact_path.relative_to(root)
    except ValueError as exc:
        raise BuildResultConsumptionError("artifact_reference resolves outside project_root") from exc

    from .storage import get_build_task

    task: AgentBuildTask | None = None
    row: dict[str, Any] | None = None
    try:
        task = _load_task(artifact_path, reference)
        if task.thread_id != thread_id:
            raise BuildResultConsumptionError("BuildResult thread does not match BUILD_TASK thread")
        row = get_build_task(
            reference,
            correlation_id=task.correlation_id,
            thread_id=thread_id,
            db_path=db_path,
        )
        if row is None:
            raise BuildResultConsumptionError("exact approved build task is missing")
        task_identity = {
            "thread_id": task.thread_id,
            "artifact_reference": build_task_reference(task),
            "correlation_id": task.correlation_id,
            "agent_id": task.agent_id,
            "agent_version": task.agent_version,
            "manifest_sha256": task.manifest_sha256,
        }
        if any(row[field] != expected for field, expected in task_identity.items()):
            raise BuildResultConsumptionError("build-task storage does not match BUILD_TASK.json")
        assert_task_matches_staged_package(task, root)
        if row["status"] == "validated":
            persisted = _load_persisted_result(root / PurePosixPath(_result_reference(task)), task, reference)
            incoming = _parse_wire_result(build_result)
            if incoming == persisted:
                return {
                    "status": "validated",
                    "thread_id": thread_id,
                    "correlation_id": task.correlation_id,
                    "agent_id": task.agent_id,
                    "artifact_reference": reference,
                    "build_result_reference": _result_reference(task),
                }
            raise BuildResultConsumptionError(
                "a different BuildResult was supplied for an already-validated correlation"
            )
        if row["status"] != "approved":
            raise BuildResultConsumptionError(
                f"build task is not approved for consumption (status={row['status']!r})"
            )
        parsed = _parse_wire_result(build_result)
        _validate_for_task(parsed, task)
        # The returned evidence is accepted only against the package that is
        # still staged after the implementation completed.
        assert_task_matches_staged_package(task, root)
    except BuildResultConsumptionError as exc:
        if row and task is not None and row["status"] == "approved":
            _raise_failed(str(exc), row=row, reference=reference, task=task, db_path=db_path)
        raise
    except (BuildTaskError, OSError, ValueError) as exc:
        message = str(exc)
        if row and task is not None and row["status"] == "approved":
            _raise_failed(message, row=row, reference=reference, task=task, db_path=db_path)
        raise BuildResultConsumptionError(message) from exc

    result_path = root / PurePosixPath(_result_reference(task))
    canonical = {
        "artifact_reference": reference,
        "agent_id": task.agent_id,
        "agent_version": task.agent_version,
        "correlation_id": task.correlation_id,
        "factory_thread_id": thread_id,
        "manifest_sha256": task.manifest_sha256,
        "build_result_sha256": _result_digest(parsed),
        "build_result": parsed,
    }
    try:
        result_path.write_text(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        from .storage import mark_build_task_status

        if not mark_build_task_status(
            reference,
            "validated",
            "BuildResult v1 validated by Factory.",
            correlation_id=task.correlation_id,
            thread_id=thread_id,
            db_path=db_path,
        ):
            raise BuildResultConsumptionError("validated build-task state was not applied atomically")
    except (OSError, ValueError, BuildTaskError) as exc:
        raise BuildResultConsumptionError(f"could not persist validated BuildResult: {exc}") from exc
    return {
        "status": "validated",
        "thread_id": thread_id,
        "correlation_id": task.correlation_id,
        "agent_id": task.agent_id,
        "artifact_reference": reference,
        "build_result_reference": _result_reference(task),
    }
