# Agent Draft Review

Status: staged draft only.

This agent is not enabled.

## Request

```text
AF048 echo proof agent: a short standalone deterministic LangGraph workflow that accepts a non-empty task string and returns Echo: followed by the exact task; reject missing, blank or non-string tasks. No model calls, tools, memory, network, runtime filesystem access or promotion.
```

## Draft identity

- ID: `af048-echo-proof-agent`
- Name: `Af048 Echo Proof Agent`
- Alias: `af048-echo-proof`

## Runtime design

- Pattern: `deterministic_workflow`
- Reason: One fixed validation-and-echo path needs no model planning or tool choice.

## Risks detected

- filesystem
- memory

## Created files

- Pending

## Approval rule

Do not promote this agent until approved. Promotion releases the full package
under `agents/<id>/` and writes the Hub-facing registry entry to
`config/agents/<id>.json` from that released package.
