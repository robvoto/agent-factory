"""Hub subprocess adapter for the deterministic AF-048 echo agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from specialist_contract import adapt_universal_task  # noqa: E402
from agent import run  # noqa: E402


def process_payload(payload: Any) -> dict[str, str]:
    """Validate Hub input and return the standard terminal result."""
    try:
        adapt_universal_task(payload)
        # The adapter validates the task but normalizes it for general agents.
        # AF-048 preserves every character of the original task string.
        result = run(payload["task"])
    except (TypeError, ValueError, KeyError) as exc:
        return {"status": "failed", "summary": str(exc)}
    return {"status": "success", "summary": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    output_path = Path(args.output_json)
    try:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
        result = process_payload(payload)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"status": "failed", "summary": str(exc)}
    try:
        output_path.write_text(
            json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"Could not write result JSON: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
