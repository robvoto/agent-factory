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
| `manifest_schema_version` | No (defaults to current) | The `agent.json` schema version this manifest conforms to. Factory only accepts versions it currently supports (see below); existing manifests without the field remain readable |
| `name` | Yes | Human-readable name |
| `purpose` | Yes | Single routing contract with `Primary responsibility:`, `Select for:`, and `Do not select for:` sections |
| `aliases` | Yes | Non-empty list of short human-facing command words (not used for Agent Hub routing — `purpose` is the sole routing contract) |
| `tools` | Yes | List of tool IDs the agent exposes |
| `permissions` | Yes | Object: `network`, `filesystem`, `shell`, `requires_approval` |
| `memory` | Yes | Object: `scope`, `retention` |
| `runtime` | Yes | Object: `mode`, `entrypoint`, and optional `progress` — how Agent Hub invokes the agent |
| `output_contract` | Conditional | Required when `runtime.mode` is `subprocess`; declares the staged status contract Factory validates before staging |
| `input_contract` | No | Declares the universal `agent-hub.task` envelope this specialist accepts, including which context fields it reads (`accepted_context`) and cannot function without (`required_context`) — see "Universal Agent Hub task boundary" below |
| `interaction_contract` | No | Declares lifecycle support: `progress`, `clarification`, `approval`, `resume`, `cancellation` |
| `task_contract` | No | Declares bounded task kinds the specialist accepts, plus an optional default task kind |
| `project_context_contract` | No | Declares this specialist's project-context participation: `supported_schema_versions`, `required`, `capabilities` (`read`/`write`), `enforced_filesystem_permission` — see "Project-context contract" below |
| `target_project_access` | No | Declares how a specialist authorizes explicit `project_root` targets and whether it may create new target roots — see "Target-project access contract" below |

## Manifest schema version

`manifest_schema_version` declares which version of the `agent.json` document
shape a manifest conforms to, separate from `input_contract.protocol_version`
(which versions the Hub task envelope) and `runtime.progress.schema_version`
(which versions progress events). Factory currently supports only version
`1` and rejects any other value on newly staged specs. Manifests written
before this field existed have no `manifest_schema_version` and remain
readable; add the field when next regenerating or hand-editing them.

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

- `output_contract.status_values` must contain exactly `success`, `needs_clarification`, `waiting_decision`, and `failed`
- `output_contract.status_contract.success.terminal` must be `true`
- `output_contract.status_contract.needs_clarification.terminal` must be `false`
- `output_contract.status_contract.waiting_decision.terminal` must be `false`
- `output_contract.status_contract.failed.terminal` must be `true`
- Every status entry must include a non-empty `caller_action`

Factory does not currently standardize `result_kind` values across all specialists. It only validates that subprocess agents declare the four shared status outcomes and their terminal/caller-facing meaning in the staged spec.

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

Agent Hub owns task identity, routing, transport, progress, clarification, approval, cancellation, and result delivery. It sends the same flat envelope to every specialist regardless of which one it is: `task` (required), plus optional `request_id`, `run_id`, `source`, `execution_mode`, `progress_jsonl`, `project_root`, `references`, `human_approved`, `approval_token`, `resume`. `project_root` and `references` are the two context-carrying fields — Hub passes them through when known but does not interpret `references` (user-provided or Hub-observed pointers such as file paths, URLs, or ticket IDs).

The specialist owns the boundary adapter. It validates the common envelope, preserves the original task, adapts known context (`project_root`, `references`) into its internal workflow, and asks for clarification instead of guessing. Specialist-specific fields and provider logic do not belong in Agent Hub — a specialist that needs richer structure (e.g. a resolved project name, a backlog lookup) builds that itself from the fields Hub gives it, or from its own `extensions` metadata.

`input_contract.accepted_context` declares which of `project_root`/`references` a specialist reads at all; `input_contract.required_context` (a subset of `accepted_context`) narrows that to the context it cannot function without. A specialist with no hard project-context requirement leaves `required_context` empty (the default) — it treats `project_root`/`references` as best-effort hints, not preconditions.

The protocol requires only `task`. Request/run identity, source, execution mode, `project_root`, `references`, approval, resume, and progress data are all optional. The manifest separately advertises lifecycle capabilities such as progress, clarification, approval, resume, and cancellation via `interaction_contract`.

Existing agents without these declarations remain readable during migration. New staged packages include the declarations and `specialist_contract.py` by default.

## Task contract

`task_contract` is for bounded, specialist-declared task kinds. It is how a specialist says "I accept `coding_task` and `backlog_refinement`" or "I also support `project_creation`" without Agent Hub branching on agent ID.

```json
{
  "task_contract": {
    "task_kinds": ["coding_task", "project_creation"],
    "default_task_kind": "coding_task"
  }
}
```

Rules:

- `task_kinds` entries must be unique lowercase snake_case identifiers
- `default_task_kind`, when present, must also appear in `task_kinds`
- An omitted or empty `task_contract` means the specialist has not declared bounded task kinds in the manifest
- Agent Hub may read this contract generically, but the specialist still owns validating the incoming task at runtime

### True clarification resume (`interaction_contract.resume`)

A specialist that declares `interaction_contract.resume = true` may return an
opaque `resume_token` (any bounded, JSON-serializable value) alongside a
`needs_clarification` result. Agent Hub stores that token with the paused
task without inspecting it, and on the next user message replays it verbatim
via the envelope's `resume` field — together with the same `request_id`/
`run_id`, the clarification reply as `task`, and the original `project_root`/
`references` captured at the first dispatch (not whatever the operator's
`/project` selection happens to be by the time they reply). The specialist
uses `resume` to continue its own checkpoint instead of receiving a
reconstructed task string.

A specialist that does not declare `resume` (the default) keeps using Hub's
universal fallback: the clarification reply is concatenated onto the
original task and redispatched as a fresh instruction. This is unconditional
and requires no declaration — every current specialist, including AI Tech
Lead, uses it today.

If a specialist declares `resume = true` but a paused task has no recorded
`resume_token` (missing, oversized, or non-serializable), Agent Hub fails the
resume attempt clearly instead of silently falling back to the reconstructed-
task shape, since that shape may not be one a true-resume specialist knows
how to interpret.

## Project-context contract (AF-054, Factory scope)

`input_contract.accepted_context`/`required_context` declare which envelope
*fields* a specialist reads. `project_context_contract` goes further: it is
Factory's own manifest schema and generation contract, declaring supported
context schema versions, whether a target project is required, which
capabilities the specialist exercises there, and the filesystem permission a
runtime should enforce.

This is Factory-side scope only. `src/agent_factory/project_context.py` is
an internal reference used to (a) validate `project_context_contract` in the
manifest, (b) generate the fail-closed logic baked into each staged
package's `specialist_contract.py`, and (c) independently re-verify a staged
package's files after they are written. It is not a shared runtime
dependency: generated `specialist_contract.py` files inline their own
validation and never import this module, and neither Agent Hub nor existing
specialists are required to import it, copy it, or match its shape.

Whether Agent Hub adopts an analogous versioned wire contract is tracked
separately as `AGENT-HUB-039`; whether AI Tech Lead adapts to it is tracked
as `ATL-072`. Neither had defined such a schema as of 2026-07-25. This
section does not claim that work is done, and Factory does not wait on it —
today's Hub envelope still carries `project_root`/`references` as two
untyped strings, and Factory's own contract and adapters are unaffected by
that either way.

```json
{
  "project_context_contract": {
    "supported_schema_versions": [1],
    "required": false,
    "capabilities": [],
    "enforced_filesystem_permission": "none"
  }
}
```

Fields:

- `supported_schema_versions` — the `ProjectContext.schema_version` values this specialist accepts. Factory currently supports only version `1` and rejects any other value on a staged spec.
- `required` — this specialist cannot do meaningful work without a real target project. When `true`, `input_contract.required_context` must include `"project_root"` (Factory validates this cross-reference so the two declarations cannot drift apart), and the specialist's generated boundary adapter (`specialist_contract.py`) raises instead of substituting its own repository as the target when `project_root` is missing.
- `capabilities` — what the specialist actually does with the target project: `read`, `write`, or both. Drives the minimum `enforced_filesystem_permission` (a `required=true`, `capabilities=[]` spec is rejected — declare what the context is for).
- `enforced_filesystem_permission` — the filesystem permission ceiling Hub/runtime should grant this specialist on the target project root: `none`, `read`, or `write`. Independent of `permissions.filesystem`, which governs the agent's own `working_directory`, not an externally supplied target project. Must be at least as permissive as `capabilities` implies (`write` capability requires `enforced_filesystem_permission="write"`).

Every generated specialist's boundary adapter fails closed on drift rather than silently reinterpreting it: a non-string `project_root`, a `project_root` path that no longer exists on disk (a stale project context), or (when `required=true`) a missing `project_root` all raise instead of falling through — this is what prevents a generated specialist from silently substituting its own repository as the target.

After writing a staged package's files, Factory independently re-reads `agent.json` and `specialist_contract.py` from disk (`verify_project_context_consistency`) and fails staging if the generated adapter's `PROJECT_ROOT_REQUIRED` constant disagrees with the manifest's `project_context_contract.required` — catching a template-rendering bug instead of trusting that writing the files correctly is the same as generating them correctly.

`permissions.allowed_roots` (seen today as a hand-added field on `ai-tech-lead`'s enabled manifest, predating this contract) is the kind of ungoverned, per-specialist field this contract is meant to replace. Migrating it is out of scope here: it is a live enabled agent, and any cutover is downstream of whatever Agent Hub and AI Tech Lead decide under `AGENT-HUB-039`/`ATL-072`, not something Factory does unilaterally.

## Target-project access contract

`project_context_contract` says whether a specialist can read or write a target project. `target_project_access` says how that target is authorized, and whether creating a new target root is part of the specialist's declared contract.

```json
{
  "target_project_access": {
    "requires_explicit_project_root": true,
    "authorization_modes": [
      "registered_target",
      "unregistered_with_approval"
    ],
    "registry_source": "settings.project_registry",
    "allows_target_creation": true,
    "creation_scope": "registered_parent",
    "fail_closed_when": [
      "platform_unavailable",
      "credentials_unavailable",
      "location_unavailable"
    ]
  }
}
```

Rules:

- `requires_explicit_project_root=true` means the specialist expects the caller to supply the target root explicitly rather than silently choosing one
- `authorization_modes` declares how a supplied root becomes authorized; Factory currently standardizes `registered_target` and `unregistered_with_approval`
- `registry_source` is required when `authorization_modes` includes `registered_target`
- `allows_target_creation=true` means this specialist may create a new target root; `creation_scope` must then be non-`none`
- `creation_scope` currently standardizes `registered_parent` for specialists that may create new roots only under an authorized parent location
- `fail_closed_when` lists the conditions under which the specialist must stop rather than guess or silently continue

This contract is generic. It is not AI Tech Lead-specific, and future Factory-created specialists may declare different task kinds, authorization modes, and creation scopes as long as they stay within the validated schema.

### Generic paused decisions (`pending_decision` / `decision`)

A specialist that pauses on something with named next actions — not just a
plain-text question — may report it structurally on the shared
`waiting_decision` status instead of inventing agent-specific pause statuses.
Any non-terminal `waiting_decision` result may include a `pending_decision`
object:

```json
{
  "pending_decision": {
    "prompt": "Plain-language description of what's paused.",
    "options": [
      {"name": "approve"},
      {"name": "request_changes", "needs_text": true}
    ]
  }
}
```

Agent Hub reads only `prompt` (text it relays to the user) and each
option's `name` (the exact `decision.option` values valid right now,
optionally flagged `needs_text` to hint the user should supply free text).
Any other key the specialist puts in `pending_decision` (e.g. its own
internal `kind` or `thread_id`) is stored and relayed back opaquely —
Hub never brands its behavior on a specific specialist's option names or
internal pause kinds. A `pending_decision` with an empty or missing
`options` list is treated as absent; the specialist's `status`/`summary`
fields are used instead.

The user resumes such a pause with `/decide <option> [text]`. Agent Hub
validates `option` against the specialist's own last-reported `options`
list, then resubmits the same `request_id` with:

```json
{"decision": {"option": "request_changes", "text": "...", "actor": "human"}}
```

Resuming a `pending_decision` pause is identified by `request_id` alone —
no separate resume token is required for this path, unlike the `resume`
field described above. A specialist can combine both mechanisms (e.g. a
true-resume `needs_clarification` pause for free-text questions, and
`pending_decision` for named-option pauses) or use neither and stay on
Hub's legacy approval/reconstructed-task fallback when talking to older callers.
