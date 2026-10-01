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
from deepagents.middleware.filesystem import FilesystemMiddleware
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

backend = FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True)
permissions = [
    FilesystemPermission(
        operations=["read"],
        paths=["/docs/**", "/skills/**", "/memory/factory/**", "/templates/**"],
        mode="allow",
    ),
    FilesystemPermission(operations=["read"], paths=["/**"], mode="deny"),
    FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
]
filesystem = FilesystemMiddleware(
    backend=backend,
    tools=["ls", "read_file", "glob", "grep"],
    _permissions=permissions,
)
checkpointer = SqliteSaver(
    conn,
    serde=JsonPlusSerializer(allowed_msgpack_modules=None),
)

agent = create_deep_agent(
    model="openai:gpt-5.6-luna",
    tools=get_factory_tools(),
    system_prompt=_SYSTEM_PROMPT,
    backend=backend,
    permissions=permissions,
    middleware=[filesystem],
    skills=["skills/"],
    memory=["memory/factory/AGENTS.md"],
    checkpointer=checkpointer,
    subagents=[],
    interrupt_on={
        "request_agent_promotion": True,
        "request_approval": True,
        "manage_memory": True,
    },
)
```

Key rules:
- Use `FilesystemBackend(..., virtual_mode=True)` whenever host filesystem paths are exposed.
- Permission paths are virtual root-relative paths such as `/docs/**`; end with an explicit deny-all rule because unmatched paths are otherwise allowed.
- Prefer a custom `FilesystemMiddleware(tools=[...])` when a built-in tool must be removed entirely, not merely hidden from the model.
- Keep built-in filesystem access read-only; use bounded custom tools for intentional writes.
- `skills=` and `memory=` paths are relative to `root_dir`.
- `SqliteSaver` requires `check_same_thread=False` on the connection and a strict serializer such as `JsonPlusSerializer(allowed_msgpack_modules=None)`.
- Disable the default general-purpose subagent when the agent does not need delegation; passing `subagents=[]` alone is not sufficient unless the active harness profile also disables it.
- Do not use `create_react_agent` — it has no skills, memory, or interrupt_on support.

## Tool design

- Prefer bounded tool functions over broad filesystem or shell access
- Use `@tool` decorator from `langchain_core.tools`
- Tools must have clear docstrings — the LLM reads them to decide when to call
- Keep tool inputs serializable (str, int, bool) — no Pydantic objects as direct parameters
- Accept JSON strings for complex inputs and parse them inside the tool

## Human-in-the-loop

- `interrupt_on={"tool_name": True}` pauses the graph before that tool runs.
- A `checkpointer` is required — without it, state cannot be resumed.
- Resume with `Command(resume={"decisions": [{"type": "approve"}]})`, providing one decision per pending action request.
- Reject with `Command(resume={"decisions": [{"type": "reject", "message": reason}]})`.
- Gate durable memory mutation (`manage_memory`) as well as promotion/approval actions.
- Check if paused with `len(agent.get_state(config).next) > 0`.

## Skills vs memory vs prompts

- Skills: detailed procedural knowledge — keep in SKILL.md files, load on demand
- Memory: critical always-active rules only — keep in AGENTS.md, always loaded
- System prompt: identity and core rules only — memory param handles the rest

## Subagent guidance

- Use subagents only when context isolation is clearly valuable
- Subagent toolsets must be minimal — no extra permissions without review
- Pass focused, compressed briefs to subagents — not raw conversation history

## Cost discipline

- Default model: `openai:gpt-5.6-luna` via the `luna` alias (set in `config/factory_settings.json`)
- Use model aliases from settings: `codex` → `openai:o4-mini`, `claude` → `anthropic:claude-sonnet-4-6`
- Do not use large models without a clear reason
- Do not run online research unless explicitly approved
