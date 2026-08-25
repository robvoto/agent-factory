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
    assert "Online research requires explicit approval" in text
    assert "Conflicting or insufficient evidence is a stop condition" in text
    assert "rather than guessing" in text


def test_design_review_surfaces_evidence_and_open_gaps() -> None:
    text = _read(SKILL)

    assert "Evidence-backed technical decisions" in text
    assert "Open questions, if any" in text
    assert "unresolved evidence gap" in text


def test_workflow_docs_do_not_claim_live_online_research_before_it_exists() -> None:
    text = _read(WORKFLOW_DOC)

    assert "The current Factory Brain can search its indexed local/trusted knowledge" in text
    assert "A live online-research capability must itself be bounded and approval-gated" in text
    assert "Factory must report the evidence gap rather than pretending the research happened" in text
