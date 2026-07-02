# {{agent_name}} Agent Instructions

Status: staged draft only.

This package is a template for a new agent. It is not enabled until approved.

## Read first

- `docs/INDEX.md` is the single documentation entry point when this agent becomes a project.
- `agent.json` defines the staged agent contract.
- `skills/INDEX.md` lists reusable skills if skills exist.

Do not turn `README.md` or `AGENTS.md` into a documentation index.

## Working rules

- Keep context bounded and read the smallest relevant docs first.
- Change only files required for the task.
- If you are writing code, make the smallest change that solves the task.
- Update tests and docs when behavior changes.
- Remove replaced code; do not leave dead code or unused shims behind.
- Validate before claiming completion.
- Use `apply_patch` for manual edits.
- Do not use destructive commands unless explicitly requested.

## Skills

- If a repeatable procedure exists, put it in a small skill and list it under `skills/`.
- Read only the smallest relevant skill for the task.
- Do not invent agent-specific skills unless they are actually needed.

## Boundaries

- Do not enable, promote, or self-modify this agent from inside the agent.
- Do not expand permissions or memory without approval.
