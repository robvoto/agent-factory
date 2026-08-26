# {{agent_name}} Agent Instructions

Status: staged draft only.

This package is a template for a new agent. It is not enabled until approved.

## Read first

- `docs/INDEX.md` is the single documentation entry point when this agent becomes a project.
- `agent.json` defines the staged agent contract.
- `specialist_contract.py` adapts the universal Agent Hub task envelope into this specialist.
- `skills/INDEX.md` lists reusable skills if skills exist.

Do not turn `README.md` or `AGENTS.md` into a documentation index.

## Working rules

- Keep context bounded and read the smallest relevant docs first.
- Preserve unknown project/resource references as unknown; ask for clarification instead of guessing.
- Before introducing or relying on heuristic or approximate inference, apply the platform heuristic-review guardrail: assistive heuristics may narrow/rank candidates when they cannot determine the final result; a heuristic that decides semantic meaning, business outcome, target, permission, or action requires explicit human approval.
- Change only files required for the task.
- If you are writing code, make the smallest change that solves the task.
- Update tests and docs when behavior changes.
- Remove replaced code; do not leave dead code or unused shims behind.
- Validate before claiming completion.
- Use `apply_patch` for manual edits.
- Do not use destructive commands unless explicitly requested.

## Governed self-improvement

- This agent may improve its own reusable skills or `AGENTS.md` without separate approval when evidence from completed work shows a repeatable problem, recurring correction, avoidable rework, or stable procedure.
- When the evidence points beyond skills or `AGENTS.md`, propose one of: a bounded code change, a new skill, an update to an existing skill, or an `AGENTS.md` change.
- Keep every improvement bounded to the demonstrated problem. Do not broaden purpose, permissions, memory access, tool access, runtime authority, repository scope, or promotion status.
- Before editing, record the evidence, target file, expected reusable benefit, risk, and validation method in the task trace or final report.
- Approved skills live in `.skills/<name>/SKILL.md` or the package's configured skill directory and must be registered in the relevant skill index.
- Keep skills concise, procedural, and task-specific. Do not duplicate policy that belongs in `AGENTS.md` or architecture rationale that belongs in docs.
- Validate every skill or `AGENTS.md` improvement with the smallest relevant test or deterministic check.
- Code or runtime self-modification still requires the normal approved bounded coding workflow and relevant validation.
- Stop without changing anything when the evidence, target, ownership, or validation method is unclear.

## Boundaries

- Do not enable, promote, grant permissions to, or silently widen the scope of this agent from inside the agent.
- Do not modify manifests, permissions, memory access, tools, runtime authority, or promotion state without explicit human approval.
- Approved self-code changes must use the normal bounded coding workflow, target the correct repository, and pass relevant tests before activation.
- Do not expand permissions or memory without approval.
- Stop when evidence is insufficient, the target is unclear, validation fails, or the proposed change would exceed the approved scope.
