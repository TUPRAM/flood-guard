"""Diagnosis figure of plan task A1: the M2 decision rule on the 29 GEOID-Flood tiles, window by window.

README
======

Reads
    * The 58 Sentinel-1 GRD tiles (before and after) of event EMSR712-3 in the GEOID-Flood sample, outside
      Git under ``<external data root>/geoid_flood/sample/``. Every file of the sample area is first checked
      against the publisher's ``SHA256SUMS``.
    * The committed summary ``outputs/geoid_s1grd_sigma0_benchmark_summary_v1.json``, to compare with.

    The label and validity rasters are hashed with the rest and **not opened**: no reference value is read.

Computes
    The frozen M2 decision rule (``floodguard.geoid_radar_benchmark.predict_s1grd_sigma0``, unchanged) on
    each tile, and from its window records: the number of windows, the number the kernel accepted, the
    reasons, and the smallest, median and largest between-class variance fraction against the 0.72 gate.
    Plan row A1 states the figure as "GEOID 0/1,421 windows".

Does not show
    * Any agreement with the CEMS map of the sample: no window was accepted, so there is nothing to compare,
      and no label is read here.
    * That the exact Mae Sai M2 run would decline elsewhere: the tiles are sigma0, with no terrain
      flattening and none of the Mae Sai masks.
    * Anything about Thailand: the sample is one foreign event (northern Germany, winter 2023-24).

Writes
    ``outputs/a1_diagnosis/m2_windows_geoid.json``, the run receipt
    ``outputs/planning_v1/a1_diagnosis_m2_windows_geoid.json`` and its register entry. No raster is written.

Run
    ``python scripts/diagnostics/m2_windows_geoid.py --external-data <external data root>``
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import abstention_diagnosis as diagnosis  # noqa: E402
from floodguard import diagnosis_run  # noqa: E402

SOURCE_RELATIVE_PATH = Path("geoid_flood") / "sample"
SUMS_RELATIVE_PATH = Path("geoid_flood") / "metadata" / "SHA256SUMS"
COMMITTED_SUMMARY = Path("outputs") / "geoid_s1grd_sigma0_benchmark_summary_v1.json"
BENCHMARK_PROTOCOL = Path("docs") / "proposal_execution" / "automated_track" / "geoid_sar_benchmark_protocol_v1.json"
BENCHMARK_SCRIPT = Path("scripts") / "benchmark_geoid_flood_sar.py"
ADAPTER_MODULE = Path("src") / "floodguard" / "geoid_radar_benchmark.py"
ATTRIBUTION = ("Modified Copernicus Sentinel-1 data (2016-2026); GEOID-Flood sample, links-ads/geoid-flood, revision "
               "868407460bf3db492f50730a57585916baa71dc6")

SPEC = diagnosis_run.FigureSpec(
    figure_id="m2_windows_geoid",
    title="The M2 decision rule on the 29 GEOID-Flood tiles of EMSR712-3: windows against the 0.72 gate",
    script="scripts/diagnostics/m2_windows_geoid.py",
    plan_statement="GEOID 0/1,421 windows",
    computes="The frozen M2 decision rule on the 29 before-and-after tile pairs of the GEOID-Flood sample, with the counts and "
             "the between-class variance fractions of its windows. No label is read and no raster is written.",
    does_not_show=(
        "Any agreement with the CEMS map of the sample: no window was accepted, and no label is read here.",
        "That the exact Mae Sai M2 run would decline elsewhere: the tiles are sigma0 with no terrain flattening and no Mae Sai mask.",
        "Anything about Thailand: the sample is one foreign event (northern Germany, winter 2023-24).",
    ),
)


def _benchmark_module():
    """Load the committed benchmark runner, whose source check this script reuses unchanged."""

    spec = importlib.util.spec_from_file_location("benchmark_geoid_flood_sar", ROOT / BENCHMARK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        import numpy as np
        import rasterio

        from floodguard.geoid_radar_benchmark import predict_s1grd_sigma0

        assert external is not None
        benchmark = _benchmark_module()
        sums_path = external / SUMS_RELATIVE_PATH
        tiles, inventory = benchmark.discover_tiles(external / SOURCE_RELATIVE_PATH, sums_path)
        fractions: list[float] = []
        reasons: Counter[str] = Counter()
        qualified = 0
        valid_cells = 0
        post_times: set[str] = set()
        for roles in tiles.values():
            with rasterio.open(roles["s1grd_pre"][0]) as pre_file, rasterio.open(roles["s1grd_post"][0]) as post_file:
                pre = np.asarray(pre_file.read(masked=True).filled(np.nan), dtype="float32")
                post = np.asarray(post_file.read(masked=True).filled(np.nan), dtype="float32")
            _candidate, summary = predict_s1grd_sigma0(pre, post)
            post_times.add(str(roles["s1grd_post"][2]))
            qualified += int(summary["qualified_windows"])
            valid_cells += int(summary["source_valid_cells"])
            reasons.update(summary["reason_counts"])
            fractions.extend(float(window["qc"]["between_variance_fraction"]) for window in summary["window_receipts"]
                             if "between_variance_fraction" in window["qc"])
        gate = diagnosis.m2_gate()
        summary_fractions = diagnosis.summarise_fractions(fractions, gate=gate, marks=(0.70, 0.71))
        committed_path = root / COMMITTED_SUMMARY
        committed = json.loads(committed_path.read_text(encoding="utf-8"))["detector"]
        total = int(sum(reasons.values())) + qualified
        figures = {
            "tiles": len(tiles),
            "windows": total,
            "windows_the_kernel_accepted": qualified,
            "reason_counts": dict(sorted(reasons.items())),
            "between_variance_fraction": summary_fractions,
            "one_normal_population_in_theory": round(diagnosis.GAUSSIAN_BVF_THEORY, 6),
            "one_normal_population_clipped_as_the_kernel_clips": round(diagnosis.clipped_gaussian_bvf(), 6),
            "radiometrically_valid_cells": valid_cells,
            "same_as_the_committed_summary": {
                "windows": total == committed["total_windows"],
                "accepted": qualified == committed["qualified_windows"],
                "fraction_min": summary_fractions["between_variance_fraction_min"] == committed["between_variance_fraction_min"],
                "fraction_median": summary_fractions["between_variance_fraction_median"] == committed["between_variance_fraction_median"],
                "fraction_max": summary_fractions["between_variance_fraction_max"] == committed["between_variance_fraction_max"],
                "valid_cells": valid_cells == committed["source_valid_cells"],
            },
        }
        inventory_bytes = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("ascii")
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={
                "published_sha256sums": diagnosis_run.file_record(sums_path, root, external),
                "geoid_flood_sample_assets": {
                    "folder": f"{diagnosis_run.EXTERNAL_LABEL}/{(SOURCE_RELATIVE_PATH / 'sample' / 'geoid-flood' / 'EMSR712-3').as_posix()}",
                    "files_checked_against_the_published_sums": len(inventory),
                    "bytes": int(sum(entry["bytes"] for entry in inventory.values())),
                    "inventory_sha256": diagnosis_run.sha256_bytes(inventory_bytes),
                    "inventory_note": "SHA-256 of the list of every file with its own SHA-256 and size, as compact sorted JSON. "
                                      "58 of the files are the radar tiles this run opens; the 58 label and validity rasters "
                                      "are hashed and not opened.",
                },
                "committed_summary": diagnosis_run.file_record(committed_path, root, external),
                "benchmark_protocol": diagnosis_run.file_record(root / BENCHMARK_PROTOCOL, root, external),
                "decision_rule_adapter": diagnosis_run.file_record(root / ADAPTER_MODULE, root, external),
                "source_check": diagnosis_run.file_record(root / BENCHMARK_SCRIPT, root, external, function="discover_tiles"),
            },
            parameters={"aoi_id": benchmark.AOI, "kernel": {"window_pixels": 256, "stride_pixels": 128, "min_between_variance_fraction": gate},
                        "change": "0.4 x VV fall + 0.6 x VH fall, in dB, from linear sigma0", "marks": [0.70, 0.71]},
            source_timestamp=max(post_times),
            confidence_basis="Window counts of the team's own decision rule on a public benchmark sample. The rule accepted no "
                             "window, so no layer exists to compare, and no label was read.",
            assumptions=[
                "The tiles are the Sentinel-1 GRD layer of the GEOID-Flood sample, linear sigma0, 1,024 by 1,024 cells of 10 m. "
                "Each tile is cut into windows of 256 cells at a stride of 128 cells: 49 windows a tile.",
                "The decision rule is the frozen M2 kernel as the committed benchmark adapted it to sigma0. It was not changed.",
            ],
            limits=[
                "No window was accepted, so the run says nothing about agreement with the CEMS map of the sample.",
                "The CEMS map of this sample was drawn from the same Sentinel-1 pass as the after image. Any later figure against "
                "it measures agreement with a same-pass map, not an independent check.",
                "The before image is from 8 September 2023 and the after image from 3 January 2024: almost four months apart.",
                "One foreign event (northern Germany, winter 2023-24). It says nothing about Thai land cover or the Mae Sai pass.",
            ],
            plan_figure={
                "stated_in_the_plan": "GEOID 0/1,421 windows",
                "plan_value": {"accepted": 0, "windows": 1421},
                "measured": {"accepted": qualified, "windows": total},
                "reproduced": (qualified, total) == (0, 1421),
                "note": "Computed again from the tiles on disk, not copied from the committed summary; "
                        "same_as_the_committed_summary compares the two.",
            },
            attributions=[ATTRIBUTION, "Copernicus Emergency Management Service Rapid Mapping products, (c) European Union (the sample's labels, not read here)"],
            not_computed=["any comparison with the CEMS map", "FPPS", "A-E class", "flood candidate"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=True, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
