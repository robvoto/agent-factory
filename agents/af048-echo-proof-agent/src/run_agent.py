"""Hub subprocess adapter for the deterministic AF-048 echo agent."""

from __future__ import annotations

import argparse
import hashlib
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


def build_manifest() -> dict[str, Any]:
    """Return deterministic package metadata for Agent Hub discovery."""
    spec = json.loads((PACKAGE_ROOT / "agent.json").read_text(encoding="utf-8"))
    manifest: dict[str, Any] = {
        "agent_id": spec["id"],
        "package_version": spec["version"],
        "manifest_schema_version": spec["manifest_schema_version"],
        "input_contract": spec["input_contract"],
        "output_contract": spec["output_contract"],
    }
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest["manifest_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--input-json")
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)
    if args.manifest:
        print(json.dumps(build_manifest(), ensure_ascii=False, sort_keys=True))
        return 0
    if not args.input_json or not args.output_json:
        parser.error("--input-json and --output-json are required unless --manifest is used")
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
