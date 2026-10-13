# Af048 Echo Proof Agent

Status: executable deterministic agent; Factory approval controls release and enablement.

The released package runs through Agent Hub's subprocess contract. Factory
approval controls release and registry enablement.

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

## Hub execution

Hub passes a JSON task file to `src/run_agent.py`, which writes a structured
result JSON file. Successful input returns exactly `Echo: ` followed by the
original task string, preserving whitespace, newlines, and Unicode.

## Approval required before

- enabling this agent
- adding tools
- adding network access
- adding filesystem access
- adding shell access
- enabling memory
- increasing cost limits
