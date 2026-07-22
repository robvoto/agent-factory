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
            "purpose": "Alpha does the alpha work.",
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
                "purpose": "Alpha does the alpha work.",
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
                "purpose": "Alpha does the alpha work.",
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
            "purpose": "Alpha does the alpha work.",
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
