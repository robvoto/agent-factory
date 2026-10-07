"""Tests for the explicit MCP manifest and runtime boundary."""

import json

import pytest
from pydantic import ValidationError

from agent_factory.agent_spec import AgentPackageSpec
from agent_factory.errors import ManifestValidationError, McpCapabilityError
from agent_factory.mcp import load_mcp_capabilities
from agent_factory.models import AgentManifest


def _purpose() -> str:
    return (
        "Primary responsibility: Perform MCP test work.\n"
        "Select for: Requests that require the declared MCP capability.\n"
        "Do not select for: Requests outside the declared MCP capability."
    )


def _declaration(**overrides) -> dict:
    declaration = {
        "name": "approved.server",
        "tools": ["records.read"],
        "permission_boundary": {
            "network": False,
            "filesystem": "read",
            "shell": False,
        },
    }
    declaration.update(overrides)
    return declaration


def _spec(**overrides) -> AgentPackageSpec:
    data = {
        "id": "mcp-agent",
        "name": "MCP Agent",
        "purpose": _purpose(),
        "aliases": ["mcp"],
        "mcp_servers": [_declaration()],
        "permissions": {"filesystem": "read"},
    }
    data.update(overrides)
    return AgentPackageSpec.model_validate(data)


def _approved() -> dict:
    return {
        "approved.server": {
            "name": "approved.server",
            "tools": ["records.read", "records.write"],
            "permission_boundary": {
                "network": False,
                "filesystem": "read",
                "shell": False,
            },
        }
    }


def test_spec_validates_mcp_tools_and_permission_boundary() -> None:
    spec = _spec()

    assert spec.mcp_servers[0].name == "approved.server"
    assert spec.mcp_servers[0].tools == ["records.read"]
    assert spec.mcp_servers[0].permission_boundary.filesystem == "read"


def test_spec_rejects_duplicate_mcp_servers_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="duplicate server names"):
        _spec(mcp_servers=[_declaration(), _declaration()])

    with pytest.raises(ValidationError, match="extra_forbidden"):
        _spec(mcp_servers=[{**_declaration(), "provider": "implicit"}])


@pytest.mark.parametrize(
    ("permission_boundary", "agent_permissions", "escalation"),
    [
        (
            {"network": False, "filesystem": "read", "shell": False},
            {"network": False, "filesystem": "none", "shell": False},
            "filesystem=read",
        ),
        (
            {"network": True, "filesystem": "none", "shell": False},
            {"network": False, "filesystem": "none", "shell": False},
            "network",
        ),
        (
            {"network": False, "filesystem": "none", "shell": True},
            {"network": False, "filesystem": "none", "shell": False},
            "shell",
        ),
    ],
)
def test_spec_rejects_mcp_permission_escalation(
    permission_boundary, agent_permissions, escalation
) -> None:
    with pytest.raises(ValidationError, match=escalation):
        _spec(
            permissions=agent_permissions,
            mcp_servers=[_declaration(permission_boundary=permission_boundary)],
        )


def test_manifest_loader_preserves_mcp_declarations() -> None:
    manifest = AgentManifest.from_dict(
        {
            "id": "mcp-agent",
            "name": "MCP Agent",
            "purpose": _purpose(),
            "aliases": ["mcp"],
            "tools": [],
            "mcp_servers": [_declaration()],
            "permissions": {"filesystem": "read"},
            "memory": {},
            "runtime": {"mode": "manual"},
        }
    )

    assert manifest.mcp_servers is not None
    assert manifest.mcp_servers[0]["name"] == "approved.server"
    assert manifest.mcp_servers[0]["tools"] == ["records.read"]


def test_manifest_loader_rejects_mcp_permission_escalation() -> None:
    with pytest.raises(ManifestValidationError, match="agent permissions ceiling"):
        AgentManifest.from_dict(
            {
                "id": "mcp-agent",
                "name": "MCP Agent",
                "purpose": _purpose(),
                "aliases": ["mcp"],
                "tools": [],
                "mcp_servers": [_declaration()],
                "permissions": {"filesystem": "none"},
                "memory": {},
                "runtime": {"mode": "manual"},
            }
        )


def test_staging_and_promotion_preserve_mcp_declarations(tmp_path, monkeypatch) -> None:
    import agent_factory.storage as storage_module
    from agent_factory import factory_tools
    from agent_factory.agent_catalog import promote_agent

    staging = tmp_path / "staging" / "agents"
    staging.mkdir(parents=True)
    db = tmp_path / "factory.sqlite3"
    monkeypatch.setattr(factory_tools, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(factory_tools, "_STAGING_DIR", staging)
    monkeypatch.setattr(storage_module, "_DEFAULT_DB_PATH", db)

    result = factory_tools.create_staged_agent_package.invoke(
        {"spec_json": _spec().model_dump_json()}
    )
    assert "Files created" in result

    staged = json.loads(
        (staging / "mcp-agent" / "agent.json").read_text(encoding="utf-8")
    )
    assert staged["mcp_servers"][0]["name"] == "approved.server"
    assert staged["mcp_servers"][0]["tools"] == ["records.read"]

    result = promote_agent("mcp-agent", project_root=tmp_path, db_path=db)
    assert "promoted" in result
    enabled = json.loads(
        (tmp_path / "config" / "agents" / "mcp-agent.json").read_text(encoding="utf-8")
    )
    assert enabled["mcp_servers"] == staged["mcp_servers"]


def test_approved_registry_and_runtime_loader_allow_declared_capability(tmp_path) -> None:
    registry = tmp_path / "mcp_servers.json"
    registry.write_text(
        json.dumps(
            {
                "servers": {
                    "approved.server": {
                        "tools": ["records.read", "records.write"],
                        "permission_boundary": {
                            "network": False,
                            "filesystem": "read",
                            "shell": False,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    handle = object()
    loaded = load_mcp_capabilities(
        _spec(),
        approved_registry_path=registry,
        available_servers={"approved.server": handle, "extra": object()},
    )

    assert len(loaded) == 1
    assert loaded[0].server_name == "approved.server"
    assert loaded[0].tools == ("records.read",)
    assert loaded[0].handle is handle


@pytest.mark.parametrize(
    ("permission_boundary", "agent_permissions", "escalation"),
    [
        (
            {"network": False, "filesystem": "read", "shell": False},
            {"network": False, "filesystem": "none", "shell": False},
            "filesystem=read",
        ),
        (
            {"network": True, "filesystem": "none", "shell": False},
            {"network": False, "filesystem": "none", "shell": False},
            "network",
        ),
        (
            {"network": False, "filesystem": "none", "shell": True},
            {"network": False, "filesystem": "none", "shell": False},
            "shell",
        ),
    ],
)
def test_runtime_loader_rejects_mcp_permission_escalation(
    permission_boundary, agent_permissions, escalation
) -> None:
    with pytest.raises(McpCapabilityError, match=escalation):
        load_mcp_capabilities(
            [_declaration(permission_boundary=permission_boundary)],
            approved_servers=_approved(),
            available_servers={"approved.server": object()},
            agent_permissions=agent_permissions,
        )


def test_runtime_loader_uses_manifest_permission_ceiling() -> None:
    from types import SimpleNamespace

    manifest = SimpleNamespace(
        mcp_servers=[_declaration()],
        permissions={"filesystem": "none"},
    )

    with pytest.raises(McpCapabilityError, match="agent permission ceiling"):
        load_mcp_capabilities(
            manifest,
            approved_servers=_approved(),
            available_servers={"approved.server": object()},
        )

    with pytest.raises(McpCapabilityError, match="Cannot override"):
        load_mcp_capabilities(
            manifest,
            approved_servers=_approved(),
            available_servers={"approved.server": object()},
            agent_permissions={"filesystem": "read"},
        )


def test_required_false_still_requires_approval_and_availability() -> None:
    declaration = _declaration(required=False)

    with pytest.raises(McpCapabilityError, match="not approved"):
        load_mcp_capabilities(
            [declaration],
            approved_servers={},
            available_servers={"approved.server": object()},
            agent_permissions={"filesystem": "read"},
        )

    with pytest.raises(McpCapabilityError, match="unavailable"):
        load_mcp_capabilities(
            [declaration],
            approved_servers=_approved(),
            available_servers={},
            agent_permissions={"filesystem": "read"},
        )


@pytest.mark.parametrize(
    ("spec", "approved", "available", "message"),
    [
        (_spec(), {}, {"approved.server": object()}, "not approved"),
        (
            _spec(mcp_servers=[_declaration(tools=["records.delete"])]),
            _approved(),
            {"approved.server": object()},
            "unapproved tool",
        ),
        (
            _spec(
                permissions={"network": True, "filesystem": "read"},
                mcp_servers=[
                    _declaration(
                        permission_boundary={
                            "network": True,
                            "filesystem": "read",
                            "shell": False,
                        }
                    )
                ]
            ),
            _approved(),
            {"approved.server": object()},
            "denied permission",
        ),
        (_spec(), _approved(), {}, "unavailable"),
    ],
)
def test_runtime_loader_fails_closed(
    spec, approved, available, message
) -> None:
    with pytest.raises(McpCapabilityError, match=message):
        load_mcp_capabilities(
            spec,
            approved_servers=approved,
            available_servers=available,
        )
