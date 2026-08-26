"""Contract tests for the Agent Factory design-interview skill.

These tests keep the evidence/research gate explicit so a future prompt or docs
cleanup cannot quietly regress Factory back to assumption-driven design.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
SKILL = PROJECT_ROOT / "skills" / "agent-design-interview" / "SKILL.md"
WORKFLOW_DOC = PROJECT_ROOT / "docs" / "agent-creator-workflow.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_design_interview_requires_one_precise_knowledge_gap() -> None:
    text = _read(SKILL)

    assert "Name one precise knowledge gap" in text
    assert "one unresolved knowledge gap at a time" in text
    assert "Do not research a broad topic" in text


def test_design_interview_is_local_first_and_stops_when_evidence_is_weak() -> None:
    text = _read(SKILL)

    assert "Check existing evidence first" in text
    assert "Request approval before network access" in text
    assert "Conflicting or insufficient evidence is a stop condition" in text
    assert "rather than guessing" in text


def test_design_review_surfaces_evidence_and_open_gaps() -> None:
    text = _read(SKILL)

    assert "Evidence-backed technical decisions" in text
    assert "Open questions, if any" in text
    assert "unresolved evidence gap" in text


def test_workflow_docs_describe_bounded_live_research_controls() -> None:
    text = _read(WORKFLOW_DOC)

    assert "use `search_memory` and `search_trusted_sources` first" in text
    assert "`request_design_research`" in text
    assert "`run_design_research`" in text
    assert "performs no network access" in text
    assert "enforced `allowed_domains` filter" in text
    assert "atomically marks the approval `claimed`" in text
    assert "records `consumed` on success or `failed` on an error" in text
