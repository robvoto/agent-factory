"""Agent Factory."""

from .build_result import (
    BuildResultConsumptionError,
    BuildResultValidationError,
    consume_agent_build_result,
)

__version__ = '0.1.0'

__all__ = [
    "BuildResultConsumptionError",
    "BuildResultValidationError",
    "consume_agent_build_result",
]
