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
        "docs/INDEX.md",
        "data/README.md",
        "logs/.gitkeep",
        ".gitignore",
        ".env.example",
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
    assert set(manifest["design"]) == {"runtime_pattern", "runtime_pattern_reason"}


def test_agent_package_template_instructions_are_seeded():
    template_dir = Path("templates/agent-package")
    agents = (template_dir / "AGENTS.md").read_text(encoding="utf-8")
    skills_index = (template_dir / "skills" / "INDEX.md").read_text(encoding="utf-8")

    assert "smallest change" in agents
    assert "apply_patch" in agents
    assert "does not define agent-specific skills yet" in skills_index
    assert "propose one of: a bounded code change" in agents
    assert "may improve its own reusable skills or `AGENTS.md` without separate approval" in agents
    assert "Do not modify manifests, permissions, memory access, tools, runtime authority, or promotion state" in agents
    assert "explicit human approval" in agents
    assert "pass relevant tests before activation" in agents
    assert agents.count("docs/INDEX.md") == 1
    data = (template_dir / "data" / "README.md").read_text(encoding="utf-8")
    assert "small, reviewed source seeds" in data
    assert "may also live here" in data
    assert "must never be committed" in data
    gitignore = (template_dir / ".gitignore").read_text(encoding="utf-8")
    assert "data/*.json" not in gitignore
    assert "data/settings.local*.json" in gitignore
    assert "AGENT_RUNTIME_MODE" not in (template_dir / ".env.example").read_text(encoding="utf-8")
