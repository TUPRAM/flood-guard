"""The Nan case, test 1 of record under amendment 2: the frozen M1-z against JAXA's ALOS-2 map of 2025-07-28.

Amendment 2 of the protocol (``docs/proposal_execution/nan_case_protocol_v1_amendment_2.json``, decision log R53)
found that the first run of the test stage read JAXA's observation-area layer (``..._REGION.geojson``) as a flood
layer, judged the JAXA files unusable and took the GFM fallback. It names the comparison the protocol meant as test 1
of record and says how it is run: once, by this script, which imports the frozen functions of
``scripts/nan_case_method.py`` and ``src/floodguard/m1z.py`` unchanged. The only new logic is the reading of the two
JAXA layers:

* the sealed zip ``JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip`` is read into memory, never extracted or changed,
  and its SHA-256 is checked against the protocol's ``sealed_references`` before it is read and after the scoring;
* the layer whose name ends with ``_FLDEXT.geojson`` is JAXA's water, the layer ending with ``_REGION.geojson`` its
  observation area; the run refuses when either is missing or when REGION covers less than half of the frame's land
  outside permanent water;
* the compared cells are the frame's land (cell centre inside the 35 units, outside ESA WorldCover class 80) whose
  centre lies inside REGION; JAXA's water is put on the grid by cell centre.

Everything else is the frozen code: the pass (the Sentinel-1C pass of 2025-07-28 about 11:20 UTC, because JAXA's files
give no time with a zone), the 0.79 dB offset of amendment 1 on that pass, M1-z at its three flood levels, the
comparators of the frozen code on the same pass and cells, GFM of the same pass as an external comparator where GFM
holds it, the measures of test 1 (by WorldCover group, a 95% interval from 2 km tiles, the reasons), the pass rule
and the case N2 reference. The JAXA map of 2025-07-19 is set against the pass nearest to 2025-07-19 12:00 Thai time,
report only. The binding block takes the dry control from the first run (``outputs/nan_case/test_result_v1.json``),
which amendment 2 keeps as written.

Outputs: ``outputs/nan_case/test_1_jaxa_v1.json`` (figures only, with the SHA-256 of every record, code file and
input it reads); the case N2 reference raster ``method/case_n2_reference/reference_test_1_jaxa_20250728.tif`` in the
work folder (JAXA's FLDEXT by cell centre inside REGION as 1 or 0, 255 outside REGION); and the frozen map of the
2025-07-28 pass in ``method/maps/`` in the format of the maps stage, written only when the maps stage has not written
it; otherwise the map on disk is read and must hold the same values. No raster or geometry of JAXA enters Git
(Sentinel Asia terms: no modification of the materials; credit "Provided by JAXA").

The run refuses unless the freeze record is committed, unchanged and pushed with the code it binds, the first test
record exists unchanged in HEAD, amendment 2 is committed and pushed, and this script is committed and pushed. It
runs once: an existing record is replaced only with ``--replace`` and ``--reason``.

Example (from the repository root)::

    python scripts/nan_case_test1_jaxa.py --external-root <external data root>

Every figure is agreement with a reference layer (another satellite's map), not a ground check. Planning guidance
only; not an official warning.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
import hashlib
import importlib.util
import io
from pathlib import Path, PurePosixPath
import re
import sys
import time
from typing import Any
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import m1z  # noqa: E402


def _load_method() -> Any:
    """The frozen ``scripts/nan_case_method.py`` as a module, loaded by path and run unchanged."""

    name = "nan_case_method"
    loaded = sys.modules.get(name)
    if loaded is not None and Path(getattr(loaded, "__file__", "")).resolve() == (ROOT / "scripts" / "nan_case_method.py").resolve():
        return loaded
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "nan_case_method.py")
    if spec is None or spec.loader is None:
        raise ImportError("scripts/nan_case_method.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


method = _load_method()
StageError = method.StageError

SCRIPT = "scripts/nan_case_test1_jaxa.py"
OUTPUT = "outputs/nan_case/test_1_jaxa_v1.json"
SCHEMA = "floodguard.nan_case_test_1_jaxa.v1"
AMENDMENT_2 = "docs/proposal_execution/nan_case_protocol_v1_amendment_2.json"
JAXA_MAIN = "JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip"
JAXA_SECOND = "JAXA_20250719_FPM_ALOS2_Thailand_geojson.zip"
FLOOD_SUFFIX = "_FLDEXT.geojson"
REGION_SUFFIX = "_REGION.geojson"
TEXT_MEMBERS = (".txt", ".xml", ".csv", ".htm", ".html", ".prj", ".md")
CASE_REFERENCE_DATE = "2025-07-28"
TEST_1_PLATFORM = "sentinel-1c"
TEST_1B_TARGET_UTC = "2025-07-19T05:00:00Z"
"""12:00 Thai time on 2025-07-19: the pass nearest to it is the pass of test 1b (report only)."""
CASE_N2_NAME = "reference_test_1_jaxa_20250728"
COMPARATOR_MODULES: tuple[str, ...] = ("radar_candidates", "sar_change_v2", "geoid_m1_review", "radar_detection", "radar_flood_classifier")
"""Modules the comparators of the frozen code call; the freeze does not bind them, the record names their SHA-256."""
MAP_BANDS = {"code_lower": 1, "code_central": 2, "code_upper": 3, "reason_central": 4}
LEVEL_OF_BAND = {"code_lower": ("lower", 0), "code_central": ("central", 0), "code_upper": ("upper", 0), "reason_central": ("central", 1)}

ASSUMPTIONS = [
    *method.ASSUMPTIONS_METHOD,
    "Test 1 of record (amendment 2): JAXA's layer whose name ends with _FLDEXT.geojson is the water and the layer ending "
    "with _REGION.geojson the observation area; both are put on the 20 m grid by cell centre.",
    "Compared cells: frame land (cell centre inside the 35 units, outside WorldCover class 80) whose centre lies inside REGION.",
    "The pass is the Sentinel-1C pass of 2025-07-28 about 11:20 UTC, because JAXA's files give no time with a zone "
    "(amendment 2); its VV and VH are raised by 0.79 dB before M1-z and the comparators run (amendment 1).",
    "The JAXA zips are read in memory and never extracted; their SHA-256 is checked against the protocol before the "
    "reading and after the scoring.",
    "The dry control of the binding rule is that of the first run (outputs/nan_case/test_result_v1.json); it does not "
    "depend on the test 1 reference.",
    "The 95% intervals come from 1000 draws of 2 km tiles (100 by 100 cells from the frame's north-west corner) with the seed recorded.",
]
LIMITS = [
    "C-band radar does not see water under trees, between buildings or under rice canopy, nor water that drained before the pass.",
    "JAXA's map is another satellite's automatic analysis (ALOS-2, L-band), not a ground check; its files give no "
    "acquisition time with a zone, so the hours between it and our pass are not known.",
    "Every figure is agreement with a reference layer. Planning guidance only; not an official warning.",
]
MEASURES_NAMED = {
    "iou_no_answer_as_not_flagged": "IoU with no-answer cells counted as not flagged (the binding figure)",
    "iou_answered_cells": "IoU on the answered cells",
    "flagged_that_is_reference_water": "the share of our flagged cells that lie on JAXA water",
    "reference_water_flagged_no_answer_as_not_flagged": "the share of JAXA water our map flags (no answer counted as not flagged)",
    "reference_water_flagged_answered_cells": "the share of JAXA water our map flags, on answered cells",
    "no_answer_share": "the share of compared cells without an answer",
}


class JaxaLayerError(StageError):
    """A JAXA zip lacks one of its two layers, holds one twice, or a layer holds no polygon."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of bytes held in memory."""

    return hashlib.sha256(data).hexdigest()


def file_entry(root: Path, relative: str) -> dict[str, str]:
    """A record of the repository by its path and SHA-256."""

    return {"path": relative, "sha256": method.sha256_file(root / relative)}


def module_hashes() -> dict[str, str | None]:
    """SHA-256 of the modules the comparators call (``None`` for one that is not in the tree)."""

    out: dict[str, str | None] = {}
    for name in COMPARATOR_MODULES:
        path = ROOT / "src" / "floodguard" / f"{name}.py"
        out[f"src/floodguard/{name}.py"] = method.sha256_file(path) if path.is_file() else None
    return out


# ---------------------------------------------------------------------------
# The two JAXA layers (the only new logic of test 1 of record)
# ---------------------------------------------------------------------------


def read_sealed(path: Path, expected_sha256: str) -> bytes:
    """The bytes of a sealed zip, read into memory, after checking their SHA-256 against the protocol's seal.

    Raises:
        StageError: when the file is missing or its bytes are not the ones the protocol sealed.
    """

    if not Path(path).is_file():
        raise StageError(f"{Path(path).name} is not in the sealed folder")
    data = Path(path).read_bytes()
    if sha256_bytes(data) != expected_sha256:
        raise StageError(f"{Path(path).name} is not the file the protocol sealed")
    return data


def verify_seal(path: Path, expected_sha256: str) -> str:
    """Check, after the scoring, that a sealed zip still holds the bytes the protocol sealed; returns the SHA-256.

    Raises:
        StageError: when the file is missing or changed.
    """

    if not Path(path).is_file():
        raise StageError(f"{Path(path).name} left the sealed folder during the run")
    digest = method.sha256_file(path)
    if digest != expected_sha256:
        raise StageError(f"{Path(path).name} changed during the run: it is no longer the file the protocol sealed")
    return digest


def read_layer(raw: bytes) -> tuple[Any, dict[str, Any]]:
    """A GeoJSON layer held in memory: its polygons in EPSG:32647 and a description (no geometry).

    A layer without a coordinate system is read as EPSG:4326, as GeoJSON is.
    """

    import pyogrio

    frame = pyogrio.read_dataframe(io.BytesIO(raw))
    crs_given = frame.crs is not None
    if not crs_given:
        frame = frame.set_crs(4326)
    polygons = frame[frame.geometry.notna() & frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    about = {"features": int(len(frame)), "polygon_features": int(len(polygons)),
             "geometry_types": sorted({str(item) for item in frame.geometry.geom_type.dropna().unique()}),
             "crs": str(frame.crs) if crs_given else "none given: read as EPSG:4326",
             "fields": [str(column) for column in frame.columns if column != frame.geometry.name]}
    return polygons.to_crs(method.EPSG), about


def layer_member(members: Sequence[zipfile.ZipInfo], suffix: str, file_name: str) -> zipfile.ZipInfo:
    """The one member whose file name ends with ``suffix`` (case is not read).

    Raises:
        JaxaLayerError: when no member or more than one ends so.
    """

    found = [info for info in members if PurePosixPath(info.filename).name.lower().endswith(suffix.lower())]
    if not found:
        raise JaxaLayerError(f"{file_name} holds no layer whose name ends with {suffix}")
    if len(found) > 1:
        raise JaxaLayerError(f"{file_name} holds more than one layer whose name ends with {suffix}: {[info.filename for info in found]}")
    return found[0]


def jaxa_layers(data: bytes, file_name: str) -> dict[str, Any]:
    """Read the flood layer (``*_FLDEXT.geojson``) and the observation area (``*_REGION.geojson``) of a JAXA zip in memory.

    Returns ``{"record", "flood", "region", "times"}``: a description of the zip and its two layers (names, sizes,
    member SHA-256, feature counts; no geometry), the polygons of each layer in EPSG:32647, and the times with an
    explicit zone found in the two layers and in the text members (the frozen ``zoned_times``).

    Raises:
        JaxaLayerError: when either layer is missing or held twice, or REGION holds no polygon.
    """

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        flood_info = layer_member(members, FLOOD_SUFFIX, file_name)
        region_info = layer_member(members, REGION_SUFFIX, file_name)
        texts = {info.filename: archive.read(info) for info in members if info.filename.lower().endswith(TEXT_MEMBERS)}
        flood_raw, region_raw = archive.read(flood_info), archive.read(region_info)
        listed = [{"member": info.filename, "bytes": int(info.file_size)} for info in members]
    flood, flood_about = read_layer(flood_raw)
    region, region_about = read_layer(region_raw)
    if not len(region):
        raise JaxaLayerError(f"{file_name}: the layer {region_info.filename} holds no polygon, so it says nothing of where ALOS-2 looked")
    times: list[datetime] = []
    for raw in (flood_raw, region_raw, *texts.values()):
        times.extend(method.zoned_times(raw.decode("utf-8", errors="ignore")))
    used = {flood_info.filename, region_info.filename}
    record = {
        "file": file_name,
        "read": "in memory from the sealed zip; nothing extracted or changed",
        "members": listed,
        "flood_layer": {"member": flood_info.filename, "sha256": sha256_bytes(flood_raw), **flood_about},
        "observation_area_layer": {"member": region_info.filename, "sha256": sha256_bytes(region_raw), **region_about},
        "members_not_used": [entry["member"] for entry in listed if entry["member"] not in used],
        "times_with_a_zone_utc": sorted({item.strftime("%Y-%m-%dT%H:%M:%SZ") for item in times}),
    }
    return {"record": record, "flood": flood, "region": region, "times": sorted(set(times))}


def compared_cells(frame_land: np.ndarray, region: np.ndarray) -> np.ndarray:
    """The compared cells of test 1: frame land (units outside permanent water) whose centre lies inside REGION."""

    land, inside = np.asarray(frame_land, dtype=bool), np.asarray(region, dtype=bool)
    if land.shape != inside.shape:
        raise StageError("the frame land and the observation area must share one grid")
    return land & inside


def region_cover(region: np.ndarray, frame_land: np.ndarray) -> float:
    """The share of the frame's land (outside permanent water) whose cell centre lies inside REGION."""

    land = np.asarray(frame_land, dtype=bool)
    if not land.any():
        return 0.0
    return float((np.asarray(region, dtype=bool) & land).sum()) / float(land.sum())


def require_cover(share: float, file_name: str, minimum: float | None = None) -> None:
    """Refuse an observation area that covers less than half of the frame's land (protocol test 1, ``usable_if``).

    Raises:
        StageError: when ``share`` is below ``minimum`` (the frozen ``JAXA_MIN_COVER_SHARE``, 0.5).
    """

    limit = method.JAXA_MIN_COVER_SHARE if minimum is None else minimum
    if share < limit:
        raise StageError(f"{file_name}: REGION covers {share:.3f} of the frame's land outside permanent water, less than half; "
                         "the protocol's test 1 is not usable on it")


def jaxa_on_grid(found: Mapping[str, Any], grid: tuple[float, float, int, int], frame_land: np.ndarray) -> dict[str, Any]:
    """JAXA's water, its observation area and the compared cells on the grid, by cell centre, with their counts."""

    water = method.rasterize_polygons(found["flood"], grid)
    region = method.rasterize_polygons(found["region"], grid)
    compared = compared_cells(frame_land, region)
    share = region_cover(region, frame_land)
    counts = {
        "region_cells_on_the_grid": int(region.sum()),
        "frame_land_cells": int(np.asarray(frame_land, dtype=bool).sum()),
        "frame_land_cells_inside_region": int(compared.sum()),
        "share_of_frame_land_inside_region": round(share, 6),
        "fldext_cells_on_the_grid": int(water.sum()),
        "fldext_cells_inside_region": int((water & region).sum()),
        "fldext_cells_on_compared_cells": int((water & compared).sum()),
    }
    return {"water": water, "region": region, "compared": compared, "share": share, "counts": counts}


# ---------------------------------------------------------------------------
# Scoring helpers (the frozen test stage's closures, written out)
# ---------------------------------------------------------------------------


def verdict(central: Mapping[str, Any]) -> bool:
    """The protocol's pass rule: IoU (no answer counted as not flagged) >= 0.40 and no-answer share <= 0.20."""

    iou, share = central.get("iou_no_answer_as_not_flagged"), central.get("no_answer_share")
    return bool(iou is not None and iou >= method.PASS_IF_IOU and share is not None and share <= method.PASS_IF_NO_ANSWER)


def better_than_ours(comparators: Mapping[str, Any], ours: Mapping[str, Any]) -> dict[str, float]:
    """The comparators whose binding IoU is above ours; they are reported, never renamed as the result."""

    mine = ours.get("iou_no_answer_as_not_flagged") or 0
    return {name: entry["iou_no_answer_as_not_flagged"] for name, entry in comparators.items()
            if isinstance(entry, Mapping) and entry.get("iou_no_answer_as_not_flagged") is not None and entry["iou_no_answer_as_not_flagged"] > mine}


def level_figures(levels: Mapping[str, tuple[np.ndarray, np.ndarray]], water: np.ndarray, compared: np.ndarray, cover: np.ndarray) -> dict[str, Any]:
    """The measures of test 1 on one pass: the three levels, the central map by WorldCover group, its 95% interval and reasons."""

    code, reason = levels["central"]
    return {
        "central": m1z.evaluate(code, water, compared),
        "lower": m1z.evaluate(levels["lower"][0], water, compared),
        "upper": m1z.evaluate(levels["upper"][0], water, compared),
        "central_by_worldcover_group": m1z.evaluate_by_cover(code, water, compared, cover),
        "central_interval_95": m1z.tile_bootstrap(code, water, compared),
        "central_reasons_on_compared_cells": m1z.reason_counts(reason, compared),
    }


def gfm_comparator(found: Mapping[str, Any] | None, water: np.ndarray, compared: np.ndarray, frame_land: np.ndarray) -> dict[str, Any]:
    """GFM's map of the same pass scored against JAXA on the same cells, as the frozen test stage scores it."""

    if found is None:
        return {"not_run": "GFM holds no item of this pass over the frame"}
    if "error" in found:
        return {"not_run": found["error"]}
    code = method.gfm_reference(found, frame_land)[2]
    return {"items": found["items"], **m1z.evaluate(code, water, compared)}


def dry_chip_share(code: np.ndarray, window: tuple[slice, slice], permanent_water: np.ndarray) -> dict[str, Any]:
    """The share of the dry chip's answered cells our map flags (the frozen dry control's count), report only."""

    part = np.asarray(code)[window]
    answered = np.isin(part, (m1z.FLAGGED, m1z.NOT_FLAGGED)) & ~np.asarray(permanent_water, dtype=bool)[window]
    flagged = answered & (part == m1z.FLAGGED)
    return {"cells": int(part.size), "answered_cells": int(answered.sum()), "flagged_cells": int(flagged.sum()),
            "flagged_share_of_answered": round(float(flagged.sum()) / float(answered.sum()), 6) if answered.any() else None}


def existing_map(external: Path, event: Any, grid: tuple[float, float, int, int], levels: Mapping[str, tuple[np.ndarray, np.ndarray]],
                 freeze_sha256: str) -> dict[str, Any] | None:
    """The map of the pass that the maps stage wrote, after checking that it holds our values; ``None`` when absent.

    Raises:
        StageError: when the map has no record beside it, was made under another freeze record, or any of its four
            bands differs from the map this run makes.
    """

    path = external / method.MAPS / f"m1z_{event.label}.tif"
    if not path.is_file():
        return None
    record_path = path.with_suffix(".json")
    if not record_path.is_file():
        raise StageError(f"{path.name} is in the maps folder without its record: it is not a map of the maps stage")
    record = method.read_json(record_path)
    if (record.get("freeze_record") or {}).get("sha256") != freeze_sha256:
        raise StageError(f"{path.name} was made under another freeze record than the one in force")
    bands = method.read_bands(path, grid, "test", MAP_BANDS, as_float=False)
    differ = []
    for band, (level, part) in LEVEL_OF_BAND.items():
        ours = np.asarray(levels[level][part], dtype="uint8")
        if not np.array_equal(np.asarray(bands[band], dtype="uint8"), ours):
            differ.append(f"{band} ({int((np.asarray(bands[band], dtype='uint8') != ours).sum())} cells)")
    del bands
    if differ:
        raise StageError(f"{path.name} differs from the map this run makes in {', '.join(differ)}: the maps stage and this run "
                         "must give the frozen method's one map")
    digest = method.sha256_file(path)
    index_path = external / method.MAPS / "maps_index_v1.json"
    listed = None
    if index_path.is_file():
        entry = (method.read_json(index_path).get("maps") or {}).get(event.label)
        listed = bool(isinstance(entry, Mapping) and entry.get("sha256") == digest)
    return {"name": path.name, "sha256": digest, "record": record_path.name, "listed_in_the_maps_index_with_these_bytes": listed,
            "status": ("found in the maps folder (written by the maps stage or an earlier run of this script); this run read it "
                       "and found the same values in its four bands")}


def first_run_summary(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """The first run of the test stage, kept as written (amendment 2), and the figures reported beside test 1 of record."""

    test_1 = record.get("test_1") or {}
    central = test_1.get("central") or {}
    test_2 = record.get("test_2") or {}
    dry = record.get("dry_control") or {}
    binding = record.get("binding") or {}
    return {
        **file_entry(root, method.TEST_RESULT),
        "generated_at_utc": record.get("generated_at_utc"),
        "kept_as_written": True,
        "test_1_gfm_fallback_reported_beside": {
            "reference": test_1.get("reference"), "pass": (test_1.get("pass") or {}).get("label"),
            "iou_no_answer_as_not_flagged": central.get("iou_no_answer_as_not_flagged"), "no_answer_share": central.get("no_answer_share"),
            "passes": test_1.get("passes")},
        "test_2_reported_beside": {"pass": (test_2.get("pass") or {}).get("label"),
                                   "iou_no_answer_as_not_flagged": (test_2.get("central") or {}).get("iou_no_answer_as_not_flagged")},
        "dry_control_used_in_the_binding": {"passes": binding.get("dry_control_passes"), "pass": (dry.get("pass") or {}).get("label"),
                                            "flagged_share_of_answered": (dry.get("central") or {}).get("flagged_share_of_answered")},
        "binding_of_the_first_run_set_aside_by_amendment_2": {
            "test_1_passes": binding.get("test_1_passes"), "case_reference_date": binding.get("case_reference_date"),
            "flood_input_of_case_N1": (binding.get("flood_input_of_case_N1") or {}).get("label"),
            "reference_of_case_N2": (binding.get("reference_of_case_N2") or {}).get("name")},
    }


# ---------------------------------------------------------------------------
# The order checks
# ---------------------------------------------------------------------------


def preflight(root: Path, arguments: argparse.Namespace) -> dict[str, Any]:
    """Refuse a run out of the order of the protocol and amendment 2; return the freeze, the first run and amendment 2.

    Raises:
        StageError: when the freeze record or the first test record is missing; the freeze is not committed,
            unchanged and pushed or the code differs from it; this record exists without ``--replace`` and
            ``--reason``; an amendment is missing, or amendment 2 is not committed and pushed; the first test record
            differs from HEAD; this script is not committed and pushed; the code that runs is not the code the
            records name; amendment 1 gives no offset for Sentinel-1C.
    """

    if not (root / method.FREEZE).is_file():
        raise StageError(f"no freeze record {method.FREEZE}: test 1 of record runs only under the freeze")
    if not (root / method.TEST_RESULT).is_file():
        raise StageError(f"{method.TEST_RESULT} does not exist: test 1 of record runs after the first run of the test stage (amendment 2)")
    freeze = method.require_frozen(root)
    if arguments.replace and not arguments.reason:
        raise StageError("--replace needs --reason")
    if (root / OUTPUT).exists() and not arguments.replace:
        raise StageError(f"{OUTPUT} exists: test 1 of record runs once (replace only with --replace and --reason)")
    for name in (method.AMENDMENT_1, AMENDMENT_2):
        if not (root / name).is_file():
            raise StageError(f"{name} is missing")
    amendment_2 = method.read_json(root / AMENDMENT_2)
    if amendment_2.get("amendment") != 2 or "test_1_of_record" not in (amendment_2.get("decision") or {}):
        raise StageError(f"{AMENDMENT_2} is not the amendment that names test 1 of record")
    for name in (AMENDMENT_2, method.TEST_RESULT):
        if not method.same_as_head(root, name):
            raise StageError(f"{name} is not in the HEAD commit or differs from it: commit it unchanged")
    if method.pushed_commit(root, AMENDMENT_2) is None:
        raise StageError(f"the commit of {AMENDMENT_2} is on no remote branch: push it before test 1 of record runs")
    dirty = method.uncommitted(root, [SCRIPT])
    if dirty:
        raise StageError(f"commit this script first: test 1 of record runs only from committed code (uncommitted: {', '.join(dirty)})")
    if method.pushed_commit(root, SCRIPT) is None:
        raise StageError(f"the commit of {SCRIPT} is on no remote branch: push it before the run")
    if method.sha256_file(Path(__file__)) != method.sha256_file(root / SCRIPT):
        raise StageError(f"the script that runs is not {SCRIPT} of the repository it records")
    running = {"scripts/nan_case_method.py": method.sha256_file(Path(method.__file__)), "src/floodguard/m1z.py": method.sha256_file(Path(m1z.__file__))}
    if any(freeze["code_sha256"].get(name) != digest for name, digest in running.items()):
        raise StageError("the frozen code that runs differs from the code the freeze record binds")
    first_run = method.read_json(root / method.TEST_RESULT)
    if not isinstance((first_run.get("binding") or {}).get("dry_control_passes"), bool):
        raise StageError(f"{method.TEST_RESULT} gives no dry control outcome (binding.dry_control_passes)")
    offsets = method.platform_offsets(root)
    if TEST_1_PLATFORM not in offsets:
        raise StageError("amendment 1 gives no offset for Sentinel-1C: the pass of test 1 of record cannot be read as amendment 2 says")
    return {"freeze": freeze, "first_run": first_run, "amendment_2": amendment_2, "offsets": offsets}


def choose_passes(passes: Sequence[Any], folder: Path) -> tuple[Any, Any | None, dict[str, Any]]:
    """The pass of test 1 (the named Sentinel-1C pass of 2025-07-28) and the pass of test 1b (nearest to 2025-07-19 12:00 Thai time).

    Raises:
        StageError: when the pass of test 1 is not fetched or its orbit has no dry-season statistics.
    """

    target = method.parse_time(method.TEST1_FALLBACK_PASS_UTC)
    event = method.nearest_pass(passes, target, within_minutes=method.PASS_MATCH_MINUTES)
    if event is None or method.platform_key(event.platform) != TEST_1_PLATFORM or event.time.date() != target.date():
        raise StageError("the Sentinel-1C pass of 2025-07-28 about 11:20 UTC (amendment 2) is not among the fetched Nan passes")
    method.dry_file(folder, event.orbit)
    second_target = method.parse_time(TEST_1B_TARGET_UTC)
    second = method.nearest_pass(passes, second_target)
    about: dict[str, Any] = {"target_utc": TEST_1B_TARGET_UTC, "target_words": "2025-07-19 12:00 Thai time"}
    if second is not None:
        about["hours_from_the_target"] = round(abs((second.time - second_target).total_seconds()) / 3600, 2)
        try:
            method.dry_file(folder, second.orbit)
        except StageError as error:
            about["not_scored"] = str(error)
    return event, second, about


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def stage(root: Path, arguments: argparse.Namespace, hooks: Mapping[str, Any]) -> dict[str, Any]:
    """Run test 1 of record once and write ``outputs/nan_case/test_1_jaxa_v1.json``; returns the record.

    Raises:
        StageError: when the order is broken (:func:`preflight`), a seal is broken, a JAXA layer is missing, REGION
            covers less than half of the frame's land, the named pass is missing, or the maps stage's map of the pass
            differs from this run's map.
    """

    checked = preflight(root, arguments)
    freeze, first_run, offsets = checked["freeze"], checked["first_run"], checked["offsets"]
    external = Path(arguments.external_root)
    log = method.Log(external / method.WORK / "test_1_jaxa.log")
    protocol, areas = method.read_json(root / method.PROTOCOL), method.read_json(root / method.AREAS)
    grid = method.area_grid(areas, method.FRAME_AREA)
    selected = m1z.M1zParameters.from_json(freeze["selected"])
    freeze_sha256 = method.sha256_file(root / method.FREEZE)
    gfm_fetch: Callable[..., Any] = hooks.get("gfm_fetch", method.fetch_gfm)
    seals = protocol["sealed_references"]["files"]
    if JAXA_MAIN not in seals:
        raise StageError(f"the protocol seals no file {JAXA_MAIN}")

    # --- preflight on the files: every input is found before JAXA is read --------------------------------------
    sealed = method.sealed_files(root, external, protocol)
    if sealed.get(JAXA_MAIN) is None:
        raise StageError(f"{JAXA_MAIN} is not in the sealed folder")
    radar = method.area_folder(external / method.RADAR_DIR, [method.FRAME_AREA])
    if radar is None:
        raise StageError(f"no radar folder {external / method.RADAR_DIR / method.FRAME_AREA}")
    try:
        passes = method.discover_passes(radar, "test")
    except StageError:
        raise
    except Exception as error:  # noqa: BLE001 - a pass being written by a download cannot be opened yet
        raise StageError(f"a pass in {radar.name} cannot be read ({type(error).__name__}: {error}); let the download finish first") from error
    event, second_pass, second_about = choose_passes(passes, radar)
    terrain = method.load_terrain(external, [method.FRAME_AREA], grid, "test")
    boundaries = Path(arguments.boundaries) if arguments.boundaries else external / method.BOUNDARIES
    units, units_record = method.frame_units_mask(boundaries, grid, protocol["frame"]["district_pcodes"])
    named_count = re.search(r"\((\d+) units", str(protocol["frame"].get("units", "")))
    units_record["units_the_protocol_names"] = int(named_count.group(1)) if named_count else None
    units_record["matches_the_protocol"] = None if named_count is None else units_record["units"] == int(named_count.group(1))
    frame_land = units & ~terrain["permanent_water"]
    log(f"test 1 of record: preflight passed; pass {event.label}; frame land {int(frame_land.sum())} cells")

    # --- JAXA of 2025-07-28: the reference of test 1 -------------------------------------------------------------
    jaxa_files: dict[str, Any] = {}
    data = read_sealed(sealed[JAXA_MAIN], seals[JAXA_MAIN])
    jaxa_files[JAXA_MAIN] = {"sha256_in_the_protocol": seals[JAXA_MAIN], "sha256_of_the_bytes_read": sha256_bytes(data)}
    found = jaxa_layers(data, JAXA_MAIN)
    del data
    main = jaxa_on_grid(found, grid, frame_land)
    require_cover(main["share"], JAXA_MAIN)
    water, compared = main["water"], main["compared"]
    jaxa_main_record = {**found["record"], **main["counts"],
                        "usable_rule": "REGION covers at least half of the frame's land outside permanent water (protocol test 1, usable_if)",
                        "usable": True}
    jaxa_times = found["times"]
    del found

    # --- JAXA of 2025-07-19: test 1b, report only (a missing layer is recorded, not refused) ---------------------
    second: dict[str, Any] | None = None
    second_record: dict[str, Any]
    if sealed.get(JAXA_SECOND) is None:
        second_record = {"file": JAXA_SECOND, "not_scored": "the file is not in the sealed folder"}
    else:
        data = read_sealed(sealed[JAXA_SECOND], seals[JAXA_SECOND])
        jaxa_files[JAXA_SECOND] = {"sha256_in_the_protocol": seals[JAXA_SECOND], "sha256_of_the_bytes_read": sha256_bytes(data)}
        try:
            found = jaxa_layers(data, JAXA_SECOND)
        except JaxaLayerError as error:
            second_record = {"file": JAXA_SECOND, "not_scored": str(error)}
        else:
            second = jaxa_on_grid(found, grid, frame_land)
            second_record = {**found["record"], **second["counts"],
                             "region_covers_at_least_half_of_the_frame_land": bool(second["share"] >= method.JAXA_MIN_COVER_SHARE)}
            del found
        del data

    # --- our map of the 2025-07-28 pass, with the offset of amendment 1 -----------------------------------------
    started = time.time()
    inputs = method.load_pass(event, grid, "test", offsets=offsets)
    applied = float(inputs["platform_offset_db"])
    if abs(applied - float(offsets[TEST_1_PLATFORM])) > 1e-9:
        raise StageError(f"the offset applied to {event.label} is {applied} dB, not the {offsets[TEST_1_PLATFORM]} dB of amendment 1")
    files_main = inputs["files"]
    levels = method.m1z_levels(inputs, terrain, selected)
    map_entry = existing_map(external, event, grid, levels, freeze_sha256)
    comparator_codes = method.comparator_maps(root, inputs, terrain, grid)
    del inputs
    figures = {"pass": event.as_json(), **level_figures(levels, water, compared, terrain["cover"]), "platform_offset_db": applied}
    figures["comparators"] = method.score_comparators(comparator_codes, water, compared)
    del comparator_codes
    raw = method.load_pass(event, grid, "test")
    raw_code = method.m1z_levels(raw, terrain, selected)["central"][0]
    figures["central_without_platform_offset_report_only"] = {**m1z.evaluate(raw_code, water, compared), "platform_offset_db": 0.0}
    del raw, raw_code
    log(f"test 1 of record: {event.label} scored in {time.time() - started:.0f} s")

    if arguments.skip_gfm:
        gfm = {"not_run": "skipped on the command line (--skip-gfm)"}
    else:
        try:
            gfm_found = gfm_fetch(grid, event.time - timedelta(minutes=method.GFM_WINDOW_MINUTES), event.time + timedelta(minutes=method.GFM_WINDOW_MINUTES))
        except Exception as error:  # noqa: BLE001 - GFM is a comparator here; a failure is recorded
            gfm_found = {"error": f"{type(error).__name__}: {error}"}
        gfm = gfm_comparator(gfm_found, water, compared, frame_land)
        del gfm_found

    choice = ("the Sentinel-1C pass of 2025-07-28 about 11:20 UTC that amendment 2 names, because JAXA's files give no "
              "acquisition time with a zone")
    if jaxa_times:
        choice += "; the files hold the times with a zone listed under jaxa, which do not change the pass amendment 2 names"
    test_1 = {
        "reference": "JAXA ALOS-2 Flood Proxy Map of 2025-07-28 (layer FLDEXT as water, inside layer REGION)",
        "label": "Agreement with JAXA's ALOS-2 map (another satellite, L-band, automatic analysis), not a ground check.",
        "of_record_under": "amendment 2 of the protocol (decision log R53)",
        "pass_choice": choice,
        "compared_cells_rule": "frame land (cell centre inside the 35 units, outside WorldCover class 80) whose cell centre lies inside REGION",
        "jaxa": jaxa_main_record,
        **figures,
        "external_comparator_gfm_same_pass": gfm,
        "measures_named": MEASURES_NAMED,
        "pass_if": f"IoU (no answer counted as not flagged) >= {method.PASS_IF_IOU} and no-answer share <= {method.PASS_IF_NO_ANSWER}",
    }
    test_1["passes"] = verdict(test_1["central"])
    test_1["verdict"] = "passes" if test_1["passes"] else "does not pass"
    test_1["comparators_better_by_iou"] = better_than_ours({**test_1["comparators"], "gfm": gfm}, test_1["central"])
    log(f"test 1 of record: IoU {test_1['central']['iou_no_answer_as_not_flagged']}, no-answer share {test_1['central']['no_answer_share']}; {test_1['verdict']}")

    # --- test 1b, report only --------------------------------------------------------------------------------------
    test_1b: dict[str, Any] = {"report_only": True, "jaxa": second_record, "pass_choice": "the pass nearest to 2025-07-19 12:00 Thai time",
                               "pass_target": second_about}
    files_second = None
    if second is not None and second_pass is not None and "not_scored" not in second_about and second["compared"].any():
        inputs = method.load_pass(second_pass, grid, "test", offsets=offsets)
        files_second = inputs["files"]
        levels_second = method.m1z_levels(inputs, terrain, selected)
        offset_second = float(inputs["platform_offset_db"])
        del inputs
        test_1b.update({"pass": second_pass.as_json(), **level_figures(levels_second, second["water"], second["compared"], terrain["cover"]),
                        "platform_offset_db": offset_second,
                        "label": "Agreement with JAXA's ALOS-2 map of 2025-07-19 inside its REGION, not a ground check; report only."})
        del levels_second
    elif "not_scored" not in second_record:
        test_1b["not_scored"] = second_about.get("not_scored") or "no pass or no compared cell for the map of 2025-07-19"
    del second

    # --- report only: the dry chip on the test 1 pass ---------------------------------------------------------------
    try:
        window = m1z.centre_window(grid, protocol["grid"]["chips"][method.CHIP_DRY])
        dry_chip = {"report_only": True, "pass": event.as_json(),
                    "rule_of_the_first_run": f"our map flags at most {method.DRY_CONTROL_MAX_SHARE} of the chip's answered cells (permanent water left out)",
                    **{level: dry_chip_share(levels[level][0], window, terrain["permanent_water"]) for level in ("central", "lower", "upper")}}
    except (KeyError, TypeError, m1z.M1zError) as error:
        dry_chip = {"report_only": True, "not_run": f"{type(error).__name__}: {error}"}

    # --- checks before anything is written ------------------------------------------------------------------------
    if map_entry is None:
        map_entry = existing_map(external, event, grid, levels, freeze_sha256)   # the maps stage may have run meanwhile
    for name in jaxa_files:
        jaxa_files[name]["sha256_after_the_scoring"] = verify_seal(sealed[name], seals[name])
        jaxa_files[name]["unchanged"] = True
        jaxa_files[name]["read"] = "in memory; never extracted or changed"

    # --- writes: the map (if the maps stage has not written it), the case N2 reference, the record -----------------
    if map_entry is None:
        written = method.write_pass_map(external, event, grid, levels, {"files": files_main}, terrain, freeze_sha256, freeze["flood_levels"], units)
        map_entry = {**written, "status": "written by this run in the format of the maps stage, which had not written it"}
    reference_n2 = method.write_case_n2_reference(
        external, grid, np.where(main["region"], np.where(water, m1z.FLAGGED, m1z.NOT_FLAGGED), m1z.NO_ANSWER).astype("uint8"), CASE_N2_NAME,
        "JAXA's FLDEXT polygons of 2025-07-28 as provided, by cell centre, inside its REGION layer; 255 outside REGION")
    binding = {
        "test_1_passes": bool(test_1["passes"]),
        "dry_control_passes": bool(first_run["binding"]["dry_control_passes"]),
        "dry_control_taken_from": file_entry(root, method.TEST_RESULT),
        "case_reference_date": CASE_REFERENCE_DATE,
        "flood_input_of_case_N1": {**event.as_json(), "map": {key: map_entry[key] for key in ("name", "sha256", "record")},
                                   "levels": "bands code_lower, code_central and code_upper of the map (lower, central and upper flood)",
                                   "platform_offset_db": applied,
                                   "days_from_the_case_reference_date_thai_calendar": method.pass_days(event, CASE_REFERENCE_DATE)},
        "per_tambon_conditions": "set by the planning lane from the map of the flood input: no-answer share <= 0.20, answered land >= 0.80, pass within 3 days, C4 to C8",
        "reference_of_case_N2": reference_n2,
        "under": "amendment 2: the binding rule of the protocol applies with this test 1 and the dry control of the first run",
    }
    times = [event.as_json()["time_utc"]] + ([second_pass.as_json()["time_utc"]] if second_pass is not None and "pass" in test_1b else [])
    record = {
        "schema": SCHEMA,
        **method.envelope(f"Nan passes {', '.join(str(item) for item in times)}; JAXA ALOS-2 maps of 2025-07-28 and 2025-07-19 "
                          "(their files give no time with a zone)", "low", ASSUMPTIONS),
        "confidence_basis": "One event and one frame; the reference is another satellite's automatic map, not a ground check.",
        "what_this_is": ("Test 1 of record of the Nan case under amendment 2: the frozen M1-z of the Sentinel-1C pass of 2025-07-28 "
                         "against JAXA's ALOS-2 map of the same day inside its observation area, with the comparators, the "
                         "map of 2025-07-19 (report only) and the binding outcome of the case."),
        "freeze_record": file_entry(root, method.FREEZE),
        "protocol": file_entry(root, method.PROTOCOL),
        "amendment_1": {**file_entry(root, method.AMENDMENT_1), "platform_offset_db_applied_to_event_passes": offsets},
        "amendment_2": file_entry(root, AMENDMENT_2),
        "first_run": first_run_summary(root, first_run),
        "code_sha256": {SCRIPT: method.sha256_file(root / SCRIPT), **method.code_hashes(root)},
        "comparator_code_sha256": module_hashes(),
        "git_commit": method.head_commit(root),
        "frozen_parameters": freeze["flood_levels"],
        "frame": {**units_record, "boundaries_sha256": method.sha256_file(boundaries), "frame_land_cells": int(frame_land.sum()),
                  "grid": dict(zip(("west", "north", "rows", "cols"), grid)), "terrain_inputs": terrain["files"],
                  "cells_where_the_lane_permanent_water_differs_from_class_80": terrain["cells_where_the_lane_permanent_water_differs_from_class_80"]},
        "passes_on_disk": [item.as_json() for item in passes],
        "jaxa_files": jaxa_files,
        "test_1": test_1,
        "test_1b_report_only": test_1b,
        "dry_chip_report_only_on_the_test_1_pass": dry_chip,
        "binding": binding,
        "comparators": {"what": method.COMPARATOR_NOTES, "rule": "a comparator that does better is reported, never renamed as the result"},
        "map_files": {"test_1_pass": map_entry,
                      "inputs_of_the_test_1_pass": files_main,
                      "inputs_of_the_test_1b_pass": files_second},
        "rights_note": ("Only figures are recorded; no JAXA geometry or raster enters Git, and the case N2 reference stays in the work "
                        "folder. Credit: JAXA ALOS-2 maps 'Provided by JAXA' (Sentinel Asia)."),
        "limits": LIMITS,
        "supersedes": method.superseded(root / OUTPUT, arguments),
    }
    method.write_record(root / OUTPUT, record)
    log(f"test 1 of record: written {OUTPUT}")
    return record


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    """The command line of the script."""

    commands = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands.add_argument("--external-root", required=True, help="the external data root (outside Git)")
    commands.add_argument("--boundaries", help="the COD-AB file; default <external root>/open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip")
    commands.add_argument("--skip-gfm", action="store_true", help="do not ask GFM for its map of the pass (the comparator is then recorded as not run)")
    commands.add_argument("--replace", action="store_true", help="replace an existing record (needs --reason)")
    commands.add_argument("--reason", help="why the record is replaced")
    return commands


def run(argv: Sequence[str] | None = None, *, root: Path | None = None, hooks: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run test 1 of record; raises :class:`StageError` when it refuses."""

    arguments = parser().parse_args(argv)
    return stage(Path(root or ROOT), arguments, hooks or {})


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry: 0 when the record is written, 2 with a sentence when the run refuses."""

    try:
        run(argv)
    except StageError as error:
        print(f"refused: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
