"""Run the FULL GeoAI pipeline on REAL data over Mae Sai, Chiang Rai.

Every component uses real inputs -- no synthetic pixels anywhere:

  A  SAR flood extent      real Sentinel-1 RTC pre/post (Planetary Computer)
  B  Water segmentation    real Sentinel-2 L2A + real MNDWI labels, U-Net with
                           real ImageNet-pretrained ResNet encoder
  C  Flood susceptibility  real Copernicus DEM GLO-30 + real DWR river network
                           (HAND / slope / distance / TWI), validated against
                           real JRC Global Surface Water
  D  Infrastructure        real OpenStreetMap building footprints
  F  Few-shot classifier   real Sentinel-2 features + real labels
  Bridge                   real DOPA sub-district boundaries -> FPPS

Outputs overwrite ``outputs/geoai/`` so the showcase page and its previews are
entirely real. Requires network access.

Usage:  python scripts/run_real_geoai_pipeline.py [--fast]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# run_real.py lives at services/geoai-runner/geoai_runner/realpipeline/run_real.py
REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:  # make root floodguard importable when not installed
    sys.path.insert(0, str(SRC_ROOT))

# D-02: the candidate lane reaches FPPS only through a signed, report-only
# receipt. `floodguard.scoring.score_subdistricts` is deliberately NOT imported
# here -- test_no_direct_scoring_import.py fails the build if it comes back.
from floodguard.candidate_zonal_receipt import score_candidate_areas  # noqa: E402

from geoai_runner.realpipeline import (  # noqa: E402  # noqa: E402
    aggregate,
    annotate,
    blocks,
    embeddings,
    susceptibility,
    water_unet,
)
from geoai_runner.realpipeline import narrative as nr  # noqa: E402
from geoai_runner.realpipeline import real_data as rd  # noqa: E402
from geoai_runner.realpipeline.geoai_page import write_geoai_page  # noqa: E402
from geoai_runner.realpipeline.raster_io import array_to_png, write_geotiff  # noqa: E402
from geoai_runner.realpipeline.registry import COMPONENTS  # noqa: E402

SHAPE = (1024, 1024)

# Component B tiling. The 1600 m buffer is half a 128 px tile's ~3.2 km ground
# width, so a training tile is a full tile-width away from any held-out pixel.
# blocks.plan_block_geometry derives the block size from these two numbers.
TILE_SIZE = 128
TILE_STRIDE = 32
BLOCK_BUFFER_M = 1600.0
STUDY_LATITUDE = 20.4

# The Sept-2024 Mae Sai flood peaked around Sep 11; the nearest same-orbit
# Sentinel-1 acquisition is Sep 15.
FLOOD_PEAK_DATE = "2024-09-11"
PEAK_OFFSET_DAYS = 4


def _candidate_signing_key() -> bytes:
    """Resolve the HMAC key that binds candidate evidence to its receipt (D-02).

    Fail-closed on purpose. The figures this run produces are published to the
    Command surface; producing them with no receipt is the exact failure the
    candidate lane exists to prevent, so an absent key stops the run rather
    than silently degrading to unsigned output.
    """

    raw = os.environ.get("FLOODGUARD_ZONAL_SIGNING_KEY_HEX", "").strip()
    if not raw:
        raise SystemExit(
            "FLOODGUARD_ZONAL_SIGNING_KEY_HEX is not set.\n"
            "Candidate GeoAI evidence must be bound to a signed report-only "
            "receipt before it can be published (audit D-02).\n"
            "  PowerShell:  $env:FLOODGUARD_ZONAL_SIGNING_KEY_HEX = "
            '(python -c "import secrets;print(secrets.token_hex(32))")\n'
            "See .env.example. The key never appears in the receipt."
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise SystemExit(
            "FLOODGUARD_ZONAL_SIGNING_KEY_HEX must be hex-encoded bytes."
        ) from exc
    if len(key) < 32:
        raise SystemExit(
            f"FLOODGUARD_ZONAL_SIGNING_KEY_HEX decodes to {len(key)} bytes; "
            "at least 32 are required."
        )
    return key


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="Fewer U-Net epochs.")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument(
        "--all-methods",
        action="store_true",
        help="Also run the OmniWaterMask baseline and Component E built-up "
        "encroachment. Downloads extra weights/products; slower.",
    )
    ap.add_argument(
        "--encroachment-t1",
        type=int,
        default=2015,
        help="Earlier built-up epoch year for Component E.",
    )
    ap.add_argument(
        "--encroachment-t2",
        type=int,
        default=2025,
        help="Later built-up epoch year for Component E.",
    )
    ap.add_argument(
        "--temporal",
        action="store_true",
        help="Component A2: build a multi-year single-orbit Sentinel-1 "
        "baseline and detect flooding as deviation from each pixel's "
        "own seasonal normal. Downloads ~180 scenes on first run "
        "(cached thereafter).",
    )
    ap.add_argument(
        "--temporal-start",
        default="2018-01-01",
        help="First acquisition date for the temporal baseline.",
    )
    ap.add_argument(
        "--temporal-end",
        default="2024-12-31",
        help="Last acquisition date for the temporal baseline.",
    )
    ap.add_argument(
        "--temporal-max-scenes",
        type=int,
        default=None,
        help="Cap the series length (smoke runs); recorded in the manifest.",
    )
    args = ap.parse_args()

    out = REPO_ROOT / "outputs" / "geoai"
    work = out / "work"
    prev = out / "previews"
    for d in (out, work, prev):
        d.mkdir(parents=True, exist_ok=True)

    metrics: dict[str, dict] = {}
    timings: dict[str, float] = {}

    # ---------------- real study area + grid -------------------------------
    print("[1/9] Real DOPA sub-districts (NGIS) ...")
    subs = rd.fetch_mae_sai_subdistricts()
    bbox = _union_bbox(subs, 0.01)
    (out / "subdistricts.geojson").write_text(json.dumps(subs), encoding="utf-8")
    from affine import Affine

    transform = Affine.translation(bbox[0], bbox[3]) * Affine.scale(
        (bbox[2] - bbox[0]) / SHAPE[1], (bbox[1] - bbox[3]) / SHAPE[0]
    )
    pixel_m = (bbox[2] - bbox[0]) / SHAPE[1] * 111000.0 * np.cos(np.radians(20.4))
    print(
        f"      {len(subs['features'])} tambons | bbox {tuple(round(v, 3) for v in bbox)} | ~{pixel_m:.0f} m/px"
    )

    # ---------------- spatial holdout partition ----------------------------
    # Seeded before any model runs, and chosen on a purely geometric criterion
    # (no role collapsing into one contiguous patch) so the held-out score can
    # never become a hyperparameter.
    seed, contiguity = blocks.select_dispersed_seed(
        SHAPE,
        transform,
        tile_size_px=TILE_SIZE,
        buffer_m=BLOCK_BUFFER_M,
        latitude=STUDY_LATITUDE,
    )
    assignment = blocks.assign_spatial_blocks(
        SHAPE,
        transform,
        seed=seed,
        tile_size_px=TILE_SIZE,
        buffer_m=BLOCK_BUFFER_M,
        latitude=STUDY_LATITUDE,
    )
    single_patch = [role for role, entry in contiguity.items() if entry["single_patch"]]
    print(
        f"      partition: {assignment.plan.blocks_per_axis}x{assignment.plan.blocks_per_axis} "
        f"blocks of {assignment.plan.block_m:.0f} m, {BLOCK_BUFFER_M:.0f} m buffer "
        f"(seed {seed}) | {assignment.role_block_counts} | "
        f"buffer {assignment.role_pixel_share['buffer'] * 100:.1f}% of scene"
    )
    if single_patch:
        print(
            f"      NOTE: role(s) {single_patch} form a single contiguous patch; "
            "their metrics carry a geographic confound."
        )

    # ---------------- A: real Sentinel-1 flood -----------------------------
    print("[2/9] Component A - real Sentinel-1 flood extent ...")
    t = time.time()
    pair = rd.fetch_sentinel1_rtc_pair(bbox=bbox, out_shape=SHAPE)
    flood = rd.real_sar_flood_extent(pair, work, drop_threshold_db=2.0, multilook=3)
    timings["sar_flood"] = round(time.time() - t, 1)
    metrics["sar_flood"] = {**flood.metrics, "data_mode": "real_licensed_inputs"}
    post_vh_db = rd._to_db(rd._boxcar(pair["bands"]["post_vh"], 3))
    array_to_png(prev / "scene_sar_post_vh.png", post_vh_db, cmap="gray", vmin=-25, vmax=-5)
    array_to_png(
        prev / "A_sar_flood_probability.png", flood.flood_probability, cmap="turbo", vmin=0, vmax=1
    )
    array_to_png(prev / "A_sar_flood_binary.png", flood.flood_binary, cmap="Blues")
    print(
        f"      pre {pair['pre_datetime'][:10]} post {pair['post_datetime'][:10]} | "
        f"flood {flood.metrics['flood_fraction'] * 100:.2f}%"
    )

    # ---------------- real Sentinel-2 + real water labels ------------------
    print("[3/9] Real Sentinel-2 L2A composite ...")
    t = time.time()
    s2 = rd.fetch_sentinel2_composite(bbox=bbox, out_shape=SHAPE)
    stack = s2["stack"]
    # Band 3 (NIR) is unpacked for documentation of the stack layout even though
    # MNDWI uses only green and SWIR1: 1=B2 2=B3 3=B4 4=B8 5=B11 6=B12.
    green, _nir, swir1 = stack[1], stack[3], stack[4]
    mndwi = (green - swir1) / (green + swir1 + 1e-6)
    water_label = (mndwi > 0.0).astype("uint8")  # real spectral-index water mask
    jrc = rd.fetch_jrc_surface_water(bbox=bbox, out_shape=SHAPE)
    timings["sentinel2"] = round(time.time() - t, 1)
    print(
        f"      {s2['datetime'][:10]} cloud {s2['cloud_cover']:.3f}% | "
        f"MNDWI water {water_label.mean() * 100:.2f}% | JRC occ>50 {(jrc['occurrence'] > 50).mean() * 100:.2f}%"
    )
    array_to_png(prev / "scene_s2_rgb.png", np.clip(stack[[2, 1, 0]] * 3.5, 0, 1))
    write_geotiff(work / "s2.tif", stack, transform, "EPSG:4326")
    write_geotiff(work / "water_label.tif", water_label, transform, "EPSG:4326", dtype="uint8")

    # ---------------- B: real U-Net water segmentation ---------------------
    print("[4/9] Component B - U-Net on real Sentinel-2 (spatial-block holdout) ...")
    t = time.time()
    epochs = args.epochs or (20 if args.fast else 120)
    # Preprocessing is fitted on training blocks only (leakage control #6 in
    # docs/immutable-multi-event-partitions-v1.md), then applied to the whole
    # scene so training and inference see the same transform.
    channel_stats = water_unet.fit_channel_stats(work / "s2.tif", assignment, role="train")
    water_unet.write_standardised_raster(work / "s2.tif", channel_stats, work / "s2_std.tif")
    class_weights = water_unet.inverse_frequency_class_weights(
        work / "water_label.tif", assignment, role="train"
    )
    partition = water_unet.prepare_role_tiles(
        work / "s2_std.tif",
        work / "water_label.tif",
        work / "tiles",
        assignment,
        tile_size=TILE_SIZE,
        stride=TILE_STRIDE,
        channel_stats=channel_stats,
    )
    model = water_unet.train_water_unet(
        partition,
        work / "unet",
        num_channels=6,
        encoder_name="resnet18",
        encoder_weights="imagenet",
        num_epochs=epochs,
        target_size=(TILE_SIZE, TILE_SIZE),
        class_weights=class_weights,
        learning_rate=3e-4,
    )
    b_mask, b_prob, b_transform, b_crs, b_artifacts = water_unet.infer_water_probability(
        model,
        work / "s2_std.tif",
        work,
        num_channels=6,
        encoder_name="resnet18",
        window_size=TILE_SIZE,
        overlap=32,
    )
    evaluation = water_unet.evaluate_roles(b_prob, water_label, assignment)
    res_b = water_unet.finalise_water_result(
        (b_prob >= evaluation["threshold_selection"]["selected_threshold"]).astype("uint8"),
        b_prob,
        b_transform,
        b_crs,
        work,
        evaluation,
        model_path=model,
        artifacts=b_artifacts,
        data_mode="real_licensed_inputs",
    )
    timings["water_unet"] = round(time.time() - t, 1)
    metrics["water_unet"] = {
        **res_b.metrics,
        "data_mode": "real_licensed_inputs",
        "partition": assignment.to_dict(),
        "tiling": partition.to_dict(),
        "epochs": epochs,
        "encoder_weights": "imagenet",
        "class_weights": list(class_weights),
    }
    array_to_png(prev / "B_water_mask.png", res_b.water_mask, cmap="Blues")
    array_to_png(prev / "B_water_confidence.png", res_b.confidence, cmap="viridis", vmin=0, vmax=1)
    array_to_png(prev / "B_partition_roles.png", assignment.role_grid, cmap="Set1")
    by_role = evaluation["metrics_by_role"]
    print(f"      tiles {partition.counts} epochs {epochs} weights {class_weights}")
    for role in ("train", "val", "test"):
        entry = by_role.get(role, {})
        detail = entry.get("blocked_reason") or f"IoU {entry.get('iou')} F1 {entry.get('f1_dice')}"
        print(f"        {role:5s}: {detail}")
    print(f"      diagnosis: {evaluation['generalisation_diagnosis']}")

    # ---------------- C: real susceptibility from real DEM -----------------
    print("[5/9] Component C - susceptibility from real Copernicus DEM + DWR rivers ...")
    t = time.time()
    dem = rd.fetch_copernicus_dem(bbox=bbox, out_shape=SHAPE)["dem"]
    try:
        rivers = rd.fetch_arcgis_featurelayer(rd.LAYERS["rivers"], bbox)
        (out / "rivers.geojson").write_text(json.dumps(rivers), encoding="utf-8")
    except rd.RealDataError:
        rivers = {"features": []}
    river_mask = rd.rasterize_lines(rivers, transform, SHAPE)
    terr = rd.terrain_features(dem, river_mask, pixel_m)
    for name, arr in terr.items():
        write_geotiff(work / f"{name}.tif", arr, transform, "EPSG:4326")
    write_geotiff(
        work / "jrc_water.tif",
        (jrc["occurrence"] > 50).astype("uint8"),
        transform,
        "EPSG:4326",
        dtype="uint8",
    )
    write_geotiff(
        work / "sar_flood_ref.tif", flood.flood_binary, transform, "EPSG:4326", dtype="uint8"
    )
    # Primary validation: does the terrain surface rank the ACTUALLY-flooded
    # (real SAR) pixels above dry ground? JRC permanent water is a secondary,
    # independent reference.
    res_c = susceptibility.compute_susceptibility_index(
        work / "hand.tif",
        work / "slope.tif",
        work / "distance_to_river.tif",
        work / "twi.tif",
        work,
        reference_flood_path=work / "sar_flood_ref.tif",
        data_mode="real_licensed_inputs",
    )
    res_c_jrc = susceptibility.compute_susceptibility_index(
        work / "hand.tif",
        work / "slope.tif",
        work / "distance_to_river.tif",
        work / "twi.tif",
        work / "jrc_check",
        reference_flood_path=work / "jrc_water.tif",
        data_mode="real_licensed_inputs",
    )
    timings["susceptibility"] = round(time.time() - t, 1)
    metrics["susceptibility"] = {
        **{k: v for k, v in res_c.metrics.items() if k != "weights"},
        "data_mode": "real_licensed_inputs",
        "dem_range_m": [float(dem.min()), float(dem.max())],
        "river_features": len(rivers.get("features", [])),
        "auc_vs_jrc_permanent_water": res_c_jrc.metrics.get("auc"),
        "assumptions": (
            "Susceptibility from real Copernicus DEM GLO-30 + real DWR river "
            "network. Primary AUC is against the real Sentinel-1 flood extent; "
            "a secondary AUC against JRC Global Surface Water is also reported. "
            "Relative propensity, not flood depth."
        ),
    }
    array_to_png(prev / "scene_dem.png", dem, cmap="terrain")
    array_to_png(
        prev / "C_susceptibility.png", res_c.susceptibility_0_100, cmap="YlOrRd", vmin=0, vmax=100
    )
    print(
        f"      DEM {dem.min():.0f}-{dem.max():.0f} m | rivers {len(rivers.get('features', []))} | "
        f"AUC vs real SAR flood {res_c.metrics.get('auc')} | vs JRC {res_c_jrc.metrics.get('auc')}"
    )

    # ---------------- D: real building footprints --------------------------
    # Overture since 2026-07-29, OSM/Overpass as fallback. OSM returned 397
    # buildings across the 8 tambons against Overture's 54,978 -- ~0.7 %, which
    # matched the pipeline's own severely_incomplete flag -- and Overpass has
    # since stopped serving (expired certificate, no cache on a clean clone).
    print("[6/9] Component D - real building footprints (Overture, OSM fallback) ...")
    t = time.time()
    building_source = "unavailable"
    try:
        buildings, building_source = rd.fetch_buildings(
            bbox, cache_path=work / "buildings.json"
        )
        print(f"      source: {building_source} | {len(buildings)} footprints")
    except rd.RealDataError as exc:
        print(f"      no building source available ({exc}); skipping")
        buildings = []
    flood_dil = _dilate(flood.flood_binary.astype(bool), 3)
    feats, exposed = [], 0
    inv = ~transform
    for b in buildings:
        col, row = inv * (b["lon"], b["lat"])
        r, c = int(row), int(col)
        ex = bool(0 <= r < SHAPE[0] and 0 <= c < SHAPE[1] and flood_dil[r, c])
        exposed += int(ex)
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "building_id": b["id"],
                    "source": building_source,
                    "exposed_to_flood": ex,
                    "amenity": b["tags"].get("amenity", ""),
                },
                "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
            }
        )
    (out / "critical_infrastructure_footprints.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8"
    )
    timings["infrastructure"] = round(time.time() - t, 1)
    metrics["infrastructure"] = {
        "building_count": len(feats),
        "exposed_count": exposed,
        "data_mode": "real_licensed_inputs",
        "building_source": building_source,
        "extraction_method": (
            "Overture Maps footprints (real)"
            if building_source == "overture"
            else "OpenStreetMap footprints (real, fallback)"
        ),
        "assumptions": (
            "Real building footprints; exposure = footprint within the real SAR "
            "flood extent (dilated). Source changed from OSM/Overpass to Overture "
            "on 2026-07-29: OSM covered ~0.7% of the district (397 vs 54,978 "
            "footprints) and Overpass stopped serving. Overture aggregates OSM "
            "with ML-derived footprints, so its coverage is far higher but its "
            "per-building attribution is weaker. SAM 3 zero-shot on THEOS-2 "
            "remains the higher-resolution upgrade."
        ),
    }
    _render_buildings(prev / "D_buildings.png", flood.flood_binary, feats, transform, SHAPE)
    print(f"      {len(feats)} real buildings | {exposed} flood-exposed")

    # ---------------- F: real few-shot classifier --------------------------
    print("[7/9] Component F - few-shot classifier on real Sentinel-2 ...")
    t = time.time()
    res_f = embeddings.few_shot_flood_classifier(
        work / "s2.tif",
        work / "water_label.tif",
        out / "flood_classifier_embeddings.parquet",
        assignment,
        n_labels_per_class=40,
    )
    timings["embeddings"] = round(time.time() - t, 1)
    metrics["embeddings"] = {**res_f.metrics, "data_mode": "real_licensed_inputs"}
    f_by_role = res_f.metrics["metrics_by_role"]
    f_test = f_by_role.get("test", {})
    print(
        f"      labels {res_f.metrics['n_training_labels']} (train blocks only) | "
        f"test {f_test.get('blocked_reason') or 'IoU ' + str(f_test.get('iou'))}"
    )
    array_to_png(prev / "F_fewshot_prediction.png", res_f.predicted_mask, cmap="Blues")
    array_to_png(
        prev / "scene_flood_reference.png", (jrc["occurrence"] > 50).astype("uint8"), cmap="Blues"
    )

    # ---------------- A2: temporal SAR (opt-in) -----------------------------
    if args.temporal:
        _run_temporal_stage(args, bbox, work, prev, out, transform, subs, flood, metrics, timings)

    # ---------------- extra methods: baseline + E (opt-in) ------------------
    if args.all_methods:
        _run_extra_methods(args, bbox, work, prev, out, transform, res_c, metrics, timings)

    # ---------------- bridge: real subdistricts -> FPPS --------------------
    print("[8/9] Bridging real AI layers -> real sub-district priority ...")
    # Real decision-layer context supplies access gap, road criticality and
    # vulnerability. Previously these were synthesised from the AI signals,
    # which double-counted flooding and overstated how much of FPPS was real.
    try:
        context = aggregate.load_subdistrict_context(
            REPO_ROOT / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
            REPO_ROOT / "outputs" / "mae_sai_admin_context.geojson",
        )
        print(f"      context: {len(context.components)} subdistricts from the decision layer")
    except aggregate.AggregationError as exc:
        print(
            f"      WARNING: real context unavailable ({exc}); "
            "falling back to placeholders and forcing low confidence"
        )
        context = None

    ai_inputs = aggregate.aggregate_subdistrict_ai_inputs(
        subs["features"],
        flood.artifacts["probability"],
        res_c.artifacts["susceptibility"],
        out / "critical_infrastructure_footprints.geojson",
        context=context,
        source_name="Sentinel-1 RTC + Sentinel-2 + Copernicus DEM + DOPA/DWR/OSM/WorldPop (all real)",
        source_timestamp=flood.metrics["post_datetime"],
    )
    table = aggregate.build_fpps_input_table(ai_inputs, context=context)

    # D-02: candidate evidence reaches FPPS only through a signed, report-only
    # receipt. Fail-closed -- unsigned candidate figures are exactly what this
    # gate exists to prevent, and they are published to the Command surface.
    signing_key = _candidate_signing_key()
    scored, candidate_receipt = score_candidate_areas(
        table,
        source_metadata={
            "study_area_id": "mae_sai",
            "dataset_mode": "real_licensed_inputs",
            "source_timestamp": flood.metrics["post_datetime"],
            "generated_at": flood.metrics["post_datetime"],
        },
        model_run_id=f"realpipeline-mae-sai-{flood.metrics['post_datetime'][:10]}",
        signing_key=signing_key,
        key_id=os.environ.get("FLOODGUARD_ZONAL_SIGNING_KEY_ID", "candidate-local"),
        generated_at=flood.metrics["post_datetime"],
    )
    (out / "candidate_zonal_receipt.json").write_text(
        json.dumps(candidate_receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(
        f"      candidate receipt: {candidate_receipt['area_count']} areas, "
        f"can_feed_decision_layer={candidate_receipt['can_feed_decision_layer']}"
    )
    cols = [
        "subdistrict_id",
        "subdistrict_name",
        "flood_likelihood_0_100",
        "exposure_0_100",
        "access_gap_0_100",
        "road_criticality_0_100",
        "vulnerability_context_0_100",
        "fpps_0_100",
        "action_class",
        "top_reason",
        "confidence_class",
        "context_source",
        "ai_flood_share",
        "ai_susceptibility_mean",
        "ai_exposed_building_count",
        "population",
        "density_per_km2",
        "osm_building_count",
        "osm_completeness_ratio",
        "osm_completeness_flag",
        "flood_anchor_version",
        "exposure_anchor_version",
        "source_name",
        "source_timestamp",
        "assumptions",
    ]
    scored_out = scored.reindex(columns=[c for c in cols if c in scored.columns])
    scored_out.to_csv(out / "geoai_subdistrict_priority.csv", index=False)

    # Deterministic bilingual narratives (Component G) from the scored table.
    thai_names = {
        aggregate.normalise_subdistrict_id(f["properties"]["subdistrict_id"]): f["properties"].get(
            "subdistrict_name_th", ""
        )
        for f in subs["features"]
    }
    res_g = nr.generate_narratives(
        [
            nr.narrative_inputs_from_row(
                row,
                acquisition_date=flood.metrics["post_datetime"][:10],
                peak_offset_days=PEAK_OFFSET_DAYS,
                tambon_name_th=thai_names.get(
                    aggregate.normalise_subdistrict_id(row["subdistrict_id"]), ""
                ),
            )
            for row in scored_out.to_dict("records")
        ],
        out / "narratives.json",
    )
    metrics["narrative"] = res_g.metrics
    print(
        f"      narratives: {res_g.metrics['narrative_count']} tambons, "
        f"{res_g.metrics['languages']} (deterministic, reproducible)"
    )

    # ---------------- manifest, figures, page ------------------------------
    print("[9/9] Writing real metrics, annotated figures, and page ...")
    manifest = {
        "data_mode": "real_licensed_inputs",
        "scene": {
            "bounds": list(bbox),
            "size": SHAPE[0],
            "crs": "EPSG:4326",
            "flood_fraction": flood.metrics["flood_fraction"],
            "pixel_m": round(pixel_m, 1),
        },
        "sources": {
            "sentinel1": f"{pair['pre_id']} -> {pair['post_id']} (Planetary Computer, RTC)",
            "sentinel2": f"{s2['item_id']} ({s2['datetime'][:10]}, {s2['cloud_cover']:.3f}% cloud)",
            "dem": "Copernicus DEM GLO-30 (Planetary Computer)",
            "water_reference": "JRC Global Surface Water (Pekel et al. 2016)",
            "subdistricts": "DOPA sub-districts via NGIS ArcGIS",
            "rivers": "DWR natural streams via NGIS ArcGIS",
            "buildings": "OpenStreetMap (Overpass API)",
            "population": "WorldPop Thailand 100 m 2020 (via committed decision-layer context)",
            "decision_context": (
                "outputs/mae_sai_subdistrict_flood_inputs.csv"
                if context is not None
                else "placeholder (real context unavailable)"
            ),
        },
        "evaluation_protocol": {
            "partition": assignment.to_dict(),
            "scale_anchors": {
                "flood_likelihood": aggregate.DEFAULT_FLOOD_ANCHOR.version,
                "exposure": aggregate.DEFAULT_EXPOSURE_ANCHOR.version,
            },
            "headline_role": "test",
            "notes": (
                "Component B and F metrics are reported per partition role; the "
                "headline is the held-out test role. Preprocessing and label sampling "
                "use training blocks only. This is a runner-local spatial split, NOT a "
                "sealed multi-event partition under "
                "docs/immutable-multi-event-partitions-v1.md."
            ),
        },
        "timings_seconds": timings,
        "metrics": _json_safe(metrics),
        "components": [
            {
                "letter": c.letter,
                "key": c.key,
                "name": c.name,
                "tier": c.tier,
                "status": c.status,
                "ai_task": c.ai_task,
                "book_ref": c.book_ref,
            }
            for c in COMPONENTS
        ],
    }
    (out / "geoai_metrics.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _component_summary(out / "geoai_component_summary.csv", metrics, timings)
    annotate.render_annotated_models(prev, manifest["metrics"], prev / "annotated_models.png")
    annotate.render_decision_bridge(
        prev, scored_out, prev / "annotated_decision_bridge.png", subs=subs, bbox=bbox, is_real=True
    )
    page = write_geoai_page(out / "geoai.html", manifest, scored_out, prev)
    web = _write_web_bundle(manifest, scored_out, prev, res_g.narratives)

    print("\nALL-REAL run complete.")
    print(f"  {page}")
    if web:
        print(f"  {web} (role-surface bundle)")
    print("\nReal sub-district priority:")
    print(
        scored_out[
            [
                "subdistrict_name",
                "flood_likelihood_0_100",
                "exposure_0_100",
                "fpps_0_100",
                "action_class",
                "confidence_class",
            ]
        ].to_string(index=False)
    )


# ----------------------------------------------------------------------------- #
def _union_bbox(subs, buffer=0.01):
    xs, ys = [], []
    for f in subs["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    xs.append(x)
                    ys.append(y)
    return (min(xs) - buffer, min(ys) - buffer, max(xs) + buffer, max(ys) + buffer)


def _dilate(mask, radius=3):
    out = mask.copy()
    for _ in range(radius):
        out = (
            out
            | np.roll(out, 1, 0)
            | np.roll(out, -1, 0)
            | np.roll(out, 1, 1)
            | np.roll(out, -1, 1)
        )
    return out


def _run_temporal_stage(args, bbox, work, prev, out, transform, subs, flood, metrics, timings):
    """Component A2 -- flood as deviation from each pixel's own seasonal normal.

    This is the answer to Component A's two structural limits: an arbitrary
    single pre-event reference, and a post-event date fixed by the orbit rather
    than by the flood. It also produces something a pre/post pair cannot -- a
    multi-year per-tambon inundation history, which turns "how often does this
    tambon flood?" into an observed quantity and gives Component C a validation
    target with real meaning.
    """

    import time

    import numpy as np
    import pandas as pd

    from geoai_runner.realpipeline import real_data as rd
    from geoai_runner.realpipeline import sar_temporal as st
    from geoai_runner.realpipeline.raster_io import array_to_png, write_geotiff

    print("[A2] Temporal SAR - multi-year single-orbit baseline ...")
    t = time.time()
    try:
        series = rd.fetch_sentinel1_rtc_series(
            bbox=bbox,
            start=args.temporal_start,
            end=args.temporal_end,
            out_shape=SHAPE,
            cache_dir=work / "s1_series",
            max_scenes=args.temporal_max_scenes,
        )
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"      temporal series unavailable: {exc}")
        metrics["temporal_sar"] = {"blocked_reason": str(exc)}
        return

    event_date = flood.metrics["post_datetime"][:10]
    print(
        f"      {len(series)} scenes on relative orbit {series.relative_orbit} "
        f"({series.orbit_direction}) | discarded {series.discarded}"
    )
    print(f"      scenes per year: {series.scenes_per_year()}")

    try:
        # The event must not contaminate its own reference.
        baseline = st.build_seasonal_baseline(
            series,
            polarisation="vh",
            exclude_dates=[event_date],
        )
    except st.TemporalSarError as exc:
        print(f"      baseline not supportable: {exc}")
        metrics["temporal_sar"] = {"blocked_reason": str(exc)}
        return

    print(f"      baseline bins {baseline.season_labels} | coverage {baseline.coverage()}")

    event_scene = next((s for s in series.scenes if s.date == event_date), None)
    if event_scene is None:
        print(f"      event date {event_date} not in the series; skipping detection")
        metrics["temporal_sar"] = {
            "blocked_reason": f"event date {event_date} absent from the selected orbit",
            "baseline": baseline.to_dict(),
        }
        return

    result = st.detect_temporal_flood(
        st.to_db(event_scene.read("vh")),
        baseline,
        event_scene.month,
        permanent_water=flood.permanent_water,
    )
    write_geotiff(
        work / "temporal_flood_probability.tif", result.probability, transform, "EPSG:4326"
    )
    write_geotiff(work / "temporal_zscore.tif", result.zscore, transform, "EPSG:4326")
    array_to_png(
        prev / "A2_temporal_probability.png",
        np.nan_to_num(result.probability),
        cmap="turbo",
        vmin=0,
        vmax=1,
    )
    array_to_png(
        prev / "A2_temporal_zscore.png", np.nan_to_num(result.zscore), cmap="RdBu", vmin=-8, vmax=8
    )

    single_pair = float(flood.metrics["flood_fraction"])
    temporal = float(result.metrics["open_water_fraction"])
    print(
        f"      single pre/post pair: {single_pair * 100:.2f}% | "
        f"temporal deviation: {temporal * 100:.2f}% of district"
    )
    print(
        f"      possible flooded vegetation: "
        f"{result.metrics['flooded_vegetation_fraction'] * 100:.2f}%"
    )

    # ---- per-tambon inundation history: the genuinely new product ----------
    unit_masks = _subdistrict_masks(subs, transform, SHAPE)
    history = st.inundation_history(
        series, baseline, unit_masks, permanent_water=flood.permanent_water
    )
    frequency = st.inundation_frequency(history)
    pd.DataFrame(history).to_csv(out / "inundation_history.csv", index=False)
    pd.DataFrame([{"subdistrict_id": k, **v} for k, v in sorted(frequency.items())]).to_csv(
        out / "inundation_frequency.csv", index=False
    )

    timings["temporal_sar"] = round(time.time() - t, 1)
    metrics["temporal_sar"] = {
        **result.metrics,
        "data_mode": "real_licensed_inputs",
        "event_date": event_date,
        "single_pair_flood_fraction": single_pair,
        "temporal_open_water_fraction": temporal,
        "inundation_frequency": frequency,
        # Calibration is deliberately not fitted: there is no licensed reference
        # for this event yet, and JRC permanent water cannot certify the flood end
        # of the curve. calibration.fit_calibration is ready for the moment a
        # qualified mask clears licensing.
        "calibration": {
            "status": "blocked_no_qualified_reference",
            "candidate_reference": (
                "UNOSAT/UNITAR satellite-detected water extent, Mae Sai District, "
                "13-19 September 2024 - pending licensing per "
                "docs/reference_mask_licensing_log.md"
            ),
            "fit_entrypoint": "geoai_runner.realpipeline.calibration.fit_calibration",
        },
    }
    print(
        f"      wrote inundation history ({len(history)} rows) and frequency "
        f"for {len(frequency)} tambons"
    )
    print("      calibration: blocked (no licensed reference for this event yet)")


def _subdistrict_masks(subs, transform, shape):
    """Rasterise each sub-district polygon to a boolean mask."""

    from rasterio.features import rasterize

    masks = {}
    for feature in subs["features"]:
        sid = str(feature["properties"]["subdistrict_id"])
        masks[sid] = rasterize(
            [(feature["geometry"], 1)],
            out_shape=shape,
            transform=transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
    return masks


def _run_extra_methods(args, bbox, work, prev, out, transform, res_c, metrics, timings):
    """Run the OmniWaterMask baseline and Component E (built-up encroachment).

    Component G no longer lives here: the deterministic narrative generator runs
    unconditionally from the scored decision table in :func:`main`, because it is
    fast, offline and reproducible -- none of which was true of the Moondream
    path it replaced.
    """

    import time

    from geoai_runner.realpipeline import encroachment as en
    from geoai_runner.realpipeline import water_baseline as wb
    from geoai_runner.realpipeline.raster_io import array_to_png, write_geotiff

    # OmniWaterMask baseline (Component B sanity check)
    print("[E1] OmniWaterMask baseline (real Sentinel-2) ...")
    try:
        t = time.time()
        base = wb.run_omniwatermask_baseline(
            work / "s2.tif", work, reference_mask_path=work / "water_label.tif"
        )
        timings["omniwatermask"] = round(time.time() - t, 1)
        metrics["omniwatermask"] = base.metrics
        array_to_png(prev / "baseline_omniwatermask.png", base.water_mask, cmap="Blues")
        print(
            f"      water {base.metrics.get('water_fraction')} | "
            f"IoU vs U-Net labels {base.metrics.get('iou_vs_unet_labels')}"
        )
    except Exception as exc:  # pragma: no cover
        print(f"      OmniWaterMask unavailable: {exc}")

    # Component E: built-up encroachment from a multi-temporal built-up product.
    # ChangeStar returned a resolution-limited null on 10 m Sentinel-2; that
    # result is preserved in encroachment.CHANGESTAR_NULL_RESULT and carried into
    # the metrics as `superseded_method`.
    print("[E2] Component E - built-up encroachment (GHSL epochs) ...")
    try:
        t = time.time()
        # Susceptibility is written on the SAME grid the change product is read
        # onto, and reproject_to_grid refuses to proceed if the extents disagree.
        write_geotiff(work / "susc_for_enc.tif", res_c.susceptibility_0_100, transform, "EPSG:4326")
        res_e = en.detect_builtup_change(
            bbox,
            args.encroachment_t1,
            args.encroachment_t2,
            work,
            susceptibility_path=work / "susc_for_enc.tif",
        )
        timings["encroachment"] = round(time.time() - t, 1)
        metrics["encroachment"] = res_e.metrics
        array_to_png(prev / "E_encroachment.png", res_e.change_mask, cmap="Reds")
        share = res_e.metrics.get("floodplain_share_of_growth")
        print(
            f"      built-up growth {res_e.metrics.get('growth_cell_fraction')} | "
            f"share inside floodplain {share}"
        )
        print(
            f"      mean delta in/out floodplain: "
            f"{res_e.metrics.get('mean_delta_in_floodplain')} / "
            f"{res_e.metrics.get('mean_delta_outside_floodplain')}"
        )
    except Exception as exc:  # pragma: no cover
        print(f"      built-up change unavailable: {exc}")
        metrics["encroachment"] = {
            "blocked_reason": str(exc),
            "superseded_method": en.CHANGESTAR_NULL_RESULT,
        }


def _write_web_bundle(manifest, scored, prev, narratives=None):
    """Emit the role-surface bundle: apps/web/public/geoai/{json,images}.

    The Next.js /command and /studio surfaces read this to render the real
    GeoAI evidence panel (no separate dashboard). Skipped if apps/web is absent.
    """

    import shutil

    web = REPO_ROOT / "apps" / "web" / "public" / "geoai"
    if not (REPO_ROOT / "apps" / "web").exists():
        return None
    web.mkdir(parents=True, exist_ok=True)
    m = manifest["metrics"]
    a, b, c, d = (
        m.get("sar_flood", {}),
        m.get("water_unet", {}),
        m.get("susceptibility", {}),
        m.get("infrastructure", {}),
    )

    def pct(x):
        return round(float(x) * 100, 2)

    bundle = {
        "data_mode": manifest["data_mode"],
        "study_area": "Mae Sai District, Chiang Rai",
        "generated_at": a.get("post_datetime", ""),
        "official_warning": False,
        # D-02: the payload carried fpps values with no tier marker at all, so
        # a reader could not tell candidate figures from governed ones. These
        # three fields make the tier machine-readable rather than editorial.
        "evidence_tier": "candidate",
        "can_feed_decision_layer": False,
        "aggregation_status": "report_only",
        "sources": manifest.get("sources", {}),
        "evaluation_protocol": manifest.get("evaluation_protocol", {}),
        "headline": {
            "sar_flood_pct": pct(a.get("flood_fraction", 0)),
            "sar_pre": a.get("pre_datetime", "")[:10],
            "sar_post": a.get("post_datetime", "")[:10],
            "unet_iou": _role_metric(b, "test", "iou"),
            "unet_f1": _role_metric(b, "test", "f1_dice"),
            "unet_metric_role": "test",
            "susc_auc": c.get("auc"),
            "susc_auc_jrc": c.get("auc_vs_jrc_permanent_water"),
            "buildings": d.get("building_count"),
            "exposed": d.get("exposed_count"),
        },
        "components": [
            {
                "letter": "A",
                "name": "SAR flood-extent detection",
                "book": "Ch. 12 · change detection",
                "metric": f"{pct(a.get('flood_fraction', 0))}% of district flooded",
                "detail": f"Sentinel-1 RTC · pre {a.get('pre_datetime', '')[:10]} → post {a.get('post_datetime', '')[:10]}",
                "input": "/geoai/scene_sar_post_vh.png",
                "output": "/geoai/A_sar_flood_probability.png",
            },
            {
                "letter": "B",
                "name": "U-Net water-mask refinement",
                "book": "Ch. 9 · semantic segmentation",
                "metric": _unet_metric_text(b),
                "detail": (
                    "Sentinel-2 L2A · ImageNet-pretrained ResNet · "
                    f"{_tile_count(b, 'train')} training tiles · "
                    f"held-out spatial blocks ({_buffer_m(b):.0f} m buffer)"
                ),
                "input": "/geoai/scene_s2_rgb.png",
                "output": "/geoai/B_water_mask.png",
            },
            {
                "letter": "C",
                "name": "Flood susceptibility surface",
                "book": "Ch. 13 · pixel regression",
                "metric": f"AUC {c.get('auc')} vs the real Sentinel-1 flood extent",
                "detail": f"Copernicus DEM GLO-30 + {c.get('river_features', '?')} DWR river features",
                "input": "/geoai/scene_dem.png",
                "output": "/geoai/C_susceptibility.png",
            },
            {
                "letter": "D",
                "name": "Critical-infrastructure extraction",
                "book": "Ch. 14 · footprints",
                "metric": f"{d.get('building_count')} buildings · {d.get('exposed_count')} flood-exposed",
                "detail": "OpenStreetMap building footprints vs SAR flood extent (coverage-flagged)",
                "input": "/geoai/scene_s2_rgb.png",
                "output": "/geoai/D_buildings.png",
            },
        ],
        "subdistricts": [
            {
                "id": r["subdistrict_id"],
                "name": r["subdistrict_name"],
                "flood_likelihood": round(float(r["flood_likelihood_0_100"]), 1),
                "exposure": round(float(r["exposure_0_100"]), 1),
                "fpps": round(float(r["fpps_0_100"]), 1),
                "action": r["action_class"],
                "confidence": r["confidence_class"],
                "population": r.get("population"),
                "context_source": r.get("context_source"),
                "narrative_en": (narratives or {}).get(r["subdistrict_name"], {}).get("en"),
                "narrative_th": (narratives or {}).get(r["subdistrict_name"], {}).get("th"),
            }
            for r in scored.to_dict("records")
        ],
        "additional_methods": _additional_methods(m, narratives),
        "limitations": [
            "Nearest post-event same-orbit Sentinel-1 scene (2024-09-15) is ~4 days after the "
            "~Sep-11 flood peak, so extent is residual and under-represents the peak.",
            "U-Net labels are the MNDWI water index (weak supervision from a physical index, not "
            "hand annotation); metrics measure agreement with that index on held-out spatial "
            "blocks, not against a gold human mask.",
            "Susceptibility is relative propensity, not flood depth. Non-operational; not an "
            "official warning.",
            "flood_likelihood and exposure use fixed versioned anchors "
            f"({manifest.get('evaluation_protocol', {}).get('scale_anchors', {})}), so values are "
            "absolute rather than ranked within the district.",
            "OpenStreetMap building coverage in Mae Sai is 0.9-5.1% of the population-implied "
            "expectation, so building counts are diagnostic only and do not enter exposure.",
            "The spatial holdout is runner-local. It is NOT a sealed multi-event partition and "
            "does not clear the qualified-label gates.",
        ],
    }
    (web / "mae-sai-real.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    for name in (
        "scene_sar_post_vh.png",
        "A_sar_flood_probability.png",
        "scene_s2_rgb.png",
        "B_water_mask.png",
        "scene_dem.png",
        "C_susceptibility.png",
        "D_buildings.png",
        "annotated_decision_bridge.png",
        "annotated_models.png",
        "baseline_omniwatermask.png",
        "E_encroachment.png",
        "F_fewshot_prediction.png",
    ):
        src = prev / name
        if src.exists():
            shutil.copy(src, web / name)
    return web / "mae-sai-real.json"


def _role_metric(block, role, key):
    """Read one metric from a role-scoped result, or None when it was blocked."""

    entry = (block or {}).get("metrics_by_role", {}).get(role, {})
    return entry.get(key)


def _tile_count(block, role):
    return (block or {}).get("tiling", {}).get("tiles_by_role", {}).get(role, "?")


def _buffer_m(block):
    geometry = (block or {}).get("partition", {}).get("geometry", {})
    return float(geometry.get("buffer_m", 0.0))


def _unet_metric_text(block):
    """Render Component B's headline, naming the role or the reason it is absent."""

    entry = (block or {}).get("metrics_by_role", {}).get("test", {})
    if "blocked_reason" in entry:
        return f"held-out metric unavailable ({entry['blocked_reason']})"
    return f"IoU {entry.get('iou')} · F1 {entry.get('f1_dice')} (held-out test blocks)"


def _additional_methods(m, narratives):
    """Baseline and roadmap methods (OmniWaterMask, E, F, G) for the role surfaces."""

    items = []
    om = m.get("omniwatermask")
    if om:
        items.append(
            {
                "letter": "*",
                "name": "OmniWaterMask baseline",
                "book": "Ch. 9 · pre-trained (zero training)",
                "metric": f"IoU {om.get('iou_vs_unet_labels', 'n/a')} vs MNDWI labels",
                "detail": "Sensor-agnostic optical water model — a check on the trained U-Net.",
                "image": "/geoai/baseline_omniwatermask.png",
            }
        )
    en = m.get("encroachment")
    if en:
        share = en.get("floodplain_share_of_growth")
        blocked = en.get("blocked_reason")
        items.append(
            {
                "letter": "E",
                "name": "Built-up encroachment (multi-temporal built-up surface)",
                "book": "Ch. 12 · change detection / Ch. 19 · ready-to-use products",
                "metric": (
                    f"unavailable ({blocked})"
                    if blocked
                    else f"{round(float(share) * 100, 1)}% of built-up growth inside the floodplain"
                    if share is not None
                    else "no built-up growth above threshold"
                ),
                "detail": (
                    f"{en.get('t1_year', '?')} → {en.get('t2_year', '?')} built-up surface fraction. "
                    "Replaces ChangeStar, which returned a resolution-limited 0% on 10 m "
                    "Sentinel-2; that null is retained as `superseded_method`."
                ),
                "image": "/geoai/E_encroachment.png",
            }
        )
    emb = m.get("embeddings")
    if emb:
        test = emb.get("metrics_by_role", {}).get("test", {})
        items.append(
            {
                "letter": "F",
                "name": "Label-scarce embeddings (few-shot)",
                "book": "Ch. 16 · foundation embeddings",
                "metric": (
                    f"unavailable ({test['blocked_reason']})"
                    if "blocked_reason" in test
                    else f"IoU {test.get('iou')} on held-out blocks from "
                    f"{emb.get('n_training_labels', '?')} labels"
                ),
                "detail": (
                    "Lightweight classifier on Sentinel-2 features. The feature vector contains "
                    "the bands the MNDWI target is derived from, so this demonstrates the "
                    "workflow rather than proving few-shot generalisation."
                ),
                "image": "/geoai/F_fewshot_prediction.png",
            }
        )
    ng = m.get("narrative")
    if ng and narratives:
        first = next(iter(narratives.values()), {})
        items.append(
            {
                "letter": "G",
                "name": "Plain-language narrative (deterministic)",
                "book": "Ch. 15 · communication",
                "metric": f"{ng.get('narrative_count', len(narratives))} bilingual narratives (EN/TH)",
                "detail": (first.get("en", "")[:200]),
                "image": None,
                "narratives": narratives,
            }
        )
    return items


def _render_buildings(path, flood, feats, transform, shape):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4, 4), dpi=110)
    ax.imshow(flood, cmap="Blues", alpha=0.75)
    inv = ~transform
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        col, row = inv * (lon, lat)
        ax.plot(
            col,
            row,
            "s",
            markersize=1.6,
            color="red" if f["properties"]["exposed_to_flood"] else "black",
        )
    ax.set_xlim(0, shape[1])
    ax.set_ylim(shape[0], 0)
    ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def _component_summary(path, metrics, timings):
    rows = []
    for c in COMPONENTS:
        m = metrics.get(c.key, {})
        rows.append(
            {
                "component": f"{c.letter}. {c.name}",
                "tier": c.tier,
                "status": c.status,
                "ai_task": c.ai_task,
                "book_ref": c.book_ref,
                "data_mode": m.get("data_mode", ""),
                "iou": m.get("iou", ""),
                "f1_dice": m.get("f1_dice", ""),
                "auc": m.get("auc", ""),
                "runtime_s": timings.get(c.key, ""),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _json_safe(o):
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_json_safe(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o


if __name__ == "__main__":
    main()
