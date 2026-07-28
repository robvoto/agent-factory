from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from agent_factory import factory_brain
from agent_factory.progress_events import ProgressReporter, StdoutJsonlProgressSink


def _events(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


class _FakeAgent:
    def __init__(self, *, interrupted: bool = False, error: BaseException | None = None) -> None:
        self._interrupted = interrupted
        self._error = error
        self.received_inputs: list[Any] = []

    def stream(self, _input_value: Any, *, config: dict[str, Any], stream_mode: list[str]):
        self.received_inputs.append(_input_value)
        assert config["configurable"]["thread_id"] == "thread-1"
        assert stream_mode == ["updates", "values"]
        if self._error is not None:
            raise self._error
        yield ("updates", {"tools": {"name": "list_known_agents"}})
        yield (
            "values",
            {"messages": [SimpleNamespace(content="Factory response")]},
        )

    def get_state(self, _config: dict[str, Any]):
        return SimpleNamespace(
            next=("approval",) if self._interrupted else (),
            values={"messages": [SimpleNamespace(content="Factory response")]},
            interrupts=(
                SimpleNamespace(
                    value={"action_requests": [{"name": "request_approval", "args": {}}]}
                ),
            ),
        )

    def update_state(self, _config: dict[str, Any], _values: dict[str, Any]) -> None:
        return None


def _prepare(monkeypatch: pytest.MonkeyPatch, agent: _FakeAgent) -> None:
    monkeypatch.setattr(factory_brain, "_check_api_key", lambda: None)
    monkeypatch.setattr(factory_brain, "_get_agent", lambda _model: agent)
    monkeypatch.setattr(factory_brain, "_record_llm_run", lambda **_kwargs: None)
    monkeypatch.setattr("agent_factory.factory_settings.resolve_model", lambda *_a, **_k: "test:model")


def _reporter(stream: io.StringIO) -> ProgressReporter:
    return ProgressReporter(
        StdoutJsonlProgressSink(
            run_id="run-1",
            request_id="req-1",
            stream=stream,
        ),
        agent_name="Agent Factory",
        heartbeat_interval_seconds=0,
    )


def test_factory_brain_emits_design_tool_validation_and_completion(monkeypatch) -> None:
    stream = io.StringIO()
    _prepare(monkeypatch, _FakeAgent())

    response, interrupted = factory_brain.invoke_factory_brain(
        "Create an agent",
        thread_id="thread-1",
        progress_reporter=_reporter(stream),
    )

    assert response == "Factory response"
    assert interrupted is False
    phases = [event["phase"] for event in _events(stream)]
    assert phases == ["starting", "design", "tool", "validation", "completed"]


def test_factory_brain_emits_waiting_approval_without_changing_result(monkeypatch) -> None:
    stream = io.StringIO()
    _prepare(monkeypatch, _FakeAgent(interrupted=True))

    response, interrupted = factory_brain.invoke_factory_brain(
        "Create an agent",
        thread_id="thread-1",
        progress_reporter=_reporter(stream),
    )

    assert response == "Factory response"
    assert interrupted is True
    assert _events(stream)[-1]["event_type"] == "waiting"
    assert _events(stream)[-1]["phase"] == "waiting_approval"


def test_factory_brain_emits_generic_failure(monkeypatch) -> None:
    stream = io.StringIO()
    _prepare(monkeypatch, _FakeAgent(error=RuntimeError("SECRET provider payload")))

    with pytest.raises(RuntimeError, match="SECRET provider payload"):
        factory_brain.invoke_factory_brain(
            "Create an agent",
            thread_id="thread-1",
            progress_reporter=_reporter(stream),
        )

    assert _events(stream)[-1]["event_type"] == "failure"
    assert "SECRET provider payload" not in stream.getvalue()


def test_factory_brain_emits_failure_when_runtime_construction_fails(monkeypatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(factory_brain, "_check_api_key", lambda: None)
    monkeypatch.setattr(
        factory_brain,
        "_get_agent",
        lambda _model: (_ for _ in ()).throw(RuntimeError("missing runtime dependency")),
    )
    monkeypatch.setattr(
        "agent_factory.factory_settings.resolve_model",
        lambda *_a, **_k: "test:model",
    )

    with pytest.raises(RuntimeError, match="missing runtime dependency"):
        factory_brain.invoke_factory_brain(
            "Create an agent",
            thread_id="thread-1",
            progress_reporter=_reporter(stream),
        )

    events = _events(stream)
    assert [event["event_type"] for event in events] == ["start", "failure"]
    assert events[-1]["human_summary"] == "Factory Brain could not start. Check the final error."
    assert "missing runtime dependency" not in stream.getvalue()


def test_factory_brain_emits_cancellation(monkeypatch) -> None:
    stream = io.StringIO()
    _prepare(monkeypatch, _FakeAgent(error=KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        factory_brain.invoke_factory_brain(
            "Create an agent",
            thread_id="thread-1",
            progress_reporter=_reporter(stream),
        )

    assert _events(stream)[-1]["phase"] == "cancelled"


def test_factory_brain_resume_and_reject_verify_api_key_before_running(monkeypatch) -> None:
    """resume/reject spawn as a fresh subprocess per dispatch (see AGENT-HUB-007's
    live smoke test) with no guarantee OPENAI_API_KEY is already in the environment —
    they must check for it (and load .env if needed) exactly like invoke does, not
    just assume _get_agent will somehow have credentials."""
    stream = io.StringIO()
    calls: list[str] = []
    monkeypatch.setattr(
        factory_brain, "_check_api_key", lambda: calls.append("checked")
    )
    monkeypatch.setattr(factory_brain, "_get_agent", lambda _model: _FakeAgent())
    monkeypatch.setattr(factory_brain, "_record_llm_run", lambda **_kwargs: None)
    monkeypatch.setattr(
        "agent_factory.factory_settings.resolve_model", lambda *_a, **_k: "test:model"
    )

    factory_brain.resume_factory_brain("thread-1", progress_reporter=_reporter(stream))
    assert calls == ["checked"]

    calls.clear()
    factory_brain.reject_factory_brain(
        "thread-1", reason="no", progress_reporter=_reporter(stream)
    )
    assert calls == ["checked"]


def test_factory_brain_resume_and_reject_send_a_real_hitl_decision(monkeypatch) -> None:
    """The pending interrupt() call in langchain's HumanInTheLoopMiddleware only
    unblocks on Command(resume={"decisions": [...]}) — resuming with plain None
    (the previous behavior) never actually communicates approve/reject, so the
    agent just re-hits the same interrupt. This proves the real payload shape,
    with one decision per pending action_request, reaches agent.stream()."""
    from langgraph.types import Command

    stream = io.StringIO()
    resume_agent = _FakeAgent()
    _prepare(monkeypatch, resume_agent)
    factory_brain.resume_factory_brain("thread-1", progress_reporter=_reporter(stream))

    sent = resume_agent.received_inputs[-1]
    assert isinstance(sent, Command)
    assert sent.resume == {"decisions": [{"type": "approve"}]}

    reject_agent = _FakeAgent()
    _prepare(monkeypatch, reject_agent)
    factory_brain.reject_factory_brain(
        "thread-1", reason="Do not create it", progress_reporter=_reporter(stream)
    )

    sent = reject_agent.received_inputs[-1]
    assert isinstance(sent, Command)
    assert sent.resume == {"decisions": [{"type": "reject", "message": "Do not create it"}]}


def test_factory_brain_resume_emits_approval_and_completion(monkeypatch) -> None:
    stream = io.StringIO()
    _prepare(monkeypatch, _FakeAgent())

    response, interrupted = factory_brain.resume_factory_brain(
        "thread-1",
        progress_reporter=_reporter(stream),
    )

    assert response == "Factory response"
    assert interrupted is False
    assert [event["phase"] for event in _events(stream)] == [
        "starting",
        "approval",
        "tool",
        "validation",
        "completed",
    ]


def test_factory_brain_reject_emits_safe_completion(monkeypatch) -> None:
    stream = io.StringIO()
    _prepare(monkeypatch, _FakeAgent())

    response = factory_brain.reject_factory_brain(
        "thread-1",
        reason="Do not create it",
        progress_reporter=_reporter(stream),
    )

    assert response == "Factory response"
    assert [event["phase"] for event in _events(stream)] == [
        "starting",
        "approval",
        "tool",
        "validation",
        "completed",
    ]
    assert "Do not create it" not in stream.getvalue()
