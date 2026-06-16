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

