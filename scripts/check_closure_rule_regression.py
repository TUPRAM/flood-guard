"""Run the closure rule v1 regression (protocol v1b, open item OI-05; plan task E3).

The permissive level of ``floodguard.closure_rules`` must reproduce, exactly,
the closed-edge IDs of the AOI-01 finals build: 1,824 walking edges and 1,738
vehicle edges. This script measures that and writes a small receipt. It is a
closure build, which the blinding rule allows before v1b is in force: it
computes no access result, no FPPS, no A-E class and no ensemble.

The finals build and its flood candidate live outside Git, so their folders are
arguments. The committed finals database is the anchor: the external build
must hold the same closed-edge IDs as the database before it is used::

    python scripts/check_closure_rule_regression.py \
        --finals-dir <run>/finals --flood-candidate <run>/flood_candidate
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.closure_rules import (  # noqa: E402
    CLOSURE_RULE_VERSION,
    MIN_INTERSECTION_M,
    apply_closure_rule,
    edge_intersections,
)

SCHEMA_VERSION = "floodguard.closure_rule_regression.v1"
DEFAULT_OUTPUT = ROOT / "outputs" / "planning_v1" / "closure_rule_v1_regression.json"
FINALS_DATABASE = ROOT / "apps" / "web" / "public" / "evidence-library" / "databases" / "aoi-01_mae_sai_core-finals.json.gz"
EXPECTED = {"walking": 1824, "modelled_vehicle": 1738}
FLOOD_INPUT_ID = "legacy_2.25db_amplitude_change_candidate_aoi01"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def id_list_sha256(identifiers: list[str]) -> str:
    """Hash a list of edge IDs, one per line, in the given order."""

    return hashlib.sha256("\n".join(identifiers).encode("utf-8")).hexdigest()


def encode(payload: dict[str, Any]) -> bytes:
    """Serialise the receipt: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def compare_mode(context: dict[str, Any], extent: Any, finals_closed: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare the permissive level with the finals closed edges for one travel mode."""

    measured = edge_intersections(context["edges"], context["node_coordinates"], extent)
    result = apply_closure_rule("permissive", context["edges"], measured, flood_input_id=FLOOD_INPUT_ID)
    expected_ids = [row["edge_id"] for row in finals_closed]
    computed_ids = result["closed_edge_ids"]
    finals_lengths = {row["edge_id"]: row["intersection_length_m"] for row in finals_closed}
    shared = [row for row in measured if row["edge_id"] in finals_lengths]
    worst = max((abs(row["intersection_length_m"] - finals_lengths[row["edge_id"]]) for row in shared), default=0.0)
    return {
        "edges_in_context": len(context["edges"]),
        "finals_closed_edges": len(expected_ids),
        "computed_closed_edges": len(computed_ids),
        "closed_edge_ids_match_exactly": computed_ids == expected_ids,
        "only_in_finals": len(set(expected_ids) - set(computed_ids)),
        "only_in_computed": len(set(computed_ids) - set(expected_ids)),
        "finals_closed_edge_ids_sha256": id_list_sha256(expected_ids),
        "computed_closed_edge_ids_sha256": id_list_sha256(computed_ids),
        "largest_intersection_length_difference_m": worst,
        "closure_basis": result["closure_basis"],
    }


def build(finals_dir: Path, candidate_dir: Path) -> dict[str, Any]:
    """Run the regression for both travel modes and return the receipt."""

    from shapely.geometry import shape
    from shapely.ops import unary_union

    analysis_path = finals_dir / "analysis.json"
    receipt_path = finals_dir / "build_receipt.json"
    build_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if sha256_file(analysis_path) != build_receipt["files"]["analysis.json"]:
        raise ValueError("analysis.json differs from the finals build receipt")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    manifest_path = candidate_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    extent_path = candidate_dir / "candidate_extent.geojson"
    if sha256_file(extent_path) != manifest["products"]["candidate_extent"]["sha256"]:
        raise ValueError("the candidate extent differs from its manifest")
    if manifest["aoi_sha256"] != build_receipt["aoi_sha256"]:
        raise ValueError("the flood candidate belongs to a different AOI")
    extent = unary_union([shape(feature["geometry"]) for feature in json.loads(extent_path.read_bytes())["features"]])
    with gzip.open(FINALS_DATABASE) as stream:
        database = json.load(stream)

    modes: dict[str, Any] = {}
    input_hashes = {
        "finals_build_receipt_sha256": sha256_file(receipt_path),
        "finals_analysis_sha256": build_receipt["files"]["analysis.json"],
        "flood_candidate_manifest_sha256": sha256_file(manifest_path),
        "candidate_extent_sha256": manifest["products"]["candidate_extent"]["sha256"],
        "committed_finals_database_sha256": sha256_file(FINALS_DATABASE),
    }
    for mode, expected_count in EXPECTED.items():
        scenario = analysis["flood_scenarios"][mode]
        if scenario["candidate_provenance"]["products"] != manifest["products"]:
            raise ValueError("the finals build used a different flood candidate")
        relative = f"contexts/{mode}/context_inputs.json"
        context_path = finals_dir / relative
        if sha256_file(context_path) != build_receipt["files"][relative]:
            raise ValueError(f"the {mode} context differs from the finals build receipt")
        context = json.loads(context_path.read_text(encoding="utf-8"))
        if context["canonical_sha256"] != scenario["context_sha256"]:
            raise ValueError(f"the {mode} flood scenario was computed on a different context")
        committed = [row["edge_id"] for row in database["analysis"]["flood_scenarios"][mode]["closed_edges"]]
        if committed != [row["edge_id"] for row in scenario["closed_edges"]]:
            raise ValueError(f"the external finals build and the committed database disagree for {mode}")
        row = compare_mode(context, extent, scenario["closed_edges"])
        row["expected_closed_edges_in_protocol"] = expected_count
        row["finals_count_equals_protocol"] = row["finals_closed_edges"] == expected_count
        row["context_canonical_sha256"] = context["canonical_sha256"]
        modes[mode] = row
        input_hashes[f"{mode}_context_file_sha256"] = build_receipt["files"][relative]

    match = all(row["closed_edge_ids_match_exactly"] and row["finals_count_equals_protocol"] for row in modes.values())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "protocol_item": "planning_protocol_v1b open item OI-05, closure_rule_v1.regression (plan 5 item 2, task E3)",
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": "Closed-edge sets only. No access result, no FPPS, no A-E class and no ensemble.",
        "source_timestamp": manifest["source_timestamp"],
        "source_timestamps": {
            "flood_candidate_post_event_acquisition": manifest["source_timestamp"],
            "finals_build_generated_at": build_receipt["generated_at"],
        },
        "confidence_class": "low",
        "confidence_basis": "The flood input is the legacy uncalibrated 2.25 dB candidate with no demonstrated skill. "
                            "The regression tests the code, not the flood map.",
        "closure_rule_version": CLOSURE_RULE_VERSION,
        "level": "permissive",
        "threshold_m": MIN_INTERSECTION_M,
        "rule": "The permissive level on the AOI-01 finals context reproduces the finals closed-edge IDs exactly.",
        "walking_closed_edges": modes["walking"]["computed_closed_edges"],
        "vehicle_closed_edges": modes["modelled_vehicle"]["computed_closed_edges"],
        "closed_edge_ids_match_exactly": match,
        "modes": modes,
        "input_hashes": input_hashes,
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "builder_sha256": sha256_file(Path(__file__)),
            "closure_rules_module_sha256": sha256_file(ROOT / "src" / "floodguard" / "closure_rules.py"),
            "finals_closure_module_sha256": sha256_file(ROOT / "src" / "floodguard" / "evidence_flood_scenario.py"),
        },
        "assumptions": [
            "Each edge is the straight segment between its two nodes in EPSG:32647; an edge is intersected when more "
            "than 1e-6 m of it lies inside the extent (drafter reading DR-B02).",
            "A flood intersection is a closure assumption. It does not show that a road was closed.",
            "The external finals build is accepted only because its closed-edge IDs equal those in the committed "
            "finals database.",
        ],
        "limitations": [
            "Only the permissive level is tested here. The strict and central levels have no reference to reproduce.",
            "The AOI-01 context and the 2.25 dB candidate are the legacy lane; they are not a case input of the protocol.",
        ],
    }


def main() -> int:
    """Run the regression and write the receipt. A mismatch is recorded as it is."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--finals-dir", type=Path, required=True)
    parser.add_argument("--flood-candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    receipt = build(args.finals_dir, args.flood_candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode(receipt))
    print(json.dumps({
        "walking_closed_edges": receipt["walking_closed_edges"],
        "vehicle_closed_edges": receipt["vehicle_closed_edges"],
        "closed_edge_ids_match_exactly": receipt["closed_edge_ids_match_exactly"],
        "receipt_sha256": sha256_file(args.output),
    }))
    return 0 if receipt["closed_edge_ids_match_exactly"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
