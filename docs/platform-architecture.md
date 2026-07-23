# Platform Architecture

## Role split (2026-06-29)

| Repo | Role |
|------|------|
| `agent-army` | Orchestrator / runtime / control plane — main entry point for users |
| `agent-factory` (this repo) | Specialist agent — creates, configures, and stages agents only |
| `ai-tech-lead` | Specialist coding agent |

`agent-factory` is **not** the runtime or orchestrator. `agent-army` runs agents and routes tasks.

## What agent-factory does

- Designs and stages agent packages on request (via Factory Brain or CLI)
- Validates manifests, tools, permissions, and memory policy
- Enables agents only after human approval
- Tracks agent lifecycle: staged → approved → enabled
- Exposes enabled agents via `config/agents/` — army reads from there
- Emits bounded progress for Factory Brain when Army/Hub calls it
- Adds the shared progress adapter only to generated agents explicitly declared Hub-callable or long-running

## What agent-factory does NOT do

- Does not run or dispatch tasks to agents (army does this)
- Does not own the user-facing Telegram gateway (army does this)
- Does not route user requests (army does this)
- Does not persist or present progress to users; Army/Hub owns `/status`, stale detection, cancellation, and Telegram updates

## Responsibilities within factory

Factory Brain:
- Designs staged agent package drafts
- Validates manifests
- Scaffolds files from templates
- Does not enable live agents without approval

Governance:
- Controls approvals
- Enforces permissions
- Records validation evidence
- Protects against uncontrolled autonomy

## Repository shape

```text
agent-factory/
  src/agent_factory/          # factory logic only
  config/agents/              # enabled agent manifests (read by army)
  staging/agents/             # staged (unapproved) drafts
  templates/agent-package/    # scaffold template
  docs/
  .skills/
```

## Key rule

Agent packages may become runnable, but agents must not directly rewrite themselves.

They can produce improvement requests. The platform turns those requests into reviewed patches.
