import json

import pytest

from agent_factory import design_research
from agent_factory.factory_tools import get_factory_tools


def test_factory_exposes_design_research_tools():
    names = {tool.name for tool in get_factory_tools()}
    assert "request_design_research" in names
    assert "run_design_research" in names


def test_request_design_research_records_exact_bounded_payload(monkeypatch):
    captured = {}

    def fake_create_approval(approval_type, target_id, summary):
        captured.update(
            approval_type=approval_type,
            target_id=target_id,
            summary=summary,
        )
        return 41

    monkeypatch.setattr("agent_factory.storage.create_approval", fake_create_approval)

    result = design_research.request_design_research.invoke(
        {
            "question": "Which official library supports editable BPMN 2.0 XML round-tripping?",
            "allowed_domains": ["https://bpmn.io/docs/", "github.com"],
        }
    )

    assert "#41" in result
    assert "No network request has run" in result
    assert captured["approval_type"] == "design-research"
    payload = json.loads(captured["summary"])
    assert payload["allowed_domains"] == ["bpmn.io", "github.com"]
    assert payload["question"].startswith("Which official library")


def test_run_design_research_refuses_unapproved_request(monkeypatch):
    monkeypatch.setattr(
        "agent_factory.storage.get_approval",
        lambda approval_id: {
            "approval_type": "design-research",
            "status": "pending",
            "summary": "{}",
        },
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("network research must not run before approval")

    monkeypatch.setattr(design_research, "_invoke_web_search", should_not_run)

    result = design_research.run_design_research.invoke({"approval_id": 7})
    assert "pending" in result
    assert "research was not run" in result


def test_run_design_research_consumes_approval_after_one_success(monkeypatch):
    payload = json.dumps(
        {
            "question": "Does bpmn-js support BPMN 2.0 editing?",
            "allowed_domains": ["bpmn.io"],
        }
    )
    monkeypatch.setattr(
        "agent_factory.storage.get_approval",
        lambda approval_id: {
            "approval_type": "design-research",
            "status": "approved",
            "summary": payload,
        },
    )
    monkeypatch.setattr(
        design_research,
        "_invoke_web_search",
        lambda question, domains: '{"answer": "supported"}',
    )
    consumed = {}

    def fake_decide(approval_id, decision, reason=""):
        consumed.update(id=approval_id, decision=decision, reason=reason)

    monkeypatch.setattr("agent_factory.storage.decide_approval", fake_decide)

    result = design_research.run_design_research.invoke({"approval_id": 9})
    assert result == '{"answer": "supported"}'
    assert consumed["id"] == 9
    assert consumed["decision"] == "consumed"


def test_domain_limits_fail_closed():
    with pytest.raises(ValueError, match="At least one explicit allowed domain"):
        design_research._normalise_domains([])

    with pytest.raises(ValueError, match="limited to"):
        design_research._normalise_domains(
            ["a.example.com", "b.example.com", "c.example.com", "d.example.com", "e.example.com", "f.example.com"]
        )


def test_citations_are_deduplicated_filtered_and_bounded():
    blocks = [
        {
            "type": "text",
            "annotations": [
                {"type": "citation", "title": "A", "url": "https://docs.example.com/a"},
                {"type": "citation", "title": "A again", "url": "https://docs.example.com/a"},
                {"type": "citation", "title": "Blocked", "url": "https://other.example.net/x"},
                {"type": "citation", "title": "B", "url": "https://sub.docs.example.com/b"},
            ],
        }
    ]
    citations = design_research._extract_citations(blocks, ["docs.example.com"])
    assert citations == [
        {"title": "A", "url": "https://docs.example.com/a"},
        {"title": "B", "url": "https://sub.docs.example.com/b"},
    ]


def test_web_search_tool_is_domain_filtered_and_low_context(monkeypatch):
    captured = {}

    class FakeResponse:
        text = "Evidence"
        content_blocks = [
            {
                "type": "text",
                "annotations": [
                    {
                        "type": "citation",
                        "title": "Official",
                        "url": "https://bpmn.io/toolkit/bpmn-js/",
                    }
                ],
            }
        ]

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def invoke(self, prompt, tools):
            captured["prompt"] = prompt
            captured["tools"] = tools
            return FakeResponse()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(
        "agent_factory.factory_settings.resolve_model",
        lambda purpose="general": "openai:gpt-4.1-mini",
    )

    result = json.loads(
        design_research._invoke_web_search(
            "Does bpmn-js support BPMN editing?",
            ["bpmn.io"],
        )
    )

    assert captured["init"]["use_responses_api"] is True
    assert captured["init"]["max_retries"] == 1
    assert captured["tools"] == [
        {
            "type": "web_search",
            "filters": {"allowed_domains": ["bpmn.io"]},
            "search_context_size": "low",
        }
    ]
    assert result["source_count"] == 1
    assert result["citations"][0]["url"].startswith("https://bpmn.io/")
