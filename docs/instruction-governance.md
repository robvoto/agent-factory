# Instruction and Skill Governance

This document defines how `AGENTS.md` files and reusable skills are scoped in Agent Factory.

## Scope Model

| Surface | Scope | Rule |
|---|---|---|
| Repo root [`AGENTS.md`](../AGENTS.md) | Shared baseline for every turn | Keep it minimal, always loaded, and fail closed. |
| Nested `AGENTS.md` files | Area-specific overlay | Add local rules only; do not replace root policy. |
| [`memory/factory/AGENTS.md`](../memory/factory/AGENTS.md) | Factory Brain instructions | Covers staging, approvals, and other Factory Brain behavior. |
| [`templates/agent-package/AGENTS.md`](../templates/agent-package/AGENTS.md) | Staged agent scaffold | Seeds new agent packages before approval; it is not live runtime policy. |
| Agent-specific `AGENTS.md` files in enabled packages | Live agent instructions | Apply only after approval and stay narrow. |

## Skills

Skills hold repeatable procedures and checklists.

- Put reusable procedures in [`.agents/skills/INDEX.md`](../.agents/skills/INDEX.md).
- Use skills for bounded workflows, not for shared policy that belongs in `AGENTS.md` or docs.
- Keep skills short enough that a future agent can find the right one quickly.

## Maintenance Ownership

| Surface | Who may create or maintain | Notes |
|---|---|---|
| Repo root `AGENTS.md` | Human, with approval-gated help from an orchestrator or coding agent | Shared baseline; update sparingly. |
| Nested `AGENTS.md` files | Human or approval-gated coding agent in the touched area | Must remain additive. |
| `memory/factory/AGENTS.md` | Human, or an orchestrator/coding agent under approval | Factory-specific only. |
| Template package `AGENTS.md` and scaffold files | Orchestrator or coding agent during staged package creation | Never enable from inside the staged package. |
| Shared skills and skill indexes | Human-maintained; orchestrator or coding agent may propose updates under approval | Keep them reusable and task-shaped. |

## Precedence

1. Repo root `AGENTS.md` sets the shared baseline.
2. The nearest nested `AGENTS.md` adds area-specific rules.
3. Template and agent-specific `AGENTS.md` files apply only to that package.
4. Skills explain how to perform a bounded procedure; they do not override fail-closed policy.


## Documentation Entry Point Rule

Every project must have one documentation entry point: `docs/INDEX.md`.

- Root `README.md` stays short and only explains purpose, repo role, canonical path, and where to start.
- Root `AGENTS.md` must point agents to `docs/INDEX.md`, not list multiple documentation files manually.
- Detailed commands, architecture, diagrams, standards, and operational notes live in specific documents linked from `docs/INDEX.md`.
- As documentation grows, update `docs/INDEX.md`; do not expand README or AGENTS navigation into another index.
## Governed Agent Improvement

Every Factory-created agent may identify opportunities to improve reusable behaviour, but may not silently alter itself.

Permitted proposal types:

- bounded code change;
- new reusable skill;
- update to an existing skill;
- `AGENTS.md` or other instruction change.

Each proposal must include:

- evidence from failures, rework, user corrections, repeated procedures, or measurable inefficiency;
- the problem and trigger condition;
- the exact target and bounded scope;
- expected reusable benefit;
- risks and approval implications;
- validation and rollback approach.

Human approval is required before implementation or activation. Approved code changes use the normal coding workflow and tests. Approved skills must be concise, registered in the relevant skill index, and validated before reuse. Agent Factory owns the canonical templates, validation rules, publication rules, and upgrade path for this capability across new and existing agents. Agent Hub may route improvement proposals but does not bypass Factory governance.

## Practical Rule

When a task touches `AGENTS.md` or skills, the finish report must say which files were used and which files were changed.
