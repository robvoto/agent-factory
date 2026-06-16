import json
from pathlib import Path


def test_agent_package_template_files_exist():
    template_dir = Path("templates/agent-package")
    required_files = [
        "AGENTS.md",
        "agent.json",
        "SYSTEM.md",
        "tools.json",
        "permissions.json",
        "memory.json",
        "README.md",
        "skills/INDEX.md",
        "tests/.gitkeep",
    ]

    for relative_path in required_files:
        assert (template_dir / relative_path).is_file(), relative_path


def test_agent_package_template_manifest_shape():
    template_dir = Path("templates/agent-package")
    manifest = json.loads((template_dir / "agent.json").read_text(encoding="utf-8"))

    assert manifest["runtime"]["mode"] == "manual"
    assert manifest["permissions"]["requires_approval"] is True
    assert manifest["memory"]["scope"] == "none"
    assert manifest["tools"] == []


def test_agent_package_template_instructions_are_seeded():
    template_dir = Path("templates/agent-package")
    agents = (template_dir / "AGENTS.md").read_text(encoding="utf-8")
    skills_index = (template_dir / "skills" / "INDEX.md").read_text(encoding="utf-8")

    assert "smallest change" in agents
    assert "apply_patch" in agents
    assert "does not define agent-specific skills yet" in skills_index
