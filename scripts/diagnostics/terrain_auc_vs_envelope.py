"""Diagnosis figure of plan task A1: do low ground and flat ground separate the season envelope inside AOI-01?

README
======

Reads
    * The Copernicus GLO-30 surface model tile N20 E099, outside Git: the file the registered receipt of plan
      tasks A2 and A4 names, checked by SHA-256.
    * The accumulated layer of UNOSAT/GISTDA product 4009 (the 2024 season envelope), through the rights
      registry and ``floodguard.flood_inputs.load_se1``. CC BY-SA 4.0; credit: UNOSAT and GISTDA,
      FL20240912THA, UNOSAT product 4009.
    * AOI-01, the COD-AB tambon boundaries, JRC Global Surface Water and ESA WorldCover 2021.

    It reads no radar image.

Computes
    On the 20 m grid of the darkening figure: two terrain features, low elevation (the surface height,
    negated) and low slope (the slope in degrees, negated), and the rank statistic of each against the
    envelope: the probability that a cell inside the envelope is lower, or flatter, than a cell outside it
    (area under the ROC curve; 0.5 is no separation). Permanent water is left out three ways, and each
    reading is given on two sets of cells: all cells, and the cells with a slope under 5 degrees. Plan row
    A1 lists the figure as "terrain AUC vs 4009 (to compute)" and names no feature. The two features are
    those of the exploratory script of the plan session, which printed their values and recorded none; this
    is the first computation from cleared files and the first recorded value. Label: vs a season envelope,
    not an event map.

Does not show
    * A flood, or a flood extent. Terrain is the same before, during and after an event.
    * That terrain can map a flood. On all cells a value above one half mostly tells the plain from the
      hills around it; the readings on the cells under 5 degrees say how the features order the plain itself.
    * How correct anything is: the envelope is not a reference.
    * HAND (height above the nearest drainage). None is computed: no HAND raster and no drainage rule is in
      the signed files or on disk.

Writes
    ``outputs/a1_diagnosis/terrain_auc_vs_envelope.json``, the run receipt
    ``outputs/planning_v1/a1_diagnosis_terrain_auc_vs_envelope.json`` and its register entry. No raster is written.

Run
    ``python scripts/diagnostics/terrain_auc_vs_envelope.py --external-data <external data root>``
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

LOW_ELEVATION = "low_elevation"
LOW_SLOPE = "low_slope"
FEATURES = {
    LOW_ELEVATION: "surface height of GLO-30 in metres, negated: larger where the ground is lower",
    LOW_SLOPE: "slope in degrees from central differences of the 20 m height grid, negated: larger where the ground is flatter",
}

SPEC = diagnosis_run.FigureSpec(
    figure_id="terrain_auc_vs_envelope",
    title="Separation of low and flat ground against the 2024 season envelope, AOI-01",
    script="scripts/diagnostics/terrain_auc_vs_envelope.py",
    plan_statement="terrain AUC vs 4009 (to compute)",
    computes="The rank statistic (area under the ROC curve) of two terrain features of the Copernicus GLO-30 surface model, low "
             "elevation and low slope, against the product 4009 accumulated layer, on 20 m cells of AOI-01 on the Thai side, "
             "with permanent water left out three ways and on two sets of cells. No radar image is read and no layer is written.",
    does_not_show=(
        "A flood or a flood extent: terrain is the same before, during and after an event.",
        "That terrain can map a flood: on all cells a value above one half mostly tells the plain from the hills around it.",
        "How correct anything is: the envelope is not a reference.",
        "HAND (height above the nearest drainage): none is computed.",
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
        elevation, slope = domain.elevation, domain.slope
        assert elevation is not None and slope is not None
        features = {LOW_ELEVATION: -elevation, LOW_SLOPE: -slope}
        readings: list[dict] = []
        for cell_set in layers.CELL_SETS:
            for water in layers.WATER_READINGS:
                statistics = diagnosis.separation_against_layer(features, domain.inside, domain.cells(water, cell_set))
                for name in (LOW_ELEVATION, LOW_SLOPE):
                    row = statistics[name]
                    readings.append({
                        "feature": name, "permanent_water": water, "cells": cell_set, "auc": row["auc"],
                        "cells_inside_the_layer": row["cells_inside_the_layer"], "cells_outside_the_layer": row["cells_outside_the_layer"],
                        "cells_left_out_for_no_value": row["cells_left_out_for_no_value"],
                        # The features are negated heights and slopes; the medians are given as the height and the slope themselves.
                        ("median_elevation_m_inside_the_layer" if name == LOW_ELEVATION else "median_slope_degrees_inside_the_layer"):
                            round(-row["median_inside_the_layer"], 2),
                        ("median_elevation_m_outside_the_layer" if name == LOW_ELEVATION else "median_slope_degrees_outside_the_layer"):
                            round(-row["median_outside_the_layer"], 2),
                    })
        by_feature = {cell_set: {name: sorted(row["auc"] for row in readings if row["feature"] == name and row["cells"] == cell_set)
                                 for name in FEATURES} for cell_set in layers.CELL_SETS}
        cells = domain.base
        figures = {
            "features": FEATURES,
            "statistic": "area under the ROC curve: the probability that a cell inside the envelope has a larger value than a "
                         "cell outside it, a tie counting one half; 0.5 is no separation",
            "domain": dict(domain.record),
            "elevation_in_the_domain_m": {"min": round(float(np.nanmin(elevation[cells])), 1), "median": round(float(np.nanmedian(elevation[cells])), 1),
                                          "max": round(float(np.nanmax(elevation[cells])), 1)},
            "readings": readings,
            "smallest_and_largest_auc_by_feature": {cell_set: {name: [values[0], values[-1]] for name, values in features_of_set.items()}
                                                    for cell_set, features_of_set in by_feature.items()},
            "not_named_the_terrain_figure_of_the_plan": "The plan names no terrain feature and no set of cells (open points A1-OP1 "
                                                        "and A1-OP10). Both features are given on both sets of cells; none is the "
                                                        "figure of record.",
            "no_interval_is_given": "Neighbouring cells are not independent, so an interval computed from the cell count would "
                                    "be far too narrow. None is given.",
        }
        return diagnosis_run.FigureResult(
            figures=figures,
            inputs=dict(domain.inputs),
            parameters={**layers.comparison_parameters(), "features": list(FEATURES)},
            source_timestamp="GLO-30 surface model (TanDEM-X acquisitions of 2010 to 2015); envelope 2024-08-01/2024-10-12",
            confidence_basis="A statistic of a 30 m surface model against an unvalidated preliminary agency extent used as a season "
                             "envelope (UNOSAT product 4009 with GISTDA; Field_Validation=0). No reference of any kind was used; "
                             "nothing here says how correct a layer is.",
            assumptions=[
                layers.STANDARD_LIMIT,
                "GLO-30 is a surface model: it holds roofs and tree tops, so built-up and wooded ground reads higher than it is.",
                "The height is warped bilinearly from 1 arc-second cells to the 20 m grid, and the slope is taken from that grid.",
                "A cell is in the comparison when its centre lies in AOI-01 and in a Thai tambon and it is not permanent water "
                "under the reading. No radar value is needed. The second set of cells keeps only those with a slope under 5 degrees.",
            ],
            limits=[
                "Terrain does not change with an event. The figure describes where the season envelope lies, not when or "
                "whether a place was flooded.",
                "AOI-01 holds hills and plain. On all cells a terrain feature can separate the envelope simply because the "
                "envelope lies on the plain: domain.slope_in_the_domain gives the share of envelope cells and of other cells "
                "under 5 degrees. The readings on the cells with a slope under 5 degrees leave the hills out.",
                "Elevation is absolute height, not height above the river, so low elevation can separate plain from hill as "
                "much as wet from dry.",
                "The envelope holds water of the whole season, with no date per patch. A value above one half is not evidence "
                "that a terrain rule maps a flood.",
                "No interval is given: the cells are not independent.",
                "The envelope is not a reference and the figure is not a validation.",
            ],
            plan_figure={
                "stated_in_the_plan": "terrain AUC vs 4009 (to compute)",
                "plan_value": None,
                "measured": {cell_set: {name: {"smallest": values[0], "largest": values[-1]} for name, values in features_of_set.items()}
                             for cell_set, features_of_set in by_feature.items()},
                "reproduced": None,
                "note": "The plan gives no value and no feature. This is the first computation from cleared files and the first "
                        "recorded value. It is not the first time the figure was seen: the exploratory script of the plan "
                        "session ranked the negated height and the negated slope against the same layer and printed both values "
                        "on the line that gave 0.421. Those values are in no committed file, and the two features were taken "
                        "from that script (open point A1-OP1).",
            },
            licence=envelope.licence(raster_cell_m=layers.CELL_M, then="two terrain features were then ranked against the cells of the layer"),
            rights=dict(envelope.rights),
            attributions=[envelope.credit + ", " + envelope.licence_name, layers.ATTRIBUTION_DEM, "JRC Global Surface Water (EC JRC/Google)",
                          "ESA WorldCover 2021 v200 (CC BY 4.0)", "HDX Thailand COD-AB boundaries"],
            open_points=diagnosis_run.open_points("A1-OP1", "A1-OP4", "A1-OP6", "A1-OP10"),
            development_reads=diagnosis_run.DEVELOPMENT_READS,
            not_computed=["HAND (height above the nearest drainage)", "any figure from a radar image", "a flood candidate or any threshold",
                          "the analysis extent of the product (rights level local; not read)", "an interval for the statistic",
                          "FPPS", "A-E class", "any value for a single tambon"],
        )

    return compute


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script from the command line."""

    return diagnosis_run.command_line(SPEC, make_compute, root=ROOT, description=__doc__, needs_external_data=True, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
