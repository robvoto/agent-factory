"""Bounded LangGraph workflow for creating staged agent packages."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TypedDict

from .agent_spec import AgentDesignConfig
from .package_scaffold import copy_standard_workspace
from .routing_purpose import build_routing_purpose

PROJECT_ROOT = Path.cwd()
TEMPLATE_DIR = PROJECT_ROOT / "templates" / "agent-package"
STAGING_DIR = PROJECT_ROOT / "staging" / "agents"
logger = logging.getLogger(__name__)


class AgentCreationState(TypedDict, total=False):
    request: str
    agent_id: str
    agent_name: str
    agent_alias: str
    agent_purpose: str
    package_dir: str
    runtime_pattern: str
    runtime_pattern_reason: str
    risks: list[str]
    created_files: list[str]
    status: str


def build_agent_creator_graph():
    """Build the LangGraph workflow.

    This intentionally uses a deterministic workflow first.
    No LLM call is made yet, so testing is safe and free.
    """

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is not installed. Run: bash scripts/wsl/setup.sh"
        ) from exc

    graph = StateGraph(AgentCreationState)
    graph.add_node("draft", draft_agent_identity)
    graph.add_node("risk_review", risk_review)
    graph.add_node("scaffold", scaffold_agent_package)
    graph.add_node("finish", finish)

    graph.add_edge(START, "draft")
    graph.add_edge("draft", "risk_review")
    graph.add_edge("risk_review", "scaffold")
    graph.add_edge("scaffold", "finish")
    graph.add_edge("finish", END)

    return graph.compile()


def create_staged_agent_package(
    request: str,
    *,
    runtime_pattern: str,
    runtime_pattern_reason: str,
) -> AgentCreationState:
    """Create a staged agent package from a plain-language request."""

    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Agent request cannot be empty.")
    design = AgentDesignConfig(
        runtime_pattern=runtime_pattern,
        runtime_pattern_reason=runtime_pattern_reason,
    )

    logger.info("Creating staged agent package from request: %s", clean_request)
    graph = build_agent_creator_graph()
    result = graph.invoke(
        {
            "request": clean_request,
            "runtime_pattern": design.runtime_pattern,
            "runtime_pattern_reason": design.runtime_pattern_reason,
        }
    )
    logger.info("Created staged agent package: %s", result.get("agent_id", "<unknown>"))
    return dict(result)


def draft_agent_identity(state: AgentCreationState) -> AgentCreationState:
    request = state["request"].strip()
    logger.debug("Drafting agent identity from request: %s", request)

    base = request.lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    words = [word for word in base.split("-") if word]

    if not words:
        words = ["new", "agent"]

    short_words = words[:4]
    agent_id = "-".join(short_words)
    if not agent_id.endswith("agent"):
        agent_id = f"{agent_id}-agent"

    agent_name = " ".join(word.capitalize() for word in agent_id.split("-"))
    agent_alias = agent_id.replace("-agent", "") or agent_id
    logger.info("Drafted agent identity %s (%s).", agent_id, agent_name)

    return {
        **state,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agent_alias": agent_alias,
        "agent_purpose": build_routing_purpose(
            primary=request,
            select_for=f"Requests that directly require: {request}",
            do_not_select_for="Requests outside this stated responsibility.",
        ),
        "package_dir": str(STAGING_DIR / agent_id),
    }


def risk_review(state: AgentCreationState) -> AgentCreationState:
    request = state["request"].lower()
    risks: list[str] = []

    risk_terms = {
        "network": ["internet", "web", "online", "browser", "scrape", "api"],
        "filesystem": ["file", "folder", "repo", "repository", "write", "delete"],
        "shell": ["terminal", "shell", "command", "bash", "powershell"],
        "memory": ["remember", "memory", "store", "learn"],
        "long_running": ["daily", "schedule", "background", "unattended", "always"],
    }

    for risk, terms in risk_terms.items():
        if any(term in request for term in terms):
            risks.append(risk)

    if not risks:
        risks.append("none_detected")
    logger.info("Risk review for %s: %s", state.get("agent_id", "<unknown>"), ", ".join(risks))

    return {**state, "risks": risks}


def scaffold_agent_package(state: AgentCreationState) -> AgentCreationState:
    package_dir = Path(state["package_dir"])
    if package_dir.exists():
        logger.info("Reusing existing staged agent package at %s.", package_dir)
        created_files = [
            str(path.relative_to(PROJECT_ROOT))
            for path in sorted(package_dir.rglob("*"))
            if path.is_file()
        ]
        return {**state, "created_files": created_files, "status": "reused"}

    logger.info("Scaffolding staged agent package at %s.", package_dir)
    package_dir.mkdir(parents=True, exist_ok=False)

    created_files: list[str] = []
    replacements = {
        "agent_id": state["agent_id"],
        "agent_name": state["agent_name"],
        "agent_alias": state["agent_alias"],
        "agent_purpose": state["agent_purpose"],
        "project_root_required": "False",
    }

    replacements["runtime_pattern"] = state["runtime_pattern"]
    replacements["runtime_pattern_reason"] = state["runtime_pattern_reason"]
    replacements["agent_purpose"] = state["agent_purpose"]
    copy_standard_workspace(TEMPLATE_DIR, package_dir, replacements)
    created_files.extend(
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted(package_dir.rglob("*"))
        if path.is_file()
    )

    write_review_file(package_dir, state)
    created_files.append(str((package_dir / "REVIEW.md").relative_to(PROJECT_ROOT)))
    logger.info("Staged agent package scaffolded at %s.", package_dir)

    return {**state, "created_files": created_files}


def write_review_file(package_dir: Path, state: AgentCreationState) -> None:
    risks = "\n".join(f"- {risk}" for risk in state.get("risks", []))
    files = "\n".join(f"- {file}" for file in state.get("created_files", []))

    content = f"""# Agent Draft Review

Status: staged draft only.

This agent is not enabled.

## Request

```text
{state['request']}
```

## Draft identity

- ID: `{state['agent_id']}`
- Name: `{state['agent_name']}`
- Alias: `{state['agent_alias']}`

## Runtime design

- Pattern: `{state['runtime_pattern']}`
- Reason: {state['runtime_pattern_reason']}

## Risks detected

{risks}

## Created files

{files if files else '- Pending'}

## Approval rule

Do not promote this agent until approved. Promotion releases the full package
under `agents/<id>/` and writes the Hub-facing registry entry to
`config/agents/<id>.json` from that released package.
"""
    (package_dir / "REVIEW.md").write_text(content, encoding="utf-8", newline="\n")
    logger.debug("Wrote REVIEW.md for %s.", package_dir.name)


def finish(state: AgentCreationState) -> AgentCreationState:
    logger.info("Finished staging agent %s.", state.get("agent_id", "<unknown>"))
    return {**state, "status": state.get("status", "staged")}


def to_json(state: AgentCreationState) -> str:
    return json.dumps(state, indent=2)
