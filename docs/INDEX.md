# Documentation Index

Read only the smallest authoritative document needed.

Working execution:

- [Agent Factory Backlog](https://docs.google.com/spreadsheets/d/1outLuOWhd-A7uvzsl9C2Jc-tKpsyci9HPZalxcmFiOg/edit) — live backlog

Operations and security:

- `COMMANDS.md` — canonical setup, validation, lifecycle, approval, promotion, deletion, routing, and Telegram commands
- `../SECURITY.md` — generated-package, credential, permission, approval, and promotion security boundaries

Diagrams:

- `diagrams/INDEX.md` - canonical diagram index
- `diagrams/01-SYSTEM-OVERVIEW.md` - system overview Mermaid flowchart
- `diagrams/02-AGENT-LIFECYCLE.md` - agent lifecycle Mermaid flowchart
- `diagrams/03-TELEGRAM-FLOWS.md` - Telegram interaction Mermaid flowchart
- `diagrams/04-KNOWLEDGE-FLOW.md` - knowledge and memory Mermaid flowchart
- `diagrams/07-AGENT-FACTORY-BPMN.md` - BPMN 2.0 process diagram for the controlled Agent Factory workflow

Reusable project standards:

- `STANDARDS_INDEX.md` - pointer to Rob's Google Drive project standards source of truth

Instruction governance:

- `instruction-governance.md` - scoped model for root, nested, template, and agent-specific `AGENTS.md` files plus reusable skills.
- `../skills/documentation-hygiene/SKILL.md` - documentation impact process and closeout checklist (AF-049)

Core direction:

- `architecture.md` - module layout and component relationships
- `platform-architecture.md` - what the platform is and is not
- `agent-lifecycle.md` - how agents are created, run, improved, and promoted
- `agent-creator-workflow.md` - bounded workflow for creating agents
- `factory-brain-flow.md` - inside the Factory Brain: tools, memory, approvals

Contracts and controls:

- `agent-contract.md` — specialist package rules, including the universal Agent Hub task boundary
- `permission-model.md`
- `trusted-sources.md`
- `agent-registry-contract.md` — how Agent Hub discovers agents; registry-driven protocol (AF-047)

Data and operations:

- `data-classification.md` — what belongs in Git vs runtime vs local-only (AF-025)
- `settings-hygiene.md` — safe pattern for local settings and secrets (AF-031)
