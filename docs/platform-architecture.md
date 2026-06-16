# Platform Architecture

## Product direction

This project is an Agent Factory Platform.
It is a standalone project, separate from AI Tech Lead, OpenClaw, and Job Hunter.

It should support three user-facing modes through one control surface:

1. Run agents.
2. Create agents.
3. Improve agents.

The control surface can be web UI, Telegram, or both.

## Main parts

```text
Web UI / Telegram
  ↓
Agent Factory Platform
  ├─ Factory
  ├─ Runtime
  ├─ Improver
  └─ Governance
```

## Responsibilities

Factory:

- creates staged agent package drafts
- validates manifests
- scaffolds files from templates
- does not enable live agents without approval

Runtime:

- runs approved agents
- captures status, logs, costs, and outputs
- stops agents when limits are reached
- does not create or modify agents by itself

Improver:

- reviews logs, failures, feedback, and cost issues
- proposes changes
- does not apply risky changes without approval

Governance:

- controls approvals
- enforces permissions
- records validation evidence
- protects against uncontrolled autonomy

## Repository shape

For now this can stay as one repo:

```text
agent-factory/
  src/agent_factory/          # platform logic
  config/agents/              # enabled agent manifests
  agents/                     # future generated/runnable agent packages
  templates/agent-package/    # scaffold template
  docs/
  .skills/
```

`agents/` is future runtime content. Do not add real agents there until approved.

## Key rule

Agent packages may become runnable, but agents must not directly rewrite themselves.

They can produce improvement requests. The platform turns those requests into reviewed patches.
