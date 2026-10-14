"""Factory subprocess adapter for the staged Shopping Agent package."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_ROOT / "runtime"))

from shopping_agent.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
