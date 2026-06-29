# Agent Contract

An agent package describes one runnable specialist agent.

The current enabled registry is `config/agents`.

Future agent package location:

```text
agents/<agent-id>/
  AGENTS.md
  agent.json
  SYSTEM.md
  tools.json
  permissions.json
  memory.json
  README.md
  skills/
    INDEX.md
  tests/
```

Optional future runtime files:

```text
agents/<agent-id>/src/
agents/<agent-id>/run.sh
```

## Manifest fields

An agent manifest (`agent.json`) must be a JSON object with:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique agent identifier (kebab-case) |
| `name` | Yes | Human-readable name |
| `purpose` | Yes | One-line description — used by army for routing decisions |
| `aliases` | Yes | Non-empty list of strings army uses to route tasks |
| `tools` | Yes | List of tool IDs the agent exposes |
| `permissions` | Yes | Object: `network`, `filesystem`, `shell`, `requires_approval` |
| `memory` | Yes | Object: `scope`, `retention` |
| `runtime` | Yes | Object: `mode`, `entrypoint` — how army invokes the agent |
| `backlog_sheet_id` | No | Google Sheets spreadsheet ID for this agent's backlog. Army uses this to add backlog items without hardcoding sheet locations. `null` if no sheet. |

### backlog_sheet_id

Army reads `backlog_sheet_id` from each agent's registry entry to know where to route "add backlog item" requests. This lets army manage any agent's backlog without hardcoded URLs.

Example: `"backlog_sheet_id": "1-e2lQ6vLUD8A5t3cuLhrjRvdTbs3hfs4ptdEE2yDaEc"`

Set to `null` if the agent has no backlog sheet.

## Enabled versus staged

A staged agent package can exist without being enabled.

An enabled agent is referenced by `config/agents` and can be routed to or run.

Only approved agents should be enabled.
