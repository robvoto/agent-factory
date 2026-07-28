# Agent Creator Workflow

## Purpose

The Agent Creator is a bounded workflow for turning a user request into a staged agent package.

It is not a free-running autonomous agent.

## Workflow

```text
User request
  ↓
Clarify missing purpose, tools, memory, risks
  ↓
Draft staged agent package
```

## Inputs

The workflow should ask for or infer only what is needed:

- agent purpose
- expected user interaction style
- required tools
- data access needs
- memory needs
- runtime mode
- approval needs
- cost limits

If the request is ambiguous, stop and ask.

## Outputs

The workflow should create a staged package from `templates/agent-package/`.

The staged package should include the standard agent-local instruction file
(`AGENTS.md`) and a `skills/INDEX.md` scaffold when applicable, so every new
agent starts with the same operating rules and a place for reusable skills.

The generated `AGENTS.md` must also include the Factory-governed improvement
contract: the agent may propose bounded code, skill, or instruction changes from
evidence, but it may not silently self-modify. Human approval and validation are
required before any reusable behaviour is activated.

A staged package is not enabled automatically.

Validation, approval, and promotion live in `agent-lifecycle.md`.

Use the terminal command:

```bash
PYTHONPATH=src python -m agent_factory create "Create an agent that researches docs safely"
```

## Risk review

Flag risks before approval:

- broad filesystem access
- internet access
- shell commands
- private data
- long-running execution
- recurring schedules
- high-cost model use
- ability to modify files
- ability to contact people or services

## Promotion rule

Only approved agents can be added to `config/agents`.

`config/agents` is the enabled registry, not the drafting area.

## Future UI behaviour

The web UI should show:

- draft manifest
- prompt
- permissions
- tools
- memory policy
- risks
- approval button

Telegram can support quick actions, but web UI is better for full review.
