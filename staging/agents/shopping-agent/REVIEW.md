# Agent Draft Review

Status: staged draft only. This agent is not enabled.

## Spec

- ID: `shopping-agent`
- Name: Shopping Agent
- Purpose: Primary responsibility: Find the best purchasable options for a user's shopping request by systematically discovering, verifying, filtering, and ranking products against explicit constraints and preferences.
Select for: Shopping requests where the user wants strong alternatives, cheaper options, best-value choices, exact variants, availability, delivery cost, or other buying constraints verified across multiple sources.
Do not select for: Purchasing or checkout, account/order changes, general non-shopping research, or presenting unverified candidates as recommendations.

## Risks

- network

## Tests

- Verify every explicit mandatory constraint is captured before discovery and preserved through ranking.
- Verify discovery covers multiple relevant sources/queries with bounded stop conditions and reports coverage limits.
- Verify discovery and candidate verification are separate phases.
- Verify exact selectable variant, current buyability, item price, relevant shipping/delivery cost, total delivered price where possible, direct product URL, source, and checked time.
- Verify PASS only when every hard constraint is confirmed; FAIL on hard mismatch or unavailable/temporarily closed seller; UNVERIFIED when a mandatory fact remains unknown.
- Verify only PASS candidates are recommendations; near-misses/benchmarks are clearly separated.
- Verify search/direct retrieval is attempted before bounded browser automation or scraping fallback.
- Verify browser/scraping fallback is bounded, auditable, and used only when needed to verify mandatory shopping facts.
- Verify concise shopper-facing output highlights useful choices such as cheapest verified option, best-value option, and closest match only when evidence supports those labels.
- Verify purchasing, checkout, account changes, and order changes are refused.
- Verify each run emits structured debugging telemetry with request/run correlation, workflow phase/node, retries, errors, stop reason, duration, and candidate counts.
- Verify each LLM call records model ID plus input/output/cached token usage when available and estimated cost; each run aggregates call count, token totals, and estimated total cost.
- Verify search/API/page/browser calls are counted and logged at run level, with safe domain/URL metadata and no secrets.
- Verify configurable hard budgets exist for LLM calls/tokens/cost, search/page/browser work, and retries; warning thresholds are surfaced before hard limits.
- Verify budget exhaustion stops safely, logs the exact stop reason, and returns partial verified results rather than silently overspending.
- Verify sensitive credentials, cookies, tokens, payment details, and raw private account data are never written to logs.
- Verify no durable user-memory behavior, shell access, or broad filesystem access is introduced for the MVP.

## Approval rule

Do not copy this agent into `config/agents` until a human approves it.
