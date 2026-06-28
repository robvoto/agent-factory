"""Tests for documentation and governance link parity."""

import re
from pathlib import Path
from urllib.parse import urlsplit


LINK_PATTERN = re.compile(r"(?<!\!)\[[^\]]+\]\(([^)]+)\)")


def iter_local_targets(markdown_text: str):
    for raw_target in LINK_PATTERN.findall(markdown_text):
        parts = urlsplit(raw_target)
        if parts.scheme or parts.netloc:
            continue
        target = parts.path.split("#", 1)[0].split("?", 1)[0]
        if target:
            yield target


def assert_markdown_links_resolve(markdown_path: Path):
    text = markdown_path.read_text(encoding="utf-8")
    for target in iter_local_targets(text):
        resolved = (markdown_path.parent / target).resolve()
        assert resolved.exists(), f"{markdown_path}: broken link -> {target}"


def test_docs_indexes_have_resolvable_internal_links():
    for relative_path in [
        "docs/INDEX.md",
        "docs/diagrams/INDEX.md",
        "docs/instruction-governance.md",
    ]:
        assert_markdown_links_resolve(Path(relative_path))


def test_instruction_governance_doc_describes_scoped_model():
    text = Path("docs/instruction-governance.md").read_text(encoding="utf-8")

    for phrase in [
        "Repo root",
        "Nested `AGENTS.md` files",
        "Factory Brain instructions",
        "Staged agent scaffold",
        "Skills hold repeatable procedures",
        "approval-gated help",
        "fail closed",
    ]:
        assert phrase in text


def test_permission_review_skill_blocks_fallback_shims():
    text = Path("skills/permission-review/SKILL.md").read_text(encoding="utf-8")

    for phrase in [
        "Fallback code, compatibility shims, silent defaults, degraded behaviour, workarounds, and hardcoded replacements",
        "Upstream dependency changes that would silently change product semantics",
        "fallback, temporary, compatibility shim, workaround, safe default, best effort, or degraded behaviour",
        "List the fallback, shim, or workaround in REVIEW.md",
    ]:
        assert phrase in text
