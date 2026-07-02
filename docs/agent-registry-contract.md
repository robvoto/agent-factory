# Agent Registry and Discovery Contract

Decision item: AF-047. Defines how Army discovers agents that Factory has created.

## Decision

Agent discovery is **registry-driven**. Army reads from `config/agents/` or calls
`uv run agent-factory manifest`. No folder scanning, GitHub scanning, or hidden
auto-discovery. An agent does not exist for Army until it has an approved entry
in `config/agents/`.

## Registry structure

```
config/agents/
  <agent-id>/
    agent.json        ← agent spec (committed, version-controlled)
    AGENTS.md         ← agent-specific instructions (optional)
```

Every enabled agent has exactly one `agent.json`. The file is committed by Factory
during promotion. Army reads it directly or via the manifest.

## agent.json required fields

| Field | Description |
|-------|-------------|
| `id` | Unique stable identifier (kebab-case) |
| `name` | Human-readable display name |
| `purpose` | One-sentence description for routing decisions |
| `aliases` | Short names Army uses to route commands (e.g. `["code", "atl"]`) |
| `tools` | Array of tool IDs the agent may use |
| `permissions` | `network`, `filesystem`, `shell`, `requires_approval`, `allowed_roots` |
| `memory` | `scope`, `retention` |
| `runtime` | `mode`, `entrypoint`, `working_directory`, `input_arg`, `output_arg` |
| `backlog_sheet_id` | Google Sheet ID for the agent's own backlog (optional) |

## How Army discovers agents

### Option A — read manifest (preferred for remote/cached use)

```bash
uv run agent-factory manifest
```

Returns JSON including `live_registry.enabled_agents[]` — a compact list of
`{id, name, purpose, aliases, runtime_entrypoint, requires_approval}` for
every enabled agent. Cache for up to `army_integration.handshake_ttl_seconds`
(default 3600 s). Re-call when TTL expires or after a promotion event.

### Option B — read registry files directly (preferred for local/trusted use)

```
config/agents/<id>/agent.json
```

Army reads each `agent.json` for full spec details. Suitable when Army runs
on the same machine and can access the factory repo.

## Lifecycle gate

An agent enters the registry only after:

1. Factory creates a staged package in `staging/agents/`
2. Human approval is granted (via `uv run agent-factory approve <id>`)
3. Factory promotes the package to `config/agents/` via `agent-catalog`

Army **must not** use staged agents or read from `staging/agents/`.

## Army ↔ Factory communication protocol

| Event | Action |
|-------|--------|
| Army starts | Call `manifest` to warm the cache |
| Agent not found in cache | Re-call `manifest` |
| New agent promoted | Factory re-runs `manifest`; Army re-caches on next call or TTL |
| Army needs full spec | Read `config/agents/<id>/agent.json` directly |
| Army wants to create an agent | Route request to Factory via CLI or Telegram |

## Constraints

- Army must not modify `config/agents/` directly — only Factory does
- Army must not discover agents by scanning the repo filesystem without calling manifest
- Human approval is required before any agent enters the registry
- The manifest hash covers static fields only; live counts do not invalidate the hash
