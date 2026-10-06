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
    * AOI-01, the COD-AB tambon boundaries, JRC Global Surface Water, ESA WorldCover 2021 and the Copernicus
      GLO-30 surface model (for the slope that gives the second set of cells).

Computes
    On a 20 m grid over AOI-01: the darkening of VH (VH before minus VH after, in dB, each a mean over a
    window of cells), and its rank statistic against the envelope: the probability that a cell inside the
    envelope darkened more than a cell outside it (area under the ROC curve; 0.5 is no separation). It is
    given for both geocodings, with permanent water left out three ways, on two sets of cells (all cells, and
    the cells with a slope under 5 degrees) and for six window sizes (1, 3, 5, 9, 15 and 25 cells). Plan row
    A1 states the figure as "darkening-dVH AUC vs the 4009 envelope 0.421"; the reading with the 5 by 5
    window on all cells follows the exploratory script that gave it. Label: vs a season envelope, not an
    event map.

Does not show
    * How correct any radar method is. The envelope is not a reference: it holds every area mapped as water
      at some time from August to October 2024, and the radar pair sees one morning, several days after the
      keyframe the Mae Sai replay sets for the modelled peak (an illustrative keyframe; no gauge record
      gives the time of the peak).
    * That the radar saw no water. A value near one half says that darkening alone does not tell the
      envelope from the rest at that pass.
    * A property of the pass that holds for every window. The value moves with the smoothing window, which
      no signed file names.
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
"""The smoothing window of the exploratory script that gave 0.421. No signed file names a window (open point A1-OP2)."""
WINDOWS: tuple[int, ...] = (1, 3, 5, 9, 15, 25)
"""The windows the figure is given for, in 20 m cells: 1 is no smoothing, 25 is 500 m."""
FEATURE = "darkening_vh_db"
EXPLORATORY_READING = {"geocoding": "gcp_polynomial", "permanent_water": layers.WATER_JRC, "cells": layers.CELLS_ALL,
                       "window_cells": BOXCAR_CELLS}
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
             "product 4009 accumulated layer, on 20 m cells of AOI-01 on the Thai side, for two geocodings, three ways of "
             "leaving out permanent water, two sets of cells and six smoothing windows. No threshold is applied and no layer "
             "is written.",
    does_not_show=(
        "How correct any radar method is: the envelope is not a reference, it is a comparison layer for a whole season.",
        "That the radar saw no water: a value near one half says that darkening alone does not tell the envelope from the rest.",
        "A property of the pass that holds for every window: the value moves with the smoothing window, which no signed file names.",
        "A flood candidate: no threshold is applied, and the candidates of tasks A2 and A4 are not read.",
    ),
    label=diagnosis_run.ENVELOPE_LABEL,
)


def reading(darkening: object, domain: layers.ComparisonDomain, *, geocoding: str, water: str, cell_set: str, window: int) -> dict:
    """Return one reading of the figure: the rank statistic of a darkening grid on one set of cells."""

    statistic = diagnosis.separation_against_layer({FEATURE: darkening}, domain.inside, domain.cells(water, cell_set))[FEATURE]
    return {"geocoding": geocoding, "permanent_water": water, "cells": cell_set, "window_cells": window, **statistic,
            # The same pairs read the other way: how often the cell inside the envelope brightened more.
            "auc_of_brightening": round(1.0 - statistic["auc"], 6)}


def make_compute(root: Path, external: Path | None) -> Callable[[], diagnosis_run.FigureResult]:
    """Return the function that computes the figures of this script."""

    def compute() -> diagnosis_run.FigureResult:
        import numpy as np

        assert external is not None
        envelope = layers.load_envelope(root, external)
        domain = layers.comparison_domain(root, external, envelope)
        readings: list[dict] = []
        by_window: list[dict] = []
        radar_inputs: dict[str, dict] = {}
        valid_cells: dict[str, int] = {}
        for geocoding, receipt_path in layers.RADAR_RECEIPTS.items():
            receipt, receipt_record = layers.registered_receipt(root, receipt_path)
            if receipt["parameters"]["geocoding"] != geocoding or layers.receipt_grid(receipt) != layers.receipt_grid(
                    layers.registered_receipt(root, layers.RADAR_RECEIPTS["gcp_polynomial"])[0]):
                raise diagnosis_run.DiagnosisRunError(f"{receipt_path.as_posix()} is not the {geocoding} run on the grid of the run of record")
            blocks = {}
            files = {}
            for date, name in layers.SIGMA0_NAMES.items():
                path, record = layers.bound_file(receipt, name, external)
                if layers.source_grid(path) != layers.receipt_grid(receipt):
                    raise diagnosis_run.DiagnosisRunError(f"{name} is not on the grid its receipt states")
                blocks[date] = layers.read_block_mean(path, domain.grid, band=layers.VH_BAND)
                files[date] = record
            radar_inputs[geocoding] = {"receipt": receipt_record, "run_role": receipt["run_role"], "sigma0_pre_20240903": files["pre"],
                                       "sigma0_post_20240915": files["post"]}
            for window in WINDOWS:
                darkening = diagnosis.darkening_db(diagnosis.boxcar_mean(blocks["pre"], window), diagnosis.boxcar_mean(blocks["post"], window))
                if window == BOXCAR_CELLS:
                    valid_cells[geocoding] = int((domain.base & np.isfinite(darkening)).sum())
                    readings += [reading(darkening, domain, geocoding=geocoding, water=water, cell_set=cell_set, window=window)
                                 for cell_set in layers.CELL_SETS for water in layers.WATER_READINGS]
                by_window += [reading(darkening, domain, geocoding=geocoding, water=layers.WATER_JRC, cell_set=cell_set, window=window)
                              for cell_set in layers.CELL_SETS]
        everything = readings + by_window
        values = [row["auc"] for row in everything]
        exploratory = next(row for row in readings if all(row[key] == value for key, value in EXPLORATORY_READING.items()))
        series = {geocoding: {cell_set: [row["auc"] for row in by_window if row["geocoding"] == geocoding and row["cells"] == cell_set]
                              for cell_set in layers.CELL_SETS} for geocoding in layers.RADAR_RECEIPTS}
        figures = {
            "feature": "darkening of VH in dB: VH before (3 September 2024) minus VH after (15 September 2024, 23:16 UTC), each "
                       "a mean over a window of 20 m cells of linear sigma0; positive where the later image is darker",
            "statistic": "area under the ROC curve: the probability that a cell inside the envelope has a larger value than a "
                         "cell outside it, a tie counting one half; 0.5 is no separation",
            "domain": dict(domain.record),
            "cells_with_a_radar_value_in_the_domain": valid_cells,
            "readings": readings,
            "readings_note": "The readings with the 5 by 5 window: two geocodings, three ways of leaving out permanent water "
                             "and two sets of cells.",
            "readings_by_smoothing_window": by_window,
            "readings_by_smoothing_window_note": "JRC surface water left out. A window of 1 cell is no smoothing; a window of "
                                                 "25 cells is a mean over 500 m. The rows of the 5 by 5 window repeat the "
                                                 "readings above.",
            "windows_cells": list(WINDOWS),
            "the_value_falls_at_every_step_as_the_window_grows": {
                geocoding: {cell_set: all(later < earlier for earlier, later in zip(values_by_window[:-1], values_by_window[1:]))
                            for cell_set, values_by_window in by_cell_set.items()}
                for geocoding, by_cell_set in series.items()},
            "reading_that_follows_the_exploratory_definition": {**EXPLORATORY_READING, "auc": exploratory["auc"]},
            "smallest_and_largest_auc_over_the_readings": [min(values), max(values)],
            "every_reading_is_below_one_half": max(values) < 0.5,
            "reading_below_one_half": "A value below one half means that the cells inside the envelope tended to darken less "
                                      "than the cells outside it. auc_of_brightening is one minus the value; it adds no "
                                      "measurement. It is the feature the exploratory script called brightening.",
            "geocodings": GEOCODING_NOTES,
            "no_interval_is_given": "Neighbouring cells are not independent, so an interval computed from the cell count would "
                                    "be far too narrow. None is given.",
        }
        measured = round(exploratory["auc"], 3)
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs={**dict(domain.inputs), "radar": radar_inputs},
            parameters={**layers.comparison_parameters(), "polarisation": "VH", "block_mean_of_source_cells": "2 by 2, on linear sigma0",
                        "boxcar_cells": BOXCAR_CELLS, "boxcar_windows_cells": list(WINDOWS),
                        "boxcar_rule": "mean of the cells with a value; no value when half the window or less has one",
                        "geocodings": list(layers.RADAR_RECEIPTS), "exploratory_reading": EXPLORATORY_READING},
            source_timestamp="2024-09-15T23:16:01Z",
            confidence_basis="A statistic of own radar layers (tier T2, unqualified, approximate geocoding) against an unvalidated "
                             "preliminary agency extent used as a season envelope (UNOSAT product 4009 with GISTDA; "
                             "Field_Validation=0). No reference of any kind was used; nothing here says how correct a layer is.",
            assumptions=[
                layers.STANDARD_LIMIT,
                "One image pair: 3 September 2024 23:16 UTC and 15 September 2024 23:16 UTC (16 September 06:16 in Thailand), "
                "both descending on relative orbit 135. The second image was taken several days after the keyframe the Mae Sai "
                "replay sets for the modelled peak. That keyframe is illustrative: no gauge record gives the time of the peak.",
                "The radar values are the stored sigma0 rasters of tasks A2 and A4: sigma0 from the SAFE calibration table, "
                "thermal noise not removed, 10 m cells, averaged here to 20 m.",
                "A cell is in the comparison when its centre lies in AOI-01 and in a Thai tambon, it is not permanent water under "
                "the reading, and it has a radar value on both dates. The second set of cells keeps only those with a GLO-30 "
                "slope under 5 degrees.",
                "The smoothing window is a free choice. The 5 by 5 window is the one of the exploratory script; the other "
                "windows are given so that the choice can be seen.",
            ],
            limits=[
                "The envelope holds water of August and of early October as well, and the pass is one morning, several days "
                "after the keyframe the replay sets for the modelled peak. A cell can be inside the envelope and dry at the "
                "pass, or wet at the pass and outside it.",
                "The value depends on the smoothing window (readings_by_smoothing_window). No window is the window of record, "
                "so no single value describes the pass.",
                "On all cells the comparison mixes hill and plain; the readings on the cells with a slope under 5 degrees "
                "leave the hills out. Neither set of cells is the domain of record.",
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
                        "exploratory script as far as cleared files allow (control-point warp, JRC water left out, all cells, "
                        "5 by 5 window). It differs from that script in two stated ways: calibrated sigma0 instead of "
                        "uncalibrated amplitudes, and the Thai side from the COD-AB boundaries instead of the product's analysis "
                        "extent. The script printed the rank statistic of seven features on one line; only this one was "
                        "carried into the plan (open point A1-OP2).",
            },
            licence=envelope.licence(raster_cell_m=layers.CELL_M, then="the radar darkening was then ranked against the cells of the layer"),
            rights={**dict(envelope.rights),
                    "sentinel_1": "No signed rights record covers the Sentinel-1 data (open points E1-OP2 and A1-OP5). Statistics for "
                                  "the whole area are committed with the Copernicus attribution; no radar layer is written."},
            attributions=[envelope.credit + ", " + envelope.licence_name, ATTRIBUTION_SENTINEL, layers.ATTRIBUTION_DEM,
                          "JRC Global Surface Water (EC JRC/Google)", "ESA WorldCover 2021 v200 (CC BY 4.0)", "HDX Thailand COD-AB boundaries"],
            open_points=diagnosis_run.open_points("A1-OP2", "A1-OP3", "A1-OP4", "A1-OP5", "A1-OP6", "A1-OP10"),
            development_reads=diagnosis_run.DEVELOPMENT_READS,
            not_computed=["a flood candidate or any threshold", "any comparison of the candidates of tasks A2 and A4 with product 4009",
                          "the absolute change of VH or of VV and the VH after the event (features of the exploratory script that "
                          "plan row A1 does not list)",
                          "the analysis extent of the product (rights level local; not read)", "an interval for the statistic",
                          "FPPS", "A-E class", "any value for a single tambon"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=True, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
