"""Build the THEOS-2 request AOI GeoJSON files.

Writes `resources/aoi/floodguard_theos2_aoi_v1.geojson` (all AOIs) plus one file
per AOI. Acquisition windows carry the measured Sentinel-2 evidence produced by
`scripts/scout_theos2_aoi_cloud.py`, so the requested date ranges and cloud
limits are reproducible rather than assumed.

The AOI bounds for Mae Sai are derived from the committed ADM3 boundaries in
`outputs/mae_sai_admin_context.geojson`. Hat Yai is centred on the study point
used by the `hat_yai_2025` CDSE profile. The Chao Phraya AOIs are newly proposed
for this request and are not present in committed FloodGuard evidence.

These AOIs are an acquisition request. They grant no permission, clear no gate,
and are not a decision input.

Usage:
    python scripts/build_theos2_aoi.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "resources" / "aoi"

# Nominal THEOS-2 PMS footprint used for the scene-count estimate.
THEOS2_PMS_SWATH_KM = 10.3

AOIS = [
    dict(
        aoi_id="AOI-01",
        slug="mae_sai_core",
        name="Mae Sai core - town, border crossing and Sai River strip",
        name_th="แม่สาย (เขตเมืองและแนวแม่น้ำสาย)",
        priority="P1",
        event_id="mae_sai_2024",
        event_name="Chiang Rai / Mae Sai flood, September 2024",
        province="Chiang Rai",
        district="Mae Sai",
        adm3_covered=(
            "Full: TH570901 Mae Sai, TH570906 Wiang Phang Kham. "
            "Partial: TH570904 Pong Pha (~43%), TH570905 Si Mueang Chum (~27%), "
            "TH570903 Ko Chang (~9%)."
        ),
        bbox=[99.8384, 20.3705, 99.9441, 20.4563],
        derivation=(
            "Union of the committed HDX COD-AB ADM3 boundaries for Mae Sai and "
            "Wiang Phang Kham in outputs/mae_sai_admin_context.geojson, the two "
            "subdistricts on the Sai River border strip that took the worst "
            "September 2024 inundation."
        ),
        purpose=(
            "Primary study area. Verify 42 OSM-derived candidate facilities and "
            "the bridge/road segments that drive the access-loss model, and give "
            "the Sentinel-1 SAR change detector an optical false-positive screen."
        ),
    ),
    dict(
        aoi_id="AOI-02",
        slug="mae_sai_district",
        name="Mae Sai district - full 8-subdistrict decision extent",
        name_th="อำเภอแม่สาย (ครบ 8 ตำบล)",
        priority="P2",
        event_id="mae_sai_2024",
        event_name="Chiang Rai / Mae Sai flood, September 2024",
        province="Chiang Rai",
        district="Mae Sai",
        adm3_covered=(
            "TH570901 Mae Sai; TH570902 Huai Khrai; TH570903 Ko Chang; "
            "TH570904 Pong Pha; TH570905 Si Mueang Chum; TH570906 Wiang Phang Kham; "
            "TH570908 Ban Dai; TH570909 Pong Ngam"
        ),
        bbox=[99.8107, 20.2577, 100.0368, 20.4651],
        derivation=(
            "Bounding box of all 8 ADM3 polygons in "
            "outputs/mae_sai_admin_context.geojson, verified to contain every "
            "polygon in full. This is the exact extent the FloodGuard decision "
            "layer scores today."
        ),
        purpose=(
            "Full-district coverage so every scored subdistrict, including the "
            "current highest-priority unit TH570903 Ko Chang, has optical "
            "evidence rather than only the two border subdistricts."
        ),
    ),
    dict(
        aoi_id="AOI-03",
        slug="hat_yai_core",
        name="Hat Yai core - municipality and U Taphao canal reach",
        name_th="หาดใหญ่ (เขตเทศบาลและคลองอู่ตะเภา)",
        priority="P1",
        event_id="hat_yai_2025",
        event_name="Hat Yai / Songkhla flood, November 2025",
        province="Songkhla",
        district="Hat Yai",
        adm3_covered="Hat Yai municipality and adjacent Khlong Hae / Khu Tao reach",
        bbox=[100.4300, 6.9650, 100.5200, 7.0550],
        derivation=(
            "Square tile centred on the Hat Yai study point POINT(100.47 7.01) "
            "used by the hat_yai_2025 CDSE profile in src/floodguard/cdse.py, "
            "sized to a single THEOS-2 PMS footprint."
        ),
        purpose=(
            "Second development event. Dense urban canal-basin flooding is a "
            "different terrain regime from the Mae Sai border valley, which is "
            "what the immutable multi-event partition contract needs."
        ),
    ),
    dict(
        aoi_id="AOI-04",
        slug="hat_yai_basin",
        name="Hat Yai extended - U Taphao basin to Songkhla Lake outlet",
        name_th="ลุ่มน้ำคลองอู่ตะเภา (ขยาย)",
        priority="P3",
        event_id="hat_yai_2025",
        event_name="Hat Yai / Songkhla flood, November 2025",
        province="Songkhla",
        district="Hat Yai and adjacent districts",
        adm3_covered="Hat Yai and neighbouring subdistricts along the U Taphao canal",
        bbox=[100.3800, 6.9000, 100.5800, 7.1200],
        derivation=(
            "Extension of AOI-03 along the U Taphao canal axis toward the "
            "Songkhla Lake outlet, to capture upstream-to-outlet flood routing."
        ),
        purpose=(
            "Optional. Only useful if upstream basin context is needed to explain "
            "the Hat Yai urban flood; not required for the first development run."
        ),
    ),
    dict(
        aoi_id="AOI-05",
        slug="chao_phraya_bang_ban_sena",
        name="Lower Chao Phraya - Bang Ban / Sena, Phra Nakhon Si Ayutthaya",
        name_th="บางบาล / เสนา จังหวัดพระนครศรีอยุธยา",
        priority="P1",
        event_id="chao_phraya_2024",
        event_name="Lower Chao Phraya seasonal flooding, 2024 and 2025",
        province="Phra Nakhon Si Ayutthaya",
        district="Bang Ban and Sena",
        adm3_covered="Bang Ban and Sena subdistricts on the Chao Phraya / Noi River reach",
        bbox=[100.4000, 14.2500, 100.5200, 14.3700],
        derivation=(
            "Newly proposed for this request. Not yet present in committed "
            "FloodGuard evidence. Selected because this reach of the lower Chao "
            "Phraya floods almost every monsoon and is a flat alluvial floodplain."
        ),
        purpose=(
            "Third development event with a genuinely different hydrology, and "
            "the only AOI in this request where near-clear optical imagery during "
            "the flood season is confirmed to exist."
        ),
    ),
    dict(
        aoi_id="AOI-06",
        slug="chao_phraya_rangsit",
        name="Greater Bangkok fringe - Rangsit / Thanyaburi, Pathum Thani",
        name_th="รังสิต / ธัญบุรี จังหวัดปทุมธานี",
        priority="P2",
        event_id="chao_phraya_2024",
        event_name="Lower Chao Phraya seasonal flooding, 2024 and 2025",
        province="Pathum Thani",
        district="Thanyaburi and Lam Luk Ka",
        adm3_covered="Rangsit, Thanyaburi and Lam Luk Ka subdistricts",
        bbox=[100.6000, 13.9800, 100.7200, 14.0800],
        derivation=(
            "Newly proposed for this request. Not yet present in committed "
            "FloodGuard evidence. Represents the dense Greater Bangkok fringe "
            "named as the scale target in the project brief."
        ),
        purpose=(
            "Urban-density stress tile. High building and road density is the "
            "hardest case for the road-disruption and access-loss models. Carries "
            "the single clearest flood-season observation measured in this scout."
        ),
    ),
]

# Windows revised from the v1 proposal using scripts/scout_theos2_aoi_cloud.py.
# `measured_evidence` quotes AOI-clipped Sentinel-2 cloud fractions, not
# scene-level cloud cover. See outputs/theos2_aoi_cloud_scout.csv.
WINDOWS = {
    "mae_sai_2024": [
        dict(
            window_id="W1-pre-immediate",
            label="Immediate pre-event baseline",
            start="2024-09-01",
            end="2024-09-08",
            max_cloud_pct=40,
            portal_scene_cloud_filter_pct=40,
            expectation="high",
            revision="added after cloud scout",
            measured_evidence=(
                "2024-09-05 measured at 12.5% AOI cloud (AOI-01) and 14.7% "
                "(AOI-02), at 100% AOI coverage."
            ),
            note=(
                "Five days before the flood peak. Seasonally matched to the event, "
                "so it pairs far better for change detection than a January "
                "baseline. Highest-value single date for this event."
            ),
        ),
        dict(
            window_id="W2-event",
            label="Flood event window",
            start="2024-09-09",
            end="2024-09-30",
            max_cloud_pct=95,
            portal_scene_cloud_filter_pct=95,
            expectation="very_low",
            revision="cloud limit raised, window widened",
            measured_evidence=(
                "Every Sentinel-2 date in this window is heavily obscured. Flood "
                "peak 2024-09-10 at 100% AOI cloud; best in window 2024-09-30 at "
                "89.2% (AOI-02). No date below 80%."
            ),
            note=(
                "Requested only in case THEOS-2 caught a break that Sentinel-2 "
                "missed. A null result here is expected and is not a problem."
            ),
        ),
        dict(
            window_id="W3-post",
            label="Post-event clear baseline",
            start="2025-01-05",
            end="2025-01-31",
            max_cloud_pct=10,
            portal_scene_cloud_filter_pct=45,
            expectation="very_high",
            revision="narrowed from 2024-11-01 to 2025-01-31",
            measured_evidence=(
                "2025-01-13, 2025-01-18 and 2025-01-23 all measured at 0.0% AOI "
                "cloud; 2025-01-28 at 0.3%."
            ),
            note=(
                "Best window for facility and road verification. Post-monsoon and "
                "before the northern biomass-burning haze season."
            ),
        ),
        dict(
            window_id="W4-post-early",
            label="Early post-event baseline",
            start="2024-11-01",
            end="2024-11-20",
            max_cloud_pct=10,
            portal_scene_cloud_filter_pct=40,
            expectation="high",
            revision="split out of the original W3",
            measured_evidence=(
                "2024-11-04 at 0.2%, 2024-11-14 at 0.2%, 2024-11-19 at 0.7% AOI "
                "cloud."
            ),
            note=(
                "Closer to the event than W3. Preferred if post-flood recovery "
                "state matters more than maximum clarity."
            ),
        ),
    ],
    "hat_yai_2025": [
        dict(
            window_id="W1-event",
            label="Flood event window",
            start="2025-11-28",
            end="2025-12-08",
            max_cloud_pct=70,
            portal_scene_cloud_filter_pct=70,
            expectation="medium",
            revision="narrowed and cloud limit lowered from 80%",
            measured_evidence=(
                "2025-12-03 at 39.3% AOI cloud (AOI-03) and 40.2% (AOI-04); "
                "2025-12-01 at 63.8% / 50.7%. Both inside the requested window."
            ),
            note=(
                "A genuine partial-visibility opportunity during the flood. This "
                "is the most realistic flood-period optical chance in the whole "
                "request and should be treated as high priority despite the cloud."
            ),
        ),
        dict(
            window_id="W2-pre",
            label="Pre-event clear baseline",
            start="2025-03-25",
            end="2025-04-05",
            max_cloud_pct=15,
            portal_scene_cloud_filter_pct=25,
            expectation="medium",
            revision="narrowed from a five-month range",
            measured_evidence=(
                "Only 1 of 38 observed dates between 2025-03-01 and 2025-07-31 "
                "fell below 10% AOI cloud: 2025-03-31 at 3.0%. Next best was "
                "2025-07-14 at 14.4%."
            ),
            note=(
                "Deliberately narrow. The original five-month request at 10% cloud "
                "would have returned almost nothing; southern Thailand is far "
                "cloudier year-round than the north."
            ),
        ),
        dict(
            window_id="W3-post",
            label="Post-event clear baseline",
            start="2026-03-15",
            end="2026-04-15",
            max_cloud_pct=10,
            portal_scene_cloud_filter_pct=30,
            expectation="high",
            revision="narrowed from 2026-02-01 to 2026-06-30",
            measured_evidence=(
                "2026-04-12 at 0.1%, 2026-03-21 at 0.2%, 2026-03-26 at 0.2% AOI "
                "cloud."
            ),
            note="First reliably clear period after the November 2025 event.",
        ),
    ],
    "chao_phraya_2024": [
        dict(
            window_id="W1-event-2024",
            label="Flood event window 2024",
            start="2024-10-07",
            end="2024-11-15",
            max_cloud_pct=25,
            portal_scene_cloud_filter_pct=75,
            expectation="high",
            revision="narrowed and cloud limit lowered from 80%",
            measured_evidence=(
                "2024-11-11 at 6.5% AOI cloud (AOI-05) and 0.8% (AOI-06); "
                "2024-10-12 at 11.2%; 2024-10-17 at 13.8%."
            ),
            note=(
                "The best flood-period optical opportunity in this request. Clear "
                "imagery during the flood season demonstrably exists here, which "
                "is not true for Mae Sai or Hat Yai."
            ),
        ),
        dict(
            window_id="W2-event-2025",
            label="Flood event window 2025",
            start="2025-10-15",
            end="2025-11-20",
            max_cloud_pct=70,
            portal_scene_cloud_filter_pct=90,
            expectation="low",
            revision="narrowed, cloud limit lowered, priority reduced",
            measured_evidence=(
                "2025 was markedly cloudier. AOI-06 best 2025-11-16 at 3.4% and "
                "2025-10-22 at 17.5%; AOI-05 best in-window only 42.7%."
            ),
            note=(
                "Second seasonal repeat, useful as an independent event fold, but "
                "clearly lower value than the 2024 window."
            ),
        ),
        dict(
            window_id="W3-dry",
            label="Dry-season clear baseline",
            start="2025-01-15",
            end="2025-02-20",
            max_cloud_pct=10,
            portal_scene_cloud_filter_pct=55,
            expectation="very_high",
            revision="narrowed from 2025-01-01 to 2025-03-31",
            measured_evidence=(
                "2025-02-04 at 0.1%, 2025-02-19 at 0.1%, 2025-02-14 at 0.2%, "
                "2025-01-20 at 0.3% AOI cloud (AOI-06)."
            ),
            note="Central plain dry season; clear acquisitions are near certain.",
        ),
    ],
}

COMMON = {
    "project": "FloodGuard Thailand",
    "request_id": "FG-THEOS2-REQ-001",
    "request_version": "v2-cloud-scouted",
    "requested_on": "2026-09-17",
    "crs": "EPSG:4326 (WGS84)",
    "preferred_product": "ORTHO PMS, 4-band (B/G/R/NIR)",
    "cloud_metric": (
        "max_cloud_pct is the AOI-clipped Sentinel-2 SCL measurement from "
        "scripts/scout_theos2_aoi_cloud.py and is what determines whether an "
        "acquisition is usable. portal_scene_cloud_filter_pct is the scene-level "
        "value to enter in the GISTDA ordering portal, which filters over the "
        "whole satellite footprint rather than the AOI; entering the AOI value "
        "there would discard usable dates. See outputs/theos2_aoi_cloud_scout.csv "
        "and outputs/theos2_portal_cloud_thresholds.csv."
    ),
    "operational_status": "non_operational_research_prototype",
    "official_warning": False,
    "redistribution_intent": (
        "None. Imagery stays in a controlled workspace outside version control. "
        "Only derived, checksum-tracked evidence is committed."
    ),
}


def ring(bbox: list[float]) -> list[list[list[float]]]:
    x0, y0, x1, y1 = bbox
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def dims_km(bbox: list[float]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    mid_lat = (y0 + y1) / 2
    width = (x1 - x0) * 111.320 * math.cos(math.radians(mid_lat))
    height = (y1 - y0) * 110.574
    return round(width, 1), round(height, 1)


def build_feature(aoi: dict) -> dict:
    width, height = dims_km(aoi["bbox"])
    props = {key: value for key, value in aoi.items() if key != "bbox"}
    props.update(
        {
            "bbox_wgs84": aoi["bbox"],
            "approx_width_km": width,
            "approx_height_km": height,
            "approx_area_sq_km": round(width * height, 1),
            "approx_theos2_pms_scenes": (
                math.ceil(width / THEOS2_PMS_SWATH_KM)
                * math.ceil(height / THEOS2_PMS_SWATH_KM)
            ),
            "requested_windows": WINDOWS[aoi["event_id"]],
        }
    )
    props.update(COMMON)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": ring(aoi["bbox"])},
    }


def write_collection(path: Path, features: list[dict]) -> None:
    document = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def write_upload_geojson(path: Path, aoi: dict, label: str) -> None:
    """Minimal single-polygon GeoJSON for the GISTDA portal AOI upload.

    Deliberately stripped: no `crs` member (RFC 7946 implies WGS84 and an
    explicit one can confuse strict parsers) and no nested property objects,
    which some upload parsers reject.
    """
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": label},
                "geometry": {"type": "Polygon", "coordinates": ring(aoi["bbox"])},
            }
        ],
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def write_upload_kml(path: Path, aoi: dict, label: str) -> None:
    """Same polygon as KML, as a fallback if the GeoJSON upload is rejected."""
    coords = " ".join(f"{x},{y},0" for x, y in ring(aoi["bbox"])[0])
    document = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{label}</name>
    <Placemark>
      <name>{label}</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>{coords}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""
    path.write_text(document, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    features = [build_feature(aoi) for aoi in AOIS]

    write_collection(OUT_DIR / "floodguard_theos2_aoi_v1.geojson", features)
    for aoi, feature in zip(AOIS, features):
        write_collection(
            OUT_DIR / f"{aoi['aoi_id'].lower()}_{aoi['slug']}.geojson", [feature]
        )

    upload_dir = OUT_DIR / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    print()
    for aoi in AOIS:
        label = f"{aoi['aoi_id']} {aoi['slug'].replace('_', ' ')}"
        stem = f"{aoi['aoi_id'].lower()}_{aoi['slug']}"
        write_upload_geojson(upload_dir / f"{stem}.geojson", aoi, label)
        write_upload_kml(upload_dir / f"{stem}.kml", aoi, label)

    print()
    for aoi, feature in zip(AOIS, features):
        props = feature["properties"]
        print(
            f"{aoi['aoi_id']} {props['priority']} {aoi['slug']:28s} "
            f"{props['approx_width_km']} x {props['approx_height_km']} km  "
            f"~{props['approx_theos2_pms_scenes']} scenes  "
            f"{len(props['requested_windows'])} windows"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
