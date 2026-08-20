# AGENTS.md — Agent Factory

Agent Factory creates, configures, and stages agents. It is a specialist agent, not the main orchestrator.

`agent-hub` is the orchestrator and runtime control plane.
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
5. For any branch/worktree, commit, push, PR, merge, or `main`-integration decision, use `.skills/git-lifecycle/SKILL.md`.
6. Do not load the whole repo unless the task requires a broad audit.
7. If a nested `AGENTS.md` exists, treat it as additive and area-specific.

## Coding workflow

- Read the smallest relevant docs before editing code.
- Make the smallest change that solves the task.
- Touch only files required for the task.
- Update tests and docs when behavior changes.
- Keep config, schema, shared knowledge, data, and docs in their proper locations instead of inline code.

## Governed self-improvement

- Agent Factory and agents it creates may improve their own reusable skills or `AGENTS.md` without separate approval when evidence from completed work shows a repeatable problem, recurring correction, avoidable rework, or stable procedure.
- Keep every improvement bounded to the demonstrated problem. Do not broaden agent purpose, permissions, memory access, tool access, runtime authority, repository scope, or promotion status.
- Before editing, record the evidence, target file, expected reusable benefit, risk, and validation method in the task trace or final report.
- Reusable skills must remain concise and procedural, be registered in the relevant skill index, and be validated with the smallest relevant test or deterministic check.
- Do not duplicate policy across skills and `AGENTS.md`. Put universal behavioural rules in `AGENTS.md`; put task-specific procedures in skills.
- Code or runtime self-modification still requires the normal approved bounded coding workflow and relevant validation.
- Never silently enable, promote, grant permissions to, or widen the scope of an agent.
- Stop without changing anything when the evidence, target, ownership, or validation method is unclear.

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

## Durable Factory learning

When a reusable lesson changes how Agent Factory should build or upgrade agents:
- Do not leave the lesson only in chat or backlog text.
- Update the canonical governance document, generated-agent template, agent-authoring skill, and enforcement tests as applicable.
- Existing agent-specific instructions may be preserved, but approved standards migrations must be applied to every registered agent package rather than left as indefinite follow-up work.
- Record incomplete implementation work in the live backlog before session closeout.

## Documentation impact (AF-049)

After any change to architecture, ownership, setup, runtime, commands, registry, lifecycle, or agent boundaries:
- Check whether `README.md`, `docs/INDEX.md`, or architecture docs need updating
- Update `docs/INDEX.md` if a new doc was added
- Do not rewrite docs unless the backlog item explicitly asks for an audit
- See `skills/documentation-hygiene/SKILL.md` for the full trigger-to-doc table

## Session closeout — open work register (AF-041)

Before ending a session:
- Record every unfinished task, open investigation, or deferred decision in the backlog Google Sheet
- Each row needs: ID, Title, Status=Backlog, evidence of what was tried, next action
- Do not leave open work only in chat — it will be lost

## Finish report

- Files changed
- Behaviour changed
- Self-improvement evidence and validation, when applicable
- Documentation impact check done (see Documentation impact (AF-049) above)
- Validation command/result, or why not run
- Remaining risk or follow-up

## Repository text format

- All tracked text files use LF line endings. `.gitattributes` and `.editorconfig` are authoritative; do not introduce or preserve CRLF.
- Before finishing edits, run `git diff --check`. If a touched tracked text file is CRLF or mixed, normalize that touched file to LF without rewriting unrelated dirty work.
