"""Agent Hub subprocess adapter for the staged Shopping Agent."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from specialist_contract import adapt_universal_task  # noqa: E402
from shopping_agent.providers import create_shopping_providers  # noqa: E402
from shopping_agent.workflow import (  # noqa: E402
    ShoppingConfig,
    run_shopping_workflow,
)


_LIMIT_ENV = {
    "max_api_calls": "SHOPPING_MAX_API_CALLS",
    "max_page_fetches": "SHOPPING_MAX_PAGE_FETCHES",
    "timeout_seconds": "SHOPPING_TIMEOUT_SECONDS",
}


def _required_nonnegative_int(name: str) -> int:
    value = os.getenv(name, "").strip()
    if not value or not value.isdecimal():
        raise ValueError(name)
    return int(value)


def _required_positive_float(name: str) -> float:
    value = os.getenv(name, "").strip()
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(name) from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(name)
    return parsed


def process_payload(payload: Any) -> dict[str, str]:
    """Validate Hub's envelope and return one standard Hub terminal result."""
    try:
        task = adapt_universal_task(payload)
    except (TypeError, ValueError, KeyError):
        return {"status": "failed", "summary": "Shopping task envelope validation failed."}

    try:
        max_api_calls = _required_nonnegative_int(_LIMIT_ENV["max_api_calls"])
        max_page_fetches = _required_nonnegative_int(_LIMIT_ENV["max_page_fetches"])
        timeout_seconds = _required_positive_float(_LIMIT_ENV["timeout_seconds"])
    except ValueError as exc:
        missing = str(exc) or "operational limit"
        return {
            "status": "failed",
            "summary": (
                "Shopping candidate is connected to Agent Hub, but its runtime is not configured. "
                f"Set {missing} in the Hub test process; no operational defaults are invented."
            ),
        }

    try:
        providers = create_shopping_providers(
            os.environ.get("SERPAPI_KEY"), timeout_seconds=timeout_seconds
        )
        result = run_shopping_workflow(
            task["task"],
            providers,
            ShoppingConfig(
                max_search_calls=3,
                max_api_calls=max_api_calls,
                max_page_fetches=max_page_fetches,
            ),
            request_id=task.get("request_id"),
            run_id=task.get("run_id"),
        )
    except Exception:
        # Do not pass provider, task, or environment details into Hub logs.
        return {"status": "failed", "summary": "Shopping workflow failed; inspect redacted agent telemetry."}

    workflow_status = result.get("status") if isinstance(result, dict) else None
    if workflow_status == "needs_clarification":
        return {
            "status": "needs_clarification",
            "summary": " ".join(result["clarification_questions"]),
        }
    return {
        "status": "success" if workflow_status == "completed" else "failed",
        "summary": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    output_path = Path(args.output_json)
    try:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        result = process_payload(payload)
    except (OSError, json.JSONDecodeError):
        result = {"status": "failed", "summary": "Shopping Hub adapter could not read its input."}
    try:
        output_path.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        print("Could not write result JSON.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
