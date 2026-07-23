from __future__ import annotations

import pytest

from agent_factory.specialist_contract import (
    SpecialistInputContract,
    SpecialistInteractionContract,
    validate_universal_task_envelope,
)


def test_default_contract_accepts_universal_context_without_interpreting_it() -> None:
    payload = {
        "task": "Review REF-123",
        "request_id": "req-1",
        "context": {
            "selected_project": {"project_key": "example"},
            "user_supplied_references": [
                {"reference": "REF-123", "source": "user_request"}
            ],
        },
    }

    result = validate_universal_task_envelope(payload)

    assert result["task"] == "Review REF-123"
    assert result["context"] == payload["context"]


def test_contract_rejects_unknown_context_instead_of_guessing() -> None:
    with pytest.raises(ValueError, match="Unsupported universal context fields"):
        validate_universal_task_envelope(
            {"task": "Review something", "context": {"backlog_reference": {}}}
        )


def test_manifest_contract_is_versioned() -> None:
    contract = SpecialistInputContract()
    assert contract.protocol == "agent-hub.task"
    assert contract.protocol_version == 1
    assert contract.required_fields == ["task"]


def test_resume_requires_clarification_or_approval() -> None:
    with pytest.raises(ValueError, match="resume requires"):
        SpecialistInteractionContract(
            clarification=False,
            approval=False,
            resume=True,
        )
