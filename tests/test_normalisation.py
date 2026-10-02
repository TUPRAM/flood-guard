"""National vulnerability anchors: pure arithmetic on invented units.

No test here reads a real raster or boundary, and none computes an FPPS, a
class or a component value. The one test that looks at the committed receipt
checks its shape and that protocol v1b repeats it exactly.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard.normalisation import (
    ANCHOR_PERCENTILES,
    MIN_UNIT_RESIDENTS,
    NormalisationError,
    dependent_share,
    national_vulnerability_anchors,
    percentile_linear,
    percentile_weighted,
    select_anchor_units,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "outputs" / "planning_v1" / "national_vulnerability_anchors_v1.json"
PROTOCOL = ROOT / "docs" / "proposal_execution" / "planning_protocol_v1b.json"
SCRIPT = ROOT / "scripts" / "build_national_vulnerability_anchors.py"


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
    with pytest.raises(NormalisationError, match="min_residents"):
        select_anchor_units(_units(2), min_residents=0)


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
