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

from geoai_runner.realpipeline import annotate, embeddings, real_data as rd  # noqa: E402
from geoai_runner.realpipeline import susceptibility, water_unet  # noqa: E402
from geoai_runner.realpipeline.geoai_page import write_geoai_page  # noqa: E402
from geoai_runner.realpipeline.raster_io import array_to_png, write_geotiff  # noqa: E402
from geoai_runner.realpipeline.registry import COMPONENTS  # noqa: E402
from floodguard.scoring import score_subdistricts  # noqa: E402

SHAPE = (1024, 1024)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="Fewer U-Net epochs.")
    ap.add_argument("--epochs", type=int, default=None)
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
    print(f"      {len(subs['features'])} tambons | bbox {tuple(round(v,3) for v in bbox)} | ~{pixel_m:.0f} m/px")

    # ---------------- A: real Sentinel-1 flood -----------------------------
    print("[2/9] Component A - real Sentinel-1 flood extent ...")
    t = time.time()
    pair = rd.fetch_sentinel1_rtc_pair(bbox=bbox, out_shape=SHAPE)
    flood = rd.real_sar_flood_extent(pair, work, drop_threshold_db=2.0, multilook=3)
    timings["sar_flood"] = round(time.time() - t, 1)
    metrics["sar_flood"] = {**flood.metrics, "data_mode": "real_licensed_inputs"}
    post_vh_db = rd._to_db(rd._boxcar(pair["bands"]["post_vh"], 3))
    array_to_png(prev / "scene_sar_post_vh.png", post_vh_db, cmap="gray", vmin=-25, vmax=-5)
    array_to_png(prev / "A_sar_flood_probability.png", flood.flood_probability, cmap="turbo", vmin=0, vmax=1)
    array_to_png(prev / "A_sar_flood_binary.png", flood.flood_binary, cmap="Blues")
    print(f"      pre {pair['pre_datetime'][:10]} post {pair['post_datetime'][:10]} | "
          f"flood {flood.metrics['flood_fraction']*100:.2f}%")

    # ---------------- real Sentinel-2 + real water labels ------------------
    print("[3/9] Real Sentinel-2 L2A composite ...")
    t = time.time()
    s2 = rd.fetch_sentinel2_composite(bbox=bbox, out_shape=SHAPE)
    stack = s2["stack"]
    green, nir, swir1 = stack[1], stack[3], stack[4]
    mndwi = (green - swir1) / (green + swir1 + 1e-6)
    water_label = (mndwi > 0.0).astype("uint8")  # real spectral-index water mask
    jrc = rd.fetch_jrc_surface_water(bbox=bbox, out_shape=SHAPE)
    timings["sentinel2"] = round(time.time() - t, 1)
    print(f"      {s2['datetime'][:10]} cloud {s2['cloud_cover']:.3f}% | "
          f"MNDWI water {water_label.mean()*100:.2f}% | JRC occ>50 {(jrc['occurrence']>50).mean()*100:.2f}%")
    array_to_png(prev / "scene_s2_rgb.png", np.clip(stack[[2, 1, 0]] * 3.5, 0, 1))
    write_geotiff(work / "s2.tif", stack, transform, "EPSG:4326")
    write_geotiff(work / "water_label.tif", water_label, transform, "EPSG:4326", dtype="uint8")

    # ---------------- B: real U-Net water segmentation ---------------------
    print("[4/9] Component B - U-Net on real Sentinel-2 (ImageNet encoder) ...")
    t = time.time()
    epochs = args.epochs or (10 if args.fast else 30)
    imgs, labs, ntiles = water_unet.prepare_training_tiles(
        work / "s2.tif", work / "water_label.tif", work / "tiles", tile_size=128, stride=96
    )
    model = water_unet.train_water_unet(
        imgs, labs, work / "unet", num_channels=6, encoder_name="resnet18",
        encoder_weights="imagenet", num_epochs=epochs, target_size=(128, 128),
        class_weights=(1.0, 25.0), learning_rate=0.001,
    )
    res_b = water_unet.infer_water_mask(
        model, work / "s2.tif", work, num_channels=6, encoder_name="resnet18",
        window_size=128, overlap=32, reference_mask_path=work / "water_label.tif",
    )
    timings["water_unet"] = round(time.time() - t, 1)
    metrics["water_unet"] = {
        **res_b.metrics, "data_mode": "real_licensed_inputs", "n_training_tiles": ntiles,
        "epochs": epochs, "encoder_weights": "imagenet",
        "assumptions": ("U-Net trained on real Sentinel-2 with labels derived from the "
                        "real MNDWI water index (weak supervision from a physical index, "
                        "not hand annotation); scored against that same index."),
    }
    array_to_png(prev / "B_water_mask.png", res_b.water_mask, cmap="Blues")
    array_to_png(prev / "B_water_confidence.png", res_b.confidence, cmap="viridis", vmin=0, vmax=1)
    print(f"      tiles {ntiles} epochs {epochs} | IoU {res_b.metrics.get('iou')} F1 {res_b.metrics.get('f1_dice')}")

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
    write_geotiff(work / "jrc_water.tif", (jrc["occurrence"] > 50).astype("uint8"),
                  transform, "EPSG:4326", dtype="uint8")
    write_geotiff(work / "sar_flood_ref.tif", flood.flood_binary, transform,
                  "EPSG:4326", dtype="uint8")
    # Primary validation: does the terrain surface rank the ACTUALLY-flooded
    # (real SAR) pixels above dry ground? JRC permanent water is a secondary,
    # independent reference.
    res_c = susceptibility.compute_susceptibility_index(
        work / "hand.tif", work / "slope.tif", work / "distance_to_river.tif",
        work / "twi.tif", work, reference_flood_path=work / "sar_flood_ref.tif",
        data_mode="real_licensed_inputs",
    )
    res_c_jrc = susceptibility.compute_susceptibility_index(
        work / "hand.tif", work / "slope.tif", work / "distance_to_river.tif",
        work / "twi.tif", work / "jrc_check", reference_flood_path=work / "jrc_water.tif",
        data_mode="real_licensed_inputs",
    )
    timings["susceptibility"] = round(time.time() - t, 1)
    metrics["susceptibility"] = {
        **{k: v for k, v in res_c.metrics.items() if k != "weights"},
        "data_mode": "real_licensed_inputs", "dem_range_m": [float(dem.min()), float(dem.max())],
        "river_features": len(rivers.get("features", [])),
        "auc_vs_jrc_permanent_water": res_c_jrc.metrics.get("auc"),
        "assumptions": ("Susceptibility from real Copernicus DEM GLO-30 + real DWR river "
                        "network. Primary AUC is against the real Sentinel-1 flood extent; "
                        "a secondary AUC against JRC Global Surface Water is also reported. "
                        "Relative propensity, not flood depth."),
    }
    array_to_png(prev / "scene_dem.png", dem, cmap="terrain")
    array_to_png(prev / "C_susceptibility.png", res_c.susceptibility_0_100, cmap="YlOrRd", vmin=0, vmax=100)
    print(f"      DEM {dem.min():.0f}-{dem.max():.0f} m | rivers {len(rivers.get('features',[]))} | "
          f"AUC vs real SAR flood {res_c.metrics.get('auc')} | vs JRC {res_c_jrc.metrics.get('auc')}")

    # ---------------- D: real OSM buildings --------------------------------
    print("[6/9] Component D - real OpenStreetMap building footprints ...")
    t = time.time()
    try:
        buildings = rd.fetch_osm_buildings(bbox, cache_path=work / "osm_buildings.json")
    except rd.RealDataError as exc:
        print(f"      Overpass unavailable ({exc}); skipping"); buildings = []
    flood_dil = _dilate(flood.flood_binary.astype(bool), 3)
    feats, exposed = [], 0
    inv = ~transform
    for b in buildings:
        col, row = inv * (b["lon"], b["lat"])
        r, c = int(row), int(col)
        ex = bool(0 <= r < SHAPE[0] and 0 <= c < SHAPE[1] and flood_dil[r, c])
        exposed += int(ex)
        feats.append({"type": "Feature",
                      "properties": {"osm_id": b["id"], "exposed_to_flood": ex,
                                     "amenity": b["tags"].get("amenity", "")},
                      "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]}})
    (out / "critical_infrastructure_footprints.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    timings["infrastructure"] = round(time.time() - t, 1)
    metrics["infrastructure"] = {
        "building_count": len(feats), "exposed_count": exposed,
        "data_mode": "real_licensed_inputs", "extraction_method": "OpenStreetMap footprints (real)",
        "assumptions": ("Real OSM building footprints; exposure = footprint within the "
                        "real SAR flood extent (dilated). SAM 3 zero-shot on THEOS-2 remains "
                        "the higher-resolution upgrade."),
    }
    _render_buildings(prev / "D_buildings.png", flood.flood_binary, feats, transform, SHAPE)
    print(f"      {len(feats)} real buildings | {exposed} flood-exposed")

    # ---------------- F: real few-shot classifier --------------------------
    print("[7/9] Component F - few-shot classifier on real Sentinel-2 ...")
    t = time.time()
    res_f = embeddings.few_shot_flood_classifier(
        work / "s2.tif", work / "water_label.tif", out / "flood_classifier_embeddings.parquet",
        n_labels_per_class=40)
    timings["embeddings"] = round(time.time() - t, 1)
    metrics["embeddings"] = {**res_f.metrics, "data_mode": "real_licensed_inputs"}
    array_to_png(prev / "F_fewshot_prediction.png", res_f.predicted_mask, cmap="Blues")
    array_to_png(prev / "scene_flood_reference.png", (jrc["occurrence"] > 50).astype("uint8"), cmap="Blues")

    # ---------------- bridge: real subdistricts -> FPPS --------------------
    print("[8/9] Bridging real AI layers -> real sub-district priority ...")
    table = _aggregate(subs, flood, res_c.susceptibility_0_100, feats, transform, SHAPE)
    scored = score_subdistricts(table)
    cols = ["subdistrict_id", "subdistrict_name", "flood_likelihood_0_100", "exposure_0_100",
            "access_gap_0_100", "road_criticality_0_100", "vulnerability_context_0_100",
            "fpps_0_100", "action_class", "top_reason", "confidence_class",
            "ai_flood_pct", "ai_susceptibility_mean", "ai_building_count",
            "ai_exposed_building_count", "source_name", "source_timestamp", "assumptions"]
    scored_out = scored.reindex(columns=[c for c in cols if c in scored.columns])
    scored_out.to_csv(out / "geoai_subdistrict_priority.csv", index=False)

    # ---------------- manifest, figures, page ------------------------------
    print("[9/9] Writing real metrics, annotated figures, and page ...")
    manifest = {
        "data_mode": "real_licensed_inputs",
        "scene": {"bounds": list(bbox), "size": SHAPE[0], "crs": "EPSG:4326",
                  "flood_fraction": flood.metrics["flood_fraction"],
                  "pixel_m": round(pixel_m, 1)},
        "sources": {
            "sentinel1": f"{pair['pre_id']} -> {pair['post_id']} (Planetary Computer, RTC)",
            "sentinel2": f"{s2['item_id']} ({s2['datetime'][:10]}, {s2['cloud_cover']:.3f}% cloud)",
            "dem": "Copernicus DEM GLO-30 (Planetary Computer)",
            "water_reference": "JRC Global Surface Water (Pekel et al. 2016)",
            "subdistricts": "DOPA sub-districts via NGIS ArcGIS",
            "rivers": "DWR natural streams via NGIS ArcGIS",
            "buildings": "OpenStreetMap (Overpass API)",
        },
        "timings_seconds": timings,
        "metrics": _json_safe(metrics),
        "components": [{"letter": c.letter, "key": c.key, "name": c.name, "tier": c.tier,
                        "status": c.status, "ai_task": c.ai_task, "book_ref": c.book_ref}
                       for c in COMPONENTS],
    }
    (out / "geoai_metrics.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _component_summary(out / "geoai_component_summary.csv", metrics, timings)
    annotate.render_annotated_models(prev, manifest["metrics"], prev / "annotated_models.png")
    annotate.render_decision_bridge(prev, scored_out, prev / "annotated_decision_bridge.png",
                                    subs=subs, bbox=bbox, is_real=True)
    page = write_geoai_page(out / "geoai.html", manifest, scored_out, prev)
    web = _write_web_bundle(manifest, scored_out, prev)

    print("\nALL-REAL run complete.")
    print(f"  {page}")
    if web:
        print(f"  {web} (role-surface bundle)")
    print("\nReal sub-district priority:")
    print(scored_out[["subdistrict_name", "flood_likelihood_0_100", "exposure_0_100",
                      "fpps_0_100", "action_class", "confidence_class"]].to_string(index=False))


# ----------------------------------------------------------------------------- #
def _union_bbox(subs, buffer=0.01):
    xs, ys = [], []
    for f in subs["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                for x, y in ring:
                    xs.append(x); ys.append(y)
    return (min(xs) - buffer, min(ys) - buffer, max(xs) + buffer, max(ys) + buffer)


def _dilate(mask, radius=3):
    out = mask.copy()
    for _ in range(radius):
        out = (out | np.roll(out, 1, 0) | np.roll(out, -1, 0)
               | np.roll(out, 1, 1) | np.roll(out, -1, 1))
    return out


def _aggregate(subs, flood, susc, buildings, transform, shape):
    from rasterio.features import rasterize

    inv = ~transform
    pts = []
    for f in buildings:
        lon, lat = f["geometry"]["coordinates"]
        col, row = inv * (lon, lat)
        pts.append((int(row), int(col), bool(f["properties"]["exposed_to_flood"])))

    rows, fmax, bmax = [], 0.0, 1
    tmp = []
    for f in subs["features"]:
        m = rasterize([(f["geometry"], 1)], out_shape=shape, transform=transform,
                      fill=0, all_touched=False, dtype="uint8").astype(bool)
        if m.sum() == 0:
            continue
        fp = float(flood.flood_binary[m].mean())
        sc = float(susc[m].mean()) / 100.0
        bc = sum(1 for r, c, _ in pts if 0 <= r < shape[0] and 0 <= c < shape[1] and m[r, c])
        ec = sum(1 for r, c, e in pts if e and 0 <= r < shape[0] and 0 <= c < shape[1] and m[r, c])
        fmax = max(fmax, fp); bmax = max(bmax, bc)
        tmp.append((f["properties"], fp, sc, bc, ec))

    emax = max([e for *_, e in tmp] or [0]) or 1
    for props, fp, sc, bc, ec in tmp:
        scaled = fp / fmax if fmax > 0 else 0.0
        likelihood = round(float(np.clip(0.55 * scaled + 0.45 * sc, 0, 1) * 100), 1)
        exposure = round(float(np.clip(0.6 * (bc / bmax) + 0.4 * scaled, 0, 1) * 100), 1)
        conf = "high" if (fp > 0 and sc > 0.4) or (fp == 0 and sc < 0.4) else "medium"
        rows.append({
            "subdistrict_id": props.get("subdistrict_id"),
            "subdistrict_name": props.get("subdistrict_name"),
            "flood_likelihood_0_100": likelihood,
            "exposure_0_100": exposure,
            "access_gap_0_100": round(min(100.0, 0.6 * likelihood + 0.4 * exposure), 1),
            "road_criticality_0_100": round(40.0 + 60.0 * (ec / emax), 1),
            "vulnerability_context_0_100": 50.0,
            "ai_flood_pct": round(fp * 100, 3),
            "ai_susceptibility_mean": round(sc, 3),
            "ai_building_count": bc,
            "ai_exposed_building_count": ec,
            "confidence_class": conf,
            "source_name": "Sentinel-1 RTC + Sentinel-2 + Copernicus DEM + DOPA/DWR/OSM (all real)",
            "source_timestamp": flood.metrics["post_datetime"],
            "assumptions": flood.metrics["assumptions"],
        })
    return pd.DataFrame(rows)


def _write_web_bundle(manifest, scored, prev):
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
    a, b, c, d = (m.get("sar_flood", {}), m.get("water_unet", {}),
                  m.get("susceptibility", {}), m.get("infrastructure", {}))

    def pct(x):
        return round(float(x) * 100, 2)

    bundle = {
        "data_mode": manifest["data_mode"],
        "study_area": "Mae Sai District, Chiang Rai",
        "generated_at": a.get("post_datetime", ""),
        "official_warning": False,
        "sources": manifest.get("sources", {}),
        "headline": {
            "sar_flood_pct": pct(a.get("flood_fraction", 0)),
            "sar_pre": a.get("pre_datetime", "")[:10], "sar_post": a.get("post_datetime", "")[:10],
            "unet_iou": b.get("iou"), "unet_f1": b.get("f1_dice"),
            "susc_auc": c.get("auc"), "susc_auc_jrc": c.get("auc_vs_jrc_permanent_water"),
            "buildings": d.get("building_count"), "exposed": d.get("exposed_count"),
        },
        "components": [
            {"letter": "A", "name": "SAR flood-extent detection", "book": "Ch. 12 · change detection",
             "metric": f"{pct(a.get('flood_fraction', 0))}% of district flooded",
             "detail": f"Sentinel-1 RTC · pre {a.get('pre_datetime','')[:10]} → post {a.get('post_datetime','')[:10]}",
             "input": "/geoai/scene_sar_post_vh.png", "output": "/geoai/A_sar_flood_probability.png"},
            {"letter": "B", "name": "U-Net water-mask refinement", "book": "Ch. 9 · semantic segmentation",
             "metric": f"IoU {b.get('iou')} · F1 {b.get('f1_dice')}",
             "detail": f"Sentinel-2 L2A · ImageNet-pretrained ResNet · {b.get('n_training_tiles','?')} tiles",
             "input": "/geoai/scene_s2_rgb.png", "output": "/geoai/B_water_mask.png"},
            {"letter": "C", "name": "Flood susceptibility surface", "book": "Ch. 13 · pixel regression",
             "metric": f"AUC {c.get('auc')} vs JRC surface water",
             "detail": f"Copernicus DEM GLO-30 + {c.get('river_features','?')} DWR river features",
             "input": "/geoai/scene_dem.png", "output": "/geoai/C_susceptibility.png"},
            {"letter": "D", "name": "Critical-infrastructure extraction", "book": "Ch. 14 · footprints",
             "metric": f"{d.get('building_count')} buildings · {d.get('exposed_count')} flood-exposed",
             "detail": "OpenStreetMap building footprints vs SAR flood extent",
             "input": "/geoai/scene_s2_rgb.png", "output": "/geoai/D_buildings.png"},
        ],
        "subdistricts": [
            {"id": r["subdistrict_id"], "name": r["subdistrict_name"],
             "flood_likelihood": round(float(r["flood_likelihood_0_100"]), 1),
             "exposure": round(float(r["exposure_0_100"]), 1),
             "fpps": round(float(r["fpps_0_100"]), 1), "action": r["action_class"],
             "confidence": r["confidence_class"]}
            for r in scored.to_dict("records")
        ],
        "limitations": [
            "Nearest post-event same-orbit Sentinel-1 scene (2024-09-15) is ~4 days after the "
            "~Sep-11 flood peak, so extent is residual and under-represents the peak.",
            "U-Net labels are the MNDWI water index (weak supervision from a physical index, not "
            "hand annotation); metrics measure agreement with that index.",
            "Susceptibility is relative propensity, not flood depth. Non-operational; not an "
            "official warning.",
        ],
    }
    (web / "mae-sai-real.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    for name in ("scene_sar_post_vh.png", "A_sar_flood_probability.png", "scene_s2_rgb.png",
                 "B_water_mask.png", "scene_dem.png", "C_susceptibility.png", "D_buildings.png",
                 "annotated_decision_bridge.png", "annotated_models.png"):
        src = prev / name
        if src.exists():
            shutil.copy(src, web / name)
    return web / "mae-sai-real.json"


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
        ax.plot(col, row, "s", markersize=1.6,
                color="red" if f["properties"]["exposed_to_flood"] else "black")
    ax.set_xlim(0, shape[1]); ax.set_ylim(shape[0], 0); ax.axis("off")
    fig.tight_layout(pad=0)
    fig.savefig(path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def _component_summary(path, metrics, timings):
    rows = []
    for c in COMPONENTS:
        m = metrics.get(c.key, {})
        rows.append({"component": f"{c.letter}. {c.name}", "tier": c.tier,
                     "status": c.status, "ai_task": c.ai_task, "book_ref": c.book_ref,
                     "data_mode": m.get("data_mode", ""), "iou": m.get("iou", ""),
                     "f1_dice": m.get("f1_dice", ""), "auc": m.get("auc", ""),
                     "runtime_s": timings.get(c.key, "")})
    pd.DataFrame(rows).to_csv(path, index=False)


def _json_safe(o):
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
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
