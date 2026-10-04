"""Diagnosis figure of plan task A1: how much of the 2024 season envelope inside AOI-01 the M2 pilot grid leaves out.

README
======

Reads
    * The accumulated layer of UNOSAT/GISTDA product 4009 (the 2024 season envelope), from the archive outside
      Git, through the rights registry and ``floodguard.flood_inputs.load_se1``. CC BY-SA 4.0; credit: UNOSAT
      and GISTDA, FL20240912THA, UNOSAT product 4009.
    * AOI-01, ``resources/aoi/aoi-01_mae_sai_core.geojson``.
    * The grid of the retired M2 run, from the run's own receipt outside Git
      (``<external data root>/proposal_execution/mae_sai_2024_gamma0_otsu_v1_20260923r3/candidate_receipt.json``).

    It reads no radar image.

Computes
    The area of the envelope inside AOI-01, the part of it inside the 12.8 km pilot grid of the M2 run and
    the share outside, and the share of AOI-01 itself that the pilot grid holds. Areas are measured in
    EPSG:32647. Plan row A1 states the figure as "pilot grid misses 80% of the 4009 envelope inside AOI-01".
    Label of the figure: vs a season envelope, not an event map.

Does not show
    * How much of the September 2024 flood the pilot grid left out. The envelope holds every area mapped
      as water at some time from August to October 2024, with no date per patch.
    * That the M2 run would have found water on a larger grid. It declined every window it had.
    * Any radar result: no image is read.

Writes
    ``outputs/a1_diagnosis/pilot_grid_vs_envelope.json``, the run receipt
    ``outputs/planning_v1/a1_diagnosis_pilot_grid_vs_envelope.json`` and its register entry. No layer is written.

Run
    ``python scripts/diagnostics/pilot_grid_vs_envelope.py --external-data <external data root>``
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
from floodguard import diagnosis_layers, diagnosis_run, flood_inputs  # noqa: E402

M2_RECEIPT_RELATIVE_PATH = Path("proposal_execution") / "mae_sai_2024_gamma0_otsu_v1_20260923r3" / "candidate_receipt.json"
COMMITTED_SUMMARY = Path("outputs") / "sar_m2_abstention_diagnostic_v1.json"

SPEC = diagnosis_run.FigureSpec(
    figure_id="pilot_grid_vs_envelope",
    title="Share of the 2024 season envelope inside AOI-01 that the M2 pilot grid leaves out",
    script="scripts/diagnostics/pilot_grid_vs_envelope.py",
    plan_statement="pilot grid misses 80% of the 4009 envelope inside AOI-01",
    computes="The area of the product 4009 accumulated layer inside AOI-01, and the share of it outside the pilot grid of the "
             "retired M2 run. Areas only; no radar image is read and no layer is written.",
    does_not_show=(
        "How much of the September 2024 flood the pilot grid left out: the envelope holds water of the whole season, with no date per patch.",
        "That the M2 run would have found water on a larger grid: it declined every window it had.",
        "Any radar result: no image is read.",
    ),
    label=diagnosis_run.ENVELOPE_LABEL,
)


def pilot_grid(receipt: dict) -> tuple[object, dict]:
    """Return the pilot grid of the M2 run as a box in EPSG:32647, with its record.

    Raises:
        diagnosis_run.DiagnosisRunError: when the grid is not north-up in EPSG:32647.
    """

    from shapely.geometry import box

    grid = receipt["grid"]
    cell, skew_x, left, skew_y, negative_cell, top = grid["transform"]
    if grid["crs"] != flood_inputs.ANALYSIS_CRS or skew_x != 0 or skew_y != 0 or cell != -negative_cell:
        raise diagnosis_run.DiagnosisRunError("the pilot grid is not a north-up grid in EPSG:32647")
    west, north = float(left), float(top)
    east, south = west + grid["width"] * cell, north - grid["height"] * cell
    return box(west, south, east, north), {"crs": grid["crs"], "cell_m": cell, "width": grid["width"], "height": grid["height"],
                                           "bounds": [west, south, east, north], "area_km2": round((east - west) * (north - south) / 1e6, 6)}


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        import shapely

        assert external is not None
        receipt_path = external / M2_RECEIPT_RELATIVE_PATH
        record = diagnosis_run.file_record(receipt_path, root, external)
        committed = json.loads((root / COMMITTED_SUMMARY).read_text(encoding="utf-8"))
        if record["sha256"] != committed["source_receipt_sha256"]:
            raise diagnosis_run.DiagnosisRunError("the M2 receipt on disk is not the one the committed summary names")
        pilot, pilot_record = pilot_grid(json.loads(receipt_path.read_text(encoding="utf-8")))
        envelope = diagnosis_layers.load_envelope(root, external)
        aoi = envelope.frame.geometry
        envelope_area = float(envelope.geometry.area)
        inside = float(shapely.intersection(envelope.geometry, pilot).area)
        aoi_inside = float(shapely.intersection(aoi, pilot).area)
        envelope_shares = diagnosis.share_outside(envelope_area, inside)
        aoi_shares = diagnosis.share_outside(float(aoi.area), aoi_inside)
        figures = {
            "envelope_inside_aoi_01_km2": round(envelope_area / 1e6, 3),
            "envelope_inside_aoi_01_and_inside_the_pilot_grid_km2": round(inside / 1e6, 3),
            "envelope_inside_aoi_01_and_outside_the_pilot_grid_km2": round((envelope_area - inside) / 1e6, 3),
            "share_of_the_envelope_in_aoi_01_outside_the_pilot_grid": envelope_shares["share_outside"],
            "share_of_the_envelope_in_aoi_01_inside_the_pilot_grid": envelope_shares["share_inside"],
            "aoi_01_km2": round(float(aoi.area) / 1e6, 3),
            "share_of_aoi_01_inside_the_pilot_grid": aoi_shares["share_inside"],
            "pilot_grid": pilot_record,
            "area_measure": "EPSG:32647, as every area of the planning runs",
        }
        percent = round(envelope_shares["share_outside"] * 100)
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={**dict(envelope.inputs), "m2_run_receipt": {**record, "read_for": "the grid of the run (crs, transform, width, height)"},
                    "committed_m2_summary": diagnosis_run.file_record(root / COMMITTED_SUMMARY, root, external,
                                                                      read_for="the SHA-256 of the M2 receipt")},
            parameters={"envelope_level": flood_inputs.AS_PROVIDED, "frame": diagnosis_layers.AOI_01_LABEL,
                        "analysis_crs": flood_inputs.ANALYSIS_CRS, "footprint_layer_read": False},
            source_timestamp=envelope.source_timestamp,
            confidence_basis="Areas of an unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; "
                             "Field_Validation=0), used as provided, against the grid of the team's own run. Nothing here was "
                             "checked against an independent source.",
            assumptions=[
                diagnosis_layers.STANDARD_LIMIT,
                "The pilot grid is the grid the receipt of the retired M2 run states: 1,280 by 1,280 cells of 10 m in EPSG:32647.",
                "Every vertex of the layer is projected to EPSG:32647 as it is and areas are measured there.",
                "AOI-01 is a rectangle that reaches across the border; the product maps Chiang Rai Province, so the envelope "
                "lies on the Thai side only.",
            ],
            limits=[
                "The share is a share of a season envelope. It is not the share of the September 2024 flood that the grid left out.",
                "The figure is about where the M2 run looked. The run declined every window, so a larger grid alone would not "
                "have given an answer.",
                "The envelope is not an observation of any day and not a reference.",
            ],
            plan_figure={
                "stated_in_the_plan": "pilot grid misses 80% of the 4009 envelope inside AOI-01",
                "plan_value": 0.80,
                "measured": envelope_shares["share_outside"],
                "reproduced": percent == 80,
                "note": "Compared as a whole percentage. Protocol v1a (EK-07) says 'about 80%'.",
            },
            licence=envelope.licence(raster_cell_m=None, then="areas were then measured against the pilot grid of the M2 run"),
            rights=dict(envelope.rights),
            attributions=[envelope.credit + ", " + envelope.licence_name],
            open_points=diagnosis_run.open_points("A1-OP6"),
            development_reads=diagnosis_run.DEVELOPMENT_READS,
            not_computed=["any figure from a radar image", "the analysis extent of the product (rights level local; not read)",
                          "FPPS", "A-E class", "flood candidate", "any value for a single tambon"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=True, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
