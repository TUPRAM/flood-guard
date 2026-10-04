"""GEOID-Flood benchmark for M1-literal and M1-v2: split, loader and scoring.

The tile split is the one declared in the signed planning protocol v1a
(``geoid_split``): the 29 tiles of activation EMSR712-3 sorted by tile number,
the first 15 for development and the last 14 for the held-out test. This
module refuses to open a test tile while tuning, scores candidates against
the same-pass CEMS map and builds the failure-strata tables.

Scores here are **agreement with a same-pass CEMS map, not independent
accuracy**. Nothing in this module computes an FPPS or an action class.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

from floodguard import sar_change_v2 as sar
from floodguard.sar_change_v2 import CANDIDATE_ABSTAIN, CANDIDATE_NO, CANDIDATE_YES

AOI: str = "EMSR712-3"
DATASET_REPOSITORY: str = "links-ads/geoid-flood"
DATASET_REVISION: str = "868407460bf3db492f50730a57585916baa71dc6"

# Declared in docs/proposal_execution/planning_protocol_v1a.json, geoid_split.
PROTOCOL_V1A_SHA256: str = "b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954"
DEVELOPMENT_TILE_IDS: tuple[int, ...] = (9, 10, 12, 13, 20, 21, 22, 23, 24, 25, 26, 30, 31, 32, 33)
TEST_TILE_IDS: tuple[int, ...] = (35, 36, 37, 38, 39, 40, 41, 42, 45, 46, 47, 48, 49, 50)
ALL_TILE_IDS: tuple[int, ...] = DEVELOPMENT_TILE_IDS + TEST_TILE_IDS

PHASE_TUNING: str = "tuning"
PHASE_HELD_OUT_SCORING: str = "held_out_scoring"

T2_SKILL_BAR_TEST_IOU_MIN: float = 0.40

AGREEMENT_WORDING: str = "agreement with a same-pass CEMS map, not independent accuracy"
REQUIRED_STATEMENT: str = (
    "v2 thresholds were tuned on GEOID development tiles and scored on held-out GEOID "
    "test tiles against a same-pass CEMS map (agreement, not independent accuracy). "
    "Design choices were informed by the Mae Sai diagnosis. Test tiles had been included "
    "in an earlier exploratory all-tile diagnostic (0.161 to 0.455), which is labelled "
    "exploratory."
)

LABEL_BACKGROUND: int = 0
LABEL_PERMANENT_WATER: int = 1
LABEL_FLOOD: int = 2
LABEL_OUTSIDE: int = 255

COUNT_KEYS: tuple[str, ...] = (
    "true_positive",
    "false_positive",
    "false_negative",
    "true_negative",
    "evaluable_cells",
    "covered_cells",
    "reference_flood_cells",
    "abstained_reference_flood_cells",
    "abstained_reference_nonflood_cells",
)

FLOODED_SHARE_STRATA: tuple[str, ...] = (
    "no reference flood",
    "above 0 to 1%",
    "above 1% to 5%",
    "above 5% to 20%",
    "above 20%",
)
PRE_EVENT_VH_EDGES_DB: tuple[float, ...] = (-22.0, -18.0, -14.0)
PRE_EVENT_VH_STRATA: tuple[str, ...] = (
    "pre-event VH below -22 dB",
    "pre-event VH -22 to -18 dB",
    "pre-event VH -18 to -14 dB",
    "pre-event VH -14 dB or above",
)
BOUNDARY_BAND_CELLS: int = 2
BOUNDARY_STRATA: tuple[str, ...] = (
    "within 2 cells of a reference flood edge",
    "further than 2 cells from a reference flood edge",
)

_SOURCE_PATTERN = re.compile(r"^EMSR712-3-(\d+)_s1grd_(pre|post)_(\d{8}T\d{6})\.tif$")


class GeoidBenchmarkError(ValueError):
    """The split, the sources or the freeze cannot support the benchmark."""


class TestTileAccessRefused(PermissionError):
    """A held-out test tile was requested where the protocol forbids it."""

    __test__ = False  # Not a pytest test class.


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def bytes_sha256(data: bytes) -> str:
    """SHA-256 of a byte string, as lowercase hex."""

    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Stable JSON encoding: sorted keys, two-space indent, LF, final newline."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def array_sha256(array: np.ndarray) -> str:
    """SHA-256 of an array's shape, dtype and C-order bytes."""

    values = np.ascontiguousarray(array)
    header = f"{values.dtype.str}:{values.shape}:".encode("ascii")
    return hashlib.sha256(header + values.tobytes()).hexdigest()


# ---------------------------------------------------------------------------
# Split and loader
# ---------------------------------------------------------------------------


def split_of(tile_id: int) -> str:
    """Return ``"development"`` or ``"test"`` for a declared tile number."""

    if tile_id in DEVELOPMENT_TILE_IDS:
        return "development"
    if tile_id in TEST_TILE_IDS:
        return "test"
    raise GeoidBenchmarkError(f"Tile {tile_id} is not one of the 29 declared tiles")


def verify_split_against_protocol(protocol: Mapping[str, Any]) -> None:
    """Check the module's split against a loaded planning protocol v1a.

    The protocol's rule is: sort the 29 tile numbers, the first 15 are
    development tiles and the remaining 14 are test tiles.
    """

    declared = protocol.get("geoid_split", {})
    development = tuple(declared.get("development_tile_ids", ()))
    test = tuple(declared.get("test_tile_ids", ()))
    if development != DEVELOPMENT_TILE_IDS or test != TEST_TILE_IDS:
        raise GeoidBenchmarkError("The split in code differs from protocol v1a geoid_split")
    ordered = tuple(sorted(development + test))
    if ordered[:15] != development or ordered[15:] != test or len(ordered) != 29:
        raise GeoidBenchmarkError("The declared split does not follow the v1a ordering rule")


def allowed_tile_ids(phase: str) -> tuple[int, ...]:
    """Tile numbers that may be opened in a phase."""

    if phase == PHASE_TUNING:
        return DEVELOPMENT_TILE_IDS
    if phase == PHASE_HELD_OUT_SCORING:
        return ALL_TILE_IDS
    raise GeoidBenchmarkError(f"Unknown phase: {phase}")


def require_access(tile_id: int, phase: str, freeze_commit: str | None = None) -> None:
    """Raise unless the protocol lets this phase open this tile.

    While tuning, any test tile is refused. Held-out scoring is refused
    altogether until the caller names the commit that holds the frozen
    configuration.
    """

    split = split_of(tile_id)
    if phase == PHASE_TUNING:
        if split == "test":
            raise TestTileAccessRefused(
                f"Tile {tile_id} is a held-out test tile and cannot be opened while tuning"
            )
        return
    if phase == PHASE_HELD_OUT_SCORING:
        if not freeze_commit or not re.fullmatch(r"[0-9a-f]{40}", freeze_commit):
            raise TestTileAccessRefused(
                "Held-out scoring needs the commit of the frozen configuration first"
            )
        return
    raise GeoidBenchmarkError(f"Unknown phase: {phase}")


@dataclass(frozen=True)
class TileInputs:
    """Radar inputs of one tile. Carries no reference information."""

    tile_id: int
    pre: np.ndarray
    post: np.ndarray
    pre_acquired_utc: str
    post_acquired_utc: str
    source_sha256: dict[str, str]


@dataclass(frozen=True)
class TileReference:
    """Same-pass CEMS label and validity rasters of one tile."""

    tile_id: int
    label: np.ndarray
    validity: np.ndarray
    source_sha256: dict[str, str]


def _acquired_utc(stamp: str) -> str:
    return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"


class GeoidTileStore:
    """Read EMSR712-3 tiles from disk under the split's access rule.

    ``sample_root`` is the directory that holds ``s1grd``, ``label`` and
    ``validity``. ``published_sums`` is the publisher's SHA256SUMS file;
    every file is checked against it before any pixel is read.
    """

    def __init__(
        self,
        sample_root: Path,
        published_sums: Path,
        *,
        phase: str,
        freeze_commit: str | None = None,
    ) -> None:
        allowed_tile_ids(phase)
        self._root = Path(sample_root)
        self._sums_path = Path(published_sums)
        self._phase = phase
        self._freeze_commit = freeze_commit
        self._published: dict[str, str] | None = None

    @property
    def phase(self) -> str:
        return self._phase

    def tile_ids(self) -> tuple[int, ...]:
        """Tile numbers this store will open."""

        return allowed_tile_ids(self._phase)

    def _published_hash(self, relative: str) -> str:
        if self._published is None:
            published: dict[str, str] = {}
            for line in self._sums_path.read_text(encoding="utf-8").splitlines():
                if "  " not in line:
                    raise GeoidBenchmarkError("Malformed published SHA256SUMS line")
                digest, name = line.split("  ", 1)
                published[name] = digest
            self._published = published
        try:
            return self._published[relative]
        except KeyError as error:
            raise GeoidBenchmarkError(f"No published SHA-256 for {relative}") from error

    def _verified(self, folder: str, filename: str) -> tuple[Path, str, str]:
        relative = str(PurePosixPath("sample", "geoid-flood", AOI, folder, filename))
        path = self._root / folder / filename
        if not path.is_file():
            raise GeoidBenchmarkError(f"Missing source file: {relative}")
        actual = file_sha256(path)
        if actual != self._published_hash(relative):
            raise GeoidBenchmarkError(f"Published SHA-256 mismatch: {relative}")
        return path, relative, actual

    def read_inputs(self, tile_id: int) -> TileInputs:
        """Read the pre and post linear sigma0 rasters of a permitted tile."""

        require_access(tile_id, self._phase, self._freeze_commit)
        import rasterio

        found: dict[str, tuple[Path, str, str, str]] = {}
        for candidate in sorted((self._root / "s1grd").glob(f"{AOI}-{tile_id}_s1grd_*.tif")):
            match = _SOURCE_PATTERN.fullmatch(candidate.name)
            if match is None or int(match.group(1)) != tile_id:
                raise GeoidBenchmarkError(f"Unexpected S1GRD file name: {candidate.name}")
            phase = match.group(2)
            if phase in found:
                raise GeoidBenchmarkError(f"Duplicate {phase} image for tile {tile_id}")
            path, relative, digest = self._verified("s1grd", candidate.name)
            found[phase] = (path, relative, digest, match.group(3))
        if set(found) != {"pre", "post"}:
            raise GeoidBenchmarkError(f"Tile {tile_id} needs one pre and one post image")
        arrays: dict[str, np.ndarray] = {}
        grids = []
        for phase, (path, _, _, _) in found.items():
            with rasterio.open(path) as dataset:
                if dataset.count != 2:
                    raise GeoidBenchmarkError("S1GRD tiles must have two bands (VV, VH)")
                names = tuple((name or "").upper() for name in dataset.descriptions)
                if any(names) and names != ("VV", "VH"):
                    raise GeoidBenchmarkError(f"Unrecognised band order: {names}")
                arrays[phase] = np.asarray(
                    dataset.read(masked=True).filled(np.nan), dtype="float32"
                )
                grids.append((dataset.crs, dataset.transform, dataset.width, dataset.height))
        if grids[0] != grids[1]:
            raise GeoidBenchmarkError(f"Pre and post grids differ for tile {tile_id}")
        if found["pre"][3] >= found["post"][3]:
            raise GeoidBenchmarkError(f"Pre image is not earlier than post for tile {tile_id}")
        return TileInputs(
            tile_id=tile_id,
            pre=arrays["pre"],
            post=arrays["post"],
            pre_acquired_utc=_acquired_utc(found["pre"][3]),
            post_acquired_utc=_acquired_utc(found["post"][3]),
            source_sha256={found[phase][1]: found[phase][2] for phase in ("pre", "post")},
        )

    def read_reference(self, tile_id: int) -> TileReference:
        """Read the label and validity rasters of a permitted tile."""

        require_access(tile_id, self._phase, self._freeze_commit)
        import rasterio

        arrays: dict[str, np.ndarray] = {}
        hashes: dict[str, str] = {}
        for layer in ("label", "validity"):
            path, relative, digest = self._verified(layer, f"{AOI}-{tile_id}_{layer}.tif")
            with rasterio.open(path) as dataset:
                if dataset.count != 1:
                    raise GeoidBenchmarkError(f"{layer} must have one band")
                arrays[layer] = dataset.read(1)
            hashes[relative] = digest
        return TileReference(
            tile_id=tile_id,
            label=arrays["label"],
            validity=arrays["validity"],
            source_sha256=hashes,
        )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def evaluable_mask(
    label: np.ndarray, validity: np.ndarray, *, include_permanent_water: bool
) -> np.ndarray:
    """Cells that take part in a comparison.

    The primary comparison keeps mapped flood, background and permanent
    water inside the valid mapped area. The secondary comparison drops
    permanent water.
    """

    label = np.asarray(label)
    validity = np.asarray(validity)
    if label.shape != validity.shape:
        raise GeoidBenchmarkError("Label and validity grids differ")
    if not np.isin(label, (LABEL_BACKGROUND, LABEL_PERMANENT_WATER, LABEL_FLOOD, LABEL_OUTSIDE)).all():
        raise GeoidBenchmarkError("The label raster contains an unknown code")
    if not np.isin(validity, (0, 1)).all():
        raise GeoidBenchmarkError("The validity raster contains an unknown code")
    classes = (
        (LABEL_BACKGROUND, LABEL_PERMANENT_WATER, LABEL_FLOOD)
        if include_permanent_water
        else (LABEL_BACKGROUND, LABEL_FLOOD)
    )
    return (validity == 1) & np.isin(label, classes)


def confusion_counts(
    candidate: np.ndarray,
    label: np.ndarray,
    validity: np.ndarray,
    *,
    include_permanent_water: bool,
    within: np.ndarray | None = None,
) -> dict[str, int]:
    """Count agreement cells between a candidate and the CEMS map.

    The four confusion counts cover only evaluable cells where the candidate
    did not abstain. Abstained evaluable cells are counted separately, split
    by reference class, so that both readings of the score can be computed.
    ``within`` restricts the count to a stratum.
    """

    candidate = np.asarray(candidate)
    if candidate.shape != np.asarray(label).shape:
        raise GeoidBenchmarkError("Candidate and label grids differ")
    if not np.isin(candidate, (CANDIDATE_NO, CANDIDATE_YES, CANDIDATE_ABSTAIN)).all():
        raise GeoidBenchmarkError("The candidate contains an unknown code")
    evaluable = evaluable_mask(label, validity, include_permanent_water=include_permanent_water)
    if within is not None:
        if within.shape != candidate.shape:
            raise GeoidBenchmarkError("Stratum and candidate grids differ")
        evaluable = evaluable & within
    flood = np.asarray(label) == LABEL_FLOOD
    covered = evaluable & (candidate != CANDIDATE_ABSTAIN)
    abstained = evaluable & (candidate == CANDIDATE_ABSTAIN)
    predicted = candidate == CANDIDATE_YES
    return {
        "true_positive": int((covered & flood & predicted).sum()),
        "false_positive": int((covered & ~flood & predicted).sum()),
        "false_negative": int((covered & flood & ~predicted).sum()),
        "true_negative": int((covered & ~flood & ~predicted).sum()),
        "evaluable_cells": int(evaluable.sum()),
        "covered_cells": int(covered.sum()),
        "reference_flood_cells": int((evaluable & flood).sum()),
        "abstained_reference_flood_cells": int((abstained & flood).sum()),
        "abstained_reference_nonflood_cells": int((abstained & ~flood).sum()),
    }


def sum_counts(rows: Iterable[Mapping[str, int]]) -> dict[str, int]:
    """Add confusion counts cell by cell (pooling before any ratio)."""

    total: Counter[str] = Counter({key: 0 for key in COUNT_KEYS})
    for row in rows:
        for key in COUNT_KEYS:
            total[key] += int(row[key])
    return {key: int(total[key]) for key in COUNT_KEYS}


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def metrics_from_counts(counts: Mapping[str, int]) -> dict[str, Any]:
    """Turn pooled counts into scores; an undefined ratio is ``None``.

    Two readings are returned. ``covered`` scores only the cells where the
    method gave an answer. ``strict`` counts every abstained cell as "not a
    candidate", so abstaining over mapped flood costs recall. Coverage is the
    share of evaluable cells with an answer; the abstained share is its
    complement.
    """

    tp = int(counts["true_positive"])
    fp = int(counts["false_positive"])
    fn = int(counts["false_negative"])
    strict_fn = fn + int(counts["abstained_reference_flood_cells"])
    evaluable = int(counts["evaluable_cells"])
    covered = int(counts["covered_cells"])
    reference = int(counts["reference_flood_cells"])
    return {
        **{key: int(counts[key]) for key in COUNT_KEYS},
        "predicted_flood_cells": tp + fp,
        "covered": {
            "iou": _ratio(tp, tp + fp + fn),
            "dice": _ratio(2 * tp, 2 * tp + fp + fn),
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
        },
        "strict": {
            "iou": _ratio(tp, tp + fp + strict_fn),
            "dice": _ratio(2 * tp, 2 * tp + fp + strict_fn),
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + strict_fn),
        },
        "coverage": _ratio(covered, evaluable),
        "abstained_cell_share": _ratio(evaluable - covered, evaluable),
        "reference_flood_share": _ratio(reference, evaluable),
        "predicted_to_reference_area_ratio": _ratio(tp + fp, reference),
    }


def score_candidate(
    candidate: np.ndarray, label: np.ndarray, validity: np.ndarray
) -> dict[str, dict[str, Any]]:
    """Score one tile on the primary and the secondary comparison."""

    return {
        "primary": metrics_from_counts(
            confusion_counts(candidate, label, validity, include_permanent_water=True)
        ),
        "secondary": metrics_from_counts(
            confusion_counts(candidate, label, validity, include_permanent_water=False)
        ),
    }


def clears_skill_bar(metrics: Mapping[str, Any]) -> bool:
    """True when both readings of the pooled test IoU reach the v1a bar.

    Protocol v1a asks for a held-out test IoU of at least 0.40 and does not
    say how abstained cells count. This benchmark requires both the covered
    and the strict reading to reach it, so abstaining cannot buy the bar.
    """

    covered = metrics["covered"]["iou"]
    strict = metrics["strict"]["iou"]
    return (
        covered is not None
        and strict is not None
        and covered >= T2_SKILL_BAR_TEST_IOU_MIN
        and strict >= T2_SKILL_BAR_TEST_IOU_MIN
    )


# ---------------------------------------------------------------------------
# Failure strata
# ---------------------------------------------------------------------------


def flooded_share_stratum(share: float | None) -> str:
    """Name the flooded-share class of a tile (share of evaluable cells)."""

    if share is None or share <= 0:
        return FLOODED_SHARE_STRATA[0]
    if share <= 0.01:
        return FLOODED_SHARE_STRATA[1]
    if share <= 0.05:
        return FLOODED_SHARE_STRATA[2]
    if share <= 0.20:
        return FLOODED_SHARE_STRATA[3]
    return FLOODED_SHARE_STRATA[4]


def _dilate(mask: np.ndarray, cells: int) -> np.ndarray:
    """Grow a mask by ``cells`` in every direction (square neighbourhood)."""

    padded = np.pad(np.asarray(mask, dtype=bool), cells)
    grown = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    for row in range(2 * cells + 1):
        for column in range(2 * cells + 1):
            grown |= padded[row : row + height, column : column + width]
    return grown


def boundary_band(
    label: np.ndarray, validity: np.ndarray, cells: int = BOUNDARY_BAND_CELLS
) -> np.ndarray:
    """Cells within ``cells`` of an edge between mapped flood and non-flood."""

    evaluable = evaluable_mask(label, validity, include_permanent_water=True)
    flood = evaluable & (np.asarray(label) == LABEL_FLOOD)
    dry = evaluable & ~flood
    return _dilate(flood, cells) & _dilate(dry, cells)


def pre_event_vh_classes(pre_vh_db: np.ndarray) -> np.ndarray:
    """Class index 0 to 3 by pre-event VH backscatter; -1 where undefined.

    The dataset has no land-cover layer on disk, so pre-event backscatter is
    the only surface description the data supports: low values are smooth
    surfaces such as water, bare soil or short grass, high values are
    woodland and built-up areas.
    """

    values = np.asarray(pre_vh_db, dtype="float64")
    classes = np.full(values.shape, -1, dtype="int8")
    finite = np.isfinite(values)
    classes[finite] = np.digitize(values[finite], PRE_EVENT_VH_EDGES_DB).astype("int8")
    return classes


def stratum_counts(
    candidate: np.ndarray,
    label: np.ndarray,
    validity: np.ndarray,
    strata: Mapping[str, np.ndarray],
) -> dict[str, dict[str, int]]:
    """Primary-comparison counts inside each named cell stratum."""

    return {
        name: confusion_counts(
            candidate, label, validity, include_permanent_water=True, within=mask
        )
        for name, mask in strata.items()
    }


def cell_strata(
    label: np.ndarray, validity: np.ndarray, pre_vh_db: np.ndarray
) -> dict[str, np.ndarray]:
    """Cell strata of one tile: flood-edge band and pre-event VH class."""

    band = boundary_band(label, validity)
    classes = pre_event_vh_classes(pre_vh_db)
    strata: dict[str, np.ndarray] = {
        BOUNDARY_STRATA[0]: band,
        BOUNDARY_STRATA[1]: ~band,
    }
    for index, name in enumerate(PRE_EVENT_VH_STRATA):
        strata[name] = classes == index
    return strata


# ---------------------------------------------------------------------------
# Search space and freeze
# ---------------------------------------------------------------------------


def expand_search_space(dimensions: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Every combination of the declared dimensions, in declared order."""

    names = list(dimensions)
    combinations: list[dict[str, Any]] = [{}]
    for name in names:
        values = list(dimensions[name])
        if not values:
            raise GeoidBenchmarkError(f"Search dimension {name} is empty")
        combinations = [{**partial, name: value} for partial in combinations for value in values]
    return combinations


def select_run(runs: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Pick the tuning run by the declared rule.

    Highest pooled development IoU on the primary comparison with abstained
    cells counted as "not a candidate" (strict reading). Ties are broken by
    higher coverage, then by the earlier run. A run whose IoU is undefined
    ranks last.
    """

    if not runs:
        raise GeoidBenchmarkError("No tuning run to select from")

    def key(run: Mapping[str, Any]) -> tuple[float, float, int]:
        iou = run["development_iou_strict"]
        coverage = run["development_coverage"]
        return (
            -1.0 if iou is None else float(iou),
            -1.0 if coverage is None else float(coverage),
            -int(run["run_index"]),
        )

    return max(runs, key=key)


def build_freeze_receipt(
    *,
    frozen_config_sha256: str,
    declared_protocol_sha256: str,
    tuning_log_sha256: str,
    code_sha256: Mapping[str, str],
    selected_run_id: str,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Receipt written beside the frozen configuration."""

    return {
        "schema": "floodguard.geoid_m1_v2_freeze_receipt.v1",
        "frozen_config_sha256": frozen_config_sha256,
        "planning_protocol_v1a_sha256": PROTOCOL_V1A_SHA256,
        "declared_benchmark_protocol_sha256": declared_protocol_sha256,
        "tuning_log_sha256": tuning_log_sha256,
        "code_sha256": dict(sorted(code_sha256.items())),
        "selected_run_id": selected_run_id,
        "frozen_at_utc": frozen_at_utc,
        "test_tiles_opened_before_freeze": False,
        "statement": (
            "Chosen on the 15 development tiles only. No test tile label, prediction or "
            "score was opened before this receipt was committed."
        ),
    }


def verify_freeze_receipt(
    receipt: Mapping[str, Any],
    *,
    frozen_config_bytes: bytes,
    declared_protocol_bytes: bytes,
    tuning_log_bytes: bytes,
    code_bytes: Mapping[str, bytes],
) -> None:
    """Raise unless every hash in the receipt matches the given bytes."""

    if receipt.get("schema") != "floodguard.geoid_m1_v2_freeze_receipt.v1":
        raise GeoidBenchmarkError("Unexpected freeze receipt schema")
    if receipt.get("planning_protocol_v1a_sha256") != PROTOCOL_V1A_SHA256:
        raise GeoidBenchmarkError("The receipt names a different planning protocol v1a")
    checks = {
        "frozen_config_sha256": frozen_config_bytes,
        "declared_benchmark_protocol_sha256": declared_protocol_bytes,
        "tuning_log_sha256": tuning_log_bytes,
    }
    for field, data in checks.items():
        if receipt.get(field) != bytes_sha256(data):
            raise GeoidBenchmarkError(f"Freeze receipt mismatch: {field}")
    recorded = receipt.get("code_sha256", {})
    if set(recorded) != set(code_bytes):
        raise GeoidBenchmarkError("Freeze receipt lists different code files")
    for name, data in code_bytes.items():
        if recorded[name] != bytes_sha256(data):
            raise GeoidBenchmarkError(f"Code changed after the freeze: {name}")


# ---------------------------------------------------------------------------
# Tuning and evaluation runs
# ---------------------------------------------------------------------------

METHODS: tuple[str, ...] = ("m1_literal", "m1_v2_kittler_illingworth", "m1_v2_otsu_comparator")
SPLITS: tuple[str, ...] = ("development", "test")


def tile_name(tile_id: int) -> str:
    """Published tile name, for example ``EMSR712-3-9``."""

    return f"{AOI}-{tile_id}"


@dataclass(frozen=True)
class LoadedTiles:
    """Filtered inputs and references of the tiles a store may open."""

    filtered: dict[str, sar.FilteredPair]
    references: dict[str, TileReference]
    inputs: dict[str, TileInputs]
    input_sha256: dict[str, str]


def load_tiles(
    store: GeoidTileStore, tile_ids: Sequence[int], *, with_reference: bool
) -> LoadedTiles:
    """Read tiles through the store and apply the refined-Lee filter.

    The store's access rule applies to every tile. With ``with_reference``
    false no label or validity raster is opened.
    """

    filtered: dict[str, sar.FilteredPair] = {}
    references: dict[str, TileReference] = {}
    inputs: dict[str, TileInputs] = {}
    hashes: dict[str, str] = {}
    for tile_id in tile_ids:
        name = tile_name(tile_id)
        tile = store.read_inputs(tile_id)
        inputs[name] = tile
        hashes.update(tile.source_sha256)
        filtered[name] = sar.filter_pair(
            tile.pre,
            tile.post,
            speckle_filter="refined_lee_7x7",
            equivalent_looks=sar.SENTINEL1_IW_GRDH_LOOKS,
        )
        if with_reference:
            references[name] = store.read_reference(tile_id)
            hashes.update(references[name].source_sha256)
    return LoadedTiles(filtered, references, inputs, dict(sorted(hashes.items())))


def _score_predictions(
    predictions: Mapping[str, tuple[np.ndarray, dict[str, Any]]],
    references: Mapping[str, TileReference],
) -> dict[str, Any]:
    per_tile: dict[str, Any] = {}
    full: list[dict[str, dict[str, Any]]] = []
    for name in sorted(predictions):
        candidate, summary = predictions[name]
        reference = references[name]
        scores = score_candidate(candidate, reference.label, reference.validity)
        full.append(scores)
        primary = scores["primary"]
        per_tile[name] = {
            "abstained": summary["abstained"],
            "thresholds_db": {
                side: info["threshold_db"] for side, info in summary["sides"].items()
            },
            "selected_blocks": {
                side: info["selected_blocks"] for side, info in summary["sides"].items()
            },
            "blocks": {side: info["blocks"] for side, info in summary["sides"].items()},
            "iou_strict": primary["strict"]["iou"],
            "iou_covered": primary["covered"]["iou"],
            "precision": primary["covered"]["precision"],
            "recall_strict": primary["strict"]["recall"],
            "reference_flood_share": primary["reference_flood_share"],
        }
    return {
        "pooled": {
            comparison: metrics_from_counts(sum_counts(row[comparison] for row in full))
            for comparison in ("primary", "secondary")
        },
        "abstained_tiles": sum(row["abstained"] for row in per_tile.values()),
        "per_tile": per_tile,
    }


def tuning_runs(
    filtered: Mapping[str, sar.FilteredPair],
    references: Mapping[str, TileReference],
    grid: Sequence[Mapping[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Yield one scored record per declared configuration, in grid order.

    Each record holds the Kittler-Illingworth result that the selection rule
    reads and the Otsu comparator. Only tiles present in ``filtered`` are
    used, so the caller's store decides which tiles tuning can see.
    """

    selections: dict[tuple[str, str, int], dict[str, sar.BlockSelection]] = {}
    for index, parameters in enumerate(grid):
        outcome: dict[str, Any] = {}
        for method in sar.THRESHOLD_METHODS:
            config = sar.M1V2Config(threshold_method=method, **parameters)
            for side in config.sides():
                key = (config.channel, side, config.block_pixels)
                if key not in selections:
                    selections[key] = {
                        name: sar.select_blocks_for_side(pair, config, side)
                        for name, pair in filtered.items()
                    }
            reuse = {
                name: {
                    side: selections[(config.channel, side, config.block_pixels)][name]
                    for side in config.sides()
                }
                for name in filtered
            }
            predictions = sar.m1_v2_predict_filtered(filtered, config, selections=reuse)
            outcome[method] = _score_predictions(predictions, references)
        primary = outcome["kittler_illingworth"]["pooled"]["primary"]
        yield {
            "record": "run",
            "run_index": index + 1,
            "parameters": dict(parameters),
            "split": "development",
            "development_iou_strict": primary["strict"]["iou"],
            "development_iou_covered": primary["covered"]["iou"],
            "development_precision": primary["covered"]["precision"],
            "development_recall_strict": primary["strict"]["recall"],
            "development_coverage": primary["coverage"],
            "development_abstained_tiles": outcome["kittler_illingworth"]["abstained_tiles"],
            "otsu_comparator_development_iou_strict": outcome["otsu"]["pooled"]["primary"][
                "strict"
            ]["iou"],
            "kittler_illingworth": outcome["kittler_illingworth"],
            "otsu_comparator": outcome["otsu"],
        }


def evaluate_split(
    store: GeoidTileStore,
    split: str,
    *,
    literal_config: sar.M1LiteralConfig,
    config: sar.M1V2Config,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Run M1-literal, M1-v2 and the Otsu comparator on one split and score them.

    Every prediction of the split is made before any label is opened. The
    Otsu comparator uses ``config`` with the threshold method replaced.
    Returns one row per tile and the SHA-256 of every file read.
    """

    if split not in SPLITS:
        raise GeoidBenchmarkError(f"Unknown split: {split}")
    tile_ids = DEVELOPMENT_TILE_IDS if split == "development" else TEST_TILE_IDS
    loaded = load_tiles(store, tile_ids, with_reference=False)
    comparator = sar.m1_v2_config_from_json(
        {**sar.config_to_json(config), "threshold_method": "otsu"}
    )
    selections = {
        name: {side: sar.select_blocks_for_side(pair, config, side) for side in config.sides()}
        for name, pair in loaded.filtered.items()
    }
    candidates: dict[str, dict[str, tuple[np.ndarray, dict[str, Any]]]] = {
        "m1_literal": {
            name: sar.m1_literal_predict(tile.pre, tile.post, literal_config)
            for name, tile in loaded.inputs.items()
        },
        "m1_v2_kittler_illingworth": sar.m1_v2_predict_filtered(
            loaded.filtered, config, selections=selections
        ),
        "m1_v2_otsu_comparator": sar.m1_v2_predict_filtered(
            loaded.filtered, comparator, selections=selections
        ),
    }
    hashes = dict(loaded.input_sha256)
    rows: list[dict[str, Any]] = []
    for tile_id in tile_ids:
        name = tile_name(tile_id)
        reference = store.read_reference(tile_id)
        hashes.update(reference.source_sha256)
        strata = cell_strata(reference.label, reference.validity, loaded.filtered[name].pre_db[1])
        row: dict[str, Any] = {
            "tile": name,
            "split": split,
            "pre_acquired_utc": loaded.inputs[name].pre_acquired_utc,
            "post_acquired_utc": loaded.inputs[name].post_acquired_utc,
            "methods": {},
        }
        for method in METHODS:
            candidate, detail = candidates[method][name]
            scores = score_candidate(candidate, reference.label, reference.validity)
            detail = {key: value for key, value in detail.items() if key != "configuration"}
            row["methods"][method] = {
                "primary": scores["primary"],
                "secondary": scores["secondary"],
                "prediction": detail,
                "candidate_sha256": array_sha256(candidate),
                "cell_strata": stratum_counts(
                    candidate, reference.label, reference.validity, strata
                ),
            }
        row["reference_flood_share"] = row["methods"]["m1_literal"]["primary"][
            "reference_flood_share"
        ]
        row["flooded_share_stratum"] = flooded_share_stratum(row["reference_flood_share"])
        rows.append(row)
    return rows, dict(sorted(hashes.items()))


def aggregate_results(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pool per-tile rows into results by method and split, with strata."""

    def pool(subset: Sequence[Mapping[str, Any]], comparison: str) -> dict[str, Any]:
        return metrics_from_counts(sum_counts(item[comparison] for item in subset))

    results: dict[str, Any] = {}
    for method in METHODS:
        results[method] = {}
        for split in SPLITS:
            chosen = [row for row in rows if row["split"] == split]
            if not chosen:
                continue
            items = [row["methods"][method] for row in chosen]
            by_share: dict[str, list[Mapping[str, Any]]] = {}
            by_slice: dict[str, list[Mapping[str, Any]]] = {}
            for row in chosen:
                by_share.setdefault(row["flooded_share_stratum"], []).append(
                    row["methods"][method]
                )
                by_slice.setdefault(row["post_acquired_utc"], []).append(row["methods"][method])
            results[method][split] = {
                "tiles": len(chosen),
                "abstained_tiles": sum(bool(item["prediction"]["abstained"]) for item in items),
                "primary": pool(items, "primary"),
                "secondary": pool(items, "secondary"),
                "strata": {
                    "by_tile_flooded_share": {
                        name: {"tiles": len(by_share[name]), **pool(by_share[name], "primary")}
                        for name in FLOODED_SHARE_STRATA
                        if name in by_share
                    },
                    "by_post_acquisition_slice": {
                        name: {"tiles": len(subset), **pool(subset, "primary")}
                        for name, subset in sorted(by_slice.items())
                    },
                    "by_cell_stratum": {
                        name: metrics_from_counts(
                            sum_counts(item["cell_strata"][name] for item in items)
                        )
                        for name in items[0]["cell_strata"]
                    },
                },
            }
    return results
