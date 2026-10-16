---
name: code-change
description: Use for Agent Factory code, tests, runtime, or integration implementation changes.
---

# Skill: Code Change

For code changes:

1. Work only inside the active Agent Factory repository/worktree resolved from Git; do not assume an old Windows-mounted path.
2. Read `AGENTS.md` and `docs/INDEX.md`.
3. Change only files required by the task.
4. Delete old and unused code when replaced; do not leave dead code behind.
5. Creating or enabling real agents requires an explicit request.
6. Run focused tests first, then full validation when practical.
7. If the change matches a trigger in `skills/documentation-hygiene/SKILL.md`, check and update the listed docs before reporting done.
8. Report files changed, documentation impact, and validation evidence.

## Parallel work
- For substantial tasks with genuinely independent workstreams, proactively use the available subagent interface to delegate bounded research, read-only review, or isolated implementation when it will materially speed or improve the work. Give each worker one owner, a precise scope, and a concrete output; keep independent review read-only. Parallel edits require separate task worktrees and disjoint file/resource ownership. The owning task agent integrates results and runs validation and review gates. Do not delegate duplicate work, weaken human approval boundaries, or create/enable product runtime agents under this coding guidance.
- Use only models/providers and execution budgets explicitly configured and authorized in the current environment. Verify a worker route before use; never infer API access or free usage from a ChatGPT plan or a model label, silently switch providers/models, or exceed an approved budget. If delegation or a selected model is unavailable, say so and proceed only within the authorized route.

## Heuristic review
- If the design introduces or relies on heuristic/approximate inference, apply the governing heuristic-review rules before coding. Assistive heuristics may support an authoritative validation layer; authoritative heuristics require explicit human approval.
