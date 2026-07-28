# Agent Registry and Discovery Contract

Decision item: AF-047. Defines how Agent Hub discovers agents that Factory has created.

## Decision

Agent discovery is **registry-driven**. Agent Hub reads from `config/agents/` or calls
`uv run agent-factory manifest`. No folder scanning, GitHub scanning, or hidden
auto-discovery. An agent does not exist for Agent Hub until it has an approved entry
in `config/agents/`.

## Registry structure

```
config/agents/
  <agent-id>/
    agent.json        ← agent spec (committed, version-controlled)
    AGENTS.md         ← agent-specific instructions (optional)
```

Every enabled agent has exactly one `agent.json`. The file is committed by Factory
during promotion. Agent Hub reads it directly or via the manifest.

## agent.json required fields

| Field | Description |
|-------|-------------|
| `id` | Unique stable identifier (kebab-case) |
| `name` | Human-readable display name |
| `purpose` | Single structured routing contract used by Hub |
| `aliases` | Short human-facing command words (e.g. `["code", "atl"]`) — not used for Agent Hub routing |
| `tools` | Array of tool IDs the agent may use |
| `permissions` | `network`, `filesystem`, `shell`, `requires_approval`, `allowed_roots` |
| `memory` | `scope`, `retention` |
| `runtime` | `mode`, `entrypoint`, `working_directory`, `input_arg`, `output_arg` |
| `output_contract` | Required for `runtime.mode = "subprocess"`; declares the validated subprocess status contract |
| `input_contract` / `interaction_contract` | Universal Hub task-envelope declaration and advertised lifecycle capabilities (optional; see `agent-contract.md`) |
| `task_contract` | Optional bounded task kinds the specialist declares it accepts |
| `project_context_contract` | Factory-side project-context participation: supported schema versions, whether a target project is required, consumed capabilities, enforced filesystem permission (optional; see "Project-context contract" in `agent-contract.md`) |
| `target_project_access` | Optional explicit-target authorization and target-creation contract for `project_root`-oriented specialists |

Any other top-level field (e.g. a backlog sheet ID) is specialist-owned
metadata, not a required registry field — see `extensions` in `agent-contract.md`.

## How Agent Hub discovers agents

### Option A — read manifest (preferred for remote/cached use)

```bash
uv run agent-factory manifest
```

Returns JSON including `live_registry.enabled_agents[]` — a compact list of
`{id, name, purpose, aliases, runtime_entrypoint, requires_approval}` for
every enabled agent. Cache for up to `hub_integration.handshake_ttl_seconds`
(default 3600 s). Re-call when TTL expires or after a promotion event.

### Option B — read registry files directly (preferred for local/trusted use)

```
config/agents/<id>/agent.json
```

Agent Hub reads each `agent.json` for full spec details. Suitable when Agent Hub runs
on the same machine and can access the factory repo.

## Lifecycle gate

An agent enters the registry only after:

1. Factory creates a staged package in `staging/agents/`
2. Human approval is granted (via `uv run agent-factory approve <id>`)
3. Factory promotes the package to `config/agents/` via `agent-catalog`

Agent Hub **must not** use staged agents or read from `staging/agents/`.

## Agent Hub ↔ Factory communication protocol

| Event | Action |
|-------|--------|
| Agent Hub starts | Call `manifest` to warm the cache |
| Agent not found in cache | Re-call `manifest` |
| New agent promoted | Factory re-runs `manifest`; Agent Hub re-caches on next call or TTL |
| Agent Hub needs full spec | Read `config/agents/<id>/agent.json` directly |
| Agent Hub wants to create an agent | Route request to Factory via CLI or Telegram |

## Constraints

- Agent Hub must not modify `config/agents/` directly — only Factory does
- Agent Hub must not discover agents by scanning the repo filesystem without calling manifest
- Human approval is required before any agent enters the registry
- The manifest hash covers static fields only; live counts do not invalidate the hash
- Subprocess specialists must declare `output_contract.status_values = ["success", "needs_clarification", "waiting_decision", "failed"]` plus the matching terminal/caller-action meaning in the registry spec Factory stages

## Universal specialist protocol metadata

Enabled registry entries may publish `input_contract` and `interaction_contract`. Agent Hub reads these declarations generically; it must not branch on specialist ID, project name, backlog provider, or identifier prefix.

A conforming generated specialist declares `protocol: agent-hub.task`, `protocol_version: 1`, required field `task`, accepted universal context, and its supported lifecycle interactions. Legacy entries without these fields remain discoverable during the migration period.
