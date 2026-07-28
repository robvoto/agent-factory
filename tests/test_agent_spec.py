from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_factory.agent_spec import AgentPackageSpec


def _subprocess_output_contract() -> dict:
    return {
        "status_values": [
            "success",
            "needs_clarification",
            "waiting_decision",
            "failed",
        ],
        "status_contract": {
            "success": {"terminal": True, "caller_action": "consume_result"},
            "needs_clarification": {
                "terminal": False,
                "caller_action": "provide_clarification",
            },
            "waiting_decision": {
                "terminal": False,
                "caller_action": "provide_decision",
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
                        "waiting_decision",
                    ],
                    "status_contract": {
                        "success": {"terminal": True, "caller_action": "consume_result"},
                        "needs_clarification": {
                            "terminal": False,
                            "caller_action": "provide_clarification",
                        },
                        "waiting_decision": {
                            "terminal": False,
                            "caller_action": "provide_decision",
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
        "waiting_decision",
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


def test_agent_package_spec_defaults_manifest_schema_version() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "universal-agent",
            "name": "Universal Agent",
            "purpose": "Primary responsibility: Perform universal work.\nSelect for: Requests that require universal work.\nDo not select for: Requests unrelated to universal work.",
            "aliases": ["universal"],
        }
    )

    assert spec.manifest_schema_version == 1


def test_agent_package_spec_rejects_unsupported_manifest_schema_version() -> None:
    with pytest.raises(ValidationError, match="Unsupported manifest_schema_version"):
        AgentPackageSpec.model_validate(
            {
                "id": "universal-agent",
                "name": "Universal Agent",
                "purpose": "Primary responsibility: Perform universal work.\nSelect for: Requests that require universal work.\nDo not select for: Requests unrelated to universal work.",
                "aliases": ["universal"],
                "manifest_schema_version": 99,
            }
        )


def test_agent_package_spec_defaults_project_context_contract() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "universal-agent",
            "name": "Universal Agent",
            "purpose": "Primary responsibility: Perform universal work.\nSelect for: Requests that require universal work.\nDo not select for: Requests unrelated to universal work.",
            "aliases": ["universal"],
        }
    )

    assert spec.project_context_contract.required is False
    assert spec.project_context_contract.supported_schema_versions == [1]
    assert spec.task_contract.task_kinds == []
    assert spec.target_project_access.authorization_modes == []


def test_agent_package_spec_accepts_task_contract() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "task-agent",
            "name": "Task Agent",
            "purpose": "Primary responsibility: Perform task-oriented work.\nSelect for: Requests that require multiple bounded task kinds.\nDo not select for: Requests unrelated to task-oriented work.",
            "aliases": ["task"],
            "task_contract": {
                "task_kinds": ["coding_task", "project_creation"],
                "default_task_kind": "coding_task",
            },
        }
    )

    assert spec.task_contract.task_kinds == ["coding_task", "project_creation"]
    assert spec.task_contract.default_task_kind == "coding_task"


def test_agent_package_spec_rejects_task_contract_default_not_in_task_kinds() -> None:
    with pytest.raises(ValidationError, match="default_task_kind must be included"):
        AgentPackageSpec.model_validate(
            {
                "id": "task-agent",
                "name": "Task Agent",
                "purpose": "Primary responsibility: Perform task-oriented work.\nSelect for: Requests that require multiple bounded task kinds.\nDo not select for: Requests unrelated to task-oriented work.",
                "aliases": ["task"],
                "task_contract": {
                    "task_kinds": ["coding_task"],
                    "default_task_kind": "project_creation",
                },
            }
        )


def test_agent_package_spec_accepts_target_project_access_contract() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "project-agent",
            "name": "Project Agent",
            "purpose": "Primary responsibility: Perform authorised project work.\nSelect for: Requests that require an explicit target project contract.\nDo not select for: Requests unrelated to authorised project work.",
            "aliases": ["project"],
            "input_contract": {"accepted_context": ["project_root"]},
            "target_project_access": {
                "requires_explicit_project_root": True,
                "authorization_modes": [
                    "registered_target",
                    "unregistered_with_approval",
                ],
                "registry_source": "settings.project_registry",
                "allows_target_creation": True,
                "creation_scope": "registered_parent",
                "fail_closed_when": [
                    "platform_unavailable",
                    "credentials_unavailable",
                    "location_unavailable",
                ],
            },
        }
    )

    assert spec.target_project_access.requires_explicit_project_root is True
    assert spec.target_project_access.creation_scope == "registered_parent"


def test_agent_package_spec_rejects_target_project_access_without_project_root_context() -> None:
    with pytest.raises(ValidationError, match="requires 'project_root' in input_contract.accepted_context"):
        AgentPackageSpec.model_validate(
            {
                "id": "project-agent",
                "name": "Project Agent",
                "purpose": "Primary responsibility: Perform authorised project work.\nSelect for: Requests that require an explicit target project contract.\nDo not select for: Requests unrelated to authorised project work.",
                "aliases": ["project"],
                "input_contract": {"accepted_context": ["references"]},
                "target_project_access": {
                    "requires_explicit_project_root": True,
                    "authorization_modes": ["registered_target"],
                    "registry_source": "settings.project_registry",
                },
            }
        )


def test_agent_package_spec_rejects_target_creation_without_scope() -> None:
    with pytest.raises(ValidationError, match="requires a non-'none' creation_scope"):
        AgentPackageSpec.model_validate(
            {
                "id": "project-agent",
                "name": "Project Agent",
                "purpose": "Primary responsibility: Perform authorised project work.\nSelect for: Requests that require an explicit target project contract.\nDo not select for: Requests unrelated to authorised project work.",
                "aliases": ["project"],
                "input_contract": {"accepted_context": ["project_root"]},
                "target_project_access": {
                    "requires_explicit_project_root": True,
                    "allows_target_creation": True,
                },
            }
        )


def test_agent_package_spec_requires_project_root_in_required_context_when_project_context_required() -> None:
    with pytest.raises(ValidationError, match="requires 'project_root' in"):
        AgentPackageSpec.model_validate(
            {
                "id": "universal-agent",
                "name": "Universal Agent",
                "purpose": "Primary responsibility: Perform universal work.\nSelect for: Requests that require universal work.\nDo not select for: Requests unrelated to universal work.",
                "aliases": ["universal"],
                "project_context_contract": {
                    "required": True,
                    "capabilities": ["read"],
                    "enforced_filesystem_permission": "read",
                },
            }
        )


def test_agent_package_spec_accepts_consistent_project_context_declarations() -> None:
    spec = AgentPackageSpec.model_validate(
        {
            "id": "universal-agent",
            "name": "Universal Agent",
            "purpose": "Primary responsibility: Perform universal work.\nSelect for: Requests that require universal work.\nDo not select for: Requests unrelated to universal work.",
            "aliases": ["universal"],
            "input_contract": {"required_context": ["project_root"]},
            "project_context_contract": {
                "required": True,
                "capabilities": ["read"],
                "enforced_filesystem_permission": "read",
            },
        }
    )

    assert spec.project_context_contract.required is True
    assert spec.input_contract.required_context == ["project_root"]


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
