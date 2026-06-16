# Architecture

This file describes the current technical shape.

For product direction, read `platform-architecture.md`.

## Current implemented pieces

1. Manifest model.
2. Loader.
3. Registry.
4. Router.
5. Minimal LangChain harness adapter.

Manifests are read from `config/agents`.

Configured agents are indexed by alias.

Routing accepts `/agent <alias> <message>`.

The LangChain adapter only checks and creates a basic harness. It does not create real specialist agents and does not add tools by default.

## Near-term direction

The current manifest/router foundation should grow into:

- staged agent package scaffolding
- approval before enabling agents
- Runtime for approved agents
- logs and cost tracking
- improvement proposals from failures and feedback

## Current boundary

Do not put real specialist agent behaviour into `src/agent_factory`.

`src/agent_factory` is platform code.

Future runnable agents should live under `agents/<agent-id>/` or be generated from `templates/agent-package/`.
