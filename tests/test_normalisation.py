"""Planning frame v1: the national vulnerability anchors and the five components, on invented units.

No test here reads a real raster or boundary, and none computes an FPPS or an
A-E class. Component values are computed for invented units only (their IDs
start with SYN or U); no real unit is scored. The anchors, weights and service
thresholds are read from the signed protocol files, so the expected values
follow the files. The one test that looks at the committed receipt checks its
shape and that protocol v1b repeats it exactly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import json
import math
import random
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from floodguard.normalisation import (
    ANCHOR_PERCENTILES,
    ANCHOR_VERSION,
    COMPONENT_FUNCTIONS,
    MIN_UNIT_RESIDENTS,
    NORMALISATION_FRAME_VERSION,
    VERIFY_TOLERANCE,
    BatchScalingError,
    NormalisationError,
    PlanningFrame,
    access_gap,
    dependent_share,
    exposure,
    flood_likelihood,
    frame_record,
    leave_one_component_out_weights,
    load_planning_frame,
    national_vulnerability_anchors,
    percentile_linear,
    percentile_weighted,
    planning_frame_from_protocols,
    protocol_hashes,
    read_protocol_in_force,
    reject_batch_scaled_components,
    road_criticality,
    select_anchor_units,
    vulnerability_context,
)
from floodguard.scoring import DEFAULT_WEIGHTS, SCORE_COMPONENTS, validate_weights
from floodguard.sensitivity import WEIGHT_SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json"
PROTOCOL = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
PROTOCOL_V1A = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1a.json"
RECEIPTS = ROOT / "docs" / "proposal_execution" / "RECEIPTS.jsonl"
SCRIPT = ROOT / "scripts" / "build_national_vulnerability_anchors.py"
MODULE = ROOT / "src" / "floodguard" / "normalisation.py"


def _units(count: int = 200) -> list[dict]:
    """Invented units whose dependent share rises evenly from 0.20 to 0.60."""

    rows = []
    for index in range(count):
        share = 0.20 + 0.40 * index / (count - 1)
        residents = 1000.0 + 10 * index
        rows.append({
            "unit_id": f"U{index:04d}",
            "residents": residents,
            "children_0_14": residents * share * 0.4,
            "older_60_plus": residents * share * 0.6,
        })
    return rows


def test_dependent_share_is_children_plus_older_over_all_residents() -> None:
    assert dependent_share(20, 30, 100) == pytest.approx(0.5)
    assert dependent_share(0, 0, 10) == 0.0
    assert dependent_share(4, 6, 10) == 1.0
    # A float sum of cells may exceed the total by a rounding error; the share is capped at 1, not refused.
    assert (4 + 6.000000001) / 10 > 1.0
    assert dependent_share(4, 6.000000001, 10) == 1.0


@pytest.mark.parametrize("arguments", [
    (1, 1, 0), (-1, 1, 10), (1, float("nan"), 10), (8, 8, 10), (1, 1, float("inf")), (True, 1, 10), ("1", 1, 10),
])
def test_dependent_share_refuses_bad_counts(arguments: tuple) -> None:
    with pytest.raises(NormalisationError):
        dependent_share(*arguments)


def test_percentile_is_linear_interpolation_between_order_statistics() -> None:
    assert percentile_linear([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile_linear([4, 1, 3, 2], 0) == 1
    assert percentile_linear([4, 1, 3, 2], 100) == 4
    assert percentile_linear([7.0], 90) == 7.0
    rng = np.random.default_rng(20261002)
    sample = rng.random(997).tolist()
    for percent in (*ANCHOR_PERCENTILES, 33.3):
        assert percentile_linear(sample, percent) == pytest.approx(float(np.percentile(sample, percent)), abs=1e-12)


@pytest.mark.parametrize("values, percent", [([], 50), ([1, 2], -1), ([1, 2], 101), ([1, float("nan")], 50)])
def test_percentile_refuses_bad_input(values: list, percent: float) -> None:
    with pytest.raises(NormalisationError):
        percentile_linear(values, percent)


def test_weighted_percentile_follows_the_weights() -> None:
    assert percentile_weighted([1, 2, 3], [1, 1, 1], 50) == 2
    assert percentile_weighted([1, 2, 3], [98, 1, 1], 50) == 1
    assert percentile_weighted([1, 2, 3], [1, 1, 98], 50) == 3
    for bad in (([1, 2], [1], 50), ([1], [0], 50), ([], [], 50), ([1], [1], 120)):
        with pytest.raises(NormalisationError):
            percentile_weighted(*bad)
    for bad in (([float("nan")], [1], 50), ([1], [float("inf")], 50)):
        with pytest.raises(NormalisationError, match="finite values and positive weights"):
            percentile_weighted(*bad)
    # Ten weights of 0.1 add up to just under their exact sum, so the running total never reaches
    # the target of the 100th percentile; the highest value is still the answer.
    assert percentile_weighted(list(range(10)), [0.1] * 10, 100) == 9


def test_unit_set_drops_small_units_and_units_without_age_support() -> None:
    units = _units(5) + [
        {"unit_id": "SMALL", "residents": MIN_UNIT_RESIDENTS - 0.5, "children_0_14": 10.0, "older_60_plus": 10.0},
        {"unit_id": "EDGE", "residents": MIN_UNIT_RESIDENTS, "children_0_14": 30.0, "older_60_plus": 20.0},
        {"unit_id": "EMPTY", "residents": None, "children_0_14": None, "older_60_plus": None},
    ]
    used, counts = select_anchor_units(units)
    assert [row["unit_id"] for row in used] == sorted(row["unit_id"] for row in used)
    assert {row["unit_id"] for row in used} == {f"U{index:04d}" for index in range(5)} | {"EDGE"}
    assert counts == {
        "units_read": 8, "units_used": 6, "excluded_no_age_support": 1, "excluded_below_min_residents": 1,
    }
    edge = next(row for row in used if row["unit_id"] == "EDGE")
    assert edge["dependent_share"] == pytest.approx(0.5)


def test_unit_set_refuses_repeated_or_incomplete_records() -> None:
    with pytest.raises(NormalisationError, match="unique"):
        select_anchor_units([*_units(2), _units(2)[0]])
    with pytest.raises(NormalisationError, match="lacks"):
        select_anchor_units([{"unit_id": "A", "residents": 200.0}])
    for bad in (0, True, float("inf"), float("nan")):
        with pytest.raises(NormalisationError, match="min_residents"):
            select_anchor_units(_units(2), min_residents=bad)
    with pytest.raises(NormalisationError, match="present and unique"):
        select_anchor_units([{**_units(2)[0], "unit_id": ""}])


def test_anchors_are_unweighted_percentiles_of_the_unit_shares() -> None:
    units = _units()
    result = national_vulnerability_anchors(units)
    shares = [(row["children_0_14"] + row["older_60_plus"]) / row["residents"] for row in units]
    assert set(result["values"]) == {"P5", "P10", "P75", "P90", "P95"}
    for percent in ANCHOR_PERCENTILES:
        assert result["values"][f"P{percent}"] == pytest.approx(float(np.percentile(shares, percent)), abs=5e-7)
        assert result["values"][f"P{percent}"] == round(result["values_full_precision"][f"P{percent}"], 6)
    values = result["values"]
    assert values["P5"] < values["P10"] < values["P75"] < values["P90"] < values["P95"]
    assert result["unit_count"] == 200 and result["excluded_unit_count"] == 0
    assert result["distribution"]["minimum"] == pytest.approx(0.20)
    assert result["distribution"]["maximum"] == pytest.approx(0.60)


def test_anchors_do_not_depend_on_unit_order_or_population_size() -> None:
    units = _units()
    reference = national_vulnerability_anchors(units)["values"]
    assert national_vulnerability_anchors(list(reversed(units)))["values"] == reference
    scaled = [
        {**row, "residents": row["residents"] * 7, "children_0_14": row["children_0_14"] * 7,
         "older_60_plus": row["older_60_plus"] * 7}
        for row in units
    ]
    assert national_vulnerability_anchors(scaled)["values"] == reference


def test_degenerate_or_empty_frames_are_refused() -> None:
    same = [
        {"unit_id": f"S{index}", "residents": 500.0, "children_0_14": 100.0, "older_60_plus": 100.0}
        for index in range(20)
    ]
    with pytest.raises(NormalisationError, match="degenerate"):
        national_vulnerability_anchors(same)
    with pytest.raises(NormalisationError, match="no unit"):
        national_vulnerability_anchors([
            {"unit_id": "A", "residents": 5.0, "children_0_14": 1.0, "older_60_plus": 1.0},
        ])


def test_builder_hashes_the_unit_table_without_writing_it() -> None:
    spec = importlib.util.spec_from_file_location("build_national_vulnerability_anchors", SCRIPT)
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    units = _units(4)
    first = builder.unit_table_sha256(units)
    assert first == builder.unit_table_sha256([dict(row) for row in units]) and len(first) == 64
    changed = [dict(row) for row in units]
    changed[0]["residents"] += 1
    assert builder.unit_table_sha256(changed) != first
    alternatives = builder.alternatives(units)
    assert "Not used" in alternatives["note"]
    assert set(alternatives["resident_weighted_same_units"]) == {"P5", "P10", "P75", "P90", "P95"}
    # No unit of the invented set is a Bangkok khwaeng, so that alternative is not shown.
    assert alternatives["bangkok_khwaeng_units"] == 0 and "without_bangkok_khwaeng" not in alternatives
    encoded = builder.encode({"a": 1})
    assert encoded.endswith(b"\n") and b"\r" not in encoded


def test_builder_shows_the_anchors_without_bangkok_khwaeng(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("build_national_vulnerability_anchors", SCRIPT)
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    units = _units(200)
    # Give the 40 units with the lowest share a Bangkok code: leaving them out must raise the low anchors.
    for index, row in enumerate(units):
        row["unit_id"] = f"{builder.BANGKOK_UNIT_PREFIX}{index:04d}" if index < 40 else f"TH99{index:04d}"
    alternatives = builder.alternatives(units)
    assert alternatives["bangkok_khwaeng_units"] == 40
    without = alternatives["without_bangkok_khwaeng"]
    assert without["unit_count"] == 160
    everyone = national_vulnerability_anchors(units)["values"]
    kept = [row for row in units if not row["unit_id"].startswith(builder.BANGKOK_UNIT_PREFIX)]
    expected = national_vulnerability_anchors(kept)["values"]
    assert {key: without[key] for key in expected} == expected
    assert without["P5"] > everyone["P5"] and without["P10"] > everyone["P10"]
    weighted = alternatives["without_bangkok_khwaeng_resident_weighted"]
    assert weighted["unit_count"] == 160 and set(expected) <= set(weighted)

    # A replaced receipt names the one it supersedes and says which figures are the same.
    previous = tmp_path / "receipt.json"
    previous.write_bytes(builder.encode(
        {"generated_at_utc": "2026-10-02T00:00:00Z", "values": everyone, "unit_count": 200}
    ))
    note = builder.supersedes(previous, {"values": everyone, "unit_count": 199}, "a test reason")
    assert note["receipt_sha256"] == builder.sha256_file(previous) and note["reason"] == "a test reason"
    assert note["generated_at_utc"] == "2026-10-02T00:00:00Z"
    assert note["same_as_superseded"]["values"] is True and note["same_as_superseded"]["unit_count"] is False
    assert note["all_same"] is False


def test_committed_receipt_carries_the_required_fields_and_matches_the_protocol() -> None:
    if not RECEIPT.exists():
        pytest.skip("the anchors have not been computed on this checkout")
    raw = RECEIPT.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    receipt = json.loads(raw.decode("ascii"))
    assert receipt["schema_version"] == "floodguard.national_vulnerability_anchors.v1"
    assert receipt["official_warning"] is False and receipt["operational_status"] == "non_operational"
    assert receipt["source_timestamp"] and receipt["confidence_class"] == "low" and receipt["assumptions"]
    # The unit set and the percentile rule are an owner decision, so the receipt is a candidate measurement.
    assert receipt["status"] == "candidate_measurement" and "owner decision" in receipt["status_note"]
    values = receipt["values"]
    assert values["P5"] < values["P10"] < values["P75"] < values["P90"] < values["P95"]
    assert all(0 < value < 1 for value in values.values())
    assert receipt["unit_count"] + receipt["excluded_unit_count"] == receipt["counts"]["units_read"]
    # No value for a single tambon is published: no key or string names a unit code.
    assert "TH5" not in raw.decode("ascii") and "adm3_pcode\":" not in raw.decode("ascii")

    anchors = json.loads(PROTOCOL.read_text(encoding="utf-8"))["national_vulnerability_anchors"]
    assert receipt["input_hashes"]["age_acquisition_manifest_sha256"] == anchors["inputs"]["age_rasters"]["manifest_sha256"]
    assert receipt["input_hashes"]["tambon_boundaries_sha256"] == anchors["inputs"]["tambon_boundaries"]["sha256"]
    if anchors["values"]["P10"] is None:
        pytest.skip("open item OI-08 is not closed yet")
    assert anchors["values"] == values
    assert anchors["output_receipt"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (ROOT / anchors["output_receipt"]["path"]) == RECEIPT
    assert anchors["output_receipt"]["unit_count"] == receipt["unit_count"]
    assert anchors["output_receipt"]["excluded_unit_count"] == receipt["excluded_unit_count"]


# ---------------------------------------------------------------------------
# Frame v1: the constants are read from the two signed protocol files
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def protocols() -> dict[str, dict[str, Any]]:
    return {
        "v1a": json.loads(PROTOCOL_V1A.read_text(encoding="utf-8")),
        "v1b": json.loads(PROTOCOL.read_text(encoding="utf-8")),
    }


@pytest.fixture(scope="module")
def frame() -> PlanningFrame:
    return load_planning_frame(PROTOCOL_V1A, PROTOCOL, RECEIPTS)


def _change(protocol: dict[str, Any], pointer: str, value: Any) -> dict[str, Any]:
    """Return a copy of a protocol with one value replaced (``DELETE`` removes the key)."""

    changed = deepcopy(protocol)
    node: Any = changed
    parts = pointer.split("/")
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last: Any = int(parts[-1]) if isinstance(node, list) else parts[-1]
    if value == "DELETE":
        del node[last]
    else:
        node[last] = value
    return changed


def _services(frame: PlanningFrame, counts: dict[str, tuple[Any, Any]]) -> dict[str, dict[str, Any]]:
    """Service entries with the protocol's mode and threshold and invented (baseline, newly lost) counts."""

    declared = {service.service: service for service in frame.access_services}
    return {
        name: {
            "mode": declared[name].mode,
            "threshold_minutes": declared[name].threshold_minutes,
            "baseline_access_residents": baseline,
            "newly_lost_residents": lost,
        }
        for name, (baseline, lost) in counts.items()
    }


def test_frame_is_read_from_the_two_protocols_in_force(frame: PlanningFrame, protocols: dict[str, dict[str, Any]]) -> None:
    signed = protocols["v1a"]["scoring_frame"]
    components = signed["components"]
    flood = components["flood_likelihood_0_100"]
    assert frame.version == signed["version"] == NORMALISATION_FRAME_VERSION
    assert dict(frame.weights) == signed["weights"] == DEFAULT_WEIGHTS
    assert frame.flood_anchor == flood["anchor"]
    assert list(frame.flood_anchor_sensitivity) == flood["anchor_sensitivity_one_at_a_time"]
    assert frame.flood_anchor_disclosure == flood["anchor_disclosure"]
    assert dict(frame.permanent_water) == {
        "source": flood["permanent_water"]["source"],
        "class": flood["permanent_water"]["class"],
    }
    access = components["access_gap_0_100"]
    declared = [(row.service, row.mode, row.threshold_minutes, row.level) for row in frame.access_services]
    assert declared == [
        *((row["service"], row["mode"], row["threshold_minutes"], "public") for row in access["public_level_services"]),
        *((row["service"], row["mode"], row["threshold_minutes"], "pitch") for row in access["pitch_level_adds"]),
    ]
    anchors = protocols["v1b"]["national_vulnerability_anchors"]
    assert dict(frame.vulnerability_anchors) == anchors["values"]
    vulnerability = components["vulnerability_context_0_100"]
    assert frame.vulnerability_bounds == ("P10", "P90")
    assert [f"national_{key}" for key in frame.vulnerability_bounds] == [
        vulnerability["lower_anchor"], vulnerability["upper_anchor"],
    ]
    assert [f"national_{key}" for key in frame.vulnerability_sensitivity_bounds] == [
        vulnerability["anchor_sensitivity"]["lower"], vulnerability["anchor_sensitivity"]["upper"],
    ]
    assert frame.vulnerability_anchor_receipt_sha256 == anchors["output_receipt"]["sha256"]
    assert frame.normalisation_rule == signed["normalisation"] and "No batch scaling" in frame.normalisation_rule
    assert dict(frame.definitions) == {name: components[name]["definition"] for name in SCORE_COMPONENTS}
    assert dict(frame.protocol_sha256) == {
        "v1a": hashlib.sha256(PROTOCOL_V1A.read_bytes()).hexdigest(),
        "v1b": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
    }
    assert frame.protocol_sha256["v1a"] == protocols["v1b"]["depends_on"]["v1a_sha256"]


def test_frame_cannot_be_changed_after_it_is_read(frame: PlanningFrame) -> None:
    with pytest.raises(TypeError):
        frame.weights["exposure_0_100"] = 1.0  # type: ignore[index]
    with pytest.raises(TypeError):
        frame.vulnerability_anchors["P10"] = 0.1  # type: ignore[index]
    with pytest.raises(AttributeError):
        frame.flood_anchor = 0.05  # type: ignore[misc]


def test_no_anchor_value_is_written_in_the_module(protocols: dict[str, dict[str, Any]]) -> None:
    source = MODULE.read_text(encoding="utf-8")
    for value in protocols["v1b"]["national_vulnerability_anchors"]["values"].values():
        assert repr(value) not in source and f"{value:.6f}" not in source
    flood = protocols["v1a"]["scoring_frame"]["components"]["flood_likelihood_0_100"]
    for value in (flood["anchor"], *flood["anchor_sensitivity_one_at_a_time"]):
        for text in (repr(value), f"{value:.2f}"):
            assert not [line for line in source.splitlines() if f" {text}" in line or f"={text}" in line], text


def test_frame_record_cites_the_protocol_and_the_anchors(frame: PlanningFrame) -> None:
    record = frame_record(frame)
    assert json.loads(json.dumps(record)) == record
    assert record["normalisation_version"] == NORMALISATION_FRAME_VERSION
    assert record["vulnerability_anchor_version"] == ANCHOR_VERSION
    assert record["vulnerability_anchors"] == {
        "lower": "P10", "upper": "P90", "values": dict(frame.vulnerability_anchors),
    }
    assert record["vulnerability_anchor_sensitivity"] == {"lower": "P5", "upper": "P95"}
    assert record["weights"] == dict(frame.weights) and record["exposure_kind"] == "share_only"
    assert record["protocol_sha256"] == dict(frame.protocol_sha256) and all(record["protocol_sha256"].values())
    assert "4 of 5 components" in record["lane_disclosure"]
    assert "after seeing the data" in record["flood_anchor_disclosure"]
    assert record["leave_one_component_out_weights"] == leave_one_component_out_weights(frame.weights)
    assert [row["service"] for row in record["access_services"]] == [row.service for row in frame.access_services]


def test_protocol_is_read_only_when_the_receipts_record_its_bytes(tmp_path: Path) -> None:
    digest = hashlib.sha256(PROTOCOL_V1A.read_bytes()).hexdigest()
    key = "planning_protocol_v1a_sha256"
    receipts = tmp_path / "RECEIPTS.jsonl"

    def write(*lines: dict[str, Any]) -> None:
        receipts.write_text("\n\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    # Blank lines, receipts of other things and receipts of the other protocol are passed over.
    write(
        {"result": "PASS"},
        {"output_hashes": "none"},
        {"output_hashes": {"planning_protocol_v1b_sha256": "f" * 64}},
        {"output_hashes": {key: digest}},
    )
    protocol, read_digest = read_protocol_in_force("v1a", PROTOCOL_V1A, receipts)
    assert read_digest == digest and protocol["protocol_id"] == "planning_protocol_v1a"

    write({"output_hashes": {"planning_protocol_v1b_sha256": digest}})
    with pytest.raises(NormalisationError, match="not in force"):
        read_protocol_in_force("v1a", PROTOCOL_V1A, receipts)
    write({"output_hashes": {key: digest}}, {"output_hashes": {key: "0" * 64}})
    with pytest.raises(NormalisationError, match="not in force"):
        read_protocol_in_force("v1a", PROTOCOL_V1A, receipts)

    # A file whose bytes are recorded but which is not signed is not in force either.
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({"status": "draft_for_signature"}), encoding="utf-8")
    write({"output_hashes": {key: hashlib.sha256(draft.read_bytes()).hexdigest()}})
    with pytest.raises(NormalisationError, match="not in force"):
        read_protocol_in_force("v1a", draft, receipts)


def test_frame_is_refused_when_v1b_names_another_v1a(tmp_path: Path, protocols: dict[str, dict[str, Any]]) -> None:
    other = tmp_path / "planning_protocol_v1b.json"
    other.write_text(json.dumps(_change(protocols["v1b"], "depends_on/v1a_sha256", "0" * 64)), encoding="utf-8")
    recorded = {
        "planning_protocol_v1a_sha256": hashlib.sha256(PROTOCOL_V1A.read_bytes()).hexdigest(),
        "planning_protocol_v1b_sha256": hashlib.sha256(other.read_bytes()).hexdigest(),
    }
    receipts = tmp_path / "RECEIPTS.jsonl"
    receipts.write_text(
        "".join(json.dumps({"output_hashes": {key: value}}) + "\n" for key, value in recorded.items()),
        encoding="utf-8",
    )
    with pytest.raises(NormalisationError, match="does not name the v1a file"):
        load_planning_frame(PROTOCOL_V1A, other, receipts)


def test_a_frame_that_was_not_read_from_the_files_in_force_computes_nothing(
    frame: PlanningFrame, protocols: dict[str, dict[str, Any]]
) -> None:
    # Protocol v1a change_control: "Outputs carry protocol_sha256 so each value can be tied to the
    # protocol bytes that produced it." A frame built from parsed mappings has no bytes to name.
    unhashed = planning_frame_from_protocols(protocols["v1a"], protocols["v1b"])
    assert dict(unhashed.protocol_sha256) == {"v1a": None, "v1b": None}
    with pytest.raises(TypeError):
        planning_frame_from_protocols(  # type: ignore[call-arg]
            protocols["v1a"], protocols["v1b"], protocol_sha256={"v1a": "0" * 64, "v1b": "1" * 64}
        )
    # A mapping edited after signing still parses (another P10), and still computes nothing.
    edited = planning_frame_from_protocols(
        protocols["v1a"], _change(protocols["v1b"], f"{_ANCHORS}/values/P10", 0.2)
    )
    assert edited.vulnerability_anchors["P10"] != frame.vulnerability_anchors["P10"]
    half = dataclasses.replace(frame, protocol_sha256={"v1a": frame.protocol_sha256["v1a"], "v1b": None})
    empty = dataclasses.replace(frame, protocol_sha256={"v1a": frame.protocol_sha256["v1a"], "v1b": ""})
    missing = dataclasses.replace(frame, protocol_sha256={"v1a": frame.protocol_sha256["v1a"]})
    rows = _batch(frame)
    calls = {
        "flood_likelihood_0_100": {"flooded_non_permanent_water_land_area": 1.0, "non_permanent_water_land_area": 4.0},
        "exposure_0_100": {"residents_inside_flood_extent": 1.0, "unit_residents": 4.0},
        "access_gap_0_100": {"services": _services(frame, {"hospital": (10, 1), "main_road_entry": (10, 1)})},
        "road_criticality_0_100": {"residents_losing_all_routes": 1.0, "residents_with_baseline_route": 4.0},
        "vulnerability_context_0_100": {"children_0_14": 1.0, "older_60_plus": 1.0, "residents": 4.0},
    }
    assert set(calls) == set(COMPONENT_FUNCTIONS)
    for refused in (unhashed, edited, half, empty, missing):
        for name, arguments in calls.items():
            with pytest.raises(NormalisationError, match="carries no protocol hashes: read it with load_"):
                COMPONENT_FUNCTIONS[name](refused, **arguments)
        with pytest.raises(NormalisationError, match="carries no protocol hashes"):
            frame_record(refused)
        with pytest.raises(NormalisationError, match="carries no protocol hashes"):
            protocol_hashes(refused)
        with pytest.raises(NormalisationError, match="carries no protocol hashes"):
            reject_batch_scaled_components(refused, rows)
        # The frame is checked before anything else, so an empty batch does not hide it.
        with pytest.raises(NormalisationError, match="carries no protocol hashes"):
            reject_batch_scaled_components(refused, [])
    # The frame in force puts both hashes in every record it returns.
    hashes = protocol_hashes(frame)
    assert hashes == dict(frame.protocol_sha256) and all(len(value) == 64 for value in hashes.values())
    for name, arguments in calls.items():
        assert COMPONENT_FUNCTIONS[name](frame, **arguments)["protocol_sha256"] == hashes
    assert frame_record(frame)["protocol_sha256"] == hashes


_FLOOD = "scoring_frame/components/flood_likelihood_0_100"
_EXPOSURE = "scoring_frame/components/exposure_0_100"
_ACCESS = "scoring_frame/components/access_gap_0_100"
_VULNERABILITY = "scoring_frame/components/vulnerability_context_0_100"
_ANCHORS = "national_vulnerability_anchors"


@pytest.mark.parametrize("which, pointer, value, message", [
    ("v1a", "status", "draft_for_signature", "signed protocol files only"),
    ("v1b", "status", "incomplete_draft", "signed protocol files only"),
    ("v1a", "scoring_frame/version", "planning_frame_v2", "implements planning_frame_v1"),
    ("v1a", _VULNERABILITY, "DELETE", "five FPPS components"),
    ("v1a", "scoring_frame/weights/exposure_0_100", "DELETE", "five FPPS components"),
    ("v1a", f"{_EXPOSURE}/kind", "share_and_headcount", "share-only exposure"),
    ("v1a", f"{_EXPOSURE}/headcount_anchor", 5000, "share-only exposure"),
    ("v1a", f"{_EXPOSURE}/density_anchor", 1000, "share-only exposure"),
    ("v1a", f"{_ACCESS}/public_level_services", [], "with a public service"),
    ("v1a", f"{_ACCESS}/pitch_level_adds/0/service", "hospital", "named once each"),
    ("v1a", f"{_ACCESS}/public_level_services/0/threshold_minutes", "soon", "do not hold"),
    ("v1a", f"{_FLOOD}/anchor", 0, "strictly between 0 and 1"),
    ("v1a", f"{_FLOOD}/anchor", 1, "strictly between 0 and 1"),
    ("v1a", f"{_FLOOD}/anchor_sensitivity_one_at_a_time", [0.1, "0.3"], "not a number"),
    ("v1a", f"{_FLOOD}/permanent_water", "DELETE", "do not hold"),
    ("v1a", f"{_VULNERABILITY}/lower_anchor", "national_P11", "do not hold"),
    ("v1a", "scoring_frame", None, "do not hold"),
    ("v1b", f"{_ANCHORS}/status", "open", "not fixed"),
    ("v1b", f"{_ANCHORS}/values/P10", None, "not a number"),
    ("v1b", f"{_ANCHORS}/values/P10", True, "not a number"),
    ("v1b", f"{_ANCHORS}/values/P90", 1.2, "strictly between 0 and 1"),
    ("v1b", f"{_ANCHORS}/values/P10", 0.9, "below the upper one"),
    ("v1b", f"{_ANCHORS}/values/P95", 0.2, "below the upper one"),
    ("v1b", f"{_ANCHORS}/values", [0.3, 0.5], "do not hold"),
    ("v1b", _ANCHORS, "DELETE", "do not hold"),
])
def test_frame_is_refused_when_the_protocol_states_another_frame(
    protocols: dict[str, dict[str, Any]], which: str, pointer: str, value: Any, message: str
) -> None:
    changed = {**protocols, which: _change(protocols[which], pointer, value)}
    with pytest.raises(NormalisationError, match=message):
        planning_frame_from_protocols(changed["v1a"], changed["v1b"])


def test_frame_is_refused_when_the_leave_one_out_reading_is_not_confirmed(protocols: dict[str, dict[str, Any]]) -> None:
    index = next(i for i, row in enumerate(protocols["v1a"]["drafter_readings"]) if row["id"] == "DR-A02")
    assert protocols["v1a"]["drafter_readings"][index]["status"] == "confirmed"
    amended = _change(protocols["v1a"], f"drafter_readings/{index}/status", "amended")
    with pytest.raises(NormalisationError, match="DR-A02"):
        planning_frame_from_protocols(amended, protocols["v1b"])
    unhashed = planning_frame_from_protocols(protocols["v1a"], protocols["v1b"])
    assert dict(unhashed.protocol_sha256) == {"v1a": None, "v1b": None}


# ---------------------------------------------------------------------------
# Frame v1: the five components on invented units
# ---------------------------------------------------------------------------


def test_flood_likelihood_uses_the_signed_anchor_and_reports_both_sensitivity_anchors(frame: PlanningFrame) -> None:
    anchor = frame.flood_anchor
    land = 4_000_000.0
    cases = ((0.0, 0.0), (anchor / 4, 25.0), (anchor / 2, 50.0), (anchor, 100.0), (2 * anchor, 100.0), (1.0, 100.0))
    for share, expected in cases:
        result = flood_likelihood(
            frame, flooded_non_permanent_water_land_area=share * land, non_permanent_water_land_area=land
        )
        assert result["value_0_100"] == pytest.approx(expected, abs=1e-9)
        assert result["flooded_share"] == pytest.approx(share)
        assert result["anchor"] == anchor
        sensitivity = result["anchor_sensitivity_one_at_a_time"]
        assert [row["anchor"] for row in sensitivity] == list(frame.flood_anchor_sensitivity)
        for row in sensitivity:
            assert row["value_0_100"] == pytest.approx(100 * min(1, share / row["anchor"]))
    assert result["component"] == "flood_likelihood_0_100"
    assert result["normalisation_version"] == NORMALISATION_FRAME_VERSION
    assert result["inputs"] == {"flooded_non_permanent_water_land_area": land, "non_permanent_water_land_area": land}
    assert "after seeing the data" in result["anchor_disclosure"]
    assert result["permanent_water"] == dict(frame.permanent_water) and result["permanent_water"]["class"] == 80
    assert "non-permanent-water land" in result["definition"]
    # Just below the anchor the value is just below 100: the anchor is where the component saturates.
    below = flood_likelihood(
        frame, flooded_non_permanent_water_land_area=(anchor - 1e-6) * land, non_permanent_water_land_area=land
    )
    assert 99.99 < below["value_0_100"] < 100.0


@pytest.mark.parametrize("flooded, land, message", [
    (0.0, 0.0, "states no component value"),
    (5.0, 4.0, "exceeds"),
    (-1.0, 4.0, "finite and not negative"),
    (float("nan"), 4.0, "finite and not negative"),
    (1.0, float("inf"), "finite and not negative"),
    (True, 4.0, "one number for one unit"),
    ("1", 4.0, "one number for one unit"),
    ([1.0, 2.0], [4.0, 4.0], "one number for one unit"),
    (None, 4.0, "one number for one unit"),
])
def test_flood_likelihood_refuses_what_the_protocol_gives_no_value_for(
    frame: PlanningFrame, flooded: Any, land: Any, message: str
) -> None:
    with pytest.raises(NormalisationError, match=message):
        flood_likelihood(frame, flooded_non_permanent_water_land_area=flooded, non_permanent_water_land_area=land)


def test_exposure_is_a_share_and_nothing_else(frame: PlanningFrame) -> None:
    for inside, residents, expected in ((0, 1000, 0.0), (250, 1000, 25.0), (1000, 1000, 100.0), (1, 3, 100 / 3)):
        result = exposure(frame, residents_inside_flood_extent=inside, unit_residents=residents)
        assert result["value_0_100"] == pytest.approx(expected)
        assert result["kind"] == "share_only" and result["component"] == "exposure_0_100"
        assert result["inputs"] == {"residents_inside_flood_extent": inside, "unit_residents": residents}
    # Share-only: a village and a city with the same exposed share get the same value.
    small = exposure(frame, residents_inside_flood_extent=30.0, unit_residents=120.0)["value_0_100"]
    large = exposure(frame, residents_inside_flood_extent=30_000.0, unit_residents=120_000.0)["value_0_100"]
    assert small == large == 25.0
    # A float sum of cells may exceed the total by a rounding error; that is capped, not refused.
    assert exposure(frame, residents_inside_flood_extent=1000.0000000001, unit_residents=1000.0)["value_0_100"] == 100.0
    assert exposure(frame, residents_inside_flood_extent=np.float64(5), unit_residents=np.int64(10))["value_0_100"] == 50.0
    with pytest.raises(TypeError):
        exposure(frame, residents_inside_flood_extent=1, unit_residents=2, headcount_anchor=5000)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        exposure(frame, residents_inside_flood_extent=1, unit_residents=2, population_per_km2=900)  # type: ignore[call-arg]
    with pytest.raises(NormalisationError, match="states no component value"):
        exposure(frame, residents_inside_flood_extent=0, unit_residents=0)
    with pytest.raises(NormalisationError, match="exceeds"):
        exposure(frame, residents_inside_flood_extent=11, unit_residents=10)


def test_access_gap_is_the_baseline_access_weighted_mean_of_the_newly_lost_shares(frame: PlanningFrame) -> None:
    public = _services(frame, {"hospital": (1000, 100), "main_road_entry": (3000, 900)})
    result = access_gap(frame, services=public)
    # Shares 0.10 and 0.30, weights 1000 and 3000: (1000 x 0.10 + 3000 x 0.30) / 4000 = 0.25, not the plain mean 0.20.
    assert result["value_0_100"] == pytest.approx(25.0)
    assert [row["newly_lost_share"] for row in result["services"]] == pytest.approx([0.1, 0.3])
    assert result["baseline_access_residents_all_services"] == 4000
    assert result["publication_level"] == "public" and result["component"] == "access_gap_0_100"
    assert result["inputs"] == {"services": public}
    assert access_gap(frame, **result["inputs"])["value_0_100"] == result["value_0_100"]
    assert [(row["service"], row["mode"], row["threshold_minutes"]) for row in result["services"]] == [
        (service.service, service.mode, service.threshold_minutes) for service in frame.access_services[:2]
    ]

    pitch = _services(frame, {
        "ddpm_located_shelter": (1000, 1000), "main_road_entry": (3000, 900), "hospital": (1000, 100),
    })
    with_shelter = access_gap(frame, services=pitch)
    assert with_shelter["value_0_100"] == pytest.approx(100 * (100 + 900 + 1000) / 5000)
    assert with_shelter["publication_level"] == "pitch"
    assert [row["service"] for row in with_shelter["services"]] == [service.service for service in frame.access_services]


def test_access_gap_counts_only_residents_who_had_access_at_baseline(frame: PlanningFrame) -> None:
    def gap(hospital: tuple[float, float], main_road: tuple[float, float]) -> dict[str, Any]:
        return access_gap(frame, services=_services(frame, {"hospital": hospital, "main_road_entry": main_road}))

    # Nobody could reach a hospital at baseline: that service has no share and no weight.
    result = gap((0, 0), (2000, 500))
    assert result["value_0_100"] == pytest.approx(25.0)
    assert result["services"][0]["newly_lost_share"] is None
    assert gap((500, 0), (2000, 0))["value_0_100"] == 0.0
    assert gap((500, 500), (2000, 2000))["value_0_100"] == 100.0
    with pytest.raises(NormalisationError, match="states no access gap"):
        gap((0, 0), (0, 0))
    with pytest.raises(NormalisationError, match="only for residents who had access at baseline"):
        gap((100, 101), (2000, 0))


def test_access_gap_takes_only_the_declared_services_modes_and_thresholds(frame: PlanningFrame) -> None:
    good = _services(frame, {"hospital": (1000, 100), "main_road_entry": (3000, 900)})
    refused: list[tuple[Any, str]] = [
        ({"hospital": good["hospital"]}, "public level"),
        ({**good, "school": good["hospital"]}, "public level"),
        ({"hospital": good["hospital"], "ddpm_located_shelter": good["hospital"]}, "public level"),
        ({}, "public level"),
        ([good], "must map each service"),
        ({**good, "hospital": 1000}, "needs a mapping"),
        ({**good, "hospital": {**good["hospital"], "mode": "walking"}}, "declared as vehicle, 30 minutes"),
        ({**good, "hospital": {**good["hospital"], "threshold_minutes": 60}}, "declared as vehicle, 30 minutes"),
        ({**good, "main_road_entry": {"mode": "vehicle", "threshold_minutes": 15}}, "one number for one unit"),
        ({**good, "hospital": {**good["hospital"], "newly_lost_residents": None}}, "one number for one unit"),
        ({**good, "hospital": {**good["hospital"], "baseline_access_residents": -1}}, "finite and not negative"),
    ]
    for services, message in refused:
        with pytest.raises(NormalisationError, match=message):
            access_gap(frame, services=services)


def test_road_criticality_is_the_share_of_connected_residents_who_lose_every_route(frame: PlanningFrame) -> None:
    result = road_criticality(frame, residents_losing_all_routes=150, residents_with_baseline_route=600)
    assert result["value_0_100"] == pytest.approx(25.0) and result["share_losing_all_routes"] == pytest.approx(0.25)
    assert result["component"] == "road_criticality_0_100"
    assert result["inputs"] == {"residents_losing_all_routes": 150, "residents_with_baseline_route": 600}
    assert road_criticality(frame, residents_losing_all_routes=0, residents_with_baseline_route=600)["value_0_100"] == 0.0
    assert road_criticality(frame, residents_losing_all_routes=600, residents_with_baseline_route=600)["value_0_100"] == 100.0
    with pytest.raises(NormalisationError, match="states no component value"):
        road_criticality(frame, residents_losing_all_routes=0, residents_with_baseline_route=0)
    with pytest.raises(NormalisationError, match="exceeds"):
        road_criticality(frame, residents_losing_all_routes=601, residents_with_baseline_route=600)


def _vulnerability(frame: PlanningFrame, share: float) -> dict[str, Any]:
    residents = 10_000.0
    return vulnerability_context(
        frame, children_0_14=0.4 * share * residents, older_60_plus=0.6 * share * residents, residents=residents
    )


def test_vulnerability_runs_from_the_national_p10_to_the_national_p90(frame: PlanningFrame) -> None:
    anchors = frame.vulnerability_anchors
    lower, upper = anchors["P10"], anchors["P90"]
    assert _vulnerability(frame, lower - 0.05)["value_0_100"] == 0.0
    assert _vulnerability(frame, upper + 0.05)["value_0_100"] == 100.0
    assert _vulnerability(frame, lower)["value_0_100"] == pytest.approx(0.0, abs=1e-6)
    assert _vulnerability(frame, upper)["value_0_100"] == pytest.approx(100.0, abs=1e-6)
    middle = _vulnerability(frame, (lower + upper) / 2)
    assert middle["value_0_100"] == pytest.approx(50.0, abs=1e-6)
    assert middle["dependent_share"] == pytest.approx((lower + upper) / 2)
    assert middle["anchors"] == {"lower": "P10", "lower_value": lower, "upper": "P90", "upper_value": upper}
    assert middle["anchor_version"] == ANCHOR_VERSION
    assert middle["anchor_receipt_sha256"] == frame.vulnerability_anchor_receipt_sha256
    assert middle["caveat"] and middle["component"] == "vulnerability_context_0_100"
    assert set(middle["inputs"]) == {"children_0_14", "older_60_plus", "residents"}

    # The anchor sensitivity is the same formula on the P5 and P95 anchors.
    wide_lower, wide_upper = anchors["P5"], anchors["P95"]
    sensitivity = _vulnerability(frame, (wide_lower + wide_upper) / 2)["anchor_sensitivity"]
    assert sensitivity["value_0_100"] == pytest.approx(50.0, abs=1e-6)
    assert (sensitivity["lower"], sensitivity["upper"]) == ("P5", "P95")
    assert (sensitivity["lower_value"], sensitivity["upper_value"]) == (wide_lower, wide_upper)
    at_p10 = _vulnerability(frame, lower)["anchor_sensitivity"]["value_0_100"]
    assert at_p10 == pytest.approx(100 * (lower - wide_lower) / (wide_upper - wide_lower), abs=1e-6)
    with pytest.raises(NormalisationError, match="positive resident count"):
        vulnerability_context(frame, children_0_14=0, older_60_plus=0, residents=0)


def test_components_take_any_real_number_type_and_return_plain_json(frame: PlanningFrame) -> None:
    # Raster sums arrive as numpy scalars, usually float32. Every component takes them, echoes the
    # floats it used, and its record survives a JSON round trip unchanged.
    def records(number: Any, whole: Any) -> dict[str, dict[str, Any]]:
        services = _services(frame, {"hospital": (whole(40), number(10)), "main_road_entry": (whole(40), number(10))})
        return {
            "flood_likelihood_0_100": flood_likelihood(
                frame, flooded_non_permanent_water_land_area=number(1), non_permanent_water_land_area=whole(40)
            ),
            "exposure_0_100": exposure(frame, residents_inside_flood_extent=number(10), unit_residents=whole(40)),
            "access_gap_0_100": access_gap(frame, services=services),
            "road_criticality_0_100": road_criticality(
                frame, residents_losing_all_routes=number(10), residents_with_baseline_route=whole(40)
            ),
            "vulnerability_context_0_100": vulnerability_context(
                frame, children_0_14=number(6), older_60_plus=number(8), residents=whole(40)
            ),
        }

    reference = records(float, float)
    kinds = [(np.float32, np.float32), (np.float32, np.int64), (np.float64, np.int32), (int, int), (Fraction, Fraction)]
    for number, whole in kinds:
        built = records(number, whole)
        assert built == reference, (number, whole)
        encoded = json.dumps(built)  # raises for a numpy scalar left in a record
        assert json.loads(encoded) == built
        for name in set(SCORE_COMPONENTS) - {"access_gap_0_100"}:
            assert all(type(value) is float for value in built[name]["inputs"].values()), (name, number)
        for service in built["access_gap_0_100"]["inputs"]["services"].values():
            assert type(service["baseline_access_residents"]) is float
            assert type(service["newly_lost_residents"]) is float
        row = {"unit_id": "SYN-TYPES", "normalisation_version": NORMALISATION_FRAME_VERSION, "components": built}
        assert reject_batch_scaled_components(frame, [json.loads(json.dumps(row))])["result"] == "PASS"
    # A float32 that is not a short binary fraction is echoed as the float that was used.
    third = np.float32(1) / np.float32(3)
    echoed = exposure(frame, residents_inside_flood_extent=third, unit_residents=np.float32(1))["inputs"]
    assert echoed["residents_inside_flood_extent"] == float(third) != 1 / 3
    # The age counts are checked like every other count, and say which one is wrong.
    for bad, message in (
        (True, "children_0_14 must be one number for one unit"),
        ("6", "children_0_14 must be one number for one unit"),
        (None, "children_0_14 must be one number for one unit"),
        (np.array([6.0, 7.0]), "children_0_14 must be one number for one unit"),
        (np.float32("nan"), "children_0_14 must be finite and not negative"),
        (-1, "children_0_14 must be finite and not negative"),
    ):
        with pytest.raises(NormalisationError, match=message):
            vulnerability_context(frame, children_0_14=bad, older_60_plus=8, residents=40)
    with pytest.raises(NormalisationError, match="older_60_plus must be one number"):
        vulnerability_context(frame, children_0_14=6, older_60_plus="8", residents=40)
    with pytest.raises(NormalisationError, match="residents must be finite"):
        vulnerability_context(frame, children_0_14=6, older_60_plus=8, residents=np.float32("inf"))
    with pytest.raises(NormalisationError, match="exceed the resident count"):
        vulnerability_context(frame, children_0_14=np.float32(30), older_60_plus=np.float32(30), residents=np.int64(40))


# ---------------------------------------------------------------------------
# Guardrail GR2: no batch scaling, no max-normalisation
# ---------------------------------------------------------------------------


def _unit_row(frame: PlanningFrame, unit_id: str, **shares: float) -> dict[str, Any]:
    """The five frame v1 records of one invented unit of 2,000 residents, from the shares given."""

    residents = 2000.0
    services = _services(frame, {
        "hospital": (1500.0, 1500.0 * shares["access"]),
        "main_road_entry": (1800.0, 1800.0 * shares["access"]),
    })
    return {
        "unit_id": unit_id,
        "normalisation_version": NORMALISATION_FRAME_VERSION,
        "components": {
            "flood_likelihood_0_100": flood_likelihood(
                frame, flooded_non_permanent_water_land_area=shares["flood"] * 1e6, non_permanent_water_land_area=1e6
            ),
            "exposure_0_100": exposure(
                frame, residents_inside_flood_extent=shares["exposure"] * residents, unit_residents=residents
            ),
            "access_gap_0_100": access_gap(frame, services=services),
            "road_criticality_0_100": road_criticality(
                frame, residents_losing_all_routes=shares["road"] * 1900.0, residents_with_baseline_route=1900.0
            ),
            "vulnerability_context_0_100": _vulnerability(frame, shares["dependent"]),
        },
    }


def _batch(frame: PlanningFrame) -> list[dict[str, Any]]:
    """Three invented units; no component reaches 100, so dividing by the batch maximum changes every one."""

    lower, upper = (frame.vulnerability_anchors[key] for key in frame.vulnerability_bounds)
    span = upper - lower
    anchor = frame.flood_anchor
    return [
        _unit_row(frame, "SYN-A", flood=0.1 * anchor, exposure=0.1, access=0.05, road=0.02, dependent=lower + 0.2 * span),
        _unit_row(frame, "SYN-B", flood=0.4 * anchor, exposure=0.3, access=0.25, road=0.1, dependent=lower + 0.5 * span),
        _unit_row(frame, "SYN-C", flood=0.8 * anchor, exposure=0.6, access=0.5, road=0.4, dependent=lower + 0.7 * span),
    ]


def _with_values(rows: list[dict[str, Any]], name: str, values: list[Any]) -> list[dict[str, Any]]:
    changed = deepcopy(rows)
    for row, value in zip(changed, values):
        row["components"][name]["value_0_100"] = value
    return changed


def test_gr2_accepts_rows_on_the_absolute_frame(frame: PlanningFrame) -> None:
    rows = _batch(frame)
    result = reject_batch_scaled_components(frame, rows)
    assert result == {
        "guardrail": "GR2_no_max_normalisation",
        "result": "PASS",
        "normalisation_version": NORMALISATION_FRAME_VERSION,
        "protocol_sha256": dict(frame.protocol_sha256),
        "components": list(SCORE_COMPONENTS),
        "rows_checked": 3,
        "components_checked": 15,
        "tolerance": 1e-9,
        "fields_compared": "every field of every record; value_0_100 within the tolerance, the others exactly",
    }
    assert json.loads(json.dumps(result)) == result
    assert reject_batch_scaled_components(frame, iter(rows[:1]))["rows_checked"] == 1
    assert set(COMPONENT_FUNCTIONS) == set(SCORE_COMPONENTS)
    for row in rows:
        for name, record in row["components"].items():
            assert record["component"] == name and 0.0 < record["value_0_100"] < 100.0


@pytest.mark.parametrize("name", SCORE_COMPONENTS)
def test_gr2_refuses_a_component_scaled_by_the_batch_maximum(frame: PlanningFrame, name: str) -> None:
    rows = _batch(frame)
    absolute = [row["components"][name]["value_0_100"] for row in rows]
    scaled = [100 * value / max(absolute) for value in absolute]
    assert max(scaled) == 100.0 and scaled != absolute
    message = rf"{name} is the frame v1 value divided by the batch maximum \(max-normalisation\)"
    with pytest.raises(BatchScalingError, match=message):
        reject_batch_scaled_components(frame, _with_values(rows, name, scaled))
    # One changed value is enough, whatever the reason for the change.
    shifted = [absolute[0], absolute[1] + 0.5, absolute[2]]
    with pytest.raises(BatchScalingError, match=rf"{name} is not the frame v1 value of the inputs it echoes .*SYN-B"):
        reject_batch_scaled_components(frame, _with_values(rows, name, shifted))


def test_gr2_takes_no_tolerance_from_its_caller(frame: PlanningFrame) -> None:
    # "The planning verifier must reject batch-scaled components." A tolerance argument of NaN, inf or
    # 1000 once turned the check off and still wrote PASS; the check now has one fixed float guard.
    assert "tolerance" not in inspect.signature(reject_batch_scaled_components).parameters
    assert VERIFY_TOLERANCE == 1e-9
    rows = _batch(frame)
    absolute = [row["components"]["exposure_0_100"]["value_0_100"] for row in rows]
    scaled = _with_values(rows, "exposure_0_100", [100 * value / max(absolute) for value in absolute])
    for tolerance in (float("nan"), float("inf"), 1000, 1e-9, 0.0, -1.0):
        with pytest.raises(TypeError, match="tolerance"):
            reject_batch_scaled_components(frame, scaled, tolerance=tolerance)  # type: ignore[call-arg]
    with pytest.raises(BatchScalingError, match="max-normalisation"):
        reject_batch_scaled_components(frame, scaled)
    # The guard is a float guard and nothing more: a change of one millionth of a point is refused.
    nudged = [absolute[0], absolute[1] + 1e-6, absolute[2]]
    with pytest.raises(BatchScalingError, match="is not the frame v1 value of the inputs it echoes .*SYN-B"):
        reject_batch_scaled_components(frame, _with_values(rows, "exposure_0_100", nudged))
    within = [absolute[0], absolute[1] + 1e-12, absolute[2]]
    assert reject_batch_scaled_components(frame, _with_values(rows, "exposure_0_100", within))["tolerance"] == 1e-9


_TWO = ("flood_likelihood_0_100", "exposure_0_100")


def _only(rows: list[dict[str, Any]], names: tuple[str, ...]) -> list[dict[str, Any]]:
    """The same rows carrying only the named component records."""

    return [{**row, "components": {name: deepcopy(row["components"][name]) for name in names}} for row in rows]


def test_gr2_checks_a_case_that_computes_two_components_only(
    frame: PlanningFrame, protocols: dict[str, dict[str, Any]]
) -> None:
    # Case SE2-dist (MUST): "Flood likelihood and exposure only, no routing. ... no FPPS and no class."
    case = next(row for row in protocols["v1a"]["case_portfolio"]["cases"] if row["id"] == "SE2-dist")
    assert "Flood likelihood and exposure only, no routing" in case["note"]
    rows = _only(_batch(frame), _TWO)
    result = reject_batch_scaled_components(frame, rows, components=_TWO)
    assert result["result"] == "PASS" and result["components"] == list(_TWO)
    assert result["rows_checked"] == 3 and result["components_checked"] == 6
    # The order of the names does not matter; the check runs in frame order.
    assert reject_batch_scaled_components(frame, rows, components=list(reversed(_TWO)))["components"] == list(_TWO)
    assert reject_batch_scaled_components(frame, iter(rows), components=iter(_TWO))["components_checked"] == 6
    for name in _TWO:
        absolute = [row["components"][name]["value_0_100"] for row in rows]
        scaled = _with_values(rows, name, [100 * value / max(absolute) for value in absolute])
        with pytest.raises(BatchScalingError, match=rf"{name} is the frame v1 value divided by the batch maximum"):
            reject_batch_scaled_components(frame, scaled, components=_TWO)
    # A row carries exactly the components that are checked: no fewer and no more.
    with pytest.raises(BatchScalingError, match="does not carry exactly the records"):
        reject_batch_scaled_components(frame, rows)
    with pytest.raises(BatchScalingError, match="does not carry exactly the records"):
        reject_batch_scaled_components(frame, _batch(frame), components=_TWO)
    with pytest.raises(BatchScalingError, match="does not carry exactly the records"):
        reject_batch_scaled_components(frame, rows, components=_TWO[:1])
    single = reject_batch_scaled_components(frame, _only(rows, _TWO[1:]), components=_TWO[1:])
    assert single["components"] == ["exposure_0_100"] and single["components_checked"] == 3


_NOT_A_SEQUENCE = "components must be a sequence of FPPS component names"
_NOT_ONCE_EACH = "components must name, once each, one or more of"


@pytest.mark.parametrize("components, message", [
    ((), _NOT_ONCE_EACH),
    ([], _NOT_ONCE_EACH),
    ("exposure_0_100", _NOT_A_SEQUENCE),
    (b"exposure_0_100", _NOT_A_SEQUENCE),
    ({"exposure_0_100": 1}, _NOT_A_SEQUENCE),
    (["exposure_0_100", "exposure_0_100"], _NOT_ONCE_EACH),
    (["exposure_0_100", "terrain_0_100"], _NOT_ONCE_EACH),
    ([*SCORE_COMPONENTS, "terrain_0_100"], _NOT_ONCE_EACH),
    (None, _NOT_A_SEQUENCE),
    (7, _NOT_A_SEQUENCE),
])
def test_gr2_refuses_a_component_list_it_cannot_check(frame: PlanningFrame, components: Any, message: str) -> None:
    with pytest.raises(NormalisationError, match=message):
        reject_batch_scaled_components(frame, _batch(frame), components=components)


def test_gr2_compares_the_whole_record_and_not_only_its_value(frame: PlanningFrame) -> None:
    # GR2: "section 2b's density exposure and fpps_flood_anchor_v1 apply to the GeoAI runner only."
    # A record whose value is right but which names another anchor or version is not a frame v1 record.
    rows = _batch(frame)
    other_anchor = frame.flood_anchor / 4

    def changed(component: str, field: str, value: Any) -> list[dict[str, Any]]:
        copy = deepcopy(rows)
        if value == "DELETE":
            del copy[1]["components"][component][field]
        else:
            copy[1]["components"][component][field] = value
        return copy

    flood, exposed, vulnerable = "flood_likelihood_0_100", "exposure_0_100", "vulnerability_context_0_100"
    lower = rows[1]["components"][vulnerable]["anchors"]
    cases = [
        (flood, "anchor", other_anchor, "anchor"),
        (flood, "normalisation_version", "fpps_flood_anchor_v1", "normalisation_version"),
        (exposed, "normalisation_version", "fpps_exposure_anchor_v1", "normalisation_version"),
        (exposed, "kind", "density", "kind"),
        (exposed, "exposed_share", 0.99, "exposed_share"),
        (exposed, "definition", "DELETE", "definition"),
        (exposed, "density_anchor", None, "density_anchor"),
        (exposed, "protocol_sha256", {"v1a": "0" * 64, "v1b": "1" * 64}, "protocol_sha256"),
        (exposed, "protocol_sha256", "DELETE", "protocol_sha256"),
        (vulnerable, "anchors", {**lower, "lower": "P5"}, "anchors"),
        (vulnerable, "anchor_version", "another_anchor_version", "anchor_version"),
        (flood, "anchor_sensitivity_one_at_a_time", [], "anchor_sensitivity_one_at_a_time"),
        ("access_gap_0_100", "publication_level", "pitch", "publication_level"),
        ("road_criticality_0_100", "component", "exposure_0_100", "component"),
    ]
    for component, field, value, named in cases:
        message = rf"not the frame v1 record .* fields that differ: {component} of unit 'SYN-B': \['{named}'\]$"
        with pytest.raises(BatchScalingError, match=message):
            reject_batch_scaled_components(frame, changed(component, field, value))
    # The GeoAI runner's two anchor fields are named as such inside a record, as they are on a row.
    for field in ("flood_anchor_version", "exposure_anchor_version"):
        message = rf"{flood} of unit 'SYN-B' carries \['{field}'\], the anchor versions of the GeoAI runner"
        with pytest.raises(BatchScalingError, match=message):
            reject_batch_scaled_components(frame, changed(flood, field, "fpps_flood_anchor_v1"))
    # Several differing records are all listed, and a wrong value is reported before a wrong label.
    two = changed(flood, "anchor", other_anchor)
    two[2]["components"][exposed]["kind"] = "density"
    with pytest.raises(BatchScalingError, match=r"SYN-B': \['anchor'\]; exposure_0_100 of unit 'SYN-C': \['kind'\]"):
        reject_batch_scaled_components(frame, two)
    both = changed(flood, "anchor", other_anchor)
    both[1]["components"][flood]["value_0_100"] += 1.0
    with pytest.raises(BatchScalingError, match="is not the frame v1 value of the inputs it echoes"):
        reject_batch_scaled_components(frame, both)
    # The same holds for a batch that carries two components only.
    subset = _only(changed(flood, "anchor", other_anchor), _TWO)
    with pytest.raises(BatchScalingError, match="fields that differ"):
        reject_batch_scaled_components(frame, subset, components=_TWO)


def test_gr2_does_not_mistake_a_saturated_unit_for_batch_scaling(frame: PlanningFrame) -> None:
    rows = _batch(frame)
    rows.append(_unit_row(frame, "SYN-D", flood=1.0, exposure=1.0, access=1.0, road=1.0, dependent=0.95))
    assert [record["value_0_100"] for record in rows[-1]["components"].values()] == [100.0] * 5
    # The batch maximum is 100 on the absolute scale, so dividing by it changes nothing and nothing is refused.
    assert reject_batch_scaled_components(frame, rows)["rows_checked"] == 4


def test_gr2_refuses_values_where_every_absolute_value_is_zero(frame: PlanningFrame) -> None:
    lower = frame.vulnerability_anchors["P10"]
    rows = [
        _unit_row(frame, f"SYN-{index}", flood=0.0, exposure=0.0, access=0.0, road=0.0, dependent=lower - 0.1)
        for index in range(3)
    ]
    assert reject_batch_scaled_components(frame, rows)["result"] == "PASS"
    with pytest.raises(BatchScalingError, match="exposure_0_100 is not the frame v1 value"):
        reject_batch_scaled_components(frame, _with_values(rows, "exposure_0_100", [0.0, 50.0, 100.0]))


def test_gr2_refuses_rows_that_are_not_on_frame_v1(frame: PlanningFrame) -> None:
    rows = _batch(frame)
    first = rows[0]
    components = first["components"]
    bare = {name: record["value_0_100"] for name, record in components.items()}
    no_echo = {**components, "exposure_0_100": {"value_0_100": components["exposure_0_100"]["value_0_100"]}}
    other_inputs = {**components, "exposure_0_100": {"value_0_100": 10.0, "inputs": {"population_per_km2": 900.0}}}
    no_value = {**components, "exposure_0_100": {"inputs": components["exposure_0_100"]["inputs"]}}
    refused: list[tuple[Any, str]] = [
        ({**first, "normalisation_version": "fpps_flood_anchor_v1"}, "does not declare planning_frame_v1"),
        ({key: value for key, value in first.items() if key != "normalisation_version"}, "does not declare"),
        ({**first, "flood_anchor_version": "fpps_flood_anchor_v1"}, "anchor versions of the GeoAI runner"),
        ({**first, "exposure_anchor_version": "fpps_exposure_anchor_v1"}, "anchor versions of the GeoAI runner"),
        ({**first, "components": {"exposure_0_100": components["exposure_0_100"]}}, "exactly the records"),
        ({**first, "components": [*components.values()]}, "exactly the records"),
        ({key: value for key, value in first.items() if key != "components"}, "exactly the records"),
        ({**first, "components": bare}, "does not echo the inputs"),
        ({**first, "components": no_echo}, "does not echo the inputs"),
        ({**first, "components": other_inputs}, "does not echo the inputs"),
        ({**first, "components": no_value}, "does not echo the inputs"),
        (["SYN-A", 10.0], "a row maps"),
    ]
    for row, message in refused:
        with pytest.raises(BatchScalingError, match=message):
            reject_batch_scaled_components(frame, [row, *rows[1:]])
    with pytest.raises(NormalisationError, match="no row to check"):
        reject_batch_scaled_components(frame, [])
    with pytest.raises(NormalisationError, match="one number for one unit"):
        reject_batch_scaled_components(frame, _with_values(rows, "exposure_0_100", ["10", "30", "60"]))
    # Echoed inputs that the frame itself refuses are refused here too.
    broken = deepcopy(rows)
    broken[0]["components"]["exposure_0_100"]["inputs"]["unit_residents"] = 0
    with pytest.raises(NormalisationError, match="states no component value"):
        reject_batch_scaled_components(frame, broken)


# ---------------------------------------------------------------------------
# Leave-one-component-out weights (drafter reading DR-A02)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset", list(WEIGHT_SCENARIOS))
def test_leave_one_out_sets_one_weight_to_zero_and_renormalises_the_other_four(preset: str) -> None:
    raw = WEIGHT_SCENARIOS[preset]
    total = sum(raw.values())
    result = leave_one_component_out_weights(raw)
    assert list(result) == list(SCORE_COMPONENTS)
    for dropped, weights in result.items():
        assert weights[dropped] == 0.0
        assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12)
        for name in SCORE_COMPONENTS:
            if name != dropped:
                assert weights[name] == pytest.approx(raw[name] / (total - raw[dropped]))
        # The scorer normalises weights itself; these already sum to 1, so it uses them as they are.
        assert validate_weights(weights) == pytest.approx(weights)


def test_leave_one_out_of_the_frame_weights_is_the_signed_rule(
    frame: PlanningFrame, protocols: dict[str, dict[str, Any]]
) -> None:
    rule = protocols["v1a"]["scoring_frame"]["leave_one_component_out"]
    assert rule["required_on_every_row"] is True and "renormalised to sum to 1" in rule["rule"]
    assert "Confirmed by the owners at signing" in rule["rule_status"]
    result = leave_one_component_out_weights(frame.weights)
    weights = frame.weights
    flood, exposed = weights["flood_likelihood_0_100"], weights["exposure_0_100"]
    assert result["flood_likelihood_0_100"]["exposure_0_100"] == pytest.approx(exposed / (1 - flood))
    assert result["exposure_0_100"]["flood_likelihood_0_100"] == pytest.approx(flood / (1 - exposed))
    assert result == leave_one_component_out_weights(dict(DEFAULT_WEIGHTS))


@pytest.mark.parametrize("weights", [
    {name: 0.2 for name in SCORE_COMPONENTS[:4]},
    {**DEFAULT_WEIGHTS, "terrain_0_100": 0.1},
    {**DEFAULT_WEIGHTS, "exposure_0_100": -0.25},
    {**{name: 0.0 for name in SCORE_COMPONENTS}, "exposure_0_100": 1.0},
    {name: 0.0 for name in SCORE_COMPONENTS},
    {**DEFAULT_WEIGHTS, "exposure_0_100": "heavy"},
    {**DEFAULT_WEIGHTS, "exposure_0_100": None},
    None,
    7,
])
def test_leave_one_out_refuses_weights_the_scorer_would_refuse(weights: Any) -> None:
    with pytest.raises(NormalisationError, match="leave-one-component-out needs valid FPPS weights"):
        leave_one_component_out_weights(weights)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), np.float32("nan"), "nan"])
@pytest.mark.parametrize("name", SCORE_COMPONENTS)
def test_leave_one_out_refuses_a_weight_that_is_not_finite(name: str, value: Any) -> None:
    # "The other four weights renormalised to sum to 1": a NaN or infinite weight has no such set, and
    # the scorer's own check lets NaN through (it is neither negative nor a zero total).
    assert all(math.isnan(weight) for weight in validate_weights({**DEFAULT_WEIGHTS, name: float("nan")}).values())
    message = "leave-one-component-out needs valid FPPS weights: every weight must be a finite number"
    with pytest.raises(NormalisationError, match=message):
        leave_one_component_out_weights({**DEFAULT_WEIGHTS, name: value})
    for weights in leave_one_component_out_weights(DEFAULT_WEIGHTS).values():
        assert all(math.isfinite(weight) for weight in weights.values())
        assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Property tests on invented units
# ---------------------------------------------------------------------------


def _random_shares(generator: random.Random) -> dict[str, float]:
    def share() -> float:
        return generator.choice([0.0, 1.0, generator.random(), generator.random() ** 3])

    return {"flood": share(), "exposure": share(), "access": share(), "road": share(), "dependent": share()}


def test_every_component_stays_on_0_100_and_is_reproduced_from_its_echo(frame: PlanningFrame) -> None:
    generator = random.Random(20261004)
    rows = [_unit_row(frame, f"SYN-{index:04d}", **_random_shares(generator)) for index in range(1500)]
    for row in rows:
        for name, record in row["components"].items():
            assert 0.0 <= record["value_0_100"] <= 100.0
            assert record["normalisation_version"] == NORMALISATION_FRAME_VERSION
            assert COMPONENT_FUNCTIONS[name](frame, **record["inputs"]) == record
        flood = row["components"]["flood_likelihood_0_100"]
        by_anchor = {entry["anchor"]: entry["value_0_100"] for entry in flood["anchor_sensitivity_one_at_a_time"]}
        by_anchor[flood["anchor"]] = flood["value_0_100"]
        ordered = [by_anchor[anchor] for anchor in sorted(by_anchor)]
        assert ordered == sorted(ordered, reverse=True)  # a smaller anchor never gives a smaller value
        assert flood["value_0_100"] == pytest.approx(100 * min(1, flood["flooded_share"] / frame.flood_anchor))
    assert reject_batch_scaled_components(frame, rows)["components_checked"] == 7500


def test_a_unit_keeps_its_values_whatever_else_is_in_the_batch(frame: PlanningFrame) -> None:
    generator = random.Random(4009)
    shares = _random_shares(generator)
    alone = _unit_row(frame, "SYN-KEPT", **shares)
    for size in (1, 5, 40):
        others = [_unit_row(frame, f"SYN-{size}-{index}", **_random_shares(generator)) for index in range(size)]
        batch = [_unit_row(frame, "SYN-KEPT", **shares), *others]
        generator.shuffle(batch)
        assert reject_batch_scaled_components(frame, batch)["rows_checked"] == size + 1
        assert next(row for row in batch if row["unit_id"] == "SYN-KEPT") == alone


def test_share_components_do_not_depend_on_the_size_of_the_unit(frame: PlanningFrame) -> None:
    generator = random.Random(712)
    pairs = [
        (flood_likelihood, "flooded_non_permanent_water_land_area", "non_permanent_water_land_area"),
        (exposure, "residents_inside_flood_extent", "unit_residents"),
        (road_criticality, "residents_losing_all_routes", "residents_with_baseline_route"),
    ]
    for _ in range(400):
        whole = 10 + 10_000 * generator.random()
        part = whole * generator.random()
        factor = generator.choice([0.001, 0.5, 3.0, 1e6])
        for function, part_name, whole_name in pairs:
            value = function(frame, **{part_name: part, whole_name: whole})["value_0_100"]
            scaled = function(frame, **{part_name: part * factor, whole_name: whole * factor})["value_0_100"]
            assert scaled == pytest.approx(value, rel=1e-9, abs=1e-9)
            more = function(frame, **{part_name: min(whole, part * 1.1), whole_name: whole})["value_0_100"]
            assert more >= value  # more flooded land or more affected residents never lowers a component
        counts = {"hospital": (whole, part), "main_road_entry": (2 * whole, 0.0)}
        scaled_counts = {name: (baseline * factor, lost * factor) for name, (baseline, lost) in counts.items()}
        gap = access_gap(frame, services=_services(frame, counts))["value_0_100"]
        assert access_gap(frame, services=_services(frame, scaled_counts))["value_0_100"] == pytest.approx(gap, abs=1e-9)
        assert gap == pytest.approx(100 * part / (3 * whole))


def test_access_gap_lies_between_the_lowest_and_the_highest_service_share(frame: PlanningFrame) -> None:
    generator = random.Random(15)
    defined = 0
    for _ in range(400):
        counts = {}
        for service in frame.access_services:
            baseline = generator.choice([0.0, 50.0, 5000 * generator.random()])
            counts[service.service] = (baseline, baseline * generator.random())
        if generator.random() < 0.5:
            del counts["ddpm_located_shelter"]
        total = sum(baseline for baseline, _lost in counts.values())
        if total == 0:
            with pytest.raises(NormalisationError, match="states no access gap"):
                access_gap(frame, services=_services(frame, counts))
            continue
        defined += 1
        result = access_gap(frame, services=_services(frame, counts))
        shares = [row["newly_lost_share"] for row in result["services"] if row["newly_lost_share"] is not None]
        assert 100 * min(shares) - 1e-9 <= result["value_0_100"] <= 100 * max(shares) + 1e-9
        assert result["value_0_100"] == pytest.approx(100 * sum(lost for _baseline, lost in counts.values()) / total)
    assert 300 < defined < 400


def test_vulnerability_never_falls_as_the_dependent_share_rises(frame: PlanningFrame) -> None:
    shares = [index / 200 for index in range(201)]
    values = [_vulnerability(frame, share)["value_0_100"] for share in shares]
    wide = [_vulnerability(frame, share)["anchor_sensitivity"]["value_0_100"] for share in shares]
    assert values == sorted(values) and wide == sorted(wide)
    assert values[0] == wide[0] == 0.0 and values[-1] == wide[-1] == 100.0
    assert all(0.0 <= value <= 100.0 for value in (*values, *wide))
