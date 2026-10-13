---
name: hub-handshake
description: How Agent Hub discovers and caches Agent Factory capabilities; how to update the manifest
---

# Skill: Hub Handshake

How Agent Hub discovers Agent Factory capabilities and how to keep the manifest current.

## What the manifest is

`uv run agent-factory manifest` emits a single-line JSON document that Agent Hub can cache.
It includes:
- Static fields: agent_id, purpose, entrypoints, shared protocol/progress metadata, hub_integration config
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
        "input_contract": {...},
        "interaction_contract": {...},
        "task_contract": {...},
        "project_context_contract": {...},
        "target_project_access": {...}
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
- The shared protocol/progress contract changes
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


## Prove specialist callability

An agent appearing in the enabled registry proves registration only. Before claiming Hub-callable, verify that the current package exposes a working manifest command and declares a `task_contract` with the task kind Hub routes. A valid package that is enabled but has no matching task kind is not eligible for that request.

For a live acceptance test, use the current Hub and Factory source revisions, correlate the routing decision to the dispatched run and specialist result, and inspect the exact `task` field received by the subprocess. Keep caller context separate from literal task input when the acceptance contract requires exact input. A new browser tab alone does not isolate a shared Telegram bot chat; use a distinct supported chat/session when another worker is active.
