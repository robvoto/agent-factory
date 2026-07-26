"""Boundary adapter for Agent Hub's universal task envelope.

Keep specialist-specific interpretation behind this boundary. Agent Hub sends
the same flat envelope to every specialist — `project_root` and `references`
are uninterpreted context; this package decides what they mean, if anything.

`resume` is only ever populated when this specialist itself set
`interaction_contract.resume = true` in agent.json and previously returned a
`resume_token` alongside a `needs_clarification` result. Hub replays that
value verbatim here on the next dispatch — it is this specialist's own
checkpoint reference, not something Hub constructs or interprets.

Project-context handling below fails closed per `project_context_contract` in
agent.json (AF-054): a missing-when-required, non-string, or stale
(nonexistent-on-disk) `project_root` is rejected rather than silently
substituting this package's own repository as the target.
"""

from __future__ import annotations

from pathlib import Path
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
    "resume",
}

# Kept in sync with project_context_contract.required in this package's agent.json.
PROJECT_ROOT_REQUIRED = {{project_root_required}}


class ProjectContextError(ValueError):
    """Raised when the dispatched project context fails the canonical contract."""


def _validate_project_root(project_root: Any) -> str | None:
    if project_root is None:
        if PROJECT_ROOT_REQUIRED:
            raise ProjectContextError(
                "project context is required but project_root is missing. "
                "This specialist must not substitute its own repository as the target."
            )
        return None
    if not isinstance(project_root, str) or not project_root.strip():
        raise ProjectContextError("project_root must be a non-empty string.")
    if not Path(project_root).exists():
        raise ProjectContextError(
            f"project_root does not exist (stale project context): {project_root!r}"
        )
    return project_root


def adapt_universal_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate common fields and the project context, without interpreting `references`."""

    if not isinstance(payload, dict):
        raise ValueError("Task input must be a JSON object.")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("A non-empty task is required.")
    unsupported = sorted(set(payload).difference(_ALLOWED_FIELDS))
    if unsupported:
        raise ValueError("Unsupported task fields: " + ", ".join(unsupported))

    project_root = _validate_project_root(payload.get("project_root"))

    return {
        "task": task.strip(),
        "request_id": payload.get("request_id"),
        "run_id": payload.get("run_id"),
        "source": payload.get("source"),
        "execution_mode": payload.get("execution_mode"),
        "progress_jsonl": payload.get("progress_jsonl"),
        "project_root": project_root,
        "references": payload.get("references"),
        "human_approved": bool(payload.get("human_approved", False)),
        "approval_token": payload.get("approval_token"),
        "resume": payload.get("resume"),
    }
