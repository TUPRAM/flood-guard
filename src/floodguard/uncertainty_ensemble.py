"""Uncertainty ensemble of one case: the predeclared grid, class retention and the headline rule (plan task E10).

Restructuring plan v2, sections 2.3 item 8, 3.1 (stage P7) and 5 item 11; protocol v1b ``ensemble_grid``; protocol
v1a guardrail GR8. The ensemble asks one question of every reporting unit of a case: how far do its FPPS and its
binding class move when the choices the protocols declared in advance are varied. Nothing here is a probability,
a confidence interval or a check against the ground: every cell is the same modelled chain run with another
declared choice.

* **The grid** is read from the two protocol files in force (:func:`load_grid`) and is never restated here: six
  core axes (flood input level, passability, facility set, population vintage, vulnerability anchors, weight
  preset), 3 x 3 x 3 x 2 x 2 x 5 = 540 cells for each lane, of which the 27 combinations of the first three need
  access runs. A file that states other axes, levels or counts is refused.
* **A cell** is computed as task E8 computes the row of a unit, through the same functions:
  ``planning_assessment.assess_unit`` gives the five components, the confidence record and the row of one
  combination of flood level, passability, facility set and population vintage; ``planning_assessment.scoring_block``
  gives the FPPS, the binding class of class rule v1, its reason code and leave-one-component-out under each pair
  of vulnerability anchors and each weight preset. The default cell of protocol v1b is therefore the row task E8
  reports.
* **What is run and what is not** is said cell by cell (:func:`cell_table`). A level that cannot be run today is
  never approximated: its cells are listed with the reason. A cell that was run and failed is reported as failed,
  with the stage and the error, and is counted; it is never dropped.
* **Class retention and the headline rule** (:func:`headline_record`). Protocol v1b: "Retention is the share of
  the 540 core cells whose v1 class equals the class of the default cell"; for a public overlay "class retention
  is computed over the 180 cells of the public facility set only". Guardrail GR8: a class is headlined only at a
  retention of at least 0.6. The rule is evaluated only when every cell of the set the protocol names has a
  class. Otherwise the headline stays ``not_evaluated``, and the record gives the share over the cells that were
  run, labelled as such, and the lowest and highest retention the missing cells could still give. A cell that
  was run and failed stays in the denominator of every share taken over the cells run. Where the protocols leave
  a reading open, the record gives both and sets no status from either: the 540 core cells beside the 180 cells
  of the public facility set (open point E10-OP11), and every pair of levels declared cut line 6 could keep
  (open point E10-OP12).
* **The outputs protocol v1b names for a unit** (``ensemble_grid.per_tambon_outputs``): the range of the FPPS, the
  share of cells in each class, the percent of cells keeping the class, the best and worst rank, the people
  losing 30-minute access over the access runs, the FPPS swing along each axis, and leave-one-component-out over
  the cells. The equity figures (EED and EER) are plan task E9 and are not computed.

The functions take measurements as arguments and read no file besides the protocol files. An ensemble is planning
guidance for preparedness and post-event prioritisation. It is not an official warning and not an observation of
a flood, and class E never means safe.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
import copy
from dataclasses import dataclass, replace
from fractions import Fraction
import itertools
import math
from pathlib import Path
import re
import statistics
from typing import Any

from floodguard import closure_rules, flood_inputs, planning_assessment, sensitivity
from floodguard.normalisation import frame_record, leave_one_component_out_weights, read_protocol_in_force
from floodguard.planning_overlay import (
    GUARDRAIL_GR8,
    HEADLINE_ELIGIBLE,
    HEADLINE_NOT_EVALUATED,
    HEADLINE_UNSTABLE,
    V2_NOT_EVALUATED,
)
from floodguard.scoring import SCORE_COMPONENTS, validate_weights

ENSEMBLE_VERSION = "uncertainty_ensemble_v1"
FLOOD_AXIS, PASSABILITY_AXIS, FACILITIES_AXIS = "flood_input_single_state", "passability", "facilities"
VINTAGE_AXIS, ANCHORS_AXIS, WEIGHTS_AXIS = "population_vintage", "vulnerability_anchors", "weights"
AXES: tuple[str, ...] = (FLOOD_AXIS, PASSABILITY_AXIS, FACILITIES_AXIS, VINTAGE_AXIS, ANCHORS_AXIS, WEIGHTS_AXIS)
"""The six core axes of protocol v1b ``ensemble_grid.core_axes``, in the order the protocol lists them."""
ROUTING_AXES: tuple[str, ...] = (FLOOD_AXIS, PASSABILITY_AXIS, FACILITIES_AXIS)
"""The axes whose combinations need access runs (``routing_combinations_note``)."""
MEASUREMENT_AXES: tuple[str, ...] = (FLOOD_AXIS, PASSABILITY_AXIS, FACILITIES_AXIS, VINTAGE_AXIS)
"""The axes that change what is measured of a unit. The two others change how the measurements are scored."""
VINTAGE_KEYS: Mapping[str, str] = {"WorldPop 2020": "worldpop_2020", "2024-rescaled demand": "rescaled_2024"}
PUBLIC_LEVEL, PITCH_LEVEL = "public", "pitch"
STATUS_RUN, STATUS_NOT_RUN = "run", "not_run"
NO_CLASS = "no_class"
"""How a cell without a binding class is counted: a unit under guardrail GR1, in every cell."""
CLASS_KEYS: tuple[str, ...] = ("A", "B", "C", "D", "E", NO_CLASS)
VULNERABILITY = "vulnerability_context_0_100"
FLOOD_LIKELIHOOD = "flood_likelihood_0_100"
THIRTY_MINUTES = 30
BOUNDS_BELOW, BOUNDS_AT_OR_ABOVE = "below_the_minimum", "at_or_above_the_minimum"

RoutingKey = tuple[str, str, str, str]
"""The levels of one set of measurements: flood level, passability, facility set, population vintage."""

OPEN_POINTS: tuple[Mapping[str, str], ...] = (
    {
        "id": "E10-OP1",
        "point": "The headline rule when cells of the set the protocol names cannot be run.",
        "signed_files_say": "Protocol v1b ensemble_grid.headline_rule: 'Retention is the share of the 540 core cells "
                            "whose v1 class equals the class of the default cell'. facility_sets.shelters_in_the_ensemble: "
                            "'For a public overlay, class retention is computed over the 180 cells of the public "
                            "facility set only, and the overlay says so.' Protocol v1a guardrail GR8: 'A class is "
                            "headlined only if it keeps at least 60 percent retention over the single-state ensemble.' "
                            "The rule goes on: 'Otherwise it is shown as unstable: verify.' The demo-tambon rule of v1a: "
                            "'If no unit is headline-eligible, it is the highest-FPPS unit, shown as unstable: verify.' "
                            "None of them says what retention is while a part of those cells cannot be run, nor how a "
                            "class is shown while its retention is not evaluated. Plan 8.4 declares a conditional cut "
                            "(line 6) that would leave 135 cells, 45 of them public.",
        "what_this_task_does": "The rule is evaluated only when every cell of the set the protocol names has a class. "
                               "Otherwise every headline stays not_evaluated. Beside it the record gives the share of "
                               "the cells that were run and keep the class, labelled as a share of the cells run, and "
                               "the lowest and highest retention the cells not run could still give. Where those two "
                               "numbers lie on one side of the minimum the record says so and still sets no status. It "
                               "also gives the retention over the cells declared cut line 6 would leave, which is not "
                               "the headline: the cut is the owners' to invoke.",
        "for_the_owners": "Whether retention may be taken over the cells that can be run, and from how many cells on; or "
                          "whether the headline waits for the whole set; or whether cut line 6 is invoked. Also whether "
                          "a class that cannot reach the minimum whatever the missing cells give may be shown as "
                          "unstable already. And how a class of task E8 is shown until then: guardrail GR8 knows two "
                          "displays, headlined or 'unstable: verify', and no class is headline-eligible today. This "
                          "task writes no page and no overlay and sets no display.",
    },
    {
        "id": "E10-OP2",
        "point": "The 2024-rescaled demand level of the population-vintage axis.",
        "signed_files_say": "Protocol v1b ensemble_grid.core_axes[population_vintage].rescale_formula (owner choice 12): "
                            "within each 1 km cell of the WorldPop 2024 grid, every 2020 100 m count is multiplied by the "
                            "ratio of the cell's 2024 total to the sum of the 2020 counts inside the cell; a cell whose "
                            "2020 sum is zero keeps zero. The formula does not say which 1 km cell a 100 m count is "
                            "inside (floodguard.age_exposure records that the two Thai grids do not nest), nor what a "
                            "positive 2020 count becomes in a 1 km cell with no 2024 total. The owners' record may "
                            "already hold both answers: docs/proposal_execution/planning_protocol_v1b_owner_choices.md, "
                            "entry 12, recommends option A because it 'matches the plan's words and the way "
                            "`bridge_worldpop_age_access.py` already spreads 2024 counts over 2020 cells', and the "
                            "owners answered A (decision log R12). That script (scripts/bridge_worldpop_age_access.py, "
                            "allocate_cell_masses) puts a 2020 demand cell in the 1 km cell that holds its centre, "
                            "within its unit, and reports the 2020 residents whose 1 km cell has no usable 2024 count "
                            "as a figure of their own "
                            "('2020_demand_population_without_age_source_support'): they are neither set to zero nor "
                            "given a 2024 count. Protocol v1b itself does not name the script.",
        "what_this_task_does": "The level is not run and not approximated. No stage builds the rescaled demand; the "
                               "formula exists as a pure function (floodguard.age_exposure.rescale_2020_counts_to_2024) "
                               "that decides neither point. Every cell of the level is reported as not run. Whether a "
                               "2020 count of the frame lies in a 1 km cell with no 2024 total was not measured here.",
        "for_the_owners": "Whether the two rules of that script are the two rules of the rescale: the 1 km cell that "
                          "holds the centre of the 100 m cell, and a positive 2020 count with no 2024 total reported as "
                          "unsupported, neither zero nor rescaled. Confirm or reject it; or give two other rules; or "
                          "invoke declared cut line 6. The level stays not run until then. With the two rules it needs "
                          "no new access run: travel times do not depend on the vintage, the resident counts of each "
                          "cell do.",
    },
    {
        "id": "E10-OP3",
        "point": "The two facility sets that add shelters: the second and the third level of the facility axis.",
        "signed_files_say": "Protocol v1b facility_sets: both sets add DDPM located shelters, whose access is walking, "
                            "30 minutes, at the pitch level (owner choice 7). The walking context is not of record "
                            "(open point E5-OP5), and no access table exists for the subset of the shelters that the second "
                            "set keeps.",
        "what_this_task_does": "Neither set is run and neither is approximated from the candidate walking context. Every "
                               "cell of the two sets is reported as not run. A run at the public level reads the public "
                               "facility set only, as the protocol says of a public overlay.",
        "for_the_owners": "A walking build of record in a declared window (E5-OP5), then task E5 for the two shelter "
                          "sets, then a pitch-level run of this task. Declared cut line 8 would drop the second set.",
    },
    {
        "id": "E10-OP4",
        "point": "The confidence class inside an ensemble cell.",
        "signed_files_say": "Protocol v1a confidence_rule_v1: 'applies_per: unit x lane' and 'uses_ensemble_output: "
                            "false'. Protocol v1b: 'Confidence rule v1 uses no ensemble output.' The headline rule "
                            "compares the v1 class of every cell, and class rule v1 reads the confidence class. Neither "
                            "file says whether the confidence record is derived again in a cell.",
        "what_this_task_does": "Every cell carries the confidence of its unit in its lane, derived as task E8 derives "
                               "it: conditions C1 to C4 and C6 to C8 from the inputs as provided (C4 always compares the "
                               "plus and the minus level of the flood input as provided), and C5 from the components of "
                               "the cell, so a cell with a component that is not computed is low confidence and class E.",
        "for_the_owners": "Whether that is the reading. With the 2024 vintage, C4, C6 and C7 would rest on other resident "
                          "counts: whether they follow the vintage of the cell.",
    },
    {
        "id": "E10-OP5",
        "point": "What the best and worst rank of a unit are.",
        "signed_files_say": "Protocol v1b ensemble_grid.per_tambon_outputs: 'Best and worst rank.' It does not say what is "
                            "ranked, among which units, or how a tie is broken.",
        "what_this_task_does": "In each cell the units of the case are ranked by FPPS, highest first; a tie goes to the "
                               "lower unit identifier, as floodguard.sensitivity ranks and as protocol v1a breaks the tie "
                               "of the demo tambon (reading DR-A03). A cell in which a unit has no FPPS is not ranked.",
        "for_the_owners": "Whether that is the rank the protocol means.",
    },
    {
        "id": "E10-OP6",
        "point": "The axis with the largest swing.",
        "signed_files_say": "Protocol v1b ensemble_grid.per_tambon_outputs: 'The axis with the largest swing.' It does not "
                            "say what swings (the FPPS, the class or the rank) nor how the swing along an axis is "
                            "summarised over the other axes.",
        "what_this_task_does": "For each axis with two or more levels run, the FPPS range across its levels is taken "
                               "with every other axis held fixed; the largest and the mean of those ranges are "
                               "reported. No axis is named as the one with the largest swing: the record says which "
                               "axis is largest under each of the two summaries.",
        "for_the_owners": "The definition of the swing, so that one axis can be named.",
    },
    {
        "id": "E10-OP7",
        "point": "People losing 30-minute access, and the equity figures.",
        "signed_files_say": "Protocol v1b ensemble_grid.per_tambon_outputs: 'Median and range of people losing 30-minute "
                            "access' and 'Median and range of EED and EER'. The first names no service; the access-gap "
                            "threshold of the main-road entry is 15 minutes.",
        "what_this_task_does": "For each public service the residents newly losing access within 30 minutes are taken "
                               "from the access runs (hospital and main-road entry, by vehicle), with their median and "
                               "range over the combinations run. EED and EER are plan task E9 and are not computed.",
        "for_the_owners": "Which service the figure means, and whether it is counted over cells or over access runs "
                          "(each access run stands for the same number of cells, so the two agree here).",
    },
    {
        "id": "E10-OP8",
        "point": "Where the access tables of the minus and plus flood levels go.",
        "signed_files_say": "Task E5 left the minus and plus flood levels to this task. Guardrail GR6 takes the minimum "
                            "across the lineage of an output; it does not say whether an intermediate table with a "
                            "public lineage of its own is committed when the output it feeds is not.",
        "what_this_task_does": "The access runs of the two levels are written with the ensemble results of the case, "
                               "outside Git, and bound by SHA-256. The receipt holds their closure counts and "
                               "whole-frame counts, as the task E5 receipt does.",
        "for_the_owners": "Whether those tables are committed where their own lineage is public, as the task E5 table "
                          "of case SE1 is (open points E1-OP1 and E8-OP7).",
    },
    {
        "id": "E10-OP9",
        "point": "The one-at-a-time items.",
        "signed_files_say": "Protocol v1b ensemble_grid.one_at_a_time: the flood-likelihood anchors 0.10 and 0.30, class "
                            "rule v1 and v2, and the terrain proxy for case O1 only. It does not say from which cell an "
                            "item is varied.",
        "what_this_task_does": "The two flood anchors are applied to the default cell alone, every other choice held "
                               "at its default. The v2 result is that of the row of task E8, which is not evaluated "
                               "where it depends on a trigger nobody evaluated (E8-OP1). The terrain proxy is not run: "
                               "case O1 has no run.",
        "for_the_owners": "Whether one at a time means from the default cell.",
    },
    {
        "id": "E10-OP10",
        "point": "Counts for the whole case that state a value of a single unit.",
        "signed_files_say": "Guardrail GR6 takes the minimum rights level across the lineage of an overlay and speaks of "
                            "apps/web/public/ only. Nothing says whether a count that states the class of one unit in "
                            "one cell may stand in a committed receipt when the lineage is below the public level "
                            "(open points E1-OP1, E8-OP5 and E8-OP7 ask the same of other figures).",
        "what_this_task_does": "The receipt in Git holds, for each cell that was run, the number of units in each class "
                               "(result.summary.class_counts_by_cell), and names no unit beside a value. Those counts "
                               "state values of single units all the same: where every unit has one class, the class "
                               "of each; and where one unit alone holds a class in the default cell, that unit can be "
                               "followed through the cells by whoever knows which unit it is. The receipt says how "
                               "many such cells and classes it holds "
                               "(rights.figures_of_local_level_layers_in_this_receipt). Unlike the rows of task E8, "
                               "the class of a unit in a cell of the minus or plus flood level cannot be rebuilt from "
                               "committed files: the access tables of those levels are outside Git (E10-OP8). The "
                               "counts have been in the receipts since the first runs of this task and are in the Git "
                               "history.",
        "for_the_owners": "Whether such counts may stand in Git. If not, class_counts_by_cell and every sentence that "
                          "follows a single unit through the cells leave the receipt and the README of the output "
                          "folder and are kept in the file outside Git only; what is in the Git history stays there "
                          "unless the owners decide otherwise.",
    },
    {
        "id": "E10-OP11",
        "point": "The cells retention is taken over, for an output that is not a public overlay.",
        "signed_files_say": "Protocol v1b ensemble_grid.headline_rule: 'Retention is the share of the 540 core cells'. "
                            "facility_sets.shelters_in_the_ensemble: 'For a public overlay, class retention is computed "
                            "over the 180 cells of the public facility set only, and the overlay says so.' The second "
                            "sentence is written for a public overlay. The results of this task are not an overlay, and "
                            "their publication eligibility follows their lineage, which may be below the public level.",
        "what_this_task_does": "A run at the public level reads the public facility set only and takes the 180 cells of "
                               "that set as the set of the rule, whatever the publication eligibility of its results; "
                               "should every one of the 180 have a class, the rule would be evaluated over them. Beside "
                               "it every record gives the same counts and bounds over the 540 core cells "
                               "(other_reading_of_the_protocol_set). No status is set from either today.",
        "for_the_owners": "Which set applies to a result that is not a public overlay: the 180 cells of the public "
                          "facility set, because it reads that set only, or the 540 core cells, because the sentence "
                          "on the 180 cells is written for a public overlay.",
    },
    {
        "id": "E10-OP12",
        "point": "The levels declared cut line 6 would keep.",
        "signed_files_say": "Protocol v1b ensemble_grid.declared_cuts.cut_line_6 and plan 8.4: 'Population-vintage and "
                            "vulnerability-anchor axes (540 to 135 cells).' The cut names the two axes and the number "
                            "of cells that stay, not the level of each axis that stays.",
        "what_this_task_does": "The share after the cut is given with the levels of the default cell kept (WorldPop 2020 "
                               "and the P10 / P90 anchors), and the record says so. The same share is given for every "
                               "other pair of levels the cut could keep, where all of its cells were run "
                               "(other_levels_the_cut_could_keep). None of them is the headline.",
        "for_the_owners": "Which level of each of the two axes stays when the cut is invoked.",
    },
)
"""What the signed files leave open for this task. None of it is decided here."""


class EnsembleError(ValueError):
    """Raised when the protocol files do not state the grid this module runs, or the inputs break its contract."""


# ---------------------------------------------------------------------------
# The grid, read from the two protocol files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Axis:
    """One core axis: the keys this module uses for its levels, and the words protocol v1b uses for them."""

    name: str
    levels: tuple[str, ...]
    protocol_levels: tuple[str, ...]


@dataclass(frozen=True)
class EnsembleGrid:
    """The predeclared grid and the headline rule, as the two protocol files state them."""

    axes: tuple[Axis, ...]
    reference_cell: Mapping[str, str]
    reference_cell_text: str
    core_cells_per_lane: int
    routing_combinations_per_lane: int
    public_cells: int
    retention_for_public_overlays: str
    class_retention_min: float
    headline_over: str
    fallback_text: str
    weight_presets_raw: Mapping[str, Mapping[str, float]]
    one_at_a_time: tuple[str, ...]
    per_tambon_outputs: tuple[str, ...]
    declared_cuts: Mapping[str, str]
    cells_after_cut_line_6: int
    runs: str
    reporting: str
    protocol_sha256: Mapping[str, str | None]
    one_pixel_m: float
    """The distance of the minus and the plus flood level, in metres (``core_axes[0].one_pixel_m``, owner choice 2)."""

    def axis(self, name: str) -> Axis:
        """Return one axis by name."""

        return next(axis for axis in self.axes if axis.name == name)


def _match_one(stated: str, keys: Sequence[str], what: str) -> str:
    normalised = stated.lower().replace("-", "_")
    found = [key for key in keys if normalised == key or normalised.startswith(key + " ")]
    if len(found) != 1:
        raise EnsembleError(f"protocol v1b names a {what} level this module does not run: {stated!r}")
    return found[0]


def _anchor_pair(stated: str) -> tuple[str, str]:
    found = re.fullmatch(r"(?:national )?(P\d+) / (P\d+)", stated.strip())
    if found is None:
        raise EnsembleError(f"protocol v1b names a pair of vulnerability anchors this module does not read: {stated!r}")
    return found.group(1), found.group(2)


def grid_from_protocols(v1a: Mapping[str, Any], v1b: Mapping[str, Any],
                        hashes: Mapping[str, str | None] | None = None) -> EnsembleGrid:
    """Read the grid and the headline rule from the parsed protocols and check them against what this module runs.

    A grid read this way carries no protocol hash unless ``hashes`` gives one: a grid that computes for a real
    unit comes from :func:`load_grid`, which reads the files in force.

    Raises:
        EnsembleError: when the files state other axes, levels, counts or rule parameters than the ones this
            module implements, or the two files disagree.
    """

    try:
        return _grid(v1a, v1b, dict(hashes or {"v1a": None, "v1b": None}))
    except EnsembleError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration) as error:
        raise EnsembleError(f"the protocol files do not hold the ensemble grid this module reads: {error!r}") from error


def _grid(v1a: Mapping[str, Any], v1b: Mapping[str, Any], hashes: dict[str, str | None]) -> EnsembleGrid:
    section = v1b["ensemble_grid"]
    if section["status"] != "fixed":
        raise EnsembleError("the ensemble grid is not fixed in protocol v1b")
    stated = {str(axis["axis"]): axis for axis in section["core_axes"]}
    if tuple(stated) != AXES:
        raise EnsembleError(f"protocol v1b lists the core axes {list(stated)}; this module runs {list(AXES)}")
    frame = v1a["scoring_frame"]
    words = {name: tuple(str(level) for level in stated[name]["levels"]) for name in AXES}

    flood = tuple(_match_one(level, flood_inputs.LEVELS, "flood") for level in words[FLOOD_AXIS])
    one_pixel_m = _one_pixel_m(stated[FLOOD_AXIS], words[FLOOD_AXIS])
    passability = tuple(_match_one(level, closure_rules.LEVELS, "passability") for level in words[PASSABILITY_AXIS])
    for level, text in zip(passability, words[PASSABILITY_AXIS]):
        factor = re.search(r"\(k = (\d+)\)", text)
        declared = int(v1b["closure_rule_v1"]["levels"][level]["delay_factor_k"])
        if factor is None or int(factor.group(1)) != declared or declared != closure_rules.DELAY_FACTOR_K[level]:
            raise EnsembleError(f"the delay factor of the {level} level is not the one closure rule v1 states")
    facilities = words[FACILITIES_AXIS]
    if list(facilities) != [str(item["id"]) for item in v1b["facility_sets"]["sets"]] or facilities[0] != PUBLIC_LEVEL:
        raise EnsembleError("the facility levels of the grid are not the facility sets of protocol v1b, public first")
    if any(level not in VINTAGE_KEYS for level in words[VINTAGE_AXIS]):
        raise EnsembleError(f"protocol v1b names a population vintage this module does not know: {words[VINTAGE_AXIS]}")
    vintage = tuple(VINTAGE_KEYS[level] for level in words[VINTAGE_AXIS])
    pairs = [_anchor_pair(level) for level in words[ANCHORS_AXIS]]
    vulnerability = frame["components"][VULNERABILITY]
    default_pair = (str(vulnerability["lower_anchor"]).removeprefix("national_"),
                    str(vulnerability["upper_anchor"]).removeprefix("national_"))
    sensitivity_pair = (str(vulnerability["anchor_sensitivity"]["lower"]).removeprefix("national_"),
                        str(vulnerability["anchor_sensitivity"]["upper"]).removeprefix("national_"))
    if pairs != [default_pair, sensitivity_pair]:
        raise EnsembleError("the anchor levels of the grid are not the anchors and the anchor sensitivity of protocol v1a")
    anchors = tuple(f"{lower}_{upper}" for lower, upper in pairs)
    presets = {str(name): {component: float(values[component]) for component in SCORE_COMPONENTS}
               for name, values in frame["weight_presets"]["raw_values_before_normalisation"].items()}
    weights = words[WEIGHTS_AXIS]
    if set(weights) != set(presets) or len(weights) != len(presets):
        raise EnsembleError("the weight levels of the grid are not the weight presets of protocol v1a")
    if presets != {name: dict(values) for name, values in sensitivity.WEIGHT_SCENARIOS.items()}:
        raise EnsembleError("the weight presets of protocol v1a are not those of floodguard.sensitivity, which v1a names")
    if presets["default"] != {component: float(frame["weights"][component]) for component in SCORE_COMPONENTS}:
        raise EnsembleError("the default weight preset is not the weights of the scoring frame")

    levels = {FLOOD_AXIS: flood, PASSABILITY_AXIS: passability, FACILITIES_AXIS: facilities, VINTAGE_AXIS: vintage,
              ANCHORS_AXIS: anchors, WEIGHTS_AXIS: weights}
    axes = tuple(Axis(name, tuple(levels[name]), words[name]) for name in AXES)
    for axis in axes:
        if len(set(axis.levels)) != len(axis.levels) or len(axis.levels) != int(stated[axis.name]["count"]):
            raise EnsembleError(f"axis {axis.name} does not have the number of distinct levels protocol v1b counts")
    core = math.prod(len(axis.levels) for axis in axes)
    routing = math.prod(len(levels[name]) for name in ROUTING_AXES)
    if core != int(section["core_cells_per_lane"]) or routing != int(section["routing_combinations_per_lane"]):
        raise EnsembleError("the axes do not multiply to the cells and the routing combinations protocol v1b counts")

    rule = section["headline_rule"]
    guardrail = next(item for item in v1a["guardrails"] if item["id"] == GUARDRAIL_GR8)
    minimum = float(rule["class_retention_min"])
    if minimum != float(guardrail["parameters"]["class_retention_min"]) or rule["fallback_text"] != guardrail["fallback_text"]:
        raise EnsembleError("protocol v1a guardrail GR8 and the headline rule of protocol v1b state other parameters")
    if not 0 < minimum <= 1:
        raise EnsembleError("the retention minimum must lie above 0 and at most at 1")
    reference_text = str(rule["reference_cell"])
    if f"share of the {core} core cells" not in reference_text or "v1 class" not in reference_text:
        raise EnsembleError("protocol v1b does not state retention as this module computes it")
    reference = _reference_cell(reference_text, axes)
    public_text = str(v1b["facility_sets"]["shelters_in_the_ensemble"]["retention_for_public_overlays"])
    counted = re.search(r"over the (\d+) cells of the public facility set only", public_text)
    public_cells = core // len(facilities)
    if counted is None or int(counted.group(1)) != public_cells:
        raise EnsembleError("protocol v1b does not count the cells of the public facility set as the axes give them")
    cuts = {str(key): str(value) for key, value in section["declared_cuts"].items()}
    cut = re.search(r"\((\d+) to (\d+) cells\)", cuts["cut_line_6"])
    after_cut = core // (len(vintage) * len(anchors))
    if cut is None or (int(cut.group(1)), int(cut.group(2))) != (core, after_cut) or "Population-vintage" not in cuts["cut_line_6"]:
        raise EnsembleError("declared cut line 6 is not the cut of the population-vintage and anchor axes this module reads")
    return EnsembleGrid(
        axes=axes, reference_cell=reference, reference_cell_text=reference_text, core_cells_per_lane=core,
        routing_combinations_per_lane=routing, public_cells=public_cells, retention_for_public_overlays=public_text,
        class_retention_min=minimum, headline_over=str(rule["over"]), fallback_text=str(rule["fallback_text"]),
        weight_presets_raw=presets, one_at_a_time=tuple(str(item) for item in section["one_at_a_time"]),
        per_tambon_outputs=tuple(str(item) for item in section["per_tambon_outputs"]), declared_cuts=cuts,
        cells_after_cut_line_6=after_cut, runs=str(section["runs"]), reporting=str(section["reporting"]),
        protocol_sha256=dict(hashes), one_pixel_m=one_pixel_m,
    )


def _one_pixel_m(axis: Mapping[str, Any], words: Sequence[str]) -> float:
    """Read the distance of the minus and the plus flood level from protocol v1b: one number for both.

    ``one_pixel_m`` gives the distance for the minus level, the plus level and vector products (owner choice 2).
    Where the words of a level name a distance in metres, it must be that number, so a receipt of this task
    never states a distance the protocol does not.
    """

    pixel = axis["one_pixel_m"]
    distances = {float(pixel[key]) for key in ("minus", "plus", "vector_products")}
    if len(distances) != 1 or not next(iter(distances)) > 0:
        raise EnsembleError("protocol v1b does not give one positive one-pixel distance for the minus and the plus level")
    distance = next(iter(distances))
    for text in words:
        named = re.search(r"(\d+(?:\.\d+)?) m(?![A-Za-z])", text)
        if named is not None and float(named.group(1)) != distance:
            raise EnsembleError(f"the flood level {text!r} names another one-pixel distance than one_pixel_m ({distance:g} m)")
    return distance


def _reference_cell(text: str, axes: Sequence[Axis]) -> dict[str, str]:
    """Read the default cell from the sentence of protocol v1b that names it, one level for each axis."""

    listed = text.split("default cell:", 1)
    parts = [part.strip() for part in listed[1].rstrip(". ").split(",")] if len(listed) == 2 else []
    suffixes = (" flood state", " passability", " facilities", "", " anchors", " weights")
    if len(parts) != len(axes):
        raise EnsembleError("protocol v1b does not name the default cell with one level for each axis")
    cell: dict[str, str] = {}
    for axis, part, suffix in zip(axes, parts, suffixes):
        if not part.endswith(suffix):
            raise EnsembleError(f"the default cell does not name its {axis.name} level in the words this module reads")
        name = part[:len(part) - len(suffix)] if suffix else part
        found = [key for key, words in zip(axis.levels, axis.protocol_levels)
                 if words == name or words.startswith(name + " ") or words.endswith(" " + name) or key == name]
        if len(found) != 1:
            raise EnsembleError(f"the default cell names no single {axis.name} level: {part!r}")
        cell[axis.name] = found[0]
    return cell


def load_grid(v1a_path: Path | str, v1b_path: Path | str, receipts_path: Path | str) -> EnsembleGrid:
    """Read the grid from the two protocol files, which must both be in force (guardrail GR5).

    Raises:
        floodguard.normalisation.NormalisationError: when a file is not in force.
        EnsembleError: see :func:`grid_from_protocols`; also when v1b names another v1a.
    """

    v1a, v1a_sha256 = read_protocol_in_force("v1a", v1a_path, receipts_path)
    v1b, v1b_sha256 = read_protocol_in_force("v1b", v1b_path, receipts_path)
    if v1b.get("depends_on", {}).get("v1a_sha256") != v1a_sha256:
        raise EnsembleError("protocol v1b does not name the v1a file that was read")
    return grid_from_protocols(v1a, v1b, {"v1a": v1a_sha256, "v1b": v1b_sha256})


def grid_record(grid: EnsembleGrid) -> dict[str, Any]:
    """Return the grid as plain JSON values, for a receipt: every axis with every level, and the rule."""

    return {
        "source": "planning_protocol_v1b.json /ensemble_grid; the weight presets from planning_protocol_v1a.json "
                  "/scoring_frame/weight_presets; the retention minimum also from v1a guardrail GR8",
        "axes": [{"axis": axis.name, "levels": list(axis.levels), "levels_as_protocol_v1b_states_them": list(axis.protocol_levels),
                  "count": len(axis.levels)} for axis in grid.axes],
        "one_pixel_m": grid.one_pixel_m,
        "core_cells_per_lane": grid.core_cells_per_lane,
        "routing_combinations_per_lane": grid.routing_combinations_per_lane,
        "cells_of_the_public_facility_set": grid.public_cells,
        "runs": grid.runs,
        "reference_cell": dict(grid.reference_cell),
        "reference_cell_as_protocol_v1b_states_it": grid.reference_cell_text,
        "weight_presets_raw_values_before_normalisation": {name: dict(values) for name, values in grid.weight_presets_raw.items()},
        "headline_rule": {"class_retention_min": grid.class_retention_min, "over": grid.headline_over,
                          "fallback_text": grid.fallback_text,
                          "retention_for_public_overlays": grid.retention_for_public_overlays},
        "one_at_a_time": list(grid.one_at_a_time),
        "per_tambon_outputs": list(grid.per_tambon_outputs),
        "declared_cuts": dict(grid.declared_cuts),
        "reporting": grid.reporting,
    }


def cells(grid: EnsembleGrid) -> list[dict[str, str]]:
    """Return every core cell of the grid, one level for each axis, in the order of the axes."""

    return [dict(zip(AXES, combination)) for combination in itertools.product(*(axis.levels for axis in grid.axes))]


def cell_id(cell: Mapping[str, str]) -> str:
    """Name a cell by its six levels, in the order of the axes."""

    return "|".join(cell[name] for name in AXES)


def routing_key(cell: Mapping[str, str]) -> RoutingKey:
    """Return the levels of a cell that decide what is measured of a unit."""

    return (cell[FLOOD_AXIS], cell[PASSABILITY_AXIS], cell[FACILITIES_AXIS], cell[VINTAGE_AXIS])


def routing_keys(grid: EnsembleGrid) -> list[RoutingKey]:
    """Return every combination of flood level, passability, facility set and population vintage of the grid."""

    return [key for key in itertools.product(*(grid.axis(name).levels for name in MEASUREMENT_AXES))]


def scope_cell_ids(grid: EnsembleGrid, level: str) -> list[str]:
    """Return the cells class retention is taken over at one level: all 540, or the public facility set alone.

    Protocol v1b: retention is the share of the core cells; for a public overlay it "is computed over the 180
    cells of the public facility set only". A run at the public level reads that facility set only and takes
    its cells, whether or not its results are a public overlay; the protocol does not say which set applies
    then (open point E10-OP11), and :func:`run_ensemble` reports the other reading beside it.
    """

    if level not in (PUBLIC_LEVEL, PITCH_LEVEL):
        raise EnsembleError(f"the level of a run is {PUBLIC_LEVEL} or {PITCH_LEVEL}")
    listed = [cell for cell in cells(grid) if level == PITCH_LEVEL or cell[FACILITIES_AXIS] == PUBLIC_LEVEL]
    if level == PUBLIC_LEVEL and len(listed) != grid.public_cells:
        raise EnsembleError("the public facility set does not hold the cells protocol v1b counts")
    return [cell_id(cell) for cell in listed]


# ---------------------------------------------------------------------------
# What is run, what is not, and what failed
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LevelNotRun:
    """A level of an axis that cannot be run today, with the reason. Its cells are reported, never approximated."""

    axis: str
    level: str
    code: str
    reason: str
    open_points: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        """Return the reason as plain JSON values."""

        return {"axis": self.axis, "level": self.level, "code": self.code, "reason": self.reason,
                "open_points": list(self.open_points)}


@dataclass(frozen=True)
class MeasurementFailure:
    """A set of measurements that was attempted and failed: the stage, the kind of error and its message."""

    stage: str
    error: str
    message: str


def cell_table(grid: EnsembleGrid, measured: Collection[RoutingKey], not_run: Sequence[LevelNotRun]) -> list[dict[str, Any]]:
    """Say of every core cell whether it is run, and if not, why: every cell of the lane is reported.

    Args:
        grid: The grid of the protocols.
        measured: The measurement combinations the caller supplies (run or attempted).
        not_run: The levels that cannot be run, each with its reason.

    Returns:
        One entry per cell, in the order of :func:`cells`: its identifier, its six levels, ``status`` and,
        for a cell that is not run, the code of every level that stops it.

    Raises:
        EnsembleError: for a level or a combination that is not of the grid, a cell that is neither measured
            nor reported as not run, or a cell that is both.
    """

    known = set(routing_keys(grid))
    unknown = sorted(set(measured) - known)
    if unknown:
        raise EnsembleError(f"measurements were supplied for combinations that are not of the grid: {unknown}")
    by_level: dict[tuple[str, str], LevelNotRun] = {}
    for item in not_run:
        if item.axis not in AXES or item.level not in grid.axis(item.axis).levels:
            raise EnsembleError(f"{item.axis}={item.level} is not a level of the grid")
        if (item.axis, item.level) in by_level:
            raise EnsembleError(f"{item.axis}={item.level} is reported as not run twice")
        by_level[(item.axis, item.level)] = item
    table: list[dict[str, Any]] = []
    for cell in cells(grid):
        reasons = [by_level[(name, cell[name])].code for name in AXES if (name, cell[name]) in by_level]
        supplied = routing_key(cell) in measured
        if supplied and reasons:
            raise EnsembleError(f"cell {cell_id(cell)} is measured and reported as not run ({reasons})")
        if not supplied and not reasons:
            raise EnsembleError(f"cell {cell_id(cell)} is neither run nor reported as not run: every cell is reported")
        table.append({"cell_id": cell_id(cell), **cell, "status": STATUS_RUN if supplied else STATUS_NOT_RUN,
                      "not_run_because": reasons})
    return table


def cell_measurements(
    unit: planning_assessment.UnitMeasurements,
    *,
    flooded_non_permanent_water_land_area: float,
    residents_inside_flood_extent: float,
    access_gap_inputs: Mapping[str, Mapping[str, Any]],
    residents_losing_all_routes: float,
    residents_with_baseline_route: float,
) -> planning_assessment.UnitMeasurements:
    """Return the measurements of a unit for one combination of flood level, passability and facility set.

    ``unit`` is the unit as task E8 measures it. The flood input of the cell takes the place of the flood
    input as provided in the two measurements the components read (the flooded land and the residents inside
    the extent), and the access counts are those of the access run of the combination. The plus and minus
    counts that confidence condition C4 compares are left as they are: confidence rule v1 applies per unit
    and lane and uses no ensemble output (open point E10-OP4).
    """

    inside = {**unit.residents_inside_flood_extent, flood_inputs.AS_PROVIDED: float(residents_inside_flood_extent)}
    return replace(
        unit, flooded_non_permanent_water_land_area=float(flooded_non_permanent_water_land_area),
        residents_inside_flood_extent=inside,
        access_gap_inputs={service: dict(counts) for service, counts in access_gap_inputs.items()},
        residents_losing_all_routes=float(residents_losing_all_routes),
        residents_with_baseline_route=float(residents_with_baseline_route))


# ---------------------------------------------------------------------------
# Retention and the headline rule
# ---------------------------------------------------------------------------


def _at_least(kept: int, total: int, minimum: float) -> bool:
    """Compare a share of whole cells with the minimum exactly: 108 of 180 is 0.6, with no binary rounding."""

    return Fraction(kept, total) >= Fraction(str(minimum))


def protocol_set_reading(grid: EnsembleGrid, *, kept: int, with_a_class: int, cells: int, over: str) -> dict[str, Any]:
    """Return what one reading of the protocol's set gives: its retention, or the bounds the missing cells leave.

    With every cell of the set classed, ``class_retention`` is the share that keeps the class of the default
    cell. Otherwise it is null and ``bounds`` gives the lowest and the highest retention the cells without a
    class could still give; ``outcome_fixed_by_the_bounds`` says on which side of the minimum both lie, if they
    lie on one. No headline status is read from this record.

    Raises:
        EnsembleError: for counts that cannot be.
    """

    if not 0 <= kept <= with_a_class <= cells or cells <= 0:
        raise EnsembleError("retention counts whole cells: kept <= cells with a class <= cells of the protocol's set")
    missing = cells - with_a_class
    minimum = grid.class_retention_min
    lower_at_least, upper_at_least = _at_least(kept, cells, minimum), _at_least(kept + missing, cells, minimum)
    return {
        "over": over,
        "cells": cells,
        "cells_with_a_class": with_a_class,
        "cells_keeping_the_reference_class": kept,
        "class_retention": None if missing else kept / cells,
        "at_or_above_the_minimum": None if missing else lower_at_least,
        "bounds": None if not missing else {"lower": kept / cells, "upper": (kept + missing) / cells,
                                           "cells_without_a_class": missing},
        "outcome_fixed_by_the_bounds": None if not missing else (
            BOUNDS_AT_OR_ABOVE if lower_at_least else (None if upper_at_least else BOUNDS_BELOW)),
    }


def cut_line_6_record(grid: EnsembleGrid, *, reference_class: str | None, classed: Mapping[str, str],
                      cells_of_the_set: Sequence[Mapping[str, str]]) -> dict[str, Any] | None:
    """Return the share of cells keeping the class over the cells declared cut line 6 would leave.

    Protocol v1b ``declared_cuts.cut_line_6`` (plan 8.4) cuts the population-vintage and the vulnerability-anchor
    axis and does not say which level of each stays (open point E10-OP12). The record gives the share with the
    levels of the default cell kept and, under ``other_levels_the_cut_could_keep``, the same share for every
    other pair of levels. A pair whose cells do not all have a class has no share. None of them is the headline:
    the cut is conditional and the owners have not invoked it.

    Args:
        grid: The grid of the protocols.
        reference_class: The v1 class of the unit in the default cell, or ``None``.
        classed: ``cell identifier -> v1 class`` for the cells of the protocol's set that have a class.
        cells_of_the_set: The cells of the protocol's set, each with its six levels.

    Returns:
        The record, or ``None`` for a unit with no class in the default cell.

    Raises:
        EnsembleError: when a pair of levels does not hold the cells the cut would leave.
    """

    if reference_class is None:
        return None
    default = (grid.reference_cell[VINTAGE_AXIS], grid.reference_cell[ANCHORS_AXIS])
    pairs = list(itertools.product(grid.axis(VINTAGE_AXIS).levels, grid.axis(ANCHORS_AXIS).levels))
    expected = len(cells_of_the_set) // len(pairs)
    options: dict[tuple[str, str], dict[str, Any]] = {}
    for vintage, anchors in pairs:
        identifiers = [cell_id(cell) for cell in cells_of_the_set if (cell[VINTAGE_AXIS], cell[ANCHORS_AXIS]) == (vintage, anchors)]
        if len(identifiers) != expected or not expected:
            raise EnsembleError("declared cut line 6 does not leave the same cells for every pair of levels it could keep")
        found = [classed[identifier] for identifier in identifiers if identifier in classed]
        whole = len(found) == len(identifiers)
        kept = sum(1 for value in found if value == reference_class)
        options[(vintage, anchors)] = {
            "levels_kept": {VINTAGE_AXIS: vintage, ANCHORS_AXIS: anchors},
            "cells": len(identifiers),
            "cells_with_a_class": len(found),
            "cells_keeping_the_reference_class": kept if whole else None,
            "retention": kept / len(identifiers) if whole else None,
            "at_or_above_the_minimum": _at_least(kept, len(identifiers), grid.class_retention_min) if whole else None,
        }
    return {
        **options[default],
        "levels_kept_are": "the levels of the default cell",
        "other_levels_the_cut_could_keep": [options[pair] for pair in pairs if pair != default],
        "note": "The share over the cells that declared cut line 6 of plan 8.4 would leave. It is not the headline: the "
                "cut is conditional and the owners have not invoked it (open point E10-OP1). The cut names the two axes "
                "it drops and not the level of each that stays: the figures here keep the levels of the default cell, "
                "and other_levels_the_cut_could_keep gives the same share for every other pair of levels. A pair whose "
                "cells do not all have a class has no share (open point E10-OP12).",
    }


def headline_record(
    grid: EnsembleGrid,
    *,
    reference_class: str | None,
    kept: int,
    with_a_class: int,
    protocol_cells: int,
    over: str,
    cells_run: int | None = None,
    after_declared_cut_line_6: Mapping[str, Any] | None = None,
    other_reading: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply the headline-stability rule to one unit (protocol v1a guardrail GR8; protocol v1b ``headline_rule``).

    Retention is the share of the cells the protocol names whose v1 class equals the class of the default
    cell. With every one of those cells classed, a retention at or above the minimum makes the class
    ``headline_eligible`` and anything lower ``unstable_verify``, with the fallback text of the protocol.

    With fewer cells classed the rule is not evaluated (open point E10-OP1): ``class_retention`` is null and
    the status is ``not_evaluated``. The record then gives the share over the cells that were run, which is
    not the retention of the protocol, and the lowest and highest retention the missing cells could still
    give. Where both lie on one side of the minimum, ``outcome_fixed_by_the_bounds`` says which; the status is
    not set from it.

    A cell that was run and has no class (it failed) stays in the denominator of
    ``retention_over_the_cells_run``: that share is taken over ``cells_run``, never over the cells with a
    class alone. For the bounds such a cell is a cell without a class, like a cell that was not run.

    Args:
        grid: The grid of the protocols.
        reference_class: The v1 class of the unit in the default cell, or ``None`` when it has none.
        kept: The cells of the protocol's set whose class equals it.
        with_a_class: The cells of the protocol's set that have a class.
        protocol_cells: The size of the protocol's set (540, or 180 for a run at the public level).
        over: The protocol's set, in words.
        cells_run: The cells of the protocol's set that were run, failed cells included; ``with_a_class``
            when it is not given.
        after_declared_cut_line_6: The record of :func:`cut_line_6_record`; reported beside the record and
            never as the headline.
        other_reading: The record of :func:`protocol_set_reading` for the other set the protocol could mean
            (open point E10-OP11); reported beside the record, and no status is set from it.

    Raises:
        EnsembleError: for counts that cannot be: negative, more kept than classed, more classed than run, more
            run than the set.
    """

    run = with_a_class if cells_run is None else cells_run
    if not 0 <= kept <= with_a_class <= run <= protocol_cells or protocol_cells <= 0:
        raise EnsembleError("retention counts whole cells: kept <= cells with a class <= cells run <= cells of the protocol's set")
    record: dict[str, Any] = {
        "guardrail": GUARDRAIL_GR8,
        "status": HEADLINE_NOT_EVALUATED,
        "class_retention": None,
        "class_retention_min": grid.class_retention_min,
        "reference_class": reference_class,
        "over": over,
        "cells_of_the_protocol_set": protocol_cells,
        "cells_run": run,
        "cells_with_a_class": with_a_class,
        "cells_run_without_a_class": run - with_a_class,
        "cells_keeping_the_reference_class": kept,
        "retention_over_the_cells_run": None,
        "bounds_over_the_protocol_set": None,
        "outcome_fixed_by_the_bounds": None,
        "not_evaluated_because": None,
        "fallback_text": None,
        "after_declared_cut_line_6": None,
        "other_reading_of_the_protocol_set": None if other_reading is None else {
            **other_reading,
            "note": "Protocol v1b states the cells of the public facility set 'for a public overlay'. Which set is the "
                    "set of the rule for a result that is not a public overlay is open point E10-OP11. No status is set "
                    "from this reading."},
    }
    if reference_class is None:
        record["not_evaluated_because"] = ("The unit has no binding class in the default cell (guardrail GR1, or the "
                                           "default cell has no result), so no class can be retained.")
        return record
    if run:
        record["retention_over_the_cells_run"] = kept / run
    if after_declared_cut_line_6 is not None:
        record["after_declared_cut_line_6"] = dict(after_declared_cut_line_6)
    reading = protocol_set_reading(grid, kept=kept, with_a_class=with_a_class, cells=protocol_cells, over=over)
    if reading["class_retention"] is not None:
        stable = bool(reading["at_or_above_the_minimum"])
        record.update({"status": HEADLINE_ELIGIBLE if stable else HEADLINE_UNSTABLE, "class_retention": reading["class_retention"],
                       "fallback_text": None if stable else grid.fallback_text})
        return record
    missing = protocol_cells - with_a_class
    record.update({
        "bounds_over_the_protocol_set": reading["bounds"],
        "outcome_fixed_by_the_bounds": reading["outcome_fixed_by_the_bounds"],
        "not_evaluated_because": (
            f"{missing} of the {protocol_cells} cells the protocol takes retention over have no class: they were not "
            "run, or failed. The protocols state no retention over a part of those cells (open point E10-OP1). "
            "retention_over_the_cells_run is a share of the cells that were run, failed cells included in the "
            "denominator, and is not the retention of the headline rule."),
    })
    return record


# ---------------------------------------------------------------------------
# One unit over the cells
# ---------------------------------------------------------------------------


def preset_header(header: Mapping[str, Any], raw_weights: Mapping[str, float]) -> dict[str, Any]:
    """Return the scoring-frame header with one weight preset in the place of the default weights.

    Protocol v1a: "Non-default presets are normalised to sum to 1 by the scorer." The weights are normalised by
    ``scoring.validate_weights`` and the leave-one-component-out weights follow from them (reading DR-A02).
    """

    return {**header, "weights": validate_weights(raw_weights),
            "leave_one_component_out_weights": leave_one_component_out_weights(raw_weights)}


def _component_values(row: Mapping[str, Any], anchors_level: str, grid: EnsembleGrid) -> dict[str, float | None]:
    """The five component values of a row under one pair of vulnerability anchors."""

    components = row["components"]
    values: dict[str, float | None] = {
        name: None if components[name] is None else float(components[name]["value_0_100"]) for name in SCORE_COMPONENTS}
    default_level, sensitivity_level = grid.axis(ANCHORS_AXIS).levels
    record = components[VULNERABILITY]
    if record is not None:
        if f"{record['anchors']['lower']}_{record['anchors']['upper']}" != default_level or (
                f"{record['anchor_sensitivity']['lower']}_{record['anchor_sensitivity']['upper']}" != sensitivity_level):
            raise EnsembleError("the vulnerability record does not carry the two pairs of anchors of the grid")
        if anchors_level == sensitivity_level:
            values[VULNERABILITY] = float(record["anchor_sensitivity"]["value_0_100"])
    return values


def _score(row: Mapping[str, Any], values: Mapping[str, float | None], header: Mapping[str, Any]) -> dict[str, Any]:
    """FPPS, v1 class, reason code and leave-one-component-out of one cell, through the scoring block of task E8."""

    confidence = row["confidence"]
    low_by_c5 = any(values[name] is None for name in SCORE_COMPONENTS)
    block = planning_assessment.scoring_block(
        values, "low" if low_by_c5 else str(confidence["confidence_class"]), bool(confidence["guardrail_gr1"]["applies"]), header)
    return {
        "fpps_0_100": block["fpps_0_100"],
        "action_class": block["action_class"],
        "action_reason_code": block["action_reason_code"],
        "would_be_class": block["would_be_class"],
        "leave_one_component_out": block["leave_one_component_out"],
        "components_not_computed": [name for name in SCORE_COMPONENTS if values[name] is None],
    }


def _spread(values: Sequence[float]) -> dict[str, Any] | None:
    """Minimum, median and maximum of a list of numbers, with how many there are; None for an empty list."""

    if not values:
        return None
    return {"min": min(values), "median": statistics.median(values), "max": max(values), "count": len(values)}


def _class_key(action_class: str | None) -> str:
    return NO_CLASS if action_class is None else str(action_class)


def _class_counts(classes: Sequence[str | None]) -> dict[str, int]:
    counted = Counter(_class_key(item) for item in classes)
    unknown = sorted(set(counted) - set(CLASS_KEYS))
    if unknown:
        raise EnsembleError(f"class rule v1 gave a class this module does not count: {unknown}")
    return {key: counted.get(key, 0) for key in CLASS_KEYS}


def axis_swings(grid: EnsembleGrid, fpps_by_cell: Mapping[str, float], cell_levels: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Measure, for each axis, how far the FPPS of one unit moves across its levels with every other axis held fixed.

    For an axis with two or more levels among the cells, the cells are grouped by the levels of the five
    other axes; the swing of a group is its highest FPPS minus its lowest. The largest and the mean of the
    group swings are returned. Protocol v1b names "the axis with the largest swing" and does not define the
    swing (open point E10-OP6), so no axis is named as that one: the record says which axis is largest under
    each of the two summaries.
    """

    by_axis: dict[str, Any] = {}
    for axis in AXES:
        groups: dict[tuple[str, ...], list[float]] = {}
        levels_run: set[str] = set()
        for identifier, fpps in fpps_by_cell.items():
            levels = cell_levels[identifier]
            levels_run.add(levels[axis])
            groups.setdefault(tuple(levels[other] for other in AXES if other != axis), []).append(fpps)
        swings = [max(values) - min(values) for values in groups.values() if len(values) >= 2]
        if len(levels_run) < 2 or not swings:
            by_axis[axis] = {"levels_run": sorted(levels_run), "measured": False,
                             "note": "Fewer than two levels of this axis were run, so no swing along it is measured."}
        else:
            by_axis[axis] = {"levels_run": sorted(levels_run), "measured": True, "groups": len(swings),
                             "largest_fpps_swing": max(swings), "mean_fpps_swing": math.fsum(swings) / len(swings)}
    measured = {axis: record for axis, record in by_axis.items() if record["measured"]}

    def largest(key: str) -> str | None:
        if not measured:
            return None
        return max(AXES, key=lambda axis: (measured[axis][key] if axis in measured else -1.0, -AXES.index(axis)))

    return {
        "by_axis": by_axis,
        "axis_with_the_largest_swing": None,
        "axis_with_the_largest_swing_status": "not_stated: protocol v1b does not define the swing (open point E10-OP6)",
        "largest_by_the_largest_fpps_swing": largest("largest_fpps_swing"),
        "largest_by_the_mean_fpps_swing": largest("mean_fpps_swing"),
        "what": "FPPS points across the levels of an axis, every other axis held fixed, over the cells with an FPPS.",
    }


def _one_at_a_time(row: Mapping[str, Any] | None, header: Mapping[str, Any], grid: EnsembleGrid) -> dict[str, Any]:
    """The one-at-a-time items of protocol v1b for one unit, each varied from the default cell alone."""

    block: dict[str, Any] = {"varied_from": "the default cell, every other choice at its default (open point E10-OP9)",
                             "as_protocol_v1b_lists_them": list(grid.one_at_a_time)}
    if row is None:
        return {**block, "status": "not_computed: the default cell has no result"}
    anchors = []
    record = row["components"][FLOOD_LIKELIHOOD]
    if record is not None:
        for item in record["anchor_sensitivity_one_at_a_time"]:
            values = _component_values(row, grid.reference_cell[ANCHORS_AXIS], grid)
            values[FLOOD_LIKELIHOOD] = float(item["value_0_100"])
            scored = _score(row, values, header)
            anchors.append({"flood_anchor": item["anchor"], "flood_likelihood_0_100": float(item["value_0_100"]),
                            "fpps_0_100": scored["fpps_0_100"], "action_class": scored["action_class"],
                            "action_reason_code": scored["action_reason_code"]})
    v2 = row["class_v2"]
    # Overlay schema 1.1 writes a v2 result that depends on a trigger nobody evaluated as "not_evaluated". Here it
    # stays what this table has always said for such a row: no result, with the status beside it.
    v2_stated = v2 is not None and v2["result"] != V2_NOT_EVALUATED
    return {
        **block,
        "flood_likelihood_anchor": anchors,
        "class_rule_v1_and_v2": {
            "v1_class": row["action_class"],
            "v2_result": v2["result"] if v2_stated else None,
            "v2_status": None if v2 is None else ("evaluated" if v2_stated else V2_NOT_EVALUATED),
            "note": "Class rule v2 is a secondary axis and is never binding. Its result is that of the row of task E8; "
                    "a result that depends on a trigger nobody evaluated is not stated (open point E8-OP1).",
        },
        "terrain_remoteness_proxy": {"status": "not_run", "reason": "Protocol v1b runs the proxy on case O1 only, and "
                                                                    "case O1 has no run (open point E1-OP2)."},
    }


def run_ensemble(
    grid: EnsembleGrid,
    rules: planning_assessment.AssessmentRules,
    case: planning_assessment.CaseSpec,
    flood: planning_assessment.FloodInputSpec,
    measurements: Mapping[RoutingKey, Sequence[planning_assessment.UnitMeasurements] | MeasurementFailure],
    *,
    routing_context_id: str,
    level: str = PUBLIC_LEVEL,
    not_run: Sequence[LevelNotRun] = (),
    people_losing_access: Mapping[RoutingKey, Mapping[str, Mapping[str, float]]] | None = None,
) -> dict[str, Any]:
    """Run the ensemble of one case over every cell that has measurements, and report every cell of the lane.

    For each combination of flood level, passability, facility set and population vintage the caller supplies
    the measurements of every unit (:func:`cell_measurements`), or the failure of the stage that should have
    produced them. Each unit of a combination is assessed as task E8 assesses a row; each cell of the
    combination then takes its FPPS, class and leave-one-component-out from the scoring block under the
    anchors and the weight preset of the cell.

    Args:
        grid: The grid of the protocols in force (:func:`load_grid`).
        rules: The assessment rules of the same protocol files.
        case, flood: The case and its one flood input, as task E8 states them.
        measurements: ``(flood level, passability, facility set, population vintage) -> measurements of every
            unit``, or a :class:`MeasurementFailure`.
        routing_context_id: The one routing context of every cell.
        level: ``public`` (the public facility set only, as protocol v1b says of a public overlay) or ``pitch``.
        not_run: The levels that cannot be run, each with its reason. A cell with neither measurements nor a
            reason is refused.
        people_losing_access: ``combination -> unit -> service -> residents newly losing access within 30
            minutes``, from the access runs.

    Returns:
        ``grid`` (the grid as the protocols state it), ``cells`` (every core cell with its status), ``units``
        (one record per unit, with every cell that was run) and ``summary`` (counts for the whole case).

    Raises:
        EnsembleError: when the grid and the rules come from other protocol files, a cell is neither run nor
            reported, the combinations do not hold the same units, or a public run is given another facility set.
    """

    frame = rules.binding.frame
    if dict(grid.protocol_sha256) != dict(frame.protocol_sha256) or not all(grid.protocol_sha256.values()):
        raise EnsembleError("the grid and the assessment rules must come from the same two protocol files in force")
    if rules.reference_closure_level != grid.reference_cell[PASSABILITY_AXIS]:
        raise EnsembleError("the default cell of the grid and the row of task E8 name another passability level")
    if level == PUBLIC_LEVEL and any(key[2] != PUBLIC_LEVEL for key in measurements):
        raise EnsembleError("a run at the public level reads the public facility set only (protocol v1b facility_sets)")
    table = cell_table(grid, set(measurements), not_run)
    scope = set(scope_cell_ids(grid, level))
    header = frame_record(frame)
    headers = {preset: preset_header(header, raw) for preset, raw in grid.weight_presets_raw.items()}
    if headers["default"]["weights"] != validate_weights(header["weights"]):
        raise EnsembleError("the default preset does not give the weights of the frame")

    unit_order: list[str] | None = None
    names: dict[str, tuple[str, str]] = {}
    rows: dict[RoutingKey, dict[str, Any]] = {}
    for key, entry in measurements.items():
        if isinstance(entry, MeasurementFailure):
            continue
        identifiers = [unit.unit_id for unit in entry]
        if len(set(identifiers)) != len(identifiers) or not identifiers:
            raise EnsembleError("a combination holds its units, each once")
        if unit_order is None:
            unit_order = identifiers
            names = {unit.unit_id: (unit.unit_name_en, unit.unit_name_th) for unit in entry}
        elif identifiers != unit_order:
            raise EnsembleError("every combination holds the same units in the same order")
        closure = planning_assessment.ClosureSpec(closure_rules.CLOSURE_RULE_VERSION, key[1])
        rows[key] = {}
        for unit in entry:
            try:
                rows[key][unit.unit_id] = planning_assessment.assess_unit(
                    rules, case, flood, closure, unit, routing_context_id=routing_context_id, frame_header=header)
            except ValueError as error:
                rows[key][unit.unit_id] = MeasurementFailure("row_assembly", type(error).__name__, str(error))
    if unit_order is None:
        raise EnsembleError("no combination has measurements: nothing was run")
    for key, entry in measurements.items():
        if isinstance(entry, MeasurementFailure):
            rows[key] = {unit_id: entry for unit_id in unit_order}

    run_cells = [cell for cell in table if cell["status"] == STATUS_RUN]
    levels_of = {cell["cell_id"]: {name: cell[name] for name in AXES} for cell in run_cells}
    reference_id = cell_id(grid.reference_cell)
    reference_key = routing_key(grid.reference_cell)
    cells_of_the_set = [cell for cell in table if cell["cell_id"] in scope]
    if len(cells_of_the_set) // (len(grid.axis(VINTAGE_AXIS).levels) * len(grid.axis(ANCHORS_AXIS).levels)) != (
            grid.cells_after_cut_line_6 // (1 if level == PITCH_LEVEL else len(grid.axis(FACILITIES_AXIS).levels))):
        raise EnsembleError("the cells of the protocol's set are not the cells declared cut line 6 counts")

    # One scoring block for each distinct set of values, confidence and weights: units and cells may share one.
    scored_blocks: dict[tuple[Any, ...], dict[str, Any]] = {}

    def scored(row: Mapping[str, Any], anchors_level: str, preset: str) -> dict[str, Any]:
        values = _component_values(row, anchors_level, grid)
        confidence = row["confidence"]
        key = (tuple(values[name] for name in SCORE_COMPONENTS), str(confidence["confidence_class"]),
               bool(confidence["guardrail_gr1"]["applies"]), preset)
        if key not in scored_blocks:
            scored_blocks[key] = _score(row, values, headers[preset])
        return copy.deepcopy(scored_blocks[key])

    results: dict[str, dict[str, dict[str, Any]]] = {unit_id: {} for unit_id in unit_order}
    for cell in run_cells:
        key = routing_key(cell)
        for unit_id in unit_order:
            row = rows[key][unit_id]
            if isinstance(row, MeasurementFailure):
                results[unit_id][cell["cell_id"]] = {"status": "failed", "stage": row.stage, "error": row.error,
                                                     "message": row.message}
                continue
            results[unit_id][cell["cell_id"]] = {"status": "computed", **scored(row, cell[ANCHORS_AXIS], cell[WEIGHTS_AXIS])}

    # The rank of each unit in each cell: FPPS, highest first; a tie goes to the lower unit identifier.
    ranks: dict[str, dict[str, int]] = {unit_id: {} for unit_id in unit_order}
    cells_ranked = 0
    for cell in run_cells:
        identifier = cell["cell_id"]
        scores = {unit_id: results[unit_id][identifier].get("fpps_0_100") for unit_id in unit_order}
        if any(value is None for value in scores.values()):
            continue
        cells_ranked += 1
        for position, unit_id in enumerate(sorted(unit_order, key=lambda item: (-float(scores[item]), item)), start=1):
            ranks[unit_id][identifier] = position

    over = (f"the {len(scope)} cells of the public facility set (protocol v1b facility_sets.shelters_in_the_ensemble, which "
            "states them for a public overlay: open point E10-OP11)"
            if level == PUBLIC_LEVEL else f"the {len(scope)} core cells (protocol v1b ensemble_grid.headline_rule)")
    units: list[dict[str, Any]] = []
    for unit_id in unit_order:
        mine = results[unit_id]
        computed = {identifier: item for identifier, item in mine.items() if item["status"] == "computed"}
        failed = {identifier: item for identifier, item in mine.items() if item["status"] == "failed"}
        reference_row = rows.get(reference_key, {}).get(unit_id)
        if isinstance(reference_row, MeasurementFailure):
            reference_row = None
        reference = computed.get(reference_id)
        if reference is not None and reference_row is not None:
            same = all(reference[field] == reference_row[field] for field in (
                "fpps_0_100", "action_class", "action_reason_code", "would_be_class", "leave_one_component_out"))
            if not same:
                raise EnsembleError(f"unit {unit_id}: the default cell is not the row task E8 computes from the same measurements")
        reference_class = None if reference is None else reference["action_class"]
        in_scope = {identifier: item for identifier, item in computed.items() if identifier in scope}
        classed = {identifier: item["action_class"] for identifier, item in in_scope.items() if item["action_class"] is not None}
        kept = sum(1 for value in classed.values() if value == reference_class) if reference_class is not None else 0
        # The other set the protocol could mean for a run at the public level: the 540 core cells (open point E10-OP11).
        classed_anywhere = [item["action_class"] for item in computed.values() if item["action_class"] is not None]
        other_reading = None if level == PITCH_LEVEL or reference_class is None else protocol_set_reading(
            grid, kept=sum(1 for value in classed_anywhere if value == reference_class), with_a_class=len(classed_anywhere),
            cells=len(table), over=f"the {len(table)} core cells (protocol v1b ensemble_grid.headline_rule)")
        headline = headline_record(
            grid, reference_class=reference_class, kept=kept, with_a_class=len(classed), protocol_cells=len(scope), over=over,
            cells_run=sum(1 for identifier in mine if identifier in scope),
            after_declared_cut_line_6=cut_line_6_record(grid, reference_class=reference_class, classed=classed,
                                                        cells_of_the_set=cells_of_the_set),
            other_reading=other_reading)
        fpps = {identifier: float(item["fpps_0_100"]) for identifier, item in computed.items() if item["fpps_0_100"] is not None}
        loco: dict[str, Any] = {}
        for dropped in SCORE_COMPONENTS:
            with_loco = [item for item in computed.values() if item["leave_one_component_out"] is not None]
            loco[dropped] = {
                "fpps_0_100": _spread([float(item["leave_one_component_out"][dropped]["fpps_0_100"]) for item in with_loco]),
                "class_counts": _class_counts([item["leave_one_component_out"][dropped]["action_class"] for item in with_loco]),
                "cells_whose_class_differs_from_the_class_of_the_cell": sum(
                    1 for item in with_loco if item["leave_one_component_out"][dropped]["action_class"] != item["action_class"]),
                "cells": len(with_loco),
            }
        losing: dict[str, Any] = {}
        if people_losing_access is not None:
            run_keys = sorted({routing_key(cell) for cell in run_cells if cell["cell_id"] in computed})
            services = sorted({service for key in run_keys for service in people_losing_access.get(key, {}).get(unit_id, {})})
            for service in services:
                counts = [float(people_losing_access[key][unit_id][service]) for key in run_keys
                          if service in people_losing_access.get(key, {}).get(unit_id, {})]
                losing[service] = {**(_spread(counts) or {}), "threshold_minutes": THIRTY_MINUTES,
                                   "over": "the access runs of the combinations run; each stands for the same number of cells"}
        confidence = None if reference_row is None else reference_row["confidence"]
        units.append({
            "unit_id": unit_id,
            "unit_name_en": names[unit_id][0],
            "unit_name_th": names[unit_id][1],
            "reference_cell": None if reference is None else {
                "cell_id": reference_id, **{field: reference[field] for field in (
                    "fpps_0_100", "action_class", "action_reason_code", "would_be_class", "leave_one_component_out")}},
            "confidence": None if confidence is None else {
                "confidence_class": confidence["confidence_class"], "confidence_kind": confidence["confidence_kind"],
                "failed_conditions": list(confidence["failed_conditions"]),
                "guardrail_gr1_applies": bool(confidence["guardrail_gr1"]["applies"]),
                "note": "The confidence of the unit in its lane, as task E8 derives it. It uses no ensemble output; "
                        "every cell carries it (open point E10-OP4)."},
            "cells_run": len(mine),
            "cells_with_a_result": len(computed),
            "cells_failed": len(failed),
            "cells_with_a_component_not_computed": sum(1 for item in computed.values() if item["components_not_computed"]),
            "fpps_0_100": _spread(list(fpps.values())),
            "class_counts": _class_counts([item["action_class"] for item in computed.values()]),
            "class_shares": ({key: count / len(mine) for key, count in
                              _class_counts([item["action_class"] for item in computed.values()]).items()} if mine else None),
            "class_shares_over": "The cells run (cells_run), failed cells included in the denominator: with a failed cell "
                                 "the shares add up to less than 1.",
            "share_of_the_cells_run_that_failed": len(failed) / len(mine) if mine else None,
            "headline_stability": headline,
            "rank": {"best": min(ranks[unit_id].values()) if ranks[unit_id] else None,
                     "worst": max(ranks[unit_id].values()) if ranks[unit_id] else None,
                     "cells_ranked": len(ranks[unit_id]), "among_units": len(unit_order),
                     "rule": "FPPS, highest first; a tie goes to the lower unit identifier (open point E10-OP5)."},
            "people_losing_30_minute_access": losing,
            "equity_eed_and_eer": {"status": "not_computed", "reason": "Plan task E9 (open point E10-OP7)."},
            "fpps_swing": axis_swings(grid, fpps, levels_of),
            "leave_one_component_out_over_the_cells": loco,
            "one_at_a_time": _one_at_a_time(reference_row, header, grid),
            "routing_combinations": [
                {"flood_input_single_state": key[0], "passability": key[1], "facilities": key[2], "population_vintage": key[3],
                 **({"status": "failed", "stage": row.stage, "error": row.error} if isinstance(row, MeasurementFailure) else
                    {"status": "computed",
                     "components": {name: None if row["components"][name] is None else float(row["components"][name]["value_0_100"])
                                    for name in SCORE_COMPONENTS},
                     "vulnerability_on_the_sensitivity_anchors": (
                         None if row["components"][VULNERABILITY] is None
                         else float(row["components"][VULNERABILITY]["anchor_sensitivity"]["value_0_100"]))})}
                for key in sorted(rows) for row in (rows[key][unit_id],)],
            "cells": [{"cell_id": cell["cell_id"], **levels_of[cell["cell_id"]], **mine[cell["cell_id"]]} for cell in run_cells],
        })
    return {
        "ensemble_version": ENSEMBLE_VERSION,
        "level": level,
        "grid": grid_record(grid),
        "cells": table,
        "levels_not_run": [item.as_record() for item in not_run],
        "reference_rows": [rows[reference_key][unit_id] for unit_id in unit_order
                           if reference_key in rows and not isinstance(rows[reference_key][unit_id], MeasurementFailure)],
        "units": units,
        "summary": case_summary(grid, table, units, level=level, cells_ranked=cells_ranked),
    }


def case_summary(grid: EnsembleGrid, table: Sequence[Mapping[str, Any]], units: Sequence[Mapping[str, Any]], *,
                 level: str, cells_ranked: int) -> dict[str, Any]:
    """Count what an ensemble holds for the whole case. No value is put beside a unit.

    Returns:
        The cells run and not run with the reasons, the unit-cells with a result and those that failed, how
        many units fall in each class in each cell, how many units keep their class in at least the minimum
        share of the cells run, and the headline statuses.
    """

    run = [cell for cell in table if cell["status"] == STATUS_RUN]
    reasons = Counter("+".join(cell["not_run_because"]) for cell in table if cell["status"] == STATUS_NOT_RUN)
    by_cell: dict[str, dict[str, int]] = {}
    failed_cells: set[str] = set()
    failures = Counter()
    by_unit = [{item["cell_id"]: item for item in unit["cells"]} for unit in units]
    for cell in run:
        identifier = cell["cell_id"]
        found = [items[identifier] for items in by_unit]
        if any(item["status"] == "failed" for item in found):
            failed_cells.add(identifier)
            failures.update(f"{item['stage']}:{item['error']}" for item in found if item["status"] == "failed")
        counted = _class_counts([item["action_class"] for item in found if item["status"] == "computed"])
        by_cell[identifier] = {key: count for key, count in counted.items() if count}
    minimum = grid.class_retention_min

    def retention(unit: Mapping[str, Any]) -> tuple[int, int] | None:
        """The cells keeping the class and the cells run, failed cells included: a failed cell keeps no class."""

        record = unit["headline_stability"]
        if record["reference_class"] is None or not record["cells_run"]:
            return None
        return int(record["cells_keeping_the_reference_class"]), int(record["cells_run"])

    shares = [retention(unit) for unit in units]
    not_evaluated = [unit["headline_stability"] for unit in units
                     if unit["headline_stability"]["status"] == HEADLINE_NOT_EVALUATED
                     and unit["headline_stability"]["reference_class"] is not None]
    fixed = Counter(record["outcome_fixed_by_the_bounds"] or "not_fixed" for record in not_evaluated)
    other = [record["other_reading_of_the_protocol_set"] for record in not_evaluated
             if record["other_reading_of_the_protocol_set"] is not None]
    other_fixed = Counter(record["outcome_fixed_by_the_bounds"] or "not_fixed" for record in other if record["bounds"] is not None)
    cut_records = [unit["headline_stability"]["after_declared_cut_line_6"] for unit in units]

    def cut_counts(options: Sequence[Mapping[str, Any] | None]) -> dict[str, Any]:
        """Count the units on each side of the minimum over the cells one pair of kept levels would leave."""

        with_a_share = [item for item in options if item is not None and item["retention"] is not None]
        stated = next((item for item in options if item is not None), None)
        return {
            "levels_kept": None if stated is None else dict(stated["levels_kept"]),
            "cells": None if stated is None else stated["cells"],
            "units_at_or_above_the_minimum": sum(1 for item in with_a_share if item["at_or_above_the_minimum"]),
            "units_below_the_minimum": sum(1 for item in with_a_share if not item["at_or_above_the_minimum"]),
            "units_keeping_the_class_in_every_one_of_those_cells": sum(
                1 for item in with_a_share if item["cells_keeping_the_reference_class"] == item["cells"]),
            "units_without_a_class_in_every_one_of_those_cells": len(units) - len(with_a_share),
        }

    pairs = max((len(item["other_levels_the_cut_could_keep"]) for item in cut_records if item is not None), default=0)
    e_threshold = 35.0
    summary = {
        "units": len(units),
        "level": level,
        "core_cells_per_lane": len(table),
        "cells_run": len(run),
        "cells_not_run": len(table) - len(run),
        "cells_not_run_by_reason": dict(sorted(reasons.items())),
        "cells_of_the_protocol_set_for_retention": units[0]["headline_stability"]["cells_of_the_protocol_set"] if units else None,
        "cells_run_with_a_failed_unit": len(failed_cells),
        "unit_cells_run": sum(unit["cells_run"] for unit in units),
        "unit_cells_with_a_result": sum(unit["cells_with_a_result"] for unit in units),
        "unit_cells_failed": sum(unit["cells_failed"] for unit in units),
        "unit_cells_failed_by_stage_and_error": dict(sorted(failures.items())),
        "unit_cells_with_a_component_not_computed": sum(unit["cells_with_a_component_not_computed"] for unit in units),
        "cells_ranked": cells_ranked,
        "reference_class_counts": _class_counts([None if unit["reference_cell"] is None else unit["reference_cell"]["action_class"]
                                                 for unit in units if unit["reference_cell"] is not None]),
        "units_without_a_default_cell_result": sum(1 for unit in units if unit["reference_cell"] is None),
        "class_counts_over_every_unit_cell": {key: sum(unit["class_counts"][key] for unit in units) for key in CLASS_KEYS},
        "units_by_number_of_classes_over_the_cells_run": dict(sorted(Counter(
            str(sum(1 for key in CLASS_KEYS if unit["class_counts"][key])) for unit in units).items())),
        "retention_over_the_cells_run": {
            "what": "The share of the cells that were run in which a unit keeps the class of its default cell. A cell "
                    "that was run and failed counts as run and keeps no class. It is not the retention of the headline "
                    "rule unless every cell of the protocol's set was run.",
            "class_retention_min": minimum,
            "units_keeping_the_class_in_every_cell_run": sum(1 for item in shares if item is not None and item[0] == item[1]),
            "units_keeping_the_class_in_at_least_the_minimum_share": sum(
                1 for item in shares if item is not None and _at_least(item[0], item[1], minimum)),
            "units_keeping_the_class_in_less_than_the_minimum_share": sum(
                1 for item in shares if item is not None and not _at_least(item[0], item[1], minimum)),
            "units_without_a_class_to_keep": sum(1 for item in shares if item is None),
        },
        "headline_status_counts": {status: sum(1 for unit in units if unit["headline_stability"]["status"] == status)
                                   for status in (HEADLINE_NOT_EVALUATED, HEADLINE_ELIGIBLE, HEADLINE_UNSTABLE)},
        "outcome_fixed_by_the_bounds_counts": {key: fixed.get(key, 0) for key in (BOUNDS_AT_OR_ABOVE, BOUNDS_BELOW, "not_fixed")},
        "other_reading_of_the_protocol_set": None if not other else {
            "over": other[0]["over"],
            "cells": other[0]["cells"],
            "outcome_fixed_by_the_bounds_counts": {key: other_fixed.get(key, 0) for key in (BOUNDS_AT_OR_ABOVE, BOUNDS_BELOW, "not_fixed")},
            "note": "The same counts with the core cells as the set of the rule. Which set applies to a result that is "
                    "not a public overlay is open point E10-OP11; no status is set from either.",
        },
        "after_declared_cut_line_6": None if all(item is None for item in cut_records) else {
            **cut_counts(cut_records),
            "levels_kept_are": "the levels of the default cell",
            "other_levels_the_cut_could_keep": [
                cut_counts([None if item is None else item["other_levels_the_cut_could_keep"][index] for item in cut_records])
                for index in range(pairs)],
            "note": "Counts over the cells that declared cut line 6 would leave. Not the headline: the owners have not "
                    "invoked the cut (open point E10-OP1). The cut does not say which level of its two axes stays: the "
                    "first counts keep the levels of the default cell, and other_levels_the_cut_could_keep gives the "
                    "counts for every other pair (open point E10-OP12).",
        },
        "units_whose_fpps_lies_on_both_sides_of_the_class_e_threshold": sum(
            1 for unit in units if unit["fpps_0_100"] is not None and unit["fpps_0_100"]["min"] < e_threshold <= unit["fpps_0_100"]["max"]),
        "class_e_threshold_fpps": e_threshold,
        "units_whose_class_changes_under_leave_one_component_out_in_the_default_cell": sum(
            1 for unit in units if unit["reference_cell"] is not None and unit["reference_cell"]["leave_one_component_out"] is not None
            and any(item["action_class"] != unit["reference_cell"]["action_class"]
                    for item in unit["reference_cell"]["leave_one_component_out"].values())),
        "units_with_one_rank_in_every_cell_ranked": sum(
            1 for unit in units if unit["rank"]["best"] is not None and unit["rank"]["best"] == unit["rank"]["worst"]),
        "class_counts_by_cell": by_cell,
        "class_counts_by_cell_note": "For each cell that was run, the number of units in each class; a class no unit has "
                                     "in the cell is left out.",
        "note": "Counts for the whole case. No unit is named beside a value here. Some counts state a value of a single "
                "unit all the same: a count that covers every unit states that value for each unit, and a class that "
                "one unit alone holds in the default cell marks that unit in every cell (open point E10-OP10; "
                "counts_that_state_a_value_of_a_single_unit counts them).",
    }
    summary["counts_that_state_a_value_of_a_single_unit"] = counts_that_state_single_units(summary)
    return summary


def counts_that_state_single_units(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Count the whole-case counts of a summary that state a value of a single unit (open point E10-OP10).

    A count names no unit. It states the class of a single unit all the same in two cases, and this function
    counts both: a cell in which every unit of the case has one class, and a class that exactly one unit
    holds in the default cell, whose count in every other cell says whether that unit holds it there. It also
    counts the cells whose class counts differ from those of the default cell: each says that a unit changed
    class, and between which classes.
    """

    units = int(summary["units"])
    by_cell = summary["class_counts_by_cell"]
    reference = {key: count for key, count in summary["reference_class_counts"].items() if count}
    alone = sorted(key for key, count in reference.items() if count == 1 and key != NO_CLASS)
    one_class = sum(1 for counts in by_cell.values() if counts and max(counts.values()) == units)
    return {
        "cells_in_which_every_unit_has_one_class": one_class,
        "classes_one_unit_alone_holds_in_the_default_cell": alone,
        "cells_in_which_such_a_class_has_another_count": sum(
            1 for counts in by_cell.values() if any(counts.get(key, 0) != 1 for key in alone)),
        "cells_whose_class_counts_differ_from_the_default_cell": sum(1 for counts in by_cell.values() if dict(counts) != reference),
        "units_with_more_than_one_class_over_the_cells_run": sum(
            count for classes, count in summary["units_by_number_of_classes_over_the_cells_run"].items() if int(classes) > 1),
        "states_a_value_of_a_single_unit": bool(one_class or alone),
        "what": "A count names no unit. Two kinds of count state the class of a single unit all the same. In a cell where "
                "every unit of the case has one class, class_counts_by_cell states the class of each unit. And a class "
                "that one unit alone holds in the default cell marks that unit: in every cell, the count of that class "
                "says whether the unit holds it there, for whoever knows which unit it is. A cell whose counts differ "
                "from those of the default cell says that a unit changed class there, and between which classes.",
    }
