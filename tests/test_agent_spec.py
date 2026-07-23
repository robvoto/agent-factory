from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_factory.agent_spec import AgentPackageSpec


def _subprocess_output_contract() -> dict:
    return {
        "status_values": [
            "success",
            "needs_clarification",
            "approval_required",
            "failed",
        ],
        "status_contract": {
            "success": {"terminal": True, "caller_action": "consume_result"},
            "needs_clarification": {
                "terminal": False,
                "caller_action": "provide_clarification",
            },
            "approval_required": {
                "terminal": False,
                "caller_action": "provide_approval",
            },
            "failed": {"terminal": True, "caller_action": "inspect_failure"},
        },
    }


def test_agent_package_spec_defaults_to_manual_runtime() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "alpha-agent",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
        }
    )

    assert spec.runtime.mode == "manual"
    assert spec.output_contract is None


def test_subprocess_runtime_requires_output_contract() -> None:
    with pytest.raises(ValidationError):
        AgentPackageSpec.model_validate(
            {
                "id": "alpha-agent",
                "name": "Alpha Agent",
                "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
                "aliases": ["alpha"],
                "runtime": {
                    "mode": "subprocess",
                    "entrypoint": "uv run alpha run-agent-task",
                    "working_directory": "/tmp/alpha",
                    "input_arg": "--input-json",
                    "output_arg": "--output-json",
                    "default_execution_mode": "execute",
                },
            }
        )


def test_subprocess_runtime_validates_status_contract() -> None:
    with pytest.raises(ValidationError):
        AgentPackageSpec.model_validate(
            {
                "id": "alpha-agent",
                "name": "Alpha Agent",
                "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
                "aliases": ["alpha"],
                "runtime": {
                    "mode": "subprocess",
                    "entrypoint": "uv run alpha run-agent-task",
                    "working_directory": "/tmp/alpha",
                    "input_arg": "--input-json",
                    "output_arg": "--output-json",
                    "default_execution_mode": "execute",
                },
                "output_contract": {
                    "status_values": [
                        "success",
                        "needs_clarification",
                        "approval_required",
                    ],
                    "status_contract": {
                        "success": {"terminal": True, "caller_action": "consume_result"},
                        "needs_clarification": {
                            "terminal": False,
                            "caller_action": "provide_clarification",
                        },
                        "approval_required": {
                            "terminal": False,
                            "caller_action": "provide_approval",
                        },
                    },
                },
            }
        )


def test_subprocess_runtime_accepts_valid_output_contract() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "alpha-agent",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
            "runtime": {
                "mode": "subprocess",
                "entrypoint": "uv run alpha run-agent-task",
                "working_directory": "/tmp/alpha",
                "input_arg": "--input-json",
                "output_arg": "--output-json",
                "default_execution_mode": "execute",
            },
            "output_contract": _subprocess_output_contract(),
        }
    )

    assert spec.runtime.mode == "subprocess"
    assert spec.output_contract is not None
    assert spec.output_contract.status_values == [
        "success",
        "needs_clarification",
        "approval_required",
        "failed",
    ]

def test_agent_package_spec_rejects_vague_one_sentence_purpose() -> None:
    with pytest.raises(ValidationError, match="exactly three routing sections"):
        AgentPackageSpec.model_validate(
            {
                "id": "vague-agent",
                "name": "Vague Agent",
                "purpose": "Handles useful work.",
                "aliases": ["vague"],
            }
        )


def test_agent_package_spec_normalizes_structured_routing_purpose() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "routing-agent",
            "name": "Routing Agent",
            "purpose": (
                "Primary responsibility:   Review routing decisions.\n"
                "Select for: Requests requiring specialist-routing review.\n"
                "Do not select for: Implementing unrelated application features."
            ),
            "aliases": ["routing"],
        }
    )

    assert spec.purpose == (
        "Primary responsibility: Review routing decisions.\n"
        "Select for: Requests requiring specialist-routing review.\n"
        "Do not select for: Implementing unrelated application features."
    )


def test_agent_package_spec_defaults_to_universal_hub_contract() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "universal-agent",
            "name": "Universal Agent",
            "purpose": "Primary responsibility: Perform universal work.\nSelect for: Requests that require universal work.\nDo not select for: Requests unrelated to universal work.",
            "aliases": ["universal"],
        }
    )

    assert spec.input_contract.protocol == "agent-hub.task"
    assert spec.input_contract.protocol_version == 1
    assert spec.interaction_contract.clarification is True
    assert spec.interaction_contract.cancellation is True


def test_agent_package_spec_accepts_specialist_owned_extensions() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "widget-forge",
            "name": "Widget Forge",
            "purpose": (
                "Primary responsibility: Forge widgets.\n"
                "Select for: Requests to forge a widget.\n"
                "Do not select for: Anything else."
            ),
            "aliases": ["widgets"],
            "extensions": {"backlog_sheet_id": "some-sheet-id"},
        }
    )

    assert spec.extensions == {"backlog_sheet_id": "some-sheet-id"}


def test_agent_package_spec_rejects_extensions_that_shadow_core_fields() -> None:
    with pytest.raises(ValidationError):
        AgentPackageSpec.model_validate(
            {
                "id": "widget-forge",
                "name": "Widget Forge",
                "purpose": (
                    "Primary responsibility: Forge widgets.\n"
                    "Select for: Requests to forge a widget.\n"
                    "Do not select for: Anything else."
                ),
                "aliases": ["widgets"],
                "extensions": {"runtime": {"mode": "manual"}},
            }
        )
