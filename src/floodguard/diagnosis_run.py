"""Receipts of the diagnosis runs of plan task A1 (restructuring plan v2, section 4.2 and row 8.1 A1).

Plan row 8.1 A1 accepts the diagnosis when "every number [is] traced". Protocol v1b says that every run is
reported. So each script under ``scripts/diagnostics/`` makes one run of one figure, and this module writes
what that run leaves behind:

* a **figures file** under ``outputs/a1_diagnosis/``: the numbers, what they are measured against, their
  limits and the points the signed files leave open;
* a **run receipt** under ``outputs/planning_v1/``: the inputs with their SHA-256, the parameters, the
  SHA-256 of both protocol files, the run times, the figures file with its SHA-256 and every earlier run;
* one **register entry** under ``outputs/planning_v1/run_register/``: the path and SHA-256 of the receipt.

A second run of a figure needs ``replace``, a reason and the external data root: the superseded receipt and
figures file are copied under that root before they are overwritten. The new receipt names the receipt and
the figures file it supersedes by SHA-256 and says whether the figures are the same. A run is refused unless
both protocol files are in force. A receipt names the script and the shared modules the run loaded by
SHA-256, and the versions of the libraries it had loaded; :func:`verify` compares both with the checkout.
Nothing here computes an FPPS, an A-E class or a flood candidate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from floodguard import normalisation

FIGURES_SCHEMA = "floodguard.a1_diagnosis_figures.v1"
RECEIPT_SCHEMA = "floodguard.a1_diagnosis_run_receipt.v1"
PLAN_TASK = "A1 (abstention diagnosis: why threshold-only change detection failed at the 16 Sep pass)"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
EXTERNAL_LABEL = "<external_data_workspace>"
DOCS = Path("docs") / "proposal_execution"
FIGURES_DIR = Path("outputs") / "a1_diagnosis"
RECEIPT_DIR = Path("outputs") / "planning_v1"
REGISTER_DIR = RECEIPT_DIR / "run_register"
RECEIPT_PREFIX = "a1_diagnosis_"
SUPERSEDED_RELATIVE_PATH = Path("proposal_execution") / "planning_v1" / "a1_diagnosis" / "superseded_runs"
RESULT_DOCUMENT = "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md"

ENVELOPE_LABEL = "vs a season envelope, not an event map"
"""The label plan row A1 gives every figure measured against the product 4009 accumulated layer."""

MODULES = (
    "src/floodguard/abstention_diagnosis.py",
    "src/floodguard/diagnosis_run.py",
    "src/floodguard/diagnosis_layers.py",
)
"""The modules every diagnosis script loads; a receipt names each by SHA-256."""


OPEN_POINTS: Mapping[str, Mapping[str, str]] = {
    "A1-OP1": {
        "point": "Which terrain feature the plan means by 'terrain AUC vs 4009'.",
        "signed_files_say": "Plan row A1: 'terrain AUC vs 4009 (to compute)'. No feature, no grid and no domain is named. "
                            "Protocol v1a announces a HAND and slope mask for M1-v2 on Mae Sai without a HAND source or a "
                            "limit (open point A4-OP2).",
        "what_was_done": "Two features of the Copernicus GLO-30 surface model were measured on the 20 m grid: low elevation "
                         "and low slope. They were taken from the exploratory script of the plan session, which was never "
                         "committed: it ranked the negated height and the negated slope against the same layer and printed "
                         "both values on the line that gave 0.421. Those two values are in no committed file, so this is the "
                         "first computation from cleared files and the first recorded value; it is not the first time the "
                         "figure was seen. HAND was not computed: no HAND raster and no drainage rule is in the signed files "
                         "or on disk. Neither figure is named the terrain figure of the plan.",
    },
    "A1-OP2": {
        "point": "The definition behind the plan's figure 0.421 (darkening of VH against the season envelope).",
        "signed_files_say": "Plan row A1 and disclosure item EK-07 of protocol v1a give the figure and no definition. The "
                            "exploratory script that produced it was never committed.",
        "what_was_done": "The definition of the exploratory script was rebuilt from cleared files: 20 m cells, a 5 by 5 mean, "
                         "VH before minus VH after in dB, the cells of AOI-01 on the Thai side outside JRC surface water. Two "
                         "things differ and are stated: the radar values are calibrated sigma0 (the exploratory run used "
                         "uncalibrated amplitudes), and the Thai side is taken from the COD-AB boundaries (the exploratory run "
                         "used the product's analysis extent, which is held at the local level and is not read here). The "
                         "5 by 5 mean is the window of that script; neither the plan nor a protocol names a window, so the "
                         "figure is also given for windows of 1, 3, 9, 15 and 25 cells, and no window is named the window of "
                         "record. The script ranked seven features against the same layer on one printed line: the darkening "
                         "of VH, the same change read as brightening, the absolute change of VH and of VV, the negated VH "
                         "after the event, the negated height and the negated slope. Only 0.421 was carried into the plan. "
                         "The reading 'auc_of_brightening' here is the second of those features; the absolute changes and "
                         "the VH after the event are not computed here, because the plan does not list them.",
    },
    "A1-OP3": {
        "point": "Which geocoding of the radar layers a figure against a mapped layer uses.",
        "signed_files_say": "Plan row A4 gives the fallback geocoding of the run of record. The A2/A4 result measured that it "
                            "displaces the radar content by about 680 m and leaves the two dates about 9 m apart (open point "
                            "A4-OP1). The owners have not decided which layers case O1 uses.",
        "what_was_done": "The figure is given under both geocodings: the run of record and the sensitivity run. Neither is "
                         "named the figure of record.",
    },
    "A1-OP4": {
        "point": "Which permanent water a diagnosis leaves out.",
        "signed_files_say": "Protocol v1a names ESA WorldCover 2021 class 80 for the flood-likelihood component, in every case. "
                            "It says nothing of a diagnosis. The exploratory run used JRC Global Surface Water (seasonality of "
                            "10 months or more, or occurrence of 80 percent or more).",
        "what_was_done": "Every figure is given three ways: JRC water left out, WorldCover class 80 left out, and nothing left out.",
    },
    "A1-OP5": {
        "point": "The rights record of the Sentinel-1 data behind a committed figure.",
        "signed_files_say": "No signed rights record covers Sentinel-1 data (open point E1-OP2), and the acquisition manifest of "
                            "July marks both SAFE files 'do not run baseline yet' (open point A4-OP5). Plan row A1 lists figures "
                            "made from them as team-owned or cleared.",
        "what_was_done": "The stored sigma0 rasters of tasks A2 and A4 were read, and statistics for the whole area are "
                         "committed with the Copernicus attribution, as the A2/A4 tables are. No radar layer is written.",
    },
    "A1-OP6": {
        "point": "Whether the product 4009 rights record covers a diagnosis comparison.",
        "signed_files_say": "The record lists its uses (use_in_this_track): the comparison with the replay model is the only "
                            "comparison it names, and its limitations say it does not cover use as machine-learning labels or "
                            "as a qualified reference. Plan row A1 allows these figures 'after the 4009 signature'.",
        "what_was_done": "The accumulated layer is used as a comparison layer only: no model was fitted to it and nothing is "
                         "called a reference. Every figure carries the licence, the credit, a change notice and the label "
                         "'vs a season envelope, not an event map'.",
    },
    "A1-OP7": {
        "point": "What a recorded grant receipt for the AIT or MBRSC product is, and what the guard does with the code that "
                 "named the two products before the guard existed.",
        "signed_files_say": "Guardrail GR9: 'without a recorded grant receipt'. Neither its form nor its place is given. The "
                            "plan keeps the earlier AIT inspection code unchanged.",
        "what_was_done": "The guard reads the rights registry: a product is granted when a registered record of its source is "
                         "confirmed by the owners and signed by a human. None exists. The code files that named a product "
                         "before the guard are listed in a baseline with the SHA-256 of the naming lines. Read word for word, "
                         "the guardrail would fail on them.",
    },
    "A1-OP8": {
        "point": "How far 'no AIT or MBRSC number' can be checked.",
        "signed_files_say": "Guardrail GR9: no such number in committed code or on any public surface.",
        "what_was_done": "The guard refuses a figure beside either name in the files of this task. It cannot tell which number "
                         "elsewhere was derived from the two products. Files committed before the plan name the AIT product as "
                         "a blocked reference record, the public offline bundle among them. None of them was changed here.",
    },
    "A1-OP9": {
        "point": "The older diagnosis scripts.",
        "signed_files_say": "Plan row A1: 'scripts moved to scripts/diagnostics/'. The exploratory scripts of the plan session "
                            "were never committed. Four older committed diagnosis scripts (scripts/diagnose_*.py) are named by "
                            "documents and tests.",
        "what_was_done": "New scripts were written under scripts/diagnostics/ that read cleared files only. No committed "
                         "script was moved.",
    },
    "A1-OP10": {
        "point": "On which cells a rank statistic against the season envelope is taken.",
        "signed_files_say": "Plan row A1 names no domain. Plan row A2 removes slopes of 5 degrees or more from the UN-SPIDER "
                            "practice, the A2/A4 result reports its areas by that slope class, and the exploratory script looked "
                            "at the cells under 5 degrees as well. Protocol v1a announces a HAND and slope mask for M1-v2 and "
                            "gives no limit (open point A4-OP2).",
        "what_was_done": "Each rank statistic is given on two sets of cells: every cell of AOI-01 on the Thai side, and the "
                         "cells of that set whose GLO-30 slope is under 5 degrees. On the first set a terrain feature mostly "
                         "tells hill from plain. Neither set is named the domain of record.",
    },
    "A1-OP11": {
        "point": "How far the reading of a product path can be checked, and when the check runs.",
        "signed_files_say": "Guardrail GR9 asks for a pre-commit test that fails when a committed script reads the paths of "
                            "either ungranted product without a recorded grant receipt. Its enforcement note asks for a "
                            "pre-commit or CI test and names no mechanism.",
        "what_was_done": "The guard reads the text of code files and runs in the test suite and as a command; the repository "
                         "installs no Git hook. It does not see a path that is read from a JSON or CSV manifest, a name that "
                         "is split across strings, or new code inside an existing function of a legacy file.",
    },
}
"""The points the signed files leave open for plan task A1. None is decided by the code."""


DEVELOPMENT_READS: tuple[str, ...] = (
    "4 October 2026, about 18:00 to 20:25 UTC, while the scripts were written and before any run: the headers of the stored sigma0, slope and "
    "land-cover rasters of tasks A2 and A4, of the GLO-30 tile and of the two JRC tiles were read (size, grid, bands, "
    "tags); the receipt of the retired M2 run was read for its keys and its grid, with the header of its mask; AOI-01 "
    "and the two radar receipts were read. No cell value was read and no figure was computed.",
    "The same evening, before any run: the statistics module was tried on invented numbers only (random draws; no file "
    "of the external data workspace was opened).",
    "5 October 2026, after the review of the first runs and before the superseding runs: the committed figures files and "
    "receipts were read; the eight superseded copies kept outside Git were read for their run times and their SHA-256; the "
    "text of five exploratory scripts of the plan session was read, to check what they had computed and that the guard "
    "refuses such text. None of them was run. No raster and no flood layer was opened, no cell value was read and no "
    "figure was computed.",
)
"""The reads made on real files before the first runs. A receipt of a figure that rests on those files lists them."""


def open_points(*identifiers: str) -> list[dict[str, str]]:
    """Return the named open points as the figures files and the receipts carry them."""

    return [{"id": identifier, **OPEN_POINTS[identifier]} for identifier in identifiers]


class DiagnosisRunError(RuntimeError):
    """Raised when a diagnosis run is refused or cannot be written."""


@dataclass(frozen=True)
class FigureSpec:
    """What one diagnosis figure is: the same for every run of it."""

    figure_id: str
    title: str
    script: str
    plan_statement: str
    computes: str
    does_not_show: tuple[str, ...]
    label: str | None = None

    @property
    def figures_path(self) -> Path:
        """Repository path of the figures file."""

        return FIGURES_DIR / f"{self.figure_id}.json"

    @property
    def receipt_path(self) -> Path:
        """Repository path of the run receipt."""

        return RECEIPT_DIR / f"{RECEIPT_PREFIX}{self.figure_id}.json"

    @property
    def register_path(self) -> Path:
        """Repository path of the register entry of the receipt."""

        return REGISTER_DIR / f"{RECEIPT_PREFIX}{self.figure_id}.json"


@dataclass(frozen=True)
class FigureResult:
    """What one run of a figure measured, and from what."""

    figures: Mapping[str, Any]
    inputs: Mapping[str, Any]
    parameters: Mapping[str, Any]
    source_timestamp: str
    confidence_basis: str
    assumptions: Sequence[str]
    limits: Sequence[str]
    plan_figure: Mapping[str, Any]
    open_points: Sequence[Mapping[str, str]] = ()
    not_computed: Sequence[str] = ()
    licence: Mapping[str, Any] | None = None
    rights: Mapping[str, Any] | None = None
    attributions: Sequence[str] = ()
    development_reads: Sequence[str] = field(default_factory=tuple)


def utc_now() -> str:
    """Return the current UTC time to the second, as the receipts write it."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 of some bytes."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    """Return the SHA-256 of a file, read in blocks."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode(payload: Mapping[str, Any]) -> bytes:
    """Serialise a figures file or a receipt: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def path_label(path: Path | str, root: Path, external: Path | None) -> str:
    """Name a file without a machine path: relative to the repository, or to the external data root."""

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        pass
    if external is not None:
        try:
            return f"{EXTERNAL_LABEL}/{resolved.relative_to(external.resolve()).as_posix()}"
        except ValueError:
            pass
    return resolved.name


def file_record(path: Path | str, root: Path, external: Path | None, **what: Any) -> dict[str, Any]:
    """Return the label, the SHA-256 and the size of an input file, with anything else said about it."""

    target = Path(path)
    return {"path": path_label(target, root, external), "sha256": sha256_file(target), "bytes": target.stat().st_size, **what}


def protocols_in_force(root: Path) -> dict[str, str]:
    """Return the SHA-256 of both protocol files, or refuse when one is not in force.

    Raises:
        floodguard.normalisation.NormalisationError: when a file is not signed or its hash is not recorded.
    """

    receipts = root / DOCS / "RECEIPTS.jsonl"
    return {
        f"planning_protocol_{name}": normalisation.read_protocol_in_force(name, root / DOCS / f"planning_protocol_{name}.json", receipts)[1]
        for name in normalisation.PROTOCOL_NAMES
    }


def base_commit(root: Path) -> str | None:
    """Return the commit the working tree is on, or None outside a Git checkout."""

    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip() or None


LIBRARIES: tuple[str, ...] = ("numpy", "scipy", "rasterio", "pyproj", "shapely", "pyogrio", "geopandas", "pandas")
"""The libraries whose version can move a figure in its last decimals: the number generator, the warps and the geometry."""


def software_versions() -> dict[str, str]:
    """Return the Python version and the version of each library of :data:`LIBRARIES` the process has loaded.

    A library that the run did not load is not imported here and is not listed. GDAL, PROJ and GEOS are listed
    with the package that carries them.
    """

    versions = {"python": platform.python_version()}
    for name in LIBRARIES:
        module = sys.modules.get(name)
        if module is None:
            continue
        versions[name] = str(getattr(module, "__version__", "unknown"))
        if name == "rasterio":
            versions["gdal"] = str(getattr(module, "__gdal_version__", "unknown"))
        elif name == "pyproj":
            versions["proj"] = str(getattr(module, "proj_version_str", "unknown"))
        elif name == "shapely":
            versions["geos"] = str(getattr(module, "geos_version_string", "unknown"))
    return versions


def code_files(spec: FigureSpec, root: Path) -> dict[str, str]:
    """Return the SHA-256 of the script of a figure and of the shared modules, as they are on disk."""

    return {name: sha256_file(root / name) for name in (spec.script, *MODULES) if (root / name).is_file()}


def implementation(spec: FigureSpec, root: Path) -> dict[str, Any]:
    """Name the code a run loaded: the script and the shared modules by SHA-256, the commit beneath them and the
    versions of the libraries the run had loaded."""

    return {
        "base_commit": base_commit(root),
        "base_commit_note": "The commit the working tree was on. The files below are the ones this run loaded, "
                            "identified by their own SHA-256, committed or not.",
        "files_sha256": code_files(spec, root),
        "software": software_versions(),
        "software_note": "The libraries the run had loaded when it finished. A figure can move in its last decimals "
                         "under another version of GDAL, PROJ, GEOS or numpy; --verify reports the versions beside "
                         "the comparison.",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes().decode("ascii"))


def _earlier_runs(previous: Mapping[str, Any], previous_sha256: str, reason: str) -> list[dict[str, Any]]:
    """Carry the history of a superseded receipt forward and add that receipt to it."""

    history = list(previous.get("run_history", {}).get("earlier_runs", []))
    times = previous.get("timestamps", {})
    history.append({
        "generated_at_utc": previous["generated_at_utc"],
        "run_started_at_utc": times.get("run_started_at_utc"),
        "run_finished_at_utc": times.get("run_finished_at_utc"),
        "receipt_sha256": previous_sha256,
        "figures_sha256": previous["outputs"]["figures"]["sha256"],
        "run_kind": previous.get("run_kind"),
        "superseded_because": reason,
    })
    return history


def assemble(spec: FigureSpec, result: FigureResult, *, root: Path, generated_at_utc: str, started_at_utc: str,
             finished_at_utc: str, protocol_sha256: Mapping[str, str], supersedes: Mapping[str, Any] | None,
             earlier_runs: Sequence[Mapping[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """Build the bytes of the figures file and the receipt that binds them."""

    common = {
        "generated_at_utc": generated_at_utc,
        "plan_task": PLAN_TASK,
        "figure_id": spec.figure_id,
        "title": spec.title,
        "official_warning": False,
        "operational_status": "non_operational",
        "source_timestamp": result.source_timestamp,
        "confidence_class": "low",
        "confidence_basis": result.confidence_basis,
        "assumptions": list(result.assumptions),
        "protocol_sha256": dict(protocol_sha256),
    }
    figures_document = {
        "schema_version": FIGURES_SCHEMA,
        **common,
        "status": "diagnosis_figures",
        "status_note": "Figures of one diagnosis run, written with protocol v1a and v1b in force. A diagnosis figure "
                       "describes why a method declined or separated poorly; it is not a flood map, not an observation "
                       "of a flood and not a measure of how correct a method is. No FPPS, A-E class or flood candidate is here.",
        "receipt_file": spec.receipt_path.as_posix(),
        "result_document": RESULT_DOCUMENT,
        "script": spec.script,
        "plan_statement": spec.plan_statement,
        "measured_against": spec.label,
        "computes": spec.computes,
        "figures": dict(result.figures),
        "plan_figure": dict(result.plan_figure),
        "does_not_show": list(spec.does_not_show),
        "limits": list(result.limits),
        "licence": None if result.licence is None else dict(result.licence),
        "attributions": list(result.attributions),
        "open_points": [dict(point) for point in result.open_points],
        "not_computed": list(result.not_computed),
    }
    figures_bytes = encode(figures_document)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        **common,
        "run": spec.title,
        "status": "run_receipt",
        "status_note": "Receipt of one diagnosis run, made with protocol v1a and v1b in force. Every run is reported: "
                       "a second run of this figure writes a new receipt that names this one.",
        "run_kind": "first_run" if supersedes is None else "superseding_run",
        "computes": spec.computes,
        # A receipt can be read or shared alone, so it carries the label and the licence block of its figures.
        "measured_against": spec.label,
        "licence": None if result.licence is None else dict(result.licence),
        "attributions": list(result.attributions),
        "protocol_state": {"v1a": "in_force", "v1b": "in_force"},
        "script": {"path": spec.script, "sha256": sha256_file(root / spec.script)},
        "implementation": implementation(spec, root),
        "parameters": dict(result.parameters),
        "inputs": dict(result.inputs),
        "rights": None if result.rights is None else dict(result.rights),
        "timestamps": {"run_started_at_utc": started_at_utc, "run_finished_at_utc": finished_at_utc},
        "outputs": {"figures": {"path": spec.figures_path.as_posix(), "sha256": sha256_bytes(figures_bytes),
                                "bytes": len(figures_bytes)}},
        "supersedes": None if supersedes is None else dict(supersedes),
        "run_history": {
            "rule": "Protocol v1b, change_control: every run is reported. Each earlier run of this figure is listed "
                    "with the SHA-256 of its receipt and of its figures file.",
            "earlier_runs": [dict(run) for run in earlier_runs],
        },
        "development_reads": list(result.development_reads),
        "open_points": [dict(point) for point in result.open_points],
        "not_computed": list(result.not_computed),
    }
    return figures_bytes, receipt


def run(spec: FigureSpec, compute: Callable[[], FigureResult], *, root: Path, external: Path | None = None,
        replace: bool = False, reason: str | None = None, now: Callable[[], str] = utc_now) -> dict[str, Any]:
    """Make one run of a figure and write its figures file, its receipt and its register entry.

    Args:
        spec: The figure.
        compute: Reads the inputs and returns what was measured. It is called once.
        root: The repository root.
        external: The external data root; a superseded receipt and figures file are copied under it.
        replace: Needed for a second run of the figure.
        reason: Why the earlier run is superseded; needed with ``replace``.
        now: Clock, for tests.

    Returns:
        A summary: the receipt path, its SHA-256, the figures and whether an earlier run was superseded.

    Raises:
        DiagnosisRunError: for a second run without ``replace`` and a reason, ``replace`` with nothing to replace,
            or ``replace`` without the external data root (the superseded files could not be kept).
        floodguard.normalisation.NormalisationError: when a protocol file is not in force.
    """

    protocol_sha256 = protocols_in_force(root)
    receipt_path, figures_path, register_path = (root / spec.receipt_path, root / spec.figures_path, root / spec.register_path)
    supersedes: dict[str, Any] | None = None
    earlier: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    if receipt_path.exists():
        if not replace or not (reason or "").strip():
            raise DiagnosisRunError(
                f"{spec.receipt_path.as_posix()} exists: a second run of this figure needs --replace and --reason, "
                "and its receipt will name the run it supersedes"
            )
        if external is None:
            raise DiagnosisRunError(
                f"a second run of {spec.figure_id} needs the external data root (--external-data or {EXTERNAL_DATA_VARIABLE}): "
                "the superseded receipt and figures file are copied there before they are overwritten, and without it "
                "they would be lost"
            )
        previous = _read_json(receipt_path)
        previous_sha256 = sha256_file(receipt_path)
        earlier = _earlier_runs(previous, previous_sha256, str(reason).strip())
        supersedes = {
            "receipt_sha256": previous_sha256,
            "figures_sha256": previous["outputs"]["figures"]["sha256"],
            "generated_at_utc": previous["generated_at_utc"],
            "reason": str(reason).strip(),
        }
    elif replace:
        raise DiagnosisRunError(f"--replace was given and {spec.receipt_path.as_posix()} does not exist: there is no run to supersede")

    started = now()
    result = compute()
    finished = now()
    if supersedes is not None and previous is not None:
        old_figures = _read_json(figures_path)["figures"] if figures_path.exists() else None
        supersedes["figures_same"] = old_figures == json.loads(json.dumps(dict(result.figures)))
        supersedes["copies_kept"] = _keep_superseded(spec, root, external, previous["generated_at_utc"])
        if not any(label.endswith("/" + spec.receipt_path.name) for label in supersedes["copies_kept"]):
            raise DiagnosisRunError(f"the superseded receipt of {spec.figure_id} could not be copied; nothing was overwritten")
    figures_bytes, receipt = assemble(spec, result, root=root, generated_at_utc=finished, started_at_utc=started,
                                      finished_at_utc=finished, protocol_sha256=protocol_sha256, supersedes=supersedes,
                                      earlier_runs=earlier)
    receipt_bytes = encode(receipt)
    for path, data in ((figures_path, figures_bytes), (receipt_path, receipt_bytes)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_bytes(encode({"path": spec.receipt_path.as_posix(), "sha256": sha256_bytes(receipt_bytes)}))
    return {
        "receipt": spec.receipt_path.as_posix(),
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "figures_file": spec.figures_path.as_posix(),
        "figures_sha256": sha256_bytes(figures_bytes),
        "run_kind": receipt["run_kind"],
        "figures": dict(result.figures),
    }


def _keep_superseded(spec: FigureSpec, root: Path, external: Path | None, generated_at_utc: str) -> list[str]:
    """Copy a superseded receipt and figures file under the external data root, and name the copies."""

    if external is None:
        return []
    stamp = generated_at_utc.replace("-", "").replace(":", "")
    folder = external / SUPERSEDED_RELATIVE_PATH / f"{stamp}_{spec.figure_id}"
    folder.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    for source in (root / spec.receipt_path, root / spec.figures_path):
        if source.exists():
            target = folder / source.name
            target.write_bytes(source.read_bytes())
            kept.append(path_label(target, root, external))
    return kept


def verify(spec: FigureSpec, compute: Callable[[], FigureResult], *, root: Path) -> dict[str, Any]:
    """Compute a figure again and compare it with the committed run. Nothing is written.

    Returns:
        Whether the figures, the inputs and the parameters are those of the receipt, whether the script and the
        shared modules on disk are the ones the receipt names, and whether the committed figures file and
        register entry have the bytes the receipt binds. ``software`` says whether the libraries loaded now have
        the versions the receipt records; it is reported and is not part of ``verified``, so that a difference in
        the environment can be told from a changed input or rule.

    Raises:
        DiagnosisRunError: when the figure has no run to compare with.
    """

    receipt_path = root / spec.receipt_path
    if not receipt_path.exists():
        raise DiagnosisRunError(f"{spec.receipt_path.as_posix()} does not exist: there is no run to verify")
    receipt = _read_json(receipt_path)
    figures_path = root / spec.figures_path
    committed = _read_json(figures_path)
    result = compute()
    plain = json.loads(json.dumps({"figures": dict(result.figures), "inputs": dict(result.inputs), "parameters": dict(result.parameters)}))
    register = _read_json(root / spec.register_path)
    checks = {
        "figures_same": plain["figures"] == committed["figures"],
        "inputs_same": plain["inputs"] == receipt["inputs"],
        "parameters_same": plain["parameters"] == receipt["parameters"],
        **code_checks(spec, receipt, root),
        "figures_file_is_the_one_the_receipt_binds": sha256_file(figures_path) == receipt["outputs"]["figures"]["sha256"],
        "register_entry_names_the_receipt": register == {"path": spec.receipt_path.as_posix(), "sha256": sha256_file(receipt_path)},
    }
    recorded = receipt.get("implementation", {}).get("software")
    loaded = software_versions()
    software = {
        "recorded_in_the_receipt": recorded,
        "loaded_now": loaded,
        "same": None if recorded is None else all(loaded.get(name) == version for name, version in recorded.items()),
    }
    return {"verified": all(checks.values()), **checks, "software": software, "generated_at_utc": receipt["generated_at_utc"]}


def code_checks(spec: FigureSpec, receipt: Mapping[str, Any], root: Path) -> dict[str, bool]:
    """Say whether the script and the shared modules on disk are the ones a receipt names by SHA-256.

    A receipt that names code which is no longer in the checkout does not trace its figure any more: the
    figure needs a superseding run, or the code its receipt names.
    """

    on_disk = code_files(spec, root)
    named = dict(receipt.get("implementation", {}).get("files_sha256", {}))
    return {
        "script_is_the_one_the_receipt_names": receipt.get("script") == {"path": spec.script, "sha256": on_disk.get(spec.script)},
        "code_files_are_the_ones_the_receipt_names": bool(named) and named == on_disk,
    }


def external_root(argument: Path | None, environment: Mapping[str, str]) -> Path | None:
    """Return the external data root from the argument or from ``FLOODGUARD_EXTERNAL_DATA``; None when neither is set."""

    if argument is not None:
        return Path(argument)
    value = environment.get(EXTERNAL_DATA_VARIABLE, "").strip()
    return Path(value) if value else None


def command_line(spec: FigureSpec, make_compute: Callable[[Path, Path | None], Callable[[], FigureResult]], *,
                 root: Path, description: str, needs_external_data: bool, argv: Sequence[str] | None = None) -> int:
    """Run one diagnosis script from the command line: a run, a superseding run or ``--verify``.

    Args:
        spec: The figure the script computes.
        make_compute: Given the repository root and the external data root, returns the function that
            reads the inputs and measures the figure.
        root: The repository root.
        description: The script's header, shown by ``--help``.
        needs_external_data: Whether the figure reads files outside Git.
        argv: The arguments; default: those of the process.

    Returns:
        0 after a run or a verification that found the same figures, 1 after a verification that did not,
        2 when a run is refused.
    """

    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--replace", action="store_true", help="make a second run of the figure; its receipt names the first")
    parser.add_argument("--reason", default=None, help="why the earlier run is superseded (needed with --replace)")
    parser.add_argument("--verify", action="store_true", help="compute the figure again and compare it with the committed run; writes nothing")
    args = parser.parse_args(argv)
    external = external_root(args.external_data, os.environ)
    if needs_external_data and external is None:
        parser.error(f"give --external-data or set {EXTERNAL_DATA_VARIABLE}")
    compute = make_compute(root, external)
    try:
        if args.verify:
            summary = verify(spec, compute, root=root)
            print(json.dumps(summary, indent=2))
            return 0 if summary["verified"] else 1
        summary = run(spec, compute, root=root, external=external, replace=args.replace, reason=args.reason)
    except DiagnosisRunError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0
