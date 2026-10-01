"""Input receipts and byte comparison for reproducible asset bakes.

A bake that claims to be reproducible needs two things anyone can check:

* an *input receipt*: every input file the bake opened, with its path relative
  to a named root (never a machine path), its size and its SHA-256, plus the
  library versions that produced the bytes;
* a *byte comparison* of a fresh bake against the committed files.

The helpers here are data-agnostic. ``scripts/build_mae_sai_flood_timeline.py``
uses them for the Mae Sai replay revision.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import hashlib
from importlib import metadata
from pathlib import Path
import platform
from typing import Any

RECEIPT_SCHEMA = "floodguard.bake_input_receipt.v1"

DEFAULT_LIBRARIES: tuple[str, ...] = (
    "numpy", "scipy", "rasterio", "pillow", "pyproj", "shapely", "pysheds", "numba", "pyogrio", "pandas", "affine",
)
"""Distributions whose versions can change the baked bytes."""


class ReceiptError(ValueError):
    """Raised when an input cannot be recorded without breaking the receipt contract."""


def sha256_file(path: Path | str) -> str:
    """Return the SHA-256 of the file at ``path`` as lowercase hexadecimal."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class InputReceipt:
    """Collect the input files a bake opens, relative to named roots.

    ``roots`` maps a short label (for example ``"external"`` and ``"repo"``) to
    a directory. :meth:`track` returns its argument unchanged, so it can wrap a
    path at the place the file is opened::

        with rasterio.open(receipt.track(path)) as src: ...

    A path outside every root is refused: recording it would put a machine
    path into a committed file.
    """

    def __init__(self, roots: Mapping[str, Path | str]) -> None:
        if not roots:
            raise ReceiptError("at least one root is required")
        self._roots = {label: Path(root).resolve() for label, root in roots.items()}
        self._paths: dict[tuple[str, str], Path] = {}
        self._hashes: dict[tuple[str, str], tuple[tuple[int, int], str]] = {}

    def locate(self, path: Path | str) -> tuple[str, str]:
        """Return ``(root label, POSIX path relative to that root)`` for ``path``.

        When roots nest, the innermost one wins.
        """
        resolved = Path(path).resolve()
        best: tuple[int, str, str] | None = None
        for label, root in self._roots.items():
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            depth = len(root.parts)
            if best is None or depth > best[0]:
                best = (depth, label, relative.as_posix())
        if best is None:
            raise ReceiptError(f"input lies outside the receipt roots: {resolved.name}")
        return best[1], best[2]

    def track(self, path: Path | str) -> Path | str:
        """Record ``path`` as an opened input and return it unchanged."""
        key = self.locate(path)
        self._paths.setdefault(key, Path(path).resolve())
        return path

    def tracked(self) -> list[tuple[str, str]]:
        """Return the recorded ``(root label, relative path)`` pairs, sorted."""
        return sorted(self._paths)

    def __contains__(self, path: object) -> bool:
        if not isinstance(path, (str, Path)):
            return False
        try:
            return self.locate(path) in self._paths
        except ReceiptError:
            return False

    def entries(self) -> list[dict[str, Any]]:
        """Hash every recorded input: ``root``, ``path``, ``bytes`` and ``sha256``, sorted by root and path.

        A file is hashed again only when its size or modification time changed since the last call, so a bake can
        put the hashes into its manifest and into its receipt without reading gigabytes twice.
        """
        rows = []
        for (label, relative), path in sorted(self._paths.items()):
            if not path.is_file():
                raise ReceiptError(f"recorded input is not a file: {label}:{relative}")
            stat = path.stat()
            state = (stat.st_size, stat.st_mtime_ns)
            cached = self._hashes.get((label, relative))
            if cached is None or cached[0] != state:
                cached = (state, sha256_file(path))
                self._hashes[(label, relative)] = cached
            rows.append({"root": label, "path": relative, "bytes": stat.st_size, "sha256": cached[1]})
        return rows


def sha256_text_file(path: Path | str) -> str:
    """Return the SHA-256 of a text file with CRLF read as LF, so a Windows checkout hashes like any other."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def source_hashes(paths: Iterable[Path | str], root: Path | str) -> list[dict[str, str]]:
    """Return ``path`` (POSIX, relative to ``root``) and line-ending-neutral ``sha256`` for each source file, sorted.

    A bake records the code that produced its bytes this way. A file cannot hold the hash of the commit that
    adds it, so the code is identified by content instead; ``git log -1 -- <path>`` then names the commit.
    """
    base = Path(root).resolve()
    rows = []
    for path in paths:
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(base).as_posix()
        except ValueError as exc:
            raise ReceiptError(f"source file lies outside the repository: {resolved.name}") from exc
        rows.append({"path": relative, "sha256": sha256_text_file(resolved)})
    return sorted(rows, key=lambda row: row["path"])


def source_differences(fresh: Iterable[Mapping[str, Any]], recorded: Iterable[Mapping[str, Any]]) -> list[str]:
    """Describe how the bake sources now differ from a recorded receipt (empty when they agree)."""
    fresh_rows = {row["path"]: row["sha256"] for row in fresh}
    recorded_rows = {row["path"]: row["sha256"] for row in recorded}
    notes = []
    for path in sorted(fresh_rows.keys() | recorded_rows.keys()):
        if path not in recorded_rows:
            notes.append(f"{path} is used now but is not in the recorded receipt")
        elif path not in fresh_rows:
            notes.append(f"{path} is in the recorded receipt but is not used now")
        elif fresh_rows[path] != recorded_rows[path]:
            notes.append(f"{path} changed since the recorded bake ({fresh_rows[path][:12]} now, {recorded_rows[path][:12]} recorded)")
    return notes


def library_versions(distributions: Iterable[str] = DEFAULT_LIBRARIES) -> dict[str, str | None]:
    """Return installed versions of ``distributions`` plus the native GDAL, PROJ, GEOS, WebP and zlib builds.

    A distribution that is not installed maps to ``None`` instead of raising, so
    the receipt can still be written on a slimmer environment.
    """
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for name in distributions:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    versions.update(_native_versions())
    return dict(sorted(versions.items()))


def _native_versions() -> dict[str, str | None]:
    native: dict[str, str | None] = {}
    try:
        import rasterio

        native["gdal (rasterio)"] = str(rasterio.__gdal_version__)
        native["proj (rasterio)"] = str(getattr(rasterio, "__proj_version__", None))
        native["geos (rasterio)"] = str(getattr(rasterio, "__geos_version__", None))
    except Exception:  # pragma: no cover - optional dependency
        native["gdal (rasterio)"] = None
    try:
        import pyproj

        native["proj (pyproj)"] = str(pyproj.proj_version_str)
    except Exception:  # pragma: no cover - optional dependency
        native["proj (pyproj)"] = None
    try:
        import shapely

        native["geos (shapely)"] = str(shapely.geos_version_string)
    except Exception:  # pragma: no cover - optional dependency
        native["geos (shapely)"] = None
    try:
        import pyogrio

        native["gdal (pyogrio)"] = str(pyogrio.__gdal_version_string__)
    except Exception:  # pragma: no cover - optional dependency
        native["gdal (pyogrio)"] = None
    try:
        from PIL import features

        native["webp (pillow)"] = features.version("webp")
        native["zlib (pillow)"] = features.version("zlib")
    except Exception:  # pragma: no cover - optional dependency
        native["webp (pillow)"] = None
    return native


def directory_listing(folder: Path | str) -> list[dict[str, Any]]:
    """Return ``name``, ``bytes`` and ``sha256`` for every file under ``folder`` (POSIX relative names, sorted)."""
    root = Path(folder)
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append({"name": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


@dataclass(frozen=True)
class DirectoryComparison:
    """Result of comparing a fresh bake with the committed folder, file by file."""

    identical: list[str] = field(default_factory=list)
    different: list[str] = field(default_factory=list)
    missing_from_fresh: list[str] = field(default_factory=list)
    """Committed files the fresh bake did not write."""
    extra_in_fresh: list[str] = field(default_factory=list)
    """Fresh files that are not committed."""

    @property
    def committed_count(self) -> int:
        return len(self.identical) + len(self.different) + len(self.missing_from_fresh)

    @property
    def matches(self) -> bool:
        """True only when both folders hold the same file names with identical bytes."""
        return self.committed_count > 0 and not (self.different or self.missing_from_fresh or self.extra_in_fresh)

    def summary(self) -> str:
        return f"{len(self.identical)}/{self.committed_count} identical"


def compare_directories(fresh: Path | str, committed: Path | str) -> DirectoryComparison:
    """Byte-compare every file of ``fresh`` and ``committed``; neither folder is written to."""
    fresh_root, committed_root = Path(fresh), Path(committed)
    fresh_files = {p.relative_to(fresh_root).as_posix(): p for p in fresh_root.rglob("*") if p.is_file()}
    committed_files = {p.relative_to(committed_root).as_posix(): p for p in committed_root.rglob("*") if p.is_file()}
    identical, different = [], []
    for name in sorted(fresh_files.keys() & committed_files.keys()):
        same = fresh_files[name].stat().st_size == committed_files[name].stat().st_size and \
            fresh_files[name].read_bytes() == committed_files[name].read_bytes()
        (identical if same else different).append(name)
    return DirectoryComparison(
        identical=identical,
        different=different,
        missing_from_fresh=sorted(committed_files.keys() - fresh_files.keys()),
        extra_in_fresh=sorted(fresh_files.keys() - committed_files.keys()),
    )


def input_differences(fresh: Iterable[Mapping[str, Any]], recorded: Iterable[Mapping[str, Any]]) -> list[str]:
    """Describe how the inputs of a fresh bake differ from a recorded receipt (empty when they agree)."""
    key = lambda row: (row["root"], row["path"])  # noqa: E731
    fresh_rows = {key(row): row for row in fresh}
    recorded_rows = {key(row): row for row in recorded}
    notes = []
    for item in sorted(fresh_rows.keys() | recorded_rows.keys()):
        label = f"{item[0]}:{item[1]}"
        if item not in recorded_rows:
            notes.append(f"{label} was opened now but is not in the recorded receipt")
        elif item not in fresh_rows:
            notes.append(f"{label} is in the recorded receipt but was not opened now")
        elif fresh_rows[item]["sha256"] != recorded_rows[item]["sha256"]:
            notes.append(f"{label} has different bytes ({fresh_rows[item]['sha256'][:12]} now, {recorded_rows[item]['sha256'][:12]} recorded)")
    return notes


def version_differences(fresh: Mapping[str, Any], recorded: Mapping[str, Any]) -> list[str]:
    """Describe library versions that differ between a fresh bake and a recorded receipt."""
    return [f"{name}: {fresh.get(name)} now, {recorded.get(name)} recorded"
            for name in sorted(fresh.keys() | recorded.keys()) if fresh.get(name) != recorded.get(name)]
