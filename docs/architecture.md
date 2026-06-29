# Architecture

Current technical shape of agent-factory. For product direction, read `platform-architecture.md`.

> **Role:** agent-factory is a specialist agent — it creates, configures, and stages agents. It does NOT orchestrate or run them. `agent-army` is the orchestrator.

## Implemented pieces

1. **AgentManifest / AgentPackageSpec** — Pydantic models for agent spec validation (`agent_spec.py`)
2. **Factory Brain** — LangGraph deep agent that designs and stages packages (`factory_brain.py`)
3. **Factory Tools** — bounded tools: create, promote, approve, delete (`factory_tools.py`)
4. **Agent Catalog** — staged + enabled inventory (`agent_catalog.py`)
5. **Creator Workflow** — deterministic scaffolding from spec (`creator_workflow.py`)
6. **Telegram gateway** — factory admin bot: /staged, /approve, /reject, /promote (`telegram_gateway.py`)
7. **Storage** — SQLite persistence for staged agents and approvals (`storage.py`)
8. **Knowledge store** — factory-scoped knowledge for docs ingestion (`knowledge_store.py`)

## What lives where

```text
agent-factory/
  src/agent_factory/       # factory logic only
  config/agents/           # enabled agents (read by army)
  staging/agents/          # unapproved drafts
  templates/agent-package/ # scaffold template
  docs/
  skills/
```

## Registry contract

Factory writes `config/agents/<id>/agent.json`. Army reads it. Required fields:

| Field | Written by | Read by |
|-------|-----------|---------|
| `id`, `name`, `purpose` | Factory | Army routing |
| `aliases` | Factory | Army dispatch |
| `runtime` | Factory | Army invocation |
| `backlog_sheet_id` | Factory | Army backlog routing |

## Current boundary

`src/agent_factory` is factory logic only. Do not put orchestration, routing, or runtime dispatch code here — those belong in `agent-army`.
