"""Explicit, environment-backed Shopping Agent configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


class MissingCredentialError(RuntimeError):
    """Raised when the configured discovery provider has no secret."""


def _int_env(env: dict[str, str], name: str, default: int, *, minimum: int = 0) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return value


@dataclass(frozen=True)
class ShoppingBudget:
    max_search_calls: int = 3
    max_api_calls: int = 3
    max_page_fetches: int = 6
    max_browser_pages: int = 0
    max_browser_actions: int = 0
    max_retries: int = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ShoppingBudget:
        values = dict(os.environ) if env is None else env
        return cls(
            max_search_calls=_int_env(values, "SHOPPING_MAX_SEARCH_CALLS", 3, minimum=1),
            max_api_calls=_int_env(values, "SHOPPING_MAX_API_CALLS", 3, minimum=1),
            max_page_fetches=_int_env(values, "SHOPPING_MAX_PAGE_FETCHES", 6, minimum=0),
            max_browser_pages=_int_env(values, "SHOPPING_MAX_BROWSER_PAGES", 0, minimum=0),
            max_browser_actions=_int_env(values, "SHOPPING_MAX_BROWSER_ACTIONS", 0, minimum=0),
            max_retries=_int_env(values, "SHOPPING_MAX_RETRIES", 0, minimum=0),
        )


@dataclass(frozen=True)
class ShoppingConfig:
    serpapi_endpoint: str = "https://serpapi.com/search.json"
    serpapi_api_key_env: str = "SERPAPI_API_KEY"
    serpapi_location: str = "Sydney, New South Wales, Australia"
    serpapi_google_domain: str = "google.com.au"
    serpapi_country: str = "au"
    serpapi_language: str = "en"
    destination_country: str = "AU"
    destination_postcode: str | None = None
    request_timeout_seconds: float = 15.0
    budget: ShoppingBudget = ShoppingBudget()

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ShoppingConfig:
        values = dict(os.environ) if env is None else env
        return cls(
            serpapi_endpoint=values.get("SHOPPING_SERPAPI_ENDPOINT", cls.serpapi_endpoint),
            serpapi_api_key_env=values.get(
                "SHOPPING_SERPAPI_API_KEY_ENV", cls.serpapi_api_key_env
            ),
            serpapi_location=values.get("SHOPPING_SERPAPI_LOCATION", cls.serpapi_location),
            serpapi_google_domain=values.get(
                "SHOPPING_SERPAPI_GOOGLE_DOMAIN", cls.serpapi_google_domain
            ),
            serpapi_country=values.get("SHOPPING_SERPAPI_COUNTRY", cls.serpapi_country),
            serpapi_language=values.get("SHOPPING_SERPAPI_LANGUAGE", cls.serpapi_language),
            destination_country=values.get("SHOPPING_DESTINATION_COUNTRY", cls.destination_country),
            destination_postcode=values.get("SHOPPING_DESTINATION_POSTCODE"),
            request_timeout_seconds=float(
                values.get("SHOPPING_REQUEST_TIMEOUT_SECONDS", "15")
            ),
            budget=ShoppingBudget.from_env(values),
        )

    def api_key(self, env: dict[str, str] | None = None) -> str:
        values = dict(os.environ) if env is None else env
        key = values.get(self.serpapi_api_key_env, "").strip()
        if not key:
            raise MissingCredentialError(
                f"SerpApi credential is missing from configured environment variable "
                f"{self.serpapi_api_key_env}."
            )
        return key
