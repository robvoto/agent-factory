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


def get_model_defaults() -> dict[str, str]:
    """Return the configured default model strings."""
    settings = _load()
    if "default_model" not in settings:
        raise RuntimeError(f"Missing default_model in {_SETTINGS_FILE}.")
    if "default_coding_model" not in settings:
        raise RuntimeError(f"Missing default_coding_model in {_SETTINGS_FILE}.")
    general_default = settings["default_model"]
    coding_default = settings["default_coding_model"]
    return {
        "general": general_default,
        "coding": coding_default,
    }


def resolve_model(name_or_string: str | None = None, *, purpose: str = "general") -> str:
    """Return the model string for a given alias or literal model string.

    Priority: explicit argument > FACTORY_MODEL env var > purpose default.
    If name_or_string matches a key in config 'models', returns that model string.
    Otherwise treats it as a literal model string (e.g. 'openai:gpt-4.1-mini').
    """
    settings = _load()
    models: dict[str, str] = settings.get("models", {})
    purpose_defaults = get_model_defaults()
    if purpose not in purpose_defaults:
        raise RuntimeError(
            f"Unknown model purpose '{purpose}'. Expected one of: {', '.join(sorted(purpose_defaults))}."
        )

    raw = name_or_string or os.environ.get("FACTORY_MODEL") or purpose_defaults[purpose]
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
