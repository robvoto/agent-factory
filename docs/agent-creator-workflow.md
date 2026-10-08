# Agent Creator Workflow

## Purpose

The Agent Creator turns a new-agent idea into a reviewed design and then into a staged agent package.

It is not a free-running autonomous agent and it must not jump from a vague request directly to scaffolding.

## Workflow

```text
User request
  ↓
Agent design interview
  ↓
Next material design decision
  ↓
Is current evidence sufficient?
  ├─ yes → continue design
  └─ no  → state one precise knowledge gap
             ↓
          search local / trusted knowledge
             ↓
          sufficient?
          ├─ yes → compact evidence brief
          └─ no  → request approval for one bounded live research question
                     ↓
                  human approves exact question + domains
                     ↓
                  one domain-filtered web-search call
                     ↓
                  evidence brief or explicit uncertainty
             ↓
          continue design
  ↓
Clarify the next material gap with the operator
  ↓
Design summary
  ↓
Human review / correction
  ↓
Approved design
  ↓
Draft + validate AgentPackageSpec
  ↓
Stage agent package
  ↓
If substantive implementation is required:
Agent Hub → AI Tech Lead
```

The Factory owns agent definition, design, lifecycle governance, staging, validation, and promotion decisions. AI Tech Lead owns substantive technical implementation after the design boundary is approved.

## Design interview

Use `skills/agent-design-interview/SKILL.md` before drafting `AgentPackageSpec` when the design is not already complete.

The interview must establish, or explicitly mark not applicable:

- goal and primary user
- inputs and outputs
- responsibilities and non-responsibilities
- human clarification / approval points
- tools and integrations
- canonical artefact / source of truth when applicable
- manual edit/update semantics when applicable
- persistence / memory needs
- runtime pattern and reason
- permissions and risks
- acceptance evidence

Ask only the next highest-value unresolved question. Do not make the operator repeat information already supplied. If a material decision remains unresolved, stop and ask instead of guessing.

### Evidence / research gate

Factory must not turn an unsupported technical assumption into an agent design decision.

At each material technical decision boundary, decide whether the existing evidence is enough. If not:

1. state one precise decision-relevant knowledge gap;
2. use `search_memory` and `search_trusted_sources` first;
3. if that answers the question, keep only a compact evidence brief and continue;
4. if live evidence is required, call `request_design_research` with the exact question and at most five relevant official/primary domains;
5. the request only creates an approval record and performs no network access;
6. after human approval, call `run_design_research` with that approval ID;
7. the live tool performs one OpenAI Responses API call using the built-in `web_search` tool, an enforced `allowed_domains` filter, low search context, one retry maximum, and a maximum of five citations returned to Factory;
8. immediately before network access, the tool atomically marks the approval `claimed`, so only one worker can execute it; it then records `consumed` on success or `failed` on an error, and neither terminal state can be reused for another paid search;
9. stop when the question is answered or evidence remains conflicting/insufficient;
10. never broaden automatically into adjacent research questions.

This mirrors the proven AI Tech Lead research principles: local/trusted evidence first, one explicit knowledge gap, primary sources, approval before online retrieval, bounded retrieval, and a clear stop condition.

Research is subordinate to the design interview. It supplies evidence; it does not make operator-owned product decisions.

Before staging, present a concise design summary for human approval or correction. Include the evidence basis for material technical choices. Design approval is not approval to promote or enable the agent.

## Runtime pattern selection

Choose the smallest pattern that fits the approved design:

- deterministic LangGraph workflow — known inspectable lifecycle / decision path, even when selected nodes use an LLM
- simple tool-calling agent — bounded dynamic tool choice without complex planning or persistent context needs
- Deep Agent — only when multi-step planning, context offloading, reusable skills, isolated subagents, or persistent memory are genuinely required

Do not select Deep Agent merely because the deliverable is called an agent. If the runtime choice depends on an external technical fact that has not been established, use the evidence gate first.

## Outputs

The workflow creates a staged package from `templates/agent-package/` after the design is approved and the `AgentPackageSpec` validates.

The staged package should include the standard agent-local instruction file (`AGENTS.md`) and a `skills/INDEX.md` scaffold when applicable, so every new agent starts with the same operating rules and a place for reusable skills.

The generated `AGENTS.md` must also include the Factory-governed improvement contract: the agent may propose bounded code, skill, or instruction changes from evidence, but it may not silently self-modify. Human approval and validation are required before any reusable behaviour is activated.

A staged package is not enabled automatically.

Validation, approval, and promotion live in `agent-lifecycle.md`.

Use the terminal command:

```bash
PYTHONPATH=src python -m agent_factory create "Create an agent that researches docs safely" \
  --runtime-pattern simple_agent \
  --runtime-pattern-reason "Bounded tool choice is sufficient for this research workflow."
```

The direct `create` command remains a bounded developer staging action and
requires the operator to declare the runtime pattern and a short reason. The
Factory Brain design conversation is the preferred path when requirements are
incomplete or architecture decisions are still open.

## Risk review

Flag risks before approval:

- broad filesystem access
- internet access
- shell commands
- private data
- long-running execution
- recurring schedules
- high-cost model use
- ability to modify files
- ability to contact people or services

## Technical implementation handoff

When an approved agent design requires substantive code, architecture, tests, configuration, infrastructure, integrations, or technical documentation, Factory prepares a bounded implementation task for Agent Hub to route to AI Tech Lead.

Factory writes that handoff as `staging/agents/<agent-id>/BUILD_TASK.json` and records
its thread and correlation in Factory SQLite. The task is strict and versioned: it
contains the staged `agent.json` identity/hash, explicit acceptance criteria and test
commands, permitted paths, relevant `docs/`/`skills/` references (including only the
same package's local references), token/time budgets, stop conditions, and the
manifest's explicit runtime pattern and reason. Preparation has no hidden defaults.
Regeneration reuses the stable artifact path while preserving superseded/stale history.
The correlation covers all caller-controlled task fields and the manifest hash, so a
changed approved artifact is stale and the `BUILD_TASK.json` control artifact cannot
be included as an implementation path.

The handoff must preserve the approved purpose, responsibilities, non-responsibilities, runtime choice, permissions, acceptance evidence, budgets, permitted paths, stop conditions, and the evidence brief behind material technical choices. The dedicated Deep Agents HITL approval marks the exact prepared correlation approved; rejection leaves it non-dispatchable. AI Tech Lead may improve implementation details but must not silently change the agent's approved purpose or lifecycle decisions.

Factory stops at **implementation-ready**. It does not need to settle every
library, adapter, selector, provider, retry policy, or internal class before
handoff when several choices can satisfy the approved contract. Those
implementation details belong to AI Tech Lead unless they materially change
purpose, permissions, budgets, lifecycle state, or acceptance criteria.

If AI Tech Lead discovers implementation evidence that invalidates a Factory design assumption, the conflict returns to Factory/operator review rather than being silently replaced during coding.

When Hub returns ATL's structured BuildResult v1 through the same Factory thread and
correlation, Factory consumes it through `consume_agent_build_result`. The Factory
consumer strictly validates the wire fields, exact approved task, staged manifest
hash/design identity, permitted changed paths, required passed test commands, and
metered budgets. A successful result is persisted as the Factory-owned
`staging/agents/<id>/BUILD_RESULT.json` control artifact and moves the exact task to
`validated`; failed or incomplete evidence moves only that approved task to
`failed`. `BUILD_TASK.json` and `BUILD_RESULT.json` are never runtime package files.

The v1 token budget covers metered `ai_tech_lead_orchestrator` usage. A separate
coding backend's token and cost usage is explicitly unknown when it exposes no
measurements, not zero. The time budget covers measured coding-agent execution
duration; cost scope and source remain explicit and do not invent backend spend.
Validation leaves the package staged. Existing separate human promotion approval is
still required before release or registry update. The Hub relay that returns the
BuildResult is a cross-project integration remaining outside this repository.

## Promotion rule

Only approved agents can be added to `config/agents`.

`config/agents` is the enabled registry, not the drafting area.

## Future UI behaviour

The web UI should show:

- design summary
- open design questions
- unresolved evidence gaps
- evidence-backed technical decisions
- draft manifest
- prompt
- permissions
- tools
- memory policy
- risks
- approval button

Telegram can support quick actions, but web UI is better for full review.
