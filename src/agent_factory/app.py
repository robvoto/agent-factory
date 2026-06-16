"""Local web app for the Agent Factory Platform."""

from __future__ import annotations

import argparse
import html
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .cli import load_allowed_tools
from .creator_workflow import create_staged_agent_package
from .logging_utils import configure_logging
from .loader import load_registry
from .router import AgentRouter

PROJECT_ROOT = Path.cwd()
DEFAULT_AGENTS_DIR = PROJECT_ROOT / "config" / "agents"
DEFAULT_TOOLS_FILE = PROJECT_ROOT / "config" / "tools.json"
STAGING_DIR = PROJECT_ROOT / "staging" / "agents"
logger = logging.getLogger(__name__)


class AgentFactoryApp(BaseHTTPRequestHandler):
    server_version = "AgentFactoryPlatform/0.2"

    def do_GET(self) -> None:  # noqa: N802 - http.server convention
        parsed = urlparse(self.path)
        logger.debug("HTTP GET %s from %s", parsed.path, self.client_address[0])

        if parsed.path == "/health":
            self._send_json({"status": "ok", "app": "agent-factory-platform"})
            return

        if parsed.path == "/agents":
            self._send_json(self._agents_payload())
            return

        if parsed.path == "/staged-agents":
            self._send_json(self._staged_agents_payload())
            return

        if parsed.path == "/route":
            params = parse_qs(parsed.query)
            command = params.get("command", [""])[0].strip()
            logger.info("Rendering route request for command: %s", command or "<empty>")
            self._send_html(self._route_page(command))
            return

        if parsed.path == "/create-agent":
            params = parse_qs(parsed.query)
            request = params.get("request", [""])[0].strip()
            logger.info("Rendering staged agent creation request: %s", request or "<empty>")
            self._send_html(self._create_agent_page(request))
            return

        if parsed.path in {"/", "/index.html"}:
            logger.debug("Rendering home page.")
            self._send_html(self._home_page())
            return

        logger.warning("No route matched HTTP path %s", parsed.path)
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _registry(self):
        allowed_tools = load_allowed_tools(DEFAULT_TOOLS_FILE)
        return load_registry(DEFAULT_AGENTS_DIR, allowed_tool_ids=allowed_tools)

    def _agents_payload(self) -> dict[str, object]:
        registry = self._registry()
        agents = [
            {
                "id": agent.id,
                "name": agent.name,
                "aliases": list(agent.aliases),
                "tools": list(agent.tools),
            }
            for agent in registry.list_agents()
        ]
        return {"agents": agents, "count": len(agents)}

    def _staged_agents_payload(self) -> dict[str, object]:
        staged = []
        if STAGING_DIR.exists():
            for path in sorted(STAGING_DIR.iterdir()):
                if not path.is_dir():
                    continue
                staged.append(
                    {
                        "id": path.name,
                        "path": str(path.relative_to(PROJECT_ROOT)),
                        "review_file": str((path / "REVIEW.md").relative_to(PROJECT_ROOT))
                        if (path / "REVIEW.md").exists()
                        else None,
                    }
                )
        return {"staged_agents": staged, "count": len(staged)}

    def _home_page(self) -> str:
        payload = self._agents_payload()
        staged_payload = self._staged_agents_payload()
        agents = payload["agents"]
        staged_agents = staged_payload["staged_agents"]

        agent_rows = []
        for agent in agents:
            aliases = ", ".join(agent["aliases"])
            tools = ", ".join(agent["tools"]) or "none"
            agent_rows.append(
                "<tr>"
                f"<td>{html.escape(agent['id'])}</td>"
                f"<td>{html.escape(agent['name'])}</td>"
                f"<td>{html.escape(aliases)}</td>"
                f"<td>{html.escape(tools)}</td>"
                "</tr>"
            )
        agent_table = "".join(agent_rows) if agent_rows else "<tr><td colspan='4'>No approved agents configured yet.</td></tr>"

        staged_rows = []
        for staged in staged_agents:
            staged_rows.append(
                "<tr>"
                f"<td>{html.escape(staged['id'])}</td>"
                f"<td><code>{html.escape(staged['path'])}</code></td>"
                f"<td><code>{html.escape(staged['review_file'] or '')}</code></td>"
                "</tr>"
            )
        staged_table = "".join(staged_rows) if staged_rows else "<tr><td colspan='3'>No staged agent drafts yet.</td></tr>"

        return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Factory Platform</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f7f7f7; color: #222; }}
    main {{ max-width: 1100px; margin: auto; background: white; padding: 2rem; border-radius: 12px; }}
    h1 {{ margin-top: 0; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin: 1rem 0; background: #fafafa; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #ddd; text-align: left; padding: 0.6rem; vertical-align: top; }}
    input[type=text] {{ width: 75%; padding: 0.6rem; }}
    button {{ padding: 0.65rem 1rem; cursor: pointer; }}
    code, pre {{ background: #eee; padding: 0.1rem 0.3rem; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Agent Factory Platform</h1>
  <p>Local WSL-first app for creating, running, and improving approved agent packages.</p>

  <section class="card">
    <h2>Status</h2>
    <p>App is running.</p>
    <p>Approved agents: <strong>{payload['count']}</strong></p>
    <p>Staged drafts: <strong>{staged_payload['count']}</strong></p>
  </section>

  <section class="card">
    <h2>Factory: create staged agent</h2>
    <form action="/create-agent" method="get">
      <input type="text" name="request" placeholder="Create an agent that researches LangChain docs safely">
      <button type="submit">Create staged draft</button>
    </form>
    <p>This uses the bounded LangGraph creator workflow. It creates a staged package only. It does not enable the agent.</p>
  </section>

  <section class="card">
    <h2>Staged agent drafts</h2>
    <table>
      <thead><tr><th>ID</th><th>Path</th><th>Review</th></tr></thead>
      <tbody>{staged_table}</tbody>
    </table>
  </section>

  <section class="card">
    <h2>Approved agents</h2>
    <table>
      <thead><tr><th>ID</th><th>Name</th><th>Aliases</th><th>Tools</th></tr></thead>
      <tbody>{agent_table}</tbody>
    </table>
  </section>

  <section class="card">
    <h2>Runtime: route command</h2>
    <form action="/route" method="get">
      <input type="text" name="command" placeholder="/agent alias message">
      <button type="submit">Run route</button>
    </form>
    <p>Until an agent is approved and enabled, routing fails closed.</p>
  </section>
</main>
</body>
</html>
"""

    def _create_agent_page(self, request: str) -> str:
        if not request:
            result = "No request entered."
            status = "Not created"
            logger.info("No agent request supplied to the web form.")
        else:
            try:
                state = create_staged_agent_package(request)
                status = "Created staged agent draft"
                result = json.dumps(state, indent=2)
                logger.info("Created staged agent draft %s from web request.", state.get("agent_id", "<unknown>"))
            except Exception as exc:
                status = "Creation failed"
                result = str(exc)
                logger.exception("Failed to create staged agent from web request: %s", request)

        return f"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Create Agent</title></head>
<body style="font-family: Arial, sans-serif; margin: 2rem;">
  <h1>{html.escape(status)}</h1>
  <p><strong>Request:</strong> {html.escape(request)}</p>
  <pre>{html.escape(result)}</pre>
  <p><a href="/">Back</a></p>
</body>
</html>
"""

    def _route_page(self, command: str) -> str:
        if not command:
            result = "No command entered."
            logger.info("No route command supplied to the web form.")
        else:
            try:
                registry = self._registry()
                routed = AgentRouter(registry).route(command)
                result = f"{routed.agent.id}: {routed.message}"
                logger.info("Web route resolved command to agent %s.", routed.agent.id)
            except Exception as exc:
                result = f"Route failed: {exc}"
                logger.exception("Failed to route web command: %s", command)

        return f"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Agent Factory Route</title></head>
<body style="font-family: Arial, sans-serif; margin: 2rem;">
  <h1>Route result</h1>
  <p><strong>Command:</strong> {html.escape(command)}</p>
  <pre>{html.escape(result)}</pre>
  <p><a href="/">Back</a></p>
</body>
</html>
"""

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_app(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    log_level: str | int | None = None,
) -> None:
    if log_level is not None or not logging.getLogger().handlers:
        configure_logging(log_level)
    server = ThreadingHTTPServer((host, port), AgentFactoryApp)
    logger.info("Agent Factory Platform app running at http://%s:%s/", host, port)
    logger.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Agent Factory Platform app.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-factory-app")
    parser.add_argument(
        "--log-level",
        default=None,
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    run_app(host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
