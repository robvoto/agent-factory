# Shopping Agent

**Status:** staged draft — not enabled.

Do not move this package to `config/agents` without human approval.

The package now contains a deterministic LangGraph workflow in `src/shopping_agent/` with four stages: parse constraints, discover with Google Shopping, verify direct retailer Product/Offer evidence, and rank verified options. The workflow accepts provider adapters as callables; it has no built-in network client, browser driver, credential store, or LLM call. Offline tests inject mocks.

## Verification rules

- Discovery uses the Google Shopping engine only and makes at most three SerpApi requests. A sanitized version of the task is the first query; up to two optional additional queries can be supplied in `ShoppingConfig`.
- Search results are discovery hints. Candidates must have a direct HTTPS retailer URL and must be verified from Product and Offer structured data returned by the direct retailer page adapter. The workflow rejects localhost, single-label hosts, common local-domain suffixes (`.localhost`, `.local`, `.internal`, `.lan`), noncanonical numeric IP forms, and non-global IP literals. Any production page adapter must also reject DNS results resolving to private or link-local addresses.
- A request for a new product requires explicit `Product.itemCondition` evidence of `NewCondition`; a product or brand name containing “new” is not proof of condition.
- `PASS` requires a proven exact product length, in-stock Offer, AUD item price, and AUD shipping amount for the exact requested Australian postcode. Delivered price is their sum. A stated length must match exactly; a stated AUD budget is enforced against delivered price unless the request explicitly says item price only.
- Every meaningful product term in the request, including brand and category, plus explicit model, alphanumeric variant, labeled numeric size, and recognized color, material, or feature tokens must appear in both the discovered title and direct Product evidence. Generic shopping instructions and price/location/length syntax are excluded. A mismatch or missing term is `UNVERIFIED`; other hard mismatches are `FAIL`. Only `PASS` results are ranked by delivered AUD price, and at most three are recommended.
- Checkout, purchase, order changes, and account changes are refused.
- Browser fallback runs only when direct evidence is incomplete, a browser adapter is supplied, and `max_browser_pages` is explicitly configured. It receives the remaining page allowance; page usage is enforced, while browser actions are telemetry only.
- Direct Product/Offer evidence must also match the discovered product name. A retailer page for a different item remains `UNVERIFIED`.

## Configuration and providers

`ShoppingConfig` contains only the approved configurable operational controls: search calls, API calls, page fetches, and browser pages. Warning thresholds for those counters are logged and added to telemetry when reached, before another call can cross a hard limit. No per-run LLM/token/cost cap, browser-action ceiling, or retry ceiling is imposed. Provider cost, token, retry, browser-page, and browser-action usage is measured when reported. The approved maximum of three Google Shopping discovery requests is enforced independently. Whole-task token and elapsed-time budgets remain unset.

Provider adapters are passed in `ShoppingProviders` and must return `ProviderCall`. They should keep credentials in their own runtime environment and never include credentials or raw private data in returned values used for logging. The workflow records provider call counts and available cost, token, retry, page, browser-action, duration, status, and safe retailer-domain metadata. Before external discovery it strips common credential assignments and prose forms, standalone bearer tokens, email addresses, phone numbers, and explicit URLs from search queries. It reports token usage as unavailable because this workflow makes no LLM calls; estimated provider cost is marked incomplete when any invoked provider does not report it. Raw provider errors, search queries, page content, cookies, headers, and credentials are not written to telemetry.

No provider adapter or runtime configuration is registered in this staged package. API-call, page-fetch, and browser-page defaults therefore remain unset; an operator must supply appropriate adapters and operational limits at runtime. Browser fallback stays disabled until an explicit page limit is provided. No live network or browser action is part of the tests.

## Offline validation

Run from the Agent Factory repository root:

```sh
python -m pytest staging/agents/shopping-agent/tests -q
```
