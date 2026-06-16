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

An agent manifest must be a JSON object with:

- `id`
- `name`
- `aliases`
- `tools`
- `permissions`
- `memory`

`id` and `name` are non-empty strings.

`aliases` is a non-empty list of strings.

`tools` is a list of tool ids.

`permissions` and `memory` are objects.

## Enabled versus staged

A staged agent package can exist without being enabled.

An enabled agent is referenced by `config/agents` and can be routed to or run.

Only approved agents should be enabled.
