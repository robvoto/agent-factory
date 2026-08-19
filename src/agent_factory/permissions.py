"""Tool access checks for Agent Factory."""

from __future__ import annotations

from collections.abc import Iterable

from .errors import UnknownToolError
from .models import AgentManifest


def validate_tools(manifest: AgentManifest, allowed_tool_ids: Iterable[str]) -> None:
    """Raise when an agent manifest names a tool outside the configured set."""

    allowed = {item.strip() for item in allowed_tool_ids if item.strip()}
    unknown = sorted(tool for tool in manifest.tools if tool not in allowed)
    if unknown:
        raise UnknownToolError(
            f"Agent '{manifest.id}' requested unknown tools: {', '.join(unknown)}"
        )
