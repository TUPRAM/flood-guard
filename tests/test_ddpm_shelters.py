"""DDPM shelter reader: the column whitelist and the shared-coordinate rule.

The rows are invented. The names and phone numbers below are test strings, not
people; the point of the tests is that they never reach the output.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from floodguard.ddpm_shelters import (
    CAPACITY_STATUS,
    COLUMN_WHITELIST,
    LABEL,
    LOCATED,
    LOCATION_MISSING,
    LOCATION_UNVERIFIED,
    OUTPUT_KEYS,
    DdpmShelterError,
    flag_locations,
    read_ddpm_shelters,
    summarise,
    whitelist_rows,
)

HEADER = [
    "ที่", "ภาค", "จังหวัด",
    "อำเภอ", "ตำบล",
    "หมู่บ้าน/ชุมชน",
    "สถานที่", "รองรับ",
    "สถานที่รับผิดชอบอปท.",
    "ชื่อ - สกุล ผู้ประสาน",
    "หมายเลขโทรศัพท์",
    "ไฟฟ้า", "ประปา", "สุขา",
    "ละติจูด", "ลองจิจูด",
]
PERSON = "TEST-COORDINATOR-NAME"
PHONE = "000-TEST-PHONE"


def _row(number: int, places: str, latitude: str, longitude: str) -> list[str]:
    return [str(number), "north", "province", "district", "tambon", "village", f"place {number}", places,
            "lao", PERSON, PHONE, "yes", "yes", "yes", latitude, longitude]


def _write(tmp_path: Path, rows: list[list[str]], header: list[str] | None = None) -> Path:
    path = tmp_path / "shelters.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header or HEADER)
        writer.writerows(rows)
    return path


def test_output_keys_are_a_subset_of_the_whitelist_and_no_personal_field_survives(tmp_path: Path) -> None:
    path = _write(tmp_path, [_row(1, "1,000", "20.40", "99.88"), _row(2, "50", "20.41", "99.89")])
    rows = read_ddpm_shelters(path)
    assert len(rows) == 2
    for row in rows:
        assert set(row) <= OUTPUT_KEYS
        assert PERSON not in map(str, row.values()) and PHONE not in map(str, row.values())
        assert row["capacity_status"] == CAPACITY_STATUS == "listed_planned_unverified"
        assert row["label"] == LABEL
    assert len(COLUMN_WHITELIST) == 8
    assert not {HEADER[9], HEADER[10]} & set(COLUMN_WHITELIST)  # coordinator name and phone number


def test_thousands_separators_are_parsed_as_numbers(tmp_path: Path) -> None:
    rows = read_ddpm_shelters(_write(tmp_path, [_row(1, "1,000", "20.40", "99.88"), _row(2, "", "20.41", "99.89")]))
    assert rows[0]["listed_places"] == 1000.0
    assert rows[1]["listed_places"] is None
    summary = summarise(rows)
    assert summary["listed_places"] == 1000.0 and summary["rows_without_a_listed_capacity"] == 1


def test_a_coordinate_shared_by_three_rows_is_not_a_location(tmp_path: Path) -> None:
    source = [_row(index, "50", "20.40341", "99.885466") for index in range(1, 4)]
    source += [_row(4, "200", "20.5", "99.9"), _row(5, "300", "20.5", "99.9"), _row(6, "70", "", "99.9"),
               _row(7, "80", "120.0", "99.9")]
    rows = read_ddpm_shelters(_write(tmp_path, source))
    assert [row["location_status"] for row in rows] == [
        LOCATION_UNVERIFIED, LOCATION_UNVERIFIED, LOCATION_UNVERIFIED, LOCATED, LOCATED,
        LOCATION_MISSING, LOCATION_MISSING,
    ]
    summary = summarise(rows)
    assert summary == {
        "listed_rows": 7, "listed_places": 800.0, "located_rows": 2, "located_places": 500.0,
        "unlocated_rows": 5, "unlocated_places": 300.0, "rows_without_a_listed_capacity": 0,
    }
    with pytest.raises(DdpmShelterError):
        flag_locations(rows, shared_rows_min=1)


def test_a_file_without_the_expected_columns_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DdpmShelterError, match="header"):
        read_ddpm_shelters(_write(tmp_path, [], header=HEADER[:-1]))
    with pytest.raises(DdpmShelterError, match="lacks"):
        whitelist_rows([{"only": "this"}])
