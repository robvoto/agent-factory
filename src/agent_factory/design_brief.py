"""Structured design brief used before AgentPackageSpec creation.

The Factory Brain uses this schema during the design interview so it can stop
and ask the operator instead of inventing missing agent behaviour.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

RuntimePattern = Literal[
    "deterministic_workflow",
    "simple_tool_agent",
    "deep_agent",
]


class AgentDesignBrief(BaseModel):
    """Human-reviewed agent design decisions required before staging."""

    goal: str
    primary_user: str
    inputs: list[str]
    outputs: list[str]
    responsibilities: list[str]
    non_responsibilities: list[str]
    tools_integrations: list[str] = Field(default_factory=list)
    human_decisions: list[str] = Field(default_factory=list)
    ambiguity_policy: str
    canonical_artifact: str | None = None
    manual_editing_required: bool = False
    source_of_truth_after_manual_edit: str | None = None
    runtime_pattern: RuntimePattern
    runtime_reason: str
    open_questions: list[str] = Field(default_factory=list)

    @field_validator(
        "goal",
        "primary_user",
        "ambiguity_policy",
        "runtime_reason",
    )
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("value must not be empty")
        return clean

    @field_validator(
        "inputs",
        "outputs",
        "responsibilities",
        "non_responsibilities",
    )
    @classmethod
    def require_non_empty_list(cls, values: list[str]) -> list[str]:
        clean = [value.strip() for value in values if value.strip()]
        if not clean:
            raise ValueError("at least one value is required")
        if len(clean) != len(values):
            raise ValueError("values must not contain empty strings")
        return clean

    @field_validator("tools_integrations", "human_decisions", "open_questions")
    @classmethod
    def normalize_optional_lists(cls, values: list[str]) -> list[str]:
        clean = [value.strip() for value in values if value.strip()]
        if len(clean) != len(values):
            raise ValueError("values must not contain empty strings")
        return clean

    @model_validator(mode="after")
    def validate_manual_edit_source_of_truth(self) -> "AgentDesignBrief":
        if self.manual_editing_required and not (
            self.source_of_truth_after_manual_edit
            and self.source_of_truth_after_manual_edit.strip()
        ):
            raise ValueError(
                "source_of_truth_after_manual_edit is required when manual_editing_required=true"
            )
        return self

    @property
    def ready_for_spec(self) -> bool:
        """A design is ready only when no unresolved operator questions remain."""
        return not self.open_questions

    def readiness_summary(self) -> str:
        if self.ready_for_spec:
            return "Design brief is complete and ready for AgentPackageSpec drafting."
        questions = "\n".join(f"- {question}" for question in self.open_questions)
        return (
            "Design brief is not ready. Resolve these questions with the operator before "
            f"drafting AgentPackageSpec:\n{questions}"
        )
