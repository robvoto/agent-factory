#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Agent Factory WSL setup"
echo "Project: $PROJECT_ROOT"
echo "Runtime: uv"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is not installed or not on PATH in WSL."
  echo "Install uv first, then rerun: bash run.sh setup"
  exit 1
fi

uv sync --all-extras
uv run pytest -q
uv run agent-factory list
uv run agent-factory langchain-check

echo ""
echo "Done. To run the project:"
echo "  cd /mnt/e/programming/agent-factory"
echo "  bash run.sh"
echo ""
echo "Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS."