"""Explicit MCP capability authorization for agent runtimes.

Factory does not discover or execute MCP servers. It validates declarations
against the committed approval registry and an explicitly supplied availability
map, then returns the authorized handles for an external runtime consumer.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent_spec import AgentPermissions, McpPermissionBoundary, McpServer
from .errors import McpCapabilityError

_DEFAULT_APPROVAL_REGISTRY = Path(__file__).parents[2] / "config" / "mcp_servers.json"


@dataclass(frozen=True)
class LoadedMcpCapability:
    """An authorized MCP handle selected by an agent declaration."""

    server_name: str
    tools: tuple[str, ...]
    permission_boundary: McpPermissionBoundary
    handle: Any


def load_approved_mcp_servers(path: str | Path) -> dict[str, McpServer]:
    """Load the explicit MCP server/tool approval registry from JSON."""

    registry_path = Path(path)
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise McpCapabilityError(
            f"MCP approval registry unavailable: {registry_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise McpCapabilityError(
            f"MCP approval registry is invalid JSON: {registry_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict) or set(raw) != {"servers"} or not isinstance(raw["servers"], dict):
        raise McpCapabilityError(
            "MCP approval registry must be an object with a 'servers' object."
        )

    approved: dict[str, McpServer] = {}
    for server_name, declaration in raw["servers"].items():
        if not isinstance(server_name, str) or not server_name.strip():
            raise McpCapabilityError("MCP approval registry contains an invalid server identifier.")
        if not isinstance(declaration, dict):
            raise McpCapabilityError(
                f"MCP approval registry entry for '{server_name}' must be an object."
            )
        if set(declaration) - {"tools", "permission_boundary"}:
            unknown = ", ".join(sorted(set(declaration) - {"tools", "permission_boundary"}))
            raise McpCapabilityError(
                f"MCP approval registry entry for '{server_name}' has unknown field(s): {unknown}."
            )
        try:
            approved_server = McpServer.model_validate(
                {"name": server_name, **declaration}
            )
        except ValueError as exc:
            raise McpCapabilityError(
                f"MCP approval registry entry for '{server_name}' is invalid: {exc}"
            ) from exc
        approved[approved_server.name] = approved_server
    return approved


def load_mcp_capabilities(
    declarations: Any,
    *,
    approved_servers: Mapping[str, McpServer] | None = None,
    available_servers: Mapping[str, Any],
    approved_registry_path: str | Path | None = None,
    agent_permissions: AgentPermissions | Mapping[str, Any] | None = None,
) -> tuple[LoadedMcpCapability, ...]:
    """Authorize and select only explicitly declared MCP server capabilities.

    ``available_servers`` is supplied by the external runtime consumer. It is
    never discovered or populated by Factory. Extra available servers are
    ignored; every declared server must be approved and available. When a
    manifest object is supplied, its own top-level permissions are authoritative
    and cannot be overridden by the caller.
    """

    if approved_servers is not None and approved_registry_path is not None:
        raise McpCapabilityError(
            "Provide either approved_servers or approved_registry_path, not both."
        )
    if approved_servers is None:
        approved_servers = load_approved_mcp_servers(
            approved_registry_path or _DEFAULT_APPROVAL_REGISTRY
        )

    declared_servers = getattr(declarations, "mcp_servers", declarations)
    if declared_servers is None:
        declared_servers = ()
    try:
        normalized = tuple(
            item if isinstance(item, McpServer) else McpServer.model_validate(item)
            for item in declared_servers
        )
    except (TypeError, ValueError) as exc:
        raise McpCapabilityError(f"MCP declaration is invalid: {exc}") from exc

    if not normalized:
        return ()

    declared_agent_permissions = getattr(declarations, "permissions", None)
    if declared_agent_permissions is not None and agent_permissions is not None:
        raise McpCapabilityError(
            "Cannot override the agent's own top-level permissions when loading MCP capabilities."
        )
    raw_agent_permissions = (
        declared_agent_permissions
        if declared_agent_permissions is not None
        else agent_permissions
    )
    if raw_agent_permissions is None:
        raise McpCapabilityError(
            "Agent permissions are required before loading MCP capabilities; refusing to load."
        )
    try:
        normalized_agent_permissions = (
            raw_agent_permissions
            if isinstance(raw_agent_permissions, AgentPermissions)
            else AgentPermissions.model_validate(raw_agent_permissions)
        )
    except (TypeError, ValueError) as exc:
        raise McpCapabilityError(
            f"Agent permissions are invalid; refusing to load MCP capabilities: {exc}"
        ) from exc

    loaded: list[LoadedMcpCapability] = []
    seen_servers: set[str] = set()
    for declaration in normalized:
        if declaration.name in seen_servers:
            raise McpCapabilityError(
                f"MCP server '{declaration.name}' was declared more than once; refusing to load it."
            )
        seen_servers.add(declaration.name)

        approved_raw = approved_servers.get(declaration.name)
        if approved_raw is None:
            raise McpCapabilityError(
                f"MCP server '{declaration.name}' is not approved; refusing to load it."
            )
        try:
            approved = (
                approved_raw
                if isinstance(approved_raw, McpServer)
                else McpServer.model_validate({"name": declaration.name, **approved_raw})
            )
        except (TypeError, ValueError) as exc:
            raise McpCapabilityError(
                f"MCP approval for server '{declaration.name}' is invalid: {exc}"
            ) from exc

        unknown_tools = sorted(set(declaration.tools) - set(approved.tools))
        if unknown_tools:
            raise McpCapabilityError(
                f"MCP server '{declaration.name}' requested unapproved tool(s): "
                + ", ".join(unknown_tools)
            )
        agent_escalations = declaration.permission_boundary.escalation_fields(
            normalized_agent_permissions
        )
        if agent_escalations:
            raise McpCapabilityError(
                f"MCP server '{declaration.name}' exceeds the agent permission ceiling: "
                + ", ".join(agent_escalations)
            )
        _ensure_permission_boundary_allowed(declaration, approved)

        if declaration.name not in available_servers or available_servers[declaration.name] is None:
            raise McpCapabilityError(
                f"MCP server '{declaration.name}' is unavailable; refusing to load it."
            )
        loaded.append(
            LoadedMcpCapability(
                server_name=declaration.name,
                tools=tuple(declaration.tools),
                permission_boundary=declaration.permission_boundary,
                handle=available_servers[declaration.name],
            )
        )
    return tuple(loaded)


def _ensure_permission_boundary_allowed(
    declaration: McpServer,
    approved: McpServer,
) -> None:
    requested = declaration.permission_boundary
    ceiling = approved.permission_boundary
    denied: list[str] = []
    if requested.network and not ceiling.network:
        denied.append("network")
    if requested.shell and not ceiling.shell:
        denied.append("shell")
    filesystem_rank = {"none": 0, "read": 1, "write": 2}
    if filesystem_rank[requested.filesystem] > filesystem_rank[ceiling.filesystem]:
        denied.append(f"filesystem={requested.filesystem}")
    if denied:
        raise McpCapabilityError(
            f"MCP server '{declaration.name}' requested denied permission boundary: "
            + ", ".join(denied)
        )
