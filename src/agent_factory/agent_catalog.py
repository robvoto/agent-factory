"""Shared agent inventory across staged and enabled agents.

This module provides one authoritative view of agents the factory knows about:

- staged drafts under ``staging/agents``
- enabled agents under ``config/agents``
- persisted staged-agent records in SQLite

Same agent IDs across staged and enabled locations are treated as one lifecycle
entry. Different agent IDs cannot claim the same alias.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .agent_spec import AgentPackageSpec
from .errors import AgentFactoryError, DuplicateAliasError
from .loader import load_agent_manifests
from .models import AgentManifest
from .storage import list_staged_agent_records

_PROJECT_ROOT = Path(__file__).parents[2]
_ENABLED_AGENTS_DIR = _PROJECT_ROOT / "config" / "agents"
_STAGING_AGENTS_DIR = _PROJECT_ROOT / "staging" / "agents"


class AgentCatalogConflictError(AgentFactoryError):
    """Raised when the same agent ID has conflicting manifests across sources."""


@dataclass(frozen=True)
class AgentCatalogEntry:
    """One logical agent across stage and enabled sources."""

    manifest: AgentManifest
    statuses: tuple[str, ...]
    locations: tuple[str, ...]

    @property
    def id(self) -> str:
        return self.manifest.id


@dataclass(frozen=True)
class AgentPackageDecision:
    """Result of checking whether a requested package can be created or reused."""

    action: str
    entry: AgentCatalogEntry | None = None


def build_agent_catalog(
    *,
    enabled_dir: Path | None = None,
    staging_dir: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, AgentCatalogEntry]:
    """Return a merged inventory of all known agents."""
    catalog: dict[str, AgentCatalogEntry] = {}

    for manifest in load_agent_manifests(enabled_dir or _ENABLED_AGENTS_DIR):
        _merge_entry(
            catalog,
            manifest,
            status="enabled",
            location=_relative_path(manifest.source),
        )

    _merge_staged_packages(
        catalog,
        staging_dir=staging_dir or _STAGING_AGENTS_DIR,
        db_path=db_path,
    )

    _validate_aliases(catalog.values())
    return catalog


def describe_agent_catalog(
    *,
    enabled_dir: Path | None = None,
    staging_dir: Path | None = None,
    db_path: Path | None = None,
) -> str:
    """Render the merged inventory as a readable text summary."""
    catalog = build_agent_catalog(
        enabled_dir=enabled_dir,
        staging_dir=staging_dir,
        db_path=db_path,
    )
    if not catalog:
        return "No known agents yet."

    lines = ["Known agents:"]
    for entry in sorted(catalog.values(), key=lambda item: item.id):
        statuses = ", ".join(entry.statuses)
        locations = ", ".join(entry.locations)
        aliases = ", ".join(entry.manifest.aliases)
        lines.append(
            f"- {entry.id} | {entry.manifest.name} | status: {statuses} | aliases: {aliases}"
        )
        lines.append(f"  locations: {locations}")
    return "\n".join(lines)


def plan_package_reuse(
    spec: AgentPackageSpec,
    *,
    enabled_dir: Path | None = None,
    staging_dir: Path | None = None,
    db_path: Path | None = None,
) -> AgentPackageDecision:
    """Determine whether a requested package should be created or reused."""
    manifest = _manifest_from_spec(spec)
    catalog = build_agent_catalog(
        enabled_dir=enabled_dir,
        staging_dir=staging_dir,
        db_path=db_path,
    )

    existing = catalog.get(manifest.id)
    if existing is None:
        return AgentPackageDecision(action="create")
    if not _same_manifest(existing.manifest, manifest):
        raise AgentCatalogConflictError(
            f"Agent {manifest.id!r} already exists with different contents at "
            f"{', '.join(existing.locations)}. Reuse the existing agent or redesign it."
        )
    return AgentPackageDecision(action="reuse", entry=existing)


def promote_agent(
    agent_id: str,
    *,
    project_root: Path | None = None,
    db_path: Path | None = None,
) -> str:
    """Promote a staged agent into config/agents without duplicating it."""
    root = project_root or _PROJECT_ROOT
    staging_dir = root / "staging" / "agents" / agent_id
    staged_manifest_path = staging_dir / "agent.json"
    if not staged_manifest_path.exists():
        return f"Cannot promote {agent_id}: agent.json not found in staging."

    enabled_dir = root / "config" / "agents"
    enabled_dir.mkdir(parents=True, exist_ok=True)
    enabled_manifest_path = enabled_dir / f"{agent_id}.json"

    staged_manifest = _load_manifest_from_path(staged_manifest_path)
    if enabled_manifest_path.exists():
        enabled_manifest = _load_manifest_from_path(enabled_manifest_path)
        if not _same_manifest(enabled_manifest, staged_manifest):
            raise AgentCatalogConflictError(
                f"Cannot promote {agent_id}: config/agents already contains a different "
                f"manifest at {enabled_manifest_path}."
            )
        _mark_staged_agent_enabled(agent_id, db_path=db_path)
        return f"Agent {agent_id} is already enabled; reused config/agents/{agent_id}.json."

    enabled_manifest_path.write_text(
        staged_manifest_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _mark_staged_agent_enabled(agent_id, db_path=db_path)
    return f"Agent {agent_id} promoted to config/agents/{agent_id}.json and is now enabled."


def _merge_staged_packages(
    catalog: dict[str, AgentCatalogEntry],
    *,
    staging_dir: Path,
    db_path: Path | None,
) -> None:
    staged_records = {row["agent_id"]: dict(row) for row in list_staged_agent_records(db_path=db_path)}
    seen_paths: set[Path] = set()

    for path in sorted(staging_dir.rglob("agent.json")):
        if path in seen_paths:
            continue
        seen_paths.add(path)
        manifest = _load_manifest_from_path(path)
        status = staged_records.get(manifest.id, {}).get("status", "staged")
        _merge_entry(
            catalog,
            manifest,
            status=status,
            location=_relative_path(path.parent),
        )

    for record in staged_records.values():
        package_dir = Path(record["path"])
        manifest_path = package_dir / "agent.json"
        if not manifest_path.exists():
            continue
        if manifest_path in seen_paths:
            continue
        seen_paths.add(manifest_path)
        manifest = _load_manifest_from_path(manifest_path)
        _merge_entry(
            catalog,
            manifest,
            status=record.get("status", "staged"),
            location=_relative_path(package_dir),
        )


def _mark_staged_agent_enabled(agent_id: str, *, db_path: Path | None = None) -> None:
    from .storage import get_staged_agent_record, record_staged_agent, update_staged_agent_status

    record = get_staged_agent_record(agent_id, db_path=db_path)
    if record is None:
        package_dir = _STAGING_AGENTS_DIR / agent_id
        if package_dir.exists():
            record_staged_agent(agent_id, package_dir, db_path=db_path)
        else:
            return
    update_staged_agent_status(agent_id, "enabled", db_path=db_path)


def _merge_entry(
    catalog: dict[str, AgentCatalogEntry],
    manifest: AgentManifest,
    *,
    status: str,
    location: str,
) -> None:
    existing = catalog.get(manifest.id)
    if existing is None:
        catalog[manifest.id] = AgentCatalogEntry(
            manifest=manifest,
            statuses=(status,),
            locations=(location,),
        )
        return

    if not _same_manifest(existing.manifest, manifest):
        raise AgentCatalogConflictError(
            f"Agent {manifest.id!r} has conflicting manifests from multiple sources."
        )

    statuses = tuple(dict.fromkeys((*existing.statuses, status)))
    locations = tuple(dict.fromkeys((*existing.locations, location)))
    catalog[manifest.id] = AgentCatalogEntry(
        manifest=manifest,
        statuses=statuses,
        locations=locations,
    )


def _validate_aliases(entries: Iterable[AgentCatalogEntry]) -> None:
    alias_owner: dict[str, str] = {}
    for entry in sorted(entries, key=lambda item: item.id):
        for alias in entry.manifest.aliases:
            owner = alias_owner.get(alias)
            if owner is None:
                alias_owner[alias] = entry.id
                continue
            if owner != entry.id:
                raise DuplicateAliasError(
                    f"Duplicate alias '{alias}' used by '{owner}' and '{entry.id}'"
                )


def _load_manifest_from_path(path: Path) -> AgentManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentManifest.from_dict(data, source=path)


def _manifest_from_spec(spec: AgentPackageSpec) -> AgentManifest:
    permissions = spec.permissions.model_dump()
    memory = spec.memory_policy.model_dump()
    input_contract = spec.input_contract.model_dump()
    interaction_contract = spec.interaction_contract.model_dump()
    task_contract = spec.task_contract.model_dump(exclude_none=True)
    project_context_contract = spec.project_context_contract.model_dump()
    target_project_access = spec.target_project_access.model_dump(exclude_none=True)
    output_contract = (
        spec.output_contract.model_dump(exclude_none=True)
        if spec.output_contract is not None
        else None
    )
    return AgentManifest.from_dict(
        {
            "id": spec.id,
            "name": spec.name,
            "purpose": spec.purpose,
            "aliases": list(spec.aliases),
            "tools": list(spec.tools),
            "permissions": permissions,
            "memory": memory,
            "runtime": spec.runtime.model_dump(exclude_none=True),
            "input_contract": input_contract,
            "interaction_contract": interaction_contract,
            "task_contract": task_contract,
            "project_context_contract": project_context_contract,
            "target_project_access": target_project_access,
            "output_contract": output_contract,
        }
    )


def _same_manifest(lhs: AgentManifest, rhs: AgentManifest) -> bool:
    return (
        lhs.id == rhs.id
        and lhs.name == rhs.name
        and lhs.purpose == rhs.purpose
        and lhs.aliases == rhs.aliases
        and lhs.tools == rhs.tools
        and lhs.permissions == rhs.permissions
        and lhs.memory == rhs.memory
        and lhs.runtime == rhs.runtime
        and _compatible_optional_contract(lhs.input_contract, rhs.input_contract)
        and _compatible_optional_contract(lhs.interaction_contract, rhs.interaction_contract)
        and _compatible_optional_contract(lhs.task_contract, rhs.task_contract)
        and _compatible_optional_contract(
            lhs.project_context_contract, rhs.project_context_contract
        )
        and _compatible_optional_contract(
            lhs.target_project_access, rhs.target_project_access
        )
        and lhs.output_contract == rhs.output_contract
    )


def _compatible_optional_contract(
    lhs: dict[str, Any] | None,
    rhs: dict[str, Any] | None,
) -> bool:
    """Treat absent legacy declarations as compatible during migration."""

    return lhs == rhs or lhs is None or rhs is None


def _relative_path(path_text: str | None) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)
