---
name: deep-agents-factory
description: How to create LangChain Deep Agents correctly in this project
---

# Skill: Deep Agents Factory

How to create LangChain Deep Agents correctly in this project.

## Creating agents

Use `create_deep_agent` from `deepagents`:

```python
from deepagents import create_deep_agent, FilesystemPermission
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.sqlite import SqliteSaver

agent = create_deep_agent(
    model="openai:gpt-4.1-mini",
    tools=get_factory_tools(),
    system_prompt=_SYSTEM_PROMPT,
    backend=FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=False),
    permissions=[
        FilesystemPermission(operations=["read"], paths=["/abs/path/to/docs/"]),
        FilesystemPermission(operations=["write"], paths=["/abs/path/to/staging/"]),
    ],
    skills=["skills/"],
    memory=["memory/factory/AGENTS.md"],
    checkpointer=SqliteSaver(conn),
    interrupt_on={"request_agent_promotion": True, "request_approval": True},
)
```

Key rules:
- Paths in `FilesystemPermission` must be **absolute strings**
- `skills=` and `memory=` paths are relative to `root_dir`
- `SqliteSaver` requires `check_same_thread=False` on the connection
- Do not use `create_react_agent` — it has no skills, memory, or interrupt_on support

## Tool design

- Prefer bounded tool functions over broad filesystem or shell access
- Use `@tool` decorator from `langchain_core.tools`
- Tools must have clear docstrings — the LLM reads them to decide when to call
- Keep tool inputs serializable (str, int, bool) — no Pydantic objects as direct parameters
- Accept JSON strings for complex inputs and parse them inside the tool

## Human-in-the-loop

- `interrupt_on={"tool_name": True}` pauses the graph before that tool runs
- A `checkpointer` is required — without it, state cannot be resumed
- Resume with `agent.invoke(None, config=config)` after human approves
- Inject rejection with `agent.update_state(config, {"messages": [HumanMessage(...)]})` then resume
- Check if paused: `len(agent.get_state(config).next) > 0`

## Skills vs memory vs prompts

- Skills: detailed procedural knowledge — keep in SKILL.md files, load on demand
- Memory: critical always-active rules only — keep in AGENTS.md, always loaded
- System prompt: identity and core rules only — memory param handles the rest

## Subagent guidance

- Use subagents only when context isolation is clearly valuable
- Subagent toolsets must be minimal — no extra permissions without review
- Pass focused, compressed briefs to subagents — not raw conversation history

## Cost discipline

- Default model: `openai:gpt-4.1-mini` (set in `config/factory_settings.json`)
- Use model aliases from settings: `codex` → `openai:o4-mini`, `claude` → `anthropic:claude-sonnet-4-6`
- Do not use large models without a clear reason
- Do not run online research unless explicitly approved
