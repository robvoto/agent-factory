import pytest

from agent_factory.errors import AgentNotFoundError
from agent_factory.loader import AgentRegistry
from agent_factory.models import AgentManifest
from agent_factory.router import AgentRouter


def make_registry():
    manifest = AgentManifest.from_dict(
        {
            "id": "alpha",
            "name": "Alpha Agent",
            "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
            "aliases": ["alpha", "a"],
            "tools": [],
            "permissions": {},
            "memory": {},
            "runtime": {"mode": "manual"},
            "output_contract": None,
        }
    )
    return AgentRegistry([manifest])


def test_router_routes_alias_command():
    result = AgentRouter(make_registry()).route("/agent a hello factory")

    assert result.agent.id == "alpha"
    assert result.message == "hello factory"


def test_router_fails_closed_for_unknown_alias():
    with pytest.raises(AgentNotFoundError):
        AgentRouter(make_registry()).route("/agent missing hello")


def test_empty_registry_lists_no_agents():
    registry = AgentRegistry([])

    assert registry.list_agents() == []
