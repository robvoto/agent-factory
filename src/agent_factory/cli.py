"""Command line interface for Agent Factory."""

from __future__ import annotations

import argparse
import logging
import json
import sys
from pathlib import Path

from .loader import load_registry
from .router import AgentRouter
from .factory_settings import get_model_defaults, list_model_aliases
from .logging_utils import configure_logging


PROJECT_ROOT = Path(__file__).parents[2]
DEFAULT_AGENTS_DIR = PROJECT_ROOT / "config" / "agents"
DEFAULT_TOOLS_FILE = PROJECT_ROOT / "config" / "tools.json"
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    log_level = _extract_log_level(raw_argv)

    parser = argparse.ArgumentParser(prog="agent-factory")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser("list", help="List configured agents")
    subparsers.add_parser("langchain-check", help="Check LangChain agent harness availability")
    subparsers.add_parser("models", help="List available AI model aliases and defaults")
    telegram_parser = subparsers.add_parser("telegram", help="Start Telegram gateway")
    telegram_parser.add_argument("bot_name", nargs="?", default=None, help="Bot name from config/factory_settings.json (default: first bot)")
    telegram_parser.add_argument("--purpose", default="general", choices=["general", "coding"], help="Default AI purpose for this Telegram session.")
    telegram_parser.add_argument("--model", default=None, help="Override the default AI model alias or literal model string.")
    subparsers.add_parser("pending", help="List pending approvals")
    subparsers.add_parser("staged", help="List staged agent drafts")

    create_parser = subparsers.add_parser("create", help="Create a staged agent package (deterministic)")
    create_parser.add_argument("request", help="Plain-language agent request")

    factory_parser = subparsers.add_parser("factory", help="Invoke the Factory Brain (requires OPENAI_API_KEY)")
    factory_parser.add_argument("request", help="Plain-language factory request")
    factory_parser.add_argument("--purpose", default="coding", choices=["general", "coding"], help="Default AI purpose for this request.")
    factory_parser.add_argument("--model", default=None, help="Override the default AI model alias or literal model string.")

    approve_parser = subparsers.add_parser("approve", help="Approve a pending action by ID")
    approve_parser.add_argument("approval_id", type=int, help="Approval ID from 'pending'")

    reject_parser = subparsers.add_parser("reject", help="Reject a pending action by ID")
    reject_parser.add_argument("approval_id", type=int, help="Approval ID from 'pending'")
    reject_parser.add_argument("reason", nargs="?", default="Rejected via CLI", help="Rejection reason")

    promote_parser = subparsers.add_parser("promote", help="Request promotion approval for a staged agent")
    promote_parser.add_argument("agent_id", help="Staged agent ID to promote")

    delete_parser = subparsers.add_parser("delete", help="Delete a staged or enabled agent")
    delete_parser.add_argument("agent_id", help="Agent ID to delete")

    route_parser = subparsers.add_parser("route", help="Route an agent command")
    route_parser.add_argument("route_command", help="Command such as /agent alias message")

    args = parser.parse_args(raw_argv)
    configure_logging(log_level or args.log_level)
    logger.info("Starting agent-factory CLI command: %s", args.subcommand)

    if args.subcommand == "langchain-check":
        from .langchain_runtime import ensure_langchain_available

        logger.debug("Checking LangChain harness availability.")
        ensure_langchain_available()
        logger.info("LangChain is available.")
        print("LangChain available: create_agent import OK.")
        return 0

    if args.subcommand == "telegram":
        from .telegram_gateway import run_telegram_gateway

        logger.info("Starting Telegram gateway from CLI.")
        run_telegram_gateway(
            bot_name=getattr(args, "bot_name", None),
            purpose=getattr(args, "purpose", "general"),
            default_model=getattr(args, "model", None),
        )
        return 0

    if args.subcommand == "create":
        from .creator_workflow import create_staged_agent_package, to_json

        logger.info("Creating a staged agent package from CLI request.")
        result = create_staged_agent_package(args.request)
        logger.info("Created staged agent draft: %s", result.get("agent_id", "<unknown>"))
        print(to_json(result))
        return 0

    if args.subcommand == "factory":
        from .factory_brain import invoke_factory_brain

        logger.info("Invoking Factory Brain from CLI.")
        response = invoke_factory_brain(
            args.request,
            model=getattr(args, "model", None),
            purpose=getattr(args, "purpose", "coding"),
        )
        print(response)
        return 0

    if args.subcommand == "models":
        defaults = get_model_defaults()
        aliases = list_model_aliases()
        print(f"Default general model: {defaults['general']}")
        print(f"Default coding model: {defaults['coding']}")
        if not aliases:
            print("No model aliases configured.")
            return 0
        print("Aliases:")
        for alias, target in sorted(aliases.items()):
            print(f"{alias}\t{target}")
        return 0

    if args.subcommand == "staged":
        from .storage import list_staged_agent_records

        logger.debug("Listing staged agent drafts.")
        records = list_staged_agent_records()
        if not records:
            print("No staged agent drafts.")
            return 0
        for r in records:
            print(f"{r['agent_id']}\t{r['status']}\t{r['created_at']}")
        return 0

    if args.subcommand == "pending":
        from .storage import list_pending_approvals

        logger.debug("Listing pending approvals.")
        records = list_pending_approvals()
        if not records:
            print("No pending approvals.")
            return 0
        for r in records:
            print(f"[{r['id']}] {r['approval_type']} / {r['target_id']}")
            print(f"    {r['summary'][:120]}")
        return 0

    if args.subcommand == "approve":
        from .storage import decide_approval, get_approval

        logger.info("Approving pending action %s.", args.approval_id)
        record = get_approval(args.approval_id)
        if not record:
            logger.warning("Approval %s was not found.", args.approval_id)
            print(f"Approval {args.approval_id} not found.")
            return 1
        if record["status"] != "pending":
            logger.warning("Approval %s is already %s.", args.approval_id, record["status"])
            print(f"Approval {args.approval_id} is already {record['status']}.")
            return 1
        decide_approval(args.approval_id, "approved", "Approved via CLI")
        if record["approval_type"] == "promote-agent":
            result = _promote_agent(record["target_id"])
            logger.info("Approval %s promoted staged agent %s.", args.approval_id, record["target_id"])
            print(result)
        else:
            logger.info("Approval %s approved.", args.approval_id)
            print(f"Approval {args.approval_id} approved.")
        return 0

    if args.subcommand == "reject":
        from .storage import decide_approval, get_approval

        logger.info("Rejecting pending action %s.", args.approval_id)
        record = get_approval(args.approval_id)
        if not record:
            logger.warning("Approval %s was not found.", args.approval_id)
            print(f"Approval {args.approval_id} not found.")
            return 1
        if record["status"] != "pending":
            logger.warning("Approval %s is already %s.", args.approval_id, record["status"])
            print(f"Approval {args.approval_id} is already {record['status']}.")
            return 1
        decide_approval(args.approval_id, "rejected", args.reason)
        logger.info("Approval %s rejected: %s", args.approval_id, args.reason)
        print(f"Approval {args.approval_id} rejected. Reason: {args.reason}")
        return 0

    if args.subcommand == "promote":
        from .factory_tools import request_agent_promotion

        logger.info("Requesting promotion approval for staged agent %s.", args.agent_id)
        result = request_agent_promotion.invoke({"agent_id": args.agent_id})
        print(result)
        return 0

    if args.subcommand == "delete":
        from .telegram_gateway import _delete_agent

        logger.info("Deleting agent %s.", args.agent_id)
        print(_delete_agent(args.agent_id))
        return 0

    allowed_tools = load_allowed_tools(DEFAULT_TOOLS_FILE)
    registry = load_registry(DEFAULT_AGENTS_DIR, allowed_tool_ids=allowed_tools)

    if args.subcommand == "list":
        logger.debug("Listing enabled agents.")
        agents = registry.list_agents()
        if not agents:
            print("No agents configured.")
            return 0
        for agent in agents:
            aliases = ", ".join(agent.aliases)
            print(f"{agent.id}\t{agent.name}\t{aliases}")
        return 0

    if args.subcommand == "route":
        logger.info("Routing command through enabled agents: %s", args.route_command)
        result = AgentRouter(registry).route(args.route_command)
        print(f"{result.agent.id}: {result.message}")
        return 0

    return 1


def _promote_agent(agent_id: str) -> str:
    """Promote a staged agent to config/agents/ and mark it enabled."""
    from .agent_catalog import promote_agent

    logger.info("Promoting staged agent %s into config/agents.", agent_id)
    result = promote_agent(agent_id, project_root=PROJECT_ROOT)
    logger.info("Promotion result for %s: %s", agent_id, result)
    return result


def load_allowed_tools(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        return ()
    allowed: list[str] = []
    for item in tools:
        if isinstance(item, str):
            allowed.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            allowed.append(item["id"])
    return tuple(allowed)


def _extract_log_level(argv: list[str]) -> str | None:
    """Remove --log-level from argv so it can appear before or after subcommands."""
    for index, arg in enumerate(list(argv)):
        if arg == "--log-level":
            if index + 1 >= len(argv):
                raise SystemExit("agent-factory: error: --log-level requires a value")
            value = argv[index + 1]
            del argv[index : index + 2]
            return value
        if arg.startswith("--log-level="):
            value = arg.split("=", 1)[1]
            del argv[index]
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
