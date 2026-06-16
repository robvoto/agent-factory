"""Shared logging setup for Agent Factory entry points."""

from __future__ import annotations

import logging
import os

DEFAULT_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def resolve_log_level(log_level: str | int | None = None) -> int:
    """Resolve a logging level from an explicit value or the environment."""
    candidate: str | int = (
        log_level
        if log_level is not None
        else os.environ.get("FACTORY_LOG_LEVEL", DEFAULT_LOG_LEVEL)
    )

    if isinstance(candidate, int):
        return candidate

    level = getattr(logging, candidate.upper(), None)
    if isinstance(level, int):
        return level

    raise ValueError(
        f"Unknown log level: {candidate!r}. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL."
    )


def configure_logging(log_level: str | int | None = None) -> None:
    """Install a consistent human-readable logging configuration."""
    level = resolve_log_level(log_level)
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
