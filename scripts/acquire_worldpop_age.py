"""Acquire exact-year Thailand WorldPop age-count rasters into a new external run."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

AGE_BANDS = ("00", "01", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55",
             "60", "65", "70", "75", "80", "85", "90")
SOURCE_BASE = "https://data.worldpop.org/GIS/AgeSex_structures/Global_2015_2030/R2025A"
CATALOG_URL = "https://hub.worldpop.org/geodata/listing?id=103"
CATALOG_1KM_URL = "https://hub.worldpop.org/geodata/listing?id=142"
RELEASE_URL = "https://data.worldpop.org/repo/prj/Global_2015_2030/R2025A/doc/Global2_Release_Statement_R2025A_v1.pdf"


def _url(year: int, band: str, resolution: str) -> str:
    if resolution == "100m":
        return f"{SOURCE_BASE}/{year}/THA/v1/100m/constrained/tha_t_{band}_{year}_CN_100m_R2025A_v1.tif"
    if resolution == "1km":
        return f"{SOURCE_BASE}/{year}/THA/v1/1km_ua/constrained/tha_t_{band}_{year}_CN_1km_R2025A_UA_v1.tif"
    raise ValueError("Unsupported WorldPop resolution")


def _fetch(year: int, band: str, resolution: str, root: Path, expected_bytes: int) -> dict[str, object]:
    url = _url(year, band, resolution)
    path = root / url.rsplit("/", 1)[-1]
    partial = path.with_suffix(".part")
    if path.exists():
        if not path.is_file() or path.stat().st_size != expected_bytes:
            raise ValueError(f"Existing age source is not the expected size: {path.name}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"band": band, "file": path.name, "url": url, "bytes": expected_bytes,
                "sha256": digest.hexdigest(), "retrieved_at_utc": datetime.fromtimestamp(
                    path.stat().st_mtime, timezone.utc).isoformat(),
                "reverified_at_utc": datetime.now(timezone.utc).isoformat()}
    if partial.exists():
        partial.unlink()
    error = ""
    for attempt in (1, 2):
        try:
            digest = hashlib.sha256()
            count = 0
            started = time.monotonic()
            max_seconds = max(300.0, expected_bytes / 102400.0)
            with requests.get(url, stream=True, timeout=(15, 30)) as response:
                response.raise_for_status()
                if response.headers.get("Content-Type", "").split(";")[0].lower() not in {"image/tiff", "application/octet-stream"}:
                    raise ValueError("Unexpected source content type")
                with partial.open("xb") as target:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            target.write(chunk)
                            digest.update(chunk)
                            count += len(chunk)
                            if time.monotonic() - started > max_seconds:
                                raise TimeoutError("Bounded source transfer exceeded wall-clock limit")
            if count != expected_bytes:
                raise ValueError(f"Source byte count changed: {count} versus {expected_bytes}")
            partial.replace(path)
            return {"band": band, "file": path.name, "url": url, "bytes": count,
                    "sha256": digest.hexdigest(), "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        except (requests.RequestException, OSError, ValueError, TimeoutError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            if partial.exists():
                partial.unlink()
    return {"band": band, "file": path.name, "url": url, "status": "failed", "error": error}


def acquire(year: int, output: Path, *, resolution: str = "100m",
            resume_incomplete: bool = False, workers: int = 2) -> dict[str, object]:
    """Fetch all mutually exclusive age bands after source and disk preflight."""
    if year not in {2024, 2025}:
        raise ValueError("This acquisition is scoped to the two project event years")
    if resolution not in {"100m", "1km"}:
        raise ValueError("Unsupported WorldPop resolution")
    if workers not in (1, 2, 3, 4):
        raise ValueError("Workers must be between one and four")
    previous_attempt_sha256 = None
    old_manifest = output / "acquisition_manifest.json"
    if output.exists():
        if not resume_incomplete:
            raise ValueError("Output run exists; only an incomplete run may be resumed explicitly")
        if old_manifest.exists():
            old_bytes = old_manifest.read_bytes()
            previous = json.loads(old_bytes)
            if (previous.get("status") != "PARTIAL"
                    or previous.get("year_represented") != year
                    or previous.get("resolution_code") != resolution):
                raise ValueError("Only a matching partial acquisition may be resumed")
            previous_attempt_sha256 = hashlib.sha256(old_bytes).hexdigest()
            archive = output / f"acquisition_manifest.attempt-{previous_attempt_sha256[:12]}.json"
            if not archive.exists():
                archive.write_bytes(old_bytes)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_sizes: dict[str, int] = {}
    for band in AGE_BANDS:
        for attempt in (1, 2):
            try:
                response = requests.head(_url(year, band, resolution), timeout=(20, 30), allow_redirects=True)
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
        content_length = response.headers.get("Content-Length", "")
        if not content_length.isdecimal() or int(content_length) < 1024:
            raise ValueError(f"Missing or implausible source size for band {band}")
        source_sizes[band] = int(content_length)
    expected_total = sum(source_sizes.values())
    free = shutil.disk_usage(output.parent).free
    if free < expected_total * 2:
        raise ValueError(f"Insufficient disk: {free} free bytes for {expected_total} source bytes")
    output.mkdir(parents=True, exist_ok=resume_incomplete)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch, year, band, resolution, output, source_sizes[band]): band for band in AGE_BANDS}
        files = [future.result() for future in concurrent.futures.as_completed(futures)]
    files.sort(key=lambda item: AGE_BANDS.index(str(item["band"])))
    manifest = {
        "schema_version": "floodguard.worldpop_age_acquisition.v1",
        "provider": "WorldPop, University of Southampton",
        "product": "Global2 R2025A v1, Thailand constrained total-sex age estimates",
        "year_represented": year,
        "publication_date": "2025-09-01",
        "resolution_code": resolution,
        "resolution": ("3 arc seconds, approximately 100 m at equator; WGS84"
                       if resolution == "100m" else
                       "30 arc seconds, approximately 1 km at equator; WGS84; 1km_ua source"),
        "units": "estimated people per grid cell",
        "catalog_url": CATALOG_URL if resolution == "100m" else CATALOG_1KM_URL,
        "product_detail_url": (
            f"https://hub.worldpop.org/geodata/summary?id={98910 if year == 2024 else 98911}"
            if resolution == "1km" else None
        ),
        "release_statement_url": RELEASE_URL,
        "rights": "Public catalog says CC BY 4.0; ODbL may apply to OSM/building-derived datasets. Public derivatives require purpose-specific review.",
        "expected_total_bytes": expected_total,
        "previous_attempt_sha256": previous_attempt_sha256,
        "status": "PASS" if all("sha256" in item for item in files) else "PARTIAL",
        "files": files,
    }
    with old_manifest.open("w" if previous_attempt_sha256 else "x", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, indent=2)
        target.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--resolution", choices=("100m", "1km"), default="100m")
    parser.add_argument("--resume-incomplete", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = acquire(args.year, args.output, resolution=args.resolution,
                     resume_incomplete=args.resume_incomplete, workers=args.workers)
    print(json.dumps({"year": args.year, "status": result["status"],
                      "files": len(result["files"]), "expected_total_bytes": result["expected_total_bytes"]}))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
