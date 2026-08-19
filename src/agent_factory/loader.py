"""Load and index agent manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .errors import DuplicateAliasError
from .models import AgentManifest
from .permissions import validate_tools


class AgentRegistry:
    """Alias index for configured agents."""

    def __init__(self, manifests: Iterable[AgentManifest]) -> None:
        self._agents_by_id: dict[str, AgentManifest] = {}
        self._aliases: dict[str, AgentManifest] = {}
        for manifest in manifests:
            self.add(manifest)

    def add(self, manifest: AgentManifest) -> None:
        if manifest.id in self._agents_by_id:
            raise DuplicateAliasError(f"Duplicate agent id: {manifest.id}")
        for alias in manifest.aliases:
            existing = self._aliases.get(alias)
            if existing is not None:
                raise DuplicateAliasError(
                    f"Duplicate alias '{alias}' used by '{existing.id}' and '{manifest.id}'"
                )
        self._agents_by_id[manifest.id] = manifest
        for alias in manifest.aliases:
            self._aliases[alias] = manifest

    def find_by_alias(self, alias: str) -> AgentManifest | None:
        return self._aliases.get(alias.strip().lower())

    def list_agents(self) -> list[AgentManifest]:
        return sorted(self._agents_by_id.values(), key=lambda agent: agent.id)


def load_registry(
    agents_dir: str | Path,
    *,
    allowed_tool_ids: Iterable[str] | None = None,
) -> AgentRegistry:
    manifests = load_agent_manifests(agents_dir, allowed_tool_ids=allowed_tool_ids)
    return AgentRegistry(manifests)


def load_agent_manifests(
    agents_dir: str | Path,
    *,
    allowed_tool_ids: Iterable[str] | None = None,
) -> list[AgentManifest]:
    root = Path(agents_dir)
    if not root.exists():
        return []

    allowed_tools = tuple(allowed_tool_ids or ())
    manifests: list[AgentManifest] = []
    for path in _manifest_paths(root):
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = AgentManifest.from_dict(data, source=path)
        validate_tools(manifest, allowed_tools)
        manifests.append(manifest)
    return manifests


def _manifest_paths(root: Path) -> list[Path]:
    direct_json = [path for path in root.glob("*.json") if path.is_file()]
    nested_agent_json = [path for path in root.glob("*/agent.json") if path.is_file()]
    return sorted(direct_json + nested_agent_json)
