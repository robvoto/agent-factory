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
9. **Progress adapter** — transport-neutral `SpecialistProgressEvent` reporting for Hub-called Factory Brain work and explicitly configured generated agents (`progress_events.py`)

## What lives where

```text
agent-factory/
  src/agent_factory/       # factory logic only
  config/agents/           # enabled agents (read by army)
  staging/agents/          # unapproved drafts
  templates/agent-package/ # base scaffold template
  templates/progress-adapter/ # optional Hub progress capability
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

## Hub progress boundary

When Agent Hub calls Factory Brain, Factory receives Hub `run_id` and `request_id` correlation values and emits versioned progress JSONL on reserved stdout. Normal and debug logs stay on stderr. The existing Factory bridge result and interrupt contract remain unchanged.

Factory translates internal Deep Agent structure into stable external phases such as `design`, `tool`, `approval`, `validation`, `waiting_approval`, `completed`, and `failed`. It does not forward framework-specific events, full prompts, hidden reasoning, raw provider payloads, secrets, or unbounded logs. Quiet liveness heartbeats are deterministic runtime telemetry and make no additional LLM calls.

Agent Hub owns progress persistence, stale detection, cancellation, rate limiting, `/status`, and Telegram presentation. Agent Factory owns only specialist emission and the optional generated-agent adapter.

Generated packages receive the adapter only when `runtime.progress.enabled` is explicitly true and the package is declared Hub-callable or long-running. Manual and short standalone agents do not receive this infrastructure.
