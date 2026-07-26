"""Factory-internal project-context contract: manifest schema, boundary-adapter
reference behavior, and independent verification of generated packages.

Scope (AF-054, corrected 2026-07-27): this module is a Factory-side concern
only. It is consumed by `agent_spec.py` (the `ProjectContextContract` manifest
field), used to generate the fail-closed logic baked into each staged
package's `specialist_contract.py`, and used to independently re-verify a
staged package after it is written (`verify_project_context_consistency`).

This is **not** a shared runtime dependency. Agent Hub and existing
specialists (e.g. AI Tech Lead) do not import, copy, or need to match this
module or the `ProjectContext`/`ProjectContextContract` classes — a
generated package's `specialist_contract.py` is fully self-contained and
inlines its own validation, precisely so it never depends on this package at
runtime. Whether Agent Hub adopts an analogous versioned wire contract is
tracked separately as `AGENT-HUB-039`; whether AI Tech Lead adapts to it is
tracked as `ATL-072`. Neither had defined such a schema as of 2026-07-25, and
this module does not assume, require, or wait on either.

What it formalizes, for Factory's own generation and validation pipeline:

  - `ProjectContext`   — the versioned shape Factory expects "the target
    project" to take once dispatched: a `schema_version` plus `project_root`/
    `references`, replacing an untyped pair of envelope strings.
  - `ProjectContextContract` — the manifest declaration a generated
    specialist carries: supported schema versions, whether a target project
    is required at all, which capabilities it exercises there (`read`/
    `write`), and the filesystem permission a runtime should enforce on that
    target root.
  - `validate_project_context` — the reference validation logic that each
    generated `specialist_contract.py` inlines (not imports) as its own
    fail-closed boundary-adapter check.
  - `verify_project_context_consistency` — an independent, post-write check
    Factory runs against a staged package's files on disk, confirming the
    generated `specialist_contract.py` actually matches what `agent.json`
    declares, rather than trusting template rendering blindly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PROJECT_CONTEXT_SCHEMA_VERSION = 1
SUPPORTED_PROJECT_CONTEXT_SCHEMA_VERSIONS = {1}

ProjectContextCapability = Literal["read", "write"]
FilesystemPermission = Literal["none", "read", "write"]

_PERMISSION_RANK: dict[FilesystemPermission, int] = {"none": 0, "read": 1, "write": 2}
_CAPABILITY_FLOOR: dict[ProjectContextCapability, FilesystemPermission] = {
    "read": "read",
    "write": "write",
}


class ProjectContext(BaseModel):
    """The versioned shape Factory expects for "the target project" once dispatched.

    Supersedes treating `project_root`/`references` as untyped envelope
    strings: a schema_version travels with the data, so a Factory-generated
    specialist's own boundary adapter can reject a shape it does not
    understand instead of guessing. Whether Agent Hub sends this shape, or a
    consuming specialist's own model matches it exactly, is out of scope
    here — see the module docstring.
    """

    schema_version: int = PROJECT_CONTEXT_SCHEMA_VERSION
    project_root: str | None = None
    references: list[str] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: int) -> int:
        if v not in SUPPORTED_PROJECT_CONTEXT_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported project context schema_version {v!r}. "
                f"Supported versions: {sorted(SUPPORTED_PROJECT_CONTEXT_SCHEMA_VERSIONS)}."
            )
        return v


class ProjectContextContract(BaseModel):
    """Manifest declaration of a specialist's project-context participation.

    `required` — this specialist cannot do meaningful work without a real
    target project. Factory generates this specialist's own boundary adapter
    (`specialist_contract.py`) to reject dispatch when `project_root` is
    missing, rather than letting it silently substitute its own repository
    as the target — this is enforced by the generated specialist itself, not
    by Agent Hub (Hub-side enforcement of this declaration is out of scope
    here; see the module docstring).

    `capabilities` — what the specialist actually does with the target
    project (`read`, `write`). Drives the minimum `enforced_filesystem_permission`.

    `enforced_filesystem_permission` — the filesystem permission this
    specialist declares it needs on the target project root, as a ceiling a
    runtime *could* enforce. This is independent of `permissions.filesystem`,
    which governs the agent's own working_directory, not an externally
    supplied target project.

    `supported_schema_versions` — the `ProjectContext.schema_version` values
    this specialist accepts. Hub must reject dispatching an unsupported
    version rather than passing it through and letting the specialist guess.
    """

    supported_schema_versions: list[int] = Field(
        default_factory=lambda: [PROJECT_CONTEXT_SCHEMA_VERSION]
    )
    required: bool = False
    capabilities: list[ProjectContextCapability] = Field(default_factory=list)
    enforced_filesystem_permission: FilesystemPermission = "none"

    @field_validator("supported_schema_versions")
    @classmethod
    def validate_supported_versions(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError(
                "project_context_contract.supported_schema_versions cannot be empty."
            )
        unknown = sorted(set(v).difference(SUPPORTED_PROJECT_CONTEXT_SCHEMA_VERSIONS))
        if unknown:
            raise ValueError(
                "project_context_contract.supported_schema_versions contains versions "
                f"Factory does not support: {unknown}."
            )
        return sorted(set(v))

    @model_validator(mode="after")
    def validate_capability_permission_floor(self) -> "ProjectContextContract":
        if self.required and not self.capabilities:
            raise ValueError(
                "project_context_contract.required=true specialists must declare at "
                "least one capability ('read' or 'write')."
            )
        floor = max(
            (_PERMISSION_RANK[_CAPABILITY_FLOOR[cap]] for cap in self.capabilities),
            default=0,
        )
        if _PERMISSION_RANK[self.enforced_filesystem_permission] < floor:
            raise ValueError(
                "project_context_contract.enforced_filesystem_permission "
                f"{self.enforced_filesystem_permission!r} is narrower than its "
                f"capabilities require: {sorted(self.capabilities)}."
            )
        return self


class ProjectContextError(ValueError):
    """Raised when a dispatched project context fails validation against a contract."""


def validate_project_context(
    payload: dict,
    contract: ProjectContextContract,
    *,
    check_path_exists: bool = True,
) -> ProjectContext | None:
    """Validate a dispatched envelope's project context against a specialist's contract.

    Fails closed rather than silently reinterpreting or defaulting:
      - missing when `contract.required` -> rejected
      - unrecognized `project_context` shape -> rejected
      - unsupported/mismatched `schema_version` -> rejected
      - stale `project_root` (path no longer exists on disk) -> rejected

    Returns None when no project context was supplied and none is required.
    """

    raw = payload.get("project_context")
    project_root = payload.get("project_root")
    references = payload.get("references") or []

    if raw is None and project_root is None:
        if contract.required:
            raise ProjectContextError(
                "project context is required but missing: no project_root or "
                "project_context was supplied."
            )
        return None

    if raw is not None:
        if not isinstance(raw, dict):
            raise ProjectContextError("project_context must be a JSON object.")
        unknown = sorted(set(raw).difference({"schema_version", "project_root", "references"}))
        if unknown:
            raise ProjectContextError(
                "project_context contains unknown fields: " + ", ".join(unknown)
            )
        try:
            context = ProjectContext.model_validate(raw)
        except Exception as exc:
            raise ProjectContextError(f"Invalid project_context: {exc}") from exc
    else:
        context = ProjectContext(project_root=project_root, references=list(references))

    if context.schema_version not in contract.supported_schema_versions:
        raise ProjectContextError(
            f"project_context.schema_version={context.schema_version} is not supported "
            f"by this specialist (supports {contract.supported_schema_versions})."
        )

    if contract.required and not context.project_root:
        raise ProjectContextError("project context is required but project_root is empty.")

    if check_path_exists and context.project_root is not None:
        if not Path(context.project_root).exists():
            raise ProjectContextError(
                f"project_root does not exist (stale project context): {context.project_root!r}"
            )

    return context


class ProjectContextConsistencyError(ValueError):
    """Raised when a staged package's agent.json and specialist_contract.py disagree."""


_PROJECT_ROOT_REQUIRED_PATTERN = re.compile(r"^PROJECT_ROOT_REQUIRED\s*=\s*(True|False)\s*$", re.MULTILINE)


def verify_project_context_consistency(package_dir: Path) -> None:
    """Independently verify a staged package's generated files agree with each other.

    Factory templates `specialist_contract.py`'s `PROJECT_ROOT_REQUIRED` from
    the same spec value it writes into `agent.json`'s
    `project_context_contract.required`. This re-reads both *from disk* after
    generation and confirms they still match, catching template-rendering
    bugs (a stale placeholder, a bad substitution) instead of trusting that
    writing the files correctly is the same as generating them correctly.
    """

    manifest_path = package_dir / "agent.json"
    adapter_path = package_dir / "specialist_contract.py"
    if not manifest_path.is_file() or not adapter_path.is_file():
        raise ProjectContextConsistencyError(
            "Cannot verify project-context consistency: agent.json or "
            f"specialist_contract.py is missing under {package_dir}."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared_required = bool(manifest.get("project_context_contract", {}).get("required", False))

    adapter_source = adapter_path.read_text(encoding="utf-8")
    match = _PROJECT_ROOT_REQUIRED_PATTERN.search(adapter_source)
    if match is None:
        raise ProjectContextConsistencyError(
            f"specialist_contract.py under {package_dir} has no PROJECT_ROOT_REQUIRED "
            "constant to verify against agent.json's project_context_contract."
        )
    generated_required = match.group(1) == "True"

    if declared_required != generated_required:
        raise ProjectContextConsistencyError(
            f"agent.json declares project_context_contract.required={declared_required} "
            f"but specialist_contract.py sets PROJECT_ROOT_REQUIRED={generated_required}. "
            "The generated manifest and boundary adapter must agree."
        )
