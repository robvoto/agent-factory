# AGENTS.md

Minimal always-loaded instructions. Not the project manual, architecture guide, or command reference.
This file is the shared base; nested `AGENTS.md` files may add narrower rules for specific areas.

## Default workflow

1. Use `docs/INDEX.md` to find the smallest relevant project document.
2. Use `.skills/INDEX.md` to choose one relevant task skill.
3. Inspect current files before editing.
4. For code, tests, runtime, or integration changes, use `code-change/SKILL.md`.
5. Do not load the whole repo unless the task requires a broad audit.
6. If a nested `AGENTS.md` exists, treat it as additive and area-specific.

## Coding workflow

- Read the smallest relevant docs before editing code.
- Make the smallest change that solves the task.
- Touch only files required for the task.
- Update tests and docs when behavior changes.
- Keep config, schema, and shared knowledge in config/docs instead of inline code.

## Universal rules

- Never guess or invent.
- Keep context bounded — load the smallest file set that answers the task.
- Keep work bounded — touch only files required for the task.
- Do not hardcode what config, schema, or knowledge should own.
- Do not add compatibility shims, unused code, or dead code unless explicitly requested.
- Do not mask failures with broad exception handling or silent defaults.
- Do not claim completion without validation evidence.
- Tests must never write to permanent data; autouse conftest fixtures isolate all persistent stores.

## Finish report

- Files changed
- Behaviour changed
- Validation command/result, or why not run
- Remaining risk or follow-up
