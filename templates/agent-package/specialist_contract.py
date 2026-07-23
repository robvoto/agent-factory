"""Boundary adapter for Agent Hub's universal task envelope.

Keep specialist-specific interpretation behind this boundary. Agent Hub sends
the same flat envelope to every specialist — `project_root` and `references`
are uninterpreted context; this package decides what they mean, if anything.
"""

from __future__ import annotations

from typing import Any

_ALLOWED_FIELDS = {
    "task",
    "request_id",
    "run_id",
    "source",
    "execution_mode",
    "progress_jsonl",
    "project_root",
    "references",
    "human_approved",
    "approval_token",
}


def adapt_universal_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate common fields and preserve project_root/references without interpreting them."""

    if not isinstance(payload, dict):
        raise ValueError("Task input must be a JSON object.")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A non-empty task is required.")
    unsupported = sorted(set(payload).difference(_ALLOWED_FIELDS))
    if unsupported:
        raise ValueError("Unsupported task fields: " + ", ".join(unsupported))

    return {
        "task": task.strip(),
        "request_id": payload.get("request_id"),
        "run_id": payload.get("run_id"),
        "source": payload.get("source"),
        "execution_mode": payload.get("execution_mode"),
        "progress_jsonl": payload.get("progress_jsonl"),
        "project_root": payload.get("project_root"),
        "references": payload.get("references"),
        "human_approved": bool(payload.get("human_approved", False)),
        "approval_token": payload.get("approval_token"),
    }
