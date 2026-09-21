# Agent Factory

[![CI](https://github.com/robvoto/agent-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/robvoto/agent-factory/actions/workflows/ci.yml)

Agent Factory is the lifecycle service for creating, validating, staging, approving, and promoting specialist agent packages in a local multi-agent platform.

It prepares agents for use. It does **not** orchestrate user work or dispatch tasks to specialists.

## Platform role

```text
Human request
      │
      ▼
  Agent Hub
      │
      ▼
Agent Factory
      │
      ├── validate specification, tools, permissions, and memory policy
      ├── stage an agent package
      └── request human approval
              │
              ▼
       Enabled agent registry
```

## Responsibilities

- create deterministic agent-package drafts;
- optionally use the Factory Brain to prepare an LLM-assisted draft;
- validate manifests, tools, permissions, contracts, and memory policy;
- keep unapproved packages in staging;
- record approval and rejection decisions;
- promote approved packages into the enabled registry;
- expose a machine-readable catalogue and handshake for Agent Hub;
- preserve an inspectable agent lifecycle.

## Engineering highlights

- **Governed agent lifecycle** — generated agents move through validation, staging, approval, promotion, and enablement rather than becoming active immediately.
- **Deterministic validation** — manifests, permissions, tools, contracts, and memory policy are checked before promotion.
- **Human approval** — LLM-generated packages are treated as untrusted drafts until explicitly approved.
- **Bounded capabilities** — factory tools operate only within defined staging and registry scopes.
- **Machine-readable integration** — Agent Hub discovers enabled specialists through explicit catalogue and handshake contracts.

## Repository boundaries

| Repository | Responsibility |
|---|---|
| `agent-hub` | Orchestration, routing, task state, approvals, and operator interaction |
| `agent-factory` | Agent creation, validation, staging, approval, and promotion |
| `ai-tech-lead-agent` | Technical planning and bounded coding-agent coordination |

Agent Factory must not become a second orchestrator. Enabled specialists are discovered and invoked by Agent Hub.

## Agent lifecycle

```text
Draft
  ▼
Validated
  ▼
Staged
  ▼
Pending approval
  ├── Rejected
  └── Approved
         ▼
      Promoted
         ▼
      Enabled
```

An LLM-generated draft is not trusted merely because it was generated successfully. Validation and explicit approval remain mandatory.

## Current capabilities

- deterministic package creation;
- LLM-assisted Factory Brain workflow;
- Pydantic specification validation;
- staged and enabled agent catalogues;
- approval, rejection, promotion, and deletion flows;
- bounded factory tools;
- SQLite lifecycle persistence;
- CLI and Telegram administration interfaces;
- setup, health, manifest, and test commands.

## Repository structure

```text
.
├── src/agent_factory/          # Factory services, validation, tools, and interfaces
├── templates/agent-package/    # Canonical package template
├── staging/agents/             # Unapproved agent drafts
├── config/agents/              # Enabled agent registry
├── docs/                       # Contracts, lifecycle, permissions, and architecture
└── tests/                      # Automated validation and behaviour tests
```

## Local development

```bash
uv sync --all-extras
uv run agent-factory setup
uv run agent-factory doctor
uv run pytest
```

Use [`docs/COMMANDS.md`](docs/COMMANDS.md) for the canonical operational command reference.

## Architecture principles

- **Stage before enablement** — generated packages cannot enter the active registry directly.
- **Human approval** — promotion requires an explicit decision.
- **Bounded tools** — factory actions operate only within defined staging and registry scopes.
- **Explicit permissions** — agent access is declared and validated rather than inferred.
- **Inspectable contracts** — manifests and interaction boundaries remain machine-readable and reviewable.
- **Separation of concerns** — creation belongs here; orchestration belongs to Agent Hub.

## Documentation

Start with [`docs/INDEX.md`](docs/INDEX.md), the single documentation entry point.

The active backlog is maintained outside the repository as an operational source of truth. Repository documentation should describe stable behaviour and architecture rather than duplicate mutable backlog rows.

## Security

Security guidance is indexed through [`docs/INDEX.md`](docs/INDEX.md) and maintained in [`SECURITY.md`](SECURITY.md).

## Licence

Licensed under the GNU General Public License v3.0. See [`LICENSE`](LICENSE).
