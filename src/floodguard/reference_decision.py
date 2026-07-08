"""Compare public reference candidates for Mae Sai."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_mae_sai_reference_decision(
    sentinel_asia_inspection: pd.DataFrame,
    cems_products: pd.DataFrame,
) -> str:
    """Build a Markdown decision note for the current Mae Sai reference candidate."""

    sa_row = sentinel_asia_inspection.iloc[0] if not sentinel_asia_inspection.empty else {}
    cems_mae_sai_count = 0
    if not cems_products.empty and "mae_sai_reference_relevance" in cems_products.columns:
        cems_mae_sai_count = int(
            (cems_products["mae_sai_reference_relevance"] == "potential_match").sum()
        )
    selected = str(sa_row.get("source_name", "Sentinel Asia public shapefile candidate"))
    return "\n".join(
        [
            "# Mae Sai Public Reference Candidate Decision",
            "",
            "Status: provisional public geometry candidate selected; real validation remains blocked.",
            "",
            "## Selected Candidate",
            "",
            f"- Candidate: {selected}",
            f"- Source URL: {sa_row.get('source_url', 'unavailable')}",
            f"- SHA-256: {sa_row.get('sha256', 'unavailable')}",
            f"- Geometry type: {sa_row.get('geometry_type', 'unavailable')}",
            f"- CRS: {sa_row.get('crs', 'unavailable')}",
            (
                "- Bbox: "
                f"{sa_row.get('bbox_lon_min', 'unavailable')}, "
                f"{sa_row.get('bbox_lat_min', 'unavailable')}, "
                f"{sa_row.get('bbox_lon_max', 'unavailable')}, "
                f"{sa_row.get('bbox_lat_max', 'unavailable')}"
            ),
            f"- Mae Sai point inside bbox: {sa_row.get('mae_sai_point_in_bbox', 'unavailable')}",
            "",
            "## Comparison",
            "",
            "- Sentinel Asia: first practical public geometry candidate because the downloaded external ZIP contains WGS84 polygon shapefile members and the Mae Sai point falls inside the shapefile bbox.",
            f"- CEMS EMSR754/EMSR756: resolved through public API, but current product rows with Mae Sai relevance = {cems_mae_sai_count}. The inspected activations are not better Mae Sai candidates.",
            "- UNOSAT public report: useful citation and area/population sanity check, but no redistributable GIS geometry has been confirmed.",
            "- NASA flood products: useful coarse temporal/context evidence, but too coarse for subdistrict or road-level validation.",
            "",
            "## Gate Decision",
            "",
            "Use the Sentinel Asia MBRSC shapefile as the first public reference-candidate lane, not as a cleared validation mask and not as ML labels.",
            "",
            "Processing remains blocked until product-level terms, redistribution/reference-only status, geometry quality, local-file record, and reference-mask status are explicitly cleared.",
        ]
    )


def write_mae_sai_reference_decision(
    sentinel_asia_inspection_path: str | Path,
    cems_products_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write the Mae Sai public reference decision note."""

    inspection = pd.read_csv(sentinel_asia_inspection_path)
    cems = pd.read_csv(cems_products_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_mae_sai_reference_decision(inspection, cems), encoding="utf-8")
    return target
