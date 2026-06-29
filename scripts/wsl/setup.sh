#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Agent Factory WSL setup"
echo "Project: $PROJECT_ROOT"
echo "Runtime: uv"

# ---------------------------------------------------------------------------
# Prerequisites (run once on a fresh WSL machine)
# ---------------------------------------------------------------------------
# 1. uv (Python package manager)
#      curl -LsSf https://astral.sh/uv/install.sh | sh
#
# 2. GitHub CLI (gh) — needed to create repos and authenticate
#      curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
#        | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
#      sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
#      echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
#        https://cli.github.com/packages stable main" \
#        | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
#      sudo apt update && sudo apt install gh -y
#      gh auth login   # choose: GitHub.com → SSH → use existing SSH key → Login with browser
#
# 3. All projects live in ~/projects/
#      git clone git@github.com:robvoto/agent-factory.git ~/projects/agent-factory
#      git clone git@github.com:robvoto/ai-tech-lead-agent.git ~/projects/ai-tech-lead
#      git clone git@github.com:robvoto/job-hunter-agent.git ~/projects/job-hunter-agent
#      git clone git@github.com:robvoto/agent-army.git ~/projects/agent-army
#
# 4. Shared resources
#      Agent Factory Backlog (Google Sheet):
#      https://docs.google.com/spreadsheets/d/1outLuOWhd-A7uvzsl9C2Jc-tKpsyci9HPZalxcmFiOg/edit
# ---------------------------------------------------------------------------

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
echo "  cd ~/projects/agent-factory"
echo "  bash run.sh"
echo ""
echo "Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS."