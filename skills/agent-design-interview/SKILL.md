---
name: agent-design-interview
description: Turn an ambiguous new-agent idea into a bounded, human-approved design before AgentPackageSpec drafting or technical implementation
---

# Skill: Agent Design Interview

Use this skill when the operator wants to create a new agent, specialist, assistant, workflow-driven agent, or reusable AI capability and the design is not already complete.

The Factory owns this design conversation. Do not delegate implementation planning to a coding agent before the design boundary is clear.

## Goal

Convert the operator's idea into a small, explicit design that can later become an `AgentPackageSpec` and, when substantive coding is required, a bounded implementation task for Agent Hub -> AI Tech Lead.

The operator owns business intent and important behavioural decisions. Factory must not silently invent missing responsibilities, permissions, process logic, source-of-truth rules, runtime behaviour, or technical facts.

## Interview behaviour

- Start from information the operator already supplied; never make them repeat answered questions.
- Ask only the next highest-value unresolved question.
- Prefer one focused question per turn when an answer affects later architecture.
- Group questions only when they are tightly related and low-risk.
- Explain why a question matters only when the choice is not obvious.
- Do not offer a large menu of architectures before the requirements justify it.
- If a choice can be determined safely from current standards and sufficient evidence, recommend one option and explain the reason briefly.
- If the operator rejects an assumption, update the design rather than defending the assumption.
- Stop safely when a required design decision is unresolved.

## Evidence gate before design decisions

Before making a material architecture, framework, library, protocol, integration, or source-of-truth recommendation, decide whether the available evidence is sufficient for that specific decision.

Use the same bounded pattern already proven in AI Tech Lead:

1. **Name one precise knowledge gap.** Do not research a broad topic because the overall task is large or unfamiliar.
2. **Check existing evidence first.** Use `search_memory` and `search_trusted_sources` before requesting live research.
3. **Skip research when the decision is already supported.** More context is not automatically better context.
4. **If evidence is insufficient, state exactly what fact is missing and why it changes the design.**
5. **Prepare one bounded live-research request.** Select only relevant official or primary documentation domains, with at most five domains. Do not use a general web search or broaden the question.
6. **Request approval before network access.** Call `request_design_research` with the exact question and allowed domains. This records the immutable research request but performs no network access. Wait for human approval; do not call `run_design_research` while the request is pending or rejected.
7. **Run the approved request once.** After approval, call `run_design_research` with that approval ID. The tool uses OpenAI Responses API web search with enforced domain filters and low search context, then marks that approval consumed so the same approval cannot be reused for repeated paid searches.
8. **Prefer official or primary sources.** Framework documentation, standards owners, official API references, changelogs, release notes, and original repositories take precedence over blogs, forums, aggregators, or generated summaries.
9. **Return a compact evidence brief.** Keep only source, date/freshness where relevant, conclusion, assumptions/uncertainty, and impact on the current design decision.
10. **Stop when the question is answered or the bounded research limit is reached.** Never crawl indefinitely or expand into adjacent questions automatically.
11. **Conflicting or insufficient evidence is a stop condition.** Ask the operator or defer the decision rather than guessing.
12. **Research informs Factory; it does not own product decisions.** The operator still owns consequential behavioural choices.

Research can occur more than once during an interview, but only at a material decision boundary and only for one unresolved knowledge gap at a time. Each live question requires its own approval.

Example for a BPMN specialist:

```text
Bad: Research everything needed to build an AI BPMN agent.

Good: Which current embeddable library provides editable BPMN 2.0 modelling,
BPMN XML round-tripping, and browser-based manual editing suitable for the
canonical diagram artefact?
```

Do not invent a library choice merely to keep the interview moving.

## Required design decisions

Before drafting `AgentPackageSpec`, establish these facts or explicitly mark them not applicable:

1. **Goal** — what outcome the agent exists to produce.
2. **Primary user** — who directs or consumes the agent's work.
3. **Inputs** — what the agent receives: chat instructions, files, records, events, APIs, or another agent's task envelope.
4. **Outputs** — the concrete deliverables or structured result.
5. **Responsibilities** — what the agent owns.
6. **Non-responsibilities** — what it must not decide or do.
7. **Human decision points** — where the operator must clarify, approve, choose, or review.
8. **Tools and integrations** — only capabilities actually needed by the design.
9. **Canonical artefact / source of truth** — when the agent creates or edits an artefact, identify which representation is authoritative.
10. **Edit/update semantics** — if humans can manually edit the artefact, decide whether those edits become authoritative and how later agent changes preserve them.
11. **Persistence / memory** — what must survive a run, if anything; default to no durable memory unless justified.
12. **Runtime pattern** — choose exactly one initial pattern and give a short reason:
    - deterministic LangGraph workflow;
    - simple tool-calling agent;
    - Deep Agent.
13. **Permissions and risk** — network, filesystem, shell, external writes, private data, long-running behaviour, cost implications.
14. **Success / acceptance evidence** — how the operator will know the first version works.

Material technical choices in these fields must pass the evidence gate above. Operator-owned business choices do not become research questions merely because Factory could search for alternatives.

## Runtime selection rule

Prefer the smallest pattern that fits the job.

Choose a **deterministic LangGraph workflow** when the lifecycle and decision gates are known and inspectable, even if one or more nodes use an LLM for interpretation.

Choose a **simple tool-calling agent** when the main uncertainty is which bounded tool to call or how to complete a small dynamic task, but complex planning, context offloading, subagents, and persistent memory are not required.

Choose a **Deep Agent** only when the task genuinely needs multi-step planning, context offloading, reusable skills, isolated subagents, or persistent memory. Do not select Deep Agents just because the project is called an agent.

If the selection depends on unresolved requirements or unsupported technical assumptions, use the evidence gate and ask the operator instead of guessing.

## Design review gate

Before `AgentPackageSpec` is drafted, present a concise design summary containing:

- Goal
- User
- Inputs
- Outputs
- Owns
- Does not own
- Human decisions
- Tools/integrations
- Source of truth
- Runtime pattern + reason
- Permissions/risks
- Acceptance evidence
- Evidence-backed technical decisions
- Open questions, if any

If any material open question or unresolved evidence gap remains, do not proceed to staging.

Ask the operator to approve or correct the design summary. Approval of the design is not approval to promote or enable the eventual agent.

## Handoff boundary

Once the design is approved:

1. Draft and validate the `AgentPackageSpec`.
2. Keep the package staged; do not enable it.
3. If the approved design requires substantive code, architecture, tests, configuration, infrastructure, integrations, or technical documentation, prepare a bounded implementation task for Agent Hub -> AI Tech Lead.
4. Preserve the approved purpose, responsibilities, non-responsibilities, permissions, runtime choice, acceptance evidence, budgets, permitted paths, stop conditions, and the evidence brief for material technical choices in that handoff.
5. AI Tech Lead may improve implementation details but must not silently change the approved agent purpose, permissions, lifecycle status, or promotion decision. If implementation evidence invalidates a Factory design assumption, return that conflict for review rather than silently substituting a different architecture.

Factory remains the lifecycle owner after implementation evidence returns.

## Anti-patterns

Do not:

- jump from a one-line idea directly to scaffolding;
- ask every possible question up front;
- invent product rules because they seem obvious;
- choose Deep Agent automatically;
- research broad topics without one decision-relevant knowledge gap;
- treat absence of evidence as permission to guess;
- use unrestricted live web search for design research;
- reuse a consumed research approval for another paid search;
- duplicate AI Tech Lead's coding workflow inside Factory;
- grant tools or permissions 'just in case';
- treat a generated diagram, document, or file preview as the source of truth when an editable canonical format exists;
- stage or promote while material design questions or evidence gaps remain unresolved.
