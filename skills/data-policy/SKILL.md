---
name: data-policy
description: How to classify files, manage settings safely, and keep Git clean
---

# Skill: Data Policy

How to classify files, manage settings safely, and keep Git clean.

## Before touching any of these — read the doc first

- `docs/data-classification.md` — full file class table
- `docs/settings-hygiene.md` — safe settings pattern

## Quick reference: what goes in Git

| Committed | Not committed |
|-----------|--------------|
| `config/agents/<id>/agent.json` | `data/*.sqlite3` |
| `config/factory_settings.json` | `data/llm_usage.json` |
| `data/settings.local.example.json` | `data/settings.local.json` |
| `staging/agents/` (draft packages) | `.env` |
| `templates/`, `docs/`, `src/` | `data/*.log` |

## The settings file pair rule

Every repo must have:
1. `data/settings.local.example.json` — **committed**, safe placeholder values only
2. `data/settings.local.json` — **gitignored**, real local values

If `data/settings.local.json` is missing → run `uv run agent-factory setup`.
Never put tokens, chat IDs, or API keys in committed files.

## Gitignore rules in force

```
data/*.sqlite3
data/llm_usage.json
data/settings.local*.json
!data/settings.local.example.json
```

## When to run doctor

Run `uv run agent-factory doctor` to verify:
- All required dirs exist
- Settings files are present and gitignored correctly
- SQLite tables are initialised
- Manifest builds without error

Run `uv run agent-factory setup` first if doctor reports missing dirs or settings.

## Coding-agent rule

Before any change to `.gitignore`, `data/`, `staging/`, `config/`, or `templates/`:
1. Check `docs/data-classification.md`
2. Confirm which class the file belongs to
3. If unsure: stop and ask — committing runtime data is worse than ignoring a source file

## CI enforcement

`tests/test_data_policy.py` runs on every commit and checks:
- SQLite, env, local settings, and llm_usage are gitignored
- `data/settings.local.example.json` exists and has no real secrets
- All `config/agents/*/agent.json` files are valid and have required fields
