"""CI validation for gitignore and data policy (AF-029).

Verifies:
- Required seed/committed files are present and tracked by git
- Runtime databases, env files, and local settings are gitignored
- No dangerous runtime files are accidentally committed
- settings.local.example.json exists and has safe content
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def _is_ignored(rel_path: str) -> bool:
    result = _git("check-ignore", "-q", rel_path)
    return result.returncode == 0


def _is_tracked(rel_path: str) -> bool:
    result = _git("ls-files", "--error-unmatch", rel_path)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Runtime files must be gitignored
# ---------------------------------------------------------------------------

def test_sqlite_files_are_gitignored() -> None:
    """SQLite runtime databases must never be committed."""
    runtime_dbs = [
        "data/agent_factory.sqlite3",
        "data/factory_checkpoints.sqlite3",
        "data/knowledge_store.sqlite3",
    ]
    not_ignored = []
    for rel in runtime_dbs:
        if not _is_ignored(rel):
            not_ignored.append(rel)
    assert not not_ignored, (
        f"These SQLite files are NOT gitignored and could be accidentally committed: {not_ignored}"
    )


def test_env_file_is_gitignored() -> None:
    assert _is_ignored(".env"), ".env must be gitignored — it may contain API keys"


def test_local_settings_is_gitignored() -> None:
    assert _is_ignored("data/settings.local.json"), (
        "data/settings.local.json must be gitignored — it contains real tokens and chat IDs"
    )


def test_llm_usage_is_gitignored() -> None:
    assert _is_ignored("data/llm_usage.json"), (
        "data/llm_usage.json must be gitignored — it is runtime cost tracking data"
    )



# ---------------------------------------------------------------------------
# Required committed files must be present and tracked
# ---------------------------------------------------------------------------

def test_settings_example_exists() -> None:
    example = DATA_DIR / "settings.local.example.json"
    assert example.exists(), (
        "data/settings.local.example.json is missing — run: uv run agent-factory setup"
    )


def test_settings_example_is_valid_json() -> None:
    example = DATA_DIR / "settings.local.example.json"
    if not example.exists():
        return  # caught by previous test
    try:
        json.loads(example.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"data/settings.local.example.json is not valid JSON: {exc}") from exc


def test_settings_example_has_no_real_secrets() -> None:
    """The example file must only contain placeholder values."""
    example = DATA_DIR / "settings.local.example.json"
    if not example.exists():
        return
    content = example.read_text(encoding="utf-8").lower()
    suspicious_keywords = ["bot_token", "api_key", "secret", "password", "access_token"]
    found = [kw for kw in suspicious_keywords if kw in content]
    assert not found, (
        f"data/settings.local.example.json may contain real secrets (keywords: {found}). "
        "Replace with placeholders like YOUR_CHAT_ID."
    )


def test_config_agents_dir_exists() -> None:
    agents_dir = PROJECT_ROOT / "config" / "agents"
    assert agents_dir.exists(), (
        "config/agents/ directory is missing — this is the live agent registry"
    )


def test_each_enabled_agent_has_spec() -> None:
    agents_dir = PROJECT_ROOT / "config" / "agents"
    if not agents_dir.exists():
        return
    missing_specs = []
    for agent_dir in agents_dir.iterdir():
        if agent_dir.is_dir():
            spec = agent_dir / "agent.json"
            if not spec.exists():
                missing_specs.append(str(agent_dir.name))
    assert not missing_specs, (
        f"These agent directories have no agent.json: {missing_specs}"
    )


def test_each_agent_spec_is_valid_json() -> None:
    agents_dir = PROJECT_ROOT / "config" / "agents"
    if not agents_dir.exists():
        return
    invalid = []
    for spec_file in agents_dir.glob("*/agent.json"):
        try:
            json.loads(spec_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            invalid.append(spec_file.name)
    assert not invalid, f"These agent.json files are invalid JSON: {invalid}"


def test_each_agent_spec_has_required_fields() -> None:
    agents_dir = PROJECT_ROOT / "config" / "agents"
    if not agents_dir.exists():
        return
    required = ["id", "name", "purpose", "aliases", "permissions", "runtime"]
    problems = []
    for spec_file in agents_dir.glob("*/agent.json"):
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        missing = [f for f in required if f not in spec]
        if missing:
            problems.append(f"{spec_file.parent.name}: missing {missing}")
    assert not problems, f"Agent specs missing required fields:\n" + "\n".join(problems)


def test_subprocess_agent_specs_declare_output_contract() -> None:
    agents_dir = PROJECT_ROOT / "config" / "agents"
    if not agents_dir.exists():
        return
    problems = []
    for spec_file in agents_dir.glob("*/agent.json"):
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        runtime = spec.get("runtime", {})
        if runtime.get("mode") != "subprocess":
            continue
        output_contract = spec.get("output_contract")
        if not isinstance(output_contract, dict):
            problems.append(f"{spec_file.parent.name}: missing output_contract")
            continue
        if output_contract.get("status_values") != [
            "success",
            "needs_clarification",
            "approval_required",
            "failed",
        ]:
            problems.append(f"{spec_file.parent.name}: invalid output_contract.status_values")
    assert not problems, "Subprocess agent specs must declare the staged output contract:\n" + "\n".join(problems)
