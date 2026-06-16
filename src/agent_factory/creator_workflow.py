"""Bounded LangGraph workflow for creating staged agent packages."""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from string import Template
from typing import TypedDict

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


def create_staged_agent_package(request: str) -> AgentCreationState:
    """Create a staged agent package from a plain-language request."""

    clean_request = request.strip()
    if not clean_request:
        raise ValueError("Agent request cannot be empty.")

    logger.info("Creating staged agent package from request: %s", clean_request)
    graph = build_agent_creator_graph()
    result = graph.invoke({"request": clean_request})
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
        "agent_purpose": request,
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
    }

    for template_file in TEMPLATE_DIR.rglob("*"):
        relative = template_file.relative_to(TEMPLATE_DIR)
        target = package_dir / relative

        if template_file.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        if template_file.name == ".gitkeep":
            shutil.copyfile(template_file, target)
        else:
            text = template_file.read_text(encoding="utf-8")
            rendered = render_template(text, replacements)
            target.write_text(rendered, encoding="utf-8", newline="\n")

        created_files.append(str(target.relative_to(PROJECT_ROOT)))

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

## Risks detected

{risks}

## Created files

{files if files else '- Pending'}

## Approval rule

Do not copy this agent into `config/agents` until approved.
"""
    (package_dir / "REVIEW.md").write_text(content, encoding="utf-8", newline="\n")
    logger.debug("Wrote REVIEW.md for %s.", package_dir.name)


def finish(state: AgentCreationState) -> AgentCreationState:
    logger.info("Finished staging agent %s.", state.get("agent_id", "<unknown>"))
    return {**state, "status": state.get("status", "staged")}


def render_template(text: str, replacements: dict[str, str]) -> str:
    # Existing templates use {{name}} style, so normalize to Template style.
    normalized = text
    for key in replacements:
        normalized = normalized.replace("{{" + key + "}}", "${" + key + "}")
    return Template(normalized).safe_substitute(replacements)


def to_json(state: AgentCreationState) -> str:
    return json.dumps(state, indent=2)
