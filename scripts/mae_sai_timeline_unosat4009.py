"""Season-envelope stage of the Mae Sai timeline bake: UNOSAT/GISTDA product 4009 as a scenario layer (SCN-ENV).

Imported by ``scripts/build_mae_sai_flood_timeline.py``. The stage reads one layer of the product archive,
``CHIANGRAI_20240801_20241012_AccumulatedFlood`` (accumulated water, August to October 2024), and nothing else from
it: no Phayao, Chiang Mai or Doi Tao layer (decision D11) and not the 22 October extent (decision D3b). It repairs
invalid polygon parts, clips the layer to the eight Mae Sai subdistricts, rasterises it and sets the modelled water
beside it.

The envelope is a scenario layer: water mapped at some time in the season, with no date per patch. It is never an
observation for a replay day, and the comparison with the model is a plausibility comparison, not a validation.

Rights: every file this stage writes is derived from product 4009 and ships under CC BY-SA 4.0 with the credit and a
change notice built from the rights record (``floodguard.rights_basis``). The stage refuses to run unless the owners
have confirmed that record. Its three files live in their own folder, ``unosat4009/``; no figure derived from the
product is returned for ``timeline.json`` or for the export pack.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import io
import json
from pathlib import Path
import warnings

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
import shapely
from shapely.geometry import shape

import floodguard.season_envelope as envelope_stats
from floodguard.rights_basis import PUBLIC_DERIVATIVE_FOLDER, require_owner_confirmation, verify_archive

LAYER = "CHIANGRAI_20240801_20241012_AccumulatedFlood"
"""The one layer of the archive this stage reads (the rights record's ``product.layer_in_scope``)."""
GEODATABASE = "FL20240912THA.gdb"
FOLDER = PUBLIC_DERIVATIVE_FOLDER
RASTER_NAME, DOCUMENT_NAME, LICENCE_NAME = "envelope.png", "envelope.json", "LICENSE"
FILE_NAMES: tuple[str, ...] = (RASTER_NAME, DOCUMENT_NAME, LICENCE_NAME)
DOCUMENT_SCHEMA = "floodguard.season_envelope.v1"
GENERATED_BY = "scripts/mae_sai_timeline_unosat4009.py"
SOURCE_CRS = "EPSG:4326"
SEASON_WINDOW = "2024-08-01/2024-10-22"
MAP_CREDIT_HOLDERS = "UNOSAT and GISTDA"
REPAIR_METHOD = "make_valid"
MIN_DIFFERENCE_KM2 = 0.5
"""A subdistrict is named among the largest differences only when the difference is at least this large."""

LABEL = "Scenario (SCN-ENV): 2024 season envelope"
CAPTION = ("UNOSAT and GISTDA product 4009: accumulated water, August to October 2024 (the layer name ends 12 Oct; the product is "
           "described to 22 Oct); includes August and early-October water; not an observation for any replay day. Clipped to Mae Sai "
           "district and rasterised to the replay grid by FloodGuard.")
STANDARD_SENTENCE = ("Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under "
                     "CC BY-SA 4.0. FloodGuard did not validate it.")
EVIDENCE_TIER = "Season envelope (scenario), used as provided; unvalidated"
COMPARISON_TITLE = "Season envelope comparison (scenario; plausibility, not validation)"
COMPARISON_USE = (f"{envelope_stats.COMPARISON_USE} The envelope also holds August and early-October water and the modelled peak is "
                  "illustrative, so the figures say where the two differ, not which one is right.")
COMPARISON_RULE = ("Both masks are counted on the replay's 10 m grid inside the eight Mae Sai subdistricts and outside mapped drainage "
                   "channels, the rule of every flooded area in the replay. agreement_iou is the overlap divided by the union; "
                   "containment_model_in_envelope is the share of the modelled water inside the envelope; containment_envelope_in_model "
                   "is the share of the envelope the modelled water reaches.")
TUNING_RULE = ("No keyframe or elevation change is tuned to product 4009 afterwards; if one is, this comparison is relabelled as "
               "calibration.")
TUNING_STATEMENT = "The comparison was computed after the stage keyframes were final and was not used for tuning."
DSM_ASSUMPTION = ("The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely "
                  "underestimated.")
LAND_COVER_REASON = ("Not computed: no land-cover map is among the replay's inputs, so the share of the envelope reached is not split "
                     "by built-up land and cropland.")
CONFIDENCE_REASON = ("A preliminary agency product that was not checked in the field, set beside an illustrative model: the envelope "
                     "spans August to October with no date per patch, and the modelled stages come from no gauge record.")
ASSUMPTIONS = [
    "The envelope is used as provided: a preliminary agency product that was not checked in the field (Field_Validation=0). FloodGuard did not validate it.",
    "The envelope holds water mapped at some time from August to October 2024, with no date per patch. It includes August and early-October water, so it is not the water of 9 to 19 September.",
    "The modelled peak is illustrative (no gauge record), so the comparison says where the two differ, not which one is right.",
    DSM_ASSUMPTION,
    "Both masks are counted on the replay's 10 m grid inside the eight Mae Sai subdistricts and outside mapped drainage channels, the rule of every flooded area in the replay.",
    "Residents are WorldPop 2020 modelled estimates, counted by two rules that the file names (100 m cells by their centre, and the replay's 10 m cells with mapped channels left out): not a census count and not the 2024 population.",
    "No land-cover map is among the replay's inputs, so the share of the envelope reached is not split by built-up land and cropland.",
    TUNING_STATEMENT,
]
LIMITATIONS = [
    "Not an observation for any replay day: the layer has no date per patch and no replay day selects it.",
    "The layer's name ends 12 October 2024, while the product is described to 22 October 2024.",
    "The third-party satellite imagery UNOSAT and GISTDA used to make the product is not relicensed by these files.",
    "UNOSAT and GISTDA do not endorse FloodGuard or its use of the product.",
    "Not an official warning and not legal advice; for preparedness learning and planning exercises only.",
]
LICENCE_TITLE = "Licence notice for the season-envelope files derived from UNOSAT product 4009"
LICENCE_LIMITS = [
    "The product is preliminary and was not checked in the field (Field_Validation=0). FloodGuard did not check it either.",
    "It shows water accumulated from August to October 2024. FloodGuard uses it only as a scenario envelope, never as an observation for a single day.",
    "The layer's name ends 20241012, while the product text runs to 22 October 2024.",
    "The third-party satellite imagery used to make the product is not relicensed by this notice.",
    "UNOSAT and GISTDA do not endorse FloodGuard or its use of the product.",
    "The statistics file sets the product beside a model: a plausibility comparison, not a validation.",
    "This notice is not legal advice and not an official warning.",
]
OTHER_INPUT_USE = {
    "copernicus-dem": {
        "en": ("The modelled water set beside the envelope: model_stage_m, model_km2, model_only_km2, the overlap, the union and the three "
               "ratios, the low-confidence areas and on_mapped_channels_km2. Model output on a terrain model (T1 scenario), not an observation."),
        "th": ("น้ำจากแบบจำลองที่นำมาเทียบกับขอบเขตนี้ ได้แก่ model_stage_m, model_km2, model_only_km2 พื้นที่ซ้อนทับ พื้นที่รวม อัตราส่วนทั้งสาม "
               "พื้นที่ความเชื่อมั่นต่ำ และ on_mapped_channels_km2 เป็นผลจากแบบจำลองบนแบบจำลองภูมิประเทศ (สถานการณ์จำลอง T1) ไม่ใช่การสังเกตการณ์"),
    },
    "worldpop": {
        "en": ("residents_in_envelope, residents_in_envelope_replay_rule and model_residents_in_water: modelled population estimates for "
               "2020, not a census count."),
        "th": ("residents_in_envelope, residents_in_envelope_replay_rule และ model_residents_in_water เป็นค่าประมาณประชากรจากแบบจำลองของปี 2563 (2020) "
               "ไม่ใช่ผลสำมะโนประชากร"),
    },
    "cod-ab": {
        "en": "The district clip, the subdistrict ids, tambon_km2 and share_of_tambon.",
        "th": "การตัดตามขอบเขตอำเภอ รหัสตำบล tambon_km2 และ share_of_tambon",
    },
}
"""What each input besides product 4009 gives ``envelope.json``, by the source id the bake uses, in English and Thai."""
OTHER_INPUTS_NOTE = ("envelope.json also holds figures that come from the open data below. Each keeps its own credit and licence: give these "
                     "credits as well when you reuse the file. The licence and the credit above cover what comes from product 4009. "
                     "This is a caution, not legal advice.")
CHANGE_NOTICE_THAI = ("FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย ({clip_geometry}) ซ่อมแซมรูปทรงเรขาคณิต ({repair_method} ซ่อมแซม {repair_count} ส่วน) "
                      "แปลงระบบพิกัดจาก {source_crs} เป็น {target_crs} และแปลงเป็นราสเตอร์ขนาดเซลล์ {cell_size_m} ม. แหล่งข้อมูล: ")
"""Thai rendering of the rights record's change-notice template, with the same placeholders; the credit and the licence follow it."""
COUNTED_SENTENCE = " The cells were then counted, and compared with the replay's modelled water, to make this table."
COUNTED_SENTENCE_THAI = " จากนั้นนับจำนวนเซลล์และเทียบกับน้ำจากแบบจำลองของการย้อนดู เพื่อจัดทำตารางนี้"
RESIDENTS_RULE = ("WorldPop 2020 cells (about 100 m) whose centre lies inside the clipped envelope, inside the eight subdistricts: the exposure "
                  "definition stated for the planning overlay. Modelled estimates, not a census count and not the 2024 population.")
RESIDENTS_REPLAY_RULE = ("Residents on envelope cells outside mapped channels, inside the eight subdistricts: the replay's exposure rule "
                         "(WorldPop 2020 spread evenly over 10 m cells), the rule of model_residents_in_water. Modelled estimates, not a "
                         "census count and not the 2024 population.")
RESIDENTS_RULES_NOTE = ("The two counts of residents inside the envelope differ because the rules differ (whole 100 m cells by their centre, "
                        "against 10 m cells with mapped channels left out). Set residents_in_envelope_replay_rule, not residents_in_envelope, "
                        "beside model_residents_in_water.")
LICENCE_THAI = {
    "title": "ประกาศสัญญาอนุญาตสำหรับไฟล์ขอบเขตน้ำตลอดฤดูที่ดัดแปลงจากผลิตภัณฑ์ UNOSAT หมายเลข 4009",
    "headings": {"files": "ไฟล์ที่ประกาศนี้ครอบคลุม", "source": "แหล่งข้อมูล", "credit": "การให้เครดิต", "licence": "สัญญาอนุญาต",
                 "share_alike": "การอนุญาตแบบเดียวกัน (ShareAlike)", "changes": "สิ่งที่ FloodGuard เปลี่ยนแปลง (ประกาศการเปลี่ยนแปลง)",
                 "other_inputs": "ข้อมูลนำเข้าอื่น (มีเครดิตและสัญญาอนุญาตของตนเอง)", "limits": "ข้อจำกัด"},
    "other_inputs_note": ("envelope.json มีตัวเลขที่มาจากข้อมูลเปิดด้านล่างนี้ด้วย ข้อมูลแต่ละชุดมีเครดิตและสัญญาอนุญาตของตนเอง เมื่อนำไฟล์ไปใช้ต่อ "
                          "โปรดให้เครดิตเหล่านี้ด้วย สัญญาอนุญาตและเครดิตข้างต้นครอบคลุมส่วนที่มาจากผลิตภัณฑ์หมายเลข 4009 ข้อความนี้เป็นข้อควรระวัง "
                          "ไม่ใช่คำแนะนำทางกฎหมาย"),
    "other_inputs_labels": {"licence": "สัญญาอนุญาต", "credit": "เครดิต", "used_for": "ใช้สำหรับ"},
    "other_inputs_used_for": {key: value["th"] for key, value in OTHER_INPUT_USE.items()},
    "share_alike": ("ท่านคัดลอก แบ่งปัน และดัดแปลงไฟล์เหล่านี้ได้ หากให้เครดิตตามข้างต้น ใส่ลิงก์ไปยังสัญญาอนุญาต ระบุสิ่งที่ท่านเปลี่ยนแปลง "
                    "และเผยแพร่ผลงานของท่านภายใต้สัญญาอนุญาตเดียวกัน คือ CC BY-SA 4.0"),
    "limits": [
        "ผลิตภัณฑ์นี้เป็นข้อมูลเบื้องต้นและยังไม่ได้ตรวจสอบในพื้นที่จริง (Field_Validation=0) FloodGuard ก็ไม่ได้ตรวจสอบเช่นกัน",
        "ข้อมูลแสดงน้ำสะสมตั้งแต่เดือนสิงหาคมถึงตุลาคม 2567 (2024) FloodGuard ใช้เป็นกรอบสถานการณ์สมมติเท่านั้น ไม่ใช้เป็นข้อมูลสังเกตการณ์ของวันใดวันหนึ่ง",
        "ชื่อชั้นข้อมูลลงท้ายด้วย 20241012 แต่คำอธิบายผลิตภัณฑ์ครอบคลุมถึงวันที่ 22 ตุลาคม 2567 (2024)",
        "ประกาศนี้ไม่ได้ให้สิทธิ์ใหม่ในภาพถ่ายดาวเทียมของบุคคลที่สามที่ใช้จัดทำผลิตภัณฑ์",
        "UNOSAT และ GISTDA ไม่ได้รับรอง FloodGuard หรือการใช้ผลิตภัณฑ์นี้ของ FloodGuard",
        "ไฟล์สถิติเทียบผลิตภัณฑ์กับแบบจำลองเพื่อดูความสมเหตุสมผล ไม่ใช่การยืนยันความถูกต้องของแบบจำลอง",
        "ประกาศนี้ไม่ใช่คำแนะนำทางกฎหมาย และไม่ใช่การเตือนภัยอย่างเป็นทางการ",
    ],
}
"""Thai half of the ``LICENSE`` file: headings, the ShareAlike sentence and the limits. Years carry the CE year."""

Track = Callable[[Path], Path]


class SeasonEnvelopeStageError(ValueError):
    """Raised when the archive, its layer or the rights record does not allow the stage to run."""


def map_credit(licence_name: str) -> str:
    """Short credit the map and the exports add while the layer is visible: the holders and the licence."""
    return f"{MAP_CREDIT_HOLDERS} · {licence_name}"


def _polygons(geometry) -> np.ndarray:
    """The polygon parts of any geometry (a repaired part can come back as a collection with stray lines)."""
    parts = shapely.get_parts(shapely.get_parts(geometry))
    return parts[shapely.get_type_id(parts) == 3]


def read_layer(archive: Path, expected: Mapping[str, object]):
    """Read the accumulated-water layer of the archive and check the attributes the rights record names.

    Only :data:`LAYER` is read, through GDAL's ``/vsizip/``; nothing else in the archive is opened. Returns the
    layer's one geometry (lon/lat). Raises when the layer does not hold exactly one feature or when
    ``Field_Validation``, ``Sensor_Date`` or ``EventCode`` differ from ``expected``.
    """
    import pyogrio

    with warnings.catch_warnings():
        # GDAL reports the layer's unclosed and self-intersecting rings as it reads them; district_clip repairs and counts them.
        warnings.simplefilter("ignore", RuntimeWarning)
        frame = pyogrio.read_dataframe(f"/vsizip/{archive.as_posix()}/{GEODATABASE}", layer=LAYER)
    if len(frame) != 1:
        raise SeasonEnvelopeStageError(f"{LAYER} must hold one dissolved feature; found {len(frame)}")
    row = frame.iloc[0]
    found = {"Field_Validation": int(row["Field_Validation"]), "Sensor_Date": str(row["Sensor_Date"])[:10], "EventCode": str(row["EventCode"])}
    differing = {key: (found.get(key), value) for key, value in expected.items() if found.get(key) != value}
    if differing:
        raise SeasonEnvelopeStageError(f"{LAYER} attributes differ from the rights record: {differing}")
    return frame.geometry.iloc[0]


def district_clip(geometry, tambons: Sequence) -> tuple[object, dict]:
    """Repair the layer's invalid polygon parts and clip it to the union of ``tambons`` (all in lon/lat).

    Only the parts whose bounding box meets the district are repaired and clipped; the count of repaired parts is
    the number of those that were invalid. Returns the clip (polygons only) and what was done.
    """
    parts = _polygons(geometry)
    district = shapely.union_all(shapely.make_valid(np.array(list(tambons), dtype=object)))
    west, south, east, north = district.bounds
    box = shapely.bounds(parts)
    near = (box[:, 0] <= east) & (box[:, 2] >= west) & (box[:, 1] <= north) & (box[:, 3] >= south)
    invalid = ~shapely.is_valid(parts)
    repaired = _polygons(shapely.make_valid(parts[near]))
    clip = shapely.union_all(_polygons(shapely.intersection(shapely.union_all(repaired), district)))
    return clip, {
        "method": REPAIR_METHOD,
        "source_parts": int(len(parts)),
        "source_parts_invalid": int(invalid.sum()),
        "parts_meeting_district": int(near.sum()),
        "parts_repaired": int((invalid & near).sum()),
        "note": ("Only the polygon parts whose bounding box meets Mae Sai district are repaired and clipped; parts_repaired counts "
                 "the invalid ones among them."),
    }


def reproject(geometry, target_crs: str):
    """``geometry`` (lon/lat) in ``target_crs``."""
    transformer = Transformer.from_crs(SOURCE_CRS, target_crs, always_xy=True)
    return shapely.transform(geometry, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))


def rasterise(geometry, transform, shape_: tuple[int, int]) -> np.ndarray:
    """Boolean mask of ``geometry`` on a north-up grid: a cell is inside when its centre is."""
    if geometry.is_empty:
        return np.zeros(shape_, dtype=bool)
    return rasterize([(geometry, 1)], out_shape=shape_, transform=transform, fill=0, all_touched=False, dtype="uint8").astype(bool)


def bitmask_png(mask: np.ndarray) -> bytes:
    """A 1-bit greyscale PNG of ``mask`` (1 = inside the envelope)."""
    buffer = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(mask, dtype=bool)).save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def cell_centre_residents(population: Path, clip) -> int:
    """Residents of the population cells whose centre lies inside ``clip``, on the population raster's own grid.

    ``population`` is a population raster (for the replay, WorldPop 2020 at about 100 m, in lon/lat); ``clip`` is
    the clipped envelope in lon/lat, already cut to the district. This is the exposure definition stated for the
    planning overlay: a whole cell counts when its centre is inside, and nothing is spread over finer cells.
    Cells without data count as no residents.
    """
    if clip.is_empty:
        return 0
    with rasterio.open(population) as src:
        geometry = clip if src.crs is None or src.crs.to_string() == SOURCE_CRS else reproject(clip, src.crs.to_string())
        window = from_bounds(*geometry.bounds, transform=src.transform).round_offsets(op="floor").round_lengths(op="ceil")
        window = Window(window.col_off - 2, window.row_off - 2, window.width + 4, window.height + 4)
        cells = src.read(1, window=window, boundless=True, fill_value=0).astype(np.float64)
        missing = ~np.isfinite(cells) | (cells < 0)
        if src.nodata is not None:
            missing |= cells == src.nodata
        transform = src.window_transform(window)
    cells = np.where(missing, 0.0, cells)
    return envelope_stats.residents_inside(rasterise(geometry, transform, cells.shape), cells)


def model_residents(stage: Mapping, counted: int) -> int:
    """The replay's own figure of residents in water at ``stage`` when it gives one, else the count on the mask.

    The replay sums its residents per subdistrict to one decimal before rounding, so its figure can differ from the
    mask count by a person; a larger difference means the two are not the same water and stops the bake.
    """
    stated = stage.get("model_residents_in_water")
    if stated is None:
        return counted
    if abs(int(stated) - counted) > 2:
        raise SeasonEnvelopeStageError(f"the replay states {stated} residents in water at {stage['id']}, but the mask holds {counted}")
    return int(stated)


def season_envelope(external: Path, rights: Mapping, admin_features: Sequence[Mapping], *, statistics_grid, raster_grid, codes: np.ndarray,
                    zones: np.ndarray, tambon_ids: Sequence[str], low_confidence: np.ndarray, residents: np.ndarray, population: Path,
                    channel_code: int, never_code: int, hand_step_m: float, stages: Sequence[Mapping], clip_source: str,
                    track: Track = lambda path: path) -> dict:
    """Read, clip and rasterise the season envelope and compare the modelled water with it.

    ``statistics_grid`` is the replay's 10 m UTM grid (``codes``, ``zones``, ``low_confidence`` and ``residents`` are
    on it); ``raster_grid`` is the replay's water display grid, on which the published 1-bit raster is drawn.
    ``population`` is the population raster ``residents`` was made from, already recorded as an input by the caller:
    the residents inside the envelope are counted twice, on its own cells by their centre (the planning overlay's
    stated exposure definition) and on the 10 m grid outside mapped channels (the replay's rule).
    ``stages`` lists the modelled extents to compare, each ``{"id", "model_stage_m", "model_extent"}``; the first is
    the one the per-subdistrict rows, the low-confidence split and the residents use, and it may carry the replay's
    own ``model_residents_in_water`` so the two files state one figure. ``clip_source`` names the
    boundary data the clip uses. ``track`` is called with the archive before it is opened.

    Returns the raster bytes and the figures of the comparison. Nothing is written: :func:`write_files` does that
    once the bake knows its generation time. Raises :class:`floodguard.rights_basis.RightsNotConfirmedError` unless
    the owners have confirmed ``rights``, before any file is opened.
    """
    require_owner_confirmation(rights)
    product = rights["product"]
    if product.get("layer_in_scope") != LAYER:
        raise SeasonEnvelopeStageError(f"the rights record covers {product.get('layer_in_scope')}, not {LAYER}")
    track(Path(external) / rights["archive"]["relative_path"])
    archive = verify_archive(rights, external)  # The file on disk is the one the record names: same size, same SHA-256.
    geometry = read_layer(archive, product["layer_attributes_checked"])
    tambons = [shape(feature["geometry"]) for feature in admin_features]
    clip, repair = district_clip(geometry, tambons)

    cell_km2 = statistics_grid.res ** 2 / 1e6
    envelope = rasterise(reproject(clip, statistics_grid.crs), statistics_grid.transform, statistics_grid.shape)
    district = zones > 0
    channel = codes == channel_code
    out_of_channel = envelope & ~channel
    values = codes.astype(int)
    rows = []
    for stage in stages:
        wet = ~channel & (values != never_code) & (values * hand_step_m < stage["model_stage_m"])
        rows.append({"id": stage["id"], "model_stage_m": round(float(stage["model_stage_m"]), 3), "model_extent": stage["model_extent"],
                     **envelope_stats.mask_agreement(wet, out_of_channel, cell_km2, district)})
    peak = stages[0]
    peak_wet = ~channel & (values != never_code) & (values * hand_step_m < peak["model_stage_m"])
    by_tambon = [{"tambon_id": row.pop("zone_id"), **row}
                 for row in envelope_stats.zone_agreement(peak_wet, out_of_channel, zones, tambon_ids, cell_km2)]
    ranked = [{"zone_id": row["tambon_id"], **row} for row in by_tambon]
    envelope_by_tambon = envelope_stats.zone_areas(envelope, zones, tambon_ids, cell_km2)
    tambon_km2 = envelope_stats.zone_areas(district, zones, tambon_ids, cell_km2)
    vector_km2 = reproject(clip, statistics_grid.crs).area / 1e6
    return {
        "raster_png": bitmask_png(rasterise(reproject(clip, raster_grid.crs), raster_grid.transform, raster_grid.shape)),
        "raster": {"width": raster_grid.width, "height": raster_grid.height, "crs": raster_grid.crs},
        "repair": repair,
        "clip_geometry": clip_source,
        "statistics_crs": statistics_grid.crs,
        "statistics_cell_m": statistics_grid.res,
        "area": {
            "grid": "Counted on the replay's 10 m grid, a cell counting when its centre is inside the clipped layer.",
            "district_km2": round(float(np.count_nonzero(envelope & district)) * cell_km2, 2),
            "district_vector_km2": round(float(vector_km2), 2),
            "on_mapped_channels_km2": round(float(np.count_nonzero(envelope & district & channel)) * cell_km2, 2),
            "by_tambon": {tid: {"envelope_km2": envelope_by_tambon[tid], "tambon_km2": round(tambon_km2[tid], 2),
                                "share_of_tambon": round(envelope_by_tambon[tid] / tambon_km2[tid], 3) if tambon_km2[tid] else None}
                          for tid in tambon_ids},
        },
        "district": rows,
        "by_tambon": by_tambon,
        "by_tambon_stage": peak["id"],
        "disagreement": {
            "minimum_km2": MIN_DIFFERENCE_KM2,
            "envelope_water_the_model_lacks": envelope_stats.largest_differences(ranked, "envelope_only_km2", MIN_DIFFERENCE_KM2),
            "modelled_water_outside_the_envelope": envelope_stats.largest_differences(ranked, "model_only_km2", MIN_DIFFERENCE_KM2),
        },
        "low_confidence": {
            "model_stage": peak["id"],
            "low_confidence_model_km2": round(float(np.count_nonzero(peak_wet & low_confidence & district)) * cell_km2, 2),
            "other_model_km2": round(float(np.count_nonzero(peak_wet & ~low_confidence & district)) * cell_km2, 2),
            "share_inside_envelope_low_confidence": envelope_stats.share_inside(peak_wet & low_confidence, out_of_channel, district),
            "share_inside_envelope_other": envelope_stats.share_inside(peak_wet & ~low_confidence, out_of_channel, district),
        },
        "residents": {
            "residents_in_envelope": cell_centre_residents(population, clip),
            "residents_in_envelope_replay_rule": envelope_stats.residents_inside(out_of_channel, residents, district),
            "model_residents_in_water": model_residents(peak, envelope_stats.residents_inside(peak_wet, residents, district)),
            "model_stage": peak["id"],
        },
    }


def other_inputs(sources: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """The inputs besides product 4009 whose figures ``envelope.json`` holds, with their licences and credits.

    ``sources`` are the bake's own source lines (``id``, ``name``, ``licence``, ``attribution``, ``timestamp``); the
    stage keeps those it names in :data:`OTHER_INPUT_USE` and says what each was used for. A source the stage needs
    and the bake does not list stops the bake: the file would ship without that credit.
    """
    by_id = {str(source.get("id")): source for source in sources}
    absent = [key for key in OTHER_INPUT_USE if key not in by_id]
    if absent:
        raise SeasonEnvelopeStageError(f"the bake lists no source line for: {absent}")
    return [{"id": key, **{name: str(by_id[key][name]) for name in ("name", "licence", "attribution", "timestamp")}, "used_for": use["en"]}
            for key, use in OTHER_INPUT_USE.items()]


def write_files(data: Mapping, out_dir: Path, *, rights: Mapping, rights_record: Mapping[str, str], study_id: str, revision: str,
                generated_at: str, href_prefix: str, bounds: Sequence[Sequence[float]], raster_cell_m: float,
                worldpop_source: str, sources: Sequence[Mapping[str, str]], clip_geometry_thai: str) -> dict[str, dict]:
    """Write ``envelope.png``, ``envelope.json`` and ``LICENSE`` into ``out_dir/unosat4009`` and return their references.

    ``data`` is the result of :func:`season_envelope`; ``rights_record`` gives the record's repository path and
    SHA-256. ``sources`` are the bake's source lines, from which the other inputs of ``envelope.json`` (terrain
    model, population grid, boundaries) take their licences and credits; ``clip_geometry_thai`` names the clip
    geometry in Thai for the Thai change notice. Each reference holds ``href``, ``sha256`` and ``bytes`` only: that
    is all ``timeline.json`` says about the files. A document that breaks its own rules
    (``floodguard.season_envelope.document_problems``) is not written.
    """
    require_owner_confirmation(rights)
    licence = {key: rights["licence"][key] for key in ("name", "full_name", "spdx_id", "url", "legal_code_url")}
    credit = rights["required_attribution_text"]
    template = rights["change_notice"]["template"]
    clip_geometry = data["clip_geometry"]
    inputs = other_inputs(sources)
    repair_count = data["repair"]["parts_repaired"]
    cell_sizes = {RASTER_NAME: (data["raster"]["crs"], f"about {raster_cell_m:.0f}", f"ประมาณ {raster_cell_m:.0f}"),
                  DOCUMENT_NAME: (data["statistics_crs"], f"{data['statistics_cell_m']:g}", f"{data['statistics_cell_m']:g}")}
    notices = {name: envelope_stats.fill_change_notice(
        template, clip_geometry=clip_geometry, repair_method=REPAIR_METHOD, repair_count=repair_count, source_crs=SOURCE_CRS,
        target_crs=crs, cell_size_m=english) for name, (crs, english, _) in cell_sizes.items()}
    notices[DOCUMENT_NAME] += COUNTED_SENTENCE
    # The same notices in Thai, for the Thai half of the licence file; the credit and the licence name stay as published.
    thai_notices = {name: envelope_stats.fill_change_notice(
        CHANGE_NOTICE_THAI, clip_geometry=clip_geometry_thai, repair_method=REPAIR_METHOD, repair_count=repair_count, source_crs=SOURCE_CRS,
        target_crs=crs, cell_size_m=thai) + f"{credit}, {licence['name']}" for name, (crs, _, thai) in cell_sizes.items()}
    thai_notices[DOCUMENT_NAME] += COUNTED_SENTENCE_THAI
    raster = data["raster_png"]
    folder = Path(out_dir) / FOLDER
    prefix = f"{href_prefix}{FOLDER}/"
    document = {
        "schema": DOCUMENT_SCHEMA,
        "id": "unosat-4009",
        "study_id": study_id,
        "revision": revision,
        "generated_by": GENERATED_BY,
        "generated_at": generated_at,
        "lane": envelope_stats.ENVELOPE_LANE,
        "evidence_tier": EVIDENCE_TIER,
        "temporal_relation": "season_envelope",
        "season_window": SEASON_WINDOW,
        "source_timestamp": rights["source_timestamp"],
        "not_an_observation_for_any_replay_day": True,
        "label": LABEL,
        "caption": CAPTION,
        "standard_sentence": STANDARD_SENTENCE,
        "source": {
            "name": rights["source"],
            "product_url": rights["product"]["product_url"],
            "dataset_url": rights["hdx"]["dataset_url"],
            "event_code": rights["product"]["event_code"],
            "layer": LAYER,
            "layer_name_ends": "2024-10-12",
            "product_described_to": "2024-10-22",
            "field_validation": rights["product"]["layer_attributes_checked"]["Field_Validation"],
            "archive": {key: rights["archive"][key] for key in ("file_name", "sha256", "bytes")},
        },
        "licence": licence,
        "credit": credit,
        "map_credit": map_credit(licence["name"]),
        "share_alike": rights["share_alike"],
        "other_inputs_note": OTHER_INPUTS_NOTE,
        "other_inputs": inputs,
        "rights_record": dict(rights_record),
        "change_notice": notices[RASTER_NAME],
        "changes": {"clip_geometry": clip_geometry, "repair": data["repair"], "source_crs": SOURCE_CRS,
                    "raster_crs": data["raster"]["crs"], "statistics_crs": data["statistics_crs"]},
        "raster": {
            "file": RASTER_NAME, "sha256": hashlib.sha256(raster).hexdigest(), "bytes": len(raster),
            "width": data["raster"]["width"], "height": data["raster"]["height"], "bit_depth": 1,
            "encoding": "1 = inside the season envelope, 0 = outside; a cell is inside when its centre is",
            "crs": data["raster"]["crs"], "bounds": [list(corner) for corner in bounds], "cell_size_m": round(raster_cell_m, 2),
            "grid": "The replay's water grid (same size and bounds as the modelled water raster).",
        },
        "area": data["area"],
        "comparison": {
            "role": envelope_stats.COMPARISON_ROLE,
            "title": COMPARISON_TITLE,
            "use": COMPARISON_USE,
            "scope": "The eight Mae Sai subdistricts.",
            "rule": COMPARISON_RULE,
            "change_notice": notices[DOCUMENT_NAME],
            "model_fields": {
                "evidence_tier": "T1 scenario (model)",
                "note": ("model_stage_m, model_km2, model_only_km2, model_residents_in_water and the low-confidence areas are model output "
                         "on the reconstructed water; envelope_km2, envelope_only_km2 and the two counts of residents in the envelope come "
                         "from the season envelope; the overlap and the three ratios use both."),
            },
            "district": data["district"],
            "by_tambon_stage": data["by_tambon_stage"],
            "by_tambon": data["by_tambon"],
            "disagreement": data["disagreement"],
            "low_confidence": data["low_confidence"],
            "land_cover": {"computed": False, "reason": LAND_COVER_REASON},
            "residents": {**data["residents"], "source": worldpop_source, "scope": "District total only.",
                          "rule": RESIDENTS_RULE, "replay_rule": RESIDENTS_REPLAY_RULE, "rules_note": RESIDENTS_RULES_NOTE},
            "tuning": {"relation": "computed_after_keyframes_final", "statement": TUNING_STATEMENT, "rule": TUNING_RULE},
        },
        "confidence": "low",
        "confidence_reason": CONFIDENCE_REASON,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "not_legal_advice": True,
    }
    problems = envelope_stats.document_problems(document, licence_name=licence["name"], credit=credit)
    if licence["name"] != "CC BY-SA 4.0":
        problems.append("derived product 4009 files ship under CC BY-SA 4.0")
    if problems:
        raise SeasonEnvelopeStageError("the season-envelope document cannot be published:\n  " + "\n  ".join(problems))
    document_bytes = (json.dumps(document, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    archive = rights["archive"]
    licence_bytes = envelope_stats.licence_notice(
        title=LICENCE_TITLE, files=FILE_NAMES, licence=licence, credit=credit,
        change_notices={RASTER_NAME: notices[RASTER_NAME], DOCUMENT_NAME: notices[DOCUMENT_NAME]},
        source_lines=[rights["source"], f"Layer read: {LAYER}", rights["product"]["product_url"], rights["hdx"]["dataset_url"],
                      f"Archive: {archive['file_name']}, {archive['bytes']:,} bytes", f"SHA-256: {archive['sha256']}",
                      f"Rights record: {rights_record['path']}"],
        limits=LICENCE_LIMITS, other_inputs=inputs, other_inputs_note=OTHER_INPUTS_NOTE,
        thai={**LICENCE_THAI, "change_notices": thai_notices, "source_lines": [
            "ขอบเขตน้ำของ UNOSAT และ GISTDA ระหว่างวันที่ 1 สิงหาคม ถึง 22 ตุลาคม 2567 (2024) จังหวัดเชียงราย ประเทศไทย "
            f"(ผลิตภัณฑ์ UNOSAT หมายเลข 4009 รหัสเหตุการณ์ {rights['product']['event_code']})",
            f"ชั้นข้อมูลที่อ่าน: {LAYER}", rights["product"]["product_url"], rights["hdx"]["dataset_url"],
            f"ไฟล์: {archive['file_name']} ขนาด {archive['bytes']:,} ไบต์", f"SHA-256: {archive['sha256']}",
            f"บันทึกสิทธิ์: {rights_record['path']}"]}).encode("utf-8")
    folder.mkdir(parents=True, exist_ok=True)
    references = {}
    for key, name, payload in (("raster", RASTER_NAME, raster), ("statistics", DOCUMENT_NAME, document_bytes), ("licence", LICENCE_NAME, licence_bytes)):
        (folder / name).write_bytes(payload)
        references[key] = {"href": prefix + name, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    return references
