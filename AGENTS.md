# AGENTS.md — Agent Factory

Agent Factory creates, configures, and stages agents. It is a specialist agent, not the main orchestrator.

`agent-army` is the orchestrator and runtime control plane.
`agent-factory` creates and configures agents only.

Minimal always-loaded instructions. Not the project manual, architecture guide, backlog, standards document, or command reference.
This file is the shared base; nested `AGENTS.md` files may add narrower rules for specific areas.

## Standards source of truth

Rob's project standards live in Google Drive:

https://drive.google.com/drive/u/1/folders/14-mkDcSsRd78yTIT17mK03jGPjcGRRNS

Use `docs/STANDARDS_INDEX.md` as the local pointer to the standards source.

Before changing project setup, architecture, documentation structure, backlog process, logging, LLM usage/cost tracking, data layout, automation, CI/CD, deployment, AGENTS.md, or reusable skills, check the current standards source if available.

If the standards source cannot be accessed, stop and ask the operator for the current exported text. Do not guess or invent standards.

## Backlog

The live backlog is a Google Sheet — use it to find, add, or update work items:
https://docs.google.com/spreadsheets/d/1outLuOWhd-A7uvzsl9C2Jc-tKpsyci9HPZalxcmFiOg/edit

Do not create duplicate local backlog files unless explicitly requested.

## Default workflow

1. Use `docs/INDEX.md` as the single documentation entry point.
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
- Keep config, schema, shared knowledge, data, and docs in their proper locations instead of inline code.

## Logging and cost discipline

- Add friendly human-readable logs for normal execution and detailed debug logs for troubleshooting.
- Exceptions must be obvious in logs; do not hide them behind silent fallbacks.
- Do not add fallback, compatibility shim, hardcoded replacement, or silent default behaviour unless explicitly approved.
- Every LLM call must be traceable with model, purpose, input/output token usage when available, estimated/actual cost when available, and stop reason.
- Enforce budgets and stop safely before expensive or uncertain operations.
- Persistent data belongs under `data/`; documentation belongs under `docs/`.

## Universal rules

- Never guess or invent.
- Keep context bounded — load the smallest file set that answers the task.
- Keep work bounded — touch only files required for the task.
- Do not hardcode what config, schema, or knowledge should own.
- Do not add compatibility shims, unused code, or dead code unless explicitly requested.
- Do not mask failures with broad exception handling or silent defaults.
- Do not claim completion without validation evidence.
- Tests must never write to permanent data; autouse conftest fixtures isolate all persistent stores.

## Data and settings hygiene

Before touching `.gitignore`, `data/`, `config/`, `staging/`, or `templates/`:
- Check `docs/data-classification.md` to confirm the file class
- Never commit SQLite DBs, `.env`, local settings (`data/settings.local.json`), or logs
- Always have a committed `data/settings.local.example.json` with placeholder values only

## Documentation impact (AF-049)

After any change to architecture, commands, registry, lifecycle, agent boundaries, setup, or runtime:
- Check whether `README.md`, `docs/INDEX.md`, or architecture docs need updating
- Update `docs/INDEX.md` if a new doc was added
- Do not rewrite docs unless the backlog item explicitly asks for an audit

## Session closeout — open work register (AF-041)

Before ending a session:
- Record every unfinished task, open investigation, or deferred decision in the backlog Google Sheet
- Each row needs: ID, Title, Status=Backlog, evidence of what was tried, next action
- Do not leave open work only in chat — it will be lost

## Finish report

- Files changed
- Behaviour changed
- Validation command/result, or why not run
- Remaining risk or follow-up
