"""Fail-closed tests for the pinned Mae Sai browser bundle generator."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps" / "web" / "scripts" / "build-mae-sai-offline-bundle.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mae_sai_offline_builder", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    return _module()


@pytest.fixture(scope="module")
def pinned_inputs(builder: ModuleType) -> tuple[dict, dict]:
    manifest = builder._load(builder.SOURCE_MANIFEST_PATH)
    sources = {
        layer_id: builder._load(path)
        for layer_id, path in builder.INPUTS.items()
    }
    return manifest, sources


def test_pinned_generator_inputs_validate_before_build(
    builder: ModuleType,
    pinned_inputs: tuple[dict, dict],
) -> None:
    manifest, sources = pinned_inputs
    builder._validate_pinned_inputs(manifest, sources)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("fpps_0_100", "not-a-number", "finite number"),
        ("source_name", None, "missing required properties"),
    ],
)
def test_pinned_generator_rejects_corrupt_required_values(
    builder: ModuleType,
    pinned_inputs: tuple[dict, dict],
    field: str,
    replacement: object,
    message: str,
) -> None:
    manifest, sources = pinned_inputs
    corrupt_sources = deepcopy(sources)
    properties = corrupt_sources["priority_areas"]["features"][0]["properties"]
    if replacement is None:
        properties.pop(field)
    else:
        properties[field] = replacement
    with pytest.raises(ValueError, match=message):
        builder._validate_pinned_inputs(manifest, corrupt_sources)


def test_pinned_generator_rejects_geometry_substitution(
    builder: ModuleType,
    pinned_inputs: tuple[dict, dict],
) -> None:
    manifest, sources = pinned_inputs
    corrupt_sources = deepcopy(sources)
    corrupt_sources["priority_areas"]["features"][0]["geometry"] = {
        "type": "Point",
        "coordinates": [99.9, 20.4],
    }
    with pytest.raises(ValueError, match="geometry type changed"):
        builder._validate_pinned_inputs(manifest, corrupt_sources)


def test_validation_failure_occurs_before_any_output_write(
    builder: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    monkeypatch.setattr(builder, "_load", lambda _path: {})
    monkeypatch.setattr(
        builder,
        "_validate_pinned_inputs",
        lambda _manifest, _sources: (_ for _ in ()).throw(ValueError("blocked")),
    )
    monkeypatch.setattr(
        builder,
        "_write",
        lambda name, _value: writes.append(name),
    )
    with pytest.raises(ValueError, match="blocked"):
        builder.main()
    assert writes == []
