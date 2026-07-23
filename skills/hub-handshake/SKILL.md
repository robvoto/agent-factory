---
name: hub-handshake
description: How Agent Hub discovers and caches Agent Factory capabilities; how to update the manifest
---

# Skill: Hub Handshake

How Agent Hub discovers Agent Factory capabilities and how to keep the manifest current.

## What the manifest is

`uv run agent-factory manifest` emits a single-line JSON document that Agent Hub can cache.
It includes:
- Static fields: agent_id, capabilities, boundaries, entrypoints, hub_integration config
- `live_registry`: enabled agents list, staged count, pending approval count, as_of timestamp

Agent Hub should call this once per session (or when `hub_integration.handshake_ttl_seconds` expires).

## Hub integration contract

```
hub_integration.handshake_command  = "uv run agent-factory manifest"
hub_integration.handshake_ttl_seconds = 3600
hub_integration.discovery = "registry-driven"
hub_integration.approval_required_before_registry_entry = true
```

Agent Hub must not scan the repo or call factory commands on every request — cache the manifest.

## live_registry fields Agent Hub reads

```json
{
  "live_registry": {
    "as_of": "2026-07-01T10:00:00+00:00",
    "enabled_agents": [
      {
        "id": "ai-tech-lead",
        "name": "AI Tech Lead",
        "purpose": "Specialist coding agent ...",
        "aliases": ["techlead", "atl", "code"],
        "runtime_entrypoint": "uv run python -m ai_tech_lead run-agent-task",
        "requires_approval": true,
        "backlog_sheet_id": "..."
      }
    ],
    "enabled_count": 1,
    "staged_count": 2,
    "pending_approval_count": 0
  }
}
```

## When to update agent_manifest.py

Update `src/agent_factory/agent_manifest.py` when:
- A new CLI command is added (add to `entrypoints`)
- A new capability is implemented (add to `capabilities`)
- A boundary changes (update `boundaries`)
- The hub integration protocol changes (update `hub_integration`)

Do not change `live_registry` fields — those are always populated from the live filesystem.
Do not change `manifest_hash` logic without bumping `MANIFEST_SCHEMA_VERSION`.

## Manifest hash

The hash covers all static fields (excludes `live_registry` and `manifest_hash` itself).
This means Agent Hub can detect structural changes without the hash flickering on every call.

## How Agent Hub should detect new agents

1. Agent Hub calls manifest on startup
2. If `live_registry.enabled_count` changes from cached value → re-call manifest
3. Agent Hub reads each agent's full spec from `config/agents/<id>/agent.json` for routing details
4. See `docs/agent-registry-contract.md` for the full protocol

## Related files

- `src/agent_factory/agent_manifest.py` — manifest builder
- `docs/agent-registry-contract.md` — full Agent Hub ↔ Factory protocol
- `config/agents/<id>/agent.json` — individual agent specs
- `tests/test_agent_manifest.py` — manifest tests
