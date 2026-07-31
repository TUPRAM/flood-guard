from __future__ import annotations

from types import SimpleNamespace

import pytest

from geoai_runner.environment import (
    EXPECTED_GEOAI_COMMIT,
    EnvironmentError,
    inspect_environment,
)


def test_environment_import_is_lazy_and_version_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []

    def fake_import(name: str) -> SimpleNamespace:
        imported.append(name)
        return SimpleNamespace(__version__="0.41.1")

    monkeypatch.setattr("geoai_runner.environment.import_module", fake_import)
    receipt = inspect_environment(declared_geoai_commit=EXPECTED_GEOAI_COMMIT)
    assert imported == ["geoai"]
    assert receipt.geoai_version == "0.41.1"
    assert receipt.declared_geoai_commit == EXPECTED_GEOAI_COMMIT


def test_wrong_source_receipt_is_rejected_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []
    monkeypatch.setattr(
        "geoai_runner.environment.import_module",
        lambda name: imported.append(name),
    )
    with pytest.raises(EnvironmentError, match="reviewed source"):
        inspect_environment(declared_geoai_commit="0" * 40)
    assert imported == []


def test_wrong_package_version_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "geoai_runner.environment.import_module",
        lambda _: SimpleNamespace(__version__="0.40.0"),
    )
    with pytest.raises(EnvironmentError, match="Expected geoai-py 0.41.1"):
        inspect_environment(declared_geoai_commit=EXPECTED_GEOAI_COMMIT)
