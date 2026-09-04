# Agent Instructions

Minimal shared routing instructions for Agent Factory. This file is not the project manual, architecture guide, backlog, standards document, or command reference.

## Default workflow

1. Use `docs/INDEX.md` to find the smallest relevant project document.
2. Use `.agents/skills/INDEX.md` for repository coding/instruction work.
3. Use `skills/INDEX.md` only for Agent Factory's product/runtime agent-authoring skills; it is a separate application-owned skill system.
4. Inspect current files before editing; do not load the whole repo unless the task requires a broad audit.
5. For branch/worktree, commit, push, PR, merge, or `main` integration, use `.agents/skills/git-lifecycle/SKILL.md`.
6. If a nested `AGENTS.md` exists, treat it as additive and area-specific.

## Standards and backlog

- Canonical shared standards are linked from `docs/STANDARDS_INDEX.md`; check them before changing project/instruction structure or reusable standards.
- The live Agent Factory backlog is the Google Sheet linked from project docs. Do not create a competing local backlog.

## Durable rule placement

- Shared project rules must be runtime-neutral.
- Put task-specific repository procedures in `.agents/skills/`.
- If no existing repository skill owns a durable rule, create a focused skill and add it to `.agents/skills/INDEX.md`.
- Agent-specific adapter files, when present, own only themselves. Shared docs/tests must not enumerate, require, or depend on specific adapter filenames.
- Do not confuse repository instruction skills with Agent Factory's product/runtime `skills/` directory.

Use `.agents/skills/instruction-maintenance/SKILL.md` for AGENTS, skills, adapters, or instruction-structure changes.

## Universal rules

- Never guess or invent; inspect the authoritative source first.
- Keep context and changes bounded to what the task requires.
- Do not hardcode behaviour that belongs in config, schema, knowledge, or another owner.
- Do not add hidden fallbacks, compatibility shims, dead paths, or broad exception swallowing unless explicitly approved.
- Heuristics that determine semantic meaning, business outcome, target, permission, or action require explicit human approval; assistive heuristics may only narrow or support an authoritative decision path.
- Runtime safety, permissions, budgets, and promotion boundaries must be enforced in code/config, not only prose.
- Do not claim completion without validation evidence.
- Preserve unrelated work when other agents or sessions may be active.

## Finish report

Report what changed, validation performed/result, remaining risk/follow-up, and Git integration state when relevant.
