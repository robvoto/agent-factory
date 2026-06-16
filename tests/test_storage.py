"""Tests for SQLite storage layer."""

import json
import tempfile
from pathlib import Path

import pytest

from agent_factory.storage import (
    get_staged_agent_record,
    get_or_create_thread,
    get_thread_state,
    list_staged_agent_records,
    record_staged_agent,
    reset_thread,
    set_thread_interrupted,
    update_staged_agent_status,
)


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.sqlite3"


def test_record_staged_agent_returns_row_id(tmp_db, tmp_path):
    pkg = tmp_path / "my-agent"
    row_id = record_staged_agent("my-agent", pkg, db_path=tmp_db)
    assert row_id == 1


def test_list_staged_agent_records_empty_before_insert(tmp_db):
    # DB doesn't exist yet — should return []
    assert list_staged_agent_records(db_path=tmp_db) == []


def test_list_staged_agent_records_after_insert(tmp_db, tmp_path):
    record_staged_agent("alpha-agent", tmp_path / "alpha-agent", db_path=tmp_db)
    record_staged_agent("beta-agent", tmp_path / "beta-agent", db_path=tmp_db)
    rows = list_staged_agent_records(db_path=tmp_db)
    assert len(rows) == 2
    assert rows[0]["agent_id"] == "alpha-agent"
    assert rows[1]["agent_id"] == "beta-agent"
    assert rows[0]["status"] == "staged"


def test_get_staged_agent_record_found(tmp_db, tmp_path):
    record_staged_agent("my-agent", tmp_path / "my-agent", db_path=tmp_db)
    row = get_staged_agent_record("my-agent", db_path=tmp_db)
    assert row is not None
    assert row["agent_id"] == "my-agent"
    assert row["status"] == "staged"
    assert "created_at" in row
    assert "updated_at" in row


def test_get_staged_agent_record_not_found(tmp_db):
    row = get_staged_agent_record("nonexistent", db_path=tmp_db)
    assert row is None


def test_update_staged_agent_status(tmp_db, tmp_path):
    record_staged_agent("my-agent", tmp_path / "my-agent", db_path=tmp_db)
    update_staged_agent_status("my-agent", "approved", db_path=tmp_db)
    row = get_staged_agent_record("my-agent", db_path=tmp_db)
    assert row["status"] == "approved"


def test_duplicate_agent_id_raises(tmp_db, tmp_path):
    record_staged_agent("my-agent", tmp_path / "my-agent", db_path=tmp_db)
    with pytest.raises(Exception):
        record_staged_agent("my-agent", tmp_path / "my-agent-2", db_path=tmp_db)


def test_reset_thread_creates_fresh_session(tmp_db):
    original_thread_id = get_or_create_thread("chat-1", db_path=tmp_db)
    set_thread_interrupted("chat-1", True, db_path=tmp_db)

    new_thread_id = reset_thread("chat-1", db_path=tmp_db)
    state = get_thread_state("chat-1", db_path=tmp_db)

    assert new_thread_id != original_thread_id
    assert state is not None
    assert state["thread_id"] == new_thread_id
    assert state["is_interrupted"] == 0
