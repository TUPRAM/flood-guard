"""Source-only checks for the NASA MCDWD native inventory."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_nasa_mcdwd.py"
SPEC = importlib.util.spec_from_file_location("inspect_nasa_mcdwd", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
aoi_window = MODULE.aoi_window
canonical_sha256 = MODULE.canonical_sha256
metadata_value = MODULE.metadata_value
native_grid = MODULE.native_grid


STRUCT = """XDim=4
YDim=4
UpperLeftPointMtrs=(100000000.000000,20000000.000000)
LowerRightMtrs=(104000000.000000,16000000.000000)
Projection=GCTP_GEO
SphereCode=12
GridOrigin=HDFE_GD_UL
PixelRegistration=HDFE_CORNER
"""


def test_native_grid_and_pixel_centres(tmp_path: Path) -> None:
    """A declared 2x2-degree polygon selects the four central native cells."""
    aoi = tmp_path / "aoi.geojson"
    aoi.write_text(json.dumps({
        "type": "FeatureCollection",
        "crs": {"properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{"type": "Feature", "geometry": {
            "type": "Polygon", "coordinates": [[[101, 17], [103, 17], [103, 19], [101, 19], [101, 17]]],
        }}],
    }), encoding="utf-8")
    width, height, transform = native_grid(STRUCT)
    window, inside = aoi_window(aoi, width, height, transform)
    assert (width, height) == (4, 4)
    assert window == (1, 3, 1, 3)
    assert inside.tolist() == [[True, True], [True, True]]


def test_native_grid_refuses_unknown_spheroid() -> None:
    """A changed HDF spheroid cannot silently become the expected WGS84 grid."""
    with pytest.raises(ValueError, match="Unsupported MCDWD native georeferencing"):
        native_grid(STRUCT.replace("SphereCode=12", "SphereCode=0"))


def test_aoi_outside_tile_refused(tmp_path: Path) -> None:
    """An AOI crossing a tile edge cannot be silently clipped as complete."""
    aoi = tmp_path / "crossing.geojson"
    aoi.write_text(json.dumps({
        "type": "FeatureCollection",
        "crs": {"properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{"type": "Feature", "geometry": {
            "type": "Polygon", "coordinates": [[[103, 17], [105, 17], [105, 19], [103, 19], [103, 17]]],
        }}],
    }), encoding="utf-8")
    width, height, transform = native_grid(STRUCT)
    with pytest.raises(ValueError, match="Complete AOI must fit"):
        aoi_window(aoi, width, height, transform)


def test_metadata_and_self_hash_refuse_changed_counts() -> None:
    """The metadata parser and receipt digest bind source-only class counts."""
    core = 'OBJECT = RANGEBEGINNINGDATE\n VALUE = "2024-10-12"\n END_OBJECT = RANGEBEGINNINGDATE'
    assert metadata_value(core, "RANGEBEGINNINGDATE") == "2024-10-12"
    with pytest.raises(ValueError, match="Missing HDF metadata"):
        metadata_value(core, "RANGEENDINGDATE")
    malformed = (
        "OBJECT = RANGEBEGINNINGDATE\n END_OBJECT = RANGEBEGINNINGDATE\n"
        'OBJECT = RANGEENDINGDATE\n VALUE = "2024-10-13"\n END_OBJECT = RANGEENDINGDATE'
    )
    with pytest.raises(ValueError, match="Missing HDF metadata"):
        metadata_value(malformed, "RANGEBEGINNINGDATE")
    receipt = {"class_counts": {"FloodCS_1Day_250m": {"0": 221, "3": 97}}}
    digest = canonical_sha256(receipt)
    receipt["receipt_sha256"] = digest
    assert canonical_sha256(receipt) == digest
    receipt["class_counts"]["FloodCS_1Day_250m"]["3"] = 98
    assert canonical_sha256(receipt) != digest
