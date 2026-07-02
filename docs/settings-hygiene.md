# Local Settings and Environment Hygiene

Decision item: AF-031. Defines the safe pattern for local settings across all agent repos.

## Rule

Every setting that varies per machine or contains a private value (token, chat ID,
path) lives in a **local settings file that is gitignored**. A **committed example**
with safe placeholder values shows operators what to fill in.

## Standard file pair

| File | Committed? | Purpose |
|------|-----------|---------|
| `data/settings.local.example.json` | Yes | Safe template; no real values |
| `data/settings.local.json` | No (gitignored) | Real local values |

The gitignore rule `data/settings.local*.json` covers both the real file and any
dated backups (`settings.local.2026-06-01.json`).

## What must NOT be in committed settings

- Telegram bot tokens (`TELEGRAM_*_TOKEN` values)
- Chat IDs or user IDs
- API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)
- Absolute WSL paths to private directories
- Production database credentials

## What may be committed

- Model alias definitions (no keys)
- Bot name and `token_env` / `allowed_chat_ids_env` variable names (not values)
- Default feature flags that are safe to share

## Startup behaviour

If the real settings file is missing the app must:

1. Log a human-readable error explaining which file is missing
2. Tell the operator to copy the example: `cp data/settings.local.example.json data/settings.local.json`
3. Stop; do not silently fall back to the example or use empty defaults for security-sensitive values

## Environment variables

Secrets must be injected via environment variables, not committed files.
Use `.env` (gitignored) for local development and the OS environment for production.

Never read `.env` from code directly — use `python-dotenv` or a startup wrapper only.
Never commit `.env`, even if it only contains non-secret defaults.

## Validation in doctor command

`uv run agent-factory doctor` checks:

- `data/settings.local.json` exists and is gitignored
- `data/settings.local.example.json` exists and is committed
- No token values appear in committed files
- `.env` is gitignored
