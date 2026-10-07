"""Fail-closed extraction of explicit shopping constraints.

The parser recognises a deliberately small set of explicit forms used by the
approved MVP benchmark (for example ``7-foot`` and ``under $30``).  It only
produces retrieval hints from the remaining words; retailer evidence, not
this parser, controls the final PASS/FAIL/UNVERIFIED result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import ShoppingConstraints

_LENGTH_RE = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(?:-\s*)?(?:foot|feet|ft|')\b", re.IGNORECASE
)
_BUDGET_RE = re.compile(
    r"\b(?P<operator>under|below|less\s+than|up\s+to|max(?:imum)?(?:\s+of)?)\s*"
    r"(?:AUD\s*)?\$?\s*(?P<value>\d+(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)
_POSTCODE_RE = re.compile(
    r"\b(?:postcode|post\s*code|zip)\s*[:#]?\s*(\d{4})\b", re.IGNORECASE
)
_AUSTRALIA_RE = re.compile(r"\b(?:australia|australian|au)\b", re.IGNORECASE)


class ConstraintClarification(ValueError):
    """Raised when an explicit mandatory constraint is absent or contradictory."""


@dataclass(frozen=True)
class ParsedRequest:
    constraints: ShoppingConstraints | None
    clarification_question: str | None = None


def _unique_decimal_matches(pattern: re.Pattern[str], text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in pattern.finditer(text):
        try:
            raw_value = match.groupdict().get("value") or match.group(1)
            value = Decimal(raw_value)
        except InvalidOperation as exc:
            raise ConstraintClarification("A numeric constraint could not be read safely.") from exc
        if value not in values:
            values.append(value)
    return values


def _product_terms(text: str, *, postcode: str | None) -> str:
    value = text.lower()
    value = _LENGTH_RE.sub(" ", value)
    value = _BUDGET_RE.sub(" ", value)
    value = _POSTCODE_RE.sub(" ", value)
    if postcode:
        value = re.sub(rf"\b{re.escape(postcode)}\b", " ", value)
    value = _AUSTRALIA_RE.sub(" ", value)
    value = re.sub(
        r"\b(?:find|show|me|please|get|buy|look\s+for|available|sold|in|to|my|house|"
        r"delivered|delivery|here|under|for|the|a|an)\b",
        " ",
        value,
    )
    return " ".join(value.split())


def parse_request(
    text: str,
    *,
    destination_postcode: str | None,
    destination_country: str = "AU",
) -> ParsedRequest:
    if not isinstance(text, str) or not text.strip():
        return ParsedRequest(None, "What product, exact variant, and delivered budget should I use?")

    lengths = _unique_decimal_matches(_LENGTH_RE, text)
    budget_matches = list(_BUDGET_RE.finditer(text))
    budgets = _unique_decimal_matches(_BUDGET_RE, text)
    postcode_matches = [match.group(1) for match in _POSTCODE_RE.finditer(text)]
    if postcode_matches and len(set(postcode_matches)) > 1:
        return ParsedRequest(None, "Which destination postcode should I use?")
    postcode = postcode_matches[0] if postcode_matches else destination_postcode

    if len(lengths) != 1:
        return ParsedRequest(None, "What exact product length should I verify?")
    budget_operators = {
        "lt" if match.group("operator").lower() in {"under", "below", "less than"} else "lte"
        for match in budget_matches
    }
    if len(budgets) != 1 or len(budget_operators) != 1:
        return ParsedRequest(None, "What is the maximum delivered price?")
    if not postcode:
        return ParsedRequest(None, "What destination postcode should I use for delivery verification?")
    if not re.fullmatch(r"\d{4}", postcode):
        return ParsedRequest(None, "The destination postcode must be four digits.")

    terms = _product_terms(text, postcode=postcode)
    if not terms:
        return ParsedRequest(None, "What product should I search for?")
    if destination_country.upper() != "AU":
        return ParsedRequest(None, "The MVP currently supports Australian delivery verification only.")

    return ParsedRequest(
        ShoppingConstraints(
            original_request=text.strip(),
            product_terms=terms,
            exact_length_feet=lengths[0],
            max_delivered_price_aud=budgets[0],
            budget_operator=next(iter(budget_operators)),
            destination_country=destination_country.upper(),
            destination_postcode=postcode,
        )
    )


def query_plan(constraints: ShoppingConstraints, *, max_queries: int) -> list[str]:
    """Create bounded retrieval variants without changing authoritative meaning."""

    exact = f"{constraints.exact_length_feet:g} foot {constraints.product_terms} Australia"
    variants = [
        exact,
        (
            f"{constraints.exact_length_feet:g}ft {constraints.product_terms} Australia "
            f"{constraints.destination_postcode}"
        ),
        f"{exact} delivery",
    ]
    return list(dict.fromkeys(variants))[:max_queries]
