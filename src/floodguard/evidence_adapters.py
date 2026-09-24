"""Deterministic, local-only normalization of the acquired evidence bundle.

Adapters preserve source errors and unknowns. They do not authorize publication,
infer event-time availability, impute observations, or change scoring contracts.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any = None) -> Any:
    return (
        json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default
    )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: json.dumps(v, ensure_ascii=False, sort_keys=True)
                    if isinstance(v, (list, dict))
                    else v
                    for k, v in row.items()
                }
            )


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _number(value: Any) -> float | None:
    try:
        n = float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) else None


def _utc(value: str | None) -> str | None:
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return date.astimezone(timezone.utc).isoformat() if date.tzinfo else None


def _record_id(kind: str, sha256: str, index: int) -> str:
    return f"{kind}:{sha256}:{index}"


def _provenance(path: Path, root: Path, entry: dict | None = None) -> dict:
    entry = entry or {}
    digest = _hash(path)
    if entry.get("sha256") and entry["sha256"] != digest:
        raise ValueError(f"Source hash mismatch: {path.relative_to(root)}")
    retrieved = entry.get("retrieved_utc") or entry.get("retrieved_at_utc")
    return {
        "source_path": path.relative_to(root).as_posix(),
        "source_sha256": digest,
        "source_url": entry.get("download_url") or entry.get("source_url"),
        "retrieved_at_original": retrieved,
        "retrieved_at_utc": _utc(retrieved),
        "source_timestamp": entry.get("source_period")
        or entry.get("source_last_updated")
        or entry.get("http_last_modified"),
        "confidence": "source_preserved_unvalidated",
        "role": "historical_context",
    }


def _aoi_map(features: dict | list) -> dict:
    if isinstance(features, dict) and features.get("type") == "FeatureCollection":
        features = features["features"]
    if isinstance(features, list):
        return {
            str(
                f.get("id")
                or f.get("properties", {}).get("aoi_id")
                or f.get("properties", {}).get("name")
                or i
            ): f
            for i, f in enumerate(features)
        }
    return features


def _point_membership(lon: float, lat: float, aois: dict) -> list[str]:
    # Point coverage uses the true AOI geometry, including holes and boundary.
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
    except ImportError:
        return []
    point = Point(lon, lat)
    matches = []
    for key, value in aois.items():
        if value.get("type") == "FeatureCollection":
            geom = unary_union([shape(f["geometry"]) for f in value["features"]])
        else:
            geom = shape(value.get("geometry", value))
        if geom.covers(point):
            matches.append(key)
    return sorted(matches)


def _gauges(root: Path, out: Path, aois: dict) -> dict:
    folder = root / "thaiwater"
    manifest = _read_json(folder / "manifest.json", [])
    files = [x for x in manifest if x.get("kind") == "water_level_observations"]
    summaries, gaps, daily, stations, metadata_qa = [], [], [], {}, []
    plots = {
        "time_zone": "unconfirmed",
        "units": "m above MSL",
        "role": "historical_context",
        "series": [],
    }
    fields = [
        "record_id",
        "source_path",
        "source_sha256",
        "source_csv_record",
        "station_code",
        "timestamp_source",
        "timestamp_utc",
        "observation_timezone",
        "water_level_raw",
        "water_level_m_msl",
        "quality_flag_raw",
        "qc_flags",
        "confidence",
        "source_timestamp",
    ]
    dest = out / "gauge_observations.csv"
    with dest.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for entry in files:
            path = folder / entry["path"]
            provenance = _provenance(path, root, entry)
            station = str(entry.get("station_code") or path.stem)
            source_rows = _rows(path)
            by_time: dict[datetime, list[dict]] = defaultdict(list)
            missing, invalid_time, mismatches, outside, off_grid = 0, 0, 0, 0, 0
            month = entry.get("source_period") or path.parent.name
            year, mon = int(month[:4]), int(month[4:6])
            # Preserve the source clock: the observation timezone is unconfirmed.
            start = datetime(year, mon, 1)  # noqa: DTZ001
            end = start + timedelta(days=calendar.monthrange(year, mon)[1])
            for index, row in enumerate(source_rows, 2):
                raw = row.get("water_level", "")
                value = _number(raw)
                flags = []
                if value is None or value in {-999.0, -9999.0, -99999.0, 999999.0}:
                    value = None
                    flags.append("missing_measurement")
                    missing += 1
                try:
                    timestamp = datetime.fromisoformat(row.get("measure_datetime", ""))
                    if timestamp.tzinfo is not None:
                        raise ValueError("unexpected timezone in naive source")
                except ValueError:
                    timestamp = None
                    flags.append("invalid_or_unexpected_timestamp")
                    invalid_time += 1
                if str(row.get("station_code")) != station:
                    flags.append("station_code_mismatch")
                    mismatches += 1
                if timestamp is not None and not start <= timestamp < end:
                    flags.append("outside_source_month")
                    outside += 1
                if timestamp is not None and (
                    timestamp.minute % 10 or timestamp.second or timestamp.microsecond
                ):
                    flags.append("off_grid_timestamp")
                    off_grid += 1
                normalized = {
                    "record_id": _record_id("hii", provenance["source_sha256"], index),
                    "source_path": provenance["source_path"],
                    "source_sha256": provenance["source_sha256"],
                    "source_csv_record": index,
                    "station_code": row.get("station_code"),
                    "timestamp_source": row.get("measure_datetime"),
                    "timestamp_utc": None,
                    "observation_timezone": "unconfirmed",
                    "water_level_raw": raw,
                    "water_level_m_msl": value,
                    "quality_flag_raw": row.get("quality_flag"),
                    "qc_flags": ";".join(flags),
                    "confidence": "numeric_not_scientifically_validated"
                    if value is not None
                    else "missing",
                    "source_timestamp": row.get("measure_datetime"),
                }
                writer.writerow(normalized)
                if timestamp is not None and start <= timestamp < end:
                    by_time[timestamp].append(normalized)
            duplicates = sum(len(v) - 1 for v in by_time.values())
            segments, segment, gap = [], [], None
            day_counts: dict[str, Counter] = defaultdict(Counter)
            numeric_values, slots_missing, conflicts, absent = [], 0, 0, 0
            for slot in range(int((end - start).total_seconds() // 600)):
                time = start + timedelta(minutes=slot * 10)
                rows = by_time.get(time, [])
                values = {r["water_level_m_msl"] for r in rows}
                value = next(iter(values)) if len(values) == 1 else None
                if any("station_code_mismatch" in r["qc_flags"] for r in rows):
                    value = None
                reason = (
                    "absent_timestamp"
                    if not rows
                    else "conflicting_duplicates"
                    if len(values) > 1
                    else "station_code_mismatch"
                    if any("station_code_mismatch" in r["qc_flags"] for r in rows)
                    else "missing_measurement"
                )
                counts = day_counts[time.date().isoformat()]
                counts["expected_slots"] += 1
                if value is not None:
                    counts["numeric_slots"] += 1
                    numeric_values.append(value)
                    segment.append([time.isoformat(), value])
                    if gap:
                        gaps.append(gap)
                        gap = None
                else:
                    slots_missing += 1
                    counts[reason] += 1
                    absent += int(reason == "absent_timestamp")
                    conflicts += int(reason == "conflicting_duplicates")
                    if segment:
                        segments.append(segment)
                        segment = []
                    if gap and gap["reason"] != reason:
                        gaps.append(gap)
                        gap = None
                    if gap is None:
                        gap = {
                            "station_code": station,
                            "month": month,
                            "start_source": time.isoformat(),
                            "end_source": time.isoformat(),
                            "slots": 0,
                            "reason": reason,
                            "observation_timezone": "unconfirmed",
                            "source_path": provenance["source_path"],
                        }
                    gap["end_source"] = time.isoformat()
                    gap["slots"] += 1
            if segment:
                segments.append(segment)
            if gap:
                gaps.append(gap)
            for date, count in sorted(day_counts.items()):
                daily.append(
                    {
                        "station_code": station,
                        "date_source": date,
                        "observation_timezone": "unconfirmed",
                        **dict(count),
                        "measurement_coverage": count["numeric_slots"]
                        / count["expected_slots"],
                        "source_path": provenance["source_path"],
                    }
                )
            lon, lat = _number(entry.get("longitude")), _number(entry.get("latitude"))
            matches = (
                _point_membership(lon, lat, aois)
                if lon is not None and lat is not None
                else []
            )
            stations[(station, month)] = {
                "station_code": station,
                "month": month,
                "name": entry.get("station_name"),
                "longitude": lon,
                "latitude": lat,
                "aoi_matches": matches,
                "aoi_relationship_source": entry.get("aoi_relationship"),
                "role": "gauge_context",
                "hydrological_substitution_allowed": False,
                "source_timestamp": month,
                "confidence": "station_metadata_unvalidated",
            }
            summary = {
                **provenance,
                "station_code": station,
                "month": month,
                "rows": len(source_rows),
                "missing_measurement_rows": missing,
                "invalid_timestamp_rows": invalid_time,
                "outside_month_rows": outside,
                "off_grid_timestamp_rows": off_grid,
                "station_code_mismatches": mismatches,
                "duplicate_timestamp_rows": duplicates,
                "conflicting_slots": conflicts,
                "absent_slots": absent,
                "numeric_slots": len(numeric_values),
                "missing_slots": slots_missing,
                "expected_slots": len(numeric_values) + slots_missing,
                "max_observed_m_msl": max(numeric_values) if numeric_values else None,
                "event_peak_verified": False,
                "aoi_matches": matches,
                "observation_timezone": "unconfirmed",
                "segment_count": len(segments),
            }
            summaries.append(summary)
            plots["series"].append(
                {
                    "station_code": station,
                    "month": month,
                    "source_sha256": provenance["source_sha256"],
                    "segments": segments,
                    "missing_slots": slots_missing,
                    "source_timestamp": month,
                    "confidence": "unvalidated_measurements",
                }
            )
    for entry in manifest:
        if entry.get("kind") != "monthly_station_metadata":
            continue
        path = folder / entry["path"]
        _provenance(path, root, entry)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        metadata_qa.append(
            {
                "path": path.relative_to(root).as_posix(),
                "header_width": len(rows[0]),
                "data_width_counts": dict(Counter(len(r) for r in rows[1:])),
                "safe_field_count": min(9, len(rows[0])),
                "unsafe_trailing_fields_excluded": any(
                    len(r) != len(rows[0]) for r in rows[1:]
                ),
            }
        )
    _csv(out / "gauge_station_months.csv", list(stations.values()))
    station_positions = {}
    for info in stations.values():
        key = (info["station_code"], info["longitude"], info["latitude"])
        if key[1] is None or key[2] is None:
            continue
        if key not in station_positions:
            station_positions[key] = {**info, "months": []}
            station_positions[key].pop("month")
        station_positions[key]["months"].append(info["month"])
    _json(
        out / "gauge_stations.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": info,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [info["longitude"], info["latitude"]],
                    },
                }
                for info in station_positions.values()
            ],
            "metadata": {
                "role": "gauge_context",
                "observation_timezone": "unconfirmed",
            },
        },
    )
    _csv(out / "gauge_daily_coverage.csv", daily)
    _csv(out / "gauge_gaps.csv", gaps)
    _json(out / "gauge_hydrograph_segments.json", plots)
    _json(
        out / "gauge_qc.json",
        {"station_months": summaries, "metadata_schema": metadata_qa},
    )
    event_windows = []
    for station in ("SLA001", "SLA002", "SLA007", "ONE037"):
        selected = [
            d
            for d in daily
            if d["station_code"] == station
            and "2025-11-20" <= d["date_source"] <= "2025-11-28"
        ]
        if selected:
            expected = sum(d["expected_slots"] for d in selected)
            numeric = sum(d.get("numeric_slots", 0) for d in selected)
            event_windows.append(
                {
                    "station_code": station,
                    "start_source": "2025-11-20",
                    "end_source": "2025-11-28",
                    "expected_slots": expected,
                    "numeric_slots": numeric,
                    "missing_slots": expected - numeric,
                    "measurement_coverage": numeric / expected,
                    "observation_timezone": "unconfirmed",
                    "event_peak_verified": False,
                }
            )
    return {
        "status": "normalized" if files else "unavailable",
        "station_month_files": len(files),
        "stations": len({s[0] for s in stations}),
        "rows": sum(s["rows"] for s in summaries),
        "missing_measurement_rows": sum(
            s["missing_measurement_rows"] for s in summaries
        ),
        "numeric_slots": sum(s["numeric_slots"] for s in summaries),
        "gap_count": len(gaps),
        "schema_mismatches": sum(
            s["unsafe_trailing_fields_excluded"] for s in metadata_qa
        ),
        "observation_timezone": "unconfirmed",
        "units": "m above MSL",
        "station_months": summaries,
        "missing_sentinels": [-999, -9999, -99999, 999999],
        "hat_yai_event_window": event_windows,
        "all_missing_station_months": [
            s["source_path"] for s in summaries if not s["numeric_slots"]
        ],
        "limitations": [
            "Source observation timezone and quality-flag meanings remain unconfirmed",
            "Missing slots remain gaps; maximum observed is not a verified event peak",
            "Gauge water-surface elevation is not flood depth; outside-AOI stations are context only",
        ],
        "mae_sai_availability": _read_json(folder / "mae_sai_availability.json", {}),
        "outputs": [
            "gauge_observations.csv",
            "gauge_station_months.csv",
            "gauge_stations.geojson",
            "gauge_daily_coverage.csv",
            "gauge_gaps.csv",
            "gauge_hydrograph_segments.json",
            "gauge_qc.json",
        ],
    }


def _population(root: Path, out: Path) -> dict:
    folder = root / "dopa"
    manifest = _read_json(folder / "manifest.json", [])
    files = [entry for entry in manifest if entry.get("kind") == "population_csv"]
    records, summaries = [], []
    for entry in files:
        path = folder / entry["path"]
        prov = _provenance(path, root, entry)
        rows = _rows(path)
        subset = []
        for index, raw in enumerate(rows, 2):
            row = {
                k.strip(): v.strip() if isinstance(v, str) else v
                for k, v in raw.items()
                if k and k.strip()
            }
            year_raw = row.get("ปี", "")
            year_be = int(year_raw) if year_raw.isdigit() else None
            flags = []
            male = _number(row.get("ชาย", row.get("ประชากรชาย")))
            female = _number(row.get("หญิง", row.get("ประชากรหญิง")))
            total = _number(row.get("รวม", row.get("ประชากรทั้งหมด", row.get("จำนวน"))))
            computed_total = (
                male + female if male is not None and female is not None else None
            )
            arithmetic_error = (
                total is not None
                and computed_total is not None
                and total != computed_total
            )
            if arithmetic_error:
                flags.append("sex_total_mismatch")
            age_label = row.get("ช่วงอายุ") or row.get("รายการ", "")
            category = (
                "age"
                if "ช่วงอายุ" in row or any(word in age_label for word in ("วัย", "สูงอายุ"))
                else "total"
            )
            if category == "age" and "ช่วงอายุ" not in row:
                flags.append("age_definition_or_overlap_review_required")
            geography = (
                "village"
                if "รหัสหมู่บ้าน" in row
                else "district"
                if "อำเภอ" in row
                else "province"
            )
            record = {
                **prov,
                "record_id": _record_id("population", prov["source_sha256"], index),
                "source_csv_record": index,
                "source_timestamp": year_raw,
                "year_be_raw": year_raw,
                "year_ce": year_be - 543 if year_be else None,
                "province_source": path.parent.name,
                "geography_level": geography,
                "district_name_raw": row.get("อำเภอ"),
                "subdistrict_code_raw": row.get("รหัสตำบล"),
                "village_code_raw": row.get("รหัสหมู่บ้าน"),
                "registration_office_code_raw": row.get("รหัสสำนักทะเบียน"),
                "category": category,
                "age_label_raw": age_label,
                "male": male,
                "female": female,
                "reported_total": total,
                "computed_sex_sum": computed_total,
                "total_difference": total - computed_total
                if arithmetic_error
                else 0
                if total is not None and computed_total is not None
                else None,
                "administrative_join_status": "unresolved",
                "qc_flags": flags,
                "raw_values": row,
                "assumptions": "registered_population_context;no_AOI_allocation;no_imputation",
            }
            records.append(record)
            subset.append(record)
        summaries.append(
            {
                **prov,
                "rows": len(rows),
                "years_ce": sorted(
                    {r["year_ce"] for r in subset if r["year_ce"] is not None}
                ),
                "arithmetic_mismatches": sum(
                    "sex_total_mismatch" in r["qc_flags"] for r in subset
                ),
                "geography_levels": sorted({r["geography_level"] for r in subset}),
            }
        )
    mae = [
        r
        for r in records
        if r["province_source"] == "chiang_rai" and r["district_name_raw"] == "แม่สาย"
    ]
    comparisons = []
    for year in sorted({r["year_ce"] for r in mae if r["year_ce"] is not None}):
        rows = [r for r in mae if r["year_ce"] == year]
        child = next((r for r in rows if r["age_label_raw"] == "วัยเด็ก"), None)
        working = next((r for r in rows if r["age_label_raw"] == "วัยแรงงาน"), None)
        elderly = next((r for r in rows if "60 ปีขึ้นไป" in r["age_label_raw"]), None)
        total = next((r for r in rows if r["age_label_raw"] == "จำนวนประชากร"), None)
        chosen = [child, working, elderly]
        age_sum = (
            sum(r["reported_total"] for r in chosen)
            if all(r and r["reported_total"] is not None for r in chosen)
            else None
        )
        published = total["reported_total"] if total else None
        comparisons.append(
            {
                "district": "แม่สาย",
                "year_ce": year,
                "age_category_sum": age_sum,
                "reported_population_total": published,
                "difference_total_minus_categories": published - age_sum
                if published is not None and age_sum is not None
                else None,
                "age_record_ids": [r["record_id"] for r in chosen if r],
                "status": "unresolved_definitions_and_coverage",
            }
        )
    age_years = sorted(
        {
            r["year_ce"]
            for r in records
            if r["province_source"] == "chiang_rai" and r["category"] == "age"
        }
    )
    _csv(out / "population_context.csv", records)
    _json(
        out / "population_qc.json",
        {
            "sources": summaries,
            "mae_sai_comparisons": comparisons,
            "chiang_rai_age_years": age_years,
        },
    )
    return {
        "status": "normalized" if files else "unavailable",
        "files": len(files),
        "rows": len(records),
        "sources": summaries,
        "arithmetic_mismatches": sum(
            "sex_total_mismatch" in r["qc_flags"] for r in records
        ),
        "chiang_rai_age_years": age_years,
        "chiang_rai_2024_age_available": 2024 in age_years,
        "mae_sai_comparisons": comparisons,
        "administrative_crosswalk": "unresolved",
        "limitations": [
            "Registered population, not event-day presence",
            "No administrative crosswalk or AOI allocation accepted",
            "Age definitions and overlapping elderly categories require review; no 2024 age imputation",
        ],
        "outputs": ["population_context.csv", "population_qc.json"],
    }


def _facilities(root: Path, out: Path, aois: dict) -> tuple[dict, dict]:
    shelter_path = root / "shelters" / "dpm-gd002_final2.csv"
    records, features, clusters = [], [], defaultdict(list)
    province_names = {"เชียงราย", "สงขลา", "พระนครศรีอยุธยา", "ปทุมธานี"}
    if shelter_path.exists():
        source_entry = next(
            (
                entry
                for entry in _read_json(root / "shelters/provenance.json", [])
                if entry.get("file") == shelter_path.name
            ),
            {},
        )
        prov = _provenance(shelter_path, root, source_entry)
        for index, raw in enumerate(_rows(shelter_path), 2):
            if raw.get("จังหวัด", "").strip() not in province_names:
                continue
            lat, lon = _number(raw.get("ละติจูด")), _number(raw.get("ลองจิจูด"))
            valid = (
                lat is not None
                and lon is not None
                and 5 <= lat <= 21
                and 97 <= lon <= 106
            )
            cap_raw = str(raw.get("รองรับ", ""))
            cap_text = cap_raw.replace(",", "").strip()
            capacity = int(cap_text) if cap_text.isdigit() else None
            record_id = _record_id("ddpm", prov["source_sha256"], index)
            flags = [
                "activation_unknown",
                "identity_unverified",
                "planning_capacity_only",
            ]
            if not valid:
                flags.append("invalid_or_missing_coordinate")
            if capacity is None:
                flags.append("unknown_capacity")
            record = {
                **prov,
                "record_id": record_id,
                "source_csv_record": index,
                "source_ordinal": raw.get("ที่"),
                "province": raw.get("จังหวัด", "").strip(),
                "district": raw.get("อำเภอ", "").strip(),
                "subdistrict": raw.get("ตำบล", "").strip(),
                "village_community": raw.get("หมู่บ้าน/ชุมชน"),
                "place_name": raw.get("สถานที่"),
                "latitude_raw": raw.get("ละติจูด"),
                "longitude_raw": raw.get("ลองจิจูด"),
                "longitude": lon if valid else None,
                "latitude": lat if valid else None,
                "planning_capacity_raw": cap_raw,
                "planning_capacity": capacity,
                "event_available_capacity": None,
                "activation_status": "unknown",
                "site_identity_status": "unreviewed_source_record",
                "aoi_matches": _point_membership(lon, lat, aois) if valid else [],
                "source_timestamp": "2024-05-06",
                "resource_modified_at": "2024-08-09",
                "role": "candidate_destination",
                "confidence": "official_planning_list_unverified_site",
                "qc_flags": flags,
                "assumptions": "no_deduplication;no_capacity_sum;not_activation_dates",
            }
            records.append(record)
            if valid:
                clusters[(lon, lat)].append(record)
                features.append(
                    {
                        "type": "Feature",
                        "id": record_id,
                        "properties": record,
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    }
                )
    cluster_rows = []
    for (lon, lat), group in sorted(clusters.items()):
        cluster_id = (
            "coordinate:"
            + hashlib.sha256(f"{lon:.12g},{lat:.12g}".encode()).hexdigest()[:20]
        )
        for record in group:
            record["coordinate_cluster_id"] = cluster_id
            record["records_sharing_coordinate"] = len(group)
            if len(group) > 1:
                record["qc_flags"].append("shared_coordinate_identity_unresolved")
        if len(group) > 1:
            cluster_rows.append(
                {
                    "coordinate_cluster_id": cluster_id,
                    "longitude": lon,
                    "latitude": lat,
                    "record_ids": [r["record_id"] for r in group],
                    "record_count": len(group),
                    "resolution": "unresolved",
                }
            )
    _csv(out / "shelter_records.csv", records)
    _csv(out / "shelter_coordinate_clusters.csv", cluster_rows)
    _json(
        out / "shelter_candidates.geojson",
        {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "role": "candidate_destinations",
                "available_capacity": "unknown",
            },
        },
    )
    shelter_summary = {
        "status": "normalized" if shelter_path.exists() else "unavailable",
        "records": len(records),
        "valid_coordinate_records": len(features),
        "invalid_coordinate_records": len(records) - len(features),
        "distinct_coordinates": len(clusters),
        "unknown_planning_capacity_records": sum(
            r["planning_capacity"] is None for r in records
        ),
        "shared_coordinate_clusters": len(cluster_rows),
        "aoi_counts": {a: sum(a in r["aoi_matches"] for r in records) for a in aois},
        "aoi_distinct_coordinates": {
            a: len(
                {
                    (r["longitude"], r["latitude"])
                    for r in records
                    if a in r["aoi_matches"]
                }
            )
            for a in aois
        },
        "limitations": [
            "Source records are not verified distinct sites",
            "Planning capacities and catalog dates do not establish event activation or available capacity",
            "Shared coordinates remain unresolved; missing capacities are not zero",
        ],
        "outputs": [
            "shelter_records.csv",
            "shelter_candidates.geojson",
            "shelter_coordinate_clusters.csv",
        ],
    }
    health_path = root / "healthcare" / "thailand_health_facilities_th.geojson"
    health_records, health_features, source_ids = [], [], Counter()
    if health_path.exists():
        prov = _provenance(
            health_path, root, _read_json(root / "healthcare/download.json", {})
        )
        for index, feature in enumerate(_read_json(health_path)["features"]):
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coordinates = geom.get("coordinates", [])
            lon = (
                _number(coordinates[0])
                if len(coordinates) > 1 and geom.get("type") == "Point"
                else None
            )
            lat = (
                _number(coordinates[1])
                if len(coordinates) > 1 and geom.get("type") == "Point"
                else None
            )
            valid = (
                lon is not None
                and lat is not None
                and -180 <= lon <= 180
                and -90 <= lat <= 90
            )
            source_id = props.get("id", props.get("ID"))
            source_ids[str(source_id)] += 1
            # Only non-contact inventory labels are carried into derived display data.
            safe_props = {
                k: v
                for k, v in props.items()
                if not re.search(r"phone|tel|contact|email|โทร|ผู้ติดต่อ", k, re.IGNORECASE)
            }
            record_id = _record_id("health", prov["source_sha256"], index)
            record = {
                **prov,
                "record_id": record_id,
                "source_feature_index": index,
                "source_id_raw": source_id,
                "source_properties": safe_props,
                "longitude": lon if valid else None,
                "latitude": lat if valid else None,
                "aoi_matches": _point_membership(lon, lat, aois) if valid else [],
                "operation_status": "unknown",
                "event_availability": "unknown",
                "source_timestamp": "2020",
                "role": "candidate_destination",
                "confidence": "historical_mirror_unverified_current_status",
                "qc_flags": [
                    "source_id_not_trusted",
                    "historical_2020",
                    "event_availability_unknown",
                ]
                + ([] if valid else ["invalid_coordinate"]),
            }
            health_records.append(record)
            if valid:
                health_features.append(
                    {
                        "type": "Feature",
                        "id": record_id,
                        "properties": record,
                        "geometry": geom,
                    }
                )
    _csv(out / "healthcare_records.csv", health_records)
    _json(
        out / "healthcare_candidates.geojson",
        {
            "type": "FeatureCollection",
            "features": health_features,
            "metadata": {"role": "candidate_destinations", "source_vintage": "2020"},
        },
    )
    return shelter_summary, {
        "status": "normalized" if health_path.exists() else "unavailable",
        "records": len(health_records),
        "valid_coordinate_records": len(health_features),
        "distinct_source_ids": len(source_ids),
        "aoi_counts": {
            a: sum(a in r["aoi_matches"] for r in health_records) for a in aois
        },
        "limitations": [
            "Historical 2020 mirror with official-source lineage",
            "Current operation, service capability and event availability unknown",
            "Source ID is not a reliable facility key",
        ],
        "outputs": ["healthcare_records.csv", "healthcare_candidates.geojson"],
    }


def _roads(root: Path, out: Path) -> dict:
    folder = root / "roads" / "official_reports"
    records = []
    for path in sorted(folder.glob("*incidents_transcribed.csv")):
        prov = _provenance(path, root)
        for index, row in enumerate(_rows(path), 2):

            def chainage(value: str) -> int | None:
                match = re.fullmatch(r"(\d+)\+(\d{3})", value or "")
                return int(match[1]) * 1000 + int(match[2]) if match else None

            phrase = row.get("traffic_status_original_th", "")
            state = (
                "reported_impassable"
                if "ผ่านไม่ได้" in phrase
                else "reported_passable_with_difficulty"
                if "ผ่านได้ไม่สะดวก" in phrase
                else "unclassified"
            )
            records.append(
                {
                    **prov,
                    **row,
                    "record_id": _record_id(
                        "road_document", prov["source_sha256"], index
                    ),
                    "chainage_start_m": chainage(row.get("km_start", "")),
                    "chainage_end_m": chainage(row.get("km_end", "")),
                    "documentary_state": state,
                    "geometry_status": "unresolved",
                    "closure_geometry": None,
                    "routing_observation_accepted": False,
                    "source_timestamp": row.get("source_date"),
                    "role": "documentary_evidence",
                    "confidence": "unverified_geolocation",
                    "qc_flags": ["no_verified_road_geometry"]
                    + (["source_inconsistency"] if row.get("quality_note") else []),
                }
            )
    _csv(out / "road_documentary_evidence.csv", records)
    return {
        "status": "normalized" if records else "unavailable",
        "records": len(records),
        "states": dict(Counter(r["documentary_state"] for r in records)),
        "spatially_accepted_closures": 0,
        "narrative_reports": [
            p.name for p in sorted(folder.glob("*restoration*.html"))
        ],
        "limitations": [
            "Route/district and chainage discrepancies remain source evidence",
            "No verified geocoded road conditions; narrative restoration is not segment-level passability",
        ],
        "outputs": ["road_documentary_evidence.csv"],
    }


def normalize_bundle(
    bundle_root: str | Path, output_dir: str | Path, aoi_features: dict | list
) -> dict:
    """Normalize acquired data without modifying sources or accepting event claims.

    ``aoi_features`` accepts an ID-keyed mapping of GeoJSON geometries/features/
    collections, or a feature list with ``id``/``aoi_id`` properties. Artifacts are
    local analysis products under ``output_dir/normalized``. Geo checks gracefully
    report missing optional geo dependencies, rather than manufacture metrics.
    """
    root, destination = Path(bundle_root).resolve(), Path(output_dir).resolve()
    if destination == root or root in destination.parents:
        raise ValueError(
            "Normalized outputs must be outside the immutable source bundle"
        )
    out = destination / "normalized"
    out.mkdir(parents=True, exist_ok=True)
    aois = _aoi_map(aoi_features)
    datasets = {
        "gauges": _gauges(root, out, aois),
        "population": _population(root, out),
    }
    datasets["shelters"], datasets["healthcare"] = _facilities(root, out, aois)
    datasets["roads"] = _roads(root, out)
    from floodguard.evidence_adapters_geo import normalize_geospatial

    datasets.update(normalize_geospatial(root, out, aois))
    aoi_summary = {}
    for aoi in aois:
        aoi_summary[aoi] = {
            "shelter_records": datasets["shelters"]["aoi_counts"].get(aoi, 0),
            "shelter_distinct_coordinates": datasets["shelters"][
                "aoi_distinct_coordinates"
            ].get(aoi, 0),
            "healthcare_records": datasets["healthcare"]["aoi_counts"].get(aoi, 0),
            "gauge_station_months": sum(
                aoi in s["aoi_matches"] for s in datasets["gauges"]["station_months"]
            ),
            "gauge_stations": sorted(
                {
                    s["station_code"]
                    for s in datasets["gauges"]["station_months"]
                    if aoi in s["aoi_matches"]
                }
            ),
            "flood_reference": datasets["flood_reference"].get("aois", {}).get(aoi, {}),
            "terrain": next(
                (
                    s
                    for s in datasets["terrain"].get("rasters", [])
                    if s["aoi_id"] == aoi
                ),
                None,
            ),
            "event_accepted_shelter_capacity": None,
            "event_accepted_road_closures": None,
            "observed_subdistrict_age_population": None,
        }
    outputs = {
        filename: f"normalized/{filename}"
        for data in datasets.values()
        for filename in data.get("outputs", [])
    }
    summary = {
        "schema_version": "1.0",
        "role": "local_candidate_evidence",
        "status": "normalized_with_limitations",
        "datasets": datasets,
        "aois": aoi_summary,
        "outputs": outputs,
        "findings": [
            "No observation timezone inferred",
            "No missing values imputed",
            "No event validation or operational acceptance conferred",
            "Rights and publication gates are evaluated separately",
        ],
    }
    _json(destination / "adapter_summary.json", summary)
    return summary
