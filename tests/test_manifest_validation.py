import json

import pytest

from agent_factory.errors import DuplicateAliasError, ManifestValidationError, UnknownToolError
from agent_factory.loader import load_agent_manifests, load_registry
from agent_factory.models import AgentManifest


def manifest_data(**overrides):
    data = {
        "id": "alpha",
        "name": "Alpha Agent",
        "purpose": "Primary responsibility: Perform alpha work.\nSelect for: Requests that require the alpha workflow.\nDo not select for: Requests unrelated to alpha work.",
        "aliases": ["alpha"],
        "tools": [],
        "permissions": {},
        "memory": {},
        "runtime": {"mode": "manual"},
        "output_contract": None,
    }
    data.update(overrides)
    return data


def write_manifest(directory, name, data):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_manifest_accepts_required_fields():
    manifest = AgentManifest.from_dict(manifest_data())

    assert manifest.id == "alpha"
    assert manifest.aliases == ("alpha",)


def test_missing_required_field_is_rejected():
    data = manifest_data()
    del data["id"]

    with pytest.raises(ManifestValidationError):
        AgentManifest.from_dict(data)


def test_duplicate_aliases_inside_manifest_are_rejected():
    with pytest.raises(ManifestValidationError):
        AgentManifest.from_dict(manifest_data(aliases=["alpha", "ALPHA"]))


def test_loader_rejects_duplicate_aliases(tmp_path):
    agents_dir = tmp_path / "agents"
    write_manifest(agents_dir, "alpha.json", manifest_data(id="alpha", aliases=["shared"]))
    write_manifest(agents_dir, "beta.json", manifest_data(id="beta", aliases=["SHARED"]))

    with pytest.raises(DuplicateAliasError):
        load_registry(agents_dir)


def test_loader_rejects_unknown_tool(tmp_path):
    agents_dir = tmp_path / "agents"
    write_manifest(agents_dir, "alpha.json", manifest_data(tools=["unknown.tool"]))

    with pytest.raises(UnknownToolError):
        load_agent_manifests(agents_dir, allowed_tool_ids=[])
