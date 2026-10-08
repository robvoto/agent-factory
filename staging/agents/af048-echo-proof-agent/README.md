# Af048 Echo Proof Agent

Status: staged draft.

This package is not live until approved and released under `agents/<id>/`. The
Hub-facing registry entry is written to `config/agents/<id>.json` from that
released package.

## Local instructions

Read `AGENTS.md` for the operating rules for this package.

## Skills

See `skills/INDEX.md` for runtime agent skills if this agent needs them. Repository coding-agent instructions, if the package later becomes a code repo, belong separately under `.agents/skills/`.

## Purpose

```text
Primary responsibility: AF048 echo proof agent: a short standalone deterministic LangGraph workflow that accepts a non-empty task string and returns Echo: followed by the exact task; reject missing, blank or non-string tasks. No model calls, tools, memory, network, runtime filesystem access or promotion.
Select for: Requests that directly require: AF048 echo proof agent: a short standalone deterministic LangGraph workflow that accepts a non-empty task string and returns Echo: followed by the exact task; reject missing, blank or non-string tasks. No model calls, tools, memory, network, runtime filesystem access or promotion.
Do not select for: Requests outside this stated responsibility.
```

## Run mode

The selected architectural runtime pattern and reason are recorded in
`agent.json` under `design`. `runtime.mode` remains the transport/execution
mode used by the caller.

## Approval required before

- enabling this agent
- adding tools
- adding network access
- adding filesystem access
- adding shell access
- enabling memory
- increasing cost limits
