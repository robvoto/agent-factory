"""Persistent SQLite-backed knowledge store for shared agent knowledge.

All agents read from and write to this store. It lives outside any single
conversation thread — knowledge survives /new, restarts, and agent changes.

Namespaces:
    ("shared", "docs")         — indexed local documentation
    ("shared", "trusted")      — ingested trusted online sources
    ("factory", "learnings")   — Factory Brain learnings across sessions
    ("agent", <id>, ...)       — per-agent learnings
    ("user", <id>, ...)        — per-user preferences
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable

from langgraph.store.base import BaseStore, GetOp, Item, ListNamespacesOp, Op, PutOp, Result, SearchItem, SearchOp

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[2]
_DEFAULT_STORE_PATH = _PROJECT_ROOT / "data" / "knowledge_store.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    namespace TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (namespace, key)
);
CREATE INDEX IF NOT EXISTS idx_namespace ON knowledge_items (namespace);
"""


@contextmanager
def _connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ns_key(namespace: tuple[str, ...]) -> str:
    return "/".join(namespace)


def _row_to_item(row: sqlite3.Row) -> Item:
    ns = tuple(row["namespace"].split("/"))
    return Item(
        namespace=ns,
        key=row["key"],
        value=json.loads(row["value"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class SqliteStore(BaseStore):
    """Persistent BaseStore backed by SQLite with keyword search."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DEFAULT_STORE_PATH

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        results: list[Result] = []
        with _connect(self._db_path) as conn:
            for op in ops:
                if isinstance(op, PutOp):
                    results.append(self._put(conn, op))
                elif isinstance(op, GetOp):
                    results.append(self._get(conn, op))
                elif isinstance(op, SearchOp):
                    results.append(self._search(conn, op))
                elif isinstance(op, ListNamespacesOp):
                    results.append(self._list_namespaces(conn, op))
                else:
                    results.append(None)
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return self.batch(ops)

    def _put(self, conn: sqlite3.Connection, op: PutOp) -> None:
        ns = _ns_key(op.namespace)
        now = datetime.now(timezone.utc).isoformat()
        if op.value is None:
            conn.execute("DELETE FROM knowledge_items WHERE namespace=? AND key=?", (ns, op.key))
        else:
            conn.execute(
                """INSERT INTO knowledge_items (namespace, key, value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(namespace, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (ns, op.key, json.dumps(op.value), now, now),
            )
        return None

    def _get(self, conn: sqlite3.Connection, op: GetOp) -> Item | None:
        ns = _ns_key(op.namespace)
        row = conn.execute(
            "SELECT * FROM knowledge_items WHERE namespace=? AND key=?", (ns, op.key)
        ).fetchone()
        return _row_to_item(row) if row else None

    def _search(self, conn: sqlite3.Connection, op: SearchOp) -> list[SearchItem]:
        ns_prefix = _ns_key(op.namespace_prefix)
        rows = conn.execute(
            "SELECT * FROM knowledge_items WHERE namespace=? OR namespace LIKE ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (ns_prefix, f"{ns_prefix}/%", op.limit, op.offset),
        ).fetchall()

        items = [_row_to_item(r) for r in rows]

        if op.query:
            q = op.query.lower()
            items = [
                i for i in items
                if q in json.dumps(i.value).lower()
            ]

        return [
            SearchItem(
                namespace=i.namespace,
                key=i.key,
                value=i.value,
                created_at=i.created_at,
                updated_at=i.updated_at,
                score=1.0,
            )
            for i in items
        ]

    def _list_namespaces(self, conn: sqlite3.Connection, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        rows = conn.execute("SELECT DISTINCT namespace FROM knowledge_items").fetchall()
        return [tuple(r["namespace"].split("/")) for r in rows]


_store: SqliteStore | None = None


def get_knowledge_store(db_path: Path | None = None) -> SqliteStore:
    global _store
    if _store is None:
        _store = SqliteStore(db_path)
        logger.info("Knowledge store initialised at %s", _store._db_path)
    return _store
