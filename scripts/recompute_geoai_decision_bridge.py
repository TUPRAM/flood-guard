"""Recompute the GeoAI decision bridge from committed per-tambon AI aggregates.

Why this exists
---------------
Components A (SAR flood extent), C (susceptibility) and D (building extraction)
were not changed by the T0.3 work, so their committed per-tambon aggregates in
``outputs/geoai/geoai_subdistrict_priority.csv`` remain valid. What changed is
everything *downstream* of them: the flood-likelihood scale (absolute anchors
instead of division by the district maximum), the exposure basis (WorldPop
population density instead of OpenStreetMap building counts), and the source of
the three non-AI FPPS components (real decision-layer context instead of proxies
synthesised from the AI signals).

This script replays only that downstream arithmetic. It does **not** re-run the
rasters, retrain any model, or contact the network -- so it cannot and does not
produce new Component B metrics. Re-running the full pipeline
(``python -m geoai_runner.realpipeline --all-methods``) is still required for
those, and is the only thing that produces a held-out Component B score.

Usage:  python scripts/recompute_geoai_decision_bridge.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
for extra in (REPO_ROOT / "src", REPO_ROOT / "services" / "geoai-runner"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from floodguard.scoring import score_subdistricts  # noqa: E402

from geoai_runner.realpipeline import aggregate, narrative as nr  # noqa: E402

GEOAI_DIR = REPO_ROOT / "outputs" / "geoai"
PRIORITY_CSV = GEOAI_DIR / "geoai_subdistrict_priority.csv"
# The script rewrites its own input, so it must be idempotent: reading a
# previously-recomputed file has to yield the same result as reading the
# original. `_flooded_share` reads whichever column form is present, and a
# missing flood column is a hard error rather than a silent zero -- a silent
# zero would quietly collapse every likelihood to its prior term.
FLOOD_COLUMNS = ("ai_flood_share", "ai_flood_pct")

# Acquisition provenance from the committed Component A run.
ACQUISITION_DATE = "2024-09-15"
PEAK_OFFSET_DAYS = 4

PROVENANCE = (
    "Recomputed from committed per-tambon Component A/C/D aggregates under "
    "flood anchor fpps_flood_anchor_v1 and exposure anchor fpps_exposure_anchor_v1, "
    "joined to real decision-layer context. Rasters were NOT re-run; Component B "
    "held-out metrics require a full pipeline run."
)


def main() -> None:
    if not PRIORITY_CSV.exists():
        raise SystemExit(f"missing {PRIORITY_CSV}; run the full pipeline first.")
    previous = pd.read_csv(PRIORITY_CSV)

    context = aggregate.load_subdistrict_context(
        REPO_ROOT / "outputs" / "mae_sai_subdistrict_flood_inputs.csv",
        REPO_ROOT / "outputs" / "mae_sai_admin_context.geojson",
    )

    rows: list[dict] = []
    for record in previous.to_dict("records"):
        sid = aggregate.normalise_subdistrict_id(record["subdistrict_id"])
        flooded_share = _flooded_share(record)
        susceptibility = float(record.get("ai_susceptibility_mean", 0.0))
        buildings = _building_count(record)

        likelihood, likelihood_terms = aggregate.fuse_flood_likelihood(
            flooded_share, susceptibility
        )
        population = context.population.get(sid)
        exposure, exposure_terms = aggregate.compute_exposure(
            population, context.area_sq_km.get(sid)
        )
        completeness = aggregate.osm_completeness(buildings, population)
        confidence, agreement_gap = aggregate.signal_agreement(
            likelihood_terms["observed_term"], likelihood_terms["prior_term"]
        )
        if exposure is None:
            confidence = "low"
        rows.append(
            {
                "subdistrict_id": sid,
                "subdistrict_name": record["subdistrict_name"],
                "flood_likelihood_0_100": likelihood,
                "exposure_0_100": exposure,
                "confidence_class": confidence,
                "signal_agreement_gap": agreement_gap,
                "ai_flood_share": round(flooded_share, 5),
                "ai_susceptibility_mean": round(susceptibility, 4),
                "ai_exposed_building_count": int(record.get("ai_exposed_building_count", 0) or 0),
                "flood_anchor_version": aggregate.DEFAULT_FLOOD_ANCHOR.version,
                "exposure_anchor_version": aggregate.DEFAULT_EXPOSURE_ANCHOR.version,
                **{f"flood_{k}": v for k, v in likelihood_terms.items()},
                **exposure_terms,
                **completeness,
                "source_name": (
                    "Sentinel-1 RTC + Copernicus DEM + DOPA/DWR/OSM/WorldPop (all real)"
                ),
                "source_timestamp": record.get("source_timestamp", ""),
                "assumptions": PROVENANCE,
            }
        )

    ai_inputs = pd.DataFrame(rows)
    table = aggregate.build_fpps_input_table(ai_inputs, context=context)
    scored = score_subdistricts(table).sort_values("fpps_0_100", ascending=False)

    columns = [
        "subdistrict_id", "subdistrict_name", "flood_likelihood_0_100", "exposure_0_100",
        "access_gap_0_100", "road_criticality_0_100", "vulnerability_context_0_100",
        "fpps_0_100", "action_class", "top_reason", "confidence_class",
        "signal_agreement_gap", "context_source",
        "ai_flood_share", "ai_susceptibility_mean", "ai_exposed_building_count",
        "population", "density_per_km2", "osm_building_count", "osm_completeness_ratio",
        "osm_completeness_flag", "flood_anchor_version", "exposure_anchor_version",
        "source_name", "source_timestamp", "assumptions",
    ]
    scored_out = scored.reindex(columns=[c for c in columns if c in scored.columns])
    scored_out.to_csv(PRIORITY_CSV, index=False)

    thai = _thai_names()
    result = nr.generate_narratives(
        [
            nr.narrative_inputs_from_row(
                row,
                acquisition_date=ACQUISITION_DATE,
                peak_offset_days=PEAK_OFFSET_DAYS,
                tambon_name_th=thai.get(
                    aggregate.normalise_subdistrict_id(row["subdistrict_id"]), ""
                ),
            )
            for row in scored_out.to_dict("records")
        ],
        GEOAI_DIR / "narratives.json",
    )

    bundle_path = _refresh_web_bundle(scored_out, result.narratives)

    print(f"wrote {PRIORITY_CSV}")
    print(f"wrote {GEOAI_DIR / 'narratives.json'} ({result.metrics['narrative_count']} tambons)")
    if bundle_path is not None:
        print(f"wrote {bundle_path}")
    print()
    print(
        scored_out[
            ["subdistrict_name", "flood_likelihood_0_100", "exposure_0_100",
             "access_gap_0_100", "fpps_0_100", "action_class", "confidence_class"]
        ].to_string(index=False)
    )


def _refresh_web_bundle(scored, narratives: dict) -> Path | None:
    """Update the role-surface bundle so /command and /studio stop showing stale numbers.

    Only the fields this recomputation actually changes are touched: the
    sub-district table, Component B's withdrawn metric, Component D's coverage
    caveat, and the limitations list. Everything else (Component A/C metrics,
    source identifiers, preview image paths) is left exactly as the last full
    pipeline run wrote it, because this script did not recompute it.
    """

    bundle_path = REPO_ROOT / "apps" / "web" / "public" / "geoai" / "mae-sai-real.json"
    if not bundle_path.exists():
        return None
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    bundle["subdistricts"] = [
        {
            "id": row["subdistrict_id"],
            "name": row["subdistrict_name"],
            "flood_likelihood": round(float(row["flood_likelihood_0_100"]), 1),
            "exposure": round(float(row["exposure_0_100"]), 1),
            "fpps": round(float(row["fpps_0_100"]), 1),
            "action": row["action_class"],
            "confidence": row["confidence_class"],
            "population": (
                round(float(row["population"]), 0) if pd.notna(row.get("population")) else None
            ),
            "context_source": row.get("context_source"),
            "narrative_en": narratives.get(row["subdistrict_name"], {}).get("en"),
            "narrative_th": narratives.get(row["subdistrict_name"], {}).get("th"),
        }
        for row in scored.to_dict("records")
    ]

    headline = bundle.setdefault("headline", {})
    # Withdrawn: the previous value was produced under train/test leakage.
    headline["unet_iou"] = None
    headline["unet_f1"] = None
    headline["unet_metric_role"] = "test"

    bundle["scale_anchors"] = {
        "flood_likelihood": aggregate.DEFAULT_FLOOD_ANCHOR.version,
        "exposure": aggregate.DEFAULT_EXPOSURE_ANCHOR.version,
    }

    for component in bundle.get("components", []):
        if component.get("letter") == "B":
            component["metric"] = "held-out metric pending re-run (previous value withdrawn)"
            component["detail"] = (
                "Sentinel-2 L2A - ImageNet-pretrained ResNet - evaluated on spatially "
                "disjoint blocks with a 1600 m buffer; the earlier score was produced "
                "under train/test leakage and is withdrawn."
            )
        elif component.get("letter") == "D":
            component["detail"] = (
                "OpenStreetMap building centroids vs SAR flood extent. OSM coverage here "
                "is 0.9-5.1% of the population-implied expectation, so counts are a "
                "diagnostic and do not enter the exposure score."
            )

    bundle["limitations"] = [
        "Nearest post-event same-orbit Sentinel-1 scene (2024-09-15) is ~4 days after the "
        "~Sep-11 flood peak, so extent is residual and under-represents the peak. This is "
        "why most sub-districts carry low confidence and action class E.",
        "Component B's previous IoU was produced under train/test leakage and is withdrawn; "
        "replacement metrics require a full pipeline re-run on held-out spatial blocks.",
        "Susceptibility is relative propensity, not flood depth. Non-operational; not an "
        "official warning.",
        "flood_likelihood and exposure use fixed versioned anchors, so values are absolute "
        "rather than ranked within the district.",
        "exposure is WorldPop 2020 population density; OpenStreetMap building coverage in "
        "Mae Sai is 0.9-5.1% of the population-implied expectation and is diagnostic only.",
        "The spatial holdout is runner-local. It is NOT a sealed multi-event partition and "
        "does not clear the qualified-label gates.",
    ]
    bundle_path.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return bundle_path


def _flooded_share(record: dict) -> float:
    """Read the unit's flooded share as a fraction, from either column form.

    ``ai_flood_share`` is a fraction (written by this script and by the current
    aggregate); ``ai_flood_pct`` is the same quantity in percent (written by the
    original pipeline run). Refusing to default keeps a schema change from
    silently zeroing the observed term.
    """

    if "ai_flood_share" in record and pd.notna(record["ai_flood_share"]):
        return float(record["ai_flood_share"])
    if "ai_flood_pct" in record and pd.notna(record["ai_flood_pct"]):
        return float(record["ai_flood_pct"]) / 100.0
    raise SystemExit(
        f"row {record.get('subdistrict_id')!r} has none of {FLOOD_COLUMNS}; refusing "
        "to treat a missing flood observation as zero."
    )


def _building_count(record: dict) -> int:
    """Read the OSM building count from either column form (see _flooded_share)."""

    for column in ("osm_building_count", "ai_building_count"):
        if column in record and pd.notna(record[column]):
            return int(record[column])
    return 0


def _thai_names() -> dict[str, str]:
    path = GEOAI_DIR / "subdistricts.geojson"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        aggregate.normalise_subdistrict_id(f["properties"].get("subdistrict_id")):
            f["properties"].get("subdistrict_name_th", "")
        for f in payload.get("features", [])
    }


if __name__ == "__main__":
    main()
