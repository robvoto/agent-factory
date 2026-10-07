# Shopping Agent

**Status:** staged runnable MVP — not enabled.

**Purpose:** Primary responsibility: Find the best purchasable options for a user's shopping request by systematically discovering, verifying, filtering, and ranking products against explicit constraints and preferences.
Select for: Shopping requests where the user wants strong alternatives, cheaper options, best-value choices, exact variants, availability, delivery cost, or other buying constraints verified across multiple sources.
Do not select for: Purchasing or checkout, account/order changes, general non-shopping research, or presenting unverified candidates as recommendations.

**Aliases:** shopping, shop

## MVP workflow

`constraints -> SerpApi discovery -> direct retailer-page verification -> PASS/FAIL/UNVERIFIED -> rank -> concise shortlist`

The runtime is a deterministic LangGraph workflow. SerpApi is discovery-only;
Google Shopping prices and delivery text are never treated as final checkout
evidence. PASS requires direct retailer evidence for the exact requested length,
current stock, item price, shipping to the configured postcode, and delivered
AUD price within budget. Missing evidence is UNVERIFIED. A direct out-of-stock,
wrong-length, or over-budget result is FAIL.

## Direct run

From the Agent Factory repository root:

```bash
# Provide SERPAPI_API_KEY through the local secret environment; do not commit it.
export SHOPPING_DESTINATION_POSTCODE=2155
PYTHONPATH=staging/agents/shopping-agent:staging/agents/shopping-agent/runtime \
  uv run python -m shopping_agent \
  --task 'Find me a 7-foot surf leash under $30 delivered to my house.' \
  --postcode 2155
```

The key is read from the configured environment variable and is never written
to results or telemetry. Configuration is available through `SHOPPING_*`
environment variables, including the SerpApi endpoint, key-variable name,
location, call budgets, page budgets, timeout, and destination.

The universal Agent Hub JSON envelope is also accepted with `--input-json`
and `--output-json`. The package remains staged/manual and is not callable by
Agent Hub until a separate human-approved promotion updates `config/agents`.

Do not move this package to `config/agents` without human approval.
