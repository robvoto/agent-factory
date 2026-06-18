# Agent Factory BPMN

Source of truth: `07-AGENT-FACTORY-BPMN.bpmn`.
Rendered view: `07-AGENT-FACTORY-BPMN.svg` is exported manually for review when needed.

This model is intended to be opened directly in a BPMN viewer for now:

- Camunda Modeler
- bpmn.io
- VS Code BPMN viewer

SVG automation is deferred until we choose one stable renderer path.

Model shape:

1. Human / Operator is the external request and response pool.
2. Agent Factory is one main pool with lanes for Telegram Interface, Orchestrator, and Specialist Agent.
3. Coding Backend is the external execution pool for Codex / Claude Code.
4. Persistent State / Logs is a BPMN data store, not a pool.

Flow rules:

- Use message flows only between Human / Operator, Agent Factory, and Coding Backend.
- Use solid sequence flows inside the Agent Factory pool.
- Use data associations for request state, decision state, and outcome persistence.

The model covers request intake, intent classification, agent selection, clarification, approval, execution, logging, and safe stop paths.
