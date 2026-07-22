---
name: documentation-hygiene
description: How to keep project documentation current and clean
---

# Skill: Documentation Hygiene

How to keep project documentation current and clean.

## Core rule

Docs must reflect current behaviour, not aspirational or historical behaviour.

## When to update docs

- When a module is created: add it to the relevant architecture doc
- When a behaviour changes: update the doc that describes it
- When a decision is made: record it in memory/factory/decisions.md
- When a doc becomes stale: update or remove it — do not leave stale content
- When a new doc is added: update `docs/INDEX.md`

## Triggered updates (AF-049)

These change types **require** checking and updating docs before closing the task:

| Change type | Docs to check |
|-------------|---------------|
| Architecture or module layout | `docs/architecture.md`, `docs/platform-architecture.md` |
| Ownership change | `docs/architecture.md`, relevant `AGENTS.md` (root or nested) |
| Setup or runtime change | `README.md`, `docs/architecture.md` |
| New CLI command | `README.md`, `docs/INDEX.md` |
| Registry or lifecycle change | `docs/agent-registry-contract.md`, `docs/agent-lifecycle.md` |
| Agent-boundary change | `docs/agent-contract.md`, `docs/platform-architecture.md` |
| Data or settings change | `docs/data-classification.md`, `docs/settings-hygiene.md` |
| Army integration change | `docs/agent-registry-contract.md` |
| New doc added | `docs/INDEX.md` |

## Docs index

`docs/INDEX.md` is the entry point. Update it whenever a new doc is added or an existing doc is renamed.

## Data and settings docs

Two docs define where files live and how settings work:
- `docs/data-classification.md` — Git vs runtime vs local-only file classes
- `docs/settings-hygiene.md` — safe pattern for local settings and secrets

Reference these before any change to `.gitignore`, `data/`, `config/`, or settings files.

## What counts as stale

- Module paths that no longer exist
- Commands that have been renamed or removed
- Architecture diagrams that don't match the actual code
- Decision history that contradicts the current implementation
- Registry or lifecycle docs that don't match the current config/agents structure

## Source citations

When implementing a framework pattern (LangGraph, LangChain Deep Agents, etc.):

- Note which source doc the pattern comes from
- Do not invent patterns from memory — verify against source docs
- If a source doc contradicts memory, trust the source doc and update memory

## Skill and memory hygiene

- Skills must describe how things are done today, not how they might be done
- Memory rules must be minimal and always correct
- Remove outdated memory entries rather than commenting them out
- Do not let skills grow into long design documents — keep them procedural and concise
