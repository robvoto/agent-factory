"""Telegram gateway for the Agent Factory Platform.

Polls Telegram for messages and routes them to the Factory Brain.
Supports slash commands and natural language requests with interrupt_on approval.

Required environment variables (load from .env):
  Configured bot token and authorized chat IDs environment names from
  config/factory_settings.json under telegram_bots[]
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .factory_brain import fork_thread, invoke_factory_brain, list_checkpoints, reject_factory_brain, resume_factory_brain
from .logging_utils import configure_logging
from .storage import (
    create_approval,
    decide_approval,
    delete_staged_agent_record,
    get_approval,
    get_or_create_thread,
    get_thread_state,
    reset_thread,
    list_pending_approvals,
    list_staged_agent_records,
    set_thread_interrupted,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[2]
_POLL_TIMEOUT = 25
_RETRY_DELAY = 5


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.debug("python-dotenv is not installed; skipping .env loading.")
        return

    loaded = load_dotenv(_PROJECT_ROOT / ".env")
    logger.debug("Loaded .env from %s: %s", _PROJECT_ROOT / ".env", loaded)


def _tg_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _tg_request(token: str, method: str, payload: dict) -> dict:
    url = _tg_url(token, method)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {exc.code}: {body}") from exc


def _send(token: str, chat_id: str | int, text: str) -> None:
    logger.debug("Sending Telegram message to chat_id=%s: %s", chat_id, text[:120].replace("\n", " "))
    _tg_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "HTML",
    })


def _get_updates(token: str, offset: int) -> list[dict]:
    logger.debug("Polling Telegram updates from offset=%s", offset)
    result = _tg_request(token, "getUpdates", {
        "offset": offset,
        "timeout": _POLL_TIMEOUT,
        "allowed_updates": ["message"],
    })
    return result.get("result", [])


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_help(token: str, chat_id: str) -> None:
    logger.info("Serving help to chat_id=%s", chat_id)
    _send(token, chat_id, (
        "<b>Agent Factory — Factory Brain</b>\n"
        "You are talking to the Factory Brain. It designs, stages, and approves agents.\n\n"
        "/help — show this\n"
        "/status — platform status\n"
        "/staged — list staged agent drafts\n"
        "/pending — list pending approvals\n"
        "/approve [id] — approve pending action or resume interrupted agent\n"
        "/reject [id] [reason] — reject or cancel\n"
        "/new — start a fresh session and clear the current context\n"
        "/checkpoints — list recent checkpoints for the current session\n"
        "/rollback &lt;checkpoint-id&gt; — restore session to a past checkpoint\n"
        "/fork &lt;checkpoint-id&gt; — branch a new session from a past checkpoint\n"
        "/delete &lt;agent-id&gt; — delete a staged or enabled agent\n\n"
        "Or send a plain message to the Factory Brain.\n"
        "Example: <i>Create an agent that researches LangChain docs</i>"
    ))


def _cmd_status(token: str, chat_id: str) -> None:
    logger.info("Serving status to chat_id=%s", chat_id)
    staged = list_staged_agent_records()
    pending = list_pending_approvals()
    thread = get_thread_state(chat_id)
    interrupted = thread and thread["is_interrupted"]
    _send(token, chat_id, (
        "<b>Agent Factory status</b>\n\n"
        f"Staged drafts: {len(staged)}\n"
        f"Pending approvals: {len(pending)}\n"
        f"Enabled agents: see config/agents/\n"
        + ("<b>⚠ Factory Brain is waiting for your approval.</b>\nSend /approve or /reject." if interrupted else "")
    ))


def _cmd_staged(token: str, chat_id: str) -> None:
    logger.info("Listing staged agents for chat_id=%s", chat_id)
    records = list_staged_agent_records()
    if not records:
        _send(token, chat_id, "No staged agent drafts.")
        return
    lines = ["<b>Staged agent drafts</b>\n"]
    for r in records:
        lines.append(f"• <code>{r['agent_id']}</code> — {r['status']}")
    _send(token, chat_id, "\n".join(lines))


def _cmd_pending(token: str, chat_id: str) -> None:
    logger.info("Listing pending approvals for chat_id=%s", chat_id)
    records = list_pending_approvals()
    if not records:
        _send(token, chat_id, "No pending approvals.")
        return
    lines = ["<b>Pending approvals</b>\n"]
    for r in records:
        lines.append(
            f"ID {r['id']} [{r['approval_type']}] {r['target_id']}\n"
            f"  {r['summary'][:120]}"
        )
    _send(token, chat_id, "\n".join(lines))


def _cmd_approve(token: str, chat_id: str, args: str, *, model: str | None = None, purpose: str = "general") -> None:
    parts = args.strip().split(None, 1)

    # /approve with no ID — resume an interrupted Factory Brain conversation
    if not parts or not parts[0].isdigit():
        thread = get_thread_state(chat_id)
        if thread and thread["is_interrupted"]:
            logger.info("Resuming interrupted Factory Brain thread for chat_id=%s", chat_id)
            _send(token, chat_id, "Resuming Factory Brain...")
            try:
                response, still_interrupted = resume_factory_brain(
                    thread["thread_id"],
                    model=model,
                    purpose=purpose,
                )
                set_thread_interrupted(chat_id, still_interrupted)
                _send(token, chat_id, response)
                if still_interrupted:
                    _send(token, chat_id, "Factory Brain is paused again. Send /approve or /reject.")
            except Exception as exc:
                logger.exception("Error resuming Factory Brain")
                _send(token, chat_id, f"Resume error: {exc}")
        else:
            logger.warning("Approve requested with no pending interrupt for chat_id=%s", chat_id)
            _send(token, chat_id, "No pending interrupt. Use /approve &lt;id&gt; for a specific approval.")
        return

    # /approve <id> — approve a specific SQLite approval record
    approval_id = int(parts[0])
    logger.info("Approving record %s for chat_id=%s", approval_id, chat_id)
    record = get_approval(approval_id)
    if not record:
        logger.warning("Approval %s not found for chat_id=%s", approval_id, chat_id)
        _send(token, chat_id, f"Approval {approval_id} not found.")
        return
    if record["status"] != "pending":
        logger.warning("Approval %s is already %s", approval_id, record["status"])
        _send(token, chat_id, f"Approval {approval_id} is already {record['status']}.")
        return

    decide_approval(approval_id, "approved", "Approved via Telegram")
    if record["approval_type"] == "promote-agent":
        result = _promote_agent(record["target_id"])
        logger.info("Approved promotion for staged agent %s", record["target_id"])
        _send(token, chat_id, f"Approved. {result}")
    else:
        logger.info("Approval %s approved.", approval_id)
        _send(token, chat_id, f"Approval {approval_id} approved.")


def _cmd_reject(token: str, chat_id: str, args: str, *, model: str | None = None, purpose: str = "general") -> None:
    parts = args.strip().split(None, 1)

    # /reject with no ID — reject an interrupted Factory Brain conversation
    if not parts or not parts[0].isdigit():
        reason = parts[0] if parts else "Rejected by user"
        thread = get_thread_state(chat_id)
        if thread and thread["is_interrupted"]:
            logger.info("Rejecting interrupted Factory Brain thread for chat_id=%s", chat_id)
            _send(token, chat_id, "Sending rejection to Factory Brain...")
            try:
                response = reject_factory_brain(
                    thread["thread_id"],
                    reason,
                    model=model,
                    purpose=purpose,
                )
                set_thread_interrupted(chat_id, False)
                _send(token, chat_id, response)
            except Exception as exc:
                logger.exception("Error rejecting Factory Brain")
                _send(token, chat_id, f"Reject error: {exc}")
        else:
            logger.warning("Reject requested with no pending interrupt for chat_id=%s", chat_id)
            _send(token, chat_id, "No pending interrupt. Use /reject &lt;id&gt; [reason] to reject a pending approval, or /delete &lt;agent-id&gt; to remove a staged agent.")
        return

    # /reject <id> [reason] — reject a specific SQLite approval record
    approval_id = int(parts[0])
    reason = parts[1].strip() if len(parts) > 1 else "Rejected via Telegram"
    logger.info("Rejecting record %s for chat_id=%s", approval_id, chat_id)
    record = get_approval(approval_id)
    if not record:
        logger.warning("Approval %s not found for chat_id=%s", approval_id, chat_id)
        _send(token, chat_id, f"Approval {approval_id} not found.")
        return
    if record["status"] != "pending":
        logger.warning("Approval %s is already %s", approval_id, record["status"])
        _send(token, chat_id, f"Approval {approval_id} is already {record['status']}.")
        return

    decide_approval(approval_id, "rejected", reason)
    logger.info("Approval %s rejected: %s", approval_id, reason)
    _send(token, chat_id, f"Approval {approval_id} rejected. Reason: {reason}")


def _cmd_delete(token: str, chat_id: str, args: str) -> None:
    parts = args.strip().split()
    if not parts:
        logger.warning("Delete requested without an agent id for chat_id=%s", chat_id)
        _send(token, chat_id, "Usage: /delete &lt;agent-id&gt; [confirm]")
        return

    agent_id = parts[0]
    confirmed = len(parts) > 1 and parts[1].lower() == "confirm"

    if not confirmed:
        staging_dir = _PROJECT_ROOT / "staging" / "agents" / agent_id
        enabled_json = _PROJECT_ROOT / "config" / "agents" / f"{agent_id}.json"
        from .storage import get_staged_agent_record
        record = get_staged_agent_record(agent_id)
        locations = []
        if staging_dir.exists():
            locations.append("staging/agents/")
        if enabled_json.exists():
            locations.append("config/agents/ <b>(ENABLED — currently running)</b>")
        if record:
            locations.append("database record")
        if not locations:
            _send(token, chat_id, f"Agent '{agent_id}' not found in staging, config/agents, or database.")
            return
        _send(token, chat_id,
            f"⚠ This will permanently delete <code>{agent_id}</code> from:\n"
            + "\n".join(f"• {loc}" for loc in locations)
            + f"\n\nTo confirm: /delete {agent_id} confirm")
        return

    logger.info("Deleting agent %s for chat_id=%s", agent_id, chat_id)
    result = _delete_agent(agent_id)
    _send(token, chat_id, result)


def _cmd_new(token: str, chat_id: str, *, model: str | None = None, purpose: str = "general") -> None:
    logger.info("Starting a new Factory Brain session for chat_id=%s", chat_id)
    try:
        from .factory_settings import resolve_model
        resolved = resolve_model(model, purpose=purpose)
        reset_thread(chat_id)
        _send(token, chat_id, f"<b>Factory Brain</b> — new session started. Previous context cleared.\nModel: <code>{resolved}</code>")
    except Exception as exc:
        logger.exception("Error starting new Factory Brain session")
        _send(token, chat_id, f"New session error: {exc}")


# ---------------------------------------------------------------------------
# Checkpoint / fork commands
# ---------------------------------------------------------------------------

def _cmd_checkpoints(token: str, chat_id: str, *, model: str | None = None, purpose: str = "general") -> None:
    thread = get_thread_state(chat_id)
    if not thread:
        _send(token, chat_id, "No active session. Start a conversation first.")
        return
    try:
        checkpoints = list_checkpoints(thread["thread_id"], model=model, purpose=purpose)
    except Exception as exc:
        _send(token, chat_id, f"Error listing checkpoints: {exc}")
        return
    if not checkpoints:
        _send(token, chat_id, "No checkpoints found for current session.")
        return
    lines = ["<b>Recent checkpoints</b> (newest first)\n"]
    for i, cp in enumerate(checkpoints):
        lines.append(f"{i+1}. <code>{cp['checkpoint_id'][:20]}…</code> — {cp['message_count']} msgs\n   <i>{cp['preview']}</i>")
    lines.append("\nTo rollback: /rollback &lt;checkpoint-id&gt;\nTo fork: /fork &lt;checkpoint-id&gt;")
    _send(token, chat_id, "\n".join(lines))


def _cmd_rollback(token: str, chat_id: str, args: str, *, model: str | None = None, purpose: str = "general") -> None:
    checkpoint_id = args.strip()
    if not checkpoint_id:
        _send(token, chat_id, "Usage: /rollback &lt;checkpoint-id&gt;")
        return
    thread = get_thread_state(chat_id)
    if not thread:
        _send(token, chat_id, "No active session.")
        return
    try:
        from .factory_settings import resolve_model
        from .factory_brain import _get_agent
        resolved = resolve_model(model, purpose=purpose)
        agent = _get_agent(resolved)
        src_config = {"configurable": {"thread_id": thread["thread_id"], "checkpoint_id": checkpoint_id}}
        state = agent.get_state(src_config)
        agent.update_state({"configurable": {"thread_id": thread["thread_id"]}}, state.values)
        _send(token, chat_id, f"Rolled back to checkpoint <code>{checkpoint_id[:20]}…</code>\nConversation restored to that point.")
    except Exception as exc:
        _send(token, chat_id, f"Rollback error: {exc}")


def _cmd_fork(token: str, chat_id: str, args: str, *, model: str | None = None, purpose: str = "general") -> None:
    checkpoint_id = args.strip()
    if not checkpoint_id:
        _send(token, chat_id, "Usage: /fork &lt;checkpoint-id&gt;")
        return
    thread = get_thread_state(chat_id)
    if not thread:
        _send(token, chat_id, "No active session.")
        return
    try:
        import uuid
        new_thread_id = str(uuid.uuid4())
        fork_thread(thread["thread_id"], checkpoint_id, new_thread_id, model=model, purpose=purpose)
        from .storage import get_or_create_thread
        new_tg_thread = get_or_create_thread(f"{chat_id}_fork_{new_thread_id[:8]}")
        _send(token, chat_id,
            f"Forked from checkpoint <code>{checkpoint_id[:20]}…</code>\n"
            f"New fork thread ID: <code>{new_thread_id[:16]}…</code>\n"
            "Use /new to start fresh or continue in the current session.")
    except Exception as exc:
        _send(token, chat_id, f"Fork error: {exc}")


# ---------------------------------------------------------------------------
# Agent lifecycle helpers
# ---------------------------------------------------------------------------

def _promote_agent(agent_id: str) -> str:
    from .agent_catalog import promote_agent

    logger.info("Promoting staged agent %s into config/agents.", agent_id)
    result = promote_agent(agent_id, project_root=_PROJECT_ROOT)
    logger.info("Promotion result for %s: %s", agent_id, result)
    return result


def _delete_agent(agent_id: str) -> str:
    messages = []
    logger.info("Deleting agent %s from staging/config/database.", agent_id)

    # Remove from staging if present
    staging_dir = _PROJECT_ROOT / "staging" / "agents" / agent_id
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
        messages.append(f"Removed staging/agents/{agent_id}/")

    # Remove from config/agents if enabled
    enabled_json = _PROJECT_ROOT / "config" / "agents" / f"{agent_id}.json"
    if enabled_json.exists():
        enabled_json.unlink()
        messages.append(f"Removed config/agents/{agent_id}.json")

    # Remove from SQLite
    deleted = delete_staged_agent_record(agent_id)
    if deleted:
        messages.append("Removed database record.")

    if not messages:
        logger.warning("Agent %s was not found in staging, config/agents, or database.", agent_id)
        return f"Agent '{agent_id}' not found in staging, config/agents, or database."

    return f"Deleted {agent_id}:\n" + "\n".join(f"• {m}" for m in messages)


# ---------------------------------------------------------------------------
# Natural language → Factory Brain
# ---------------------------------------------------------------------------

def _handle_natural_language(token: str, chat_id: str, text: str, *, model: str | None = None, purpose: str = "general") -> None:
    thread_id = get_or_create_thread(chat_id)
    logger.info("Forwarding natural language message from chat_id=%s to Factory Brain.", chat_id)
    _send(token, chat_id, "Working on it...")
    try:
        response, interrupted = invoke_factory_brain(
            text,
            thread_id=thread_id,
            model=model,
            purpose=purpose,
        )
        set_thread_interrupted(chat_id, interrupted)
        _send(token, chat_id, response)
        logger.info("Factory Brain responded for chat_id=%s; interrupted=%s", chat_id, interrupted)
        if interrupted:
            _send(token, chat_id, "⏸ Factory Brain is waiting for your approval.\nSend /approve to continue or /reject to cancel.")
    except RuntimeError as exc:
        logger.exception("Factory Brain runtime error for chat_id=%s", chat_id)
        _send(token, chat_id, f"Factory Brain error: {exc}")
    except Exception as exc:
        logger.exception("Factory Brain unexpected error")
        _send(token, chat_id, f"Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# Update routing
# ---------------------------------------------------------------------------

def _handle_update(token: str, allowed_ids: set[str], update: dict, *, model: str | None = None, purpose: str = "general") -> None:
    message = update.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        logger.debug("Ignoring empty Telegram update.")
        return
    if chat_id not in allowed_ids:
        logger.warning("Rejected message from unauthorized chat_id=%s", chat_id)
        _send(token, chat_id, "Unauthorized.")
        return

    if text.startswith("/"):
        parts = text[1:].split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        logger.info("Received Telegram command /%s from chat_id=%s", cmd, chat_id)

        if cmd in ("start", "help"):
            _cmd_help(token, chat_id)
        elif cmd == "status":
            _cmd_status(token, chat_id)
        elif cmd == "staged":
            _cmd_staged(token, chat_id)
        elif cmd == "pending":
            _cmd_pending(token, chat_id)
        elif cmd == "approve":
            _cmd_approve(token, chat_id, args, model=model, purpose=purpose)
        elif cmd == "reject":
            _cmd_reject(token, chat_id, args, model=model, purpose=purpose)
        elif cmd == "new":
            _cmd_new(token, chat_id, model=model, purpose=purpose)
        elif cmd == "delete":
            _cmd_delete(token, chat_id, args)
        elif cmd == "checkpoints":
            _cmd_checkpoints(token, chat_id, model=model, purpose=purpose)
        elif cmd == "rollback":
            _cmd_rollback(token, chat_id, args, model=model, purpose=purpose)
        elif cmd == "fork":
            _cmd_fork(token, chat_id, args, model=model, purpose=purpose)
        else:
            logger.warning("Unknown Telegram command /%s from chat_id=%s", cmd, chat_id)
            _send(token, chat_id, f"Unknown command: /{cmd}\nSend /help for options.")
    else:
        _handle_natural_language(token, chat_id, text, model=model, purpose=purpose)


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def run_telegram_gateway(
    bot_name: str | None = None,
    *,
    log_level: str | int | None = None,
    default_model: str | None = None,
    purpose: str = "general",
) -> None:
    if log_level is not None or not logging.getLogger().handlers:
        configure_logging(log_level)
    _load_env()

    from .factory_settings import get_telegram_bot_config
    cfg = get_telegram_bot_config(bot_name)
    token = cfg["token"]
    allowed_ids = cfg["allowed_chat_ids"]

    logger.info("Telegram gateway starting. Bot: %s  Allowed chat IDs: %s", cfg["name"], allowed_ids)
    logger.info("Agent Factory Telegram gateway running [%s]. Press Ctrl+C to stop.", cfg["name"])
    logger.info("Telegram AI purpose=%s default_model=%s", purpose, default_model or "<config default>")

    offset = 0
    while True:
        try:
            updates = _get_updates(token, offset)
            logger.debug("Received %s Telegram updates.", len(updates))
            for update in updates:
                offset = max(offset, update["update_id"] + 1)
                try:
                    _handle_update(token, allowed_ids, update, model=default_model, purpose=purpose)
                except Exception:
                    logger.exception("Error handling update %s", update.get("update_id"))
        except KeyboardInterrupt:
            logger.info("Telegram gateway stopped.")
            break
        except Exception:
            logger.exception("Polling error, retrying in %ds", _RETRY_DELAY)
            time.sleep(_RETRY_DELAY)
