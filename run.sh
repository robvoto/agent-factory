#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

usage() {
  cat <<'EOF'
Agent Factory Platform runner

Usage:
  bash run.sh                      Start the Agent Factory Telegram app
  bash run.sh telegram             Start the Agent Factory Telegram app
  bash run.sh dev                  Start with hot reload (auto-restart on code changes)
  bash run.sh setup                Install/sync dependencies with uv
  bash run.sh test                 Run pytest only; must not create persistent project files
  bash run.sh list                 List enabled agents
  bash run.sh staged               List staged agent drafts
  bash run.sh pending              List pending approvals
  bash run.sh check                Check LangChain harness import
  bash run.sh create "<request>"   Developer-only: create a staged package
  bash run.sh factory "<request>"  Developer-only: invoke Factory Brain once
  bash run.sh promote <agent-id>   Request promotion approval for a staged agent
  bash run.sh approve <id>         Approve a pending action by ID
  bash run.sh reject <id> [reason] Reject a pending action by ID
  bash run.sh delete <agent-id>    Delete a staged or enabled agent
  bash run.sh route "<command>"    Developer-only: route a command, e.g. "/agent research hello"
  bash run.sh all                  Run non-mutating checks: test + list + check
  bash run.sh ingest-knowledge      Index local docs and trusted online sources into shared knowledge store
  bash run.sh web                  Start optional local web app
  bash run.sh help                 Show this help

Run the project:
  cd ~/projects/agent-factory
  bash run.sh

Expected MVP interaction:
  Telegram talks to the Agent Factory Brain.

Dependency rule:
  This project is uv-first. Do not use pip/activate as the normal path.
EOF
}

require_wsl() {
  if grep -qi microsoft /proc/version 2>/dev/null; then
    return 0
  fi
  echo "ERROR: run.sh is intended for WSL."
  echo "Use: cd ~/projects/agent-factory && bash run.sh"
  exit 1
}

require_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  echo "ERROR: uv is not installed or not on PATH."
  echo "Install uv in WSL, then run: bash run.sh setup"
  exit 1
}

uv_cmd() {
  require_uv
  uv run "$@"
}

run_setup() {
  require_uv
  uv sync --all-extras
}

run_telegram() { uv_cmd agent-factory telegram "$@"; }
run_dev()      { uv_cmd python -m agent_factory.hot_reload; }
run_web()      { uv_cmd python -m agent_factory.app; }
run_test()     { uv_cmd pytest -q; }
run_list()     { uv_cmd agent-factory list; }
run_staged()   { uv_cmd agent-factory staged; }
run_pending()  { uv_cmd agent-factory pending; }
run_check()    { uv_cmd agent-factory langchain-check; }

run_route() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh route "/agent research hello"'
    exit 1
  fi
  uv_cmd agent-factory route "$*"
}

run_create() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh create "Create an agent that researches LangChain docs safely"'
    exit 1
  fi
  uv_cmd agent-factory create "$*"
}

run_factory() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh factory "Create an agent that researches LangChain docs safely"'
    exit 1
  fi
  uv_cmd agent-factory factory "$*"
}

run_promote() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh promote langchain-research-agent'
    exit 1
  fi
  uv_cmd agent-factory promote "$1"
}

run_approve() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh approve 1'
    exit 1
  fi
  uv_cmd agent-factory approve "$1"
}

run_reject() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh reject 1 "Not ready"'
    exit 1
  fi
  uv_cmd agent-factory reject "$@"
}

run_ingest_knowledge() {
  uv_cmd python -c "from agent_factory.knowledge_ingestion import run_ingestion; run_ingestion()"
}

run_delete() {
  if [ "$#" -lt 1 ]; then
    echo 'Example: bash run.sh delete langchain-research-agent'
    exit 1
  fi
  uv_cmd agent-factory delete "$1"
}

main() {
  require_wsl

  local command="${1:-telegram}"
  if [ "$#" -gt 0 ]; then shift; fi

  case "$command" in
    telegram|start|run) run_telegram "$@" ;;
    dev)                run_dev ;;
    web|app)            run_web ;;
    setup)              run_setup ;;
    test)               run_test ;;
    list)               run_list ;;
    staged)             run_staged ;;
    pending)            run_pending ;;
    check|langchain-check) run_check ;;
    route)              run_route "$@" ;;
    create)             run_create "$@" ;;
    factory)            run_factory "$@" ;;
    promote)            run_promote "$@" ;;
    approve)            run_approve "$@" ;;
    reject)             run_reject "$@" ;;
    delete)             run_delete "$@" ;;
    ingest-knowledge)   run_ingest_knowledge ;;
    all)                run_test; run_list; run_check ;;
    help|-h|--help)     usage ;;
    *)
      echo "ERROR: unknown command: $command"
      echo ""
      usage
      exit 1
      ;;
  esac
}

main "$@"