# Shopping Agent backlog

**Owner:** Shopping Agent package, not the Agent Factory platform or Agent Hub.
**Status:** Planned product work. This file is not a runtime instruction or permission to alter behavior.

This Git-tracked backlog stays with the staged package, then the released package, and later with a separate Shopping repository if graduation is approved. Factory's platform backlog remains separately governed. Review changes through the normal Git and approval workflow. Never store personal orders, addresses, credentials or session details here.

## SHOP-001 — Product reality checks (High; before Shopping promotion where approved)

**Problem:** A Temu cream product was smaller than expected, a periodic table was only a printed picture, and a car was a tiny model; a surf leash was a genuine bargain.

**Acceptance:** Verify the offered physical product/category against the user's intent, the exact priced variant, and materially relevant size/scale/volume/weight/pack quantity using direct retailer evidence. A confirmed mismatch is FAIL; a material unknown is UNVERIFIED rather than a verified bargain. Show compact details and prominent warnings where relevant, not a full dimension dump for every product. Test the three Temu cases and genuine bargain surf leash offline. Reuse existing product verification; first check what AF-058 already covers. No new agent, platform logic or speculative fraud scoring.

## SHOP-002 — Free and low-cost shopping data sources (High; after MVP)

**Goal:** Prefer practical free sources before paid services, without falsely claiming that search results verify actual stock, variant or delivered price.

**Acceptance:** Revalidate official quotas, terms, access prerequisites, Australian coverage and provider costs before implementation. Evaluate the existing Google Shopping/SerpApi discovery adapter and its free allowance first; verify using permitted direct retailer Product/Offer evidence. Consider Open Food Facts for useful packaged-food product details. Evaluate eBay developer access separately; Amazon's gated affiliate APIs are not a general free consumer-search dependency. Use optional specialist-owned provider adapters, not hardcoded provider behavior in Factory or Hub. Do not scrape against site restrictions, bypass authentication or require paid subscriptions for the MVP. Preserve UNVERIFIED if mandatory retailer/delivery evidence is missing.

## SHOP-003 — Advanced misleading-listing analysis (Later)

Investigate customer-photo size/scale checks, misleading-image detection, reviews and cross-source comparisons if measurable reliability benefits justify complexity and cost. Do not promise fraud detection guarantees.

## SHOP-004 — Price history, alerts and purchasing (Later)

Evaluate trustworthy pricing history and optional alerts separately. Purchasing, checkout and account/order changes require a distinct approval and are outside the read-only shopping MVP.

## Dependencies and ownership

- AF-048 is closed. AF-058 is the active Shopping MVP implementation; do not interfere with its worktrees or BuildResult acceptance.
- Audit accepted AF-058 before implementing SHOP-001; obtain explicit approval for semantic changes. Where possible, test SHOP-001 before promotion.
- Agent Factory owns manufacturing, review, release and registry promotion; Shopping owns shopping logic, provider selection and this backlog; Hub owns routing and Telegram interaction.
- AF-059 in the Factory Google Sheet is a cross-reference to SHOP-001, not authorization to put Shopping-specific logic into Factory.

## Source

User's self-sent email, 16 October 2026, about Temu size/type disappointments and the surf leash. Current Shopping package README.md, SYSTEM.md, REVIEW.md and agent.json remain the implementation/contract references.
