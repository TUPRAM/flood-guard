"""Write the equity and access parity fixture for the Mae Sai replay's TypeScript tests.

The page recomputes three things in the browser that Python also computes:

* which resident nodes have lost walking access to a shelter at a stage
  (``lost_at`` and ``home_wet`` in ``scripts/mae_sai_timeline_evacuation.py``);
* the Evacuation Equity Gap between proxy-vulnerable residents and everyone else
  (``floodguard.replay_equity.replay_equity_gap``): each group's loss rate is the share of its residents with a
  shelter within reach before the flood who lost it (owner decision R8, option B), and no ratio is given, with a
  reason, when a group has fewer than 50 such residents or when nobody has lost access;
* the side-by-side figures of every shelter set (``floodguard.shelter_set_comparison.shelter_set_summary``):
  residents within reach before the flood, still within reach, newly lost with their share of that baseline,
  and the modelled access cut-off hour.

This script computes all three with the Python code, from the served manifest and its access node file, and
writes the results as a fixture. The web tests then check that ``flood-timeline-evacuation.ts`` gives the
same level indices, the same lost residents, the same within-reach denominators, the same rates, ratio,
reason and wording and the same set figures, so a changed threshold, rounding rule or denominator on either
side fails a test.

Where the replay's equity rule gives a ratio, the script also checks it against the unchanged
``floodguard.equity.compute_equity_gap`` fed the same numerators and denominators; the two differ only where
the replay withholds a ratio.

Everything in the fixture is a T1 scenario on a modelled flood: not observed evacuation outcomes, not a
score and not an action class. "Vulnerable" is the terrain and remoteness proxy, not age, disability or
income.

Run from the repository root (read-only on the data; it writes only the fixture):

    python apps/web/scripts/equity-access-parity-fixture.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

# Metric version 1, the code the replay's rule was written beside; floodguard.equity itself is version 2.0.
from floodguard.equity_v1 import compute_equity_gap  # noqa: E402
from floodguard.replay_equity import (  # noqa: E402
    DENOMINATOR,
    MINIMUM_GROUP_SIZE,
    REASON_INSUFFICIENT_GROUP,
    REASON_NO_LOSS,
    REASON_UNDEFINED_RATIO,
    replay_equity_gap,
)
from floodguard.shelter_set_comparison import (  # noqa: E402
    CUTOFF_COVERAGE_SHARE,
    CUTOFF_NO_BASELINE,
    CUTOFF_NOT_REACHED,
    CUTOFF_REACHED,
    shelter_set_summary,
)

SPEC = importlib.util.spec_from_file_location("mae_sai_timeline_evacuation", ROOT / "scripts" / "mae_sai_timeline_evacuation.py")
evac = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evac)

WEB = ROOT / "apps" / "web"
MANIFEST_URL_PATTERN = 'TIMELINE_MANIFEST_URL = "'
FIXTURE = WEB / "src" / "lib" / "__fixtures__" / "mae-sai-equity-access-parity.json"
HOURS = 11 * 24
SCOPES = ("all", "flooded")
EQUITY_COLUMNS = ["vulnerable_lost", "vulnerable_within_reach", "non_vulnerable_lost", "non_vulnerable_within_reach",
                  "vulnerable_rate", "non_vulnerable_rate", "ratio", "band", "interpretation", "reason"]
# Replay hours at which the set comparison is sampled: before the flood, through the rise, the peak and the recession.
COMPARISON_HOURS = (0, 24, 36, 40, 42, 44, 46, 47, 48, 49, 52, 55, 58, 60, 72, 84, 96, 108, 120, 144, 168, 216, 263)

# Hand-picked inputs around every rule of the Evacuation Equity Gap: (case, vulnerable lost, vulnerable within reach
# before the flood, other lost, other within reach before the flood). "Group" below means that within-reach
# denominator. The expected values are computed below by floodguard.replay_equity; nothing here states an expected result.
EQUITY_EDGE_INPUTS: list[tuple[str, float, float, float, float]] = [
    ("ratio exactly 1.2 (upper limit of similar)", 1200, 10000, 1000, 10000),
    ("ratio 1.201 (just above 1.2)", 1201, 10000, 1000, 10000),
    ("ratio 1.199 (just below 1.2)", 1199, 10000, 1000, 10000),
    ("ratio 1.25", 1250, 10000, 1000, 10000),
    ("ratio exactly 0.8 (lower limit of similar)", 800, 10000, 1000, 10000),
    ("ratio 0.799 (just below 0.8)", 799, 10000, 1000, 10000),
    ("ratio 0.801 (just above 0.8)", 801, 10000, 1000, 10000),
    ("ratio 0.75", 750, 10000, 1000, 10000),
    ("ratio exactly 1", 500, 10000, 500, 10000),
    ("ratio 2", 20, 100, 10, 100),
    ("three-decimal ratio rounding", 100, 300, 100, 700),
    ("three-decimal ratio rounding, other way", 200, 300, 100, 700),
    ("large ratio in exponent notation", 5000, 10000, 4, 10000),
    ("ratio 100", 5000, 10000, 50, 10000),
    ("ratio 12.5", 1250, 10000, 100, 10000),
    ("small ratio", 1, 10000, 5000, 10000),
    ("rate half-way case 0.00005", 5, 100000, 1000, 10000),
    ("rate half-way case 0.00015", 15, 100000, 1000, 10000),
    ("rate half-way case 0.00025", 25, 100000, 1000, 10000),
    ("rate half-way case 0.12345", 12345, 100000, 1000, 10000),
    # A loss too small for four-decimal rounding is still a loss: the rule reads the lost counts, and the ratio
    # then uses the unrounded rates.
    ("vulnerable rate rounds to zero", 0.004, 100, 10, 100),
    ("both rates round to zero", 0.004, 100, 0.004, 100),
    ("only the non-vulnerable rate rounds to zero", 5, 100, 0.004, 100),
    ("small loss in a large group, no vulnerable loss", 0, 7152, 3, 74647),
    ("small loss in both large groups", 1, 7152, 3, 74647),
    ("small vulnerable loss only, large groups", 2, 7152, 0, 74647),
    ("small vulnerable loss beside a large other loss", 0.3, 7152, 5671, 74647),
    ("no vulnerable loss", 0, 2440, 7086, 32085),
    ("only vulnerable loss", 5, 50, 0, 100),
    ("no loss in either group", 0, 50, 0, 100),
    ("no vulnerable residents", 0, 0, 5, 50),
    ("no vulnerable residents and no other loss", 0, 0, 0, 50),
    ("no other residents", 5, 50, 0, 0),
    ("no residents at all", 0, 0, 0, 0),
    ("everyone lost", 50, 50, 100, 100),
    ("fractional residents", 34.3, 7151.6, 5671, 74646.9),
    # The null rule: no ratio when a group has fewer than 50 residents within reach before the flood, or when nobody
    # has lost access.
    ("vulnerable group of exactly 50 (enough)", 10, 50, 100, 1000),
    ("vulnerable group of 49.99 (too small)", 10, 49.99, 100, 1000),
    ("vulnerable group of 49 (too small)", 10, 49, 100, 1000),
    ("other group of exactly 50 (enough)", 100, 1000, 10, 50),
    ("other group of 49 (too small)", 100, 1000, 10, 49),
    ("both groups too small", 1, 3, 1, 7),
    ("one resident in the vulnerable group", 1, 1, 100, 1000),
    ("too small and no loss (group size is the reason)", 0, 26.5, 0, 7553.2),
    ("too small and only vulnerable loss (group size is the reason)", 5, 26.5, 0, 7553.2),
    ("no loss, both groups large", 0, 2440.4, 0, 32084.7),
    ("no loss, groups of exactly 50", 0, 50, 0, 50),
    ("only vulnerable loss, both groups large", 320, 7151.6, 0, 74646.9),
    # The served replay at the 3.5 m peak, all residents (rounded): the denominator is the residents within reach
    # before the flood (373 and 24,537 for the plan of 8), not all residents counted (7,152 and 74,647).
    ("plan of 8 at the peak, within-reach denominators", 320, 373, 13109, 24537),
    ("plan of 8 at the peak, if all residents counted were the denominators", 320, 7152, 13109, 74647),
    ("reported set at the peak, within-reach denominators", 0, 2440, 7086, 32085),
    ("nobody in the vulnerable group within reach (the default view)", 0, 0, 5400, 5698),
    ("27 vulnerable residents within reach, all lost (too small)", 26.5, 26.5, 7093.5, 7553.2),
    ("everyone within reach lost in both groups", 373, 373, 24537, 24537),
]


def manifest_href() -> str:
    """The one manifest URL the page serves, read from ``flood-timeline.ts``."""
    source = (WEB / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    start = source.index(MANIFEST_URL_PATTERN) + len(MANIFEST_URL_PATTERN)
    return source[start:source.index('"', start)]


def read_nodes(data: bytes, access: dict) -> dict[str, np.ndarray]:
    """Decode ``access-nodes.bin`` with the manifest layout (little-endian float32 and uint8 columns)."""
    count = access["nodes"]["count"]
    out: dict[str, np.ndarray] = {}
    for field in access["nodes"]["layout"]:
        rows = field["shape"][0] if "shape" in field else 1
        dtype = np.dtype("<f4") if field["dtype"] == "float32" else np.dtype("u1")
        values = np.frombuffer(data, dtype=dtype, count=rows * count, offset=field["offset"])
        out[field["name"]] = values.reshape(rows, count) if "shape" in field else values
    return out


def equity_rows(inputs: list[tuple[float, float, float, float]]) -> list[list]:
    """Run ``floodguard.replay_equity.replay_equity_gap`` on (vulnerable lost, vulnerable within reach, other lost, other within reach).

    The denominators are the residents of each group with a shelter within reach before the flood. Each row is
    also checked against the unchanged ``floodguard.equity.compute_equity_gap`` fed the same four numbers (its
    "total" columns take the within-reach residents): the rates always agree, and the ratio and wording agree
    wherever the replay gives a ratio or calls it undefined. The replay differs by withholding the ratio for
    small groups and when nobody has lost access (there ``floodguard.equity`` says 1.0), and where a rounded
    rate of zero hides residents who did lose access: the replay judges loss on the lost counts and divides the
    unrounded rates there.
    """
    frame = pd.DataFrame({
        "subdistrict_id": [f"case-{index}" for index in range(len(inputs))],
        "subdistrict_name": "parity case",
        "total_vulnerable_population": [row[1] for row in inputs],
        "vulnerable_population_losing_access": [row[0] for row in inputs],
        "total_non_vulnerable_population": [row[3] for row in inputs],
        "non_vulnerable_population_losing_access": [row[2] for row in inputs],
        "confidence_class": "low",
    })
    reference = compute_equity_gap(frame)
    number = lambda value: None if pd.isna(value) else float(value)  # noqa: E731
    rows = []
    for given, (_, base) in zip(inputs, reference.iterrows()):
        gap = replay_equity_gap(*given)
        if gap.denominator != DENOMINATOR or (gap.vulnerable_within_reach, gap.non_vulnerable_within_reach) != (float(given[1]), float(given[3])):
            raise SystemExit(f"{given}: the replay's rates do not divide by the residents within reach before the flood")
        base_rates = [number(base["vulnerable_access_loss_rate"]), number(base["non_vulnerable_access_loss_rate"])]
        base_ratio, base_text = number(base["equity_gap_ratio"]), str(base["interpretation_text"])
        if [gap.vulnerable_rate, gap.non_vulnerable_rate] != base_rates:
            raise SystemExit(f"{given}: the replay's loss rates differ from floodguard.equity")
        # A rate of 0.0000 with residents lost: floodguard.equity reads it as no loss, the replay does not.
        hidden = (given[0] > 0 and gap.vulnerable_rate == 0) or (given[2] > 0 and gap.non_vulnerable_rate == 0)
        if hidden and gap.reason == REASON_NO_LOSS:
            raise SystemExit(f"{given}: residents lost access, but the replay reports no loss")
        if gap.reason is None and not hidden and (gap.ratio != base_ratio or gap.interpretation != base_text):
            raise SystemExit(f"{given}: the replay's ratio or wording differs from floodguard.equity")
        if gap.reason == REASON_UNDEFINED_RATIO and (given[2] != 0 or base_ratio is not None or gap.interpretation != base_text):
            raise SystemExit(f"{given}: the replay's undefined ratio differs from floodguard.equity")
        if gap.reason == REASON_NO_LOSS and (base_ratio != 1.0 or given[0] != 0 or given[2] != 0):
            raise SystemExit(f"{given}: no loss is reported although residents lost access, or floodguard.equity no longer states 1.0")
        if (gap.reason == REASON_INSUFFICIENT_GROUP) != (min(given[1], given[3]) < MINIMUM_GROUP_SIZE):
            raise SystemExit(f"{given}: the group-size rule was not applied as documented")
        rows.append([*(float(value) for value in given), gap.vulnerable_rate, gap.non_vulnerable_rate, gap.ratio, gap.band,
                     gap.interpretation, gap.reason])
    return rows


def random_inputs(count: int) -> list[tuple[float, float, float, float]]:
    """Reproducible inputs with fractional residents, like the population-weighted node sums.

    Each row is (vulnerable lost, vulnerable within reach, other lost, other within reach); the lost residents
    never exceed those within reach.
    """
    rng = random.Random(20240912)
    rows = []
    for _ in range(count):
        vulnerable_reach = round(rng.uniform(50, 8000), 1)
        other_reach = round(rng.uniform(500, 80000), 1)
        rows.append((round(vulnerable_reach * rng.random() ** 2, 1), vulnerable_reach, round(other_reach * rng.random() ** 2, 1), other_reach))
    return rows


def assert_stable(lost: float, within_reach: float, label: str) -> None:
    """Fail when ``lost / within_reach`` is within 1e-9 of a four-decimal rounding edge (the browser sums in another order)."""
    if within_reach == 0:
        return
    scaled = lost / within_reach * 1e4
    if abs(scaled - math.floor(scaled) - 0.5) < 1e-5:
        raise SystemExit(f"{label}: loss rate {lost / within_reach!r} sits on a rounding edge; the parity fixture would be fragile")


def assert_clear_of_minimum(within_reach: float, label: str) -> None:
    """Fail when a denominator is within 1e-6 of the 50-resident minimum (the browser sums in another order)."""
    if abs(within_reach - MINIMUM_GROUP_SIZE) < 1e-6:
        raise SystemExit(f"{label}: {within_reach!r} residents within reach sits on the group-size limit; the parity fixture would be fragile")


def fixture_text() -> str:
    """Compute the whole fixture with the Python code and return it as JSON text."""
    href = manifest_href()
    manifest = json.loads((WEB / "public" / href.lstrip("/")).read_text(encoding="utf-8"))
    access, shelters = manifest["access"], manifest["shelters"]
    node_bytes = (WEB / "public" / access["nodes"]["href"].lstrip("/")).read_bytes()
    if hashlib.sha256(node_bytes).hexdigest() != access["nodes"]["sha256"]:
        raise SystemExit("access-nodes.bin does not match the manifest hash")
    nodes = read_nodes(node_bytes, access)
    levels = [float(level) for level in access["levels"]]
    if levels != evac.LEVELS:
        raise SystemExit("the manifest's access levels differ from the builder's LEVELS")

    # Same values as the bake: float32 residents read as float64; everyone else = total - vulnerable.
    # Sums use math.fsum (exactly rounded), so the fixture does not depend on how a NumPy build orders additions.
    total = lambda values: math.fsum(values.tolist())  # noqa: E731
    population = nodes["population"].astype(float)
    vulnerable = nodes["vulnerable_population"].astype(float)
    other = population - vulnerable
    peak_stage = float(shelters["method"]["peak_stage_m"])
    masks = {"all": np.ones(len(population), dtype=bool), "flooded": evac.home_wet(nodes["home_code"], peak_stage)}

    # --- Stage -> evaluated level, at every hour of the replay and at awkward stages -----------------
    knots_t = [anchor["t"] for anchor in manifest["stage_anchors"]]
    knots_s = [anchor["stage_m"] for anchor in manifest["stage_anchors"]]
    probe = np.arange(254, dtype=np.uint8)

    def level_index(stage: float) -> int:
        """The level index ``evac.lost_at`` uses at ``stage``, recovered from its output (codes at or below it are lost)."""
        index = int(np.flatnonzero(evac.lost_at(probe, stage)).max())
        if index >= 253:
            raise SystemExit(f"stage {stage} is beyond the cut codes this fixture can express")
        return index

    hours = [[hour, float(np.interp(hour / 24, knots_t, knots_s))] for hour in range(HOURS)]
    hours = [[hour, stage, level_index(stage)] for hour, stage in hours]
    edge_stages = sorted({0.0, 0.049, 0.05, 0.0999999, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.7, 0.8, 1.0, 1.15, 2.65, 3.2, 3.45, 3.5,
                          3.999999, 4.0, 4.05, 5.0, *levels})
    level_cases = [[stage, level_index(stage)] for stage in edge_stages]
    codes = [0, 1, 2, 3, 16, 40, 69, 70, 71, 80, 81, 253, 254, 255]
    lost_cases = [[stage, [bool(value) for value in evac.lost_at(np.array(codes, dtype=np.uint8), stage)]]
                  for stage in (0.0, 0.05, 0.15, 0.79, 0.8, 2.0, 3.5, 4.0, 4.05)]
    home_codes = [0, 1, 2, 10, 69, 70, 71, 253, 254, 255]
    home_cases = [[stage, [bool(value) for value in evac.home_wet(np.array(home_codes, dtype=np.uint8), stage)]]
                  for stage in (0.0, 0.05, 0.1, 0.5, 3.5, 12.7, 99.0)]

    # --- Lost residents and the equity gap, per shelter set, scope and level ----------------------
    # Each loss rate divides by the residents of the group with a shelter of the set within reach before the flood
    # (cut code other than "no baseline access"), not by all residents counted in the group.
    knee = f"plan_{shelters['knee_k']}"
    set_ids = ["reported_2024", "plan_1", knee, access["sets"][-1]]
    access_rows = []
    for set_id in dict.fromkeys(set_ids):
        row_codes = nodes["cut_codes"][access["sets"].index(set_id)]
        for scope in SCOPES:
            mask = masks[scope]
            totals = [total(population[mask]), total(vulnerable[mask]), total(other[mask])]
            no_baseline = (row_codes == evac.NO_BASELINE_ACCESS) & mask
            within = mask & ~no_baseline
            reach = [total(population[within]), total(vulnerable[within]), total(other[within])]
            assert_clear_of_minimum(reach[1], f"{set_id}/{scope} vulnerable")
            assert_clear_of_minimum(reach[2], f"{set_id}/{scope} other")
            # The set-comparison module counts the same baseline: the two Python paths must name one denominator.
            twin = shelter_set_summary(population, row_codes, peak_stage, [], vulnerable_population=vulnerable, mask=mask)
            if twin.vulnerable_baseline != reach[1] or abs(twin.baseline - reach[0]) > 1e-6 or abs(twin.residents - totals[0]) > 1e-6:
                raise SystemExit(f"{set_id}/{scope}: the within-reach residents differ from floodguard.shelter_set_comparison")
            sums = []
            for level in levels:
                lost = evac.lost_at(row_codes, level) & mask
                if (lost & ~within).any():
                    raise SystemExit(f"{set_id}/{scope}/{level}: a node lost access without having had it before the flood")
                sums.append((total(population[lost]), total(vulnerable[lost]), total(other[lost])))
                assert_stable(sums[-1][1], reach[1], f"{set_id}/{scope}/{level} vulnerable")
                assert_stable(sums[-1][2], reach[2], f"{set_id}/{scope}/{level} other")
            equity = equity_rows([(lost_v, reach[1], lost_o, reach[2]) for _, lost_v, lost_o in sums])
            access_rows.append({
                "set": set_id, "scope": scope,
                "totals": {"population": totals[0], "vulnerable": totals[1], "non_vulnerable": totals[2]},
                "within_reach": {"population": reach[0], "vulnerable": reach[1], "non_vulnerable": reach[2]},
                "no_baseline_access": total(population[no_baseline]),
                "levels": [[index, lost_all, *row[:1], row[2], *row[4:]] for index, ((lost_all, _, _), row) in enumerate(zip(sums, equity))],
            })

    # --- Shelter sets side by side: baseline, keeping, newly lost and the cut-off hour ---------------
    hourly_stages = [stage for _, stage, _ in hours]
    comparison_rows = []
    for set_id in access["sets"]:
        row_codes = nodes["cut_codes"][access["sets"].index(set_id)]
        for scope in SCOPES:
            mask = masks[scope]
            summary = lambda stage: shelter_set_summary(  # noqa: E731
                population, row_codes, stage, hourly_stages, vulnerable_population=vulnerable, mask=mask)
            at_peak = summary(peak_stage)
            # The same hour from the builder's own lost_at, node by node: the module and the builder must agree, and no
            # hour may sit on the half-of-baseline edge (the browser sums in another order).
            with_baseline = (row_codes != evac.NO_BASELINE_ACCESS) & mask
            baseline = total(population[with_baseline])
            cutoff = None
            for hour, stage in enumerate(hourly_stages):
                keeping = baseline - total(population[evac.lost_at(row_codes, stage) & mask])
                if abs(keeping - CUTOFF_COVERAGE_SHARE * baseline) < 1e-6 * max(baseline, 1.0):
                    raise SystemExit(f"{set_id}/{scope} hour {hour}: coverage sits on the cut-off edge; the parity fixture would be fragile")
                if cutoff is None and baseline > 0 and keeping < CUTOFF_COVERAGE_SHARE * baseline:
                    cutoff = hour
            expected_status = CUTOFF_NO_BASELINE if baseline == 0 else CUTOFF_REACHED if cutoff is not None else CUTOFF_NOT_REACHED
            if (at_peak.cutoff_status, at_peak.cutoff_hour) != (expected_status, cutoff) or abs(at_peak.baseline - baseline) > 1e-6:
                raise SystemExit(f"{set_id}/{scope}: floodguard.shelter_set_comparison disagrees with the builder's lost_at")
            sampled = [(hour, summary(hourly_stages[hour])) for hour in COMPARISON_HOURS]
            comparison_rows.append({
                "set": set_id, "scope": scope, "residents": at_peak.residents, "baseline": at_peak.baseline,
                "vulnerable_baseline": at_peak.vulnerable_baseline,
                "at_peak": {"keeping": at_peak.keeping, "lost": at_peak.lost, "lost_share": at_peak.lost_share,
                            "vulnerable_lost": at_peak.vulnerable_lost},
                "cutoff_status": at_peak.cutoff_status, "cutoff_hour": at_peak.cutoff_hour,
                "hours": [[hour, item.keeping, item.lost, item.lost_share] for hour, item in sampled],
            })

    edge_rows = equity_rows([row[1:] for row in EQUITY_EDGE_INPUTS])
    fixture = {
        "generated_by": "apps/web/scripts/equity-access-parity-fixture.py (scripts/mae_sai_timeline_evacuation.py lost_at and home_wet; floodguard.replay_equity.replay_equity_gap; floodguard.shelter_set_comparison.shelter_set_summary)",
        "manifest": href,
        "access_nodes_sha256": access["nodes"]["sha256"],
        "scenario_tier": access["scenario_tier"],
        "vulnerable_definition": "vulnerable = terrain/remoteness proxy (homes on slopes or far from a drivable road), not age, disability or income",
        "confidence": access["confidence"],
        "source_timestamp": access["source_timestamp"],
        "assumptions": [
            "T1 scenario (model): access is computed on the reconstructed water with illustrative stage keyframes; nothing here is an observed evacuation outcome.",
            "Residents are WorldPop 2020 modelled estimates at road nodes; vulnerable residents are the terrain and remoteness proxy.",
            "The flooded scope counts residents whose home node is wet at the modelled peak stage; the all scope counts every resident node.",
            "Hours come from illustrative stage keyframes, not observed; the access cut-off hour is the first replay hour when fewer than half of the residents with a shelter within reach before the flood still have one.",
            "Each group's loss rate is, of its residents who had a shelter of the set within reach before the flood, the share who lost it (owner decision R8, option B); residents with no shelter of the set within reach before the flood are not in the rate.",
            "No ratio is stated when a group has fewer than 50 residents within reach before the flood or when nobody has lost access; the shelter sets are not ranked.",
            "Loss is judged on the residents who lost access, not on the rounded rates: a loss that rounds to a rate of 0.0000 still counts, and the ratio then uses the unrounded rates.",
            "No score and no action class is computed from these figures.",
        ],
        "official_warning": False,
        "peak_stage_m": peak_stage,
        "level_step_m": 0.05,
        "hour_columns": ["hour", "stage_m", "level_index"],
        "hours": hours,
        "level_cases": level_cases,
        "lost_codes": codes,
        "lost_cases": lost_cases,
        "home_codes": home_codes,
        "home_wet_cases": home_cases,
        "equity_denominator": DENOMINATOR,
        "equity_minimum_group": MINIMUM_GROUP_SIZE,
        "equity_null_reasons": [REASON_INSUFFICIENT_GROUP, REASON_NO_LOSS, REASON_UNDEFINED_RATIO],
        "equity_columns": EQUITY_COLUMNS,
        "equity_edge_cases": [{"case": name, "row": row} for (name, *_), row in zip(EQUITY_EDGE_INPUTS, edge_rows)],
        "equity_random_cases": equity_rows(random_inputs(150)),
        "access_level_columns": ["level_index", "people_lost", "vulnerable_lost", "non_vulnerable_lost",
                                 "vulnerable_rate", "non_vulnerable_rate", "ratio", "band", "interpretation", "reason"],
        "access": access_rows,
        "cutoff_coverage_share": CUTOFF_COVERAGE_SHARE,
        "set_comparison_hour_columns": ["hour", "keeping", "lost", "lost_share"],
        "set_comparison": comparison_rows,
    }

    def block(rows: list, indent: str = "  ") -> str:
        return "[\n" + ",\n".join(f"{indent}{json.dumps(row, ensure_ascii=False)}" for row in rows) + "\n ]"

    # One row per line keeps the diff readable.
    parts = []
    for key, value in fixture.items():
        if key in ("hours", "level_cases", "lost_cases", "home_wet_cases", "equity_edge_cases", "equity_random_cases"):
            parts.append(f' {json.dumps(key)}: {block(value)}')
        elif key == "access":
            groups = []
            for group in value:
                head = json.dumps({name: group[name] for name in ("set", "scope", "totals", "within_reach", "no_baseline_access")}, ensure_ascii=False)
                groups.append(f'  {head[:-1]}, "levels": {block(group["levels"], "   ")[:-2]}  ]}}')
            parts.append(f' "access": [\n' + ",\n".join(groups) + "\n ]")
        elif key == "set_comparison":
            groups = []
            for group in value:
                head = json.dumps({name: item for name, item in group.items() if name != "hours"}, ensure_ascii=False)
                groups.append(f'  {head[:-1]}, "hours": {block(group["hours"], "   ")[:-2]}  ]}}')
            parts.append(f' "set_comparison": [\n' + ",\n".join(groups) + "\n ]")
        else:
            parts.append(f" {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}")
    text = "{\n" + ",\n".join(parts) + "\n}\n"
    json.loads(text)  # The hand-laid layout must still be valid JSON.
    return text


def main() -> None:
    text = fixture_text()
    document = json.loads(text)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    # LF on every platform, matching the repository's eol=lf policy (Windows text mode would write CRLF).
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT).as_posix()} ({len(document['hours'])} hours, {len(document['access'])} set/scope groups, "
          f"{len(document['equity_edge_cases'])} + {len(document['equity_random_cases'])} equity cases, "
          f"{len(document['set_comparison'])} set comparisons)")


if __name__ == "__main__":
    main()
