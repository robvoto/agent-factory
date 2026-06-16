"""Hot reload wrapper for the Telegram gateway.

Watches src/ and config/ for changes and restarts the gateway process.
In-flight conversations are safe — all thread state lives in SQLite.

Usage: bash run.sh dev
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[2]
_WATCH_DIRS = [
    _PROJECT_ROOT / "src",
    _PROJECT_ROOT / "config",
    _PROJECT_ROOT / "memory",
]


def run_with_reload(bot_name: str | None = None) -> None:
    from watchfiles import watch

    cmd = [sys.executable, "-m", "agent_factory.cli", "telegram"]
    if bot_name:
        cmd += ["--bot", bot_name]

    env = os.environ.copy()

    print(f"[hot-reload] Starting gateway. Watching {[str(d) for d in _WATCH_DIRS]}")

    proc: subprocess.Popen | None = None

    def _start() -> subprocess.Popen:
        return subprocess.Popen(cmd, env=env, cwd=str(_PROJECT_ROOT))

    proc = _start()

    try:
        for changes in watch(*[str(d) for d in _WATCH_DIRS if d.exists()]):
            changed = [Path(c[1]).relative_to(_PROJECT_ROOT) for c in changes]
            print(f"[hot-reload] Changed: {changed} — restarting gateway...")
            proc.terminate()
            proc.wait(timeout=10)
            proc = _start()
    except KeyboardInterrupt:
        print("[hot-reload] Stopping.")
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
