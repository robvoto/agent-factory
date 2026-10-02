from __future__ import annotations

from pathlib import Path

import pytest

from agent_factory import factory_brain


def test_factory_backend_uses_virtual_mode() -> None:
    backend = factory_brain._build_filesystem_backend()
    assert backend.virtual_mode is True
    assert backend.cwd == factory_brain._PROJECT_ROOT.resolve()


def test_factory_permissions_are_fail_closed() -> None:
    from deepagents.middleware.filesystem import _check_fs_permission

    rules = factory_brain._build_filesystem_permissions()

    for path in [
        "/docs/guide.md",
        "/skills/agent-authoring/SKILL.md",
        "/memory/factory/AGENTS.md",
        "/templates/agent-package/README.md",
    ]:
        assert _check_fs_permission(rules, "read", path) == "allow"

    for path in [
        "/src/agent_factory/factory_brain.py",
        "/config/factory_settings.json",
        "/data/agent_factory.sqlite3",
        "/.env",
        "/docs/.env",
        "/skills/secrets/key.txt",
        "/etc/passwd",
    ]:
        assert _check_fs_permission(rules, "read", path) == "deny"

    for path in [
        "/docs/guide.md",
        "/staging/agents/new-agent/agent.json",
        "/memory/factory/LEARNINGS.md",
        "/tmp/file.txt",
    ]:
        assert _check_fs_permission(rules, "write", path) == "deny"


def test_virtual_backend_blocks_traversal_and_absolute_escape(tmp_path: Path) -> None:
    from deepagents.backends import FilesystemBackend

    (tmp_path / "allowed.txt").write_text("allowed", encoding="utf-8")
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    with pytest.raises(ValueError, match="traversal"):
        backend.read("/../outside-secret.txt")

    result = backend.read(str(outside))
    assert result.file_data is None
    assert "not found" in (result.error or "").lower()


def test_virtual_backend_blocks_symlink_escape(tmp_path: Path) -> None:
    from deepagents.backends import FilesystemBackend

    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    with pytest.raises(ValueError, match="symlink|outside|root|escape"):
        backend.read("/link.txt")


def test_checkpointer_uses_strict_msgpack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory_brain, "_CHECKPOINT_DB", tmp_path / "checkpoints.sqlite3")
    monkeypatch.setattr(factory_brain, "_checkpointer_conn", None)

    checkpointer = factory_brain._build_checkpointer()
    assert checkpointer.serde._allowed_msgpack_modules is None
    assert checkpointer.serde.pickle_fallback is False


def test_factory_profile_excludes_execute_and_disables_default_subagent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_register(key, profile):
        captured["key"] = key
        captured["profile"] = profile

    monkeypatch.setattr("deepagents.register_harness_profile", fake_register)
    factory_brain._register_factory_harness_profile("openai:gpt-test")

    profile = captured["profile"]
    assert captured["key"] == "openai:gpt-test"
    assert "execute" in profile.excluded_tools
    assert profile.general_purpose_subagent.enabled is False


def test_factory_agent_construction_gates_memory_and_disables_subagents(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    sentinel_agent = object()

    monkeypatch.setattr(factory_brain, "_agents_by_model", {})
    monkeypatch.setattr(factory_brain, "_ensure_dependencies", lambda: None)
    monkeypatch.setattr(factory_brain, "_build_checkpointer", lambda: object())
    monkeypatch.setattr(factory_brain, "_build_filesystem_backend", lambda: object())
    monkeypatch.setattr(factory_brain, "_build_filesystem_permissions", lambda: [object()])
    monkeypatch.setattr(factory_brain, "_build_filesystem_middleware", lambda _backend, _permissions: object())
    monkeypatch.setattr(factory_brain, "_register_factory_harness_profile", lambda _model: None)
    monkeypatch.setattr("agent_factory.factory_tools.get_factory_tools", lambda: [])
    monkeypatch.setattr("agent_factory.knowledge_store.get_knowledge_store", lambda: object())
    monkeypatch.setattr("langmem.create_manage_memory_tool", lambda *a, **k: "manage-memory")
    monkeypatch.setattr("langmem.create_search_memory_tool", lambda *a, **k: "search-memory")
    runtime_model = object()
    model_init: dict[str, object] = {}

    def fake_init_chat_model(model_name, **kwargs):
        model_init["model"] = model_name
        model_init.update(kwargs)
        return runtime_model

    monkeypatch.setattr("langchain.chat_models.init_chat_model", fake_init_chat_model)

    def fake_create_deep_agent(*args, **kwargs):
        captured.update(kwargs)
        return sentinel_agent

    monkeypatch.setattr("deepagents.create_deep_agent", fake_create_deep_agent)

    agent = factory_brain._get_agent("openai:gpt-test")

    assert agent is sentinel_agent
    assert captured["model"] is runtime_model
    assert model_init == {
        "model": "openai:gpt-test",
        "timeout": 60,
        "max_retries": 1,
    }
    assert captured["subagents"] == []
    assert captured["skills"] == ["skills/"]
    assert captured["memory"] == ["memory/factory/AGENTS.md"]
    assert captured["interrupt_on"] == {
        "request_agent_promotion": True,
        "request_approval": True,
        "manage_memory": True,
    }


def test_manage_memory_durable_write_occurs_only_after_human_approval() -> None:
    from collections.abc import Sequence
    from typing import Any

    from deepagents import create_deep_agent
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore
    from langgraph.types import Command
    from langmem import create_manage_memory_tool

    class ScriptedModel(BaseChatModel):
        responses: list[AIMessage]
        index: int = 0

        @property
        def _llm_type(self) -> str:
            return "scripted-memory-approval-test"

        def bind_tools(
            self,
            tools: Sequence[Any],
            *,
            tool_choice: str | None = None,
            **kwargs: Any,
        ):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            message = self.responses[self.index]
            self.index += 1
            return ChatResult(generations=[ChatGeneration(message=message)])

    store = InMemoryStore()
    manage_memory = create_manage_memory_tool(("shared", "factory"), store=store)
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "manage_memory",
                        "args": {"content": "remember alpha", "action": "create"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        tools=[manage_memory],
        store=store,
        checkpointer=MemorySaver(),
        interrupt_on={"manage_memory": True},
        subagents=[],
    )
    config = {"configurable": {"thread_id": "memory-approval-test"}}

    first = agent.invoke(
        {"messages": [{"role": "user", "content": "remember alpha"}]},
        config,
    )
    assert "__interrupt__" in first
    assert store.search(("shared", "factory")) == []

    resumed = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config,
    )
    stored = store.search(("shared", "factory"))
    assert len(stored) == 1
    assert stored[0].value == {"content": "remember alpha"}
    assert resumed["messages"][-1].content == "done"


def test_compiled_factory_filesystem_tool_surface_excludes_shell_subagents_and_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    model = "openai:gpt-4.1-mini"
    factory_brain._register_factory_harness_profile(model)
    backend = StateBackend()
    permissions = factory_brain._build_filesystem_permissions()
    filesystem_middleware = factory_brain._build_filesystem_middleware(backend, permissions)

    agent = create_deep_agent(
        model=model,
        backend=backend,
        permissions=permissions,
        middleware=[filesystem_middleware],
        subagents=[],
    )
    tool_names = set(agent.get_graph().nodes["tools"].data._tools_by_name)

    assert tool_names == {"ls", "read_file", "glob", "grep"}
    assert "execute" not in tool_names
    assert "task" not in tool_names
    assert "write_file" not in tool_names
    assert "edit_file" not in tool_names
    assert "delete" not in tool_names


def test_factory_checkpointer_persists_and_resumes_interrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    monkeypatch.setattr(factory_brain, "_CHECKPOINT_DB", tmp_path / "resume.sqlite3")
    monkeypatch.setattr(factory_brain, "_checkpointer_conn", None)

    class State(TypedDict):
        value: int

    def gated_step(state: State) -> State:
        approved = interrupt("approve")
        return {"value": state["value"] + (1 if approved else 0)}

    builder = StateGraph(State)
    builder.add_node("gated", gated_step)
    builder.add_edge(START, "gated")
    builder.add_edge("gated", END)
    graph = builder.compile(checkpointer=factory_brain._build_checkpointer())
    config = {"configurable": {"thread_id": "factory-test-thread"}}

    first = graph.invoke({"value": 41}, config)
    assert "__interrupt__" in first
    assert graph.get_state(config).next == ("gated",)

    resumed = graph.invoke(Command(resume=True), config)
    assert resumed["value"] == 42
    assert graph.get_state(config).next == ()
