"""Tests for model selection and defaults."""

from __future__ import annotations

import json
from pathlib import Path

from agent_factory import factory_settings


def _write_settings(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "model_environment": {
                    "general": "FACTORY_GENERAL_MODEL",
                    "coding": "FACTORY_CODING_MODEL",
                    "global": "FACTORY_MODEL",
                },
                "models": {
                    "codex": "openai:o4-mini",
                    "luna": "openai:gpt-5.6-luna",
                    "mini": "openai:gpt-4.1-mini",
                    "claude": "anthropic:claude-sonnet-4-6",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_resolve_model_uses_general_and_coding_defaults(tmp_path, monkeypatch):
    settings_file = tmp_path / "factory_settings.json"
    _write_settings(settings_file)
    monkeypatch.setattr(factory_settings, "_SETTINGS_FILE", settings_file)
    monkeypatch.setenv("FACTORY_GENERAL_MODEL", "luna")
    monkeypatch.setenv("FACTORY_CODING_MODEL", "codex")
    monkeypatch.delenv("FACTORY_MODEL", raising=False)

    assert factory_settings.resolve_model(purpose="general") == "openai:gpt-5.6-luna"
    assert factory_settings.resolve_model(purpose="coding") == "openai:o4-mini"


def test_resolve_model_honors_aliases_and_literals(tmp_path, monkeypatch):
    settings_file = tmp_path / "factory_settings.json"
    _write_settings(settings_file)
    monkeypatch.setattr(factory_settings, "_SETTINGS_FILE", settings_file)
    monkeypatch.delenv("FACTORY_MODEL", raising=False)

    assert factory_settings.resolve_model("mini") == "openai:gpt-4.1-mini"
    assert factory_settings.resolve_model("anthropic:claude-opus-4-8") == "anthropic:claude-opus-4-8"


def test_resolve_model_rejects_unknown_purpose(tmp_path, monkeypatch):
    settings_file = tmp_path / "factory_settings.json"
    _write_settings(settings_file)
    monkeypatch.setattr(factory_settings, "_SETTINGS_FILE", settings_file)
    monkeypatch.delenv("FACTORY_MODEL", raising=False)

    try:
        factory_settings.resolve_model(purpose="research")
    except RuntimeError as exc:
        assert "Unknown model purpose" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for unknown purpose")


def test_get_model_defaults_and_aliases(tmp_path, monkeypatch):
    settings_file = tmp_path / "factory_settings.json"
    _write_settings(settings_file)
    monkeypatch.setattr(factory_settings, "_SETTINGS_FILE", settings_file)

    defaults = factory_settings.get_model_defaults()
    aliases = factory_settings.list_model_aliases()

    assert defaults == {"general": "<not configured>", "coding": "<not configured>"}
    assert aliases["codex"] == "openai:o4-mini"


def test_resolve_model_fails_closed_when_runtime_model_is_missing(tmp_path, monkeypatch):
    settings_file = tmp_path / "factory_settings.json"
    _write_settings(settings_file)
    monkeypatch.setattr(factory_settings, "_SETTINGS_FILE", settings_file)
    monkeypatch.delenv("FACTORY_MODEL", raising=False)
    monkeypatch.delenv("FACTORY_GENERAL_MODEL", raising=False)
    monkeypatch.delenv("FACTORY_CODING_MODEL", raising=False)

    try:
        factory_settings.resolve_model(purpose="general")
    except RuntimeError as exc:
        assert "No runtime model configured" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when runtime model is missing")


def test_get_telegram_bot_config_without_bots_raises(tmp_path, monkeypatch):
    settings_file = tmp_path / "factory_settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "model_environment": {
                    "general": "FACTORY_GENERAL_MODEL",
                    "coding": "FACTORY_CODING_MODEL",
                    "global": "FACTORY_MODEL",
                },
                "models": {},
                "telegram_bots": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(factory_settings, "_SETTINGS_FILE", settings_file)

    try:
        factory_settings.get_telegram_bot_config()
    except RuntimeError as exc:
        assert "No telegram_bots configured" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when no telegram_bots are configured")
