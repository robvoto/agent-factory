---
name: agent-authoring
description: How to design staged agent packages for the Agent Factory Platform
---

# Skill: Agent Authoring

How to design staged agent packages for the Agent Factory Platform.

## Required files

Every staged package under `staging/agents/<agent-id>/` must include:

```text
agent.json
SYSTEM.md
tools.json
permissions.json
memory.json
README.md
REVIEW.md
tests/.gitkeep
```

## Naming rules

- Agent ID: lowercase letters, digits, and hyphens only; starts with a letter; max 64 chars
- Example: `research-agent`, `code-reviewer-agent`
- Name: human-readable; max 120 chars; title case preferred
- Aliases: short command words; lowercase; no duplicates

## Manifest rules (agent.json)

Required fields: `id`, `name`, `aliases`, `tools`, `permissions`, `memory`, `runtime`

- `tools`: list of approved tool IDs; may be empty
- `permissions.requires_approval`: always `true` for new agents
- `runtime.mode`: `"manual"` until explicitly promoted
- `runtime.entrypoint`: `null` until a real implementation exists

## Prompt standards (SYSTEM.md)

The system prompt must:

- State the agent's name and purpose clearly
- List what the agent may and may not do
- Include a stop rule: pause before risky or destructive actions
- Be concise — no more than one page

## Testing expectations

- Every package must have a `tests/` directory
- At minimum, a `.gitkeep` placeholder
- Later: at least one test verifying the agent refuses out-of-scope requests

## Approval rules

- Staged packages are drafts only
- A human must review REVIEW.md before promotion
- Never copy to `config/agents` without explicit approval
- record_decision must log any durable decisions made during the creation process
