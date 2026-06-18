# Roadmap

This is the live execution summary.
Open work is managed in `../data/backlog/agent_factory_backlog.xlsx`.
See `../backlog/INDEX.md` for the backlog landing page.
For product direction, read `platform-architecture.md`.
For technical shape, read `architecture.md`.
For lifecycle and creation, read `agent-lifecycle.md` and `agent-creator-workflow.md`.
For factory runtime and memory, read `factory-brain-flow.md` and `diagrams/04-KNOWLEDGE-FLOW.md`.

## Done

- manifest loading and validation
- alias registry and routing
- fail-closed permission checks
- `config/agents` as the enabled registry only
- `templates/agent-package/` as the staged agent package scaffold
- draft package creation command
- structured agent spec validation
- staged package reuse instead of duplicate creation
- Factory Brain runtime skeleton
- bounded Factory Brain tools
- long-lived conversation checkpoints
- human-in-the-loop approval interrupts
- Telegram gateway
- SQLite-backed state and approval records
- staged package records and pending approval records
- memory write/read hooks for Factory Brain learnings
- checkpoint listing, rollback, and fork support
- hot reload support
- initial BPMN process diagram for the controlled workflow

## Next

- MCP support in the agent spec and runtime wiring
- explicit agent versioning and promotion diffs
- shared knowledge base to replace the current memory stopgaps
- tighter deployment and reload behavior once the core flow stays stable
- Implement stable browser-based diagram rendering in WSL using one supported Chromium path.

## Why these are next

- MCP support blocks useful army agents.
- Versioning is needed to promote v2 without deleting v1.
- Shared knowledge replaces the current memory stopgaps.
- Deployment and reload behavior needs to stay stable before the platform grows further.
