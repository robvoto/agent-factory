---
name: backlog-management
description: Use when a Factory task refers to a backlog item, task ID, roadmap status, or approval record.
---

# Factory Backlog Management

Use the live backlog and project documents as authoritative sources. Chat history, copied prompts, generated artifacts, and local notes are context only; verify current state before acting.

## Retrieve current records

- Read the Agent Factory backlog spreadsheet, ID 1outLuOWhd-A7uvzsl9C2Jc-tKpsyci9HPZalxcmFiOg, using the backlog credential profile and the exact backlog tab.
- Match the exact task ID first. Confirm its title, status, scope, acceptance criteria, and any linked evidence from the current row.
- Read referenced Google Docs through the authorized Docs read connector. Open and read the document in place; do not download it to inspect it.
- If the row, status, or referenced source cannot be verified, report the specific retrieval failure and do not fill gaps from memory.

## Prepare and execute work

- Treat the live row as the source for task meaning and status. Treat an approved, correlated task artifact as the source for the implementation boundary and permitted paths.
- Compare the row, artifact, and current staged package before implementation. Stop and report any disagreement that changes scope, acceptance, permissions, limits, or lifecycle state.
- Do not mark an item approved, in progress, complete, promoted, or closed unless the corresponding authorized workflow has succeeded and the live record confirms it.
- A worker may update a backlog cell only when the human has authorized that record change or the active workflow explicitly includes it. Do not edit rows as a side effect of implementation.
- Report the task ID and title, the live status observed, the source checked, and any unresolved mismatch. Distinguish verified facts from historical context.

## Source and session handling

- Reuse a browser tab this worker opened for sequential reading. Open a separate tab or session only when isolation is needed.
- On a connector failure, inspect the returned error and retry once with the corrected safe request. Do not repeat an identical failing request or claim the source is unavailable before attempting its documented connector.
- Never expose credentials or copy secrets into backlog notes, task artifacts, or logs.
