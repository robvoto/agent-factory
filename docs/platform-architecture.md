# Platform Architecture

## Role split (2026-06-29)

| Repo | Role |
|------|------|
| `agent-hub` | Orchestrator / runtime / control plane — main entry point for users |
| `agent-factory` (this repo) | Lifecycle service and governance boundary — creates, validates, stages, releases, and registers agents |
| `ai-tech-lead` | Specialist coding agent |

An agent can remain a standard released package owned by Factory. It becomes an
independent product agent in a separate specialist repository only after an explicit
human and architecture decision based on genuine independent engineering needs. That
decision is not an automatic promotion side effect.

`agent-factory` is **not** the runtime or orchestrator. `agent-hub` runs agents and routes tasks.

## What agent-factory does

- Designs and stages agent packages on request (via Factory Brain or CLI)
- Validates manifests, tools, permissions, and memory policy
- Validates explicit MCP server/tool declarations against the approval registry and selects authorized runtime handles
- Enables released agents only after validation and human approval
- Tracks agent lifecycle: prototype/incubating → approved → standard release or independently implemented release → enabled
- Owns the registry contract, permissions, promotion, activation metadata, and governed upgrades for both Factory-owned and independent product agents
- Exposes released agents via `config/agents/` — Agent Hub reads from there
- Emits bounded progress for Factory Brain when Agent Hub calls it
- Adds the shared progress adapter only to generated agents explicitly declared Hub-callable or long-running

## What agent-factory does NOT do

- Does not run or dispatch tasks to agents (Agent Hub does this)
- Does not own the user-facing Telegram gateway (Agent Hub does this)
- Does not route user requests (Agent Hub does this)
- Does not persist or present progress to users; Agent Hub owns `/status`, stale detection, cancellation, and Telegram updates
- Does not discover, start, or execute MCP servers; an external runtime must supply explicit available handles after Factory authorization
- Does not decide automatic graduation or become the implementation owner of an independent product agent

## Responsibilities within factory

Factory Brain:
- Designs staged agent package drafts and may propose governed upgrades
- Validates manifests
- Scaffolds files from templates
- Does not enable live agents without approval

Independent product repositories:
- Own their product implementation, dependencies, implementation tests, and implementation release work after graduation
- Supply a release for Factory validation and registry activation
- Do not bypass Factory's registration, permission, release-contract, promotion, or activation gates

Governance:
- Controls approvals
- Enforces permissions
- Records validation evidence
- Protects against uncontrolled autonomy

## Repository shape

```text
agent-factory/
  src/agent_factory/          # factory logic only
  agents/                    # approved Factory-owned released packages
  config/agents/              # enabled release manifests (read by Agent Hub)
  staging/agents/             # incubation/review drafts only
  templates/agent-package/    # scaffold template
  # independent product implementations live in their own specialist repositories only after graduation
  docs/
  .agents/skills/
```

`staging/` contains draft artefacts only. `agents/<id>/` is the authoritative
released package home for a Factory-owned standard agent. `config/agents/` is the
enabled Hub-facing registry and contains registry manifests, not the full package
store. Agent Hub does not own, move, or version specialist package workspaces.

## Key rule

Agent packages may become runnable, but agents must not directly rewrite themselves.
Agent Hub consumes enabled release definitions; it is never the development home.
Rollback reactivates a previously validated release through release governance rather
than restoring arbitrary filesystem state.

They can produce improvement requests. The platform turns those requests into reviewed patches.
