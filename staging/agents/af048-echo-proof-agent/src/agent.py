"""Deterministic echo behavior for the AF-048 proof agent."""


def run(task: str) -> str:
    """Prefix non-blank input with Echo: without changing the input."""
    if not isinstance(task, str):
        raise ValueError("task must be a non-empty string")
    if not task.strip():
        raise ValueError("task must be a non-empty string")
    return "Echo: " + task
