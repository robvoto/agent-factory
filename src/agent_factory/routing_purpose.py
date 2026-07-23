"""Canonical routing-purpose contract for registered specialist agents."""

from __future__ import annotations

import re

PRIMARY_LABEL = "Primary responsibility:"
SELECT_LABEL = "Select for:"
EXCLUDE_LABEL = "Do not select for:"
MAX_PURPOSE_CHARS = 1200

_PATTERN = re.compile(
    rf"^{re.escape(PRIMARY_LABEL)}\s*(?P<primary>.+?)\n"
    rf"{re.escape(SELECT_LABEL)}\s*(?P<select>.+?)\n"
    rf"{re.escape(EXCLUDE_LABEL)}\s*(?P<exclude>.+)$",
    re.DOTALL,
)


def build_routing_purpose(*, primary: str, select_for: str, do_not_select_for: str) -> str:
    """Build the single canonical routing description stored in agent.json purpose."""

    return (
        f"{PRIMARY_LABEL} {_clean_section(primary)}\n"
        f"{SELECT_LABEL} {_clean_section(select_for)}\n"
        f"{EXCLUDE_LABEL} {_clean_section(do_not_select_for)}"
    )


def validate_routing_purpose(value: str) -> str:
    """Validate and normalize the routing-purpose contract.

    Routing must have one source of truth. A vague sentence is rejected rather
    than accepted as a legacy fallback.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("Agent purpose cannot be empty.")
    normalized = value.strip().replace("\r\n", "\n")
    if len(normalized) > MAX_PURPOSE_CHARS:
        raise ValueError(f"Agent purpose must be {MAX_PURPOSE_CHARS} characters or less.")

    match = _PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            "Agent purpose must use exactly three routing sections: "
            "'Primary responsibility:', 'Select for:', and 'Do not select for:'."
        )

    sections = {name: _clean_section(text) for name, text in match.groupdict().items()}
    if any(len(text) < 12 for text in sections.values()):
        raise ValueError("Each agent purpose routing section must contain meaningful detail.")
    if sections["select"].casefold() == sections["exclude"].casefold():
        raise ValueError("'Select for' and 'Do not select for' must describe different scopes.")

    return build_routing_purpose(
        primary=sections["primary"],
        select_for=sections["select"],
        do_not_select_for=sections["exclude"],
    )


def _clean_section(value: str) -> str:
    return " ".join(str(value).split()).strip()
