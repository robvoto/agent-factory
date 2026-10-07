"""SQLite persistence for the Agent Factory Platform.

Tables:
  staged_agents   — draft packages waiting for approval
  approvals       — pending/decided approval records
  factory_threads — Telegram chat → LangGraph thread mapping
  build_tasks     — Factory implementation handoffs keyed by thread
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[2]
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "agent_factory.sqlite3"
logger = logging.getLogger(__name__)
BUILD_TASK_STATUSES = frozenset({"prepared", "approved", "rejected", "stale", "superseded"})

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

CREATE TABLE IF NOT EXISTS build_tasks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id           TEXT NOT NULL,
    artifact_reference  TEXT NOT NULL,
    correlation_id      TEXT NOT NULL,
    agent_id            TEXT NOT NULL,
    agent_version       TEXT NOT NULL,
    manifest_sha256     TEXT NOT NULL,
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    decision_reason     TEXT,
    CHECK (status IN ('prepared', 'approved', 'rejected', 'stale', 'superseded'))
);

CREATE INDEX IF NOT EXISTS idx_build_tasks_thread_id ON build_tasks(thread_id);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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

    unique_artifact_reference = False
    for index in conn.execute("PRAGMA index_list(build_tasks)").fetchall():
        if not index[2]:
            continue
        columns = conn.execute(f"PRAGMA index_info({index[1]!r})").fetchall()
        if [column[2] for column in columns] == ["artifact_reference"]:
            unique_artifact_reference = True
            break
    if unique_artifact_reference:
        # AF-048 originally made the stable artifact path unique. Preserve every
        # old row while replacing only that schema constraint.
        conn.execute("DROP INDEX IF EXISTS idx_build_tasks_thread_id")
        conn.execute("ALTER TABLE build_tasks RENAME TO build_tasks_legacy")
        conn.execute(
            """CREATE TABLE build_tasks (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id           TEXT NOT NULL,
                artifact_reference  TEXT NOT NULL,
                correlation_id      TEXT NOT NULL,
                agent_id            TEXT NOT NULL,
                agent_version       TEXT NOT NULL,
                manifest_sha256     TEXT NOT NULL,
                status              TEXT NOT NULL,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL,
                decision_reason     TEXT,
                CHECK (status IN ('prepared', 'approved', 'rejected', 'stale', 'superseded'))
            )"""
        )
        conn.execute(
            "INSERT INTO build_tasks (id, thread_id, artifact_reference, correlation_id, agent_id,"
            " agent_version, manifest_sha256, status, created_at, updated_at, decision_reason)"
            " SELECT id, thread_id, artifact_reference, correlation_id, agent_id, agent_version,"
            " manifest_sha256, status, created_at, updated_at, decision_reason"
            " FROM build_tasks_legacy"
        )
        conn.execute("DROP TABLE build_tasks_legacy")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_build_tasks_thread_id ON build_tasks(thread_id)")


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


def claim_approved_approval(
    approval_id: int,
    approval_type: str,
    *,
    db_path: Path | None = None,
) -> bool:
    """Atomically claim one approved approval record for a single execution."""
    logger.info("Claiming approved %s approval %s.", approval_type, approval_id)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE approvals SET status = 'claimed'"
            " WHERE id = ? AND approval_type = ? AND status = 'approved'",
            (approval_id, approval_type),
        )
        conn.commit()
        return cur.rowcount == 1


def finalise_claimed_approval(
    approval_id: int,
    status: str,
    reason: str,
    *,
    db_path: Path | None = None,
) -> None:
    """Record the terminal outcome of a previously claimed approval."""
    logger.info("Finalising claimed approval %s as %s.", approval_id, status)
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        conn.execute(
            "UPDATE approvals SET status = ?, decision_reason = ?"
            " WHERE id = ? AND status = 'claimed'",
            (status, reason, approval_id),
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
# build_tasks (Factory implementation handoffs)
# ---------------------------------------------------------------------------

def record_build_task(
    *,
    thread_id: str,
    artifact_reference: str,
    correlation_id: str,
    agent_id: str,
    agent_version: str,
    manifest_sha256: str,
    status: str = "prepared",
    db_path: Path | None = None,
) -> int:
    """Record one prepared build task without creating a second approval record."""

    if status not in BUILD_TASK_STATUSES:
        raise ValueError(f"Unknown build-task status: {status!r}")
    now = _now_iso()
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO build_tasks (thread_id, artifact_reference, correlation_id, agent_id,"
            " agent_version, manifest_sha256, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                artifact_reference,
                correlation_id,
                agent_id,
                agent_version,
                manifest_sha256,
                status,
                now,
                now,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_build_task(
    artifact_reference: str,
    *,
    correlation_id: str | None = None,
    thread_id: str | None = None,
    db_path: Path | None = None,
) -> dict | None:
    """Return an exact task, or fail closed when a path-only lookup is ambiguous."""

    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        return None
    clauses = ["artifact_reference = ?"]
    params: list[str] = [artifact_reference]
    if correlation_id is not None:
        clauses.append("correlation_id = ?")
        params.append(correlation_id)
    if thread_id is not None:
        clauses.append("thread_id = ?")
        params.append(thread_id)
    with _connect(resolved) as conn:
        row = conn.execute(
            "SELECT id, thread_id, artifact_reference, correlation_id, agent_id, agent_version,"
            " manifest_sha256, status, created_at, updated_at, decision_reason"
            " FROM build_tasks WHERE " + " AND ".join(clauses)
            + " ORDER BY id",
            params,
        ).fetchall()
    if len(row) > 1:
        raise ValueError(
            "Build-task artifact reference is ambiguous; correlation_id and thread_id are required"
        )
    return dict(row[0]) if row else None


def list_build_tasks_for_reference(
    artifact_reference: str,
    *,
    db_path: Path | None = None,
) -> list[dict]:
    """Return all historical rows for one stable artifact path."""

    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        return []
    with _connect(resolved) as conn:
        rows = conn.execute(
            "SELECT id, thread_id, artifact_reference, correlation_id, agent_id, agent_version,"
            " manifest_sha256, status, created_at, updated_at, decision_reason"
            " FROM build_tasks WHERE artifact_reference = ? ORDER BY id",
            (artifact_reference,),
        ).fetchall()
    return [dict(item) for item in rows]


def list_build_tasks_for_thread(thread_id: str, *, db_path: Path | None = None) -> list[dict]:
    """Return build tasks for one Factory thread without a repository scan."""

    resolved = db_path or _DEFAULT_DB_PATH
    if not resolved.exists():
        return []
    with _connect(resolved) as conn:
        rows = conn.execute(
            "SELECT id, thread_id, artifact_reference, correlation_id, agent_id, agent_version,"
            " manifest_sha256, status, created_at, updated_at, decision_reason"
            " FROM build_tasks WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_build_task_approved(
    *,
    thread_id: str,
    artifact_reference: str,
    correlation_id: str,
    db_path: Path | None = None,
) -> bool:
    """Atomically mark the exact prepared task approved by HITL middleware."""

    now = _now_iso()
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE build_tasks SET status = 'approved', updated_at = ?"
            " WHERE thread_id = ? AND artifact_reference = ? AND correlation_id = ?"
            " AND status = 'prepared'",
            (now, thread_id, artifact_reference, correlation_id),
        )
        conn.commit()
        return cur.rowcount == 1


def mark_build_task_status(
    artifact_reference: str,
    status: str,
    reason: str = "",
    *,
    correlation_id: str,
    thread_id: str,
    db_path: Path | None = None,
) -> bool:
    """Record a fail-closed terminal or superseding build-task state."""

    if status not in BUILD_TASK_STATUSES:
        raise ValueError(f"Unknown build-task status: {status!r}")
    now = _now_iso()
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE build_tasks SET status = ?, updated_at = ?, decision_reason = ?"
            " WHERE artifact_reference = ? AND correlation_id = ? AND thread_id = ?"
            " AND status NOT IN ('rejected', 'stale', 'superseded')",
            (status, now, reason, artifact_reference, correlation_id, thread_id),
        )
        conn.commit()
        return cur.rowcount == 1


def reject_build_tasks_for_thread(
    thread_id: str,
    reason: str = "Rejected by user",
    *,
    db_path: Path | None = None,
) -> int:
    """Leave every unapproved task in a thread non-dispatchable."""

    now = _now_iso()
    with _connect(db_path or _DEFAULT_DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE build_tasks SET status = 'rejected', updated_at = ?, decision_reason = ?"
            " WHERE thread_id = ? AND status = 'prepared'",
            (now, reason, thread_id),
        )
        conn.commit()
        return cur.rowcount


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
