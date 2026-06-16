# Factory Brain Memory

This file adds Factory Brain-specific rules on top of the repo root `AGENTS.md`.
Keep it narrow: shared workspace rules live in the root file, and deeper procedural detail belongs in skills or docs.
Before changing Factory Brain behavior, read `docs/agent-creator-workflow.md`, `docs/agent-lifecycle.md`, and `docs/agent-contract.md`.

## Runtime

- Run from WSL at /mnt/e/programming/agent-factory
- Never use Windows paths for Python or shell commands
- Secrets come from local .env — never committed

## Core behaviour

- **Stage before enabling**: no agent goes to config/agents without human approval
- **Fail closed**: when uncertain, ask — do not guess or proceed
- **No self-modification**: do not modify skills, memory, or rules without approval
- **Cost discipline**: use the configured general default model first; ask before expensive operations
- **Promotion requests go through the tool**: use `request_agent_promotion`, not direct file writes

## Agent creation lifecycle

1. Clarify if the request is ambiguous
2. Produce a validated AgentPackageSpec JSON
3. Flag all risky permissions explicitly
4. Stage the draft with `create_staged_agent_package`
5. Present the staged package for review
6. Call request_agent_promotion to record the promotion request

## What counts as risky (always flag)

- shell: terminal commands of any kind
- network: internet access, web scraping, external API calls
- filesystem_write: writing outside staging/
- memory_write: modifying shared memory or skills without approval
- long_running: background processes, scheduled tasks

## Permission defaults for new staged packages

```json
{ "network": false, "filesystem": "none", "shell": false, "requires_approval": true }
```

Any deviation must be explicitly flagged and approved before enabling.
