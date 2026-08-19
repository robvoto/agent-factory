"""Command router for configured agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .errors import AgentNotFoundError, RouteError
from .loader import AgentRegistry
from .models import AgentManifest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteResult:
    agent: AgentManifest
    message: str


class AgentRouter:
    """Route `/agent <alias> <message>` commands to configured agents."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def route(self, command: str) -> RouteResult:
        logger.info("Routing command: %s", command)
        parts = command.strip().split(maxsplit=2)
        if len(parts) < 2 or parts[0] != "/agent":
            logger.warning("Rejected malformed route command: %s", command)
            raise RouteError("Expected command format: /agent <alias> <message>")

        alias = parts[1].strip().lower()
        message = parts[2].strip() if len(parts) == 3 else ""
        logger.debug("Looking up agent alias %s.", alias)
        agent = self._registry.find_by_alias(alias)
        if agent is None:
            logger.warning("No configured agent matches alias %s.", alias)
            raise AgentNotFoundError(f"No configured agent matches alias: {alias}")
        logger.info("Routed command to agent %s.", agent.id)
        return RouteResult(agent=agent, message=message)
