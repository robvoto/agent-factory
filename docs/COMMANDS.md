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
- Configured defaults are Luna (`general`) and Codex (`coding`). Precedence is purpose-specific environment variable, then `FACTORY_MODEL`, then the configured default. Environment values may be aliases or provider model strings.
- `langchain-check` verifies the LangChain runtime import path.

## Test an incubating subprocess agent

Create a JSON task file, inspect the package and permissions, then run:

```bash
uv run agent-factory test <agent-id> --input-json /path/to/task.json --approve
uv run agent-factory test-runs [agent-id]
```

The test command accepts only a validated package in `staging/agents/<id>/` with
`runtime.mode = "subprocess"` and a `python <relative-script.py>` entrypoint. It
copies that package to a temporary directory, runs the declared entrypoint there,
passes temporary input/output JSON files, validates the returned status, and
deletes the temporary copy when the command ends. It refuses packages already
released or present in the enabled registry. It does not use Agent Hub, Telegram,
the enabled registry, or the release path.

This is a local process, not an operating-system sandbox: package code runs with
the current user's filesystem and network access. Review the package before
approving a run. Declared network, filesystem-write, shell, or environment
access also requires `--approve-risk`. Environment variables are not inherited;
expose only a specifically reviewed variable when needed:

```bash
uv run agent-factory test <agent-id> --input-json /path/to/task.json \
  --approve --approve-risk --expose-env API_KEY_NAME
```

The harness fails closed for declared tools or MCP capabilities because it does
not provide those integrations. `test-runs` lists timestamps, identifiers,
package/manifest/input hashes, approval and outcome metadata; task input and
agent output are not stored in the audit table. The invocation prints the result
to the operator's terminal.

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
