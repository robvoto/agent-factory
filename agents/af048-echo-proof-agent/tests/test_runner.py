import json

from run_agent import main, process_payload


def test_process_payload_preserves_whitespace_unicode_and_newlines():
    task = "  hello\n🌱  "

    assert process_payload({"task": task}) == {
        "status": "success",
        "summary": "Echo: " + task,
    }


def test_process_payload_accepts_current_hub_context_envelope():
    task = "  hello\n🌱  "
    payload = {
        "task": task,
        "task_kind": "coding_task",
        "project_context": {"schema_version": "1.0"},
        "backlog_reference": {"id": "AF-048"},
        "governed_skills": [],
        "execution_constraints": {},
    }

    assert process_payload(payload) == {
        "status": "success",
        "summary": "Echo: " + task,
    }


def test_process_payload_rejects_invalid_task():
    assert process_payload({"task": "  "}) == {
        "status": "failed",
        "summary": "A non-empty task is required.",
    }


def test_process_payload_rejects_unsupported_fields():
    result = process_payload({"task": "hello", "unexpected": True})

    assert result["status"] == "failed"
    assert result["summary"] == "Unsupported task fields: unexpected"


def test_main_uses_hub_json_file_contract(tmp_path):
    task = "  hello\n🌱  "
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(
        json.dumps({"task": task}, ensure_ascii=False), encoding="utf-8"
    )

    assert main(["--input-json", str(input_path), "--output-json", str(output_path)]) == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "status": "success",
        "summary": "Echo: " + task,
    }


def test_manifest_mode_emits_stable_hub_metadata(capsys):
    from run_agent import build_manifest

    assert main(["--manifest"]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted == build_manifest()
    assert emitted["agent_id"] == "af048-echo-proof-agent"
    assert emitted["package_version"] == "1.0.1"
    assert len(emitted["manifest_hash"]) == 64
    assert main(["--manifest"]) == 0
    assert json.loads(capsys.readouterr().out) == emitted
