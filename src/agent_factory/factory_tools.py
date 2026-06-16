"""Bounded tool functions exposed to the Factory Brain.

These are the only actions the Factory Brain may take directly.
No shell, no network, no unrestricted filesystem write.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from .agent_catalog import build_agent_catalog, describe_agent_catalog, plan_package_reuse
from .errors import AgentFactoryError
from .agent_spec import AgentPackageSpec

_PROJECT_ROOT = Path(__file__).parents[2]
_STAGING_DIR = _PROJECT_ROOT / "staging" / "agents"
_MEMORY_DIR = _PROJECT_ROOT / "memory" / "factory"
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"
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
def create_staged_agent_package(spec_json: str) -> str:
    """Create a staged agent package from a validated JSON spec.

    The spec must be a JSON object with these fields:
      id         - lowercase identifier, e.g. "research-agent"
      name       - human-readable name, e.g. "Research Agent"
      purpose    - what this agent does
      aliases    - list of command aliases, e.g. ["research", "find"]
      tools      - list of approved tool IDs (may be empty)
      permissions - object: network, filesystem, shell, requires_approval
      memory_policy - object: scope, retention
      risks      - list of risk labels (auto-populated from permissions)
      tests      - list of test descriptions

    Returns a summary of created files or an error message.
    """
    from pydantic import ValidationError

    try:
        raw = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON supplied for staged agent creation: %s", exc)
        return f"Invalid JSON in spec: {exc}"

    try:
        spec = AgentPackageSpec.model_validate(raw)
    except ValidationError as exc:
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

    package_dir = _STAGING_DIR / spec.id
    logger.info("Creating staged agent package for %s at %s.", spec.id, package_dir)
    package_dir.mkdir(parents=True, exist_ok=False)

    (package_dir / "agent.json").write_text(
        json.dumps(
            {
                "id": spec.id,
                "name": spec.name,
                "aliases": spec.aliases,
                "tools": spec.tools,
                "permissions": spec.permissions.model_dump(),
                "memory": spec.memory_policy.model_dump(),
                "runtime": {"mode": "manual", "entrypoint": None},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (package_dir / "SYSTEM.md").write_text(
        f"# {spec.name} System Prompt\n\n"
        f"You are {spec.name}.\n\n"
        f"Purpose:\n\n```text\n{spec.purpose}\n```\n\n"
        "Operating rules:\n\n"
        "- Stay within the approved tools and permissions.\n"
        "- Ask for clarification when the task is ambiguous.\n"
        "- Stop before risky or destructive actions.\n"
        "- Report what you did and what remains uncertain.\n"
        "- Do not modify your own files or permissions.\n",
        encoding="utf-8",
    )

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
        "Do not move to `config/agents` without human approval.\n",
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
        f"## Risks\n\n{risks_text}\n\n"
        f"## Tests\n\n{tests_text}\n\n"
        "## Approval rule\n\n"
        "Do not copy this agent into `config/agents` until a human approves it.\n",
        encoding="utf-8",
    )
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


@tool
def record_decision(note: str) -> str:
    """Record a durable project decision in memory/factory/decisions.md.

    Use only for decisions that have been reviewed and explicitly approved.
    """
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    decisions_file = _MEMORY_DIR / "decisions.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        read_staged_review,
        create_staged_agent_package,
        record_decision,
        request_agent_promotion,
        request_approval,
    ]
