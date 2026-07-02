"""Tests for diagram source, preview, and documentation parity."""

from pathlib import Path


def test_diagram_assets_have_expected_companions_and_index_links():
    diagrams_dir = Path("docs/diagrams")
    numbered = [
        "01-SYSTEM-OVERVIEW",
        "02-AGENT-LIFECYCLE",
        "03-TELEGRAM-FLOWS",
        "04-KNOWLEDGE-FLOW",
    ]

    for stem in numbered:
        assert (diagrams_dir / f"{stem}.md").is_file(), stem
        assert (diagrams_dir / f"{stem}.mmd").is_file(), stem
        assert (diagrams_dir / f"{stem}.svg").is_file(), stem

    assert (diagrams_dir / "07-AGENT-FACTORY-BPMN.md").is_file()
    assert (diagrams_dir / "07-AGENT-FACTORY-BPMN.bpmn").is_file()
    assert (diagrams_dir / "07-AGENT-FACTORY-BPMN.svg").is_file()

    index = (diagrams_dir / "INDEX.md").read_text(encoding="utf-8")
    for stem in numbered:
        assert f"{stem}.md" in index
    for suffix in ["07-AGENT-FACTORY-BPMN.md", "07-AGENT-FACTORY-BPMN.bpmn", "07-AGENT-FACTORY-BPMN.svg"]:
        assert suffix in index


def test_render_script_uses_local_renderer():
    script = Path("docs/diagrams/render.sh").read_text(encoding="utf-8")

    assert "mermaid.ink" not in script
    assert "jsdom" in script
    assert "local jsdom + Mermaid" in script
    assert "requires Node.js 20.19+" in script
    assert "process.exit(1)" in script
