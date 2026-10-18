"""Structured run and provider telemetry with an allowlisted logging surface."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import urlsplit

from .models import ProviderUsage

_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_QUERY_SECRET = re.compile(r"(?i)([?&](?:api[_-]?key|key|token|auth|password|secret|session|cookie)=)[^&#\s]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|auth(?:orization)?|cookie|password|secret)\s*[:=]\s*[^,;\s]+"
)
_URL = re.compile(r"https?://[^\s\"'<>]+", re.I)
_SENSITIVE_NAMES = {"secret", "password", "cookie", "authorization", "credential", "token", "access_token", "auth_token", "auth", "api_key", "payment", "card", "account", "private", "raw"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return parsed.hostname.casefold()


def redact_log_payload(value: Any) -> Any:
    """Redact sensitive keys and secret-bearing strings before diagnostic logging."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            normalized = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
            parts = set(normalized.split("_"))
            sensitive = (
                normalized in _SENSITIVE_NAMES
                or bool(parts.intersection(_SENSITIVE_NAMES))
                or {"api", "key"}.issubset(parts)
            )
            result[name] = "[REDACTED]" if sensitive else redact_log_payload(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_log_payload(item) for item in value]
    if isinstance(value, str):
        safe = _BEARER.sub("Bearer [REDACTED]", value)
        safe = _QUERY_SECRET.sub(r"\1[REDACTED]", safe)
        safe = _SECRET_ASSIGNMENT.sub("[REDACTED]", safe)
        return _URL.sub(lambda match: _safe_url_text(match.group(0)), safe)
    return value


def _safe_url_text(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[URL REDACTED]"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "[URL REDACTED]"
    return f"{parsed.scheme}://{parsed.hostname.casefold()}"


@dataclass(frozen=True)
class CallTelemetry:
    run_id: str
    phase_or_node: str
    call_type: str
    provider_or_tool: str
    duration_ms: int
    status: str
    safe_domain_or_url: str | None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    estimated_cost_usd: Decimal | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase_or_node": self.phase_or_node,
            "call_type": self.call_type,
            "provider_or_tool": self.provider_or_tool,
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "estimated_cost_usd": _decimal_text(self.estimated_cost_usd),
            "duration_ms": self.duration_ms,
            "status": self.status,
            "safe_domain_or_url": self.safe_domain_or_url,
        }


@dataclass(frozen=True)
class RunTelemetry:
    request_id: str
    run_id: str
    started_at: str
    finished_at: str
    duration_ms: int
    stop_reason: str
    candidate_discovered_count: int
    pass_count: int
    fail_count: int
    unverified_count: int
    llm_call_count: int
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    estimated_cost_usd: Decimal | None
    search_call_count: int
    api_call_count: int
    page_fetch_count: int
    browser_page_count: int | None
    browser_action_count: int | None
    retry_count: int
    error_count: int
    exhausted_metric: str | None
    warnings: tuple[str, ...]
    calls: tuple[CallTelemetry, ...]
    provider_usage: Mapping[str, Mapping[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "stop_reason": self.stop_reason,
            "candidate_discovered_count": self.candidate_discovered_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "unverified_count": self.unverified_count,
            "llm_call_count": self.llm_call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "estimated_cost_usd": _decimal_text(self.estimated_cost_usd),
            "search_call_count": self.search_call_count,
            "api_call_count": self.api_call_count,
            "page_fetch_count": self.page_fetch_count,
            "browser_page_count": self.browser_page_count,
            "browser_action_count": self.browser_action_count,
            "retry_count": self.retry_count,
            "error_count": self.error_count,
            "exhausted_metric": self.exhausted_metric,
            "warnings": list(self.warnings),
            "calls": [call.as_dict() for call in self.calls],
            "provider_usage": {
                provider: {
                    **usage,
                    "estimated_cost_usd": _decimal_text(usage.get("estimated_cost_usd")),
                }
                for provider, usage in self.provider_usage.items()
            },
        }

    def log_record(self) -> dict[str, Any]:
        """Return telemetry only; request text, constraints, evidence, and provider payloads are omitted."""

        return redact_log_payload(self.as_dict())


class TelemetryBuilder:
    def __init__(self, request_id: str, run_id: str, started_at: datetime):
        self.request_id = request_id
        self.run_id = run_id
        self.started_at = started_at
        self.calls: list[CallTelemetry] = []
        self.search_call_count = 0
        self.api_call_count = 0
        self.page_fetch_count = 0
        self.browser_page_count: int | None = 0
        self.browser_action_count: int | None = 0
        self.retry_count = 0
        self.error_count = 0
        self._input_tokens: int | None = 0
        self._output_tokens: int | None = 0
        self._cached_tokens: int | None = 0
        self._cost: Decimal | None = Decimal("0")
        self.provider_usage: dict[str, dict[str, Any]] = {}

    def record_call(
        self,
        *,
        phase: str,
        call_type: str,
        provider: str,
        duration_ms: int,
        status: str,
        url: str | None,
        usage: ProviderUsage = ProviderUsage(),
        api_calls: int = 0,
    ) -> None:
        self.calls.append(
            CallTelemetry(
                run_id=self.run_id,
                phase_or_node=phase,
                call_type=call_type,
                provider_or_tool=provider,
                duration_ms=duration_ms,
                status=status,
                safe_domain_or_url=safe_domain(url),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_tokens=usage.cached_tokens,
                estimated_cost_usd=usage.estimated_cost_usd,
            )
        )
        if call_type == "search":
            self.search_call_count += 1
        self.api_call_count += api_calls
        if call_type == "page_fetch":
            self.page_fetch_count += 1
        if call_type == "browser":
            if usage.browser_pages is None:
                self.browser_page_count = None
            elif self.browser_page_count is not None:
                self.browser_page_count += usage.browser_pages
            if usage.browser_actions is None:
                self.browser_action_count = None
            elif self.browser_action_count is not None:
                self.browser_action_count += usage.browser_actions
        self.retry_count += usage.retries
        if status == "error":
            self.error_count += 1
        self._merge_optional("input_tokens", usage.input_tokens)
        self._merge_optional("output_tokens", usage.output_tokens)
        self._merge_optional("cached_tokens", usage.cached_tokens)
        self._merge_cost(usage.estimated_cost_usd)
        self._merge_provider(provider, usage, api_calls)

    def _merge_optional(self, field_name: str, value: int | None) -> None:
        attribute = f"_{field_name}"
        current = getattr(self, attribute)
        if value is None:
            setattr(self, attribute, None)
        elif current is not None:
            setattr(self, attribute, current + value)

    def _merge_cost(self, value: Decimal | None) -> None:
        if value is None:
            self._cost = None
        elif self._cost is not None:
            self._cost += value

    def _merge_provider(self, provider: str, usage: ProviderUsage, api_calls: int) -> None:
        current = self.provider_usage.setdefault(
            provider,
            {"call_count": 0, "api_call_count": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "estimated_cost_usd": Decimal("0")},
        )
        current["call_count"] += 1
        current["api_call_count"] += api_calls
        for field_name in ("input_tokens", "output_tokens", "cached_tokens"):
            value = getattr(usage, field_name)
            current[field_name] = None if value is None or current[field_name] is None else current[field_name] + value
        cost = usage.estimated_cost_usd
        current["estimated_cost_usd"] = None if cost is None or current["estimated_cost_usd"] is None else current["estimated_cost_usd"] + cost

    def finish(
        self,
        *,
        finished_at: datetime,
        stop_reason: str,
        candidate_discovered_count: int,
        pass_count: int,
        fail_count: int,
        unverified_count: int,
        exhausted_metric: str | None,
        warnings: tuple[str, ...],
        browser_page_count: int | None,
        browser_action_count: int | None,
    ) -> RunTelemetry:
        return RunTelemetry(
            request_id=self.request_id,
            run_id=self.run_id,
            started_at=self.started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=max(0, int((finished_at - self.started_at).total_seconds() * 1000)),
            stop_reason=stop_reason,
            candidate_discovered_count=candidate_discovered_count,
            pass_count=pass_count,
            fail_count=fail_count,
            unverified_count=unverified_count,
            llm_call_count=0,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cached_tokens=self._cached_tokens,
            estimated_cost_usd=self._cost,
            search_call_count=self.search_call_count,
            api_call_count=self.api_call_count,
            page_fetch_count=self.page_fetch_count,
            browser_page_count=browser_page_count,
            browser_action_count=browser_action_count,
            retry_count=self.retry_count,
            error_count=self.error_count,
            exhausted_metric=exhausted_metric,
            warnings=warnings,
            calls=tuple(self.calls),
            provider_usage=self.provider_usage,
        )


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")
