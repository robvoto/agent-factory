"""Validated agent package specification for the Factory Brain.

Stage 3: structured spec with Pydantic validation before any files are written.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar, Literal, Mapping

from pydantic import BaseModel, Field, field_validator, model_validator

from .routing_purpose import validate_routing_purpose
from .specialist_contract import (
    SpecialistInputContract,
    SpecialistInteractionContract,
)

VALID_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
SUPPORTED_RUNTIME_MODES = {"manual", "subprocess", "factory_brain"}
AGENT_MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS = {1}
SUBPROCESS_OUTPUT_STATUS_VALUES = (
    "success",
    "needs_clarification",
    "approval_required",
    "failed",
)
SUBPROCESS_STATUS_TERMINAL = {
    "success": True,
    "needs_clarification": False,
    "approval_required": False,
    "failed": True,
}


class AgentPermissions(BaseModel):
    network: bool = False
    filesystem: str = "none"  # "none", "read", or "write"
    shell: bool = False
    requires_approval: bool = True

    def risk_flags(self) -> list[str]:
        flags: list[str] = []
        if self.network:
            flags.append("network")
        if self.filesystem == "write":
            flags.append("filesystem_write")
        if self.shell:
            flags.append("shell")
        return flags


class AgentMemoryPolicy(BaseModel):
    scope: str = "none"
    retention: str = "none"


class AgentProgressConfig(BaseModel):
    enabled: bool = False
    hub_callable: bool = False
    long_running: bool = False
    adapter: Literal[
        "deterministic_workflow",
        "simple_agent",
        "deep_agent",
    ] | None = None
    schema_version: int = 1
    transport: Literal["stdout_jsonl"] = "stdout_jsonl"

    @model_validator(mode="after")
    def validate_enabled_progress(self) -> "AgentProgressConfig":
        if not self.enabled:
            return self
        if not (self.hub_callable or self.long_running):
            raise ValueError(
                "Enabled progress requires hub_callable=true or long_running=true."
            )
        if self.adapter is None:
            raise ValueError(
                "Enabled progress requires an adapter: deterministic_workflow, "
                "simple_agent, or deep_agent."
            )
        if self.schema_version != 1:
            raise ValueError("Only SpecialistProgressEvent schema_version=1 is supported.")
        return self


class AgentRuntimeConfig(BaseModel):
    mode: str = "manual"
    entrypoint: str | None = None
    working_directory: str | None = None
    input_arg: str | None = None
    output_arg: str | None = None
    default_execution_mode: str | None = None
    manifest_command: str | None = None
    progress: AgentProgressConfig | None = None
    notes: str | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in SUPPORTED_RUNTIME_MODES:
            raise ValueError(
                f"Unsupported runtime.mode {v!r}. "
                f"Supported modes: {sorted(SUPPORTED_RUNTIME_MODES)}."
            )
        return v

    @model_validator(mode="after")
    def validate_mode_specific_fields(self) -> "AgentRuntimeConfig":
        if self.progress is not None and self.progress.enabled and self.mode != "subprocess":
            raise ValueError(
                "Enabled progress is supported only for subprocess agents."
            )

        if self.mode == "manual":
            return self

        if self.mode == "subprocess":
            _require_non_empty_runtime_fields(
                self,
                "entrypoint",
                "working_directory",
                "input_arg",
                "output_arg",
                "default_execution_mode",
            )
            if self.default_execution_mode not in {"instruction_only", "execute"}:
                raise ValueError(
                    "runtime.default_execution_mode must be 'instruction_only' or 'execute' "
                    f"for subprocess agents. Got: {self.default_execution_mode!r}"
                )
            return self

        if self.mode == "factory_brain":
            _require_non_empty_runtime_fields(
                self,
                "working_directory",
                "manifest_command",
            )
        return self


class AgentStatusMeaning(BaseModel):
    terminal: bool
    caller_action: str
    notes: str | None = None

    @field_validator("caller_action")
    @classmethod
    def validate_caller_action(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("status_contract caller_action values must be non-empty strings.")
        return v.strip()


class AgentOutputContract(BaseModel):
    status_values: list[str]
    status_contract: dict[str, AgentStatusMeaning]

    @field_validator("status_values")
    @classmethod
    def validate_status_values(cls, v: list[str]) -> list[str]:
        normalized = [status.strip() for status in v if status.strip()]
        if len(normalized) != len(v):
            raise ValueError("output_contract.status_values must contain only non-empty strings.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("output_contract.status_values must not contain duplicates.")
        expected = set(SUBPROCESS_OUTPUT_STATUS_VALUES)
        if set(normalized) != expected:
            raise ValueError(
                "output_contract.status_values must contain exactly: "
                f"{list(SUBPROCESS_OUTPUT_STATUS_VALUES)}."
            )
        return list(SUBPROCESS_OUTPUT_STATUS_VALUES)

    @model_validator(mode="after")
    def validate_status_contract(self) -> "AgentOutputContract":
        expected = set(SUBPROCESS_OUTPUT_STATUS_VALUES)
        if set(self.status_contract) != expected:
            raise ValueError(
                "output_contract.status_contract must define exactly these statuses: "
                f"{list(SUBPROCESS_OUTPUT_STATUS_VALUES)}."
            )
        for status, expected_terminal in SUBPROCESS_STATUS_TERMINAL.items():
            actual = self.status_contract[status].terminal
            if actual != expected_terminal:
                raise ValueError(
                    f"output_contract.status_contract[{status!r}].terminal must be "
                    f"{expected_terminal!r}. Got: {actual!r}"
                )
        return self


class McpServer(BaseModel):
    name: str
    description: str = ""
    required: bool = True


class AgentPackageSpec(BaseModel):
    id: str
    version: str = "1.0.0"
    manifest_schema_version: int = AGENT_MANIFEST_SCHEMA_VERSION
    name: str
    purpose: str
    aliases: list[str]
    tools: list[str] = []
    mcp_servers: list[McpServer] = []
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    memory_policy: AgentMemoryPolicy = Field(default_factory=AgentMemoryPolicy)
    runtime: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    input_contract: SpecialistInputContract = Field(default_factory=SpecialistInputContract)
    interaction_contract: SpecialistInteractionContract = Field(
        default_factory=SpecialistInteractionContract
    )
    output_contract: AgentOutputContract | None = None
    risks: list[str] = []
    tests: list[str] = []
    # Specialist-owned manifest metadata with no universal meaning (e.g. a
    # specialist's own backlog pointer). Written verbatim into agent.json;
    # Factory and Hub never interpret its contents.
    extensions: dict[str, Any] = Field(default_factory=dict)

    _CORE_MANIFEST_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "id",
            "manifest_schema_version",
            "name",
            "purpose",
            "aliases",
            "tools",
            "mcp_servers",
            "permissions",
            "memory",
            "runtime",
            "input_contract",
            "interaction_contract",
            "output_contract",
        }
    )

    @field_validator("extensions")
    @classmethod
    def validate_extensions(cls, v: dict[str, Any]) -> dict[str, Any]:
        collisions = sorted(set(v).intersection(cls._CORE_MANIFEST_FIELDS))
        if collisions:
            raise ValueError(
                "extensions must not shadow core manifest fields: " + ", ".join(collisions)
            )
        return v

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not VALID_ID_PATTERN.match(v):
            raise ValueError(
                f"Agent ID must start with a letter, contain only lowercase letters, "
                f"digits, and hyphens, and be at most 64 characters. Got: {v!r}"
            )
        return v

    @field_validator("manifest_schema_version")
    @classmethod
    def validate_manifest_schema_version(cls, v: int) -> int:
        if v not in SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS:
            raise ValueError(
                "Unsupported manifest_schema_version "
                f"{v!r}. Supported versions: {sorted(SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS)}."
            )
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Agent name cannot be empty.")
        if len(v) > 120:
            raise ValueError("Agent name must be 120 characters or less.")
        return v.strip()

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        return validate_routing_purpose(v)

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one alias is required.")
        normalized = [alias.strip().lower() for alias in v if alias.strip()]
        if len(normalized) != len(v):
            raise ValueError("All aliases must be non-empty strings.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate aliases are not allowed.")
        return normalized

    @model_validator(mode="after")
    def auto_flag_risky_permissions(self) -> "AgentPackageSpec":
        for flag in self.permissions.risk_flags():
            if flag not in self.risks:
                self.risks.append(flag)
        if self.mcp_servers:
            if "mcp_servers" not in self.risks:
                self.risks.append("mcp_servers")
        return self

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "AgentPackageSpec":
        if self.runtime.progress is not None and self.runtime.progress.enabled:
            self.interaction_contract.progress = True
        if self.permissions.requires_approval:
            self.interaction_contract.approval = True
        if self.runtime.mode == "subprocess" and self.output_contract is None:
            raise ValueError(
                "Subprocess agents must define output_contract with the staged status contract."
            )
        return self


class DuplicateStagedAgentError(ValueError):
    """Raised when a staged agent with the same ID already exists."""


def validate_not_duplicate(spec: AgentPackageSpec, staged_dir: Path) -> None:
    """Raise DuplicateStagedAgentError if a package with the same ID already exists."""
    if (staged_dir / spec.id).exists():
        raise DuplicateStagedAgentError(
            f"Staged agent package already exists: {spec.id!r}. "
            "Remove or rename it before re-staging."
        )


def normalize_runtime_config(agent_id: str, runtime: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return AgentRuntimeConfig.model_validate(dict(runtime)).model_dump(exclude_none=True)
    except Exception as exc:  # pragma: no cover - exercised through caller-specific tests
        raise ValueError(f"Agent {agent_id!r} has invalid runtime config: {exc}") from exc


def normalize_output_contract(
    agent_id: str,
    runtime_mode: str,
    output_contract: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if runtime_mode == "subprocess" and output_contract is None:
        raise ValueError(
            f"Agent {agent_id!r} uses runtime.mode='subprocess' but has no output_contract."
        )
    if output_contract is None:
        return None
    try:
        return AgentOutputContract.model_validate(dict(output_contract)).model_dump(exclude_none=True)
    except Exception as exc:  # pragma: no cover - exercised through caller-specific tests
        raise ValueError(f"Agent {agent_id!r} has invalid output_contract: {exc}") from exc


def _require_non_empty_runtime_fields(runtime: AgentRuntimeConfig, *fields: str) -> None:
    missing = [
        field
        for field in fields
        if not isinstance(getattr(runtime, field), str) or not str(getattr(runtime, field)).strip()
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"runtime is missing required fields: {joined}.")
