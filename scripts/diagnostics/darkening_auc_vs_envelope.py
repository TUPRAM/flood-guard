"""Diagnosis figure of plan task A1: does the fall in VH backscatter at the 16 September pass separate the season envelope?

README
======

Reads
    * The stored sigma0 rasters of plan tasks A2 and A4 (3 and 15 September 2024, 23:16 UTC), outside Git, as
      the bytes their two registered receipts bind: the run of record (control-point polynomial warp) and the
      sensitivity run (a DEM height for every cell). Contains modified Copernicus Sentinel data 2024.
    * The accumulated layer of UNOSAT/GISTDA product 4009 (the 2024 season envelope), through the rights
      registry and ``floodguard.flood_inputs.load_se1``. CC BY-SA 4.0; credit: UNOSAT and GISTDA,
      FL20240912THA, UNOSAT product 4009.
    * AOI-01, the COD-AB tambon boundaries, JRC Global Surface Water and ESA WorldCover 2021.

Computes
    On a 20 m grid over AOI-01: the darkening of VH (VH before minus VH after, in dB, each a 5 by 5 mean),
    and its rank statistic against the envelope: the probability that a cell inside the envelope darkened
    more than a cell outside it (area under the ROC curve; 0.5 is no separation). It is given for both
    geocodings and with permanent water left out three ways. Plan row A1 states the figure as
    "darkening-dVH AUC vs the 4009 envelope 0.421". Label: vs a season envelope, not an event map.

Does not show
    * How correct any radar method is. The envelope is not a reference: it holds every area mapped as water
      at some time from August to October 2024, and the radar pair sees one morning after the peak.
    * That the radar saw no water. A value near one half says that darkening alone does not tell the
      envelope from the rest at that pass.
    * A flood candidate. No threshold is applied and no layer is written. The candidates of tasks A2 and
      A4 are not read and not compared with product 4009.

Writes
    ``outputs/a1_diagnosis/darkening_auc_vs_envelope.json``, the run receipt
    ``outputs/planning_v1/a1_diagnosis_darkening_auc_vs_envelope.json`` and its register entry. No raster is written.

Run
    ``python scripts/diagnostics/darkening_auc_vs_envelope.py --external-data <external data root>``
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import abstention_diagnosis as diagnosis  # noqa: E402
from floodguard import diagnosis_layers as layers  # noqa: E402
from floodguard import diagnosis_run  # noqa: E402

BOXCAR_CELLS = 5
FEATURE = "darkening_vh_db"
EXPLORATORY_READING = {"geocoding": "gcp_polynomial", "permanent_water": layers.WATER_JRC}
GEOCODING_NOTES = {
    "gcp_polynomial": "the run of record of tasks A2 and A4: the plan's fallback, a control-point polynomial warp. The A2/A4 "
                      "result measured that it displaces the radar content by about 680 m.",
    "annotation_grid_with_cell_height": "the sensitivity run of tasks A2 and A4: a DEM height for every cell. It is not in the "
                                        "plan and replaces nothing.",
}
ATTRIBUTION_SENTINEL = "Contains modified Copernicus Sentinel data 2024"

SPEC = diagnosis_run.FigureSpec(
    figure_id="darkening_auc_vs_envelope",
    title="Separation of the VH darkening at the 16 September 2024 pass against the 2024 season envelope, AOI-01",
    script="scripts/diagnostics/darkening_auc_vs_envelope.py",
    plan_statement="darkening-dVH AUC vs the 4009 envelope 0.421",
    computes="The rank statistic (area under the ROC curve) of the VH darkening between 3 and 15 September 2024 against the "
             "product 4009 accumulated layer, on 20 m cells of AOI-01 on the Thai side, for two geocodings and three ways of "
             "leaving out permanent water. No threshold is applied and no layer is written.",
    does_not_show=(
        "How correct any radar method is: the envelope is not a reference, it is a comparison layer for a whole season.",
        "That the radar saw no water: a value near one half says that darkening alone does not tell the envelope from the rest.",
        "A flood candidate: no threshold is applied, and the candidates of tasks A2 and A4 are not read.",
    ),
    label=diagnosis_run.ENVELOPE_LABEL,
)


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        import numpy as np

        assert external is not None
        envelope = layers.load_envelope(root, external)
        domain = layers.comparison_domain(root, external, envelope)
        readings: list[dict] = []
        radar_inputs: dict[str, dict] = {}
        valid_cells: dict[str, int] = {}
        for geocoding, receipt_path in layers.RADAR_RECEIPTS.items():
            receipt, receipt_record = layers.registered_receipt(root, receipt_path)
            if receipt["parameters"]["geocoding"] != geocoding or layers.receipt_grid(receipt) != layers.receipt_grid(
                    layers.registered_receipt(root, layers.RADAR_RECEIPTS["gcp_polynomial"])[0]):
                raise diagnosis_run.DiagnosisRunError(f"{receipt_path.as_posix()} is not the {geocoding} run on the grid of the run of record")
            smoothed = {}
            files = {}
            for date, name in layers.SIGMA0_NAMES.items():
                path, record = layers.bound_file(receipt, name, external)
                if layers.source_grid(path) != layers.receipt_grid(receipt):
                    raise diagnosis_run.DiagnosisRunError(f"{name} is not on the grid its receipt states")
                smoothed[date] = diagnosis.boxcar_mean(layers.read_block_mean(path, domain.grid, band=layers.VH_BAND), BOXCAR_CELLS)
                files[date] = record
            radar_inputs[geocoding] = {"receipt": receipt_record, "run_role": receipt["run_role"], "sigma0_pre_20240903": files["pre"],
                                       "sigma0_post_20240915": files["post"]}
            darkening = diagnosis.darkening_db(smoothed["pre"], smoothed["post"])
            valid_cells[geocoding] = int((domain.base & np.isfinite(darkening)).sum())
            for water in layers.WATER_READINGS:
                statistic = diagnosis.separation_against_layer({FEATURE: darkening}, domain.inside, domain.cells(water))[FEATURE]
                readings.append({"geocoding": geocoding, "permanent_water": water, **statistic,
                                 # The same pairs read the other way: how often the cell inside the envelope brightened more.
                                 "auc_of_brightening": round(1.0 - statistic["auc"], 6)})
        values = [row["auc"] for row in readings]
        exploratory = next(row for row in readings if all(row[key] == value for key, value in EXPLORATORY_READING.items()))
        figures = {
            "feature": "darkening of VH in dB: VH before (3 September 2024) minus VH after (15 September 2024, 23:16 UTC), each "
                       "a 5 by 5 mean of 20 m cells of linear sigma0; positive where the later image is darker",
            "statistic": "area under the ROC curve: the probability that a cell inside the envelope has a larger value than a "
                         "cell outside it, a tie counting one half; 0.5 is no separation",
            "domain": dict(domain.record),
            "cells_with_a_radar_value_in_the_domain": valid_cells,
            "readings": readings,
            "reading_that_follows_the_exploratory_definition": {**EXPLORATORY_READING, "auc": exploratory["auc"]},
            "smallest_and_largest_auc_over_the_readings": [min(values), max(values)],
            "every_reading_is_below_one_half": max(values) < 0.5,
            "reading_below_one_half": "A value below one half means that the cells inside the envelope tended to darken less "
                                      "than the cells outside it. In every reading the median inside the envelope is negative: "
                                      "those cells were brighter on 15 September than on 3 September. auc_of_brightening is one "
                                      "minus the value; it adds no measurement.",
            "geocodings": GEOCODING_NOTES,
            "no_interval_is_given": "Neighbouring cells are not independent, so an interval computed from the cell count would "
                                    "be far too narrow. None is given.",
        }
        measured = round(exploratory["auc"], 3)
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={**dict(domain.inputs), "radar": radar_inputs},
            parameters={**layers.comparison_parameters(), "polarisation": "VH", "block_mean_of_source_cells": "2 by 2, on linear sigma0",
                        "boxcar_cells": BOXCAR_CELLS, "boxcar_rule": "mean of the cells with a value; no value when half the window or less has one",
                        "geocodings": list(layers.RADAR_RECEIPTS), "exploratory_reading": EXPLORATORY_READING},
            source_timestamp="2024-09-15T23:16:01Z",
            confidence_basis="A statistic of own radar layers (tier T2, unqualified, approximate geocoding) against an unvalidated "
                             "preliminary agency extent used as a season envelope (UNOSAT product 4009 with GISTDA; "
                             "Field_Validation=0). No reference of any kind was used; nothing here says how correct a layer is.",
            assumptions=[
                layers.STANDARD_LIMIT,
                "One image pair: 3 September 2024 23:16 UTC and 15 September 2024 23:16 UTC (16 September 06:16 in Thailand), "
                "both descending on relative orbit 135. The second image was taken several days after the flood peak.",
                "The radar values are the stored sigma0 rasters of tasks A2 and A4: sigma0 from the SAFE calibration table, "
                "thermal noise not removed, 10 m cells, averaged here to 20 m.",
                "A cell is in the comparison when its centre lies in AOI-01 and in a Thai tambon, it is not permanent water under "
                "the reading, and it has a radar value on both dates.",
            ],
            limits=[
                "The envelope holds water of August and of early October as well, and the pass is one morning several days "
                "after the peak. A cell can be inside the envelope and dry at the pass, or wet at the pass and outside it.",
                "Under the geocoding of the run of record the radar content lies about 680 m from where it belongs, and the two "
                "dates lie about 9 m apart (open point A4-OP1). That reading compares displaced radar cells with the envelope.",
                "Darkening is one feature. Water under buildings or trees, and water standing on fields that were already wet "
                "on 3 September, does not darken the image.",
                "No interval is given: the cells are not independent.",
                "The envelope is not a reference and the figure is not a validation.",
            ],
            plan_figure={
                "stated_in_the_plan": "darkening-dVH AUC vs the 4009 envelope 0.421",
                "plan_value": 0.421,
                "measured": exploratory["auc"],
                "reproduced": measured == 0.421,
                "note": "The plan gives the figure and no definition. The measured value is the reading that follows the "
                        "exploratory script as far as cleared files allow (control-point warp, JRC water left out). It differs "
                        "from that script in two stated ways: calibrated sigma0 instead of uncalibrated amplitudes, and the "
                        "Thai side from the COD-AB boundaries instead of the product's analysis extent (open point A1-OP2).",
            },
            licence=envelope.licence(raster_cell_m=layers.CELL_M, then="the radar darkening was then ranked against the cells of the layer"),
            rights={**dict(envelope.rights),
                    "sentinel_1": "No signed rights record covers the Sentinel-1 data (open points E1-OP2 and A1-OP5). Statistics for "
                                  "the whole area are committed with the Copernicus attribution; no radar layer is written."},
            attributions=[envelope.credit + ", " + envelope.licence_name, ATTRIBUTION_SENTINEL,
                          "JRC Global Surface Water (EC JRC/Google)", "ESA WorldCover 2021 v200 (CC BY 4.0)", "HDX Thailand COD-AB boundaries"],
            open_points=diagnosis_run.open_points("A1-OP2", "A1-OP3", "A1-OP4", "A1-OP5", "A1-OP6"),
            development_reads=diagnosis_run.DEVELOPMENT_READS,
            not_computed=["a flood candidate or any threshold", "any comparison of the candidates of tasks A2 and A4 with product 4009",
                          "the analysis extent of the product (rights level local; not read)", "an interval for the statistic",
                          "FPPS", "A-E class", "any value for a single tambon"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=True, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
