"""SQLite persistence for the Agent Factory Platform.

Tables:
  staged_agents   — draft packages waiting for approval
  approvals       — pending/decided approval records
  factory_threads — Telegram chat → LangGraph thread mapping
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

_PROJECT_ROOT = Path(__file__).parents[2]
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "agent_factory.sqlite3"
logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS staged_agents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL UNIQUE,
    path        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'staged',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_type   TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    summary         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    requested_at    TEXT NOT NULL,
    decided_at      TEXT,
    decision_reason TEXT
);

CREATE TABLE IF NOT EXISTS factory_threads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL UNIQUE,
    thread_id       TEXT NOT NULL,
    is_interrupted  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
        yield conn
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental schema changes that ALTER existing tables."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(factory_threads)").fetchall()
    }
    if "is_interrupted" not in existing:
        conn.execute(
            "ALTER TABLE factory_threads ADD COLUMN is_interrupted INTEGER NOT NULL DEFAULT 0"
        )


# ---------------------------------------------------------------------------
# staged_agents
# ---------------------------------------------------------------------------

def record_staged_agent(
    agent_id: str,
    package_path: Path,
    *,
    db_path: Path | None = None,
) -> int:
    """Insert a new staged_agents row. Returns the new row id."""
    now = _now_iso()
    logger.info("Recording staged agent %s at %s.", agent_id, package_path)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO staged_agents (agent_id, path, status, created_at, updated_at)"
            " VALUES (?, ?, 'staged', ?, ?)",
            (agent_id, str(package_path), now, now),
        )
        conn.commit()
        return cur.lastrowid


def list_staged_agent_records(*, db_path: Path | None = None) -> list[dict]:
    """Return all rows from staged_agents ordered by creation time."""
    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        logger.debug("No staged-agent database exists yet at %s.", resolved)
        return []
    logger.debug("Listing staged agent records from %s.", resolved)
    with _connect(resolved) as conn:
        rows = conn.execute(
            "SELECT agent_id, path, status, created_at, updated_at"
            " FROM staged_agents ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get_staged_agent_record(agent_id: str, *, db_path: Path | None = None) -> dict | None:
    """Return the staged_agents row for agent_id, or None."""
    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        logger.debug("No staged-agent database exists yet at %s.", resolved)
        return None
    logger.debug("Loading staged agent record for %s from %s.", agent_id, resolved)
    with _connect(resolved) as conn:
        row = conn.execute(
            "SELECT agent_id, path, status, created_at, updated_at"
            " FROM staged_agents WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
    return dict(row) if row else None


def update_staged_agent_status(
    agent_id: str,
    new_status: str,
    *,
    db_path: Path | None = None,
) -> None:
    """Update the status field for a staged agent record."""
    now = _now_iso()
    logger.info("Updating staged agent %s status -> %s.", agent_id, new_status)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        conn.execute(
            "UPDATE staged_agents SET status = ?, updated_at = ? WHERE agent_id = ?",
            (new_status, now, agent_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# approvals
# ---------------------------------------------------------------------------

def create_approval(
    approval_type: str,
    target_id: str,
    summary: str,
    *,
    db_path: Path | None = None,
) -> int:
    """Insert a pending approval record. Returns the new approval id."""
    now = _now_iso()
    logger.info("Recording approval request for %s (%s).", target_id, approval_type)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO approvals (approval_type, target_id, summary, status, requested_at)"
            " VALUES (?, ?, ?, 'pending', ?)",
            (approval_type, target_id, summary, now),
        )
        conn.commit()
        return cur.lastrowid


def get_approval(approval_id: int, *, db_path: Path | None = None) -> dict | None:
    """Return one approval row by id, or None."""
    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        logger.debug("No approvals database exists yet at %s.", resolved)
        return None
    logger.debug("Loading approval %s from %s.", approval_id, resolved)
    with _connect(resolved) as conn:
        row = conn.execute(
            "SELECT id, approval_type, target_id, summary, status, requested_at,"
            " decided_at, decision_reason FROM approvals WHERE id = ?",
            (approval_id,),
        ).fetchone()
    return dict(row) if row else None


def list_pending_approvals(*, db_path: Path | None = None) -> list[dict]:
    """Return all pending approval rows."""
    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        logger.debug("No approvals database exists yet at %s.", resolved)
        return []
    logger.debug("Listing pending approvals from %s.", resolved)
    with _connect(resolved) as conn:
        rows = conn.execute(
            "SELECT id, approval_type, target_id, summary, requested_at"
            " FROM approvals WHERE status = 'pending' ORDER BY requested_at"
        ).fetchall()
    return [dict(r) for r in rows]


def decide_approval(
    approval_id: int,
    decision: str,
    reason: str = "",
    *,
    db_path: Path | None = None,
) -> None:
    """Set an approval to 'approved' or 'rejected' with an optional reason."""
    now = _now_iso()
    logger.info("Decision recorded for approval %s: %s.", approval_id, decision)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        conn.execute(
            "UPDATE approvals SET status = ?, decided_at = ?, decision_reason = ?"
            " WHERE id = ?",
            (decision, now, reason, approval_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# factory_threads  (Telegram chat → LangGraph thread mapping)
# ---------------------------------------------------------------------------

def get_or_create_thread(chat_id: str, *, db_path: Path | None = None) -> str:
    """Return the LangGraph thread_id for a Telegram chat, creating one if needed."""
    import uuid

    resolved = db_path or _DEFAULT_DB_PATH
    now = _now_iso()
    logger.debug("Loading or creating Factory Brain thread for chat_id=%s.", chat_id)
    with _connect(resolved) as conn:
        row = conn.execute(
            "SELECT thread_id FROM factory_threads WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE factory_threads SET updated_at = ? WHERE chat_id = ?",
                (now, chat_id),
            )
            conn.commit()
            logger.debug("Reusing existing thread %s for chat_id=%s.", row["thread_id"], chat_id)
            return row["thread_id"]
        thread_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO factory_threads (chat_id, thread_id, is_interrupted, created_at, updated_at)"
            " VALUES (?, ?, 0, ?, ?)",
            (chat_id, thread_id, now, now),
        )
        conn.commit()
        logger.info("Created Factory Brain thread %s for chat_id=%s.", thread_id, chat_id)
        return thread_id


def reset_thread(chat_id: str, *, db_path: Path | None = None) -> str:
    """Start a fresh Factory Brain session for a chat and return the new thread_id."""
    import uuid

    resolved = db_path or _DEFAULT_DB_PATH
    now = _now_iso()
    thread_id = str(uuid.uuid4())
    logger.info("Resetting Factory Brain thread for chat_id=%s to %s.", chat_id, thread_id)
    with _connect(resolved) as conn:
        conn.execute("DELETE FROM factory_threads WHERE chat_id = ?", (chat_id,))
        conn.execute(
            "INSERT INTO factory_threads (chat_id, thread_id, is_interrupted, created_at, updated_at)"
            " VALUES (?, ?, 0, ?, ?)",
            (chat_id, thread_id, now, now),
        )
        conn.commit()
    return thread_id


def set_thread_interrupted(chat_id: str, interrupted: bool, *, db_path: Path | None = None) -> None:
    """Mark a Telegram thread as interrupted (waiting for human approval) or clear it."""
    now = _now_iso()
    logger.info("Setting chat_id=%s interrupted=%s.", chat_id, interrupted)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        conn.execute(
            "UPDATE factory_threads SET is_interrupted = ?, updated_at = ? WHERE chat_id = ?",
            (1 if interrupted else 0, now, chat_id),
        )
        conn.commit()


def get_thread_state(chat_id: str, *, db_path: Path | None = None) -> dict | None:
    """Return thread_id and is_interrupted for a chat, or None if no thread exists."""
    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        logger.debug("No Factory Brain thread database exists yet at %s.", resolved)
        return None
    logger.debug("Loading thread state for chat_id=%s from %s.", chat_id, resolved)
    with _connect(resolved) as conn:
        row = conn.execute(
            "SELECT thread_id, is_interrupted FROM factory_threads WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# staged_agents — delete
# ---------------------------------------------------------------------------

def delete_staged_agent_record(agent_id: str, *, db_path: Path | None = None) -> bool:
    """Remove a staged_agents row. Returns True if a row was deleted."""
    logger.info("Deleting staged agent record for %s.", agent_id)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute("DELETE FROM staged_agents WHERE agent_id = ?", (agent_id,))
        conn.commit()
        return cur.rowcount > 0
