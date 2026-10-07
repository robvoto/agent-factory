"""Bounded tool functions exposed to the Factory Brain.

These are the only actions the Factory Brain may take directly.
No shell, no network, no unrestricted filesystem write.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from .agent_catalog import (
    build_agent_catalog,
    describe_agent_catalog,
    plan_package_reuse,
)
from .agent_spec import AgentPackageSpec, validate_agent_package_spec_payload
from .build_task import (
    BUILD_TASK_FILENAME,
    AgentBuildTask,
    BuildTaskError,
    assert_task_matches_staged_package,
    deterministic_correlation_id,
    load_staged_manifest,
)
from .build_task import build_task_reference as task_reference
from .design_research import request_design_research, run_design_research
from .errors import AgentFactoryError
from .package_scaffold import copy_standard_workspace
from .project_context import (
    ProjectContextConsistencyError,
    verify_project_context_consistency,
)

_PROJECT_ROOT = Path(__file__).parents[2]
_STAGING_DIR = _PROJECT_ROOT / "staging" / "agents"
_MEMORY_DIR = _PROJECT_ROOT / "memory" / "factory"
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"
_PROGRESS_TEMPLATE_DIR = _TEMPLATES_DIR / "progress-adapter"
logger = logging.getLogger(__name__)


@tool
def list_templates() -> str:
    """List available agent package templates."""
    if not _TEMPLATES_DIR.exists():
        logger.info("No templates directory found at %s.", _TEMPLATES_DIR)
        return "No templates directory found."
    templates = sorted(p.name for p in _TEMPLATES_DIR.iterdir() if p.is_dir())
    if not templates:
        logger.info("Templates directory exists but contains no template packages.")
        return "No templates available."
    logger.info("Listing %s template packages.", len(templates))
    return "Available templates:\n" + "\n".join(f"- {t}" for t in templates)


@tool
def list_staged_agents() -> str:
    """List all staged agent draft packages."""
    if not _STAGING_DIR.exists():
        logger.info("No staged agent directory found at %s.", _STAGING_DIR)
        return "No staged agents yet."
    agents = sorted(p.name for p in _STAGING_DIR.iterdir() if p.is_dir())
    if not agents:
        logger.info("No staged agent drafts exist yet.")
        return "No staged agent drafts exist yet."
    logger.info("Listing %s staged agent drafts.", len(agents))
    return "Staged agent drafts:\n" + "\n".join(f"- {a}" for a in agents)


@tool
def read_staged_review(agent_id: str) -> str:
    """Read the REVIEW.md for a staged agent draft by its ID."""
    package_dir = _STAGING_DIR / agent_id.strip()
    if not package_dir.exists():
        logger.warning("Staged agent not found: %s", agent_id)
        return f"Staged agent not found: {agent_id!r}"
    review = package_dir / "REVIEW.md"
    if not review.exists():
        logger.warning("REVIEW.md not found for staged agent: %s", agent_id)
        return f"REVIEW.md not found for staged agent: {agent_id!r}"
    logger.info("Reading staged review for %s.", agent_id)
    return review.read_text(encoding="utf-8")


@tool
def list_known_agents() -> str:
    """List all staged and enabled agents the factory knows about."""
    try:
        return describe_agent_catalog(
            enabled_dir=_PROJECT_ROOT / "config" / "agents",
            staging_dir=_STAGING_DIR,
        )
    except AgentFactoryError as exc:
        logger.warning("Failed to build agent catalog: %s", exc)
        return f"Unable to list known agents: {exc}"


@tool
def list_registered_tool_ids() -> str:
    """List tool IDs currently allowed in AgentPackageSpec manifests."""
    from .cli import load_allowed_tools

    tool_ids = load_allowed_tools(_PROJECT_ROOT / "config" / "tools.json")
    if not tool_ids:
        return "No registered manifest tool IDs."
    return "Registered manifest tool IDs:\n" + "\n".join(f"- {tool_id}" for tool_id in tool_ids)


@tool
def validate_agent_package_spec(spec_json: str) -> str:
    """Validate an AgentPackageSpec JSON draft without writing or staging files.

    Use this before create_staged_agent_package. Validation fails closed on
    unknown fields, including nested contract/runtime fields, so intended
    behavior cannot be silently discarded by schema defaults.

    Returns the normalized validated spec JSON or a validation error.
    """
    from pydantic import ValidationError

    try:
        raw = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON supplied for agent spec validation: %s", exc)
        return f"Invalid JSON in spec: {exc}"

    try:
        spec = validate_agent_package_spec_payload(raw)
        _validate_registered_tool_ids(spec)
    except (ValidationError, ValueError) as exc:
        logger.warning("Invalid agent spec draft: %s", exc)
        return f"Invalid agent spec:\n{exc}"

    return "Valid AgentPackageSpec. No files were written.\n" + spec.model_dump_json(
        indent=2,
        exclude_none=True,
    )


def _validate_registered_tool_ids(spec: AgentPackageSpec) -> None:
    """Fail closed when a draft names tools outside config/tools.json."""
    from .cli import load_allowed_tools

    allowed = set(load_allowed_tools(_PROJECT_ROOT / "config" / "tools.json"))
    unknown = sorted(tool_id for tool_id in spec.tools if tool_id not in allowed)
    if unknown:
        raise ValueError(
            "Unknown tool ID(s) not registered in config/tools.json: "
            + ", ".join(unknown)
        )


@tool
def create_staged_agent_package(spec_json: str) -> str:
    """Create a staged agent package from a validated JSON spec.

    The spec must be a JSON object with these fields:
      id         - lowercase identifier, e.g. "research-agent"
      manifest_schema_version - agent.json schema version (defaults to current)
      name       - human-readable name, e.g. "Research Agent"
      purpose    - routing contract with Primary responsibility, Select for, and Do not select for sections
      aliases    - list of command aliases, e.g. ["research", "find"]
      tools      - list of approved tool IDs (may be empty)
      mcp_servers - explicit MCP server/tool declarations and permission boundaries
      permissions - object: network, filesystem, shell, requires_approval
      memory_policy - object: scope, retention
      design - object: runtime_pattern and runtime_pattern_reason; required for new packages
      runtime    - object: mode plus mode-specific invocation details
      input_contract - universal Hub task-envelope declaration
      interaction_contract - advertised progress/clarification/approval/resume/cancellation support
      task_contract - optional declared task kinds and default task kind
      project_context_contract - Factory-side project-context participation: supported
                   schema versions, whether a target project is required,
                   consumed capabilities (read/write), and the enforced
                   filesystem permission on the target project root. After
                   writing files, Factory independently re-reads agent.json
                   and specialist_contract.py from disk and fails staging if
                   they disagree.
      target_project_access - optional target-project authorization and
                   creation contract: explicit project_root requirement,
                   authorization modes, registry source, whether creating new
                   targets is allowed, creation scope, and fail-closed reasons
      output_contract - required for subprocess agents: staged status contract
      runtime.progress - optional Hub progress config for Hub-callable or long-running agents
      risks      - list of risk labels (auto-populated from permissions)
      tests      - list of test descriptions
      operating_rules - approved runtime rules rendered into SYSTEM.md
      extensions - specialist-owned metadata with no universal meaning (e.g. a
                   backlog pointer); written through verbatim, never interpreted

    Returns a summary of created files or an error message.
    """
    from pydantic import ValidationError

    try:
        raw = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON supplied for staged agent creation: %s", exc)
        return f"Invalid JSON in spec: {exc}"

    try:
        spec = validate_agent_package_spec_payload(raw)
        _validate_registered_tool_ids(spec)
    except (ValidationError, ValueError) as exc:
        logger.warning("Invalid staged agent spec: %s", exc)
        return f"Invalid agent spec:\n{exc}"

    try:
        decision = plan_package_reuse(
            spec,
            enabled_dir=_PROJECT_ROOT / "config" / "agents",
            staging_dir=_STAGING_DIR,
        )
    except AgentFactoryError as exc:
        logger.warning("Agent inventory conflict for %s: %s", spec.id, exc)
        return str(exc)

    if decision.action == "reuse" and decision.entry is not None:
        statuses = ", ".join(decision.entry.statuses)
        locations = ", ".join(decision.entry.locations)
        logger.info("Reusing existing agent package for %s.", spec.id)
        if "staged" in decision.entry.statuses:
            from .storage import get_staged_agent_record, record_staged_agent

            if get_staged_agent_record(spec.id) is None:
                package_dir = _STAGING_DIR / spec.id
                if package_dir.exists():
                    record_staged_agent(spec.id, package_dir)
                    logger.info("Backfilled staged agent record for %s.", spec.id)
        return (
            f"Agent package already exists: {spec.id}\n"
            f"Status: {statuses}\n"
            f"Locations: {locations}\n"
            "No duplicate package was created."
        )

    progress = spec.runtime.progress
    if progress is not None and progress.enabled and not _PROGRESS_TEMPLATE_DIR.is_dir():
        logger.error("Progress adapter template is missing: %s", _PROGRESS_TEMPLATE_DIR)
        return f"Progress adapter template is missing: {_PROGRESS_TEMPLATE_DIR}"

    package_dir = _STAGING_DIR / spec.id
    logger.info("Creating staged agent package for %s at %s.", spec.id, package_dir)
    package_dir.mkdir(parents=True, exist_ok=False)

    agent_manifest_data: dict[str, Any] = {
        "id": spec.id,
        "version": spec.version,
        "manifest_schema_version": spec.manifest_schema_version,
        "name": spec.name,
        "purpose": spec.purpose,
        "aliases": spec.aliases,
        "tools": spec.tools,
        "mcp_servers": [server.model_dump(exclude_none=True) for server in spec.mcp_servers],
        "permissions": spec.permissions.model_dump(),
        "memory": spec.memory_policy.model_dump(),
        "design": spec.design.model_dump() if spec.design is not None else None,
        "runtime": spec.runtime.model_dump(exclude_none=True),
        "input_contract": spec.input_contract.model_dump(),
        "interaction_contract": spec.interaction_contract.model_dump(),
        "task_contract": spec.task_contract.model_dump(exclude_none=True),
        "project_context_contract": spec.project_context_contract.model_dump(),
        "target_project_access": spec.target_project_access.model_dump(exclude_none=True),
        "output_contract": (
            spec.output_contract.model_dump(exclude_none=True)
            if spec.output_contract is not None
            else None
        ),
    }
    agent_manifest_data.update(spec.extensions)

    template_dir = _TEMPLATES_DIR / "agent-package"
    copy_standard_workspace(
        template_dir,
        package_dir,
        {
            "agent_id": spec.id,
            "agent_name": spec.name,
            "agent_alias": spec.aliases[0],
            "agent_purpose": spec.purpose,
            "project_root_required": str(spec.project_context_contract.required),
            "runtime_pattern": spec.design.runtime_pattern if spec.design else "",
            "runtime_pattern_reason": spec.design.runtime_pattern_reason if spec.design else "",
        },
    )
    (package_dir / "agent.json").write_text(
        json.dumps(agent_manifest_data, indent=2) + "\n",
        encoding="utf-8",
    )

    system_text = (template_dir / "SYSTEM.md").read_text(encoding="utf-8")
    system_text = system_text.replace("{{agent_name}}", spec.name).replace(
        "{{agent_purpose}}", spec.purpose
    )
    if spec.operating_rules:
        approved_rules = "\n".join(f"- {rule}" for rule in spec.operating_rules)
        system_text += f"\nApproved operating rules:\n\n{approved_rules}\n"
    (package_dir / "SYSTEM.md").write_text(system_text, encoding="utf-8")

    agents_text = (template_dir / "AGENTS.md").read_text(encoding="utf-8")
    agents_text = agents_text.replace("{{agent_name}}", spec.name).replace(
        "{{agent_purpose}}", spec.purpose
    )
    (package_dir / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    (package_dir / "tools.json").write_text(
        json.dumps({"tools": spec.tools}, indent=2) + "\n", encoding="utf-8"
    )

    (package_dir / "permissions.json").write_text(
        json.dumps(spec.permissions.model_dump(), indent=2) + "\n", encoding="utf-8"
    )

    (package_dir / "memory.json").write_text(
        json.dumps(spec.memory_policy.model_dump(), indent=2) + "\n", encoding="utf-8"
    )

    (package_dir / "README.md").write_text(
        f"# {spec.name}\n\n"
        "**Status:** staged draft — not enabled.\n\n"
        f"**Purpose:** {spec.purpose}\n\n"
        f"**Aliases:** {', '.join(spec.aliases)}\n\n"
        "Do not promote this agent until human approval. Promotion releases the "
        "full package under `agents/<id>/` and writes `config/agents/<id>.json` "
        "from that released package.\n",
        encoding="utf-8",
    )

    specialist_contract_template = (
        _TEMPLATES_DIR / "agent-package" / "specialist_contract.py"
    ).read_text(encoding="utf-8")
    (package_dir / "specialist_contract.py").write_text(
        specialist_contract_template.replace(
            "{{project_root_required}}",
            str(spec.project_context_contract.required),
        ),
        encoding="utf-8",
    )

    tests_dir = package_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / ".gitkeep").touch()

    risks_text = "\n".join(f"- {r}" for r in spec.risks) or "- none detected"
    tests_text = "\n".join(f"- {t}" for t in spec.tests) or "- none specified"
    (package_dir / "REVIEW.md").write_text(
        f"# Agent Draft Review\n\n"
        "Status: staged draft only. This agent is not enabled.\n\n"
        f"## Spec\n\n"
        f"- ID: `{spec.id}`\n"
        f"- Name: {spec.name}\n"
        f"- Purpose: {spec.purpose}\n\n"
        f"## Runtime design\n\n"
        f"- Pattern: `{spec.design.runtime_pattern if spec.design else 'legacy/unspecified'}`\n"
        f"- Reason: {spec.design.runtime_pattern_reason if spec.design else 'Legacy manifest; select explicitly before a new staging release.'}\n\n"
        f"## Risks\n\n{risks_text}\n\n"
        f"## Tests\n\n{tests_text}\n\n"
        "## Approval rule\n\n"
        "Do not promote this agent until a human approves it. Promotion releases "
        "the full package under `agents/<id>/` and writes `config/agents/<id>.json` "
        "from that released package.\n",
        encoding="utf-8",
    )
    if progress is not None and progress.enabled:
        _copy_progress_adapter(package_dir)
        logger.info(
            "Added %s progress adapter to staged agent %s.",
            progress.adapter,
            spec.id,
        )

    try:
        verify_project_context_consistency(package_dir)
    except ProjectContextConsistencyError as exc:
        logger.error("Project-context consistency check failed for %s: %s", spec.id, exc)
        return f"Staged agent package {spec.id} failed independent validation: {exc}"

    logger.debug("Wrote staged agent files for %s.", spec.id)

    created = sorted(
        str(f.relative_to(_PROJECT_ROOT))
        for f in package_dir.rglob("*")
        if f.is_file()
    )

    from .storage import get_staged_agent_record, record_staged_agent

    if get_staged_agent_record(spec.id) is None:
        record_staged_agent(spec.id, package_dir)
        logger.info("Recorded staged agent %s in storage.", spec.id)
    else:
        logger.info("Staged agent %s was already recorded in storage.", spec.id)

    files_text = "\n".join(f"- {f}" for f in created)
    risks_summary = ", ".join(spec.risks) or "none"
    logger.info("Created staged agent package %s with risks: %s", spec.id, risks_summary)
    return (
        f"Staged agent package created: {spec.id}\n\n"
        f"Risks flagged: {risks_summary}\n\n"
        f"Files created:\n{files_text}\n\n"
        "Review the package at staging/agents/ before approving. "
        "Do not enable without human approval."
    )


def _copy_progress_adapter(package_dir: Path) -> None:
    """Copy the reviewed self-contained progress adapter into a staged package."""

    if not _PROGRESS_TEMPLATE_DIR.is_dir():
        raise RuntimeError(
            f"Progress adapter template is missing: {_PROGRESS_TEMPLATE_DIR}"
        )
    for source in _PROGRESS_TEMPLATE_DIR.rglob("*"):
        relative = source.relative_to(_PROGRESS_TEMPLATE_DIR)
        if "__pycache__" in relative.parts or source.suffix == ".pyc":
            continue
        target = package_dir / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _factory_thread_id(config: RunnableConfig) -> str:
    configurable = config.get("configurable") if isinstance(config, dict) else None
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise BuildTaskError("Factory thread identity is unavailable; refusing to create a build task")
    return thread_id.strip()


def _staged_package_dir(agent_id: str) -> Path:
    from .agent_spec import VALID_ID_PATTERN

    normalized = agent_id.strip()
    if not VALID_ID_PATTERN.fullmatch(normalized):
        raise BuildTaskError(f"Invalid staged agent id: {agent_id!r}")
    staging_root = _STAGING_DIR.resolve()
    package_dir = (_STAGING_DIR / normalized).resolve()
    try:
        package_dir.relative_to(staging_root)
    except ValueError as exc:
        raise BuildTaskError("staged package resolves outside staging/agents") from exc
    if not package_dir.is_dir():
        raise BuildTaskError(f"Staged agent not found: {normalized!r}")
    return package_dir


@tool
def prepare_agent_build_task(
    agent_id: str,
    permitted_paths: list[str],
    acceptance_criteria: list[str],
    test_commands: list[str],
    relevant_docs: list[str],
    relevant_skills: list[str],
    token_budget: int,
    time_budget_seconds: int,
    stop_conditions: list[str],
    config: RunnableConfig,
) -> str:
    """Validate and persist an explicit Factory implementation handoff.

    All implementation controls are caller-supplied.  This tool has no hidden
    defaults and only writes ``BUILD_TASK.json`` inside the requested staged
    package.  It does not approve, dispatch, execute, or promote the agent.
    """

    thread_id = _factory_thread_id(config)
    package_dir = _staged_package_dir(agent_id)
    raw_manifest, _manifest, digest = load_staged_manifest(package_dir, agent_id.strip())
    design = raw_manifest["design"]
    controls = {
        "agent_id": agent_id.strip(),
        "permitted_paths": permitted_paths,
        "acceptance_criteria": acceptance_criteria,
        "test_commands": test_commands,
        "relevant_docs": relevant_docs,
        "relevant_skills": relevant_skills,
        "token_budget": token_budget,
        "time_budget_seconds": time_budget_seconds,
        "stop_conditions": stop_conditions,
    }
    correlation_id = deterministic_correlation_id(thread_id, {**controls, "manifest_sha256": digest})
    task = AgentBuildTask.model_validate(
        {
            "agent_id": agent_id.strip(),
            "agent_version": raw_manifest["version"],
            "manifest_schema_version": raw_manifest["manifest_schema_version"],
            "manifest_sha256": digest,
            "staging_target": f"staging/agents/{agent_id.strip()}",
            "permitted_paths": permitted_paths,
            "acceptance_criteria": acceptance_criteria,
            "test_commands": test_commands,
            "relevant_docs": relevant_docs,
            "relevant_skills": relevant_skills,
            "token_budget": token_budget,
            "time_budget_seconds": time_budget_seconds,
            "stop_conditions": stop_conditions,
            "runtime_pattern": design["runtime_pattern"],
            "runtime_pattern_reason": design["runtime_pattern_reason"],
            "thread_id": thread_id,
            "correlation_id": correlation_id,
        }
    )
    reference = task_reference(task)
    artifact_path = (package_dir / BUILD_TASK_FILENAME).resolve()
    try:
        artifact_path.relative_to(package_dir.resolve())
    except ValueError as exc:
        raise BuildTaskError("build-task artifact resolves outside staged package") from exc

    from .storage import (
        list_build_tasks_for_reference,
        list_build_tasks_for_thread,
        mark_build_task_status,
        record_build_task,
    )

    reference_rows = list_build_tasks_for_reference(reference)
    exact_row = next(
        (row for row in reference_rows if row["correlation_id"] == task.correlation_id),
        None,
    )
    for row in reference_rows:
        if row["status"] in {"prepared", "approved"} and row["thread_id"] != thread_id:
            raise BuildTaskError(
                "A current build task for this staged artifact belongs to another Factory thread"
            )

    if exact_row is not None and exact_row["status"] == "prepared":
        try:
            existing_task = AgentBuildTask.model_validate(
                json.loads(artifact_path.read_text(encoding="utf-8"))
            )
            if existing_task == task:
                assert_task_matches_staged_package(existing_task, _PROJECT_ROOT)
                return json.dumps(
                    {"status": "prepared", "artifact_reference": reference, "correlation_id": task.correlation_id},
                    sort_keys=True,
                )
        except (OSError, json.JSONDecodeError, ValueError, BuildTaskError):
            mark_build_task_status(
                reference,
                "stale",
                "Artifact or staged package changed before regeneration.",
                correlation_id=exact_row["correlation_id"],
                thread_id=exact_row["thread_id"],
            )
            exact_row["status"] = "stale"

    if exact_row is not None and exact_row["status"] == "approved":
        try:
            approved_task = AgentBuildTask.model_validate(
                json.loads(artifact_path.read_text(encoding="utf-8"))
            )
            assert_task_matches_staged_package(approved_task, _PROJECT_ROOT)
        except (OSError, json.JSONDecodeError, ValueError, BuildTaskError):
            mark_build_task_status(
                reference,
                "stale",
                "Staged package changed; regeneration required.",
                correlation_id=exact_row["correlation_id"],
                thread_id=exact_row["thread_id"],
            )
            exact_row["status"] = "stale"
        else:
            raise BuildTaskError("An approved current build task already exists for this Factory thread")

    if exact_row is not None and exact_row["status"] in {"rejected", "stale", "superseded"}:
        raise BuildTaskError(
            "The exact build-task correlation is terminal; change the staged manifest "
            "or explicit build controls before regeneration"
        )

    for row in list_build_tasks_for_thread(thread_id):
        if row["status"] == "approved":
            try:
                approved_path = _PROJECT_ROOT / row["artifact_reference"]
                approved_task = AgentBuildTask.model_validate(
                    json.loads(approved_path.read_text(encoding="utf-8"))
                )
                assert_task_matches_staged_package(approved_task, _PROJECT_ROOT)
            except (OSError, json.JSONDecodeError, ValueError, BuildTaskError):
                mark_build_task_status(
                    row["artifact_reference"],
                    "stale",
                    "Staged package changed; regeneration required.",
                    correlation_id=row["correlation_id"],
                    thread_id=row["thread_id"],
                )
            else:
                raise BuildTaskError("An approved current build task already exists for this Factory thread")

    for row in reference_rows:
        if row["thread_id"] == thread_id and row["status"] == "prepared" and row["correlation_id"] != task.correlation_id:
            mark_build_task_status(
                reference,
                "superseded",
                "Replaced by an explicit regenerated build task.",
                correlation_id=row["correlation_id"],
                thread_id=row["thread_id"],
            )

    artifact_path.write_text(task.model_dump_json(indent=2) + "\n", encoding="utf-8")
    record_build_task(
        thread_id=thread_id,
        artifact_reference=reference,
        correlation_id=task.correlation_id,
        agent_id=task.agent_id,
        agent_version=task.agent_version,
        manifest_sha256=task.manifest_sha256,
    )
    logger.info("Prepared build task %s for Factory thread %s.", reference, thread_id)
    return json.dumps(
        {"status": "prepared", "artifact_reference": reference, "correlation_id": task.correlation_id},
        sort_keys=True,
    )


@tool
def approve_agent_build_handoff(build_task_reference: str, config: RunnableConfig) -> str:
    """Mark the exact prepared build task approved after HITL middleware approval."""

    thread_id = _factory_thread_id(config)
    reference = build_task_reference.strip()
    expected_prefix = "staging/agents/"
    if not reference.startswith(expected_prefix) or not reference.endswith(f"/{BUILD_TASK_FILENAME}"):
        raise BuildTaskError("build_task_reference must be a staged BUILD_TASK.json repo-relative reference")
    artifact_path = (_PROJECT_ROOT / reference).resolve()
    staging_root = (_PROJECT_ROOT / "staging" / "agents").resolve()
    try:
        artifact_path.relative_to(staging_root)
    except ValueError as exc:
        raise BuildTaskError("build-task reference resolves outside staging/agents") from exc
    if not artifact_path.is_file():
        raise BuildTaskError(f"Build-task artifact not found: {reference}")
    try:
        task = AgentBuildTask.model_validate(json.loads(artifact_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BuildTaskError(f"Invalid build-task artifact: {reference}") from exc
    if task.thread_id != thread_id or task_reference(task) != reference:
        raise BuildTaskError("build-task correlation does not match the current Factory thread")
    assert_task_matches_staged_package(task, _PROJECT_ROOT)
    from .storage import get_build_task, mark_build_task_approved

    row = get_build_task(
        reference,
        correlation_id=task.correlation_id,
        thread_id=thread_id,
    )
    if not row or row["thread_id"] != thread_id or row["status"] != "prepared":
        raise BuildTaskError("build task is missing, already decided, or not prepared for this thread")
    if not mark_build_task_approved(
        thread_id=thread_id,
        artifact_reference=reference,
        correlation_id=task.correlation_id,
    ):
        raise BuildTaskError("build task approval was not applied atomically")
    logger.info("Approved build task %s for Factory thread %s.", reference, thread_id)
    return json.dumps(
        {"status": "approved", "artifact_reference": reference, "correlation_id": task.correlation_id},
        sort_keys=True,
    )


@tool
def record_decision(note: str) -> str:
    """Record a durable project decision in memory/factory/decisions.md.

    Use only for decisions that have been reviewed and explicitly approved.
    """
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    decisions_file = _MEMORY_DIR / "decisions.md"
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
    entry = f"\n## {timestamp}\n\n{note.strip()}\n"
    logger.info("Recording decision in %s.", decisions_file)
    with decisions_file.open("a", encoding="utf-8") as f:
        f.write(entry)
    return "Decision recorded in memory/factory/decisions.md."


@tool
def request_approval(summary: str) -> str:
    """Record a pending approval request in the database.

    Use before: promoting a staged agent, enabling permissions, modifying shared memory.
    A human must respond via Telegram /approve <id> or /reject <id> before the action proceeds.
    """
    from .storage import create_approval

    logger.info("Creating general approval request.")
    approval_id = create_approval(
        approval_type="general",
        target_id="factory",
        summary=summary.strip(),
    )
    return (
        f"Approval request #{approval_id} recorded.\n"
        "A human must approve before this action proceeds.\n"
        "Use /pending in Telegram to see it, then /approve or /reject."
    )


@tool
def request_agent_promotion(agent_id: str) -> str:
    """Request approval to promote a staged agent to the enabled registry.

    The agent must exist in staging/agents/. A human must approve via Telegram /approve <id>.
    Do not call this until the staged package has been reviewed.
    """
    from .storage import create_approval

    logger.info("Requesting promotion approval for staged agent %s.", agent_id)
    try:
        catalog = build_agent_catalog(
            enabled_dir=_PROJECT_ROOT / "config" / "agents",
            staging_dir=_STAGING_DIR,
        )
    except AgentFactoryError as exc:
        logger.warning("Unable to inspect agent catalog for promotion: %s", exc)
        return f"Unable to inspect agent inventory: {exc}"
    entry = catalog.get(agent_id.strip())
    if not entry:
        logger.warning("Staged agent not found for promotion request: %s", agent_id)
        return f"Staged agent not found: {agent_id!r}. Create it first with create_staged_agent_package."
    if "enabled" in entry.statuses:
        logger.info("Staged agent %s is already enabled.", agent_id)
        return f"Agent {agent_id!r} is already enabled."

    package_dir = _STAGING_DIR / agent_id.strip()
    review_file = package_dir / "REVIEW.md"
    review_summary = ""
    if review_file.exists():
        review_summary = review_file.read_text(encoding="utf-8")[:400]

    approval_id = create_approval(
        approval_type="promote-agent",
        target_id=agent_id.strip(),
        summary=(
            f"Promote staged agent '{agent_id}' to config/agents/.\n\n"
            f"Review summary:\n{review_summary}"
        ),
    )
    logger.info("Promotion approval %s created for staged agent %s.", approval_id, agent_id)
    return (
        f"Promotion request #{approval_id} created for agent '{agent_id}'.\n"
        f"Use /approve {approval_id} in Telegram to enable it, or /reject {approval_id} to cancel."
    )


def get_factory_tools() -> list:
    """Return the list of factory tool instances for the Factory Brain.

    read_project_doc is excluded — FilesystemBackend handles file reads natively.
    """
    return [
        list_templates,
        list_staged_agents,
        list_known_agents,
        list_registered_tool_ids,
        read_staged_review,
        validate_agent_package_spec,
        create_staged_agent_package,
        prepare_agent_build_task,
        approve_agent_build_handoff,
        record_decision,
        request_design_research,
        run_design_research,
        request_agent_promotion,
        request_approval,
    ]
