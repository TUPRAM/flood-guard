"""Acquire exact Mae Sai Sentinel-2 L2A COG assets anonymously from Earth Search.

The full COGs stay in the external data workspace. Only a small, per-asset
manifest of source URLs, byte counts, and SHA-256 digests belongs in Git.
Interrupted transfers resume with HTTP Range and keep their partial files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
EXTERNAL_DIR = Path.home() / "Documents" / "FloodGuard_external_data" / "earth_search" / "mae_sai_2024"
MANIFEST = Path(__file__).resolve().parents[1] / "outputs" / "earth_search_mae_sai_sentinel2_reference_assets.csv"
SCENES = {
    "event": (
        "S2B_47QNC_20240915_0_L2A",
        "S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143.SAFE",
    ),
    "dry": (
        "S2B_47QNC_20240905_0_L2A",
        "S2B_MSIL2A_20240905T034539_N0511_R104_T47QNC_20240905T080012.SAFE",
    ),
}
ASSETS = ("blue", "green", "red", "nir", "nir08", "swir16", "swir22", "scl")
COLUMNS = (
    "scene_role", "item_id", "product_uri", "asset", "asset_url",
    "local_path_hint", "file_size_bytes", "sha256", "source_edition",
    "original_safe_sha256", "acquired_at_utc", "etag",
)


def _urlopen(url: str, *, method: str = "GET", headers: dict[str, str] | None = None):
    request = Request(url, method=method, headers=headers or {})
    return urlopen(request, timeout=90)


def _item(item_id: str, expected_product_uri: str) -> dict[str, Any]:
    url = f"{EARTH_SEARCH}/collections/sentinel-2-l2a/items/{item_id}"
    with _urlopen(url) as response:
        item = json.load(response)
    if item.get("id") != item_id:
        raise ValueError(f"Earth Search returned the wrong item for {item_id}.")
    if item.get("properties", {}).get("s2:product_uri") != expected_product_uri:
        raise ValueError(f"Earth Search product URI differs from {expected_product_uri}.")
    for asset_name in ASSETS:
        asset = item.get("assets", {}).get(asset_name)
        if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
            raise TypeError(f"{item_id} lacks a valid asset {asset_name}.")
        media_type = asset.get("type", "")
        if not isinstance(media_type, str) or not media_type.startswith("image/tiff") or "profile=cloud-optimized" not in media_type:
            raise ValueError(f"{item_id} asset {asset_name} is not a TIFF COG.")
    return item


def _head(url: str) -> tuple[int, str]:
    with _urlopen(url, method="HEAD") as response:
        size = int(response.headers.get("Content-Length", "0"))
        if size <= 0 or response.headers.get("Accept-Ranges", "").lower() != "bytes":
            raise ValueError(f"COG does not advertise a positive size and HTTP Range: {url}")
        return size, response.headers.get("ETag", "")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, expected_size: int, *, attempts: int = 8) -> None:
    if target.exists():
        if target.stat().st_size != expected_size:
            raise ValueError(f"Existing COG has an unexpected size: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, attempts + 1):
        have = partial.stat().st_size if partial.exists() else 0
        if have > expected_size:
            raise ValueError(f"Partial COG exceeds the source size: {partial}")
        if have == expected_size:
            partial.replace(target)
            return
        try:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with _urlopen(url, headers=headers) as response:
                status = response.status
                if have and status == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {have}-"):
                        raise ValueError(f"Unexpected Content-Range for {partial}: {content_range}")
                    mode = "ab"
                elif status == 200:
                    mode = "wb"  # Server ignored Range; restart this file safely.
                else:
                    raise ValueError(f"Unexpected HTTP status {status} for {url}")
                with partial.open(mode) as output:
                    while chunk := response.read(4 * 1024 * 1024):
                        output.write(chunk)
            have = partial.stat().st_size
            if have == expected_size:
                partial.replace(target)
                return
            if have > expected_size:
                raise ValueError(f"Downloaded COG exceeds the source size: {partial}")
            print(f"  short read: {have}/{expected_size} bytes; resuming", flush=True)
        except (OSError, URLError, HTTPException) as exc:
            print(f"  attempt {attempt}/{attempts} interrupted: {type(exc).__name__}; resuming", flush=True)
        if attempt < attempts:
            time.sleep(min(attempt * 2, 15))
    raise RuntimeError(f"COG download incomplete after {attempts} attempts: {target.name}")


def _existing_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if any(set(row) != set(COLUMNS) for row in rows):
        raise ValueError(f"Existing manifest schema differs: {path}")
    return {(row["item_id"], row["asset"]): row for row in rows}


def _write_manifest(path: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))
    os.replace(temporary, path)


def _acquire_asset(
    role: str,
    item_id: str,
    product_uri: str,
    asset_name: str,
    url: str,
    external_dir: Path,
) -> dict[str, str]:
    size, etag = _head(url)
    target = external_dir / item_id / f"{asset_name}.tif"
    print(f"  downloading {role}/{asset_name}: {size} bytes", flush=True)
    _download(url, target, size)
    digest = _sha256(target)
    return {
        "scene_role": role,
        "item_id": item_id,
        "product_uri": product_uri,
        "asset": asset_name,
        "asset_url": url,
        "local_path_hint": f"<external_data_workspace>/earth_search/mae_sai_2024/{item_id}/{asset_name}.tif",
        "file_size_bytes": str(size),
        "sha256": digest,
        "source_edition": "element84_cog_of_l2a",
        "original_safe_sha256": "not_recorded",
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "etag": etag,
    }


def acquire(
    *,
    scene: str,
    external_dir: Path = EXTERNAL_DIR,
    manifest: Path = MANIFEST,
    workers: int = 4,
) -> None:
    """Download selected exact-product COGs and record each verified file."""
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    rows = _existing_rows(manifest)
    selected = ("event", "dry") if scene == "both" else (scene,)
    done = 0
    for role in selected:
        item_id, product_uri = SCENES[role]
        item = _item(item_id, product_uri)
        print(f"Verified Earth Search product URI: {item_id}", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _acquire_asset,
                    role,
                    item_id,
                    product_uri,
                    asset_name,
                    item["assets"][asset_name]["href"],
                    external_dir,
                )
                for asset_name in ASSETS
            ]
            for future in as_completed(futures):
                row = future.result()
                key = (row["item_id"], row["asset"])
                prior = rows.get(key)
                if prior and (prior["sha256"] != row["sha256"] or prior["asset_url"] != row["asset_url"]):
                    raise ValueError(f"Existing manifest disagrees with asset {item_id}/{row['asset']}.")
                rows[key] = row
                _write_manifest(manifest, rows)
                done += 1
                print(f"[{done}/{len(selected) * len(ASSETS)}] recorded {role}/{row['asset']} SHA-256 {row['sha256']}", flush=True)
    print(f"Manifest: {manifest} ({len(rows)} asset rows)", flush=True)


def main() -> None:
    """Run the anonymous acquisition command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=("event", "dry", "both"), default="both")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--external-data-dir", type=Path, default=EXTERNAL_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    acquire(scene=args.scene, external_dir=args.external_data_dir, manifest=args.manifest, workers=args.workers)


if __name__ == "__main__":
    main()
