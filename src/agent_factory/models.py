"""Agent manifest models and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent_spec import (
    AgentTargetProjectAccess,
    AgentTaskContract,
    normalize_output_contract,
    normalize_runtime_config,
)
from .specialist_contract import SpecialistInputContract, SpecialistInteractionContract
from .project_context import ProjectContextContract
from .errors import ManifestValidationError
from .routing_purpose import validate_routing_purpose


REQUIRED_FIELDS = {"id", "name", "purpose", "aliases", "tools", "permissions", "memory", "runtime"}


@dataclass(frozen=True)
class AgentManifest:
    """Validated agent manifest used by the factory."""

    id: str
    name: str
    purpose: str
    aliases: tuple[str, ...]
    tools: tuple[str, ...]
    permissions: dict[str, Any]
    memory: dict[str, Any]
    runtime: dict[str, Any] = None  # type: ignore[assignment]
    input_contract: dict[str, Any] | None = None
    interaction_contract: dict[str, Any] | None = None
    task_contract: dict[str, Any] | None = None
    project_context_contract: dict[str, Any] | None = None
    target_project_access: dict[str, Any] | None = None
    output_contract: dict[str, Any] | None = None
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
        try:
            purpose = validate_routing_purpose(_required_string(data["purpose"], "purpose"))
        except ValueError as exc:
            raise ManifestValidationError(str(exc)) from exc
        aliases = _string_list(data["aliases"], "aliases", allow_empty=False)
        tools = _string_list(data["tools"], "tools", allow_empty=True)

        normalized_aliases = tuple(alias.strip().lower() for alias in aliases)
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise ManifestValidationError("Manifest contains duplicate aliases.")

        if not isinstance(data["permissions"], dict):
            raise ManifestValidationError("permissions must be an object.")
        if not isinstance(data["memory"], dict):
            raise ManifestValidationError("memory must be an object.")

        runtime = data["runtime"]
        if not isinstance(runtime, dict):
            raise ManifestValidationError("runtime must be an object.")
        input_contract = data.get("input_contract")
        interaction_contract = data.get("interaction_contract")
        task_contract = data.get("task_contract")
        project_context_contract = data.get("project_context_contract")
        target_project_access = data.get("target_project_access")
        output_contract = data.get("output_contract")
        if input_contract is not None and not isinstance(input_contract, dict):
            raise ManifestValidationError("input_contract must be an object when present.")
        if interaction_contract is not None and not isinstance(interaction_contract, dict):
            raise ManifestValidationError("interaction_contract must be an object when present.")
        if task_contract is not None and not isinstance(task_contract, dict):
            raise ManifestValidationError("task_contract must be an object when present.")
        if project_context_contract is not None and not isinstance(project_context_contract, dict):
            raise ManifestValidationError("project_context_contract must be an object when present.")
        if target_project_access is not None and not isinstance(target_project_access, dict):
            raise ManifestValidationError("target_project_access must be an object when present.")
        if output_contract is not None and not isinstance(output_contract, dict):
            raise ManifestValidationError("output_contract must be an object when present.")

        try:
            normalized_runtime = normalize_runtime_config(agent_id, runtime)
            normalized_input_contract = (
                SpecialistInputContract.model_validate(input_contract).model_dump()
                if input_contract is not None
                else None
            )
            normalized_interaction_contract = (
                SpecialistInteractionContract.model_validate(interaction_contract).model_dump()
                if interaction_contract is not None
                else None
            )
            normalized_task_contract = (
                AgentTaskContract.model_validate(task_contract).model_dump(exclude_none=True)
                if task_contract is not None
                else None
            )
            normalized_project_context_contract = (
                ProjectContextContract.model_validate(project_context_contract).model_dump()
                if project_context_contract is not None
                else None
            )
            normalized_target_project_access = (
                AgentTargetProjectAccess.model_validate(target_project_access).model_dump(
                    exclude_none=True
                )
                if target_project_access is not None
                else None
            )
            normalized_output_contract = normalize_output_contract(
                agent_id,
                normalized_runtime["mode"],
                output_contract,
            )
        except ValueError as exc:
            raise ManifestValidationError(str(exc)) from exc

        return cls(
            id=agent_id,
            name=name,
            purpose=purpose,
            aliases=normalized_aliases,
            tools=tuple(tool.strip() for tool in tools),
            permissions=dict(data["permissions"]),
            memory=dict(data["memory"]),
            runtime=normalized_runtime,
            input_contract=normalized_input_contract,
            interaction_contract=normalized_interaction_contract,
            task_contract=normalized_task_contract,
            project_context_contract=normalized_project_context_contract,
            target_project_access=normalized_target_project_access,
            output_contract=normalized_output_contract,
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
