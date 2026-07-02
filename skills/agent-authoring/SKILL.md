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

Optional but expected fields:
- `purpose`: one-sentence description used by Army for routing decisions — always include it
- `backlog_sheet_id`: Google Sheet ID for the agent's own backlog (if it has one)

Rules:
- `tools`: list of approved tool IDs; may be empty
- `permissions.requires_approval`: always `true` for new agents
- `runtime.mode`: `"manual"` until explicitly promoted
- `runtime.entrypoint`: `null` until a real implementation exists

## Army discovery fields

Army reads these fields from agent.json when deciding how to route:
- `id`, `name`, `purpose`, `aliases` — routing identity
- `runtime.entrypoint` — how Army invokes the agent
- `permissions.requires_approval` — whether Army must ask before running

Always set `purpose` to a clear one-sentence description of what the agent does and who should route to it.

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

- Staged packages are drafts only — they live in `staging/agents/` and are committed for review
- A human must review REVIEW.md before promotion
- Never copy to `config/agents` without explicit approval
- record_decision must log any durable decisions made during the creation process
- Once promoted to `config/agents/`, Army can discover the agent via manifest or direct file read
