# Code Change Skill

For code changes:

1. Stay inside `/mnt/e/programming/agent-factory`.
2. Read `AGENTS.md` and `docs/INDEX.md`.
3. Change only files required by the task.
4. Delete old and unused code — if something is replaced, remove the original. No dead code left behind.
5. Real agents require an explicit request.
6. Run focused tests first, then full validation when practical.
7. If the change matches a trigger type in `skills/documentation-hygiene/SKILL.md` (AF-049), check and update the listed docs before reporting done.
8. Report files changed, documentation impact, and validation evidence.

## Heuristic review
- If the design introduces or relies on a heuristic/approximate inference, apply the global `heuristic-review` skill before coding. Assistive heuristics may be used only when an independent LLM/authoritative validation layer controls the final outcome; authoritative heuristics require explicit human approval.
