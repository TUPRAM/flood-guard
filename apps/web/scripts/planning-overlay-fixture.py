"""Write the planning assessment overlay fixture the web screens and their tests are built against.

The fixture is an invented case with invented units: a fixture, not a place. No unit, input, date or unit number in
it comes from a real tambon, a real flood product or a real detector. What is real in it is what the signed protocols
fix for every overlay, and the validator requires: the frame header (its weights, its anchors and its disclosure text,
which names the tambons of the real analysis the anchor was chosen on), the national vulnerability anchors with their
receipt hash, and the SHA-256 of the two protocol files. It exists so that the screens of plan section 7.2 can be built
before task E8 writes the first real overlay, and so that both parsers are tested on every state the signed protocols
name:

* every tier: T0 engine rows, T1 scenario rows in the lanes SCN and SCN-ENV, T2 own-candidate rows, T3 dated agency
  rows, and one T4 row, which is locked and carries no value;
* every reason code: the six of class rule v1 and ``insufficient_denominator`` (guardrail GR1, no class);
* every failed condition C1 to C8 of confidence rule v1, with the would-be class of each low-confidence row;
* the v2 class as a secondary axis, including "no v2 trigger met";
* an OBS row that is not event_aligned (guardrail GR7), and the three states of the headline slot (guardrail GR8);
* the three rights levels local, pitch and public among the inputs (guardrail GR6).

The component records come from ``floodguard.normalisation`` and the confidence records from
``floodguard.confidence``, both read from the two signed protocol files in force, applied to the invented inputs
below. FPPS and the v1 class come from ``floodguard.scoring.score_subdistricts``. The v2 result is laid out from
invented trigger inputs by the evaluation order of protocol v1a: the fixture exercises the shape of that axis and is
not the v2 wrapper of task E8. Two states cannot be shown with invented units and are left out: condition C3
``by_construction`` (protocol v1a grants it to product 4009 in the eight Mae Sai tambons only) and a tier T2 row that
passes the skill condition (protocol v1a evaluates two named detectors only).

The script also writes ``apps/web/src/lib/planning-protocol-binding.json``: the constants of the two protocol files
in force that the web parser checks every overlay against (``floodguard.planning_overlay.protocol_binding_record``).

Run from the repository root (it writes only the two fixture files and the binding file):

    python apps/web/scripts/planning-overlay-fixture.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import normalisation  # noqa: E402
from floodguard.confidence import ConfidenceInputs, derive_confidence  # noqa: E402
from floodguard.normalisation import NormalisationError, frame_record, protocol_hashes, read_protocol_in_force  # noqa: E402
from floodguard.planning_overlay import (  # noqa: E402
    CLOSURE_BASIS_PREFIX,
    SCHEMA_ID,
    SCHEMA_RELATIVE_PATH,
    SCHEMA_VERSION,
    V2_TRIGGER_ORDER,
    ProtocolBinding,
    expected_temporal_relation,
    load_overlay_schema,
    load_protocol_binding,
    overlay_text,
    protocol_binding_record,
    summarise_overlay,
)
from floodguard.scoring import SCORE_COMPONENTS, score_subdistricts  # noqa: E402

DOCS = ROOT / "docs" / "proposal_execution"
V1A = DOCS / "planning_protocol_v1a.json"
V1B = DOCS / "planning_protocol_v1b.json"
RECEIPTS = DOCS / "RECEIPTS.jsonl"
FIXTURES = ROOT / "apps" / "web" / "src" / "lib" / "__fixtures__"
FIXTURE = FIXTURES / "planning-assessment-overlay.fixture.json"
SUMMARY = FIXTURES / "planning-assessment-overlay.fixture.summary.json"
BINDING = ROOT / "apps" / "web" / "src" / "lib" / "planning-protocol-binding.json"

GENERATED_AT = "2026-10-04T00:00:00Z"
# The commit whose confidence.py and normalisation.py produced the records (the base of task E11).
CODE_COMMIT = "4624f8df5a88321031174afb573ccceb045ad674"
CASE_ID = "FX-CASE-01"
REFERENCE = date(2030, 1, 10)  # Invented: no real event has this date.
NOT_A_PLACE_EN = "(fixture, not a place)"
NOT_A_PLACE_TH = "(ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)"
FIXTURE_ROW_NOTE = "Fixture row: every input of this row is invented and the unit is not a place."
# Every invented input declares one invented source product, so that the fixture shows the field filled.
FIXTURE_SOURCE_PRODUCT = "fixture_invented_input"

AGENCY_DATED = "fx_agency_extent_dated"
AGENCY_LATE = "fx_agency_extent_late"
OWN_CANDIDATE = "fx_own_candidate"
SEASON_LAYER = "fx_season_layer"
ROUTING = "fx_routing_context"

# input_id: (role, name, rights level, acquisition date of a flood input)
INPUTS: dict[str, tuple[str, str, str, date | None]] = {
    AGENCY_DATED: ("flood_input", "Fixture agency extent A (invented, not a product)", "public", date(2030, 1, 11)),
    AGENCY_LATE: ("flood_input", "Fixture agency extent B, late date (invented, not a product)", "public", date(2030, 1, 20)),
    OWN_CANDIDATE: ("flood_input", "Fixture own candidate (invented, not a detector)", "public", date(2030, 1, 11)),
    SEASON_LAYER: ("flood_input", "Fixture season layer (invented, not a product)", "public", None),
    ROUTING: ("routing_context", "Fixture routing context (invented road graph)", "public", None),
    "fx_population": ("population", "Fixture resident counts (invented)", "public", None),
    "fx_age_structure": ("age_structure", "Fixture age counts (invented)", "public", None),
    "fx_boundaries": ("boundaries", "Fixture unit boundaries (invented)", "public", None),
    "fx_listed_shelters": ("facilities", "Fixture listed shelters (invented, pitch level)", "pitch", None),
    "fx_local_only_layer": ("other", "Fixture layer kept local (invented, local level)", "local", None),
}


def _unit(number: int, kind: str = "unit") -> dict[str, str]:
    prefix = "FX-U" if kind == "unit" else "FX-E"
    label_en = "Fixture unit" if kind == "unit" else "Fixture engine row"
    label_th = "หน่วยทดสอบ" if kind == "unit" else "แถวทดสอบเครื่องคำนวณ"
    return {
        "unit_id": f"{prefix}{number:02d}",
        "unit_name_en": f"{label_en} {number:02d} {NOT_A_PLACE_EN}",
        "unit_name_th": f"{label_th} {number:02d} {NOT_A_PLACE_TH}",
    }


# One entry per derived row (tiers T1 to T3). Every number is invented.
#   areas: flooded and total non-permanent-water land; people: residents inside the extent and unit residents;
#   access: service -> (residents with baseline access, residents newly losing it); routes: (losing all, with a route);
#   ages: (children 0-14, adults 60 and over); v2: invented inputs of the B, C and D triggers.
DERIVED_ROWS: list[dict[str, Any]] = [
    dict(key="obs-t3-class-a", unit=1, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(12, 40), people=(1600, 2000),
         access={"hospital": (1800, 1440), "main_road_entry": (1900, 1330)}, routes=(900, 1900), ages=(400, 520),
         v2=(False, False, False), retention=0.83),
    dict(key="obs-t3-class-b", unit=2, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(6, 40), people=(900, 1800),
         access={"hospital": (1600, 1000), "main_road_entry": (1700, 1050)}, routes=(1400, 1700), ages=(300, 420),
         v2=(True, False, False), retention=0.41),
    dict(key="obs-t3-class-c", unit=3, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(8, 40), people=(1020, 1500),
         access={"hospital": (1350, 720), "main_road_entry": (1400, 760)}, routes=(500, 1400), ages=(270, 390),
         v2=(False, True, False)),
    dict(key="obs-t3-class-d", unit=4, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(5, 50), people=(480, 1200),
         access={"hospital": (1100, 300), "main_road_entry": (1150, 350), "ddpm_located_shelter": (700, 150)},
         routes=(200, 1150), ages=(200, 330), v2=(False, False, True), retention=0.72),
    dict(key="obs-t3-no-v2-trigger", unit=5, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(9, 60), people=(700, 1400),
         access={"hospital": (1300, 500), "main_road_entry": (1350, 560)}, routes=(300, 1350), ages=(250, 330),
         v2=(False, False, False)),
    dict(key="obs-t3-low-priority-score", unit=6, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(1, 50), people=(60, 1000),
         access={"hospital": (900, 40), "main_road_entry": (950, 30)}, routes=(10, 950), ages=(160, 200),
         v2=(False, False, False)),
    dict(key="obs-t3-c2-not-event-aligned", unit=7, lane="OBS", tier="T3", flood=AGENCY_LATE, areas=(6, 40), people=(900, 1800),
         access={"hospital": (1600, 1000), "main_road_entry": (1700, 1050)}, routes=(1400, 1700), ages=(300, 420),
         v2=(True, False, False)),
    dict(key="obs-t3-c3-coverage", unit=8, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(5, 50), people=(480, 1200),
         access={"hospital": (1100, 300), "main_road_entry": (1150, 350)}, routes=(200, 1150), ages=(200, 330),
         v2=(False, False, True), coverage=0.55),
    dict(key="obs-t3-c4-input-uncertainty", unit=9, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(8, 40), people=(1020, 1500),
         access={"hospital": (1350, 720), "main_road_entry": (1400, 760)}, routes=(500, 1400), ages=(270, 390),
         v2=(False, True, False), pixel=(18, 14)),
    dict(key="obs-t3-c5-component-not-computed", unit=10, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(7, 35),
         people=(300, 800), access={"hospital": (0, 0), "main_road_entry": (0, 0)}, routes=(0, 0), ages=(150, 230),
         v2=(False, False, False), no_route=1.0, hospitals=0),
    dict(key="obs-t3-c6-gr1-no-class", unit=11, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(4, 20), people=(30, 60),
         access={"hospital": (50, 20), "main_road_entry": (55, 25)}, routes=(10, 55), ages=(12, 18),
         v2=(False, False, False)),
    dict(key="obs-t3-c7-baseline-no-route", unit=12, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(12, 40),
         people=(1600, 2000), access={"hospital": (1800, 1440), "main_road_entry": (1900, 1330)}, routes=(900, 1900),
         ages=(400, 520), v2=(False, False, False), no_route=0.25),
    dict(key="obs-t3-c8-no-hospital", unit=13, lane="OBS", tier="T3", flood=AGENCY_DATED, areas=(1, 50), people=(60, 1000),
         access={"hospital": (0, 0), "main_road_entry": (950, 30)}, routes=(10, 950), ages=(160, 200),
         v2=(False, False, False), hospitals=0),
    dict(key="obs-t2-c1-and-c4-own-candidate", unit=14, lane="OBS", tier="T2", flood=OWN_CANDIDATE, areas=(5, 50),
         people=(480, 1200), access={"hospital": (1100, 300), "main_road_entry": (1150, 350)}, routes=(200, 1150),
         ages=(200, 330), v2=(False, False, True), abstention=0.35),
    dict(key="obs-t2-c1-own-candidate", unit=15, lane="OBS", tier="T2", flood=OWN_CANDIDATE, areas=(8, 40),
         people=(1020, 1500), access={"hospital": (1350, 720), "main_road_entry": (1400, 760)}, routes=(500, 1400),
         ages=(270, 390), v2=(False, True, False), abstention=0.1, iou=0.52),
    dict(key="scn-t1-agency-base-class-a", unit=2, lane="SCN", tier="T1", flood=AGENCY_DATED, base="agency_product_as_provided",
         scenario=("FX-S1", "Fixture what-if: the three highest-ranked invented links are closed (invented scenario)."),
         areas=(12, 40), people=(1350, 1800), access={"hospital": (1600, 1250), "main_road_entry": (1700, 1300)},
         routes=(1500, 1700), ages=(300, 420), v2=(True, False, False)),
    dict(key="scn-t1-own-candidate-base", unit=14, lane="SCN", tier="T1", flood=OWN_CANDIDATE, base="own_t2_candidate",
         scenario=("FX-S2", "Fixture what-if: the invented own candidate grown by one pixel (invented scenario)."),
         areas=(9, 60), people=(700, 1400), access={"hospital": (1300, 500), "main_road_entry": (1350, 560)},
         routes=(300, 1350), ages=(250, 330), v2=(False, False, False), abstention=0.1, iou=0.52),
    dict(key="scn-env-t1-class-c", unit=3, lane="SCN-ENV", tier="T1", flood=SEASON_LAYER, base="agency_product_as_provided",
         scenario=("FX-ENV", "Fixture season-envelope scenario: every area the invented season layer maps is treated as flooded at once."),
         areas=(10, 40), people=(1050, 1500), access={"hospital": (1350, 740), "main_road_entry": (1400, 780)},
         routes=(520, 1400), ages=(270, 390), v2=(False, False, False), retention=0.66),
    dict(key="scn-env-t1-c8-no-hospital", unit=13, lane="SCN-ENV", tier="T1", flood=SEASON_LAYER, base="agency_product_as_provided",
         scenario=("FX-ENV", "Fixture season-envelope scenario: every area the invented season layer maps is treated as flooded at once."),
         areas=(10, 50), people=(720, 1000), access={"hospital": (0, 0), "main_road_entry": (950, 700)},
         routes=(600, 950), ages=(160, 200), v2=(False, False, False), hospitals=0),
]

# Engine rows (tier T0): synthetic component values in the order of SCORE_COMPONENTS, and a declared confidence.
ENGINE_ROWS: list[tuple[str, tuple[float, float, float, float, float], str]] = [
    ("eng-t0-class-a", (70, 80, 75, 60, 50), "medium"),
    ("eng-t0-class-b", (60, 50, 60, 80, 40), "medium"),
    ("eng-t0-class-c", (60, 66, 52, 40, 30), "medium"),
    ("eng-t0-class-d", (80, 40, 30, 20, 60), "medium"),
    ("eng-t0-low-priority-score", (20, 10, 5, 0, 30), "medium"),
    ("eng-t0-declared-low", (70, 80, 75, 60, 50), "low"),
]


def _input_sha256(input_id: str) -> str:
    """An invented input has no file: its hash is the SHA-256 of a label, and says so in the assumptions."""

    return hashlib.sha256(f"floodguard planning overlay fixture input: {input_id}".encode("utf-8")).hexdigest()


def _inputs() -> list[dict[str, Any]]:
    return [
        {
            "input_id": input_id,
            "role": role,
            "name": name,
            "source_product": FIXTURE_SOURCE_PRODUCT,
            "acquisition_date": None if acquired is None else acquired.isoformat(),
            "sha256": _input_sha256(input_id),
            "rights_level": rights_level,
            "licence": "none: invented fixture input",
            "attribution": "FloodGuard fixture (invented, not a source)",
            "change_notice": None,
            "source_timestamp": "invented for the fixture on 2026-10-04",
        }
        for input_id, (role, name, rights_level, acquired) in INPUTS.items()
    ]


def _scored(values: dict[str, float], confidence_class: str, weights: dict[str, float]) -> tuple[float, str, str]:
    """FPPS, v1 class and reason code from the unchanged scorer."""

    table = pd.DataFrame([{"subdistrict_id": "row", "subdistrict_name": "row", "confidence_class": confidence_class, **values}])
    row = score_subdistricts(table, weights).iloc[0]
    return float(row["fpps_0_100"]), str(row["action_class"]), str(row["action_reason_code"])


def _headline(retention: float | None, retention_min: float) -> dict[str, Any]:
    status = "not_evaluated"
    if retention is not None:
        status = "headline_eligible" if retention >= retention_min else "unstable_verify"
    return {
        "guardrail": "GR8_headline_stability",
        "status": status,
        "class_retention": retention,
        "class_retention_min": retention_min,
    }


def _scoring_block(
    values: dict[str, float | None],
    confidence_class: str,
    gr1_applies: bool,
    frame_header: dict[str, Any],
) -> dict[str, Any]:
    """FPPS, binding class, reason code, would-be class and leave-one-component-out of one row."""

    if any(value is None for value in values.values()):
        # Low confidence gives class E by the first rule of class rule v1, whatever the FPPS would have been.
        return {"fpps_0_100": None, "action_class": "E", "action_reason_code": "low_confidence",
                "would_be_class": None, "leave_one_component_out": None}
    complete = {name: float(value) for name, value in values.items() if value is not None}
    fpps, action_class, reason_code = _scored(complete, confidence_class, frame_header["weights"])
    would_be = None
    if confidence_class == "low" and not gr1_applies:
        would_be = _scored(complete, "medium", frame_header["weights"])[1]
    loco = {}
    for dropped in SCORE_COMPONENTS:
        left_out = _scored(complete, confidence_class, frame_header["leave_one_component_out_weights"][dropped])
        loco[dropped] = {"fpps_0_100": left_out[0], "action_class": None if gr1_applies else left_out[1]}
    if gr1_applies:
        action_class, reason_code = None, "insufficient_denominator"
    return {"fpps_0_100": fpps, "action_class": action_class, "action_reason_code": reason_code,
            "would_be_class": would_be, "leave_one_component_out": loco}


def _class_v2(
    spec: dict[str, Any],
    scoring: dict[str, Any],
    confidence_class: str,
    gr1_applies: bool,
    values: dict[str, float | None],
    dependent_share: float,
    v1a: dict[str, Any],
    frame_header: dict[str, Any],
) -> dict[str, Any]:
    """Lay out the secondary v2 axis from invented trigger inputs, in the evaluation order of protocol v1a."""

    block = {"class_rule_version": "class_rule_v2", "label": "secondary", "binding": False}
    if gr1_applies:
        return {**block, "result": None, "trigger_evidence": []}
    parameters = v1a["class_rules"]["v2"]["parameters"]
    fpps_min, exposure_floor = parameters["fpps_min"], parameters["exposure_floor_for_non_e"]
    percentile = parameters["national_dependent_share_percentile"]
    threshold = frame_header["vulnerability_anchors"]["values"][percentile]
    fpps = scoring["fpps_0_100"]
    exposure = values["exposure_0_100"]
    link, facility, recurrence = spec["v2"]
    scored_enough = fpps is not None and fpps >= fpps_min
    met = {
        "E": confidence_class == "low" or (exposure is not None and exposure < exposure_floor) or not scored_enough,
        "A": scoring["action_class"] == "A" and dependent_share >= threshold,
        "B": link,
        "C": scored_enough and confidence_class == "medium" and facility,
        "D": scored_enough and recurrence,
    }
    shown = lambda value: "not computed" if value is None else f"{value:.2f}"  # noqa: E731
    evidence = {
        "E": f"Confidence {confidence_class}; exposure {shown(exposure)} against a floor of {exposure_floor}; "
             f"FPPS {shown(fpps)} against a minimum of {fpps_min}.",
        "A": f"v1 class {scoring['action_class']}; dependent share {dependent_share:.4f} against the national {percentile} of {threshold}.",
        "B": f"Fixture: invented outcome of the critical-link isolation test ({str(link).lower()}).",
        "C": f"Fixture: invented outcome of the serving-facility test ({str(facility).lower()}).",
        "D": f"Fixture: invented recurrence flag ({str(recurrence).lower()}).",
    }
    first = next((trigger for trigger in V2_TRIGGER_ORDER if met[trigger]), None)
    return {
        **block,
        "result": first or v1a["class_rules"]["v2"]["evaluation"]["otherwise"],
        "trigger_evidence": [
            {"trigger": trigger, "met": bool(met[trigger]), "evidence": evidence[trigger]} for trigger in V2_TRIGGER_ORDER
        ],
    }


def _derived_row(spec: dict[str, Any], binding: ProtocolBinding, v1a: dict[str, Any], frame_header: dict[str, Any]) -> dict[str, Any]:
    frame, rule = binding.frame, binding.rule
    flooded_area, land_area = spec["areas"]
    inside, residents = spec["people"]
    losing, with_route = spec["routes"]
    children, older = spec["ages"]
    services = {
        service.service: {
            "mode": service.mode,
            "threshold_minutes": service.threshold_minutes,
            "baseline_access_residents": spec["access"][service.service][0],
            "newly_lost_residents": spec["access"][service.service][1],
        }
        for service in frame.access_services
        if service.service in spec["access"]
    }
    calls = {
        "flood_likelihood_0_100": lambda: normalisation.flood_likelihood(
            frame, flooded_non_permanent_water_land_area=flooded_area, non_permanent_water_land_area=land_area),
        "exposure_0_100": lambda: normalisation.exposure(frame, residents_inside_flood_extent=inside, unit_residents=residents),
        "access_gap_0_100": lambda: normalisation.access_gap(frame, services=services),
        "road_criticality_0_100": lambda: normalisation.road_criticality(
            frame, residents_losing_all_routes=losing, residents_with_baseline_route=with_route),
        "vulnerability_context_0_100": lambda: normalisation.vulnerability_context(
            frame, children_0_14=children, older_60_plus=older, residents=residents),
    }
    components: dict[str, Any] = {}
    assumptions = [FIXTURE_ROW_NOTE]
    for name in SCORE_COMPONENTS:
        try:
            components[name] = calls[name]()
        except NormalisationError as error:
            components[name] = None
            assumptions.append(f"{name} is not computed: {error}.")
    values = {name: None if record is None else record["value_0_100"] for name, record in components.items()}
    exposure_value = values["exposure_0_100"]
    grow, shrink = spec.get("pixel", (4, 5))
    role, flood_name, _rights, acquired = INPUTS[spec["flood"]]
    own_candidate = spec["tier"] == "T2" or spec.get("base") == "own_t2_candidate"
    confidence = derive_confidence(
        ConfidenceInputs(
            unit_id=_unit(spec["unit"])["unit_id"],
            lane=spec["lane"],
            tier=spec["tier"],
            flood_input=flood_name,
            scenario_base=spec.get("base"),
            acquisition_date=acquired,
            case_reference_date=REFERENCE,
            unit_valid_coverage=spec.get("coverage", 0.95),
            coverage_by_construction=False,
            exposure_plus_one_pixel_0_100=min(100.0, exposure_value + grow),
            exposure_minus_one_pixel_0_100=max(0.0, exposure_value - shrink),
            t2_abstention_fraction=spec.get("abstention") if own_candidate else None,
            t2_geoid_held_out_test_iou=spec.get("iou") if own_candidate else None,
            component_status={name: "computed" if components[name] is not None else "not_computed" for name in SCORE_COMPONENTS},
            unit_residents=residents,
            baseline_vehicle_no_route_share=spec.get("no_route", 0.04),
            hospitals_reachable_at_baseline=spec.get("hospitals", 2),
        ),
        rule,
    )
    assert role == "flood_input"
    confidence_class = confidence["confidence_class"]
    gr1_applies = confidence["guardrail_gr1"]["applies"]
    scoring = _scoring_block(values, confidence_class, gr1_applies, frame_header)
    scenario = spec.get("scenario")
    level = "central"
    assumptions.append(
        f"Road closure is modelled from the invented flood input (closure_rule_v1, {level} level): a flood "
        "intersection does not prove a road closure."
    )
    retention_min = next(row for row in v1a["guardrails"] if row["id"] == "GR8_headline_stability")["parameters"]["class_retention_min"]
    return {
        "row_id": f"{CASE_ID}:{spec['key']}",
        **_unit(spec["unit"]),
        "tier": spec["tier"],
        "lane": spec["lane"],
        "temporal_relation": expected_temporal_relation(confidence["measurements"], rule.recency_window_days),
        "flood_input": flood_name,
        "scenario": None if scenario is None else {"id": scenario[0], "declaration": scenario[1]},
        "lineage": {
            "flood_input_id": spec["flood"],
            "routing_context_id": ROUTING,
            "closure_rule": {"version": "closure_rule_v1", "level": level, "closure_basis": f"{CLOSURE_BASIS_PREFIX}{spec['flood']}"},
        },
        "normalisation_version": frame.version,
        "components": components,
        "fpps_0_100": scoring["fpps_0_100"],
        "confidence": confidence,
        "action_class": scoring["action_class"],
        "action_reason_code": scoring["action_reason_code"],
        "would_be_class": scoring["would_be_class"],
        "class_v2": _class_v2(spec, scoring, confidence_class, gr1_applies, values,
                              components["vulnerability_context_0_100"]["dependent_share"], v1a, frame_header),
        "leave_one_component_out": scoring["leave_one_component_out"],
        "headline_stability": _headline(None if scoring["action_class"] is None else spec.get("retention"), retention_min),
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": GENERATED_AT,
        "assumptions": assumptions,
    }


def _engine_row(number: int, key: str, numbers: tuple[float, ...], confidence_class: str,
                frame_header: dict[str, Any], retention_min: float) -> dict[str, Any]:
    values = {name: float(value) for name, value in zip(SCORE_COMPONENTS, numbers)}
    scoring = _scoring_block(dict(values), confidence_class, False, frame_header)
    return {
        "row_id": f"{CASE_ID}:{key}",
        **_unit(number, "engine"),
        "tier": "T0",
        "lane": "ENG",
        "temporal_relation": None,
        "flood_input": None,
        "scenario": None,
        "lineage": {"flood_input_id": None, "routing_context_id": None, "closure_rule": None},
        "normalisation_version": frame_header["normalisation_version"],
        "components": {name: {"component": name, "value_0_100": value, "synthetic": True} for name, value in values.items()},
        "fpps_0_100": scoring["fpps_0_100"],
        "confidence": {
            "confidence_class": confidence_class,
            "confidence_kind": "declared",
            "declaration": f"Engine row: confidence {confidence_class} was set by declaration. Rule v1 derives none for tier T0.",
        },
        "action_class": scoring["action_class"],
        "action_reason_code": scoring["action_reason_code"],
        "would_be_class": scoring["would_be_class"],
        "class_v2": None,
        "leave_one_component_out": scoring["leave_one_component_out"],
        "headline_stability": _headline(None, retention_min),
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": GENERATED_AT,
        "assumptions": [
            "Engine row: synthetic component values that test the scorer. It is not a place and no flood input is behind it.",
        ],
    }


def _locked_row(frame_header: dict[str, Any], retention_min: float) -> dict[str, Any]:
    return {
        "row_id": f"{CASE_ID}:t4-locked",
        **_unit(1),
        "tier": "T4",
        "lane": None,
        "temporal_relation": None,
        "flood_input": None,
        "scenario": None,
        "lineage": {"flood_input_id": None, "routing_context_id": None, "closure_rule": None},
        "normalisation_version": frame_header["normalisation_version"],
        "components": {name: None for name in SCORE_COMPONENTS},
        "fpps_0_100": None,
        "confidence": None,
        "action_class": None,
        "action_reason_code": None,
        "would_be_class": None,
        "class_v2": None,
        "leave_one_component_out": None,
        "headline_stability": _headline(None, retention_min),
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": GENERATED_AT,
        "assumptions": [
            "Tier T4 (qualified) is locked: it is not reached in this release, so the row carries no value.",
            FIXTURE_ROW_NOTE,
        ],
    }


def build_overlay() -> dict[str, Any]:
    """Assemble the fixture overlay under the two protocol files in force."""

    binding = load_protocol_binding(V1A, V1B, RECEIPTS)
    v1a, _sha256 = read_protocol_in_force("v1a", V1A, RECEIPTS)
    frame_header = frame_record(binding.frame)
    retention_min = next(row for row in v1a["guardrails"] if row["id"] == "GR8_headline_stability")["parameters"]["class_retention_min"]
    rows = [_derived_row(spec, binding, v1a, frame_header) for spec in DERIVED_ROWS]
    rows += [
        _engine_row(number, key, numbers, confidence_class, frame_header, retention_min)
        for number, (key, numbers, confidence_class) in enumerate(ENGINE_ROWS, start=1)
    ]
    rows.append(_locked_row(frame_header, retention_min))
    inputs = _inputs()
    levels = ("local", "pitch", "public")
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_id": SCHEMA_ID,
        "dataset_mode": "fixture_demo",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "accepted_fpps": None,
        "accepted_action_class": None,
        "source_timestamp": GENERATED_AT,
        "generated_at": GENERATED_AT,
        "source_name": "FloodGuard planning assessment overlay fixture (invented case, not a place)",
        "data_version": "planning-overlay-fixture-1",
        "git_commit": CODE_COMMIT,
        "case": {
            "case_id": CASE_ID,
            "kind": "fixture",
            "title_en": "Fixture case 01 (fixture, not a place)",
            "title_th": "กรณีทดสอบ 01 (ข้อมูลทดสอบ ไม่ใช่สถานที่จริง)",
            "frame": "Fifteen invented units and six engine rows (fixture, not a place)",
            "case_reference_date": REFERENCE.isoformat(),
            "fixture_notice": "Fixture, not a place: the units, inputs, dates and unit numbers in this file are invented "
                              "to exercise the parsers and the screens, and no row describes a real tambon, flood or "
                              "detector. The frame header with its disclosure text, the national anchors and the "
                              "protocol hashes are those of the signed protocols.",
        },
        "protocol_sha256": protocol_hashes(binding.frame),
        "evidence_tier_model_version": "evidence_tiers_v1",
        "normalisation_version": binding.frame.version,
        "confidence_rule_version": binding.rule.version,
        "class_rule_version": v1a["class_rules"]["v1"]["version"],
        "secondary_class_rule_version": v1a["class_rules"]["v2"]["version"],
        "scoring_frame": frame_header,
        "publication_eligibility": min((item["rights_level"] for item in inputs), key=levels.index),
        "inputs": inputs,
        "assumptions": [
            "Fixture, not a place: every unit, flood input, date and unit number is invented. The dates are in 2030.",
            "The frame header (weights, anchors and the anchor disclosure text, which names real tambons), the "
            "national vulnerability anchors with their receipt hash and the protocol hashes are those of the signed "
            "protocols v1a and v1b, as in every overlay. They describe the protocol, not a unit of this file.",
            "The component and confidence records were produced by floodguard.normalisation and floodguard.confidence "
            "under the two signed protocol files, from the invented inputs each record echoes.",
            "An invented input has no file: its sha256 is the SHA-256 of a fixture label.",
            "The source timestamp of the fixture is the time it was written, because its inputs have no source.",
            "The v2 results are laid out from invented trigger inputs by the evaluation order of protocol v1a. They "
            "show the shape of the secondary axis and are not the output of the v2 wrapper.",
            "The headline-stability values are invented: no ensemble has run.",
            "Planning guidance only. Not an official warning. Class E never means safe.",
        ],
        "rows": rows,
    }


def fixture_text() -> str:
    """The fixture file: the overlay, accepted by the schema and by the strict validator, as ASCII JSON."""

    binding = load_protocol_binding(V1A, V1B, RECEIPTS)
    schema = load_overlay_schema(ROOT / SCHEMA_RELATIVE_PATH)
    return overlay_text(build_overlay(), schema, binding=binding)


def summary_text(text: str | None = None) -> str:
    """The summary file: the SHA-256 of the fixture bytes and what the Python side counts in it."""

    text = fixture_text() if text is None else text
    document = {
        "fixture": FIXTURE.name,
        "written_by": "apps/web/scripts/planning-overlay-fixture.py",
        "file_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        "summary": summarise_overlay(json.loads(text)),
    }
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def binding_text() -> str:
    """The binding file: the protocol constants the web parser checks an overlay against, as ASCII JSON."""

    record = protocol_binding_record(load_protocol_binding(V1A, V1B, RECEIPTS))
    return json.dumps(record, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def main() -> None:
    text = fixture_text()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    # LF on every platform, matching the repository's eol=lf policy.
    FIXTURE.write_text(text, encoding="ascii", newline="\n")
    SUMMARY.write_text(summary_text(text), encoding="ascii", newline="\n")
    BINDING.write_text(binding_text(), encoding="ascii", newline="\n")
    summary = json.loads(SUMMARY.read_text(encoding="ascii"))["summary"]
    print(f"wrote {FIXTURE.relative_to(ROOT).as_posix()} ({summary['row_count']} rows, {len(text)} bytes), "
          f"{SUMMARY.relative_to(ROOT).as_posix()} and {BINDING.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
