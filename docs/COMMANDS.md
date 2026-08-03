# Agent Factory Commands

This is the canonical operator command reference. Run commands from the repository root.

## Setup and validation

```bash
uv sync --all-extras
uv run agent-factory setup
uv run agent-factory doctor
uv run pytest
```

Use `uv run agent-factory --help` or `uv run agent-factory <command> --help` for the current CLI-generated argument details.

## Inspect factory state

```bash
uv run agent-factory list
uv run agent-factory manifest
uv run agent-factory staged
uv run agent-factory pending
uv run agent-factory models
uv run agent-factory langchain-check
```

- `list` shows enabled agents.
- `manifest` prints the machine-readable factory handshake.
- `staged` lists all staged-agent records and their current statuses, including records retained after promotion with status `enabled`.
- `pending` shows approval requests and their numeric IDs.
- `models` shows configured model defaults and aliases.
- `langchain-check` verifies the LangChain runtime import path.

## Create agent drafts

Deterministic creation:

```bash
uv run agent-factory create "Create an agent that researches approved documentation"
```

LLM-assisted Factory Brain creation requires the configured provider credentials:

```bash
uv run agent-factory factory "Create an agent that researches approved documentation"
```

Both paths create staged work. They do not bypass validation, approval, or promotion controls.

## Approval and promotion

```bash
uv run agent-factory pending
uv run agent-factory approve <approval-id>
uv run agent-factory reject <approval-id> "Reason for rejection"
uv run agent-factory promote <agent-id>
```

`promote` requests promotion approval. It does not silently enable an agent without the required approval path.

## Delete an agent

```bash
uv run agent-factory delete <agent-id>
```

Deletion is consequential. Confirm the target identifier and inspect staged/enabled state before running it.

## Telegram administration

```bash
uv run agent-factory telegram
```

An optional configured bot name can be supplied as the positional argument. The Factory Telegram interface is for factory administration; Agent Hub remains the platform's main operator entry point.

## Route a registered agent command

```bash
uv run agent-factory route "/agent <alias> <message>"
```

Routing uses the enabled registry and allowed-tool configuration. It does not create or promote agents.
