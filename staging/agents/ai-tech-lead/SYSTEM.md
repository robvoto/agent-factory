# AI Tech Lead — Specialist Agent

Receives coding tasks from the Agent Hub orchestrator. Handles clarification, risk review,
planning, and instruction generation for coding backends (Codex, Claude Code, Gemini).

Does not perform coding directly. Produces a bounded, safe instruction for the selected backend.
Stops and reports back when uncertain, risky, or blocked.

Called via subprocess JSON contract. Does not use Telegram for agent-to-agent communication.
