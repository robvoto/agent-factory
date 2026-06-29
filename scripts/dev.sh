#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Agent Factory Platform dev check"
echo "Project: $PROJECT_ROOT"
echo "Runtime: uv"

if grep -qi microsoft /proc/version 2>/dev/null; then
  :
else
  echo "ERROR: This script is intended to run from WSL."
  echo "Use: cd ~/projects/agent-factory && bash scripts/dev.sh"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is not installed or not on PATH in WSL."
  echo "Run setup first: bash run.sh setup"
  exit 1
fi

uv run pytest -q
uv run agent-factory list
uv run agent-factory langchain-check

echo ""
echo "Dev check passed."
