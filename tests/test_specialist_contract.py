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
        "project_root": "/home/robvoto/projects/example",
        "references": ["REF-123"],
    }

    result = validate_universal_task_envelope(payload)

    assert result["task"] == "Review REF-123"
    assert result["project_root"] == payload["project_root"]
    assert result["references"] == payload["references"]


def test_contract_rejects_unknown_fields_instead_of_guessing() -> None:
    with pytest.raises(ValueError, match="Unsupported universal task fields"):
        validate_universal_task_envelope(
            {"task": "Review something", "backlog_reference": {}}
        )


def test_manifest_contract_is_versioned() -> None:
    contract = SpecialistInputContract()
    assert contract.protocol == "agent-hub.task"
    assert contract.protocol_version == 1
    assert contract.required_fields == ["task"]
    assert "project_root" in contract.optional_fields
    assert "references" in contract.optional_fields
    assert "progress_jsonl" in contract.optional_fields


def test_resume_requires_clarification_or_approval() -> None:
    with pytest.raises(ValueError, match="resume requires"):
        SpecialistInteractionContract(
            clarification=False,
            approval=False,
            resume=True,
        )
