"""Machine-readable capability handshake for Agent Factory."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = 2
MANIFEST_COMMAND = "uv run agent-factory manifest"

_PROJECT_ROOT = Path(__file__).parents[2]
_AGENTS_DIR = _PROJECT_ROOT / "config" / "agents"
_STAGING_DIR = _PROJECT_ROOT / "staging" / "agents"
_BACKLOG_URL = "https://docs.google.com/spreadsheets/d/1outLuOWhd-A7uvzsl9C2Jc-tKpsyci9HPZalxcmFiOg/edit"

_REQUIRED_DOCS = [
    "docs/INDEX.md",
    "docs/platform-architecture.md",
    "docs/architecture.md",
    "docs/agent-contract.md",
    "docs/permission-model.md",
    "docs/trusted-sources.md",
]


def _load_enabled_agents() -> list[dict[str, Any]]:
    """Read enabled agent configs from config/agents/. Returns compact summaries."""
    agents: list[dict[str, Any]] = []
    if not _AGENTS_DIR.exists():
        return agents
    for agent_dir in sorted(_AGENTS_DIR.iterdir()):
        spec_file = agent_dir / "agent.json"
        if not spec_file.is_file():
            continue
        try:
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
            agents.append({
                "id": spec.get("id", agent_dir.name),
                "name": spec.get("name", ""),
                "purpose": spec.get("purpose", ""),
                "aliases": spec.get("aliases", []),
                "runtime_entrypoint": spec.get("runtime", {}).get("entrypoint", ""),
                "requires_approval": spec.get("permissions", {}).get("requires_approval", True),
                "backlog_sheet_id": spec.get("backlog_sheet_id"),
                "input_contract": spec.get("input_contract"),
                "interaction_contract": spec.get("interaction_contract"),
            })
        except Exception:
            logger.warning("Could not read agent spec: %s", spec_file)
    return agents


def _count_staged() -> int:
    """Count staged agent packages in staging/agents/."""
    if not _STAGING_DIR.exists():
        return 0
    return sum(1 for d in _STAGING_DIR.iterdir() if d.is_dir())


def _count_pending_approvals() -> int:
    """Count pending approval records in the factory DB without hard dependency."""
    try:
        from .storage import list_pending_approvals
        return len(list_pending_approvals())
    except Exception:
        return -1


def build_factory_manifest(*, include_live: bool = True) -> dict[str, Any]:
    """Return the compact handshake other agents (Agent Hub) can cache.

    include_live=True (default) adds live registry counts and enabled agent list.
    Set include_live=False for static/offline manifests in tests.
    """
    manifest: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "agent_id": "agent-factory",
        "agent_name": "Agent Factory",
        "package": "agent_factory",
        "package_version": __version__,
        "role": "specialist agent that creates, validates, and stages agents",
        "purpose": (
            "Primary responsibility: Design and govern new specialist agent packages.\n"
            "Select for: Creating, configuring, validating, staging, approving, rejecting, or "
            "promoting a specialist agent package as the requested deliverable.\n"
            "Do not select for: Implementing backlog items, fixing bugs, changing documentation, "
            "or modifying source code in the existing Agent Factory repository or any other "
            "existing software project."
        ),
        "entrypoints": {
            "cli": "agent-factory",
            "manifest": "manifest",
            "list": "list",
            "create": "create",
            "factory": "factory",
            "telegram": "telegram",
            "pending": "pending",
            "staged": "staged",
            "approve": "approve",
            "reject": "reject",
            "promote": "promote",
            "delete": "delete",
            "route": "route",
            "setup": "setup",
            "doctor": "doctor",
        },
        "specialist_protocol": {
            "protocol": "agent-hub.task",
            "protocol_version": 1,
            "required_fields": ["task"],
            "optional_context": ["project_root", "references"],
            "ownership": (
                "Agent Hub transports known context without interpreting it; each specialist "
                "adapts the universal envelope into its own workflow."
            ),
        },
        "progress_contract": {
            "optional": True,
            "activation": "Hub supplies run_id and request_id",
            "schema_version": 1,
            "transport": "stdout_jsonl",
            "log_transport": "stderr",
            "final_result_transport": "existing output JSON file",
            "generated_adapters": [
                "deterministic_workflow",
                "simple_agent",
                "deep_agent",
            ],
            "notes": (
                "Progress is operational telemetry only. It excludes hidden reasoning, "
                "full prompts, secrets, raw provider payloads, and unbounded logs."
            ),
        },
        "required_docs": _REQUIRED_DOCS,
        "registry": {
            "enabled_agents_dir": "config/agents",
            "staged_agents_dir": "staging/agents",
            "package_template_dir": "templates/agent-package",
        },
        "backlog_url": _BACKLOG_URL,
        "hub_integration": {
            "handshake_command": MANIFEST_COMMAND,
            "handshake_ttl_seconds": 3600,
            "discovery": "registry-driven — Agent Hub reads config/agents/<id>/agent.json or calls manifest",
            "approval_required_before_registry_entry": True,
            "notes": "Agent Hub should call `manifest` once per session or when TTL expires. Never auto-scan the repo.",
        },
    }

    if include_live:
        enabled_agents = _load_enabled_agents()
        manifest["live_registry"] = {
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "enabled_agents": enabled_agents,
            "enabled_count": len(enabled_agents),
            "staged_count": _count_staged(),
            "pending_approval_count": _count_pending_approvals(),
        }

    manifest["manifest_hash"] = _manifest_hash(manifest)
    return manifest


def render_factory_manifest(*, compact: bool = False, include_live: bool = True) -> str:
    """Render the handshake as JSON for other agents to cache."""

    manifest = build_factory_manifest(include_live=include_live)
    if compact:
        return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)


def _manifest_hash(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_hash", None)
    # live_registry is excluded from hash so the hash is stable for static fields
    payload.pop("live_registry", None)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
