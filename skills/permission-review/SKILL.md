---
name: permission-review
description: How to review risk before enabling an agent
---

# Skill: Permission Review

How to review risk before enabling an agent.

## Risk categories

### Filesystem risk
- `filesystem: "write"` — can modify files outside staging/
- Always flag; always require approval
- Default is `"none"` — read is acceptable for doc agents

### Shell risk
- `shell: true` — can run terminal commands
- Highest risk category; never grant by default
- Requires explicit justification and human approval

### Network risk
- `network: true` — can access the internet or external APIs
- Flag all internet access; flag all external API calls
- Requires explicit justification and human approval

### Memory risk
- Modifying `memory/factory/AGENTS.md` or `skills/` without approval
- Always route through request_approval tool

### Cost risk
- Using large models (GPT-4o, Claude Opus) without a stated reason
- Running in background or on a schedule without approval
- Agents that loop indefinitely

### Privacy risk
- Access to credentials, tokens, or secrets
- Logging or transmitting user messages externally

### Fallback and compatibility risk
- Fallback code, compatibility shims, silent defaults, degraded behaviour, workarounds, and hardcoded replacements
- Upstream dependency changes that would silently change product semantics
- Any proposed change that says "safe default", "best effort", or equivalent

## Reviewing a staged agent

Check these fields in `agent.json`:

1. `permissions.network` — should be `false` unless justified
2. `permissions.filesystem` — should be `"none"` or `"read"` unless justified
3. `permissions.shell` — should be `false` unless justified
4. `tools` — each tool ID must be in the approved tool registry

## Approval requirement

Any staged agent with a non-default permission must include in REVIEW.md:

- Which permission is elevated
- Why it is required
- What the risk is
- Who approved it (after the fact)

## Fallback and shim review

If a proposed change is described as fallback, temporary, compatibility shim, workaround, safe default, best effort, or degraded behaviour:

1. Stop and ask for approval before implementing it.
2. Report the product impact instead of silently replacing semantics.
3. List the fallback, shim, or workaround in REVIEW.md, or state explicitly that none were introduced.
