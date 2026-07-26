"""Universal Agent Hub-to-specialist contract declarations and validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

UNIVERSAL_TASK_PROTOCOL = "agent-hub.task"
UNIVERSAL_TASK_PROTOCOL_VERSION = 1
UNIVERSAL_CONTEXT_KEYS = (
    "project_root",
    "references",
)


class SpecialistInputContract(BaseModel):
    """Manifest declaration for the stable universal task envelope.

    The envelope is flat — Hub sends the same top-level keys to every
    specialist regardless of which one it is. `project_root` and `references`
    are the two context-carrying fields; a specialist declares which of them
    it actually reads via `accepted_context`, but Hub sends both whenever it
    knows them either way. `required_context` narrows that further to the
    keys the specialist cannot function without — Hub can use it to decide
    whether to ask the user for missing context before dispatching.
    """

    protocol: str = UNIVERSAL_TASK_PROTOCOL
    protocol_version: int = UNIVERSAL_TASK_PROTOCOL_VERSION
    required_fields: list[str] = Field(default_factory=lambda: ["task"])
    optional_fields: list[str] = Field(
        default_factory=lambda: [
            "request_id",
            "run_id",
            "source",
            "execution_mode",
            "progress_jsonl",
            "project_root",
            "references",
            "human_approved",
            "approval_token",
            "resume",
        ]
    )
    accepted_context: list[str] = Field(default_factory=lambda: list(UNIVERSAL_CONTEXT_KEYS))
    required_context: list[str] = Field(default_factory=list)

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
        unknown_context = sorted(set(self.accepted_context).difference(UNIVERSAL_CONTEXT_KEYS))
        if unknown_context:
            raise ValueError(
                "input_contract.accepted_context contains unsupported universal keys: "
                + ", ".join(unknown_context)
            )
        unaccepted_required = sorted(set(self.required_context).difference(self.accepted_context))
        if unaccepted_required:
            raise ValueError(
                "input_contract.required_context must be a subset of accepted_context: "
                + ", ".join(unaccepted_required)
            )
        return self


class SpecialistInteractionContract(BaseModel):
    """Lifecycle behaviours advertised to Agent Hub.

    `resume=True` means this specialist implements *true* checkpoint resume:
    when it pauses for clarification it returns an opaque `resume_token` in
    its output, and Hub replays that token verbatim (via the envelope's
    `resume` field) alongside the clarification reply and the original
    request/run identity and universal context, instead of reconstructing a
    combined task string. This is independent of Hub's reconstructed-task
    fallback, which is always available regardless of this flag — a
    specialist that never sets `resume_token` simply keeps using it.
    """

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
    """Validate and normalize a universal task envelope without interpreting context.

    `project_root` and `references` are passed through unchanged — this
    function does not inspect what they mean, only that they are present
    among the fields the specialist declared it accepts.
    """

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
    return normalized
