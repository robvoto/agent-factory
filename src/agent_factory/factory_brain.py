"""Factory Brain: Deep Agent for designing and staging agent packages.

Uses create_deep_agent with SqliteSaver checkpointer for persistent conversations,
interrupt_on for human-in-the-loop approval, and FilesystemBackend (read-only on
docs/skills/memory/templates) plus bounded write tools.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from langgraph.types import Command

from .progress_events import ProgressReporter, run_agent_with_progress

_PROJECT_ROOT = Path(__file__).parents[2]
_CHECKPOINT_DB = _PROJECT_ROOT / "data" / "factory_checkpoints.sqlite3"
logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the Agent Factory Brain.

Your job is to help design and stage AI agent packages for the Agent Factory Platform.

Core rules:
- Clarify ambiguous requests before acting.
- Produce a validated AgentPackageSpec JSON before staging a package.
- Write agent.json purpose as the single routing contract with exactly three sections: Primary responsibility, Select for, and Do not select for.
- Make each purpose specific enough to distinguish the agent from other registered agents; never submit a vague one-sentence purpose.
- Follow these routing-purpose examples:

Good coding-agent purpose:
Primary responsibility: Lead and execute work on new or existing technical solutions.
Select for: Implementing backlog items, building new technical solutions, or changing code, tests, configuration, architecture, infrastructure, or documentation for a new or existing technical solution, regardless of technology stack or hosting location, subject only to available authorised access.
Do not select for: Designing, staging, approving, rejecting, or promoting a new specialist agent package as the requested deliverable.

Good Agent Factory purpose:
Primary responsibility: Design and govern new specialist agent packages.
Select for: Creating, configuring, validating, staging, approving, rejecting, or promoting a specialist agent package as the requested deliverable.
Do not select for: Implementing backlog items, fixing bugs, changing documentation, or modifying source code in the existing Agent Factory repository or any other existing software project.

Good research-agent purpose:
Primary responsibility: Research and summarise LangChain documentation and implementation patterns.
Select for: Evidence-based questions requiring current LangChain documentation, APIs, or architecture guidance.
Do not select for: Implementing code changes or researching topics outside the LangChain ecosystem.

Bad purpose — reject it:
Handles useful work and helps with agents.
- Flag risky permissions (shell, network, filesystem_write) explicitly.
- Use request_approval before promoting, enabling, or modifying shared memory.
- Never enable an agent yourself — staging only.
- Ask when uncertain rather than guessing.
- Call list_known_agents before creating or promoting an agent so reused staged or enabled agents are not duplicated.
- Before answering architecture or "what should we do next" questions, call search_memory or search_trusted_sources for relevant context, including Thoughtworks Radar when judging current engineering patterns.
- Prefer retrieved context over memory drift or guessing.
- Call manage_memory to save architectural decisions, user preferences, and patterns — do not rely on conversation history alone.
- Prefer small, cheap models and bounded tools.
"""

# Module-level singletons — created once, reused across requests.
_checkpointer_conn: sqlite3.Connection | None = None
_agents_by_model: dict[str, Any] = {}


def _get_agent(resolved_model: str) -> Any:
    """Return the compiled Factory Brain agent for a resolved model."""
    global _checkpointer_conn

    cached = _agents_by_model.get(resolved_model)
    if cached is not None:
        logger.debug("Reusing cached Factory Brain agent for %s.", resolved_model)
        return cached

    logger.info("Creating Factory Brain agent for %s.", resolved_model)
    _ensure_dependencies()

    import deepagents
    from deepagents import FilesystemPermission, create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langgraph.checkpoint.sqlite import SqliteSaver

    from langmem import create_manage_memory_tool, create_search_memory_tool

    from .factory_tools import get_factory_tools
    from .knowledge_store import get_knowledge_store

    _CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    if _checkpointer_conn is None:
        _checkpointer_conn = sqlite3.connect(str(_CHECKPOINT_DB), check_same_thread=False)
    checkpointer = SqliteSaver(_checkpointer_conn)

    backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT), virtual_mode=False)

    r = str(_PROJECT_ROOT)
    permissions = [
        FilesystemPermission(
            operations=["read"],
            paths=[f"{r}/docs/", f"{r}/skills/", f"{r}/memory/factory/", f"{r}/templates/"],
        ),
        FilesystemPermission(operations=["write"], paths=[f"{r}/staging/agents/", f"{r}/memory/factory/LEARNINGS.md"]),
    ]

    store = get_knowledge_store()
    memory_tools = [
        create_manage_memory_tool(("factory", "learnings"), store=store,
            instructions="Save architectural decisions, user preferences, approved/rejected patterns, and any knowledge useful across future sessions."),
        create_search_memory_tool(("shared", "docs"), store=store,
            instructions="Search local project documentation and knowledge base."),
        create_search_memory_tool(("shared", "trusted"), store=store,
            name="search_trusted_sources",
            instructions="Search indexed trusted online sources (LangChain docs, Anthropic docs, etc.)."),
    ]

    agent = create_deep_agent(
        model=resolved_model,
        tools=[*get_factory_tools(), *memory_tools],
        system_prompt=_SYSTEM_PROMPT,
        backend=backend,
        permissions=permissions,
        skills=["skills/"],
        memory=["memory/factory/AGENTS.md"],
        checkpointer=checkpointer,
        store=store,
        interrupt_on={
            "request_agent_promotion": True,
            "request_approval": True,
        },
    )
    _agents_by_model[resolved_model] = agent
    logger.debug("Factory Brain agent compiled successfully for %s.", resolved_model)
    return agent


def invoke_factory_brain(
    request: str,
    *,
    thread_id: str | None = None,
    model: str | None = None,
    purpose: str = "coding",
    progress_reporter: ProgressReporter | None = None,
) -> tuple[str, bool]:
    """Invoke the Factory Brain with a plain-language request.

    Returns (response_text, is_interrupted).
    is_interrupted=True means the agent paused to wait for human approval.

    Requires OPENAI_API_KEY in the environment or a .env file at the project root.
    """
    reporter = progress_reporter or ProgressReporter()
    reporter.started("Factory Brain accepted the agent-design request.")
    started_at = time.perf_counter()

    try:
        _ensure_openai_credentials()

        import uuid
        from langchain_core.callbacks import UsageMetadataCallbackHandler
        from .factory_settings import resolve_model

        resolved_model = resolve_model(model, purpose=purpose)
        agent = _get_agent(resolved_model)
        tid = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": tid}}
        usage_cb = UsageMetadataCallbackHandler()
        run_config = {**config, "callbacks": [usage_cb]}
    except (KeyboardInterrupt, SystemExit):
        reporter.cancelled()
        raise
    except Exception:
        reporter.failed("Factory Brain could not start. Check the final error.")
        logger.exception("Factory Brain failed during startup.")
        raise

    logger.info("Invoking Factory Brain for thread %s.", tid)
    logger.debug("Factory Brain request: %s", request)
    reporter.phase("design", "Factory Brain is designing the agent package.")

    try:
        with reporter.heartbeat_scope():
            result = run_agent_with_progress(
                agent,
                {"messages": [{"role": "user", "content": request}]},
                config=run_config,
                reporter=reporter,
            )
    except (KeyboardInterrupt, SystemExit):
        reporter.cancelled()
        raise
    except Exception as exc:
        reporter.failed()
        _record_llm_run(
            operation="invoke_factory_brain",
            request_kind="new-thread" if thread_id is None else "thread-turn",
            requested_model=model,
            effective_model=resolved_model,
            status="error",
            duration_seconds=time.perf_counter() - started_at,
            usage_cb=usage_cb,
            thread_id=tid,
            error=str(exc),
        )
        raise

    reporter.phase("validation", "Factory Brain is validating the result.")
    response = _extract_response(result)
    interrupted = _is_interrupted(agent, config)
    if interrupted:
        reporter.waiting(
            "waiting_approval",
            "Factory Brain is waiting for human approval.",
        )
    else:
        reporter.completed("Factory Brain completed the agent-design task.")
    _record_llm_run(
        operation="invoke_factory_brain",
        request_kind="new-thread" if thread_id is None else "thread-turn",
        requested_model=model,
        effective_model=resolved_model,
        duration_seconds=time.perf_counter() - started_at,
        usage_cb=usage_cb,
        thread_id=tid,
        result_preview=response,
    )
    logger.info("Factory Brain completed for thread %s; interrupted=%s", tid, interrupted)
    logger.debug("Factory Brain response: %s", response)
    return response, interrupted


def resume_factory_brain(
    thread_id: str,
    *,
    model: str | None = None,
    purpose: str = "coding",
    progress_reporter: ProgressReporter | None = None,
) -> tuple[str, bool]:
    """Resume an interrupted Factory Brain conversation.

    Call this after the human has approved the pending action.
    Returns (response_text, is_interrupted) — is_interrupted=True if it
    paused again waiting for another approval.
    """
    reporter = progress_reporter or ProgressReporter()
    reporter.started("Factory Brain resumed the approved task.")
    started_at = time.perf_counter()

    try:
        _ensure_openai_credentials()

        from langchain_core.callbacks import UsageMetadataCallbackHandler
        from .factory_settings import resolve_model

        resolved_model = resolve_model(model, purpose=purpose)
        agent = _get_agent(resolved_model)
        config = {"configurable": {"thread_id": thread_id}}
        usage_cb = UsageMetadataCallbackHandler()
        run_config = {**config, "callbacks": [usage_cb]}
    except (KeyboardInterrupt, SystemExit):
        reporter.cancelled()
        raise
    except Exception:
        reporter.failed("Factory Brain could not resume. Check the final error.")
        logger.exception("Factory Brain failed during resume startup.")
        raise

    logger.info("Resuming Factory Brain thread %s.", thread_id)
    reporter.phase("approval", "Factory Brain is applying the approved action.")
    try:
        with reporter.heartbeat_scope():
            decision_count = _pending_decision_count(agent, config)
            result = run_agent_with_progress(
                agent,
                Command(resume={"decisions": [{"type": "approve"}] * decision_count}),
                config=run_config,
                reporter=reporter,
            )
    except (KeyboardInterrupt, SystemExit):
        reporter.cancelled()
        raise
    except Exception as exc:
        reporter.failed()
        _record_llm_run(
            operation="resume_factory_brain",
            request_kind="resume",
            requested_model=model,
            effective_model=resolved_model,
            status="error",
            duration_seconds=time.perf_counter() - started_at,
            usage_cb=usage_cb,
            thread_id=thread_id,
            error=str(exc),
        )
        raise
    reporter.phase("validation", "Factory Brain is validating the resumed result.")
    response = _extract_response(result)
    interrupted = _is_interrupted(agent, config)
    if interrupted:
        reporter.waiting(
            "waiting_approval",
            "Factory Brain is waiting for another human approval.",
        )
    else:
        reporter.completed("Factory Brain completed the approved task.")
    _record_llm_run(
        operation="resume_factory_brain",
        request_kind="resume",
        requested_model=model,
        effective_model=resolved_model,
        duration_seconds=time.perf_counter() - started_at,
        usage_cb=usage_cb,
        thread_id=thread_id,
        result_preview=response,
    )
    logger.info("Factory Brain resume completed for thread %s; interrupted=%s", thread_id, interrupted)
    return response, interrupted


def reject_factory_brain(
    thread_id: str,
    reason: str = "Rejected by user",
    *,
    model: str | None = None,
    purpose: str = "coding",
    progress_reporter: ProgressReporter | None = None,
) -> str:
    """Inject a rejection message into an interrupted conversation and resume.

    The agent will receive the rejection and respond accordingly.
    """
    reporter = progress_reporter or ProgressReporter()
    reporter.started("Factory Brain received the rejection.")
    started_at = time.perf_counter()

    try:
        _ensure_openai_credentials()

        from langchain_core.callbacks import UsageMetadataCallbackHandler
        from .factory_settings import resolve_model

        resolved_model = resolve_model(model, purpose=purpose)
        agent = _get_agent(resolved_model)
        config = {"configurable": {"thread_id": thread_id}}
        usage_cb = UsageMetadataCallbackHandler()
        run_config = {**config, "callbacks": [usage_cb]}
    except (KeyboardInterrupt, SystemExit):
        reporter.cancelled()
        raise
    except Exception:
        reporter.failed("Factory Brain could not apply the rejection. Check the final error.")
        logger.exception("Factory Brain failed during rejection startup.")
        raise

    logger.info("Rejecting Factory Brain thread %s: %s", thread_id, reason)
    reporter.phase("approval", "Factory Brain is applying the rejection safely.")
    try:
        with reporter.heartbeat_scope():
            decision_count = _pending_decision_count(agent, config)
            result = run_agent_with_progress(
                agent,
                Command(
                    resume={
                        "decisions": [{"type": "reject", "message": reason}] * decision_count
                    }
                ),
                config=run_config,
                reporter=reporter,
            )
    except (KeyboardInterrupt, SystemExit):
        reporter.cancelled()
        raise
    except Exception as exc:
        reporter.failed()
        _record_llm_run(
            operation="reject_factory_brain",
            request_kind="reject",
            requested_model=model,
            effective_model=resolved_model,
            status="error",
            duration_seconds=time.perf_counter() - started_at,
            usage_cb=usage_cb,
            thread_id=thread_id,
            error=str(exc),
        )
        raise
    reporter.phase("validation", "Factory Brain is validating the rejection result.")
    response = _extract_response(result)
    reporter.completed("Factory Brain completed the rejected task safely.")
    _record_llm_run(
        operation="reject_factory_brain",
        request_kind="reject",
        requested_model=model,
        effective_model=resolved_model,
        duration_seconds=time.perf_counter() - started_at,
        usage_cb=usage_cb,
        thread_id=thread_id,
        result_preview=response,
    )
    logger.debug("Factory Brain rejection response for thread %s: %s", thread_id, response)
    return response


def list_checkpoints(thread_id: str, *, model: str | None = None, purpose: str = "general") -> list[dict]:
    """Return the last 10 checkpoints for a thread, newest first."""
    from .factory_settings import resolve_model

    resolved_model = resolve_model(model, purpose=purpose)
    agent = _get_agent(resolved_model)
    config = {"configurable": {"thread_id": thread_id}}
    history = list(agent.get_state_history(config))
    results = []
    for state in history[:10]:
        ts = state.config["configurable"].get("checkpoint_id", "")
        msg_count = len(state.values.get("messages", []))
        last_msg = ""
        msgs = state.values.get("messages", [])
        if msgs:
            last = msgs[-1]
            content = last.content if hasattr(last, "content") else ""
            last_msg = (content[:80] + "…") if isinstance(content, str) and len(content) > 80 else str(content)[:80]
        results.append({"checkpoint_id": ts, "message_count": msg_count, "preview": last_msg})
    return results


def fork_thread(thread_id: str, checkpoint_id: str, new_thread_id: str, *, model: str | None = None, purpose: str = "general") -> str:
    """Fork a new thread from a specific checkpoint of an existing thread."""
    import uuid
    from .factory_settings import resolve_model

    resolved_model = resolve_model(model, purpose=purpose)
    agent = _get_agent(resolved_model)
    src_config = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
    state = agent.get_state(src_config)
    if not state:
        raise ValueError(f"Checkpoint {checkpoint_id!r} not found in thread {thread_id!r}")
    dst_config = {"configurable": {"thread_id": new_thread_id}}
    agent.update_state(dst_config, state.values)
    logger.info("Forked thread %s from checkpoint %s → new thread %s", thread_id, checkpoint_id, new_thread_id)
    return new_thread_id


def _is_interrupted(agent: Any, config: dict) -> bool:
    """Return True if the agent graph is paused waiting for a human."""
    try:
        state = agent.get_state(config)
        return len(state.next) > 0
    except Exception as exc:
        logger.exception("Unable to inspect Factory Brain interrupt state.")
        raise RuntimeError("Unable to inspect Factory Brain interrupt state.") from exc


def _pending_decision_count(agent: Any, config: dict) -> int:
    """Count how many approval decisions HumanInTheLoopMiddleware is waiting for.

    `interrupt(hitl_request)["decisions"]` (see langchain's human_in_the_loop
    middleware) requires exactly one decision per pending `action_requests`
    entry, or it raises a mismatch error. Factory Brain only ever gates one
    tool (`request_approval`), so this is normally 1, but it's read from the
    actual pending interrupt rather than assumed.
    """
    state = agent.get_state(config)
    total = sum(
        len(pending.value["action_requests"])
        for pending in state.interrupts
        if isinstance(pending.value, dict)
        and isinstance(pending.value.get("action_requests"), list)
    )
    return total or 1


def _extract_response(result: Any) -> str:
    if result is None:
        return "Factory Brain returned no response."
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return "Factory Brain returned no response."
    last = messages[-1]
    content = last.content if hasattr(last, "content") else str(last)
    if isinstance(content, list):
        # Reasoning models return content as a list of typed blocks — extract text only
        parts = [
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ]
        return "\n".join(parts).strip() or "Factory Brain returned no response."
    return content


def check_factory_brain_dependencies() -> None:
    """Fail clearly when the declared Factory Brain runtime is incomplete."""

    _ensure_dependencies()


def _ensure_dependencies() -> None:
    try:
        import deepagents  # noqa: F401
        from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: F401
    except ImportError as exc:
        logger.exception("Factory Brain dependencies are missing.")
        raise RuntimeError(
            "Factory Brain dependencies are not installed. "
            "Run: uv sync --extra langchain"
        ) from exc


def _ensure_openai_credentials() -> None:
    """Load .env if needed and fail clearly if OPENAI_API_KEY is still missing.

    Each invoke/resume/reject call runs as its own fresh subprocess (see
    AGENT-HUB-007's live smoke test), so none of them can assume the parent
    process's environment already has the key — every entry point that
    creates the agent must check this itself.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        _try_load_dotenv()
    _check_api_key()


def _check_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Add it to a .env file at the project root or export it before running."
        )


def _try_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        logger.debug("python-dotenv is not installed; skipping .env loading.")


def _record_llm_run(
    *,
    operation: str,
    request_kind: str,
    requested_model: str | None,
    effective_model: str | None,
    duration_seconds: float,
    usage_cb: Any,
    thread_id: str | None,
    status: str = "ok",
    error: str | None = None,
    result_preview: str | None = None,
) -> None:
    from .cost_log import extract_usage_metadata, record_llm_run

    resolved_effective_model = effective_model
    resolved_requested_model = requested_model or resolved_effective_model

    record_llm_run(
        operation=operation,
        request_kind=request_kind,
        requested_model=resolved_requested_model,
        effective_model=resolved_effective_model,
        status=status,
        duration_seconds=duration_seconds,
        usage_by_model=extract_usage_metadata(usage_cb),
        error=error,
        thread_id=thread_id,
        result_preview=result_preview,
    )
