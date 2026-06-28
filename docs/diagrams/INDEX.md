# Diagrams Index

All Agent Factory diagrams live here. The `.mmd` file is always the source of truth for Mermaid diagrams. SVG files are generated locally from those sources — do not edit them by hand.

To regenerate: `bash render.sh` (uses local `jsdom` + Mermaid, no external renderer).

---

## Mermaid flowcharts (01–06)

Each diagram has two files: `.mmd` (source) and `.svg` (scalable preview).

| # | Diagram | What it shows |
|---|---|---|
| 01 | [System Overview](01-SYSTEM-OVERVIEW.md) | Every component and how they connect. Start here. |
| 02 | [Agent Lifecycle](02-AGENT-LIFECYCLE.md) | How an agent goes from idea → factory → army → improvement. |
| 03 | [Telegram Flows](03-TELEGRAM-FLOWS.md) | Which bot to use, what each handles, all commands. |
| 04 | [Knowledge Flow](04-KNOWLEDGE-FLOW.md) | How agents share knowledge and learn from each other. |
| 05 | [Army Routing Interaction](05-ARMY-ROUTING.md) | Interaction diagram showing how the orchestrator decides which agent handles a request. |
| 06 | [Coding Task End to End](06-CODING-TASK-END-TO-END.md) | A coding task through every layer and gate. |

---

## Process diagram 07 — BPMN source of truth

Diagram 07 shows the controlled Agent Factory workflow.
The `.bpmn` file is the source of truth. The `.svg` preview is exported manually for review when needed.

For now, open the `.bpmn` in Camunda Modeler, bpmn.io, or the VS Code BPMN viewer.
The preview `.svg` is maintained alongside the source model.

- `07-AGENT-FACTORY-BPMN.bpmn` - source model
- `07-AGENT-FACTORY-BPMN.svg` - manual preview export
- `07-AGENT-FACTORY-BPMN.md` - short readme

---

## Related docs

| Document | What it shows |
|---|---|
| [Factory Brain Flow](../factory-brain-flow.md) | Inside the Factory Brain: tools, memory, approvals. |
| [AI Tech Lead: Army Integration](../../staging/agents/ai-tech-lead/SYSTEM.md) | How the army calls AI Tech Lead via JSON subprocess contract. |
