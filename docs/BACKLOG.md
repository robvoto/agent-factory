# Agent Factory — Backlog

Items discovered during the army/factory split (2026-06-29). Add to the Google Sheet backlog.

## Must-have (incomplete implementation)

### FACTORY-001: Real coding-agent adapter execution
**Status:** Not implemented  
**Detail:** Factory Brain can stage agent packages but cannot actually invoke a specialist agent (e.g., ai-tech-lead) to execute a task. The `run_agent_task` tool in agent.json is declared but not wired.

### FACTORY-002: Remove remaining runtime/orchestration language from docs
**Status:** Partially done  
**Detail:** Some docs and diagrams (e.g., `docs/diagrams/05-ARMY-ROUTING.md`, `docs/platform-architecture.md`) were written when factory was the main runtime. Review and update diagrams and platform-architecture doc to reflect army as orchestrator.

### FACTORY-003: Propagate `purpose` field to all existing staging agents
**Status:** Fixed for new agents (2026-06-29)  
**Detail:** `factory_tools.py` now writes `purpose` to agent.json. Existing staging agents (e.g., `langchain-research-agent`) may not have `purpose`. Check and add it.

### FACTORY-004: Skill / AGENTS.md compliance enforcement
**Status:** Not implemented  
**Detail:** No automated check that factory code complies with AGENTS.md rules or skill constraints.

## Should-have

### FACTORY-005: Shared knowledge namespace with army
**Status:** Deferred  
**Detail:** Factory's `knowledge_ingestion.py` indexes docs into `("shared","docs")` and `("shared","trusted")` namespaces. After the split, army can no longer read these. Coordinate with ARMY-004.

### FACTORY-006: Factory callable via army orchestrator
**Status:** Not wired  
**Detail:** Army should be able to dispatch "create an agent" tasks to factory brain. Currently only reachable via factory's own Telegram / CLI.

## Decided

### FACTORY-007: Factory telegram gateway stays in factory
**Decision:** Not moving to army. Factory Telegram handles factory admin (/staged, /approve, /reject). Army owns the user-facing gateway.

### FACTORY-008: factory/knowledge_store.py stays in factory
**Decision:** Factory keeps its own SQLite knowledge store. Knowledge sharing with army is a future concern (see FACTORY-005).
