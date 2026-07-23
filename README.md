# Agent Factory

Creates, configures, and stages AI agent packages. Does **not** orchestrate or dispatch tasks.

## Role

Agent Factory is a **specialist agent** in the platform. Its job is:

- Design and stage agent packages on request
- Validate manifests, tools, permissions, and memory policy
- Enable agents only after human approval
- Track the agent lifecycle (staged → approved → enabled)

**Agent Hub (`agent-hub`) is the orchestrator and entry point for users.**
Factory is called by Agent Hub when an agent-creation task is requested.

## Related repos

| Repo | Role |
|------|------|
| `agent-hub` | Orchestrator / runtime / control plane — **main entry point** |
| `agent-factory` (this repo) | Creates, configures, and stages agents only |
| `ai-tech-lead` | Specialist coding agent |

## Agent registry

Enabled agents live in `config/agents/<id>/agent.json`. Agent Hub reads from here.

Staged (unapproved) drafts live in `staging/agents/`.

## Quick start

```bash
cd ~/projects/agent-factory
uv sync --all-extras
uv run agent-factory setup
uv run agent-factory doctor
uv run pytest
uv run agent-factory list
```

## Factory Brain

The Factory Brain is a LangGraph deep agent that designs and stages agent packages.
It requires `OPENAI_API_KEY` in `.env` and the `langchain` optional dependency set, which includes SQLite checkpoint support. `uv run agent-factory doctor` verifies that runtime before Factory Brain is invoked.

```bash
uv run agent-factory factory "Create an agent that researches LangChain docs safely"
```

## Telegram (factory admin bot)

```bash
uv run agent-factory telegram
```

Factory's Telegram bot handles factory admin commands only:
`/staged`, `/pending`, `/approve`, `/reject`, `/create`, `/promote`, `/delete`.

This is **not** the main user bot — that is Agent Hub's Telegram gateway.

## Key commands

```bash
uv run agent-factory list          # list enabled agents
uv run agent-factory manifest      # print compact machine-readable factory handshake
uv run agent-factory staged        # list staged drafts
uv run agent-factory pending       # list pending approvals
uv run agent-factory create "..."  # create staged draft (deterministic, no LLM)
uv run agent-factory factory "..." # invoke Factory Brain (LLM)
uv run agent-factory approve <id>  # approve a pending action
uv run agent-factory reject <id>   # reject a pending action
uv run agent-factory promote <id>  # request promotion to config/agents
```

## Key files

- `src/agent_factory/factory_brain.py` — Factory Brain agent
- `src/agent_factory/factory_tools.py` — bounded tools (create, promote, approve)
- `src/agent_factory/agent_spec.py` — Pydantic spec validation
- `src/agent_factory/agent_catalog.py` — staged + enabled inventory
- `src/agent_factory/telegram_gateway.py` — factory admin Telegram bot
- `src/agent_factory/storage.py` — SQLite persistence
- `templates/agent-package/` — agent package template
- `staging/agents/` — staged (unapproved) drafts
- `config/agents/` — enabled agents (read by Agent Hub)

## Backlog

https://docs.google.com/spreadsheets/d/1outLuOWhd-A7uvzsl9C2Jc-tKpsyci9HPZalxcmFiOg/edit

## Key docs

- `docs/agent-lifecycle.md`
- `docs/agent-creator-workflow.md`
- `docs/agent-contract.md`
- `docs/permission-model.md`
- `docs/platform-architecture.md`
