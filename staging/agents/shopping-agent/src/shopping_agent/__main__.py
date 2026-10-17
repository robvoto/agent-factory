"""Manual CLI for the staged Shopping Agent MVP."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

from .providers import create_shopping_providers
from .workflow import ShoppingConfig, run_shopping_workflow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare retailer offers against explicit shopping constraints."
    )
    parser.add_argument("task", help="Shopping request; purchases and checkout are refused.")
    parser.add_argument(
        "--max-api-calls",
        type=int,
        required=True,
        help="Required per-run cap for SerpApi and retailer page calls.",
    )
    parser.add_argument(
        "--max-page-fetches",
        type=int,
        required=True,
        help="Required per-run cap for direct retailer page fetches.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        required=True,
        help="Timeout for each individual HTTPS request.",
    )
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be finite and greater than zero")

    api_key = os.environ.get("SERPAPI_KEY")
    providers = create_shopping_providers(api_key, timeout_seconds=args.timeout_seconds)
    config = ShoppingConfig(
        max_search_calls=3,
        max_api_calls=args.max_api_calls,
        max_page_fetches=args.max_page_fetches,
    )
    result = run_shopping_workflow(args.task, providers, config)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 2 if result["status"] == "provider_unavailable" else 0


if __name__ == "__main__":
    sys.exit(main())
