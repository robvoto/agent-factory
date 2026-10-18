# Shopping Agent

**Status:** staged draft, not enabled. Version 1.0.0 remains in `staging/agents`.

This package implements a deterministic LangGraph workflow for discovering products, verifying retailer evidence, classifying candidates, and returning a ranked shortlist. It has no live provider adapters; search, page retrieval, and browser verification are injected interfaces so workflow tests use only offline fixtures.

## Request and constraint handling

Call `ShoppingWorkflow.run()` with a `ShoppingRequest`. The request carries the discovery query, explicit hard constraints, preferences, and optional discovery queries. The workflow copies hard constraints and preferences into a read-only ledger and passes the same ledger to each provider. It does not infer constraints from free-form prose.

Supported hard constraint keys are:

- `product.name`, `product.brand`, `product.model`, `product.sku`, `product.mpn`, `product.gtin`, `product.gtin8`, `product.gtin12`, `product.gtin13`, `product.gtin14`, `product.color`, `product.size`, `product.material`, and `product.category` for exact, case-insensitive text matches with surrounding whitespace normalized.
- `offer.seller_name`, `offer.currency`, `offer.availability`, and `delivery.country` use the same exact text comparison. Availability uses `in_stock` or `out_of_stock`.
- `offer.price_max`, `delivery.price_max`, and `offer.delivered_price_max` for non-negative numeric limits.

Unknown constraint keys or ambiguous values fail the run before provider calls. The workflow does not turn preferences into hard filters.

## Evidence and recommendations

Shopping/search results are discovery only. A candidate can PASS only when a page-fetch or browser adapter returns structured retailer page data from the same host as the discovered product URL, explicitly marked `retailer_page` or `browser_page`. `extract_json_ld_scripts()` parses JSON-LD script blocks from a page already retrieved by the adapter. The data must contain a Schema.org `Product` and an explicit `Offer`. The workflow verifies variant fields, in-stock status, seller, price, currency, and shipping cost. When a requested shipping destination is present, the retailer evidence must also identify that destination.

Candidate URLs reject localhost/local hostnames and non-global IP addresses. Provider adapters that resolve hostnames must also prevent connections to private or link-local addresses.

Classification is deterministic:

- `PASS`: direct Product and Offer evidence verifies all hard constraints and the offer is in stock with a known seller, price, currency, and shipping cost.
- `FAIL`: direct evidence proves a hard constraint is violated or the offer is out of stock.
- `UNVERIFIED`: a required fact is missing, evidence is not from the retailer host, or the source does not provide usable Product and Offer data.

Only PASS candidates can be recommended. They are sorted by delivered price (item price plus shipping), with URL as a stable tie-breaker. The workflow returns at most three.

## Limits and provider adapters

Pass `BudgetLimits` when constructing `ShoppingWorkflow`. All configured limits are checked in code. Hard budget exhaustion stops further provider work, records the triggering metric, and preserves already verified results. Configured warning thresholds are included in run telemetry.

The staged manifest declares configurable API, page-fetch, browser-page, and browser-action guardrails but contains no numeric defaults. The workflow does not invent those values: an unset API-call or page-fetch limit disables that call type, and browser fallback is disabled until both `max_browser_pages` and `max_browser_actions` are set. Search and page adapters receive a per-call API request and retry bound. Browser adapters receive a per-call limit of one page, one action, and one API request; actual page/action counts must be reported in `ProviderUsage`. SerpApi discovery is capped at three requests even if `max_search_calls` is configured higher. API adapters also require `max_api_calls` to be set. No retries are performed by this package; adapters must report retries and the workflow checks them against `max_retries`.

The manifest does not define API-call, page-fetch, or browser-page default values. Those operational values remain unresolved and need explicit runtime configuration. Provider usage and estimated cost are reported when adapters supply them; missing cost or token data is represented as unavailable. When a token or cost hard limit is configured but the corresponding usage is unavailable, the workflow stops further provider calls with `usage_unavailable` and identifies the relevant limit in telemetry. Token and cost guardrails also stop subsequent calls when returned usage crosses a configured limit. Since this package has no provider-specific pre-call cost estimator, a single provider call can exceed a token or cost limit before its returned usage is observed.

## Refusals, telemetry, and data handling

The workflow refuses explicit `purchase`, `checkout`, `account_change`, or `order_change` actions before calling providers. It also refuses direct buy/purchase/order commands (including a product noun phrase such as “buy camera”), checkout, order placement, or account/order changes. These checks are a bounded command detector, not a general language understanding layer; callers should pass `requested_action` explicitly when the requested action is known.

Run telemetry includes the manifest's run fields and per-call provider, phase, type, duration, status, safe domain, token usage, and estimated cost fields. It records provider-specific call and usage aggregates, class counts, browser use, retries, errors, warnings, and the stop reason. LLM call count is zero because this workflow does not use an LLM. Input/output/cached token fields aggregate provider-reported usage and are null when any call omits those values. Estimated cost is likewise null when any provider call omits it. `RunTelemetry.log_record()` exposes telemetry only; it excludes request prose, constraints, evidence, and provider payloads. Sensitive keys and secret-bearing strings are redacted by `redact_log_payload()`.

No purchase, checkout, account-change, or order-change integration exists. The package adds no memory, filesystem access, shell access, or tool permissions.

## Changed files and validation

Implementation files:

- `src/models.py` — request, constraint, evidence, and result contracts.
- `src/budgets.py` — configurable operation limits and warning thresholds.
- `src/verification.py` — JSON-LD extraction, strict same-host Product/Offer verification, and deterministic classification.
- `src/telemetry.py` — structured run/call accounting and log-safe projection.
- `src/workflow.py` — LangGraph capture, discovery, verification, refusal, and shortlist stages.
- `src/__init__.py` — package exports.
- `README.md` — package behavior, safety boundaries, and unresolved operational values.
- `tests/conftest.py` — offline retailer Product/Offer fixture.
- `tests/test_budgets.py` — deterministic budget and warning threshold cases.
- `tests/test_verification.py` — evidence, variant, availability, shipping, and classification cases.
- `tests/test_workflow.py` — constraint propagation, discovery limits, shortlist, fallback, refusals, telemetry, and redaction cases.

Validation: `python -m pytest staging/agents/shopping-agent/tests -q` is pending after the requested corrections; the earlier 30-pass result predates them.
