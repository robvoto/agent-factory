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

Required routing field:
- `purpose`: the single routing contract used by Hub. It must contain exactly `Primary responsibility:`, `Select for:`, and `Do not select for:` sections

Universal dispatch fields (`input_contract`, `interaction_contract`) default automatically — see `docs/agent-contract.md`. A backlog pointer or other specialist-owned metadata goes under `extensions`, not a dedicated field.

Rules:
- `tools`: list of approved tool IDs; may be empty
- `permissions.requires_approval`: always `true` for new agents
- `runtime.mode`: `"manual"` until explicitly promoted
- `runtime.entrypoint`: `null` until a real implementation exists

## Agent Hub discovery fields

Agent Hub reads these fields from agent.json when deciding how to route:
- `id`, `name`, `purpose` — routing identity (`purpose` is the sole routing contract; `aliases` are human-facing only)
- `runtime.entrypoint` — how Agent Hub invokes the agent
- `permissions.requires_approval` — whether Agent Hub must ask before running

Factory must reject vague or one-sentence purposes. `purpose` is the only routing description and must clearly state the primary responsibility, positive selection scope, and exclusion scope.

## Optional Hub progress

Do not add progress infrastructure to every agent.

Enable `runtime.progress` only when the agent is a subprocess agent and is either Hub-callable or genuinely long-running. Select exactly one adapter:

- `deterministic_workflow`
- `simple_agent`
- `deep_agent`

The generated adapter must preserve the final output JSON contract, reserve stdout for progress JSONL, keep logs on stderr, and exclude prompts, hidden reasoning, raw provider payloads, secrets, and unbounded logs. Heartbeats are deterministic and must not make additional LLM calls.

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
- Once promoted to `config/agents/`, Agent Hub can discover the agent via manifest or direct file read

## Routing-purpose examples

Good:

```text
Primary responsibility: Lead and execute changes to existing software.
Select for: Implementing backlog items or modifying code, tests, configuration, architecture, or documentation in an existing repository, including Agent Factory, Agent Hub, AI Tech Lead, or another existing software project.
Do not select for: Designing, staging, approving, rejecting, or promoting a new specialist agent package as the requested deliverable.
```

Good:

```text
Primary responsibility: Research and summarise LangChain documentation and implementation patterns.
Select for: Evidence-based questions requiring current LangChain documentation, APIs, or architecture guidance.
Do not select for: Implementing code changes or researching topics outside the LangChain ecosystem.
```

Reject vague purposes such as:

```text
Handles useful work and helps with agents.
```
