from __future__ import annotations

import io
import json
import time
from types import SimpleNamespace
from typing import Any

from agent_factory.progress_events import (
    ProgressReporter,
    StdoutJsonlProgressSink,
    progress_reporter_from_ids,
    run_agent_with_progress,
)


def _events(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_stdout_progress_is_correlated_monotonic_and_bounded() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(
        StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name="Test Agent",
    )

    reporter.started()
    reporter.phase(
        "design",
        "Designing the package.",
        {"adapter": "deep_agent", "secret": "must not pass"},
    )

    events = _events(stream)
    assert [event["sequence"] for event in events] == [1, 2]
    assert all(event["run_id"] == "run-1" for event in events)
    assert all(event["request_id"] == "req-1" for event in events)
    assert events[1]["metadata"] == {"adapter": "deep_agent"}
    assert "secret" not in stream.getvalue().lower()


class _BrokenStream:
    def write(self, _value: str) -> int:
        raise BrokenPipeError("closed")

    def flush(self) -> None:
        raise AssertionError("flush should not run")


def test_broken_pipe_disables_progress_without_breaking_work() -> None:
    sink = StdoutJsonlProgressSink(
        run_id="run-1",
        request_id="req-1",
        stream=_BrokenStream(),  # type: ignore[arg-type]
    )
    reporter = ProgressReporter(sink, agent_name="Test Agent")

    assert reporter.started() is False
    assert reporter.phase("working", "Still working.") is False
    assert sink.enabled is False


def test_missing_correlation_uses_noop_sink() -> None:
    stream = io.StringIO()
    reporter = progress_reporter_from_ids(
        run_id=None,
        request_id="req-1",
        stream=stream,
        agent_name="Test Agent",
    )

    assert reporter.enabled is False
    assert reporter.started() is False
    assert stream.getvalue() == ""


def test_deep_agent_events_map_without_forwarding_payloads() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(
        StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name="Test Agent",
    )

    reporter.handle_deep_agent_event(
        (
            "updates",
            {
                "tools": {
                    "name": "create_staged_agent_package",
                    "raw_payload": "SECRET RAW PROVIDER PAYLOAD",
                }
            },
        )
    )
    reporter.handle_deep_agent_event(("updates", {"__interrupt__": {"reason": "SECRET"}}))

    events = _events(stream)
    assert events[0]["phase"] == "staging"
    assert events[1]["phase"] == "waiting_approval"
    assert "SECRET RAW PROVIDER PAYLOAD" not in stream.getvalue()
    assert '"reason"' not in stream.getvalue()


def test_simple_agent_and_deterministic_adapters_share_schema() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(
        StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name="Test Agent",
    )

    reporter.phase(
        "deterministic_step",
        "Running deterministic validation.",
        {"adapter": "deterministic_workflow"},
    )
    reporter.handle_simple_agent_event({"event": "tool_start", "payload": "SECRET"})

    events = _events(stream)
    assert events[0]["metadata"] == {"adapter": "deterministic_workflow"}
    assert events[1]["phase"] == "tool"
    assert events[1]["metadata"] == {"adapter": "simple_agent"}
    assert "SECRET" not in stream.getvalue()


def test_quiet_work_emits_deterministic_heartbeat() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(
        StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name="Test Agent",
        heartbeat_interval_seconds=0.02,
    )
    reporter.phase("design", "Designing the package.")

    with reporter.heartbeat_scope():
        time.sleep(0.08)

    assert any(event["event_type"] == "heartbeat" for event in _events(stream))


class _StreamAgent:
    def __init__(self) -> None:
        self.invoke_called = False

    def stream(self, input_value: Any, *, config: dict[str, Any], stream_mode: list[str]):
        assert input_value == {"messages": ["hello"]}
        assert config["configurable"]["thread_id"] == "thread-1"
        assert stream_mode == ["updates", "values"]
        yield ("updates", {"tools": {"name": "list_known_agents"}})
        yield (
            "values",
            {"messages": [SimpleNamespace(content="done")]},
        )

    def invoke(self, _input_value: Any, *, config: dict[str, Any]):
        self.invoke_called = True
        return {"messages": [SimpleNamespace(content="fallback")]}

    def get_state(self, _config: dict[str, Any]):
        return SimpleNamespace(values={"messages": [SimpleNamespace(content="state")]})


def test_run_agent_with_progress_uses_one_streamed_turn() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(
        StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name="Test Agent",
    )
    agent = _StreamAgent()

    result = run_agent_with_progress(
        agent,
        {"messages": ["hello"]},
        config={"configurable": {"thread_id": "thread-1"}},
        reporter=reporter,
    )

    assert result["messages"][-1].content == "done"
    assert agent.invoke_called is False
    assert _events(stream)[0]["phase"] == "tool"


def test_run_agent_without_progress_preserves_invoke_path() -> None:
    agent = _StreamAgent()
    reporter = ProgressReporter(agent_name="Test Agent")

    result = run_agent_with_progress(
        agent,
        {"messages": ["hello"]},
        config={"configurable": {"thread_id": "thread-1"}},
        reporter=reporter,
    )

    assert result["messages"][-1].content == "fallback"
    assert agent.invoke_called is True
