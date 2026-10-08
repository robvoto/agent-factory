# Architecture

Current technical shape of agent-factory. For product direction, read `platform-architecture.md`.

> **Role:** agent-factory is the lifecycle service — it creates, validates, stages, and governs released agents. It does NOT orchestrate or run them. `agent-hub` is the orchestrator.

## Lifecycle placement

Factory-owned standard agents may remain in this repository after promotion. An agent
is implemented in a separate specialist repository only after an explicit human and
architecture decision that it has genuine independent engineering needs. Graduation is
not automatic, and promotion means release and enablement rather than graduation.

For an independent product agent, the specialist repository owns implementation,
dependencies, implementation tests, and implementation release work. Factory continues
to own and gate the registry entry, release contract, permissions, promotion, activation
metadata, and governed upgrades. Agent Hub consumes the enabled release definition and
runs or orchestrates it; it is not the development home.

## Implemented pieces

1. **AgentManifest / AgentPackageSpec** — Pydantic models for agent spec validation (`agent_spec.py`)
2. **MCP capability boundary** — explicit approval-registry validation and runtime handle selection (`mcp.py`); no provider discovery or execution
3. **Factory Brain** — LangGraph Deep Agent that designs and stages packages (`factory_brain.py`); Factory Brain was already implemented as a Deep Agent before AF-050. AF-050 hardens its packaging, permissions, persistence, and security boundaries rather than migrating it to Deep Agents. Its declared `langchain` dependency set includes SQLite checkpoint support, and `agent-factory doctor` validates that runtime before use. Runtime safety limits are centrally configured in `config/factory_settings.json`: Deep Agent turns use an explicit graph recursion limit, while provider calls use explicit timeout and retry caps so permissive framework defaults cannot leave a bad design or research turn effectively unbounded.
4. **Factory Tools** — bounded tools: create, prepare/approve implementation handoffs, promote, approve, delete (`factory_tools.py`)
5. **Agent Catalog** — staged + enabled inventory (`agent_catalog.py`)
6. **Creator Workflow** — deterministic scaffolding from spec (`creator_workflow.py`)
7. **Telegram gateway** — factory admin bot: /staged, /approve, /reject, /promote (`telegram_gateway.py`)
8. **Storage** — SQLite persistence for staged agents and approvals (`storage.py`)
9. **Knowledge store** — factory-scoped knowledge for docs ingestion (`knowledge_store.py`)
10. **Progress adapter** — transport-neutral `SpecialistProgressEvent` reporting for Hub-called Factory Brain work and explicitly configured generated agents (`progress_events.py`)
11. **AF-048 build-task/build-result boundary** — strict staged `BUILD_TASK.json` and Factory-owned `BUILD_RESULT.json` artifacts, SQLite thread/correlation lifecycle persistence, deterministic ATL BuildResult v1 validation, promotion gating, and a structured specialist-result wrapper (`build_task.py`, `build_result.py`, `storage.py`, `agent_catalog.py`, `factory_brain.py`)

## What lives where

```text
agent-factory/
  src/agent_factory/       # factory logic only
  agents/                  # approved Factory-owned released packages
  config/agents/           # enabled release manifests (read by Agent Hub)
  staging/agents/          # incubation/review drafts only
  templates/agent-package/ # base scaffold template
  templates/progress-adapter/ # optional Hub progress capability
  # independent product implementations live in their own specialist repositories after graduation
  docs/
  skills/
```

## Registry contract

Factory releases the validated package under `agents/<id>/`, then writes and
activates `config/agents/<id>.json` from that released package. Agent Hub reads
the registry entry. Required fields:

| Field | Written by | Read by |
|-------|-----------|---------|
| `id`, `name`, `purpose` | Factory | Agent Hub routing |
| `aliases` | Factory | Human-facing command shortcuts (not Agent Hub routing) |
| `runtime` | Factory | Agent Hub invocation |
| `input_contract`, `interaction_contract`, `task_contract` | Factory | Agent Hub universal dispatch/capability discovery |
| `extensions` (e.g. a backlog pointer) | Factory | Specialist's own tooling — Agent Hub does not interpret it |
| `target_project_access` | Factory | Generic explicit-target authorization and creation contract for project-root specialists |
| `mcp_servers` | Factory | External runtime capability authorization; Factory validates and selects handles, but does not execute MCP tools |

## Current boundary

`src/agent_factory` is factory logic only. Do not put orchestration, routing, or runtime dispatch code here — those belong in `agent-hub`.

Factory may modify or rebuild incubating packages and may propose upgrades, but it must
not silently self-modify a released independent product implementation. Changes to
permissions, tools or capability declarations, the runtime contract, manifest-governed
model or cost limits, or the active release version require Factory validation and
explicit human approval before activation. Release rollback reactivates a previously
validated release through the registry; it does not restore arbitrary filesystem
snapshots.

Factory does not dispatch the task, call AI Tech Lead/Codex/Claude, or make a direct
Factory-to-ATL call. Agent Hub routes the approved task and returns ATL BuildResult
v1 under the same Factory thread/correlation. Factory then performs strict schema,
task, manifest, changed-path, test, budget, and staged-package validation before
persisting `BUILD_RESULT.json` and marking the exact task `validated`. Promotion
still requires the existing separate human approval; only that path creates the
released `agents/<id>/` package home and registry entry. The Hub relay that returns
BuildResult remains a cross-project integration boundary and is not claimed complete
by this repository change.

## Hub progress boundary

When Agent Hub calls Factory Brain, Factory receives Hub `run_id` and `request_id` correlation values and emits versioned progress JSONL on reserved stdout. Normal and debug logs stay on stderr. The existing Factory bridge result and interrupt contract remain unchanged.

Factory translates internal Deep Agent structure into stable external phases such as `design`, `tool`, `approval`, `validation`, `waiting_approval`, `completed`, and `failed`. It does not forward framework-specific events, full prompts, hidden reasoning, raw provider payloads, secrets, or unbounded logs. Quiet liveness heartbeats are deterministic runtime telemetry and make no additional LLM calls.

Agent Hub owns progress persistence, stale detection, cancellation, rate limiting, `/status`, and Telegram presentation. Agent Factory owns only specialist emission and the optional generated-agent adapter.

Generated packages receive the adapter only when `runtime.progress.enabled` is explicitly true and the package is declared Hub-callable or long-running. Manual and short standalone agents do not receive this infrastructure.
