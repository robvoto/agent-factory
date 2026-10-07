"""JSON subprocess/manual entrypoint for the staged Shopping Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from .settings import ShoppingConfig
from .workflow import default_dependencies, new_telemetry, run_shopping


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the staged Shopping Agent MVP.")
    parser.add_argument("--task", help="Natural-language shopping request.")
    parser.add_argument("--postcode", help="Destination postcode for delivery verification.")
    parser.add_argument("--input-json", type=Path, help="Agent Hub universal task envelope.")
    parser.add_argument("--output-json", type=Path, help="Where to write the structured result.")
    return parser.parse_args()


def _failure_result(message: str, *, request_id: str, run_id: str) -> dict[str, Any]:
    telemetry = new_telemetry(request_id, run_id)
    telemetry.finish(
        stop_reason="failed",
        now_iso=telemetry.started_at,
        monotonic_now=telemetry._started_monotonic,
    )
    return {
        "status": "failed",
        "result_kind": "shopping_result",
        "summary": message,
        "constraints": None,
        "shortlist": [],
        "unverified_candidates": [],
        "failed_candidates": [],
        "telemetry": telemetry.to_dict(),
    }


def main() -> int:
    args = _args()
    payload: dict[str, Any] = {}
    if args.input_json:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        task = payload.get("task")
        request_id = payload.get("request_id") or str(uuid.uuid4())
        run_id = payload.get("run_id") or str(uuid.uuid4())
        postcode = args.postcode or os.environ.get("SHOPPING_DESTINATION_POSTCODE")
    else:
        task = args.task
        request_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        postcode = args.postcode or os.environ.get("SHOPPING_DESTINATION_POSTCODE")
    if not isinstance(task, str) or not task.strip():
        result = _failure_result(
            "A non-empty shopping task is required.",
            request_id=request_id,
            run_id=run_id,
        )
    else:
        config = ShoppingConfig.from_env()
        if postcode and postcode != config.destination_postcode:
            config = replace(config, destination_postcode=postcode)
        telemetry = new_telemetry(request_id, run_id)
        dependencies = default_dependencies(config, telemetry)
        result = run_shopping(
            task,
            dependencies=dependencies,
            request_id=request_id,
            run_id=run_id,
            destination_postcode=postcode,
            telemetry=telemetry,
        )

    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        args.output_json.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if result.get("status") in {"success", "needs_clarification"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
