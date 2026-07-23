"""Boundary adapter for Agent Hub's universal task envelope.

Keep specialist-specific interpretation behind this boundary. Agent Hub supplies
known context and uninterpreted references; this package decides what they mean.
"""

from __future__ import annotations

from typing import Any

_ALLOWED_FIELDS = {
    "task",
    "request_id",
    "run_id",
    "source",
    "execution_mode",
    "context",
    "human_approved",
    "approval_token",
    "resume",
}
_ALLOWED_CONTEXT = {"selected_project", "user_supplied_references"}


def adapt_universal_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate common fields and preserve context without interpreting it."""

    if not isinstance(payload, dict):
        raise ValueError("Task input must be a JSON object.")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A non-empty task is required.")
    unsupported = sorted(set(payload).difference(_ALLOWED_FIELDS))
    if unsupported:
        raise ValueError("Unsupported task fields: " + ", ".join(unsupported))

    context = payload.get("context", {})
    if not isinstance(context, dict):
        raise ValueError("context must be an object when supplied.")
    unsupported_context = sorted(set(context).difference(_ALLOWED_CONTEXT))
    if unsupported_context:
        raise ValueError("Unsupported context fields: " + ", ".join(unsupported_context))

    return {
        "task": task.strip(),
        "request_id": payload.get("request_id"),
        "run_id": payload.get("run_id"),
        "source": payload.get("source"),
        "execution_mode": payload.get("execution_mode"),
        "context": dict(context),
        "human_approved": bool(payload.get("human_approved", False)),
        "approval_token": payload.get("approval_token"),
        "resume": payload.get("resume"),
    }
