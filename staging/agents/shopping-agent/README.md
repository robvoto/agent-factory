# Shopping Agent

**Status:** staged draft — not enabled.

Do not move this package to `config/agents` without human approval.

The package now contains a deterministic LangGraph workflow in `src/shopping_agent/` with four stages: parse constraints, discover with Google Shopping, verify direct retailer Product/Offer evidence, and rank verified options. The workflow accepts provider adapters as callables; it has no built-in network client, browser driver, credential store, or LLM call. Offline tests inject mocks.

## Verification rules

- Discovery uses the Google Shopping engine only and makes at most three SerpApi requests. The task text is the first query; up to two optional additional queries can be supplied in `ShoppingConfig`.
- Search results are discovery hints. Candidates must have a direct HTTPS retailer URL and must be verified from Product and Offer structured data returned by the direct retailer page adapter.
- `PASS` requires a proven exact product length, in-stock Offer, AUD item price, and AUD shipping amount for the exact requested Australian postcode. Delivered price is their sum. A stated length must match exactly; a stated AUD budget is enforced against delivered price unless the request explicitly says item price only.
- A hard mismatch is `FAIL`. Missing or ambiguous mandatory evidence is `UNVERIFIED`. Only `PASS` results are ranked, by delivered AUD price, and at most three are recommended.
- Checkout, purchase, order changes, and account changes are refused.
- Browser fallback runs only when direct evidence is incomplete, a browser adapter is supplied, and both `max_browser_pages` and `max_browser_actions` are explicitly configured. It receives the remaining page and action allowances and must report actual pages and actions used.

## Configuration and providers

`ShoppingConfig` contains optional limit and warning-threshold fields corresponding to the staged manifest. No numeric per-run, API, page-fetch, browser-page, browser-action, retry, token, or cost defaults are supplied. `None` leaves the corresponding control unset. The approved maximum of three Google Shopping discovery requests is enforced independently. Whole-task token and elapsed-time budgets remain unset.

Provider adapters are passed in `ShoppingProviders` and must return `ProviderCall`. They should keep credentials in their own runtime environment, accept one request per invocation, avoid retries, and never include credentials or raw private data in returned values used for logging. The workflow records provider call counts and available cost, token, retry, page, browser-action, duration, status, and safe retailer-domain metadata. It reports token usage as unavailable because this workflow makes no LLM calls; estimated provider cost is marked incomplete when any invoked provider does not report it. Raw provider errors, search queries, page content, cookies, headers, and credentials are not written to telemetry.

No provider adapter or runtime configuration is registered in this staged package. API-call, page-fetch, and browser-page defaults therefore remain unset; an operator must supply appropriate adapters and limits at runtime. Browser fallback stays disabled until explicit page and action limits are provided. No live network or browser action is part of the tests.

## Offline validation

Run from the Agent Factory repository root:

```sh
python -m pytest staging/agents/shopping-agent/tests -q
```
