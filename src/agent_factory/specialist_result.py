"""Deterministic validation for structured specialist result extensions."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from .agent_spec import VALID_ID_PATTERN


class NextTaskContract(BaseModel):
    """Factory-side schema for an explicit optional specialist handoff."""

    model_config = ConfigDict(extra="forbid")

    task_kind: StrictStr
    task: StrictStr
    references: list[StrictStr] | None = None

    @field_validator("task_kind", "task")
    @classmethod
    def require_non_empty_string(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("references", mode="before")
    @classmethod
    def require_list_when_present(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("must be a list of strings when present")  # noqa: TRY004
        return value


class FactorySpecialistResult(BaseModel):
    """Structured Factory boundary for callers that need an optional handoff."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "waiting_approval", "rejected", "failed"]
    summary: StrictStr
    next_task: NextTaskContract | None = None
    artifact_reference: StrictStr | None = None

    @field_validator("summary")
    @classmethod
    def require_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary must be a non-empty string")
        return value

    @model_validator(mode="after")
    def validate_handoff_fields(self) -> FactorySpecialistResult:
        if self.next_task is not None and self.status != "success":
            raise ValueError("next_task is only valid on a successful Factory result")
        if self.artifact_reference is not None:
            if self.status != "success" or self.next_task is None:
                raise ValueError(
                    "artifact_reference requires a successful result with next_task"
                )
            if (
                "\x00" in self.artifact_reference
                or not self.artifact_reference.startswith("staging/agents/")
                or not self.artifact_reference.endswith("/BUILD_TASK.json")
            ):
                raise ValueError(
                    "artifact_reference must be a staged BUILD_TASK.json repo-relative reference"
                )
            path = PurePosixPath(self.artifact_reference)
            if (
                str(path) != self.artifact_reference
                or path.parts[:2] != ("staging", "agents")
                or len(path.parts) != 4
                or path.parts[3] != "BUILD_TASK.json"
                or not VALID_ID_PATTERN.fullmatch(path.parts[2])
            ):
                raise ValueError(
                    "artifact_reference must identify one normalized staged agent BUILD_TASK.json"
                )
        return self


class NextTaskContractError(ValueError):
    """An explicit next_task value violates the Factory producer contract."""


def validate_next_task_contract(value: Any) -> NextTaskContract:
    """Validate one explicit ``next_task`` object without interpreting prose."""

    if not isinstance(value, dict):
        raise NextTaskContractError("next_task must be a JSON object")
    try:
        return NextTaskContract.model_validate(value)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise NextTaskContractError(f"invalid next_task contract: {details}") from exc
