"""Validated agent package specification for the Factory Brain.

Stage 3: structured spec with Pydantic validation before any files are written.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator

VALID_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


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


class McpServer(BaseModel):
    name: str
    description: str = ""
    required: bool = True


class AgentPackageSpec(BaseModel):
    id: str
    version: str = "1.0.0"
    name: str
    purpose: str
    aliases: list[str]
    tools: list[str] = []
    mcp_servers: list[McpServer] = []
    permissions: AgentPermissions = AgentPermissions()
    memory_policy: AgentMemoryPolicy = AgentMemoryPolicy()
    risks: list[str] = []
    tests: list[str] = []

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not VALID_ID_PATTERN.match(v):
            raise ValueError(
                f"Agent ID must start with a letter, contain only lowercase letters, "
                f"digits, and hyphens, and be at most 64 characters. Got: {v!r}"
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
        if not v.strip():
            raise ValueError("Agent purpose cannot be empty.")
        return v.strip()

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


class DuplicateStagedAgentError(ValueError):
    """Raised when a staged agent with the same ID already exists."""


def validate_not_duplicate(spec: AgentPackageSpec, staged_dir: Path) -> None:
    """Raise DuplicateStagedAgentError if a package with the same ID already exists."""
    if (staged_dir / spec.id).exists():
        raise DuplicateStagedAgentError(
            f"Staged agent package already exists: {spec.id!r}. "
            "Remove or rename it before re-staging."
        )
