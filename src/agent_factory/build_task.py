"""Strict, Factory-owned implementation handoff artifacts.

The build task is a bounded handoff contract.  It is not an execution plan
for Factory and it is not promotion evidence.  The staged package remains the
source of truth until a separate promotion approval releases it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .agent_spec import SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS, VALID_ID_PATTERN
from .models import AgentManifest

BUILD_TASK_SCHEMA_VERSION = 1
BUILD_TASK_FILENAME = "BUILD_TASK.json"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class BuildTaskError(ValueError):
    """A build-task boundary or staged-package check failed closed."""


class AgentBuildTask(BaseModel):
    """Versioned, minimal contract for an approved implementation handoff."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = BUILD_TASK_SCHEMA_VERSION
    agent_id: StrictStr
    agent_version: StrictStr
    manifest_schema_version: StrictInt
    manifest_sha256: StrictStr
    staging_target: StrictStr
    permitted_paths: list[StrictStr]
    acceptance_criteria: list[StrictStr]
    test_commands: list[StrictStr]
    relevant_docs: list[StrictStr]
    relevant_skills: list[StrictStr]
    token_budget: StrictInt
    time_budget_seconds: StrictInt
    stop_conditions: list[StrictStr]
    runtime_pattern: Literal["deterministic_workflow", "simple_agent", "deep_agent"]
    runtime_pattern_reason: StrictStr
    thread_id: StrictStr
    correlation_id: StrictStr

    @field_validator(
        "agent_id",
        "agent_version",
        "manifest_sha256",
        "staging_target",
        "runtime_pattern_reason",
        "thread_id",
        "correlation_id",
    )
    @classmethod
    def non_empty_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must be a non-empty string")
        return normalized

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        if not VALID_ID_PATTERN.fullmatch(value.strip()):
            raise ValueError("agent_id must be a normalized kebab-case identifier")
        return value.strip()

    @field_validator(
        "permitted_paths",
        "acceptance_criteria",
        "test_commands",
        "relevant_docs",
        "relevant_skills",
        "stop_conditions",
    )
    @classmethod
    def non_empty_string_list(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("must contain at least one item")
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("must contain only non-empty strings")
        if len(set(normalized)) != len(normalized):
            raise ValueError("must not contain duplicates")
        return normalized

    @field_validator("manifest_sha256")
    @classmethod
    def validate_manifest_hash(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value

    @field_validator("manifest_schema_version")
    @classmethod
    def validate_manifest_schema_version(cls, value: int) -> int:
        if value not in SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS:
            raise ValueError(f"unsupported manifest schema version: {value}")
        return value

    @field_validator("token_budget", "time_budget_seconds")
    @classmethod
    def validate_positive_budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_paths_and_identity(self) -> AgentBuildTask:
        expected_target = f"staging/agents/{self.agent_id}"
        if self.staging_target != expected_target:
            raise ValueError(
                "staging_target must identify the agent's staged package: "
                f"{expected_target!r}"
            )
        for value in self.permitted_paths:
            _validate_repo_relative_path(value, "permitted_paths")
            if not value.startswith(f"{self.staging_target}/"):
                raise ValueError(
                    "permitted_paths must remain inside staging_target: " + value
                )
            if value == f"{self.staging_target}/{BUILD_TASK_FILENAME}":
                raise ValueError("permitted_paths must not include the Factory control artifact")
        for value in self.relevant_docs:
            _validate_repo_relative_path(value, "relevant_docs")
            if not _is_allowed_reference(value, self.staging_target, "docs"):
                raise ValueError(
                    "relevant_docs must reference docs/ or the exact staged package docs/: "
                    + value
                )
        for value in self.relevant_skills:
            _validate_repo_relative_path(value, "relevant_skills")
            if not _is_allowed_reference(value, self.staging_target, "skills"):
                raise ValueError(
                    "relevant_skills must reference skills/ or the exact staged package skills/: "
                    + value
                )
        return self


def _validate_repo_relative_path(value: str, field_name: str) -> None:
    if "\x00" in value or "\\" in value:
        raise ValueError(f"{field_name} contains an invalid path: {value!r}")
    path = PurePosixPath(value)
    if str(path) != value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"{field_name} must be a normalized repo-relative path: {value!r}")
    if any(part == "secrets" or part == ".env" or part.startswith(".env.") for part in path.parts):
        raise ValueError(f"{field_name} must not reference secret paths: {value!r}")


def _is_allowed_reference(value: str, staging_target: str, namespace: str) -> bool:
    return value.startswith((f"{namespace}/", f"{staging_target}/{namespace}/"))


def manifest_sha256(manifest_path: Path) -> str:
    """Hash the exact staged manifest bytes used to prepare a task."""

    try:
        return hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BuildTaskError(f"Unable to read staged manifest: {manifest_path}") from exc


def load_staged_manifest(package_dir: Path, expected_agent_id: str) -> tuple[dict[str, Any], AgentManifest, str]:
    """Read and validate the staged manifest without inferring missing design data."""

    manifest_path = package_dir / "agent.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildTaskError(f"Unable to read staged agent manifest: {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise BuildTaskError("staged agent.json must be a JSON object")
    try:
        manifest = AgentManifest.from_dict(raw, source=manifest_path)
    except Exception as exc:
        raise BuildTaskError(f"Invalid staged agent manifest: {exc}") from exc
    if manifest.id != expected_agent_id:
        raise BuildTaskError(
            f"staged manifest id {manifest.id!r} does not match requested agent {expected_agent_id!r}"
        )
    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise BuildTaskError("staged agent.json must declare a non-empty version")
    design = raw.get("design")
    if not isinstance(design, dict):
        raise BuildTaskError("staged agent.json must declare design.runtime_pattern and reason")
    runtime_pattern = design.get("runtime_pattern")
    runtime_reason = design.get("runtime_pattern_reason")
    if not isinstance(runtime_pattern, str) or not runtime_pattern.strip():
        raise BuildTaskError("staged design.runtime_pattern is missing")
    if not isinstance(runtime_reason, str) or not runtime_reason.strip():
        raise BuildTaskError("staged design.runtime_pattern_reason is missing")
    schema_version = raw.get("manifest_schema_version")
    if schema_version not in SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS:
        raise BuildTaskError(f"unsupported staged manifest_schema_version: {schema_version!r}")
    return raw, manifest, manifest_sha256(manifest_path)


def assert_task_matches_staged_package(task: AgentBuildTask, project_root: Path) -> None:
    """Fail closed if the approved task no longer describes its staged package."""

    package_dir = (project_root / task.staging_target).resolve()
    staging_root = (project_root / "staging" / "agents").resolve()
    try:
        package_dir.relative_to(staging_root)
    except ValueError as exc:
        raise BuildTaskError("build task staging target is outside staging/agents") from exc
    if not package_dir.is_dir():
        raise BuildTaskError(f"staged package is missing: {task.staging_target}")
    raw, manifest, digest = load_staged_manifest(package_dir, task.agent_id)
    design = raw["design"]
    expected_correlation_id = build_task_correlation_id(task)
    if (
        manifest.id != task.agent_id
        or raw.get("version") != task.agent_version
        or raw.get("manifest_schema_version") != task.manifest_schema_version
        or digest != task.manifest_sha256
        or task.correlation_id != expected_correlation_id
        or design.get("runtime_pattern") != task.runtime_pattern
        or design.get("runtime_pattern_reason") != task.runtime_pattern_reason
    ):
        raise BuildTaskError(
            f"build task for {task.agent_id!r} is stale versus staged agent.json; regenerate and reapprove it"
        )


def build_task_reference(task: AgentBuildTask) -> str:
    """Return the stable repo-relative reference consumed by a later adapter."""

    return f"{task.staging_target}/{BUILD_TASK_FILENAME}"


def canonical_task_payload(values: dict[str, Any]) -> str:
    """Canonicalize explicit tool inputs for deterministic correlation IDs."""

    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_correlation_id(thread_id: str, values: dict[str, Any]) -> str:
    return hashlib.sha256(f"{thread_id}:{canonical_task_payload(values)}".encode()).hexdigest()[:32]


def build_task_correlation_id(task: AgentBuildTask) -> str:
    """Recompute the correlation from every caller-controlled task field."""

    return deterministic_correlation_id(
        task.thread_id,
        {
            "agent_id": task.agent_id,
            "permitted_paths": task.permitted_paths,
            "acceptance_criteria": task.acceptance_criteria,
            "test_commands": task.test_commands,
            "relevant_docs": task.relevant_docs,
            "relevant_skills": task.relevant_skills,
            "token_budget": task.token_budget,
            "time_budget_seconds": task.time_budget_seconds,
            "stop_conditions": task.stop_conditions,
            "manifest_sha256": task.manifest_sha256,
        },
    )
