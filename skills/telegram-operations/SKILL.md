---
name: telegram-operations
description: Safe Telegram design, runtime, and browser-test procedures for Agent Factory and generated agents.
---

# Skill: Telegram Operations

Use this skill when Agent Factory, a generated agent, or a human tester needs to design, run, or validate Telegram behavior.

## Scope

This skill covers:
- Agent Factory Telegram gateway behavior;
- generated-agent Telegram interaction requirements;
- safe browser-based Telegram Web verification;
- approval/resume semantics;
- avoiding ambiguous composer controls.

It does not grant Telegram credentials, browser access, or permission to send messages by itself.

## Core safety rules

- Never guess an unlabeled Telegram control.
- Treat sending a Telegram message as an external side effect.
- Never purchase, approve, promote, delete, or mutate shared state merely because a Telegram UI action is available.
- Preserve explicit human approval boundaries from the underlying workflow.
- If UI state is ambiguous, stop and inspect the real DOM/state instead of probing buttons.

## Agent Factory Telegram gateway

Factory's Telegram gateway is only a transport. Business logic remains in Factory Brain and bounded tools.

Important command semantics:
- `/new`: starts a fresh Factory Brain thread and clears old conversational context.
- `/approve <id>`: approves a specific persisted approval record only.
- `/approve` with no ID: resumes a LangGraph thread only when that thread is actually interrupted.
- These are different mechanisms. Do not assume approving a persisted research record automatically resumes or continues Factory Brain.
- After approving a design-research record, a later normal-language Factory Brain turn may be required to call `run_design_research(<id>)`.
- `/reject <id> [reason]`: rejects a persisted approval record.
- `/reject` with no ID applies only to an interrupted Factory Brain thread.

Always verify the live code before changing these semantics.

## Keep Telegram turns bounded

Telegram conversations can become expensive because the whole thread may contribute context.

- Use `/new` when a long design conversation has already been summarised and only a compact handoff is needed.
- Carry forward only the approved design, unresolved decisions, and required evidence.
- Do not resend entire historical conversations.
- Runtime/provider limits must come from central Factory settings rather than hardcoded call sites.
- A long-running or repeatedly failing turn is a stop condition: inspect the actual process, approval state, and provider error before retrying.

## Browser testing with Human MCP

When validating Telegram Web through Human MCP:

1. Open a dedicated owned Telegram tab and retain its `page_id`.
2. Take a fresh snapshot before interaction.
3. Identify the **real composer**:
   - class contains `input-message-input`;
   - class does **not** contain `input-field-input-fake`.
4. Never fill the fake/mirror editor `input-field-input-fake`.
5. Fill the real composer only.
6. Snapshot again and verify the circular composer button state:
   - safe send state: class contains `btn-send` and `send`;
   - voice/record state: class contains `btn-send` and `record`.
7. Click the circular button only when the current snapshot explicitly proves it is in `send` state.
8. After sending, verify:
   - real composer cleared;
   - button returned to `record`;
   - outgoing message appears or the chat preview updates;
   - expected bot response arrives.

Do not identify Send from glyphs/icons alone.

## Proven Telegram Web failure pattern

On 2026-10-02, filling Telegram's fake mirror editor made draft text appear present but left Telegram in voice/record mode. Repeated guessing of the circular control triggered voice recording.

The proven path was:
- snapshot DOM metadata;
- identify the real `input-message-input`;
- fill that real composer;
- verify `btn-send ... send`;
- click only after that explicit state appeared;
- verify the composer cleared.

This is the canonical browser-test path until Telegram's DOM changes.

## Keyboard actions

A bounded Human MCP `browser_press_key` tool may be available, but do not use Enter as a workaround for an unresolved Telegram composer state.

Prefer the explicit verified `send` button state for Telegram messaging.

## Approvals and research

For Factory design research:
- `request_design_research` creates an immutable approval record and does not perform network access.
- Human approval changes that record to approved.
- `run_design_research(id)` is the single bounded network attempt and atomically claims the approval.
- A claimed request that fails must end in a terminal status; never silently reuse it.
- If a request hits provider rate limits or grows excessively large, start a fresh compact Factory session rather than retrying the bloated thread.

## Generated-agent design

When a generated agent uses Telegram:
- Telegram should be a transport/integration, not the source of truth for domain state.
- Define exactly which messages/commands it accepts.
- Define authentication/allowed-chat rules.
- Separate read-only notifications from actions that mutate external systems.
- Require explicit approval for consequential writes.
- Keep Telegram-specific UI/browser logic out of domain workflows unless the agent genuinely needs browser automation.
- Prefer the Telegram Bot API for runtime agents; use Telegram Web browser automation mainly for human-in-the-loop testing or cases the Bot API cannot satisfy.

## Test checklist

Before declaring Telegram support complete:
- gateway starts from documented command;
- allowed chat IDs are enforced;
- `/new` clears prior Factory context;
- persisted approval commands behave as documented;
- interrupted-thread resume behaves separately and correctly;
- real composer is used in browser tests;
- record/voice control is never clicked when Send was intended;
- sent messages are verified after the action;
- process/runtime failures surface clearly;
- repo is clean and tests pass before push.
