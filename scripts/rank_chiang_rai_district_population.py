"""Pick the SE2-blind district by population alone (protocol v1b, open item OI-09).

Plan 6.1 defines the outcome-blind companion case SE2-blind as the amphoe-seat
tambons of the most populous Chiang Rai district, leaving out Mueang Chiang Rai
and Mae Sai, by WorldPop 2020 total. This script ranks the districts of Chiang
Rai province by that total and names the first one. It reads no flood layer and
computes no exposure, no FPPS, no A-E class and no ensemble.

Both inputs live outside Git, so their locations are arguments::

    python scripts/rank_chiang_rai_district_population.py \
        --worldpop <external data root>/open_context/worldpop_population/tha_ppp_2020.tif \
        --boundaries <external data root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "floodguard.se2_blind_district_ranking.v1"
DEFAULT_OUTPUT = ROOT / "outputs" / "planning_v1" / "se2_blind_district_ranking.json"
SOURCE_MANIFEST = ROOT / "outputs" / "open_context_data_file_manifest.csv"
PROVINCE_PCODE = "TH57"
EXCLUDED_DISTRICTS = {"TH5701": "Mueang Chiang Rai", "TH5709": "Mae Sai"}
BOUNDARY_LAYER = "tha_admin2"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode(payload: dict[str, Any]) -> bytes:
    """Serialise the receipt: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def select_blind_district(totals: dict[str, float], excluded: set[str]) -> dict[str, Any]:
    """Return the most populous district outside ``excluded`` and how clear the choice is.

    Args:
        totals: Residents by district code.
        excluded: District codes that may not be picked.

    Returns:
        The selected code, the runner-up and the margin between them as a share
        of the selected total. Ties break on the lower district code.

    Raises:
        ValueError: when fewer than two districts are eligible or a total is not a positive number.
    """

    eligible = {code: value for code, value in totals.items() if code not in excluded}
    if len(eligible) < 2:
        raise ValueError("at least two eligible districts are needed")
    if any(not math.isfinite(value) or value <= 0 for value in eligible.values()):
        raise ValueError("district totals must be positive numbers")
    ranked = sorted(eligible, key=lambda code: (-eligible[code], code))
    first, second = ranked[0], ranked[1]
    return {
        "selected": first,
        "runner_up": second,
        "margin_share_of_selected": (eligible[first] - eligible[second]) / eligible[first],
        "ranking": ranked,
    }


def recorded_source_hashes() -> dict[str, str]:
    """Read the recorded SHA-256 of the national source files from the committed manifest."""

    with SOURCE_MANIFEST.open(encoding="utf-8-sig", newline="") as stream:
        return {row["source_group"]: row["sha256"] for row in csv.DictReader(stream)}


def district_totals(worldpop: Path, boundaries: Path) -> tuple[dict[str, float], dict[str, str]]:
    """Sum WorldPop 2020 cells whose centre lies in each Chiang Rai district."""

    import numpy as np
    import pyogrio
    import rasterio
    from rasterio.mask import mask

    frame = pyogrio.read_dataframe(
        boundaries, layer=BOUNDARY_LAYER, columns=["adm2_pcode", "adm2_name", "adm1_pcode"],
        where=f"adm1_pcode = '{PROVINCE_PCODE}'",
    )
    if frame.empty or not frame["adm2_pcode"].is_unique:
        raise ValueError("Chiang Rai districts must be present with unique codes")
    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    with rasterio.open(worldpop) as source:
        if source.crs is None or source.crs.to_epsg() != 4326:
            raise ValueError("the population raster must be EPSG:4326")
        for code, name, geometry in zip(frame["adm2_pcode"], frame["adm2_name"], frame.geometry):
            data, _transform = mask(source, [geometry], crop=True, all_touched=False, filled=False)
            values = np.ma.masked_invalid(data[0]).astype("float64")
            values = np.ma.masked_less(values, 0)
            totals[str(code)] = float(values.sum())
            names[str(code)] = str(name)
    return totals, names


def build(worldpop: Path, boundaries: Path) -> dict[str, Any]:
    """Rank the districts and return the receipt."""

    recorded = recorded_source_hashes()
    worldpop_sha256 = sha256_file(worldpop)
    boundaries_sha256 = sha256_file(boundaries)
    if worldpop_sha256 != recorded["worldpop_population"] or boundaries_sha256 != recorded["hdx_cod_ab"]:
        raise ValueError("an input differs from outputs/open_context_data_file_manifest.csv")
    totals, names = district_totals(worldpop, boundaries)
    missing = set(EXCLUDED_DISTRICTS) - set(totals)
    if missing:
        raise ValueError(f"excluded districts are not in the boundary layer: {sorted(missing)}")
    choice = select_blind_district(totals, set(EXCLUDED_DISTRICTS))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    ranked_all = sorted(totals, key=lambda code: (-totals[code], code))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol_item": "planning_protocol_v1b open item OI-09, se2_frame.se2_blind_district (plan 6.1, case SE2-blind)",
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": "District population totals only. No flood layer is read. No exposure, FPPS, A-E class or ensemble.",
        "source_timestamp": "2020",
        "source_timestamps": {"population_year_represented": 2020, "district_boundaries_valid_on": "2022-01-22"},
        "confidence_class": "low",
        "confidence_basis": "Modelled 2020 residential population on 2022 boundaries; not a census count.",
        "rule": "The most populous district of Chiang Rai province by WorldPop 2020 total, leaving out Mueang Chiang Rai "
                "and Mae Sai. A cell counts for the district that holds its centre. Ties break on the lower district code.",
        "excluded_districts": dict(sorted(EXCLUDED_DISTRICTS.items())),
        "selected_district": {"adm2_pcode": choice["selected"], "adm2_name": names[choice["selected"]]},
        "runner_up_district": {"adm2_pcode": choice["runner_up"], "adm2_name": names[choice["runner_up"]]},
        "margin_share_of_selected": round(choice["margin_share_of_selected"], 6),
        "districts_ranked": [
            {"rank": rank, "adm2_pcode": code, "adm2_name": names[code], "residents_2020": round(totals[code], 1),
             "eligible": code not in EXCLUDED_DISTRICTS}
            for rank, code in enumerate(ranked_all, start=1)
        ],
        "input_hashes": {"worldpop_2020_sha256": worldpop_sha256, "district_boundaries_sha256": boundaries_sha256},
        "implementation": {"base_commit": commit.stdout.strip() or None, "builder_sha256": sha256_file(Path(__file__))},
        "assumptions": [
            "WorldPop 2020 is a modelled residential population, not a census count.",
            "A 100 m cell belongs to the district that holds its centre; boundary cells are not split.",
            "Districts are the 2022 COD-AB tha_admin2 polygons of province TH57.",
        ],
        "limitations": [
            "The rule picks a district. It does not say which tambons are the amphoe seat; the plan gives no rule for that.",
            "Flooded shares for the Chiang Rai tambons inside the 4009 analysis extent were already seen in exploratory "
            "work (v1a disclosure item EK-09). The selection rule uses none of them, but the case is blind by rule, not "
            "by ignorance.",
        ],
    }


def main() -> int:
    """Run the ranking and write the receipt."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worldpop", type=Path, required=True)
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    receipt = build(args.worldpop, args.boundaries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode(receipt))
    print(json.dumps({"selected": receipt["selected_district"], "runner_up": receipt["runner_up_district"],
                      "margin_share_of_selected": receipt["margin_share_of_selected"],
                      "receipt_sha256": sha256_file(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
