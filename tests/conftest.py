"""Shared pytest fixtures — enforces test isolation for all persistent state."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_agent_db(tmp_path, monkeypatch):
    """Redirect storage._DEFAULT_DB_PATH to a temp file for every test."""
    import agent_factory.storage as storage_mod

    monkeypatch.setattr(storage_mod, "_DEFAULT_DB_PATH", tmp_path / "agent_factory.sqlite3")


@pytest.fixture(autouse=True)
def _isolate_checkpoint_db(tmp_path, monkeypatch):
    """Redirect factory_brain._CHECKPOINT_DB to a temp file and clear cached connection."""
    import agent_factory.factory_brain as brain_mod

    monkeypatch.setattr(brain_mod, "_CHECKPOINT_DB", tmp_path / "checkpoints.sqlite3")
    monkeypatch.setattr(brain_mod, "_checkpointer_conn", None)
    monkeypatch.setattr(brain_mod, "_agents_by_model", {})
