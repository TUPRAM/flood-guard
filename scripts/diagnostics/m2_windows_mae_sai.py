"""Diagnosis figure of plan task A1: how the 81 windows of the retired M2 run at Mae Sai met the 0.72 gate.

README
======

Reads
    * The receipt of the retired M2 run on the Mae Sai pilot grid, outside Git:
      ``<external data root>/proposal_execution/mae_sai_2024_gamma0_otsu_v1_20260923r3/candidate_receipt.json``.
      It is the team's own file. Its SHA-256 must be the one the committed summary names.
    * The committed summary ``outputs/sar_m2_abstention_diagnostic_v1.json``, to compare with.

    It reads no image, no flood map and no label.

Computes
    From the window records of the receipt: the number of windows, the number the kernel accepted, the
    reason each was declined, and the smallest, median and largest between-class variance fraction against
    the 0.72 gate. It also counts the windows whose only failed test was that gate.

Does not show
    * Whether water was present in any window. A declined window has no answer; it is not a dry window.
    * That the method would decline on another grid or another radiometry. The run used terrain-flattened
      gamma0 on a 12.8 km pilot grid that holds about two fifths of AOI-01.
    * Any agreement with a flood map: none is read.

Writes
    ``outputs/a1_diagnosis/m2_windows_mae_sai.json``, the run receipt
    ``outputs/planning_v1/a1_diagnosis_m2_windows_mae_sai.json`` and its register entry.

Run
    ``python scripts/diagnostics/m2_windows_mae_sai.py --external-data <external data root>``
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import abstention_diagnosis as diagnosis  # noqa: E402
from floodguard import diagnosis_run  # noqa: E402
from floodguard.label_factory.sar_abstention_diagnostic import summarize_windows  # noqa: E402

M2_RECEIPT_RELATIVE_PATH = Path("proposal_execution") / "mae_sai_2024_gamma0_otsu_v1_20260923r3" / "candidate_receipt.json"
COMMITTED_SUMMARY = Path("outputs") / "sar_m2_abstention_diagnostic_v1.json"

SPEC = diagnosis_run.FigureSpec(
    figure_id="m2_windows_mae_sai",
    title="The 81 windows of the retired M2 run at Mae Sai against the 0.72 gate",
    script="scripts/diagnostics/m2_windows_mae_sai.py",
    plan_statement="Abstention diagnosis (protocol v1a, EK-07: all 81 of 81 windows abstained with between-class variance "
                   "fractions of 0.598-0.651 against the 0.72 gate)",
    computes="Counts and between-class variance fractions of the windows of the retired M2 run at Mae Sai, read from the "
             "run's own receipt. No image and no flood map is read.",
    does_not_show=(
        "Whether water was present in any window: a declined window has no answer, it is not a dry window.",
        "That the method would decline on another grid or with another radiometry.",
        "Any agreement with a flood map: none is read.",
    ),
)


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        assert external is not None
        receipt_path = external / M2_RECEIPT_RELATIVE_PATH
        committed_path = root / COMMITTED_SUMMARY
        committed = json.loads(committed_path.read_text(encoding="utf-8"))
        record = diagnosis_run.file_record(receipt_path, root, external)
        if record["sha256"] != committed["source_receipt_sha256"]:
            raise diagnosis_run.DiagnosisRunError("the M2 receipt on disk is not the one the committed summary names")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        windows = summarize_windows(receipt)
        gate = float(receipt["configuration"]["min_between_variance_fraction"])
        fractions = diagnosis.summarise_fractions(
            (window["qc"]["between_variance_fraction"] for window in receipt["window_receipts"]), gate=gate, marks=(0.65, 0.70))
        grid = receipt["grid"]
        figures = {
            "windows": windows["total_windows"],
            "windows_the_kernel_accepted": windows["qualified_windows"],
            "windows_declined": windows["total_windows"] - windows["qualified_windows"],
            "reason_counts": windows["reason_counts"],
            "windows_whose_only_failed_test_was_the_gate": windows["sole_variance_veto_windows"],
            "between_variance_fraction": fractions,
            "one_normal_population_in_theory": round(diagnosis.GAUSSIAN_BVF_THEORY, 6),
            "one_normal_population_clipped_as_the_kernel_clips": round(diagnosis.clipped_gaussian_bvf(), 6),
            "valid_samples_per_window": {"min": windows["valid_samples_min"], "max": windows["valid_samples_max"]},
            "classified_cells": receipt["counts"]["candidate_cells"] + receipt["counts"]["classified_non_candidate_cells"],
            "grid_cells": receipt["counts"]["total_cells"],
            "same_as_the_committed_summary": windows == committed["window_summary"],
        }
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={"m2_run_receipt": {**record, "self_hash_verified_by": "outputs/sar_m2_abstention_diagnostic_v1.json (source_receipt_self_hash_verified)"},
                    "committed_summary": diagnosis_run.file_record(committed_path, root, external)},
            parameters={
                "kernel_configuration": receipt["configuration"],
                "grid": {"crs": grid["crs"], "width": grid["width"], "height": grid["height"], "transform": grid["transform"]},
                "radiometry": receipt["radiometry"],
                "speckle_filter_applied": receipt["speckle_filter_applied"],
                "marks": [0.65, 0.70],
            },
            source_timestamp=str(receipt["post_observed_at_utc"]),
            confidence_basis="Counts read from the team's own run receipt. The run declined every window, so there is no flood "
                             "layer to check, and nothing here was checked against a flood map.",
            assumptions=[
                "The window records of the receipt are the windows the retired M2 run evaluated: 256 by 256 cells of 10 m at a "
                "stride of 128 cells on a 1,280 by 1,280 pilot grid.",
                "The image pair is 3 and 15 September 2024, 23:16 UTC, relative orbit 135; the second image is 16 September "
                "06:16 in Thailand.",
            ],
            limits=[
                "A declined window has no answer. The figure does not say whether the ground was wet or dry.",
                "The pilot grid holds about two fifths of AOI-01; see the pilot-grid figure.",
                "M2 is retired as a failed first version (plan guardrail G24). Its gate is not lowered here.",
            ],
            plan_figure={
                "stated_in_the_plan": "all 81 of 81 windows abstained with between-class variance fractions of 0.598-0.651 "
                                      "against the 0.72 gate (protocol v1a, EK-07)",
                "plan_value": {"windows": 81, "declined": 81, "fraction_min": 0.598, "fraction_max": 0.651},
                "measured": {"windows": figures["windows"], "declined": figures["windows_declined"],
                             "fraction_min": round(fractions["between_variance_fraction_min"], 3),
                             "fraction_max": round(fractions["between_variance_fraction_max"], 3)},
                "reproduced": (figures["windows"], figures["windows_declined"], round(fractions["between_variance_fraction_min"], 3),
                               round(fractions["between_variance_fraction_max"], 3)) == (81, 81, 0.598, 0.651),
                "note": "Plan row A1 does not list this figure by itself; disclosure item EK-07 of protocol v1a does, and the "
                        "figure of one normal population is read against it.",
            },
            development_reads=diagnosis_run.DEVELOPMENT_READS,
            not_computed=["any comparison with a flood map", "FPPS", "A-E class", "flood candidate"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=True, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
