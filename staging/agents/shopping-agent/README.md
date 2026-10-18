# Shopping Agent

**Status:** staged test candidate — not enabled.

Do not move this package to `config/agents` without human approval.

The package contains a deterministic LangGraph workflow in `src/shopping_agent/` with four stages: parse constraints, discover with Google Shopping, verify direct retailer Product/Offer evidence, and rank verified options. It includes SerpApi and direct-retailer HTTPS adapters plus a command-line interface. Credentials stay in the environment, browser automation is not configured, and the workflow makes no LLM calls. Offline tests inject mocks.

## Verification rules

- Discovery uses the Google Shopping engine only and makes at most three SerpApi requests. A sanitized version of the task is the first query; up to two optional additional queries can be supplied in `ShoppingConfig`.
- Search results are discovery hints. Candidates must have a direct HTTPS retailer URL and must be verified from Product and Offer structured data returned by the direct retailer page adapter. The workflow rejects localhost, single-label hosts, common local-domain suffixes (`.localhost`, `.local`, `.internal`, `.lan`), noncanonical numeric IP forms, and non-global IP literals. The direct adapter also rejects DNS results resolving to private or link-local addresses.
- A request for a new product requires explicit `Product.itemCondition` evidence of `NewCondition`; a product or brand name containing “new” is not proof of condition.
- `PASS` requires a proven exact product length, in-stock Offer, AUD item price, and AUD shipping amount for the exact requested Australian postcode. Delivered price is their sum. A stated length must match exactly; a stated AUD budget is enforced against delivered price unless the request explicitly says item price only.
- Request lengths accept an ASCII hyphen between the amount and any already supported unit, with optional surrounding spaces: `7-foot`, `7-ft`, and `2-m` use the same Decimal conversions as `7 ft` and `200 cm`. Numeric ranges joined by an ASCII hyphen, en/em dash, minus sign, or `to`, and lengths with an ASCII/unicode minus sign, request one exact length before providers run; no endpoint or positive value is chosen. Other separator syntax is not normalized. Explicit model IDs such as `X100-7-foot` remain identity constraints. Retailer titles still do not prove length: structured Product/Offer evidence is required.
- Shipping evidence must pair that postcode with an explicit Australian country on the same `shippingDestination` or `eligibleRegion` entry. Accepted country text is `AU`, `AUS`, or `Australia` (case-insensitive); an explicit schema.org `Country` object may supply those values through `identifier` or `name`, with every supplied identity consistent. Missing, foreign, unrecognized, or conflicting country evidence leaves shipping unknown and the candidate `UNVERIFIED`; AUD currency, seller location, shipment origin, or an unrelated destination cannot prove Australian delivery. The supported region/country fields follow [schema.org DefinedRegion](https://schema.org/DefinedRegion) and [addressCountry](https://schema.org/addressCountry).
- Explicit `under`, `below`, and `less than` bounds exclude the exact AUD budget; `maximum`, `max`, `up to`, `at most`, and a bare AUD budget allow equality. The same comparison applies to the existing item-only or delivered-price basis.
- Different explicitly recognized postcodes, product lengths, or budget amounts/comparisons trigger a fixed clarification question for each affected field before any provider call. Equivalent repeats are accepted, including `2 m`/`200 cm` and synonymous price bounds. Different compatible bounds still require clarification; the workflow does not choose the first, last, or tighter value. Budget clarification asks for one AUD amount and whether the price may equal it. Any bare `$` amount requires currency clarification even alongside an explicit AUD amount. All recognized constraint spans are excluded from product identity terms; unrelated model/variant text remains required.
- Every meaningful product term in the request, including brand and category, plus explicit model, alphanumeric variant, labeled numeric size, and recognized color, material, or feature tokens must appear in both the discovered title and direct Product evidence. Generic shopping instructions and price/location/length syntax are excluded. A mismatch or missing term is `UNVERIFIED`; other hard mismatches are `FAIL`. Only `PASS` results are ranked by delivered AUD price, and at most three are recommended.
- Checkout, purchase, order changes, and account changes are refused.
- Browser fallback runs only when direct evidence is incomplete, a browser adapter is supplied, and `max_browser_pages` is explicitly configured. It receives the remaining page allowance; page usage is enforced, while browser actions are telemetry only.
- Direct Product/Offer evidence must also match the discovered product name. A retailer page for a different item remains `UNVERIFIED`.

## Configuration and providers

`ShoppingConfig` contains only the approved configurable operational controls: search calls, API calls, page fetches, and browser pages. Warning thresholds for those counters are logged and added to telemetry when reached, before another call can cross a hard limit. No per-run LLM/token/cost cap, browser-action ceiling, or retry ceiling is imposed. Provider cost, token, retry, browser-page, and browser-action usage is measured when reported. The approved maximum of three Google Shopping discovery requests is enforced independently. Whole-task token and elapsed-time budgets remain unset.

Provider adapters are passed in `ShoppingProviders` and must return `ProviderCall`. They should keep credentials in their own runtime environment and never include credentials or raw private data in returned values used for logging. The workflow records provider call counts and available cost, token, retry, page, browser-action, duration, status, and safe retailer-domain metadata. Before external discovery it strips common credential assignments and prose forms, standalone bearer tokens, email addresses, phone numbers, and explicit URLs from search queries. It reports token usage as unavailable because this workflow makes no LLM calls; estimated provider cost is marked incomplete when any invoked provider does not report it. Raw provider errors, search queries, page content, cookies, headers, and credentials are not written to telemetry.

A Hub subprocess adapter is available for the isolated Agent Hub test profile. The adapter uses the same deterministic workflow, reads the SerpApi credential only from the Hub process environment, and does not enable browser automation, checkout, purchases, or account changes. Test runs still require explicitly configured API-call, page-fetch, and per-request timeout values; the adapter does not invent operational defaults.

When the workflow needs a postcode, currency, or exact-length clarification, the adapter returns `needs_clarification` with the actual questions instead of a failed result. It makes no provider calls for that ambiguous request and creates no resume token. These budget and clarification corrections are covered offline; live provider, Hub interaction, and promotion acceptance remain separate.

Set `SERPAPI_KEY` in the Agent Hub process environment (never in source code or command arguments), then route a shopping task to this candidate from an Agent Hub process running with `HUB_PROFILE=test`. Configure `SHOPPING_MAX_API_CALLS`, `SHOPPING_MAX_PAGE_FETCHES`, and `SHOPPING_TIMEOUT_SECONDS` in that test process. If any operational limit is missing or invalid, the adapter reports the exact configuration variable and makes no provider call. The command-line interface remains available for isolated local checks:

```sh
PYTHONPATH=staging/agents/shopping-agent/src python -m shopping_agent \
  "Find a 2 m garden hose under AUD 50, postcode 2000" \
  --max-api-calls <operator-selected-limit> \
  --max-page-fetches <operator-selected-limit> \
  --timeout-seconds <operator-selected-per-request-timeout>
```

The three operational values are required at each invocation so the package does not invent limits. Search is capped at three SerpApi requests. The request timeout is a hard deadline for each HTTPS call, including DNS and response reading; each response is limited to 8 MiB. It is not a whole-task deadline. If `SERPAPI_KEY` is absent, the CLI makes no discovery request and returns `provider_unavailable`.

Retailer fetches require HTTPS, reject redirects, resolve the host to public IP addresses with the Linux `getent` resolver, reject mixed/private DNS answers, and connect to a validated IP while retaining TLS hostname verification. The resolver and each HTTPS call use the required finite per-request deadline. Provider exceptions and response bodies are not logged. SerpApi usage/cost remains unavailable unless the provider reports it. The adapter follows SerpApi's Google Shopping endpoint and required query parameters documented at [SerpApi Google Shopping API](https://serpapi.com/google-shopping-api).

Tests use injected mock transports only; they do not call SerpApi or retailer sites. Browser fallback stays disabled.

## Offline validation

Run from the Agent Factory repository root:

```sh
python -m pytest staging/agents/shopping-agent/tests -q
```
