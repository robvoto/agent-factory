# Data Classification and Git Policy

Decision item: AF-025. Defines what belongs in Git, what is runtime state, and what is local-only.

## File classes

| Class | Description | Git? | Location |
|-------|-------------|------|----------|
| **Source seed** | Committed reference data agents read at startup | Yes | `data/` (JSON/YAML seeds only) |
| **Config (shared)** | Committed non-secret settings shared across installs | Yes | `config/` |
| **Config (local)** | Per-machine settings with real tokens/IDs | No | `data/settings.local.json` (gitignored) |
| **Runtime DB** | SQLite databases created at runtime | No | `data/*.sqlite3` |
| **Generated output** | Diagrams, reports, rendered SVGs | No (mostly) | `docs/diagrams/*.svg` (except approved previews) |
| **Logs** | Rolling log files | No | `data/*.log` or `logs/` |
| **Environment files** | `.env`, token/key files | No | `.env`, `env/` |
| **Production backup** | DB exports for recovery | No | Outside repo, separate volume |

## Decision rules for common file types

### Prompts and agent specs

- `templates/agent-package/` — committed source templates
- `staging/agents/<id>/` — **committed**; draft packages staged for review before promotion
- `config/agents/<id>/agent.json` — **committed** after human-approved promotion

### Settings

- `config/factory_settings.json` — committed; contains model aliases and bot config keys only, no real tokens
- `data/settings.local.json` — **not committed**; contains real token values and chat IDs
- Always provide `data/settings.local.example.json` as a safe committed example

### SQLite databases

All SQLite databases under `data/` are **runtime state** and must not be committed:

| File | Purpose |
|------|---------|
| `data/agent_factory.sqlite3` | Staged agents, approvals, Telegram threads |
| `data/factory_checkpoints.sqlite3` | LangGraph conversation checkpoints |
| `data/knowledge_store.sqlite3` | Shared knowledge (may grow large) |

Created automatically by the app on first run. Use `uv run agent-factory setup` to initialise.

### Logs and generated data

- `data/llm_usage.json` — gitignored; runtime cost tracking
- `data/*.log` — gitignored
- `docs/diagrams/*.svg` — committed only when they are approved static previews (not CLI-generated outputs)

## What to do when unsure

1. Check this table
2. If still unsure, put the file in `data/` and add it to `.gitignore` — committing runtime data is worse than ignoring a source file
3. If a source file must be committed but was accidentally ignored, remove the ignore rule and add the file explicitly
4. Never commit `.env`, local settings, SQLite DBs, logs, or production credentials

## Gitignore summary

The following patterns are enforced in `.gitignore`:

```
data/*.sqlite3
data/*.json           # runtime; use setup for seeds
*.sqlite3
*.sqlite3-journal
*.log
.env
env/
data/settings.local*.json
staging/agents/
```

Committed exceptions (must be explicit git-add):

```
config/agents/<id>/agent.json
config/factory_settings.json
data/settings.local.example.json
templates/
```

## Coding-agent handoff rule

Before any change to `.gitignore`, `data/`, `config/`, `staging/`, or `templates/`,
the coding agent must reference this document and confirm whether the file belongs
to one of the classes above. If unsure, stop and ask the operator.
