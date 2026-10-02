"""Loader for config/factory_settings.json — models and telegram bot configs."""

from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[2]
_SETTINGS_FILE = _PROJECT_ROOT / "config" / "factory_settings.json"


def _load() -> dict:
    if not _SETTINGS_FILE.exists():
        return {}
    return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))


def _model_environment(settings: dict) -> dict[str, str]:
    configured = settings.get("model_environment")
    if not isinstance(configured, dict):
        raise RuntimeError(f"Missing model_environment in {_SETTINGS_FILE}.")
    required = {"general", "coding", "global"}
    if set(configured) != required or any(
        not isinstance(value, str) or not value.strip() for value in configured.values()
    ):
        raise RuntimeError(
            f"model_environment in {_SETTINGS_FILE} must define general, coding, and global environment variables."
        )
    return {key: value.strip() for key, value in configured.items()}


def _runtime_model_name(settings: dict, *, purpose: str) -> str:
    environment = _model_environment(settings)
    specific = os.environ.get(environment[purpose], "").strip()
    global_model = os.environ.get(environment["global"], "").strip()
    raw = specific or global_model
    if not raw:
        raise RuntimeError(
            f"No runtime model configured for purpose '{purpose}'. Set "
            f"{environment[purpose]} or {environment['global']}."
        )
    return raw


def get_model_defaults() -> dict[str, str]:
    """Return the models currently selected by runtime configuration."""
    settings = _load()
    environment = _model_environment(settings)
    global_model = os.environ.get(environment["global"], "").strip()
    return {
        "general": os.environ.get(environment["general"], "").strip() or global_model or "<not configured>",
        "coding": os.environ.get(environment["coding"], "").strip() or global_model or "<not configured>",
    }


def resolve_model(name_or_string: str | None = None, *, purpose: str = "general") -> str:
    """Return the model string for a given alias or literal model string.

    Priority: explicit argument > purpose-specific runtime env var > global runtime env var.
    If name_or_string matches a key in config 'models', returns that model string.
    Otherwise treats it as a literal model string (e.g. 'openai:gpt-4.1-mini').
    """
    settings = _load()
    models: dict[str, str] = settings.get("models", {})
    environment = _model_environment(settings)
    if purpose not in {"general", "coding"}:
        raise RuntimeError(
            f"Unknown model purpose '{purpose}'. Expected one of: general, coding."
        )

    raw = name_or_string or _runtime_model_name(settings, purpose=purpose)
    return models.get(raw, raw)


def list_model_aliases() -> dict[str, str]:
    """Return the configured model alias map."""
    settings = _load()
    models: dict[str, str] = settings.get("models", {})
    return dict(models)


def get_telegram_bot_config(bot_name: str | None = None) -> dict:
    """Return {token, allowed_chat_ids} for the named bot (or the first bot if name is None).

    Reads token and chat IDs from environment variables specified in the bot config.
    Raises RuntimeError if the bot is not found or env vars are missing.
    """
    settings = _load()
    bots: list[dict] = settings.get("telegram_bots", [])

    if not bots:
        raise RuntimeError(f"No telegram_bots configured in {_SETTINGS_FILE}.")

    if bot_name:
        matched = next((b for b in bots if b["name"] == bot_name), None)
        if not matched:
            names = [b["name"] for b in bots]
            raise RuntimeError(f"Telegram bot '{bot_name}' not in config. Available: {names}")
        bot = matched
    else:
        bot = bots[0]

    token = os.environ.get(bot["token_env"], "").strip()
    raw_ids = os.environ.get(bot["allowed_chat_ids_env"], "").strip()

    if not token:
        raise RuntimeError(
            f"Telegram bot '{bot['name']}': env var {bot['token_env']} is not set."
        )
    if not raw_ids:
        raise RuntimeError(
            f"Telegram bot '{bot['name']}': env var {bot['allowed_chat_ids_env']} is not set."
        )

    allowed_ids = {cid.strip() for cid in raw_ids.split(",") if cid.strip()}
    return {"name": bot["name"], "token": token, "allowed_chat_ids": allowed_ids}


def list_bot_names() -> list[str]:
    settings = _load()
    return [b["name"] for b in settings.get("telegram_bots", [])]
