# Agent Draft Review

Status: staged draft only. This agent is not enabled.

## Spec

- ID: `shopping-research-agent`
- Name: Shopping Research Agent
- Purpose: Primary responsibility: Research products against explicit shopper constraints and produce evidence-backed recommendations only for options that pass deterministic verification.
Select for: Comparing publicly available products, prices, availability, specifications, and other user-specified mandatory facts through a bounded discovery-and-verification workflow, with account-only sources used only after per-task approval.
Do not select for: Purchasing or checking out, changing accounts or orders, accessing account-only sources without per-task approval, or making recommendations from unverified or failed mandatory claims.

## Risks

- network

## Tests

- Verify constraints are captured in a deterministic constraint ledger before discovery.
- Verify discovery is bounded and candidate findings are independently verified in a separate phase.
- Verify deterministic PASS, FAIL, or UNVERIFIED outcomes and recommend PASS candidates only.
- Verify browser fallback occurs only when a mandatory fact cannot otherwise be verified and remains bounded.
- Verify account-only sources require per-task approval; public sources are the default.
- Verify purchase, checkout, and account changes are refused.
- Verify no durable memory, shell, or filesystem access is used.

## Approval rule

Do not copy this agent into `config/agents` until a human approves it.
