from __future__ import annotations

from agent_factory import setup_doctor


def test_factory_brain_dependency_check_passes_with_declared_extra() -> None:
    results = setup_doctor._check_factory_brain_dependencies()

    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].label == "Factory Brain runtime dependencies"


def test_factory_brain_dependency_check_reports_real_failure(monkeypatch) -> None:
    def fail() -> None:
        raise RuntimeError("Factory Brain dependencies are not installed.")

    monkeypatch.setattr(
        "agent_factory.factory_brain.check_factory_brain_dependencies",
        fail,
    )

    results = setup_doctor._check_factory_brain_dependencies()

    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].label == "Factory Brain runtime dependencies"
    assert results[0].detail == "Factory Brain dependencies are not installed."
