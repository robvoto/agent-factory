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
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent_spec import AgentPackageSpec, VALID_ID_PATTERN, SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS
from .build_task import (
    BUILD_TASK_FILENAME,
    AgentBuildTask,
    BuildTaskError,
    assert_task_matches_staged_package,
    build_task_reference,
    load_staged_manifest,
)
from .errors import AgentFactoryError, DuplicateAliasError
from .loader import load_agent_manifests
from .models import AgentManifest
from .storage import list_staged_agent_records
from .versioning import package_diff, package_sha256, require_newer_version, version_key

_PROJECT_ROOT = Path(__file__).parents[2]
_ENABLED_AGENTS_DIR = _PROJECT_ROOT / "config" / "agents"
_STAGING_AGENTS_DIR = _PROJECT_ROOT / "staging" / "agents"
_RELEASED_AGENTS_DIR = _PROJECT_ROOT / "agents"
_FACTORY_CONTROL_ARTIFACTS = frozenset({BUILD_TASK_FILENAME, "BUILD_RESULT.json"})


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


@dataclass(frozen=True)
class AgentPromotionPreview:
    agent_id: str
    staged_version: str
    active_version: str | None
    staged_sha256: str
    active_sha256: str | None
    diff: str


def build_agent_catalog(
    *,
    enabled_dir: Path | None = None,
    staging_dir: Path | None = None,
    released_dir: Path | None = None,
    db_path: Path | None = None,
    allowed_tool_ids: Iterable[str] | None = None,
) -> dict[str, AgentCatalogEntry]:
    """Return a merged inventory of all known agents.

    `allowed_tool_ids` defaults to the real configured set (`config/tools.json`,
    the same source `cli.py`'s registry loading uses) rather than an empty
    allowlist — every already-enabled agent that declares any tool at all
    would otherwise be rejected as requesting "unknown tools" the moment this
    inventory is inspected (as `list_known_agents`/`request_agent_promotion` do).
    """
    catalog: dict[str, AgentCatalogEntry] = {}

    if allowed_tool_ids is None:
        from .cli import DEFAULT_TOOLS_FILE, load_allowed_tools

        allowed_tool_ids = load_allowed_tools(DEFAULT_TOOLS_FILE)

    for manifest in load_agent_manifests(
        enabled_dir or _ENABLED_AGENTS_DIR, allowed_tool_ids=allowed_tool_ids
    ):
        _merge_entry(
            catalog,
            manifest,
            status="enabled",
            location=_relative_path(manifest.source),
        )

    resolved_enabled_dir = enabled_dir or _ENABLED_AGENTS_DIR
    resolved_released_dir = released_dir or (
        resolved_enabled_dir.parent.parent / "agents"
        if enabled_dir is not None
        else _RELEASED_AGENTS_DIR
    )
    _merge_released_packages(
        catalog,
        released_dir=resolved_released_dir,
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
    released_dir: Path | None = None,
    db_path: Path | None = None,
) -> str:
    """Render the merged inventory as a readable text summary."""
    catalog = build_agent_catalog(
        enabled_dir=enabled_dir,
        staging_dir=staging_dir,
        released_dir=released_dir,
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
        released_dir=(
            enabled_dir.parent.parent / "agents"
            if enabled_dir is not None
            else None
        ),
        db_path=db_path,
    )

    existing = catalog.get(manifest.id)
    if existing is None:
        return AgentPackageDecision(action="create")
    if _same_manifest(existing.manifest, manifest):
        return AgentPackageDecision(action="reuse", entry=existing)
    if "enabled" not in existing.statuses:
        raise AgentCatalogConflictError(
            f"Agent {manifest.id!r} already exists with different staged contents at "
            f"{', '.join(existing.locations)}. Resolve the staged package before creating another."
        )
    current = existing.manifest
    if current.version is None or current.manifest_schema_version is None:
        raise AgentCatalogConflictError(
            f"Cannot update {manifest.id!r}: enabled manifest has no supported version metadata."
        )
    release_root = (
        enabled_dir.parent.parent / "agents" if enabled_dir is not None else _RELEASED_AGENTS_DIR
    )
    if not (release_root / manifest.id / "agent.json").is_file():
        raise AgentCatalogConflictError(
            f"Cannot update {manifest.id!r}: Factory's active released package is missing."
        )
    if manifest.manifest_schema_version not in SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS:
        raise AgentCatalogConflictError(
            f"Cannot update {manifest.id!r}: staged manifest schema "
            f"{manifest.manifest_schema_version!r} is unsupported."
        )
    try:
        require_newer_version(manifest.version or "", current.version)
    except ValueError as exc:
        raise AgentCatalogConflictError(f"Cannot update {manifest.id!r}: {exc}") from exc
    return AgentPackageDecision(action="upgrade", entry=existing)


def preview_agent_promotion(
    agent_id: str,
    *,
    project_root: Path | None = None,
    db_path: Path | None = None,
) -> AgentPromotionPreview:
    """Validate and render the exact staged release that needs approval."""
    root = project_root or _PROJECT_ROOT
    _validate_release_agent_id(agent_id)
    staging_dir = root / "staging" / "agents" / agent_id
    staged_path = staging_dir / "agent.json"
    released_dir = root / "agents" / agent_id
    enabled_path = root / "config" / "agents" / agent_id / "agent.json"
    previous_dir = root / "agents" / ".previous" / agent_id
    if not staged_path.is_file():
        raise AgentCatalogConflictError(f"Cannot promote {agent_id}: staged agent.json is missing.")
    try:
        _assert_build_result_gate(
            agent_id, staging_dir=staging_dir, project_root=root, db_path=db_path
        )
    except BuildTaskError as exc:
        raise AgentCatalogConflictError(
            f"Cannot promote {agent_id}: current implementation handoff is not validated: {exc}"
        ) from exc
    staged_raw, staged_manifest = _load_versioned_manifest(staged_path)
    if staged_manifest.id != agent_id:
        raise AgentCatalogConflictError("Staged manifest ID does not match the requested agent ID.")
    if staged_manifest.manifest_schema_version not in SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS:
        raise AgentCatalogConflictError(
            f"Staged manifest schema {staged_manifest.manifest_schema_version!r} is unsupported."
        )

    has_release = released_dir.exists()
    has_enabled = enabled_path.exists()
    if has_release != has_enabled:
        raise AgentCatalogConflictError(
            f"Cannot promote {agent_id}: released package and enabled registry disagree."
        )
    if has_release:
        if not (released_dir / "agent.json").is_file():
            raise AgentCatalogConflictError(f"Released package for {agent_id} has no agent.json.")
        active_raw, active_manifest = _load_versioned_manifest(released_dir / "agent.json")
        enabled_raw, enabled_manifest = _load_versioned_manifest(enabled_path)
        if active_manifest.id != agent_id or enabled_manifest.id != agent_id:
            raise AgentCatalogConflictError("Active package or registry has a conflicting agent ID.")
        if active_raw != enabled_raw:
            raise AgentCatalogConflictError(
                f"Cannot promote {agent_id}: enabled manifest differs from Factory's active release."
            )
        if staged_manifest.manifest_schema_version != active_manifest.manifest_schema_version:
            raise AgentCatalogConflictError(
                "Cannot promote across manifest schema versions; the staged manifest is incompatible with the active release."
            )
        try:
            require_newer_version(staged_manifest.version or "", active_manifest.version or "")
        except ValueError as exc:
            raise AgentCatalogConflictError(f"Cannot promote {agent_id}: {exc}") from exc
        active_version = active_manifest.version
        active_sha = package_sha256(released_dir)
        diff = package_diff(released_dir, staging_dir)
    else:
        if previous_dir.exists():
            raise AgentCatalogConflictError(
                f"Cannot promote {agent_id}: an orphaned previous release exists without an active release."
            )
        active_version = None
        active_sha = None
        diff = package_diff(None, staging_dir)

    return AgentPromotionPreview(
        agent_id=agent_id,
        staged_version=staged_manifest.version or "",
        active_version=active_version,
        staged_sha256=package_sha256(staging_dir),
        active_sha256=active_sha,
        diff=diff,
    )


def promote_agent(
    agent_id: str,
    *,
    expected_staged_sha256: str,
    expected_active_sha256: str | None,
    project_root: Path | None = None,
    db_path: Path | None = None,
) -> str:
    """Activate an approved staged version while retaining one prior release."""
    root = project_root or _PROJECT_ROOT
    preview = preview_agent_promotion(agent_id, project_root=root, db_path=db_path)
    if preview.staged_sha256 != expected_staged_sha256:
        raise AgentCatalogConflictError("Staged package changed after approval; request promotion approval again.")
    if preview.active_sha256 != expected_active_sha256:
        raise AgentCatalogConflictError("Active release changed after approval; request promotion approval again.")

    staging_dir = root / "staging" / "agents" / agent_id
    released_dir = root / "agents" / agent_id
    previous_dir = root / "agents" / ".previous" / agent_id
    enabled_path = root / "config" / "agents" / agent_id / "agent.json"
    temporary_dir = root / "agents" / f".release-{agent_id}.tmp"
    temporary_manifest = enabled_path.with_name("agent.json.tmp")
    had_active = released_dir.exists()
    temporary_dir.parent.mkdir(parents=True, exist_ok=True)
    if temporary_dir.exists():
        shutil.rmtree(temporary_dir)
    shutil.copytree(staging_dir, temporary_dir, ignore=_ignore_factory_control_artifacts)
    if package_sha256(temporary_dir) != expected_staged_sha256:
        shutil.rmtree(temporary_dir)
        raise AgentCatalogConflictError("Staged package changed while preparing its release.")

    previous_dir.parent.mkdir(parents=True, exist_ok=True)
    if previous_dir.exists():
        shutil.rmtree(previous_dir)
    try:
        if had_active:
            os.replace(released_dir, previous_dir)
        os.replace(temporary_dir, released_dir)
        enabled_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_manifest.write_bytes((released_dir / "agent.json").read_bytes())
        os.replace(temporary_manifest, enabled_path)
    except Exception:
        if released_dir.exists():
            shutil.rmtree(released_dir)
        if previous_dir.exists():
            os.replace(previous_dir, released_dir)
        temporary_manifest.unlink(missing_ok=True)
        temporary_dir_safe_remove(temporary_dir)
        raise
    _mark_staged_agent_enabled(agent_id, staging_dir=staging_dir.parent, db_path=db_path)
    old_text = preview.active_version or "none"
    return (
        f"Agent {agent_id} promoted from {old_text} to {preview.staged_version}; "
        f"Factory retained the prior release at agents/.previous/{agent_id}/."
        if had_active
        else f"Agent {agent_id} first release {preview.staged_version} is active at agents/{agent_id}/."
    )


def preview_agent_rollback(
    agent_id: str, *, project_root: Path | None = None
) -> dict[str, str]:
    root = project_root or _PROJECT_ROOT
    _validate_release_agent_id(agent_id)
    active_dir = root / "agents" / agent_id
    previous_dir = root / "agents" / ".previous" / agent_id
    enabled_path = root / "config" / "agents" / agent_id / "agent.json"
    if not (active_dir / "agent.json").is_file() or not (previous_dir / "agent.json").is_file() or not enabled_path.is_file():
        raise AgentCatalogConflictError(f"Cannot roll back {agent_id}: active or previous release is missing.")
    active_raw, active = _load_versioned_manifest(active_dir / "agent.json")
    previous_raw, previous = _load_versioned_manifest(previous_dir / "agent.json")
    enabled_raw, _enabled = _load_versioned_manifest(enabled_path)
    if active_raw != enabled_raw or active.id != agent_id or previous.id != agent_id:
        raise AgentCatalogConflictError("Rollback blocked: active release and enabled registry conflict.")
    if active.manifest_schema_version != previous.manifest_schema_version:
        raise AgentCatalogConflictError("Rollback blocked: previous manifest schema is incompatible.")
    if version_key(previous.version or "") >= version_key(active.version or ""):
        raise AgentCatalogConflictError("Rollback blocked: previous release is not older than the active release.")
    return {
        "active_version": active.version or "",
        "previous_version": previous.version or "",
        "active_sha256": package_sha256(active_dir),
        "previous_sha256": package_sha256(previous_dir),
    }


def rollback_agent(
    agent_id: str,
    *,
    expected_active_sha256: str,
    expected_previous_sha256: str,
    project_root: Path | None = None,
) -> str:
    """Reactivate the last approved version and keep the displaced version available."""
    root = project_root or _PROJECT_ROOT
    preview = preview_agent_rollback(agent_id, project_root=root)
    if preview["active_sha256"] != expected_active_sha256 or preview["previous_sha256"] != expected_previous_sha256:
        raise AgentCatalogConflictError("Release state changed after rollback approval; request rollback again.")
    active_dir = root / "agents" / agent_id
    previous_dir = root / "agents" / ".previous" / agent_id
    enabled_path = root / "config" / "agents" / agent_id / "agent.json"
    displaced_dir = root / "agents" / f".rollback-active-{agent_id}.tmp"
    temporary_manifest = enabled_path.with_name("agent.json.tmp")
    if displaced_dir.exists():
        shutil.rmtree(displaced_dir)
    old_registry_bytes = enabled_path.read_bytes()
    active_moved = False
    previous_moved = False
    registry_updated = False
    try:
        os.replace(active_dir, displaced_dir)
        active_moved = True
        os.replace(previous_dir, active_dir)
        previous_moved = True
        temporary_manifest.write_bytes((active_dir / "agent.json").read_bytes())
        os.replace(temporary_manifest, enabled_path)
        registry_updated = True
        os.replace(displaced_dir, previous_dir)
    except Exception:
        if previous_moved and active_dir.exists():
            os.replace(active_dir, previous_dir)
        if active_moved and displaced_dir.exists():
            os.replace(displaced_dir, active_dir)
        if registry_updated:
            temporary_manifest.write_bytes(old_registry_bytes)
            os.replace(temporary_manifest, enabled_path)
        temporary_manifest.unlink(missing_ok=True)
        raise
    return f"Agent {agent_id} rolled back from {preview['active_version']} to {preview['previous_version']}."


def _load_versioned_manifest(path: Path) -> tuple[dict[str, Any], AgentManifest]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentCatalogConflictError(f"Invalid release manifest at {path}: {exc}") from exc
    if not isinstance(raw, dict) or "version" not in raw or "manifest_schema_version" not in raw:
        raise AgentCatalogConflictError(f"Release manifest at {path} lacks version metadata.")
    schema_version = raw["manifest_schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version not in SUPPORTED_AGENT_MANIFEST_SCHEMA_VERSIONS
    ):
        raise AgentCatalogConflictError(f"Release manifest at {path} uses an incompatible schema version.")
    try:
        manifest = AgentManifest.from_dict(raw, source=path)
    except Exception as exc:
        raise AgentCatalogConflictError(f"Incompatible release manifest at {path}: {exc}") from exc
    return raw, manifest


def _validate_release_agent_id(agent_id: str) -> None:
    if not VALID_ID_PATTERN.fullmatch(agent_id):
        raise AgentCatalogConflictError(f"Invalid agent ID for release operation: {agent_id!r}.")


def temporary_dir_safe_remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _merge_released_packages(
    catalog: dict[str, AgentCatalogEntry],
    *,
    released_dir: Path,
) -> None:
    if not released_dir.exists():
        return
    for path in sorted(released_dir.glob("*/agent.json")):
        manifest = _load_manifest_from_path(path)
        _merge_entry(
            catalog,
            manifest,
            status="released",
            location=_relative_path(path.parent),
        )

def _ignore_factory_control_artifacts(_directory: str, names: list[str]) -> list[str]:
    """Keep Factory control artifacts out of released runtime packages."""

    return [name for name in names if name in _FACTORY_CONTROL_ARTIFACTS]


def _assert_build_result_gate(
    agent_id: str,
    *,
    staging_dir: Path,
    project_root: Path,
    db_path: Path | None,
) -> None:
    """Require the latest current-manifest task to have validated evidence."""

    from .storage import list_build_tasks_for_agent, list_build_tasks_for_agent_manifest

    if not list_build_tasks_for_agent(agent_id, db_path=db_path):
        # Legacy/simple config-only packages have no implementation handoff
        # and retain the existing promotion path.
        return

    _raw, _manifest, manifest_digest = load_staged_manifest(staging_dir, agent_id)

    history = list_build_tasks_for_agent_manifest(
        agent_id,
        manifest_digest,
        db_path=db_path,
    )
    if not history:
        raise BuildTaskError("build-task history exists, but none matches the current staged manifest")
    current = history[-1]
    if current["status"] != "validated":
        raise BuildTaskError(
            f"latest build task correlation {current['correlation_id']} is {current['status']!r}"
        )
    task_path = (project_root / current["artifact_reference"]).resolve()
    try:
        task = AgentBuildTask.model_validate(
            json.loads(task_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BuildTaskError("validated build task artifact is invalid") from exc
    if (
        task.agent_id != agent_id
        or task.correlation_id != current["correlation_id"]
        or task.manifest_sha256 != manifest_digest
        or build_task_reference(task) != current["artifact_reference"]
    ):
        raise BuildTaskError("validated build task identity does not match current staged manifest")
    assert_task_matches_staged_package(task, project_root)
    from .build_result import _load_persisted_result, _validate_for_task

    persisted = _load_persisted_result(
        project_root / f"{task.staging_target}/BUILD_RESULT.json",
        task,
        current["artifact_reference"],
    )
    _validate_for_task(persisted, task)


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
        staged_id = path.parent.name
        if staged_records.get(staged_id, {}).get("status") == "enabled" and staged_id in catalog:
            seen_paths.add(path)
            continue
        seen_paths.add(path)
        manifest = _load_manifest_from_path(path)
        status = staged_records.get(manifest.id, {}).get("status", "staged")
        # Once a staged package has been promoted, config/agents is the live
        # source of truth.  Keeping the old staging directory is useful for
        # audit/review, but it must not later conflict with a legitimately
        # evolved enabled manifest.
        if status == "enabled" and manifest.id in catalog:
            continue
        _merge_entry(
            catalog,
            manifest,
            status=status,
            location=_relative_path(path.parent),
        )

    for record in staged_records.values():
        if record.get("status") == "enabled" and record["agent_id"] in catalog:
            continue
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


def _mark_staged_agent_enabled(
    agent_id: str,
    *,
    staging_dir: Path | None = None,
    db_path: Path | None = None,
) -> None:
    from .storage import (
        get_staged_agent_record,
        record_staged_agent,
        update_staged_agent_status,
    )

    record = get_staged_agent_record(agent_id, db_path=db_path)
    if record is None:
        package_dir = (staging_dir or _STAGING_AGENTS_DIR) / agent_id
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
            "version": spec.version,
            "manifest_schema_version": spec.manifest_schema_version,
            "name": spec.name,
            "purpose": spec.purpose,
            "aliases": list(spec.aliases),
            "tools": list(spec.tools),
            "mcp_servers": [server.model_dump(exclude_none=True) for server in spec.mcp_servers],
            "permissions": permissions,
            "memory": memory,
            "design": spec.design.model_dump() if spec.design is not None else None,
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
        and lhs.version == rhs.version
        and lhs.manifest_schema_version == rhs.manifest_schema_version
        and lhs.name == rhs.name
        and lhs.purpose == rhs.purpose
        and lhs.aliases == rhs.aliases
        and lhs.tools == rhs.tools
        and _compatible_optional_contract(lhs.mcp_servers, rhs.mcp_servers)
        and lhs.permissions == rhs.permissions
        and lhs.memory == rhs.memory
        # A legacy manifest without design remains readable and reusable only
        # by another legacy-shaped spec; an explicit new design must not be
        # silently treated as equivalent to an unknown old pattern.
        and lhs.design == rhs.design
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
