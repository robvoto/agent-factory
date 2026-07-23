"""Setup (AF-026) and doctor/health-check (AF-028) commands for Agent Factory."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[2]
_DATA_DIR = _PROJECT_ROOT / "data"
_CONFIG_DIR = _PROJECT_ROOT / "config"


class CheckResult(NamedTuple):
    ok: bool
    label: str
    detail: str


# ---------------------------------------------------------------------------
# Setup (AF-026)
# ---------------------------------------------------------------------------

def run_setup() -> int:
    """Create required dirs, copy missing example settings, init DB schemas.

    Idempotent: never overwrites existing local settings without approval.
    Returns 0 on success, 1 if any required step fails.
    """
    ok = True

    print("=== Agent Factory Setup ===\n")

    # 1. Required directories
    required_dirs = [
        _DATA_DIR,
        _PROJECT_ROOT / "staging" / "agents",
        _PROJECT_ROOT / "logs",
    ]
    for d in required_dirs:
        if d.exists():
            print(f"  [ok] {d.relative_to(_PROJECT_ROOT)} exists")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  [created] {d.relative_to(_PROJECT_ROOT)}")

    # 2. Local settings bootstrap (never overwrite)
    example = _DATA_DIR / "settings.local.example.json"
    local = _DATA_DIR / "settings.local.json"

    if not example.exists():
        _write_settings_example(example)
        print(f"  [created] {example.relative_to(_PROJECT_ROOT)}")
    else:
        print(f"  [ok] {example.relative_to(_PROJECT_ROOT)} exists")

    if local.exists():
        print(f"  [ok] {local.relative_to(_PROJECT_ROOT)} exists (not overwritten)")
    else:
        shutil.copy(example, local)
        print(f"  [copied] {local.relative_to(_PROJECT_ROOT)} (from example — fill in real values)")

    # 3. Init SQLite schemas
    db_path = _DATA_DIR / "agent_factory.sqlite3"
    try:
        from .storage import _connect, _SCHEMA  # type: ignore[attr-defined]
        with _connect(db_path) as conn:
            conn.executescript(_SCHEMA)
        print(f"  [ok] {db_path.relative_to(_PROJECT_ROOT)} schema ready")
    except Exception as exc:
        print(f"  [FAIL] could not init agent_factory.sqlite3: {exc}")
        ok = False

    print()
    print("Next steps:")
    print("  1. Edit data/settings.local.json — add real Telegram token and chat IDs")
    print("  2. Copy model API keys into .env (gitignored)")
    print("  3. Run: uv run pytest")
    print("  4. Run: uv run agent-factory doctor")

    return 0 if ok else 1


def _write_settings_example(path: Path) -> None:
    example = {
        "telegram_allowed_chat_ids": ["YOUR_CHAT_ID"],
        "_note": "Copy this file to settings.local.json and fill in real values. Never commit real values.",
    }
    path.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Doctor / health-check (AF-028)
# ---------------------------------------------------------------------------

def run_doctor() -> int:
    """Report data, settings, SQLite, and git health.

    Returns 0 if all checks pass, 1 if any check fails.
    """
    checks: list[CheckResult] = []

    checks += _check_directories()
    checks += _check_settings()
    checks += _check_sqlite()
    checks += _check_git_hygiene()
    checks += _check_factory_brain_dependencies()
    checks += _check_factory_manifest()

    _print_report(checks)
    failures = [c for c in checks if not c.ok]
    return 0 if not failures else 1


def _check_directories() -> list[CheckResult]:
    results = []
    for d in [_DATA_DIR, _PROJECT_ROOT / "staging" / "agents", _PROJECT_ROOT / "config" / "agents"]:
        rel = str(d.relative_to(_PROJECT_ROOT))
        results.append(CheckResult(ok=d.exists(), label=f"dir: {rel}", detail="" if d.exists() else "missing — run: uv run agent-factory setup"))
    return results


def _check_settings() -> list[CheckResult]:
    results = []

    example = _DATA_DIR / "settings.local.example.json"
    local = _DATA_DIR / "settings.local.json"

    results.append(CheckResult(
        ok=example.exists(),
        label="settings.local.example.json exists",
        detail="" if example.exists() else "missing — run: uv run agent-factory setup",
    ))
    results.append(CheckResult(
        ok=local.exists(),
        label="settings.local.json exists",
        detail="" if local.exists() else "missing — run: uv run agent-factory setup",
    ))

    # Verify local settings is gitignored
    if local.exists():
        ignored = _is_gitignored(local)
        results.append(CheckResult(
            ok=ignored,
            label="settings.local.json is gitignored",
            detail="" if ignored else "WARNING: local settings is tracked by Git — add to .gitignore",
        ))

    # Check that example doesn't contain real token values
    if example.exists():
        content = example.read_text(encoding="utf-8").lower()
        suspicious = any(kw in content for kw in ["bot_token", "api_key", "secret", "password"])
        results.append(CheckResult(
            ok=not suspicious,
            label="settings.local.example.json has no real secrets",
            detail="" if not suspicious else "example file may contain real credentials — review it",
        ))

    return results


def _check_sqlite() -> list[CheckResult]:
    results = []
    db_path = _DATA_DIR / "agent_factory.sqlite3"
    if not db_path.exists():
        results.append(CheckResult(ok=False, label="agent_factory.sqlite3 exists", detail="missing — run: uv run agent-factory setup"))
        return results

    results.append(CheckResult(ok=True, label="agent_factory.sqlite3 exists", detail=""))

    try:
        conn = sqlite3.connect(db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        for expected in ["staged_agents", "approvals", "factory_threads"]:
            results.append(CheckResult(
                ok=expected in tables,
                label=f"sqlite table: {expected}",
                detail="" if expected in tables else f"table missing — run: uv run agent-factory setup",
            ))
    except Exception as exc:
        results.append(CheckResult(ok=False, label="agent_factory.sqlite3 readable", detail=str(exc)))

    return results


def _check_git_hygiene() -> list[CheckResult]:
    results = []
    dangerous = [
        _DATA_DIR / "agent_factory.sqlite3",
        _DATA_DIR / "factory_checkpoints.sqlite3",
        _DATA_DIR / "knowledge_store.sqlite3",
        _DATA_DIR / "llm_usage.json",
        _DATA_DIR / "settings.local.json",
        _PROJECT_ROOT / ".env",
    ]
    for f in dangerous:
        if not f.exists():
            continue
        tracked = _is_git_tracked(f)
        label = f"git: {f.relative_to(_PROJECT_ROOT)} not tracked"
        results.append(CheckResult(
            ok=not tracked,
            label=label,
            detail="" if not tracked else "DANGER: runtime/secrets file is tracked — remove from git",
        ))

    return results


def _check_factory_brain_dependencies() -> list[CheckResult]:
    try:
        from .factory_brain import check_factory_brain_dependencies

        check_factory_brain_dependencies()
        return [
            CheckResult(
                ok=True,
                label="Factory Brain runtime dependencies",
                detail="deepagents and SQLite checkpoint support are available",
            )
        ]
    except Exception as exc:
        return [
            CheckResult(
                ok=False,
                label="Factory Brain runtime dependencies",
                detail=str(exc),
            )
        ]


def _check_factory_manifest() -> list[CheckResult]:
    results = []
    try:
        from .agent_manifest import build_factory_manifest
        m = build_factory_manifest(include_live=True)
        enabled = m.get("live_registry", {}).get("enabled_count", -1)
        results.append(CheckResult(ok=True, label="manifest builds OK", detail=f"{enabled} enabled agent(s)"))
    except Exception as exc:
        results.append(CheckResult(ok=False, label="manifest builds OK", detail=str(exc)))
    return results


def _is_gitignored(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=_PROJECT_ROOT,
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_git_tracked(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            cwd=_PROJECT_ROOT,
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False


def _print_report(checks: list[CheckResult]) -> None:
    total = len(checks)
    failures = [c for c in checks if not c.ok]
    print("=== Agent Factory Doctor ===\n")
    for c in checks:
        icon = "[ok]  " if c.ok else "[FAIL]"
        line = f"  {icon} {c.label}"
        if c.detail:
            line += f"\n         {c.detail}"
        print(line)
    print()
    if failures:
        print(f"  {len(failures)}/{total} checks failed.")
    else:
        print(f"  All {total} checks passed.")
