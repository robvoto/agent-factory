# Initial Deep Agent Factory Implementation Plan

Status: closed and archived source plan.

This file keeps the original plan for background only.
Do not add new work here.
The live backlog is `../data/backlog/agent_factory_backlog.xlsx`.
The live backlog is `../backlog/INDEX.md`.

## Goal

Build a Telegram-first Agent Factory that can:

- receive a request
- classify intent
- select or reuse an agent
- ask for clarification when needed
- request approval for risky or destructive work
- execute coding work through bounded tools
- record state, logs, checkpoints, and approvals
- return a concise result to the human

## Original completion snapshot

- manifest loading and validation
- alias registry and routing
- fail-closed permission checks
- `config/agents/` as the enabled registry only
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

## Original open gaps

- shared RAG knowledge base for all agents
- full MCP server declaration and runtime wiring in agent specs
- agent versioning and promotion diffs
- queued message delivery for async handoff
- zero-downtime deployment
- hot reload beyond the current local development flow
- broader observability and cost dashboards
