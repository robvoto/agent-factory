"""Universal Agent Hub-to-specialist contract declarations and validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

UNIVERSAL_TASK_PROTOCOL = "agent-hub.task"
UNIVERSAL_TASK_PROTOCOL_VERSION = 1
UNIVERSAL_CONTEXT_KEYS = (
    "selected_project",
    "user_supplied_references",
)


class SpecialistInputContract(BaseModel):
    """Manifest declaration for the stable universal task envelope."""

    protocol: str = UNIVERSAL_TASK_PROTOCOL
    protocol_version: int = UNIVERSAL_TASK_PROTOCOL_VERSION
    required_fields: list[str] = Field(default_factory=lambda: ["task"])
    optional_fields: list[str] = Field(
        default_factory=lambda: [
            "request_id",
            "run_id",
            "source",
            "execution_mode",
            "context",
            "human_approved",
            "approval_token",
            "resume",
        ]
    )
    accepted_context: list[str] = Field(default_factory=lambda: list(UNIVERSAL_CONTEXT_KEYS))

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        if value != UNIVERSAL_TASK_PROTOCOL:
            raise ValueError(f"input_contract.protocol must be {UNIVERSAL_TASK_PROTOCOL!r}.")
        return value

    @field_validator("protocol_version")
    @classmethod
    def validate_protocol_version(cls, value: int) -> int:
        if value != UNIVERSAL_TASK_PROTOCOL_VERSION:
            raise ValueError(
                "Only universal task protocol_version=1 is currently supported."
            )
        return value

    @model_validator(mode="after")
    def validate_fields(self) -> "SpecialistInputContract":
        if self.required_fields != ["task"]:
            raise ValueError("input_contract.required_fields must be exactly ['task'].")
        if "context" not in self.optional_fields:
            raise ValueError("input_contract.optional_fields must include 'context'.")
        unknown = sorted(set(self.accepted_context).difference(UNIVERSAL_CONTEXT_KEYS))
        if unknown:
            raise ValueError(
                "input_contract.accepted_context contains unsupported universal keys: "
                + ", ".join(unknown)
            )
        return self


class SpecialistInteractionContract(BaseModel):
    """Lifecycle behaviours advertised to Agent Hub."""

    progress: bool = False
    clarification: bool = True
    approval: bool = False
    resume: bool = False
    cancellation: bool = True

    @model_validator(mode="after")
    def validate_resume(self) -> "SpecialistInteractionContract":
        if self.resume and not (self.clarification or self.approval):
            raise ValueError(
                "interaction_contract.resume requires clarification or approval support."
            )
        return self


def default_input_contract() -> SpecialistInputContract:
    return SpecialistInputContract()


def default_interaction_contract() -> SpecialistInteractionContract:
    return SpecialistInteractionContract()


def validate_universal_task_envelope(
    payload: dict[str, Any],
    contract: SpecialistInputContract | None = None,
) -> dict[str, Any]:
    """Validate and normalize a universal task envelope without interpreting context."""

    active_contract = contract or default_input_contract()
    if not isinstance(payload, dict):
        raise ValueError("Universal task input must be a JSON object.")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("Universal task input requires a non-empty 'task' string.")

    allowed = set(active_contract.required_fields + active_contract.optional_fields)
    unsupported = sorted(set(payload).difference(allowed))
    if unsupported:
        raise ValueError("Unsupported universal task fields: " + ", ".join(unsupported))

    normalized = dict(payload)
    normalized["task"] = task.strip()
    context = normalized.get("context")
    if context is not None:
        if not isinstance(context, dict):
            raise ValueError("Universal task 'context' must be an object when supplied.")
        unsupported_context = sorted(set(context).difference(active_contract.accepted_context))
        if unsupported_context:
            raise ValueError(
                "Unsupported universal context fields: " + ", ".join(unsupported_context)
            )
        normalized["context"] = dict(context)
    return normalized
