"""Checks for definition boundaries, explicit demand and destination claims."""

import csv
import json

import pytest

from floodguard.evidence_population_review import (
    build_capacity_demand,
    build_population_review,
    review_destination_identities,
    review_population_groups,
)

STAMP = "2026-09-21T10:50:00+00:00"


def population_source(tmp_path, labels, *, flags=None):
    rows = []
    for index, label in enumerate(labels):
        rows.append(
            {
                "record_id": str(index),
                "category": "age",
                "age_label_raw": label,
                "province_source": "pathum_thani",
                "geography_level": "province",
                "district_name_raw": "",
                "year_ce": 2024,
                "reported_total": 100,
                "male": 50,
                "female": 50,
                "computed_sex_sum": 100,
                "qc_flags": json.dumps(flags or []),
                "raw_values": "{}",
                "source_url": "https://example.go.th/population",
            }
        )
    with (tmp_path / "population_context.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_participation_changes_only_capacity_demand_and_conserves_residents():
    original = [{"population_id": "p", "total_population": 500, "subdistrict_id": "s"}]
    result = build_capacity_demand(
        original,
        demand_basis="residential_participation",
        participation_fraction=0.1,
        assumption_id="residential-10pct",
    )
    assert result["population_rows"][0]["total_population"] == 50
    assert result["population_rows"][0]["residential_population"] == 500
    assert result["population_rows"][0]["subdistrict_id"] == "s"
    assert result["total_residential_population"] == 500
    assert result["actual_evacuation_demand"] is None
    assert original[0]["total_population"] == 500


def test_risk_demand_does_not_replace_missing_risk_with_residents_or_zero():
    rows = [
        {
            "population_id": "a",
            "total_population": 200,
            "population_at_risk": 40,
            "population_at_risk_basis": "historical footprint intersection",
        },
        {"population_id": "b", "total_population": 100},
    ]
    result = build_capacity_demand(
        rows,
        demand_basis="population_at_risk_participation",
        participation_fraction=0.25,
        assumption_id="risk-25pct",
    )
    assert result["known_scenario_demand_population"] == 10
    assert result["scenario_demand_population"] is None
    assert result["allocation_eligible"] is False
    assert result["unresolved_population_ids"] == ["b"]
    assert result["population_rows"][1]["total_population"] is None


@pytest.mark.parametrize("fraction", [-1, 1.1, float("nan"), True])
def test_invalid_participation_is_rejected(fraction):
    with pytest.raises(ValueError):
        build_capacity_demand(
            [],
            demand_basis="residential_participation",
            participation_fraction=fraction,
            assumption_id="test",
        )


def test_risk_requires_basis_and_cannot_exceed_residents():
    for risk, basis in [(20, ""), (101, "footprint")]:
        with pytest.raises(ValueError):
            build_capacity_demand(
                [
                    {
                        "population_id": "p",
                        "total_population": 100,
                        "population_at_risk": risk,
                        "population_at_risk_basis": basis,
                    }
                ],
                demand_basis="population_at_risk_participation",
                participation_fraction=0.1,
                assumption_id="test",
            )


def test_full_residential_is_explicit_diagnostic_and_ids_unique():
    row = {"population_id": "p", "total_population": 100}
    with pytest.raises(ValueError):
        build_capacity_demand(
            [row],
            demand_basis="full_residential_diagnostic",
            participation_fraction=0.1,
            assumption_id="full",
        )
    with pytest.raises(ValueError):
        build_capacity_demand(
            [row, row],
            demand_basis="residential_participation",
            participation_fraction=0.1,
            assumption_id="duplicate",
        )
    result = build_capacity_demand(
        [row],
        demand_basis="full_residential_diagnostic",
        participation_fraction=1,
        assumption_id="diagnostic",
    )
    assert result["is_full_residential_diagnostic"]
    assert result["actual_evacuation_demand"] is None


def test_literal_bands_allow_source_grain_context_without_local_equity(tmp_path):
    population_source(tmp_path, ["0-4 ปี", "05-9 ปี", "10 ปีขึ้นไป"])
    result = review_population_groups(tmp_path, generated_at=STAMP)
    check = result["denominator_checks"][0]
    assert check["context_distribution_eligible"]
    assert check["classified_age_sum"] == 300
    assert check["independent_registered_total"] is None
    assert check["event_local_group_counts_eligible"] is False
    assert result["demographic_equity_eligible"] is False


def test_generic_children_definition_does_not_override_ambiguous_source(tmp_path):
    population_source(
        tmp_path, ["วัยเด็ก", "วัยแรงงาน", "ผู้สูงอายุ (60 ปีขึ้นไป)", "ผู้สูงอายุ (65 ปีขึ้นไป)"]
    )
    result = review_population_groups(
        tmp_path, generated_at=STAMP, source_evidence=[{"generic_child_age": "0-14"}]
    )
    definitions = {d["source_label"]: d for d in result["definitions"]}
    assert definitions["วัยเด็ก"]["age_min_inclusive"] is None
    assert definitions["ผู้สูงอายุ (60 ปีขึ้นไป)"]["age_min_inclusive"] == 60
    check = result["denominator_checks"][0]
    assert check["classified_age_sum"] is None
    assert check["context_distribution_eligible"] is False
    assert "overlapping_age_categories_must_not_be_summed" in check["reason_codes"]


def test_gaps_and_bad_arithmetic_block_context_partition(tmp_path):
    population_source(tmp_path, ["0-4 ปี", "10 ปีขึ้นไป"])
    assert not review_population_groups(tmp_path, generated_at=STAMP)[
        "denominator_checks"
    ][0]["context_distribution_eligible"]
    population_source(tmp_path, ["0-4 ปี", "5 ปีขึ้นไป"], flags=["sex_total_mismatch"])
    assert not review_population_groups(tmp_path, generated_at=STAMP)[
        "denominator_checks"
    ][0]["context_distribution_eligible"]


def test_identity_and_dated_activity_do_not_verify_geometry_or_capacity(tmp_path):
    (tmp_path / "shelter_candidates.geojson").write_text(
        json.dumps(
            {
                "features": [
                    {
                        "properties": {
                            "record_id": "s",
                            "aoi_matches": ["aoi-01_mae_sai_core"],
                            "records_sharing_coordinate": 10,
                            "phone": "private",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    reviews = [
        {
            "source_record_id": "s",
            "source_url": "https://agency.go.th/report",
            "retrieved_at_utc": STAMP,
            "evidence_basis": "official dated report",
            "name_match": True,
            "address_match": True,
            "official_facility_id": "site",
            "reported_event_activity": {
                "date": "2024-09-11",
                "summary": "Reported occupied venue.",
            },
        }
    ]
    result = review_destination_identities(tmp_path, reviews, generated_at=STAMP)
    row = result["rows"][0]
    assert result["supported_name_address_matches"] == 1
    assert result["dated_venue_activity_reports"] == 1
    assert row["coordinate_verified"] is False
    assert row["event_available_capacity"] is None
    assert row["event_availability"] == "unknown"
    assert row["identity_merge_approved"] is False
    assert "phone" not in json.dumps(result)


def test_unmatched_review_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="absent"):
        review_destination_identities(
            tmp_path,
            [
                {
                    "source_record_id": "missing",
                    "source_url": "https://agency.go.th/report",
                    "retrieved_at_utc": STAMP,
                    "evidence_basis": "official page",
                }
            ],
            generated_at=STAMP,
        )


def test_public_summary_omits_local_counts_and_source_records(tmp_path):
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    population_source(normalized, ["0-4 ปี", "5 ปีขึ้นไป"])
    summary = build_population_review(
        normalized, tmp_path / "review", generated_at=STAMP
    )
    text = json.dumps(summary)
    assert "classified_age_sum" not in text
    assert "raw_values" not in text
    assert "source_record_id" not in text
    assert summary["capacity"]["actual_available_shelter_capacity"] is None
    assert summary["capacity"]["default_participation_fraction"] == 0.1


def test_zero_classified_denominator_is_not_eligible(tmp_path):
    population_source(tmp_path, ["0-4 ปี", "5 ปีขึ้นไป"])
    path = tmp_path / "population_context.csv"
    text = path.read_text(encoding="utf-8").replace(",100,50,50,100,", ",0,0,0,0,")
    path.write_text(text, encoding="utf-8")
    result = review_population_groups(tmp_path, generated_at=STAMP)
    assert result["denominator_checks"][0]["classified_age_sum"] == 0
    assert not result["denominator_checks"][0]["context_distribution_eligible"]


def test_source_village_codes_preserve_repeated_keys(tmp_path):
    population_source(tmp_path, ["0-4 ปี", "5 ปีขึ้นไป"])
    path = tmp_path / "population_context.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [*reader.fieldnames, "subdistrict_code_raw", "village_code_raw"]
        rows = list(reader)
    village = {
        **rows[0],
        "category": "total",
        "geography_level": "village",
        "province_source": "songkhla",
        "subdistrict_code_raw": "90010500",
        "village_code_raw": "90010501",
    }
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([*rows, village, village])
    check = review_population_groups(tmp_path, generated_at=STAMP)[
        "administrative_code_checks"
    ][0]
    assert check["invalid_code_prefix_rows"] == 0
    assert check["repeated_code_pair_rows"] == 1
    assert check["spatial_join_eligible"] is False
