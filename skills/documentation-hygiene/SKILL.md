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

## Docs index

`docs/INDEX.md` is the entry point. Update it whenever a new doc is added or an existing doc is renamed.

## What counts as stale

- Module paths that no longer exist
- Commands that have been renamed or removed
- Architecture diagrams that don't match the actual code
- Decision history that contradicts the current implementation

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
