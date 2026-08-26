import json

import pytest

from agent_factory import design_research
from agent_factory.factory_tools import get_factory_tools
from agent_factory.storage import claim_approved_approval, create_approval, decide_approval, get_approval


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

    monkeypatch.setattr(
        "agent_factory.storage.claim_approved_approval",
        lambda approval_id, approval_type: approval_id == 9 and approval_type == "design-research",
    )

    def fake_finalise(approval_id, status, reason):
        consumed.update(id=approval_id, status=status, reason=reason)

    monkeypatch.setattr("agent_factory.storage.finalise_claimed_approval", fake_finalise)

    result = design_research.run_design_research.invoke({"approval_id": 9})
    assert result == '{"answer": "supported"}'
    assert consumed["id"] == 9
    assert consumed["status"] == "consumed"


def test_claim_approved_approval_allows_only_one_research_execution():
    approval_id = create_approval("design-research", "factory-design", "{}")
    decide_approval(approval_id, "approved", "Approved for test")

    assert claim_approved_approval(approval_id, "design-research") is True
    assert claim_approved_approval(approval_id, "design-research") is False
    assert get_approval(approval_id)["status"] == "claimed"


def test_run_design_research_refuses_a_claim_lost_to_another_worker(monkeypatch):
    payload = json.dumps(
        {"question": "Does bpmn-js support BPMN 2.0 editing?", "allowed_domains": ["bpmn.io"]}
    )
    monkeypatch.setattr(
        "agent_factory.storage.get_approval",
        lambda approval_id: {"approval_type": "design-research", "status": "approved", "summary": payload},
    )
    monkeypatch.setattr("agent_factory.storage.claim_approved_approval", lambda *_args: False)
    monkeypatch.setattr(
        design_research,
        "_invoke_web_search",
        lambda *_args: pytest.fail("paid research must not run after losing the claim"),
    )

    result = design_research.run_design_research.invoke({"approval_id": 9})
    assert "approved" in result
    assert "research was not run" in result


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
        usage_metadata = {"input_tokens": 17, "output_tokens": 9, "total_tokens": 26}
        response_metadata = {"finish_reason": "stop"}
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
    recorded = {}
    monkeypatch.setattr(
        "agent_factory.cost_log.record_llm_run", lambda **kwargs: recorded.update(kwargs)
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
    assert recorded["operation"] == "live_design_research"
    assert recorded["request_kind"] == "approved-design-research"
    assert recorded["usage_by_model"]["openai:gpt-4.1-mini"].total_tokens == 26
    assert recorded["stop_reason"] == "stop"


def test_web_search_records_a_failed_model_call(monkeypatch):
    class FailingChatOpenAI:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("provider timeout")

    recorded = {}
    monkeypatch.setattr("langchain_openai.ChatOpenAI", FailingChatOpenAI)
    monkeypatch.setattr(
        "agent_factory.factory_settings.resolve_model",
        lambda purpose="general": "openai:gpt-4.1-mini",
    )
    monkeypatch.setattr(
        "agent_factory.cost_log.record_llm_run", lambda **kwargs: recorded.update(kwargs)
    )

    with pytest.raises(RuntimeError, match="provider timeout"):
        design_research._invoke_web_search("Does bpmn-js support BPMN editing?", ["bpmn.io"])

    assert recorded["status"] == "error"
    assert recorded["error"] == "provider timeout"
    assert recorded["stop_reason"] == "unknown"
