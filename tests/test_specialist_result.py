from __future__ import annotations

import pytest

from agent_factory.specialist_result import (
    NextTaskContractError,
    validate_next_task_contract,
)

SHOPPING_AGENT_NEXT_TASK = {
    "task_kind": "coding_task",
    "task": "Implement the approved Shopping Agent package.",
    "references": ["shopping-agent://approved-design", "AGENT-HUB-054"],
}


def test_shopping_agent_next_task_fixture_is_accepted() -> None:
    result = validate_next_task_contract(SHOPPING_AGENT_NEXT_TASK)

    assert result.model_dump(exclude_none=True) == SHOPPING_AGENT_NEXT_TASK


def test_references_is_optional() -> None:
    result = validate_next_task_contract(
        {
            "task_kind": "coding_task",
            "task": "Implement the approved Shopping Agent package.",
        }
    )

    assert result.references is None


@pytest.mark.parametrize(
    "field",
    [
        "agent_id",
        "status",
        "resume_token",
        "pending_decision",
        "project_root",
        "request_id",
        "run_id",
        "context",
        "metadata",
    ],
)
def test_next_task_rejects_non_contract_fields(field: str) -> None:
    value = {**SHOPPING_AGENT_NEXT_TASK, field: "not part of next_task"}

    with pytest.raises(NextTaskContractError, match="Extra inputs are not permitted"):
        validate_next_task_contract(value)


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"task": "Implement it."},
        {"task_kind": "coding_task"},
        {"task_kind": "", "task": "Implement it."},
        {"task_kind": "coding_task", "task": ""},
        {"task_kind": "coding_task", "task": "Implement it.", "references": None},
        {"task_kind": "coding_task", "task": "Implement it.", "references": "REF-1"},
    ],
)
def test_next_task_rejects_malformed_values(value) -> None:
    with pytest.raises(NextTaskContractError):
        validate_next_task_contract(value)


def test_next_task_does_not_parse_natural_language() -> None:
    with pytest.raises(NextTaskContractError, match="JSON object"):
        validate_next_task_contract("next_task: coding_task — implement it")
