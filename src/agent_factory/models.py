"""Agent manifest models and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ManifestValidationError


REQUIRED_FIELDS = {"id", "name", "aliases", "tools", "permissions", "memory"}


@dataclass(frozen=True)
class AgentManifest:
    """Validated agent manifest used by the factory."""

    id: str
    name: str
    aliases: tuple[str, ...]
    tools: tuple[str, ...]
    permissions: dict[str, Any]
    memory: dict[str, Any]
    runtime: dict[str, Any] = None  # type: ignore[assignment]
    source: str | None = None

    def __post_init__(self) -> None:
        if self.runtime is None:
            object.__setattr__(self, "runtime", {})

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str | Path | None = None) -> "AgentManifest":
        if not isinstance(data, dict):
            raise ManifestValidationError("Agent manifest must be a JSON object.")

        missing = sorted(REQUIRED_FIELDS.difference(data))
        if missing:
            raise ManifestValidationError(f"Missing required manifest fields: {', '.join(missing)}")

        agent_id = _required_string(data["id"], "id")
        name = _required_string(data["name"], "name")
        aliases = _string_list(data["aliases"], "aliases", allow_empty=False)
        tools = _string_list(data["tools"], "tools", allow_empty=True)

        normalized_aliases = tuple(alias.strip().lower() for alias in aliases)
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise ManifestValidationError("Manifest contains duplicate aliases.")

        if not isinstance(data["permissions"], dict):
            raise ManifestValidationError("permissions must be an object.")
        if not isinstance(data["memory"], dict):
            raise ManifestValidationError("memory must be an object.")

        runtime = data.get("runtime", {})
        if not isinstance(runtime, dict):
            raise ManifestValidationError("runtime must be an object.")

        return cls(
            id=agent_id,
            name=name,
            aliases=normalized_aliases,
            tools=tuple(tool.strip() for tool in tools),
            permissions=dict(data["permissions"]),
            memory=dict(data["memory"]),
            runtime=dict(runtime),
            source=str(source) if source is not None else None,
        )


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _string_list(value: Any, field_name: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ManifestValidationError(f"{field_name} must be a list of strings.")
    if not allow_empty and not value:
        raise ManifestValidationError(f"{field_name} must contain at least one value.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ManifestValidationError(f"{field_name} must contain only non-empty strings.")
        result.append(item.strip())
    return tuple(result)
