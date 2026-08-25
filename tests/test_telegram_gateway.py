"""Tests for Telegram command routing."""

from __future__ import annotations

from agent_factory import telegram_gateway


def test_new_command_starts_fresh_session(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(telegram_gateway, "reset_thread", lambda chat_id: calls.append(("reset", chat_id)) or "fresh-thread")
    monkeypatch.setattr(telegram_gateway, "_send", lambda token, chat_id, text: calls.append(("send", text)))

    telegram_gateway._handle_update(
        "token",
        {"123"},
        {"message": {"chat": {"id": 123}, "text": "/new"}, "update_id": 1},
        purpose="coding",
    )

    assert calls[0] == ("reset", "123")
    assert calls[1][0] == "send"
    assert "Factory Brain" in calls[1][1]
    assert "new session started" in calls[1][1]


def test_approve_design_research_uses_generic_approval_path(monkeypatch):
    calls: list[tuple] = []
    record = {
        "id": 17,
        "approval_type": "design-research",
        "target_id": "factory-design",
        "summary": '{"question":"Which BPMN editor?","allowed_domains":["bpmn.io"]}',
        "status": "pending",
    }

    monkeypatch.setattr(telegram_gateway, "get_approval", lambda approval_id: record if approval_id == 17 else None)
    monkeypatch.setattr(
        telegram_gateway,
        "decide_approval",
        lambda approval_id, decision, reason="": calls.append(("decide", approval_id, decision, reason)),
    )
    monkeypatch.setattr(
        telegram_gateway,
        "_promote_agent",
        lambda agent_id: (_ for _ in ()).throw(AssertionError("design research must not enter promotion path")),
    )
    monkeypatch.setattr(
        telegram_gateway,
        "_send",
        lambda token, chat_id, text: calls.append(("send", text)),
    )

    telegram_gateway._cmd_approve("token", "123", "17")

    assert ("decide", 17, "approved", "Approved via Telegram") in calls
    assert ("send", "Approval 17 approved.") in calls


def test_reject_design_research_uses_generic_approval_path(monkeypatch):
    calls: list[tuple] = []
    record = {
        "id": 18,
        "approval_type": "design-research",
        "target_id": "factory-design",
        "summary": '{"question":"Which BPMN editor?","allowed_domains":["bpmn.io"]}',
        "status": "pending",
    }

    monkeypatch.setattr(telegram_gateway, "get_approval", lambda approval_id: record if approval_id == 18 else None)
    monkeypatch.setattr(
        telegram_gateway,
        "decide_approval",
        lambda approval_id, decision, reason="": calls.append(("decide", approval_id, decision, reason)),
    )
    monkeypatch.setattr(
        telegram_gateway,
        "_send",
        lambda token, chat_id, text: calls.append(("send", text)),
    )

    telegram_gateway._cmd_reject("token", "123", "18 Not needed")

    assert ("decide", 18, "rejected", "Not needed") in calls
    assert ("send", "Approval 18 rejected. Reason: Not needed") in calls
