"""Transport-neutral progress reporting for Factory Brain and generated agents.

The Hub-facing contract is versioned JSONL on reserved stdout. Normal and debug
logs remain on stderr, and final structured results remain on the existing
output-file boundary.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Protocol, TextIO

logger = logging.getLogger(__name__)

PROGRESS_SCHEMA_VERSION = 1
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0
MAX_PROGRESS_SUMMARY_CHARS = 280
MAX_PROGRESS_METADATA_STRING_CHARS = 120

_ALLOWED_EVENT_TYPES = {
    "completed",
    "failure",
    "heartbeat",
    "phase",
    "start",
    "waiting",
    "warning",
}
_ALLOWED_METADATA_KEYS = {
    "action",
    "adapter",
    "attempt",
    "source",
    "status",
    "tool",
}
_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_PHASE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_SAFE_LABEL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.:-]{0,79}$")


class ProgressSink(Protocol):
    """Minimal output boundary shared by deterministic and agent runtimes."""

    @property
    def enabled(self) -> bool: ...

    def emit(
        self,
        *,
        event_type: str,
        phase: str,
        human_summary: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool: ...


class NullProgressSink:
    """No-op sink used for standalone or direct Factory calls."""

    @property
    def enabled(self) -> bool:
        return False

    def emit(
        self,
        *,
        event_type: str,
        phase: str,
        human_summary: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        del event_type, phase, human_summary, metadata
        return False


class StdoutJsonlProgressSink:
    """Write validated SpecialistProgressEvent objects to reserved stdout."""

    def __init__(
        self,
        *,
        run_id: str,
        request_id: str,
        stream: TextIO | None = None,
    ) -> None:
        self._run_id = _required_identifier(run_id, field="run_id")
        self._request_id = _required_identifier(request_id, field="request_id")
        self._stream = stream or sys.stdout
        self._sequence = 0
        self._enabled = True
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(
        self,
        *,
        event_type: str,
        phase: str,
        human_summary: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        if not self._enabled:
            return False

        payload = {
            "schema_version": PROGRESS_SCHEMA_VERSION,
            "run_id": self._run_id,
            "request_id": self._request_id,
            "sequence": 0,
            "event_type": _validated_event_type(event_type),
            "phase": _validated_phase(phase),
            "human_summary": _bounded_summary(human_summary),
            "occurred_at": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "metadata": _bounded_metadata(metadata),
        }

        with self._lock:
            if not self._enabled:
                return False
            self._sequence += 1
            payload["sequence"] = self._sequence
            try:
                self._stream.write(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                )
                self._stream.write("\n")
                self._stream.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self._enabled = False
                logger.warning(
                    "Factory progress stream disabled after write failure: %s",
                    exc,
                )
                return False
        return True


class ProgressReporter:
    """Workflow-facing progress API with safe Deep Agent event translation."""

    def __init__(
        self,
        sink: ProgressSink | None = None,
        *,
        agent_name: str = "Agent Factory",
        heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._sink = sink or NullProgressSink()
        self._agent_name = _required_agent_name(agent_name)
        self._heartbeat_interval_seconds = max(0.0, heartbeat_interval_seconds)
        self._state_lock = threading.Lock()
        self._current_phase = "starting"
        self._last_emit_monotonic = time.monotonic()
        self._last_signature: tuple[str, str, str] | None = None

    @property
    def enabled(self) -> bool:
        return self._sink.enabled

    def emit(
        self,
        *,
        event_type: str,
        phase: str,
        human_summary: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        signature = (event_type, phase, human_summary)
        if event_type != "heartbeat" and signature == self._last_signature:
            return False
        try:
            emitted = self._sink.emit(
                event_type=event_type,
                phase=phase,
                human_summary=human_summary,
                metadata=metadata,
            )
        except Exception:
            logger.exception(
                "Factory progress event rejected event_type=%s phase=%s",
                event_type,
                phase,
            )
            return False
        if emitted:
            with self._state_lock:
                self._current_phase = phase
                self._last_emit_monotonic = time.monotonic()
                self._last_signature = signature
        return emitted

    def started(self, summary: str | None = None) -> bool:
        return self.emit(
            event_type="start",
            phase="starting",
            human_summary=summary or f"{self._agent_name} accepted the task.",
        )

    def phase(
        self,
        phase: str,
        summary: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        return self.emit(
            event_type="phase",
            phase=phase,
            human_summary=summary,
            metadata=metadata,
        )

    def waiting(self, phase: str, summary: str) -> bool:
        return self.emit(
            event_type="waiting",
            phase=phase,
            human_summary=summary,
        )

    def completed(self, summary: str | None = None) -> bool:
        return self.emit(
            event_type="completed",
            phase="completed",
            human_summary=summary or f"{self._agent_name} completed the task.",
        )

    def failed(self, summary: str | None = None) -> bool:
        return self.emit(
            event_type="failure",
            phase="failed",
            human_summary=summary
            or f"{self._agent_name} failed. Check the final result.",
        )

    def cancelled(self) -> bool:
        return self.emit(
            event_type="warning",
            phase="cancelled",
            human_summary=f"{self._agent_name} run was cancelled.",
        )

    def handle_deep_agent_event(self, event: Any) -> bool:
        """Translate event structure only; never forward model or tool payloads."""

        labels = _event_labels(event)
        lower_labels = {label.lower() for label in labels}

        approval_labels = {
            "__interrupt__",
            "interrupt",
            "request_approval",
            "request_agent_promotion",
        }
        if lower_labels & approval_labels:
            return self.waiting(
                "waiting_approval",
                f"{self._agent_name} is waiting for human approval.",
            )

        if any("create_staged_agent_package" in label for label in lower_labels):
            return self.phase(
                "staging",
                f"{self._agent_name} is staging the approved agent package.",
                {"tool": "create_staged_agent_package", "source": "deep_agent"},
            )

        if any(
            token in label
            for label in lower_labels
            for token in ("validate", "review", "risk")
        ):
            return self.phase(
                "validation",
                f"{self._agent_name} is validating the agent design.",
                {"source": "deep_agent"},
            )

        tool_name = _first_tool_label(lower_labels)
        if tool_name is not None:
            return self.phase(
                "tool",
                f"{self._agent_name} is using a bounded tool.",
                {"tool": tool_name, "source": "deep_agent"},
            )

        if lower_labels & {"model", "agent", "updates"}:
            return self.phase(
                "design",
                f"{self._agent_name} is designing the agent package.",
                {"source": "deep_agent"},
            )
        return False

    def handle_simple_agent_event(self, event: Any) -> bool:
        """Translate common simple-agent callback events without forwarding payloads."""

        labels = {label.lower() for label in _event_labels(event)}
        if labels & {"approval", "approval_required", "interrupt", "waiting"}:
            return self.waiting(
                "waiting_approval",
                f"{self._agent_name} is waiting for human approval.",
            )
        if any("tool" in label for label in labels):
            return self.phase(
                "tool",
                f"{self._agent_name} is using a bounded tool.",
                {"adapter": "simple_agent"},
            )
        if labels & {"validation", "review", "checking"}:
            return self.phase(
                "validation",
                f"{self._agent_name} is validating the result.",
                {"adapter": "simple_agent"},
            )
        if labels & {"agent", "model", "messages", "start", "updates"}:
            return self.phase(
                "working",
                f"{self._agent_name} is working on the task.",
                {"adapter": "simple_agent"},
            )
        return False

    @contextmanager
    def heartbeat_scope(self):
        """Emit deterministic liveness only after a genuinely quiet interval."""

        if not self.enabled or self._heartbeat_interval_seconds <= 0:
            yield
            return

        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(stop_event,),
            name="agent-factory-progress-heartbeat",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=max(1.0, self._heartbeat_interval_seconds))

    def _heartbeat_loop(self, stop_event: threading.Event) -> None:
        check_interval = min(
            1.0,
            max(0.05, self._heartbeat_interval_seconds / 4),
        )
        while not stop_event.wait(check_interval):
            with self._state_lock:
                quiet_for = time.monotonic() - self._last_emit_monotonic
                phase = self._current_phase
            if quiet_for < self._heartbeat_interval_seconds:
                continue
            self.emit(
                event_type="heartbeat",
                phase=phase,
                human_summary=f"{self._agent_name} is still working: {phase.replace('_', ' ')}.",
            )


def progress_reporter_from_ids(
    *,
    run_id: str | None,
    request_id: str | None,
    stream: TextIO | None = None,
    agent_name: str = "Agent Factory",
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> ProgressReporter:
    """Create stdout progress only for a fully correlated Hub request."""

    if not run_id or not request_id:
        return ProgressReporter(agent_name=agent_name)
    try:
        sink = StdoutJsonlProgressSink(
            run_id=run_id,
            request_id=request_id,
            stream=stream,
        )
    except ValueError as exc:
        logger.warning("Factory live progress disabled: %s", exc)
        return ProgressReporter(agent_name=agent_name)
    return ProgressReporter(
        sink,
        agent_name=agent_name,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )


def run_agent_with_progress(
    agent: Any,
    input_value: Any,
    *,
    config: dict[str, Any],
    reporter: ProgressReporter,
) -> Any:
    """Run one Deep Agent turn and translate streamed events when enabled."""

    if not reporter.enabled:
        return agent.invoke(input_value, config=config)

    final_values: dict[str, Any] | None = None
    for event in agent.stream(
        input_value,
        config=config,
        stream_mode=["updates", "values"],
    ):
        reporter.handle_deep_agent_event(event)
        mode, payload = _unpack_stream_event(event)
        if mode == "values" and isinstance(payload, dict):
            final_values = payload

    if final_values is not None:
        return final_values

    snapshot = agent.get_state(config)
    values = getattr(snapshot, "values", None)
    if not isinstance(values, dict):
        raise RuntimeError("Agent stream completed without a final state.")
    return values


def _unpack_stream_event(event: Any) -> tuple[str | None, Any]:
    if isinstance(event, tuple):
        if len(event) == 2 and isinstance(event[0], str):
            return event[0], event[1]
        if len(event) >= 3 and isinstance(event[-2], str):
            return event[-2], event[-1]
    return None, event


def _event_labels(event: Any) -> set[str]:
    labels: set[str] = set()

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 3:
            return
        if isinstance(value, tuple):
            for item in value:
                visit(item, depth + 1)
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key == "__interrupt__":
                    labels.add(key)
                elif isinstance(key, str) and _SAFE_LABEL_RE.fullmatch(key):
                    labels.add(key)
                if key in {"name", "type", "event"}:
                    if isinstance(item, str) and _SAFE_LABEL_RE.fullmatch(item):
                        labels.add(item)
                elif isinstance(item, Mapping | tuple):
                    visit(item, depth + 1)

    visit(event)
    return labels


def _first_tool_label(labels: set[str]) -> str | None:
    known = {
        "create_staged_agent_package",
        "list_known_agents",
        "list_staged_agents",
        "list_templates",
        "manage_memory",
        "read_staged_review",
        "record_decision",
        "search_memory",
        "search_trusted_sources",
        "tools",
    }
    for label in sorted(labels):
        if label in known or label.startswith(("list_", "read_", "search_")):
            return label
    return None


def _required_agent_name(value: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized or len(normalized) > 120:
        raise ValueError("agent_name must be a non-empty string of at most 120 characters")
    return normalized


def _required_identifier(value: str, *, field: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized or len(normalized) > 80:
        raise ValueError(f"{field} must be a non-empty string of at most 80 characters")
    return normalized


def _validated_event_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in _ALLOWED_EVENT_TYPES:
        raise ValueError(f"unsupported progress event_type: {value!r}")
    if _EVENT_TYPE_RE.fullmatch(normalized) is None:
        raise ValueError(f"invalid progress event_type: {value!r}")
    return normalized


def _validated_phase(value: str) -> str:
    normalized = str(value).strip().lower().replace(" ", "_")
    if _PHASE_RE.fullmatch(normalized) is None:
        raise ValueError(f"invalid progress phase: {value!r}")
    return normalized


def _bounded_summary(value: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized:
        raise ValueError("progress human_summary must not be empty")
    if len(normalized) <= MAX_PROGRESS_SUMMARY_CHARS:
        return normalized
    return normalized[: MAX_PROGRESS_SUMMARY_CHARS - 1].rstrip() + "…"


def _bounded_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in _ALLOWED_METADATA_KEYS:
            continue
        if isinstance(value, bool) or value is None:
            normalized[key] = value
        elif isinstance(value, int | float):
            normalized[key] = value
        elif isinstance(value, str):
            normalized[key] = " ".join(value.split())[
                :MAX_PROGRESS_METADATA_STRING_CHARS
            ]
    return normalized
