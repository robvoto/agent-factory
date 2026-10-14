"""Semantic version and deterministic package-diff helpers for releases."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def version_key(value: str) -> tuple:
    """Return a SemVer 2.0 precedence key; build metadata does not affect order."""
    match = _VERSION.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid semantic version {value!r}; expected MAJOR.MINOR.PATCH[-prerelease][+build].")
    major, minor, patch, prerelease, _build = match.groups()
    if prerelease is None:
        prerelease_key: tuple = (1, ())
    else:
        identifiers = tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in prerelease.split(".")
        )
        prerelease_key = (0, identifiers)
    return int(major), int(minor), int(patch), prerelease_key


def require_newer_version(staged: str, active: str) -> None:
    if version_key(staged) <= version_key(active):
        raise ValueError(f"Staged version {staged} must be newer than active version {active}.")


def package_sha256(package_dir: Path) -> str:
    """Hash all package paths and contents, excluding Factory build control files."""
    digest = hashlib.sha256()
    ignored = {"BUILD_TASK.json", "BUILD_RESULT.json"}
    for path in sorted(path for path in package_dir.rglob("*") if path.is_file()):
        if path.name in ignored:
            continue
        relative = path.relative_to(package_dir).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def package_diff(before: Path | None, after: Path, *, max_chars: int = 7000) -> str:
    """Render changed file paths and unified text diffs for a staged package."""
    import difflib

    old_files = _package_files(before) if before is not None else {}
    new_files = _package_files(after)
    changed = sorted(path for path in old_files.keys() | new_files.keys() if old_files.get(path) != new_files.get(path))
    if not changed:
        return "No package file changes."
    lines = ["Changed package files:"]
    for name in changed:
        if name not in old_files:
            lines.append(f"+ {name}")
        elif name not in new_files:
            lines.append(f"- {name}")
        else:
            lines.append(f"~ {name}")
        old_text = old_files.get(name, b"").decode("utf-8", errors="replace").splitlines(keepends=True)
        new_text = new_files.get(name, b"").decode("utf-8", errors="replace").splitlines(keepends=True)
        if old_text != new_text:
            lines.extend(difflib.unified_diff(old_text, new_text, fromfile=f"enabled/{name}", tofile=f"staged/{name}"))
        rendered = "\n".join(lines)
        if len(rendered) >= max_chars:
            return rendered[: max_chars - 32] + "\n… diff truncated; review the staged package."
    return "\n".join(lines).rstrip()


def _package_files(package_dir: Path | None) -> dict[str, bytes]:
    if package_dir is None or not package_dir.is_dir():
        return {}
    return {
        path.relative_to(package_dir).as_posix(): path.read_bytes()
        for path in package_dir.rglob("*")
        if path.is_file() and path.name not in {"BUILD_TASK.json", "BUILD_RESULT.json"}
    }
