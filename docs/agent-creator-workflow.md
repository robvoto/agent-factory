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
          └─ no  → request approval for bounded online research
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
2. search existing Factory memory, indexed project documentation, and trusted-source knowledge first;
3. if that answers the question, keep only a compact evidence brief and continue;
4. if new online evidence is required, ask for explicit approval before retrieval;
5. prefer official or primary sources and keep research bounded to the current knowledge gap;
6. stop when the question is answered, the configured limit is reached, or evidence remains conflicting/insufficient;
7. never broaden automatically into adjacent research questions.

This deliberately mirrors the proven AI Tech Lead research principles: repo/local evidence first, one explicit knowledge gap, primary sources, approval before online retrieval, bounded source/query limits, and a clear stop condition.

Research is subordinate to the design interview. It supplies evidence; it does not make operator-owned product decisions.

The current Factory Brain can search its indexed local/trusted knowledge. A live online-research capability must itself be bounded and approval-gated before the workflow treats online retrieval as available. Until that capability exists, Factory must report the evidence gap rather than pretending the research happened.

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

A staged package is not enabled automatically.

Validation, approval, and promotion live in `agent-lifecycle.md`.

Use the terminal command:

```bash
PYTHONPATH=src python -m agent_factory create "Create an agent that researches docs safely"
```

The direct `create` command remains a bounded developer staging action. The Factory Brain design conversation is the preferred path when requirements are incomplete or architecture decisions are still open.

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

The handoff must preserve the approved purpose, responsibilities, non-responsibilities, runtime choice, permissions, acceptance evidence, budgets, permitted paths, stop conditions, and the evidence brief behind material technical choices. AI Tech Lead may improve implementation details but must not silently change the agent's approved purpose or lifecycle decisions.

If AI Tech Lead discovers implementation evidence that invalidates a Factory design assumption, the conflict returns to Factory/operator review rather than being silently replaced during coding.

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
