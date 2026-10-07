"""Shared standard workspace scaffolding for generated agent packages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from string import Template


def render_template(text: str, replacements: dict[str, str]) -> str:
    """Render the package template's ``{{name}}`` placeholders safely."""

    normalized = text
    for key in replacements:
        normalized = normalized.replace("{{" + key + "}}", "${" + key + "}")
    return Template(normalized).safe_substitute(replacements)


def copy_standard_workspace(
    template_dir: Path,
    package_dir: Path,
    replacements: dict[str, str],
) -> None:
    """Copy the complete common package workspace from the canonical template."""

    for template_file in template_dir.rglob("*"):
        relative = template_file.relative_to(template_dir)
        target = package_dir / relative

        if template_file.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if template_file.name == ".gitkeep":
            shutil.copyfile(template_file, target)
            continue

        file_replacements = replacements
        if relative == Path("agent.json"):
            file_replacements = {
                key: json.dumps(value)[1:-1]
                for key, value in replacements.items()
            }
        rendered = render_template(template_file.read_text(encoding="utf-8"), file_replacements)
        target.write_text(rendered, encoding="utf-8", newline="\n")
