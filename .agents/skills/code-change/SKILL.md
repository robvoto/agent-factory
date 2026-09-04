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

## Heuristic review
- If the design introduces or relies on heuristic/approximate inference, apply the governing heuristic-review rules before coding. Assistive heuristics may support an authoritative validation layer; authoritative heuristics require explicit human approval.
