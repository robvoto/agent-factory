# Agent Factory Platform

A WSL-first platform for creating, running, monitoring, and improving AI agent packages in a controlled way.

The project direction is deliberately bounded:

- create staged agent packages
- validate manifests, tools, permissions, and memory policy
- enable agents only after approval
- run approved agents safely
- turn failures and feedback into reviewed improvement proposals

This is not OpenClaw, not AI Tech Lead, and not Job Hunter.

## Runtime rule

Run this project from WSL.

Use this path in WSL:

```bash
/mnt/e/programming/agent-factory
```

The Windows path exists only for MCP/tool access:

```text
E:\Programming\agent-factory
```

Do not use Windows PowerShell or Windows Python for normal development commands.

## Platform modes

One control surface should eventually support:

```text
Agents   - run, stop, inspect, view logs and costs
Factory  - create staged agent packages
Improve  - review failures and approve proposed fixes
```

Web UI is best for review and editing. Telegram is best for quick control.

## Current implemented scope

- Load manifests from `config/agents`
- Validate required fields
- Reject duplicate aliases
- Reject unknown tools
- Create staged agent packages from bounded requests (deterministic, no LLM)
- Invoke the Factory Brain to design and stage packages via LangGraph react agent
- Route `/agent <alias> <message>`
- List configured agents
- Provide a minimal LangChain harness check for future agent work

No real agents are configured yet. `config/agents` should contain only `.gitkeep`.

## WSL quick setup

This project is `uv`-first. Do not use manual `pip` / `source .venv/bin/activate` as the normal path.

From WSL:

```bash
cd /mnt/e/programming/agent-factory
bash run.sh setup
```

That runs:

```bash
uv sync --all-extras
uv run pytest -q
uv run agent-factory list
uv run agent-factory langchain-check
```

## Daily WSL test command

After setup, use this from WSL:

```bash
cd /mnt/e/programming/agent-factory
bash run.sh all
```

It runs non-mutating checks only:

```text
uv run pytest -q
uv run agent-factory list
uv run agent-factory langchain-check
```

Expected while no agents exist:

```text
No agents configured.
```

## Factory Brain (Stage 2)

The Factory Brain uses a LangGraph react agent to design and stage agent packages.
It loads rules from `memory/factory/AGENTS.md` and skills from `skills/`.

Requires `OPENAI_API_KEY` in the environment or a `.env` file at the project root.

```bash
cd /mnt/e/programming/agent-factory
bash run.sh factory "Create an agent that researches LangChain docs safely"
```

The Factory Brain will:

1. Clarify the request if needed
2. Produce a validated `AgentPackageSpec`
3. Flag risky permissions
4. Create a staged package under `staging/agents/`
5. Present the result for human review

No agent is enabled. No risky tools are granted. Staging only.

## Manual WSL commands

```bash
cd /mnt/e/programming/agent-factory
uv run pytest -q
uv run agent-factory factory "Create an agent that researches docs safely"
uv run agent-factory create "Create an agent that researches docs safely"
uv run agent-factory list
uv run agent-factory langchain-check
```

Run the project:

```bash
cd /mnt/e/programming/agent-factory
bash run.sh
```

`bash run.sh` starts the Telegram Agent Factory app. Use `bash run.sh web` only for the optional local web app.

## Open in VS Code from WSL

```bash
cd /mnt/e/programming/agent-factory
code .
```

## Key docs

- `docs/platform-architecture.md`
- `docs/agent-lifecycle.md`
- `docs/agent-creator-workflow.md`
- `docs/agent-contract.md`
- `docs/permission-model.md`
