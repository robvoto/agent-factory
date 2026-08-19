import pytest

from agent_factory.errors import UnknownToolError
from agent_factory.models import AgentManifest
from agent_factory.permissions import validate_tools


def test_permission_check_accepts_empty_tool_list():
    manifest = AgentManifest.from_dict(
        {
            "id": "alpha",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
            "tools": [],
            "permissions": {},
            "memory": {},
            "runtime": {"mode": "manual"},
            "output_contract": None,
        }
    )

    validate_tools(manifest, allowed_tool_ids=[])


def test_permission_check_denies_unknown_tools():
    manifest = AgentManifest.from_dict(
        {
            "id": "alpha",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha"],
            "tools": ["shell.run"],
            "permissions": {},
            "memory": {},
            "runtime": {"mode": "manual"},
            "output_contract": None,
        }
    )

    with pytest.raises(UnknownToolError):
        validate_tools(manifest, allowed_tool_ids=["local.search"])
