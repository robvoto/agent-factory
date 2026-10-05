"""Deterministic validation for structured specialist result extensions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError, field_validator


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
