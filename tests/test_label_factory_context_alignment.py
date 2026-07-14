from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from floodguard.label_factory.context_alignment import (
    CONTEXT_ALIGNMENT_MANIFEST_NAME,
    ContextAlignmentError,
    TargetRasterGrid,
    build_context_alignment,
    load_context_alignment_manifest,
)

rasterio = pytest.importorskip("rasterio")
np = pytest.importorskip("numpy")


def test_build_context_alignment_is_complete_hashed_and_deterministic(
    tmp_path: Path,
) -> None:
    sources = _source_rasters(tmp_path / "sources")
    grid = _target_grid()

    first = build_context_alignment(
        **sources,
        output_directory=tmp_path / "first",
        target_grid=grid,
    )
    second = build_context_alignment(
        **sources,
        output_directory=tmp_path / "second",
        target_grid=grid,
    )

    assert first == second
    assert (tmp_path / "first" / CONTEXT_ALIGNMENT_MANIFEST_NAME).read_bytes() == (
        tmp_path / "second" / CONTEXT_ALIGNMENT_MANIFEST_NAME
    ).read_bytes()
    assert first["layer_count"] == 5
    assert first["query_model_only"] is True
    assert first["eligible_for_decision_layer"] is False
    assert first["eligible_for_fpps"] is False
    assert first["eligible_for_warning"] is False
    assert first["target_grid"]["target_grid_sha256"] == grid.sha256
    assert first["manifest_sha256"] == _canonical_sha256(
        {key: value for key, value in first.items() if key != "manifest_sha256"}
    )

    loaded = load_context_alignment_manifest(
        tmp_path / "first" / CONTEXT_ALIGNMENT_MANIFEST_NAME
    )
    assert loaded == first

    layers = {row["layer_role"]: row for row in first["layers"]}
    assert set(layers) == {
        "land_cover",
        "permanent_water_context",
        "elevation",
        "slope",
        "dem_hillshade",
    }
    assert layers["permanent_water_context"]["source_roles"] == [
        "jrc_occurrence",
        "jrc_seasonality",
    ]
    assert len(layers["permanent_water_context"]["source_sha256s"]) == 2
    assert layers["elevation"]["eligible_for_current_context_layers_csv"] is False
    assert layers["elevation"]["review_bundle_layer_role"] is None
    assert layers["slope"]["eligible_for_current_context_layers_csv"] is True
    assert all(row["valid_data_fraction"] == 1.0 for row in layers.values())
    assert all(len(row["processed_layer_sha256"]) == 64 for row in layers.values())

    first_hashes = {
        role: row["processed_layer_sha256"] for role, row in layers.items()
    }
    second_hashes = {
        row["layer_role"]: row["processed_layer_sha256"]
        for row in second["layers"]
    }
    assert first_hashes == second_hashes

    with rasterio.open(tmp_path / "first" / "permanent_water_context.tif") as ds:
        permanent = ds.read(1)
        assert ds.crs.to_string() == grid.crs
        assert ds.transform.a == grid.affine[0]
        assert ds.transform.e == grid.affine[4]
        assert ds.nodata == 255
    assert permanent.tolist() == [
        [1, 0, 0, 0],
        [1, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ]

    with rasterio.open(tmp_path / "first" / "slope.tif") as ds:
        slope = ds.read(1)
        assert ds.dtypes == ("float32",)
        assert ds.nodata == -9999.0
    assert np.allclose(slope, 45.0, atol=1e-5)


def test_context_alignment_rejects_incomplete_source_coverage_atomically(
    tmp_path: Path,
) -> None:
    sources = _source_rasters(tmp_path / "sources")
    sources["worldcover_path"] = _write_tif(
        tmp_path / "sources" / "small_worldcover.tif",
        np.full((2, 2), 10, dtype="uint8"),
        transform=_transform(),
        nodata=0,
    )
    output = tmp_path / "blocked"

    with pytest.raises(
        ContextAlignmentError,
        match="worldcover has incomplete target coverage or nodata",
    ):
        build_context_alignment(
            **sources,
            output_directory=output,
            target_grid=_target_grid(),
        )

    assert not output.exists()


def test_context_alignment_rejects_jrc_semantic_nodata_atomically(
    tmp_path: Path,
) -> None:
    sources = _source_rasters(tmp_path / "sources")
    occurrence = np.full((4, 4), 95, dtype="uint8")
    occurrence[1, 2] = 255
    sources["jrc_occurrence_path"] = _write_tif(
        tmp_path / "sources" / "occurrence_with_nodata.tif",
        occurrence,
        transform=_transform(),
        nodata=None,
    )
    output = tmp_path / "blocked"

    with pytest.raises(
        ContextAlignmentError,
        match="jrc_occurrence has incomplete target coverage or nodata: 1/16",
    ):
        build_context_alignment(
            **sources,
            output_directory=output,
            target_grid=_target_grid(),
        )

    assert not output.exists()


def test_context_alignment_rejects_dem_nodata_atomically(tmp_path: Path) -> None:
    sources = _source_rasters(tmp_path / "sources")
    elevation = np.full((4, 4), 100.0, dtype="float32")
    elevation[2, 1] = -9999.0
    sources["dem_path"] = _write_tif(
        tmp_path / "sources" / "dem_with_nodata.tif",
        elevation,
        transform=_transform(),
        nodata=-9999.0,
    )
    output = tmp_path / "blocked"

    with pytest.raises(
        ContextAlignmentError,
        match="copernicus_dem has incomplete target coverage or nodata",
    ):
        build_context_alignment(
            **sources,
            output_directory=output,
            target_grid=_target_grid(),
        )

    assert not output.exists()


def test_context_alignment_requires_matching_raw_jrc_grids(tmp_path: Path) -> None:
    sources = _source_rasters(tmp_path / "sources")
    shifted = rasterio.transform.from_origin(110.0, 200.0, 10.0, 10.0)
    sources["jrc_seasonality_path"] = _write_tif(
        tmp_path / "sources" / "shifted_seasonality.tif",
        np.full((4, 4), 12, dtype="uint8"),
        transform=shifted,
        nodata=None,
    )

    with pytest.raises(ContextAlignmentError, match="share one raw grid"):
        build_context_alignment(
            **sources,
            output_directory=tmp_path / "blocked",
            target_grid=_target_grid(),
        )


def test_context_alignment_rejects_rotated_or_non_north_up_target() -> None:
    with pytest.raises(ContextAlignmentError, match="north-up"):
        TargetRasterGrid(
            crs="EPSG:32647",
            affine=(10.0, 0.1, 100.0, 0.0, -10.0, 200.0),
            width=4,
            height=4,
        )


def test_context_alignment_does_not_overwrite_existing_output(tmp_path: Path) -> None:
    sources = _source_rasters(tmp_path / "sources")
    output = tmp_path / "context"
    output.mkdir()

    with pytest.raises(ContextAlignmentError, match="immutable and already exists"):
        build_context_alignment(
            **sources,
            output_directory=output,
            target_grid=_target_grid(),
        )


def test_context_alignment_manifest_rejects_tampering(tmp_path: Path) -> None:
    sources = _source_rasters(tmp_path / "sources")
    output = tmp_path / "context"
    build_context_alignment(
        **sources,
        output_directory=output,
        target_grid=_target_grid(),
    )
    path = output / CONTEXT_ALIGNMENT_MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["eligible_for_fpps"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ContextAlignmentError, match="self-hash mismatch"):
        load_context_alignment_manifest(path)


def _source_rasters(directory: Path) -> dict[str, Path]:
    transform = _transform()
    land_cover = np.array(
        [
            [10, 20, 30, 40],
            [50, 60, 70, 80],
            [90, 95, 100, 10],
            [20, 30, 40, 50],
        ],
        dtype="uint8",
    )
    occurrence = np.array(
        [
            [95, 95, 50, 0],
            [100, 91, 89, 0],
            [0, 50, 92, 95],
            [0, 0, 95, 100],
        ],
        dtype="uint8",
    )
    seasonality = np.array(
        [
            [12, 9, 12, 0],
            [10, 10, 12, 0],
            [0, 5, 11, 9],
            [0, 0, 8, 12],
        ],
        dtype="uint8",
    )
    elevation = (
        np.tile(np.arange(4, dtype="float32") * 10.0, (4, 1)) + 100.0
    )
    return {
        "worldcover_path": _write_tif(
            directory / "worldcover.tif",
            land_cover,
            transform=transform,
            nodata=0,
        ),
        "jrc_occurrence_path": _write_tif(
            directory / "occurrence.tif",
            occurrence,
            transform=transform,
            nodata=None,
        ),
        "jrc_seasonality_path": _write_tif(
            directory / "seasonality.tif",
            seasonality,
            transform=transform,
            nodata=None,
        ),
        "dem_path": _write_tif(
            directory / "dem.tif",
            elevation,
            transform=transform,
            nodata=None,
        ),
    }


def _write_tif(
    path: Path,
    array: object,
    *,
    transform: object,
    nodata: int | float | None,
) -> Path:
    values = np.asarray(array)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype=str(values.dtype),
        crs="EPSG:32647",
        transform=transform,
        nodata=nodata,
    ) as dataset:
        dataset.write(values, 1)
    return path


def _transform() -> object:
    return rasterio.transform.from_origin(100.0, 200.0, 10.0, 10.0)


def _target_grid() -> TargetRasterGrid:
    transform = _transform()
    return TargetRasterGrid(
        crs="EPSG:32647",
        affine=(
            transform.a,
            transform.b,
            transform.c,
            transform.d,
            transform.e,
            transform.f,
        ),
        width=4,
        height=4,
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
