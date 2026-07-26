from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agent_factory.project_context import (
    ProjectContext,
    ProjectContextConsistencyError,
    ProjectContextContract,
    ProjectContextError,
    validate_project_context,
    verify_project_context_consistency,
)


def test_project_context_defaults_to_current_schema_version() -> None:
    context = ProjectContext()
    assert context.schema_version == 1
    assert context.project_root is None
    assert context.references == []


def test_project_context_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValidationError, match="Unsupported project context schema_version"):
        ProjectContext(schema_version=99)


def test_contract_defaults_are_permissive_and_not_required() -> None:
    contract = ProjectContextContract()
    assert contract.supported_schema_versions == [1]
    assert contract.required is False
    assert contract.capabilities == []
    assert contract.enforced_filesystem_permission == "none"


def test_contract_rejects_empty_supported_schema_versions() -> None:
    with pytest.raises(ValidationError, match="cannot be empty"):
        ProjectContextContract(supported_schema_versions=[])


def test_contract_rejects_unsupported_schema_version_in_list() -> None:
    with pytest.raises(ValidationError, match="does not support"):
        ProjectContextContract(supported_schema_versions=[1, 2])


def test_contract_required_without_capabilities_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must declare at least one capability"):
        ProjectContextContract(required=True, capabilities=[])


def test_contract_write_capability_requires_write_permission() -> None:
    with pytest.raises(ValidationError, match="narrower than its capabilities require"):
        ProjectContextContract(capabilities=["write"], enforced_filesystem_permission="read")


def test_contract_accepts_consistent_capability_and_permission() -> None:
    contract = ProjectContextContract(
        required=True,
        capabilities=["read", "write"],
        enforced_filesystem_permission="write",
    )
    assert contract.capabilities == ["read", "write"]


def test_validate_project_context_returns_none_when_absent_and_not_required() -> None:
    contract = ProjectContextContract()
    result = validate_project_context({"task": "do something"}, contract)
    assert result is None


def test_validate_project_context_rejects_missing_when_required() -> None:
    contract = ProjectContextContract(
        required=True, capabilities=["read"], enforced_filesystem_permission="read"
    )
    with pytest.raises(ProjectContextError, match="required but missing"):
        validate_project_context({"task": "do something"}, contract)


def test_validate_project_context_rejects_stale_project_root() -> None:
    contract = ProjectContextContract()
    with pytest.raises(ProjectContextError, match="does not exist"):
        validate_project_context(
            {"task": "do something", "project_root": "/nonexistent/path/for/testing"},
            contract,
        )


def test_validate_project_context_accepts_existing_project_root(tmp_path) -> None:
    contract = ProjectContextContract(
        required=True, capabilities=["read"], enforced_filesystem_permission="read"
    )
    result = validate_project_context(
        {"task": "do something", "project_root": str(tmp_path)},
        contract,
    )
    assert result is not None
    assert result.project_root == str(tmp_path)


def test_validate_project_context_accepts_explicit_schema_version(tmp_path) -> None:
    contract = ProjectContextContract(supported_schema_versions=[1])
    result = validate_project_context(
        {
            "task": "do something",
            "project_context": {"schema_version": 1, "project_root": str(tmp_path)},
        },
        contract,
    )
    assert result is not None
    assert result.schema_version == 1


def test_validate_project_context_rejects_unsupported_schema_version(tmp_path) -> None:
    contract = ProjectContextContract()
    with pytest.raises(ProjectContextError, match="Invalid project_context"):
        validate_project_context(
            {
                "task": "do something",
                "project_context": {"schema_version": 2, "project_root": str(tmp_path)},
            },
            contract,
        )


def test_validate_project_context_rejects_version_mismatched_contract(tmp_path, monkeypatch) -> None:
    import agent_factory.project_context as project_context_module

    monkeypatch.setattr(
        project_context_module, "SUPPORTED_PROJECT_CONTEXT_SCHEMA_VERSIONS", {1, 2}
    )
    contract = ProjectContextContract(supported_schema_versions=[1])
    with pytest.raises(ProjectContextError, match="is not supported by this specialist"):
        validate_project_context(
            {
                "task": "do something",
                "project_context": {"schema_version": 2, "project_root": str(tmp_path)},
            },
            contract,
        )


def test_validate_project_context_rejects_unknown_fields(tmp_path) -> None:
    contract = ProjectContextContract()
    with pytest.raises(ProjectContextError, match="unknown fields"):
        validate_project_context(
            {
                "task": "do something",
                "project_context": {"project_root": str(tmp_path), "extra": "nope"},
            },
            contract,
        )


def _write_package(tmp_path, *, manifest_required: bool, adapter_required: str) -> None:
    (tmp_path / "agent.json").write_text(
        json.dumps({"project_context_contract": {"required": manifest_required}}),
        encoding="utf-8",
    )
    (tmp_path / "specialist_contract.py").write_text(
        f"PROJECT_ROOT_REQUIRED = {adapter_required}\n", encoding="utf-8"
    )


def test_verify_project_context_consistency_passes_when_matching(tmp_path) -> None:
    _write_package(tmp_path, manifest_required=True, adapter_required="True")
    verify_project_context_consistency(tmp_path)  # does not raise


def test_verify_project_context_consistency_rejects_drift(tmp_path) -> None:
    _write_package(tmp_path, manifest_required=True, adapter_required="False")
    with pytest.raises(ProjectContextConsistencyError, match="must agree"):
        verify_project_context_consistency(tmp_path)


def test_verify_project_context_consistency_requires_both_files(tmp_path) -> None:
    with pytest.raises(ProjectContextConsistencyError, match="missing"):
        verify_project_context_consistency(tmp_path)


def test_verify_project_context_consistency_requires_project_root_required_constant(tmp_path) -> None:
    (tmp_path / "agent.json").write_text(
        json.dumps({"project_context_contract": {"required": False}}), encoding="utf-8"
    )
    (tmp_path / "specialist_contract.py").write_text("# no constant here\n", encoding="utf-8")
    with pytest.raises(ProjectContextConsistencyError, match="no PROJECT_ROOT_REQUIRED"):
        verify_project_context_consistency(tmp_path)
