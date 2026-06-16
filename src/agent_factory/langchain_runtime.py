"""Minimal LangChain harness integration.

This module creates a basic LangChain agent harness only.
It does not configure any specialist Agent Factory agents.
"""

from __future__ import annotations

from typing import Any

from .errors import AgentFactoryError


class LangChainUnavailableError(AgentFactoryError):
    """Raised when LangChain is not installed in the active Python environment."""


def ensure_langchain_available() -> None:
    """Verify that the active environment has LangChain's agent harness available."""

    try:
        from langchain.agents import create_agent  # noqa: F401
    except ImportError as exc:
        raise LangChainUnavailableError(
            "LangChain is not installed. Run: bash scripts/wsl/setup.sh"
        ) from exc


def create_basic_langchain_agent(
    *,
    model: str,
    system_prompt: str = "You are a concise and accurate assistant.",
) -> Any:
    """Create a basic LangChain agent with no tools.

    The caller may invoke the returned agent later. This function does not
    execute model calls and does not add tools by default.
    """

    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        raise LangChainUnavailableError(
            "LangChain is not installed. Run: bash scripts/wsl/setup.sh"
        ) from exc

    return create_agent(
        model=model,
        tools=[],
        system_prompt=system_prompt,
    )
