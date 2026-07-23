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
| `purpose` | Yes | Single routing contract with `Primary responsibility:`, `Select for:`, and `Do not select for:` sections |
| `aliases` | Yes | Non-empty list of short human-facing command words (not used for Agent Hub routing — `purpose` is the sole routing contract) |
| `tools` | Yes | List of tool IDs the agent exposes |
| `permissions` | Yes | Object: `network`, `filesystem`, `shell`, `requires_approval` |
| `memory` | Yes | Object: `scope`, `retention` |
| `runtime` | Yes | Object: `mode`, `entrypoint`, and optional `progress` — how Agent Hub invokes the agent |
| `output_contract` | Conditional | Required when `runtime.mode` is `subprocess`; declares the staged status contract Factory validates before staging |
| `input_contract` | No | Declares the universal `agent-hub.task` envelope this specialist accepts — see "Universal Agent Hub task boundary" below |
| `interaction_contract` | No | Declares lifecycle support: `progress`, `clarification`, `approval`, `resume`, `cancellation` |

Any other top-level field (e.g. a specialist's own backlog pointer) is
specialist-owned metadata with no universal meaning — Factory writes it
through unchanged from `AgentPackageSpec.extensions`, and neither Factory nor
Agent Hub interprets it. `backlog_sheet_id` is no longer part of the core
manifest; a specialist that wants one supplies it as an extension field
(`"extensions": {"backlog_sheet_id": "..."}`), the same way any custom field
works.

## Enabled versus staged

A staged agent package can exist without being enabled.

An enabled agent is referenced by `config/agents` and can be routed to or run.

Only approved agents should be enabled.

## Subprocess output contract

For `runtime.mode = "subprocess"`, Factory now validates the staged caller contract instead of leaving it to downstream runtime policy only.

- `output_contract.status_values` must contain exactly `success`, `needs_clarification`, `approval_required`, and `failed`
- `output_contract.status_contract.success.terminal` must be `true`
- `output_contract.status_contract.needs_clarification.terminal` must be `false`
- `output_contract.status_contract.approval_required.terminal` must be `false`
- `output_contract.status_contract.failed.terminal` must be `true`
- Every status entry must include a non-empty `caller_action`

Factory does not currently standardize `result_kind` or `caller_action` names across all specialists. It only validates that subprocess agents declare the four status outcomes and their terminal/caller-facing meaning in the staged spec.

## Optional Hub progress contract

`runtime.progress` is optional and defaults to absent/disabled. Enable it only for a subprocess agent that is Hub-callable or genuinely long-running.

```json
{
  "progress": {
    "enabled": true,
    "hub_callable": true,
    "long_running": false,
    "adapter": "deep_agent",
    "schema_version": 1,
    "transport": "stdout_jsonl"
  }
}
```

Rules:

- `adapter` must be `deterministic_workflow`, `simple_agent`, or `deep_agent`
- enabled progress requires `hub_callable=true` or `long_running=true`
- enabled progress is valid only for `runtime.mode="subprocess"`
- stdout is reserved for versioned progress JSONL when Hub supplies `run_id` and `request_id`
- normal/debug logs stay on stderr
- the final result stays in the existing output JSON file
- the adapter must not emit prompts, hidden reasoning, raw model/provider payloads, secrets, or unbounded logs
- deterministic heartbeats must not create additional LLM calls

When enabled, Factory copies `runtime/progress_events.py` and `PROGRESS.md` into the staged package. Short standalone and manual agents receive no progress adapter.

## Universal Agent Hub task boundary

Newly generated specialists declare the versioned `agent-hub.task` protocol in `agent.json`.

Agent Hub owns task identity, routing, transport, progress, clarification, approval, cancellation, and result delivery. It sends the same flat envelope to every specialist regardless of which one it is: `task` (required), plus optional `request_id`, `run_id`, `source`, `execution_mode`, `progress_jsonl`, `project_root`, `references`, `human_approved`, `approval_token`. `project_root` and `references` are the two context-carrying fields — Hub passes them through when known but does not interpret `references` (user-provided or Hub-observed pointers such as file paths, URLs, or ticket IDs).

The specialist owns the boundary adapter. It validates the common envelope, preserves the original task, adapts known context (`project_root`, `references`) into its internal workflow, and asks for clarification instead of guessing. Specialist-specific fields and provider logic do not belong in Agent Hub — a specialist that needs richer structure (e.g. a resolved project name, a backlog lookup) builds that itself from the fields Hub gives it, or from its own `extensions` metadata.

The protocol requires only `task`. Request/run identity, source, execution mode, `project_root`, `references`, approval, and progress data are all optional. The manifest separately advertises lifecycle capabilities such as progress, clarification, approval, resume, and cancellation via `interaction_contract`.

Existing agents without these declarations remain readable during migration. New staged packages include the declarations and `specialist_contract.py` by default.
