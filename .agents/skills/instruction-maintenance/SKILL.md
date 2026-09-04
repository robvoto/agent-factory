---
name: instruction-maintenance
description: Use when editing AGENTS.md, repository skills, adapter files, instruction routing, or docs that define agent workflow.
---

# Skill: Instruction Maintenance

## Rules
- Keep `AGENTS.md` small and routing-focused.
- Repository coding-agent skills live under `.agents/skills/`; Agent Factory product/runtime skills under `skills/` are a separate application concern.
- Shared `AGENTS.md`, docs, tests, and `.agents/skills/*` must remain runtime-neutral and must not enumerate or depend on agent-specific adapter filenames.
- Agent-specific adapters, when present, own only their own bootstrap and may point into shared routing; shared owners must not point back to them.
- Prefer moving detail into the owning skill or `DETAILS.md` instead of expanding always-loaded files.
- Update `.agents/skills/INDEX.md` when adding/removing repository skills.
- Check `docs/STANDARDS_INDEX.md` before restructuring instructions or reusable project conventions.
- Validate changed instruction paths/references and run `git diff --check` before completion.
