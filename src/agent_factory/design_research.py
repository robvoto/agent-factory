"""Approval-gated, bounded live research for Agent Factory design decisions.

The Factory must first search its indexed local/trusted knowledge. This module is
only for one material design knowledge gap that remains unresolved.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import tool

_MAX_QUESTION_CHARS = 1200
_MAX_DOMAINS = 5
_MAX_CITATIONS = 5
_RESULT_PREVIEW_CHARS = 500
logger = logging.getLogger(__name__)


def _normalise_domains(raw_domains: list[str]) -> list[str]:
    domains: list[str] = []
    for raw in raw_domains:
        value = str(raw).strip().lower()
        if not value:
            continue
        parsed = urlparse(value if "://" in value else f"https://{value}")
        host = (parsed.hostname or "").strip(".")
        if not host or "." not in host:
            raise ValueError(f"Invalid research domain: {raw!r}")
        if host not in domains:
            domains.append(host)
    if not domains:
        raise ValueError("At least one explicit allowed domain is required for live research.")
    if len(domains) > _MAX_DOMAINS:
        raise ValueError(f"Live research is limited to {_MAX_DOMAINS} allowed domains per question.")
    return domains


def _validate_question(question: str) -> str:
    cleaned = str(question).strip()
    if not cleaned:
        raise ValueError("A precise design knowledge-gap question is required.")
    if len(cleaned) > _MAX_QUESTION_CHARS:
        raise ValueError(
            f"Design research question is too long; maximum is {_MAX_QUESTION_CHARS} characters."
        )
    return cleaned


def _approval_payload(question: str, allowed_domains: list[str]) -> str:
    return json.dumps(
        {
            "question": _validate_question(question),
            "allowed_domains": _normalise_domains(allowed_domains),
        },
        sort_keys=True,
    )


@tool
def request_design_research(question: str, allowed_domains: list[str]) -> str:
    """Request human approval for one bounded live design-research question.

    Use only after local and indexed trusted knowledge are insufficient. Supply
    the exact decision-relevant question and only official/primary domains that
    are relevant to it. The request does not perform network access.
    """
    from .storage import create_approval

    payload = _approval_payload(question, allowed_domains)
    approval_id = create_approval(
        approval_type="design-research",
        target_id="factory-design",
        summary=payload,
    )
    return (
        f"Design research approval #{approval_id} recorded. No network request has run. "
        f"Approve it before calling run_design_research."
    )


@tool
def run_design_research(approval_id: int) -> str:
    """Run one previously approved bounded live design-research request.

    The approval record fixes the exact question and allowed domains. An
    unapproved, rejected, already-consumed, malformed, or mismatched approval is
    refused rather than inferred or widened.
    """
    from .storage import claim_approved_approval, finalise_claimed_approval, get_approval

    approval = get_approval(int(approval_id))
    if not approval:
        return f"Design research approval #{approval_id} was not found."
    if approval.get("approval_type") != "design-research":
        return f"Approval #{approval_id} is not a design-research approval."
    status = str(approval.get("status", "")).strip().lower()
    if status != "approved":
        return f"Design research approval #{approval_id} is {status or 'not approved'}; research was not run."

    try:
        payload = json.loads(str(approval.get("summary", "")))
        question = _validate_question(payload["question"])
        allowed_domains = _normalise_domains(payload["allowed_domains"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return f"Design research approval #{approval_id} is malformed; research was not run: {exc}"

    if not claim_approved_approval(int(approval_id), "design-research"):
        current = get_approval(int(approval_id))
        current_status = str((current or {}).get("status", "not available")).strip().lower()
        return f"Design research approval #{approval_id} is {current_status}; research was not run."

    try:
        result = _invoke_web_search(question, allowed_domains)
    except Exception as exc:
        logger.exception("Design research approval %s failed after being claimed.", approval_id)
        finalise_claimed_approval(
            int(approval_id),
            "failed",
            f"Approved bounded design research failed after its single claimed attempt: {exc}",
        )
        return f"Design research approval #{approval_id} failed; research was not rerun: {exc}"

    finalise_claimed_approval(
        int(approval_id),
        "consumed",
        "Approved bounded design research executed once.",
    )
    return result


def _invoke_web_search(question: str, allowed_domains: list[str]) -> str:
    """Execute one OpenAI Responses API web-search call and return compact evidence."""
    from langchain_openai import ChatOpenAI

    from .factory_settings import resolve_model

    resolved = resolve_model(purpose="general")
    if not resolved.startswith("openai:"):
        raise RuntimeError(
            "Factory live design research currently requires an OpenAI model because "
            "the bounded implementation uses the OpenAI Responses API web-search tool."
        )
    model_name = resolved.removeprefix("openai:")
    llm = ChatOpenAI(model=model_name, use_responses_api=True, max_retries=1)
    web_tool = {
        "type": "web_search",
        "filters": {"allowed_domains": allowed_domains},
        "search_context_size": "low",
    }
    prompt = (
        "Answer exactly one technical design knowledge-gap question using only the "
        "allowed official/primary domains enforced by the web-search tool. Keep the "
        "result concise and decision-relevant. Separate supported facts from uncertainty. "
        "Do not expand into adjacent research questions. If the evidence is insufficient "
        "or conflicting, say so explicitly and stop.\n\n"
        f"Question: {question}"
    )
    started_at = perf_counter()
    try:
        response = llm.invoke(prompt, tools=[web_tool])
    except Exception as exc:
        _record_research_llm_run(
            resolved_model=resolved,
            duration_seconds=perf_counter() - started_at,
            status="error",
            error=str(exc),
        )
        raise

    _record_research_llm_run(
        resolved_model=resolved,
        duration_seconds=perf_counter() - started_at,
        status="ok",
        response=response,
    )
    citations = _extract_citations(response.content_blocks, allowed_domains)
    evidence = {
        "question": question,
        "allowed_domains": allowed_domains,
        "answer": response.text.strip(),
        "citations": citations,
        "source_count": len(citations),
    }
    return json.dumps(evidence, ensure_ascii=False, indent=2)


def _record_research_llm_run(
    *,
    resolved_model: str,
    duration_seconds: float,
    status: str,
    response: Any | None = None,
    error: str | None = None,
) -> None:
    """Write the required audit record for the bounded research model call."""
    from .cost_log import extract_usage_metadata, record_llm_run

    usage_metadata = getattr(response, "usage_metadata", None)
    usage_by_model = (
        extract_usage_metadata({resolved_model: usage_metadata})
        if isinstance(usage_metadata, Mapping)
        else {}
    )
    response_metadata = getattr(response, "response_metadata", None)
    stop_reason = _stop_reason(response_metadata)
    response_text = str(getattr(response, "text", "")).strip()

    record_llm_run(
        operation="live_design_research",
        request_kind="approved-design-research",
        requested_model=resolved_model,
        effective_model=resolved_model,
        status=status,
        duration_seconds=duration_seconds,
        usage_by_model=usage_by_model,
        error=error,
        result_preview=response_text[:_RESULT_PREVIEW_CHARS] or None,
        stop_reason=stop_reason,
    )


def _stop_reason(response_metadata: Any) -> str:
    if not isinstance(response_metadata, Mapping):
        return "unknown"
    for key in ("finish_reason", "stop_reason"):
        value = response_metadata.get(key)
        if value:
            return str(value)
    return "unknown"


def _extract_citations(content_blocks: list[dict], allowed_domains: list[str]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in content_blocks or []:
        if block.get("type") != "text":
            continue
        for annotation in block.get("annotations", []) or []:
            if annotation.get("type") != "citation":
                continue
            url = str(annotation.get("url", "")).strip()
            if not url or url in seen or not _url_on_allowed_domain(url, allowed_domains):
                continue
            seen.add(url)
            citations.append(
                {
                    "title": str(annotation.get("title", "")).strip(),
                    "url": url,
                }
            )
            if len(citations) >= _MAX_CITATIONS:
                return citations
    return citations


def _url_on_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)
