from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from floodguard.label_factory.sentinel1_processing import (
    CANONICAL_FLOAT_NODATA,
    CANONICAL_MASK_NODATA,
    PINNED_SNAP_VERSION,
    SNAP_PARALLELISM,
    SNAP_TILE_CACHE_SIZE,
    Sentinel1ProcessingError,
    TargetRasterGrid,
    _resolve_source_product,
    _snap_version,
    extract_canonical_rtc_layers,
    run_snap_rtc_graph,
    write_processing_run_manifest,
)


GRID_HASH = hashlib.sha256(b"grid").hexdigest()


def _grid() -> TargetRasterGrid:
    return TargetRasterGrid(
        crs="EPSG:32647",
        left=581120,
        bottom=2255360,
        right=581440,
        top=2255680,
        resolution_m=10,
        grid_contract_sha256=GRID_HASH,
    )


def _snap_fixture(tmp_path: Path) -> Path:
    dim = tmp_path / "fixture.dim"
    dim.write_text("<Dimap_Document />\n", encoding="utf-8")
    data = tmp_path / "fixture.data"
    data.mkdir()
    transform = from_origin(581100, 2255700, 10, 10)
    for name in (
        "Gamma0_VV",
        "Gamma0_VH",
        "localIncidenceAngle",
        "projectedLocalIncidenceAngle",
        "layoverShadowMask",
    ):
        is_mask = name == "layoverShadowMask"
        values = (
            np.zeros((36, 36), dtype="uint8")
            if is_mask
            else np.full((36, 36), 0.1 if name.startswith("Gamma") else 35.0, dtype="float32")
        )
        with rasterio.open(
            data / f"{name}.img",
            "w",
            driver="ENVI",
            width=36,
            height=36,
            count=1,
            dtype=values.dtype,
            crs="EPSG:32647",
            transform=transform,
        ) as dataset:
            dataset.write(values, 1)
    return dim


def test_target_grid_requires_exact_cell_dimensions() -> None:
    with pytest.raises(Sentinel1ProcessingError, match="integer number"):
        TargetRasterGrid(
            "EPSG:32647", 0, 0, 101, 100, 10, GRID_HASH
        )


def test_target_grid_requires_approved_crs_resolution_and_edge_origin() -> None:
    with pytest.raises(Sentinel1ProcessingError, match="target CRS"):
        TargetRasterGrid("EPSG:4326", 0, 0, 320, 320, 10, GRID_HASH)
    with pytest.raises(Sentinel1ProcessingError, match="10 m pixels"):
        TargetRasterGrid("EPSG:32647", 0, 0, 320, 320, 20, GRID_HASH)
    with pytest.raises(Sentinel1ProcessingError, match="edge-origin"):
        TargetRasterGrid("EPSG:32647", 5, 0, 325, 320, 10, GRID_HASH)


def test_snap_graph_centres_pixels_on_approved_edge_origin_grid() -> None:
    graph = ElementTree.parse(
        Path(__file__).parents[1] / "resources" / "snap" / "sentinel1_grd_rtc_v1.xml"
    )
    assert graph.findtext(".//standardGridOriginX") == "5"
    assert graph.findtext(".//standardGridOriginY") == "5"
    assert [
        element.text for element in graph.findall(".//externalDEMApplyEGM")
    ] == ["true", "true"]


def test_extract_canonical_layers_writes_tagged_db_outputs(tmp_path: Path) -> None:
    dim = _snap_fixture(tmp_path)
    output = tmp_path / "output"

    result = extract_canonical_rtc_layers(
        snap_dim=dim,
        output_directory=output,
        acquisition_prefix="event",
        grid=_grid(),
        source_product_id="PRODUCT-EVENT",
    )

    vv_path = output / "event_vv_db.tif"
    assert vv_path.is_file()
    with rasterio.open(vv_path) as dataset:
        assert dataset.crs.to_string() == "EPSG:32647"
        assert dataset.width == dataset.height == 32
        assert dataset.nodata == CANONICAL_FLOAT_NODATA
        assert dataset.tags()["grid_contract_sha256"] == GRID_HASH
        assert np.allclose(dataset.read(1), -10.0, atol=1e-5)
    assert result["outputs"]["vv"]["valid_data_fraction"] == 1.0
    assert result["source_bands"]["Gamma0_VV"]["source_header_sha256"]
    assert result["eligible_for_fpps"] is False


def test_layover_shadow_cells_become_nodata(tmp_path: Path) -> None:
    dim = _snap_fixture(tmp_path)
    mask_path = dim.with_suffix(".data") / "layoverShadowMask.img"
    with rasterio.open(mask_path, "r+") as dataset:
        values = dataset.read(1)
        values[2:4, 2:4] = 2
        dataset.write(values, 1)

    output = tmp_path / "output"
    extract_canonical_rtc_layers(
        snap_dim=dim,
        output_directory=output,
        acquisition_prefix="pre",
        grid=_grid(),
        source_product_id="PRODUCT-PRE",
    )

    with rasterio.open(output / "pre_vv_db.tif") as dataset:
        values = dataset.read(1)
        assert CANONICAL_FLOAT_NODATA in values


def test_missing_radiometric_support_is_nodata_in_geometry_mask(tmp_path: Path) -> None:
    dim = _snap_fixture(tmp_path)
    gamma_path = dim.with_suffix(".data") / "Gamma0_VV.img"
    with rasterio.open(gamma_path, "r+") as dataset:
        values = dataset.read(1)
        values[2:4, 2:4] = 0
        dataset.write(values, 1)

    output = tmp_path / "output"
    result = extract_canonical_rtc_layers(
        snap_dim=dim,
        output_directory=output,
        acquisition_prefix="event",
        grid=_grid(),
        source_product_id="PRODUCT-EVENT",
    )

    with rasterio.open(output / "event_layover_shadow_mask.tif") as dataset:
        mask = dataset.read(1)
        assert dataset.nodata == CANONICAL_MASK_NODATA
        assert np.all(mask[:2, :2] == CANONICAL_MASK_NODATA)
    with rasterio.open(output / "event_vh_db.tif") as dataset:
        assert np.all(dataset.read(1)[:2, :2] == CANONICAL_FLOAT_NODATA)
    assert result["outputs"]["layover_shadow_mask"]["valid_cell_count"] == 1020


def test_extract_rejects_incomplete_snap_coverage(tmp_path: Path) -> None:
    dim = _snap_fixture(tmp_path)
    grid = TargetRasterGrid(
        "EPSG:32647", 581120, 2255360, 582000, 2256240, 10, GRID_HASH
    )
    with pytest.raises(Sentinel1ProcessingError, match="does not cover"):
        extract_canonical_rtc_layers(
            snap_dim=dim,
            output_directory=tmp_path / "output",
            acquisition_prefix="event",
            grid=grid,
            source_product_id="PRODUCT-EVENT",
        )


def test_processing_manifest_is_immutable_and_self_hashed(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    write_processing_run_manifest({"artifact_schema": "fixture"}, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    observed = payload.pop("manifest_sha256")
    expected = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert observed == expected
    with pytest.raises(Sentinel1ProcessingError, match="immutable"):
        write_processing_run_manifest({"artifact_schema": "fixture"}, path)


def test_unpacked_safe_is_read_by_manifest_and_tree_hashed(tmp_path: Path) -> None:
    safe = tmp_path / "PRODUCT.SAFE"
    safe.mkdir()
    (safe / "manifest.safe").write_text("manifest", encoding="utf-8")
    measurement = safe / "measurement"
    measurement.mkdir()
    raster = measurement / "image.tiff"
    raster.write_bytes(b"one")

    first = _resolve_source_product(safe)
    raster.write_bytes(b"two")
    second = _resolve_source_product(safe)

    assert first.read_path == safe / "manifest.safe"
    assert first.product_name == "PRODUCT.SAFE"
    assert first.packaging == "unpacked_safe_directory"
    assert first.file_count == 2
    assert first.sha256 != second.sha256

    direct_manifest = _resolve_source_product(safe / "manifest.safe")
    assert direct_manifest.sha256 == second.sha256
    assert direct_manifest.packaging == "unpacked_safe_directory"


def test_snap_version_must_match_pin(tmp_path: Path) -> None:
    gpt = tmp_path / "snap" / "bin" / "gpt.exe"
    gpt.parent.mkdir(parents=True)
    gpt.write_bytes(b"gpt")
    version = gpt.parent.parent / "VERSION.txt"
    version.write_text(PINNED_SNAP_VERSION, encoding="utf-8")
    assert _snap_version(gpt) == PINNED_SNAP_VERSION
    version.write_text("13.0.1", encoding="utf-8")
    with pytest.raises(Sentinel1ProcessingError, match="not the pinned"):
        _snap_version(gpt)


def test_snap_runner_uses_safe_manifest_and_bounded_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gpt = tmp_path / "snap" / "bin" / "gpt.exe"
    gpt.parent.mkdir(parents=True)
    gpt.write_bytes(b"gpt")
    (gpt.parent.parent / "VERSION.txt").write_text(
        PINNED_SNAP_VERSION, encoding="utf-8"
    )
    graph = tmp_path / "graph.xml"
    graph.write_text("<graph />", encoding="utf-8")
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"dem")
    safe = tmp_path / "PRODUCT.SAFE"
    safe.mkdir()
    manifest = safe / "manifest.safe"
    manifest.write_text("manifest", encoding="utf-8")
    auxdata = tmp_path / "auxdata"
    orbit = (
        auxdata
        / "Orbits"
        / "Sentinel-1"
        / "POEORB"
        / "S1A"
        / "S1A_TEST_POEORB.EOF.zip"
    )
    orbit.parent.mkdir(parents=True)
    orbit.write_bytes(b"orbit")
    egm = auxdata / "dem" / "egm96" / "ww15mgh_b.zip"
    egm.parent.mkdir(parents=True)
    egm.write_bytes(b"egm")
    output = tmp_path / "out" / "event.dim"
    captured: list[str] = []
    product_name = ["ORIGINAL_SAFE"]

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured.extend(command)
        output.write_text(
            f"""<Dimap_Document><Metadata><MDATTR name="PRODUCT">{product_name[0]}</MDATTR>
            <MDATTR name="Processing_system_identifier">Sentinel-1 IPF 003.80</MDATTR>
            <MDATTR name="orbit_state_vector_file">S1A_TEST_POEORB.EOF.zip</MDATTR>
            </Metadata></Dimap_Document>""",
            encoding="utf-8",
        )
        output.with_suffix(".data").mkdir()
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(
        "floodguard.label_factory.sentinel1_processing.subprocess.run", fake_run
    )
    result = run_snap_rtc_graph(
        gpt_path=gpt,
        graph_path=graph,
        source_product=safe,
        external_dem=dem,
        subset_wkt="POLYGON ((0 0, 1 0, 1 1, 0 0))",
        output_dim=output,
        snap_auxdata_directory=auxdata,
    )

    assert f"-Pinput={manifest}" in captured
    assert captured[captured.index("-c") + 1] == SNAP_TILE_CACHE_SIZE
    assert captured[captured.index("-q") + 1] == str(SNAP_PARALLELISM)
    assert "-x" in captured
    assert result["source_packaging"] == "unpacked_safe_directory"
    assert result["snap_version"] == PINNED_SNAP_VERSION
    assert result["orbit_state_vector_file"] == "S1A_TEST_POEORB.EOF.zip"
    assert result["orbit_auxiliary_sha256"] == hashlib.sha256(b"orbit").hexdigest()
    assert result["external_dem_apply_egm"] is True
    assert result["snap_egm96_auxiliary_sha256"] == hashlib.sha256(b"egm").hexdigest()

    product_name[0] = "CONVERTED_COG"
    output = tmp_path / "out" / "cog.dim"
    with pytest.raises(Sentinel1ProcessingError, match="COG-converted"):
        run_snap_rtc_graph(
            gpt_path=gpt,
            graph_path=graph,
            source_product=safe,
            external_dem=dem,
            subset_wkt="POLYGON ((0 0, 1 0, 1 1, 0 0))",
            output_dim=output,
            snap_auxdata_directory=auxdata,
        )
