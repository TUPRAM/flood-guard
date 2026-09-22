"""Reviewed exclusions must not manufacture facility access or duplicate demand."""

import copy

import pytest

from floodguard.evidence_case_review import apply_destination_review


def fixture():
    context = {"input_hashes": {"osm": "a" * 64}, "osm_facilities": [
        {"facility_id": "point", "candidate_destination_eligible": True,
         "source_geometry": {"type": "Point", "coordinates": [1, 1]}, "capacity": None},
        {"facility_id": "site", "candidate_destination_eligible": True,
         "source_geometry": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}, "capacity": None},
    ]}
    review = {"osm_sha256": "a" * 64, "exclusions": [{"facility_id": "point", "duplicate_of": "site",
        "reason": "Reviewed same-site duplicate", "source_url": "https://example.org/site"}]}
    return context, review


def test_duplicate_review_preserves_raw_records_and_unknown_capacity():
    context, review = fixture()
    original = copy.deepcopy(context)
    result = apply_destination_review(context, review)
    assert context == original
    assert not result["osm_facilities"][0]["candidate_destination_eligible"]
    assert result["osm_facilities"][1]["candidate_destination_eligible"]
    assert all(row["capacity"] is None for row in result["osm_facilities"])


@pytest.mark.parametrize("damage", ["wrong_hash", "outside", "missing", "duplicate", "excluded_parent"])
def test_rejects_unsupported_review(damage):
    context, review = fixture()
    if damage == "wrong_hash":
        review["osm_sha256"] = "b" * 64
    elif damage == "outside":
        context["osm_facilities"][0]["source_geometry"]["coordinates"] = [3, 3]
    elif damage == "missing":
        review["exclusions"][0]["facility_id"] = "absent"
    elif damage == "duplicate":
        review["exclusions"] *= 2
    else:
        review["exclusions"].append({"facility_id": "site", "reason": "unresolved", "source_url": "https://example.org/site"})
    with pytest.raises(ValueError):
        apply_destination_review(context, review)
