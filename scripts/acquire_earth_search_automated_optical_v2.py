"""Verify or acquire the exact Sentinel-2 COGs frozen for automated optical v2.

Development reuses the hashed Mae Sai v1 files without downloading them again.
Final holdout downloads the pinned Chaiyaphum event and dry-context products
outside Git. Neither mode opens image pixels or runs a water classifier.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import URLError

try:
    from scripts.acquire_earth_search_mae_sai_reference import (
        ASSETS,
        _head,
        _item,
        _sha256,
        _urlopen,
    )
except ModuleNotFoundError:
    from acquire_earth_search_mae_sai_reference import (  # type: ignore[no-redef]
        ASSETS,
        _head,
        _item,
        _sha256,
        _urlopen,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = REPO_ROOT / "docs/proposal_execution/automated_track/preregistration_v2.json"
PREREG_COMMIT = "efc69f5f66dfe8c2d667a9827566126709f1cab9"
MANIFESTS = {
    "development": REPO_ROOT / "outputs/earth_search_automated_optical_v2_development_assets.csv",
    "final_holdout": REPO_ROOT / "outputs/earth_search_automated_optical_v2_holdout_assets.csv",
}
EXTERNAL_SUBDIRS = {
    "development": Path("earth_search/mae_sai_2024"),
    "final_holdout": Path("earth_search/chaiyaphum_2021_v2"),
}
COLUMNS = (
    "scene_role", "item_id", "product_uri", "asset", "asset_url",
    "file_size_bytes", "sha256", "scale", "offset", "source_edition",
    "original_safe_sha256", "local_path_hint", "processing_baseline",
    "sensing_utc", "etag", "preregistration_sha256", "verified_at_utc",
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RANGE_BYTES = 8 * 1024 * 1024


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_plan(path: Path = PREREG_PATH) -> dict[str, Any]:
    """Verify the frozen plan's self-hash and exact pre-registration commit."""
    plan = json.loads(path.read_text(encoding="utf-8"))
    digest = plan.get("preregistration_sha256")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("v2 pre-registration SHA-256 is missing or malformed")
    if _canonical_sha256({key: value for key, value in plan.items() if key != "preregistration_sha256"}) != digest:
        raise ValueError("v2 pre-registration self-hash mismatch")
    if plan.get("schema") != "floodguard.automated_optical_preregistration.v2":
        raise ValueError("unexpected v2 pre-registration schema")
    try:
        shown = subprocess.run(
            ["git", "show", f"{PREREG_COMMIT}:docs/proposal_execution/automated_track/preregistration_v2.json"],
            cwd=REPO_ROOT, check=True, capture_output=True,
        ).stdout
        committed = json.loads(shown.decode("utf-8"))
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot verify the v2 pre-registration Git commit") from exc
    if _canonical_sha256(committed) != _canonical_sha256(plan):
        raise ValueError("v2 pre-registration differs from the frozen Git commit")
    return plan


def _read_rows(path: Path, columns: tuple[str, ...]) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f"manifest schema differs: {path}")
        rows = list(reader)
    result = {(row["item_id"], row["asset"]): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate item/asset in manifest: {path}")
    return result


def _write_rows(path: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))
    os.replace(temporary, path)


def _scene_ids(plan: dict[str, Any], scene: str) -> tuple[tuple[str, str, str], ...]:
    section = plan["development" if scene == "development" else "final_holdout"]
    return tuple(
        (role, section[f"{role}_item_id"], section.get(f"{role}_product_uri", ""))
        for role in ("event", "dry")
    )


def _stac_scale_offset(asset: dict[str, Any], name: str) -> tuple[str, str]:
    bands = asset.get("raster:bands")
    if not isinstance(bands, list) or len(bands) != 1 or not isinstance(bands[0], dict):
        raise ValueError(f"STAC {name} lacks exactly one raster:bands entry")
    if name == "scl":
        return "", ""
    band = bands[0]
    scale, offset = band.get("scale"), band.get("offset")
    if (isinstance(scale, bool) or not isinstance(scale, (int, float)) or
            isinstance(offset, bool) or not isinstance(offset, (int, float)) or
            not math.isfinite(scale) or not math.isfinite(offset) or scale <= 0):
        raise ValueError(f"STAC {name} lacks finite reflectance scale/offset")
    return str(scale), str(offset)


def _stac_item(item_id: str, product_uri: str, expected_sensing: str | None) -> dict[str, Any]:
    item = _item(item_id, product_uri)
    properties = item["properties"]
    if expected_sensing:
        try:
            actual_time = datetime.fromisoformat(properties["datetime"].replace("Z", "+00:00"))
            frozen_time = datetime.fromisoformat(expected_sensing.replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError) as exc:
            raise ValueError(f"STAC sensing time is invalid: {item_id}") from exc
        if actual_time.tzinfo is None or frozen_time.tzinfo is None or actual_time != frozen_time:
            raise ValueError(f"STAC sensing time differs from frozen plan: {item_id}")
    baseline = properties.get("s2:processing_baseline")
    match = re.search(r"_N(\d{2})(\d{2})_", product_uri)
    if not match or baseline != f"{match.group(1)}.{match.group(2)}":
        raise ValueError(f"STAC processing baseline differs from product URI: {item_id}")
    for name in ASSETS:
        asset = item["assets"][name]
        if not asset["href"].startswith("https://"):
            raise ValueError(f"STAC {name} asset URL is not HTTPS")
        _stac_scale_offset(asset, name)
    return item


def _row(
    *, plan: dict[str, Any], scene: str, role: str, item: dict[str, Any], name: str,
    size: int, digest: str, etag: str,
) -> dict[str, str]:
    item_id = item["id"]
    scale, offset = _stac_scale_offset(item["assets"][name], name)
    return {
        "scene_role": role,
        "item_id": item_id,
        "product_uri": item["properties"]["s2:product_uri"],
        "asset": name,
        "asset_url": item["assets"][name]["href"],
        "file_size_bytes": str(size),
        "sha256": digest,
        "scale": scale,
        "offset": offset,
        "source_edition": plan["source_edition"],
        "original_safe_sha256": "not_recorded",
        "local_path_hint": f"<external_data_workspace>/{EXTERNAL_SUBDIRS[scene].as_posix()}/{item_id}/{name}.tif",
        "processing_baseline": item["properties"]["s2:processing_baseline"],
        "sensing_utc": item["properties"]["datetime"],
        "etag": etag,
        "preregistration_sha256": plan["preregistration_sha256"],
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _download_ranged(
    url: str, target: Path, expected_size: int, etag: str, *, trusted_sha256: str | None,
    attempts: int = 8,
) -> None:
    """Download verified byte ranges, resuming only a bound source partial file."""
    partial = target.with_suffix(target.suffix + ".part")
    sidecar = partial.with_suffix(partial.suffix + ".json")
    identity = {"url": url, "size": expected_size, "etag": etag}
    if target.exists():
        if target.stat().st_size != expected_size:
            raise ValueError(f"Existing COG has an unexpected size: {target}")
        if trusted_sha256:
            if _sha256(target) != trusted_sha256:
                raise ValueError(f"Existing COG SHA-256 differs from prior manifest: {target}")
        elif not sidecar.exists() or json.loads(sidecar.read_text(encoding="utf-8")) != identity:
            raise ValueError(f"Existing COG lacks a matching prior manifest or source binding: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if sidecar.exists():
        if json.loads(sidecar.read_text(encoding="utf-8")) != identity:
            raise ValueError(f"Partial COG belongs to a different source: {partial}")
    elif partial.exists() and partial.stat().st_size:
        raise ValueError(f"Nonempty partial COG has no source binding: {partial}")
    else:
        sidecar.write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
    for attempt in range(1, attempts + 1):
        try:
            while True:
                have = partial.stat().st_size if partial.exists() else 0
                if have > expected_size:
                    raise ValueError(f"Partial COG exceeds the source size: {partial}")
                if have == expected_size:
                    partial.replace(target)
                    return
                end = min(have + _RANGE_BYTES, expected_size) - 1
                with _urlopen(url, headers={"Range": f"bytes={have}-{end}"}) as response:
                    content_range = response.headers.get("Content-Range", "")
                    expected_range = f"bytes {have}-{end}/{expected_size}"
                    if response.status != 206 or content_range != expected_range:
                        raise ValueError(f"Unexpected Content-Range for {partial}: {content_range}")
                    if etag and response.headers.get("ETag", "") != etag:
                        raise ValueError(f"COG ETag changed during transfer: {partial}")
                    block = response.read(end - have + 1)
                if len(block) != end - have + 1:
                    raise OSError(f"Short byte range for {partial}")
                with partial.open("ab") as output:
                    output.write(block)
        except (OSError, URLError, HTTPException) as exc:
            print(f"  attempt {attempt}/{attempts} interrupted: {type(exc).__name__}; resuming", flush=True)
            if attempt < attempts:
                time.sleep(min(attempt * 2, 15))
    raise RuntimeError(f"COG download incomplete after {attempts} attempts: {target.name}")


def _verify_development_asset(
    plan: dict[str, Any], role: str, item: dict[str, Any], name: str,
    external_root: Path, prior_v1: dict[str, str], prior_v2: dict[str, str] | None,
) -> dict[str, str]:
    item_id = item["id"]
    url = item["assets"][name]["href"]
    if any((
        prior_v1["scene_role"] != role,
        prior_v1["item_id"] != item_id,
        prior_v1["product_uri"] != item["properties"]["s2:product_uri"],
        prior_v1["asset"] != name,
        prior_v1["asset_url"] != url,
        prior_v1["source_edition"] != "element84_cog_of_l2a",
    )):
        raise ValueError(f"v1 receipt disagrees with development asset {role}/{name}")
    target = external_root / EXTERNAL_SUBDIRS["development"] / item_id / f"{name}.tif"
    size = target.stat().st_size
    if size != int(prior_v1["file_size_bytes"]):
        raise ValueError(f"development asset byte count differs from v1 receipt: {role}/{name}")
    digest = _sha256(target)
    if digest != prior_v1["sha256"]:
        raise ValueError(f"development asset SHA-256 differs from v1 receipt: {role}/{name}")
    row = _row(
        plan=plan, scene="development", role=role, item=item, name=name,
        size=size, digest=digest, etag=prior_v1["etag"],
    )
    if prior_v2:
        if any(prior_v2[key] != row[key] for key in COLUMNS if key != "verified_at_utc"):
            raise ValueError(f"v2 manifest disagrees with development asset {role}/{name}")
        return prior_v2
    return row


def _acquire_holdout_asset(
    plan: dict[str, Any], role: str, item: dict[str, Any], name: str,
    external_root: Path, prior_v2: dict[str, str] | None,
) -> dict[str, str]:
    url = item["assets"][name]["href"]
    size, etag = _head(url)
    item_id = item["id"]
    target = external_root / EXTERNAL_SUBDIRS["final_holdout"] / item_id / f"{name}.tif"
    if prior_v2 and any((
        prior_v2["item_id"] != item_id,
        prior_v2["asset_url"] != url,
        prior_v2["file_size_bytes"] != str(size),
        prior_v2["etag"] != etag,
    )):
        raise ValueError(f"v2 manifest disagrees with holdout asset {role}/{name}")
    _download_ranged(
        url, target, size, etag, trusted_sha256=prior_v2["sha256"] if prior_v2 else None,
    )
    digest = _sha256(target)
    row = _row(
        plan=plan, scene="final_holdout", role=role, item=item, name=name,
        size=size, digest=digest, etag=etag,
    )
    if prior_v2:
        if any(prior_v2[key] != row[key] for key in COLUMNS if key != "verified_at_utc"):
            raise ValueError(f"v2 manifest disagrees with holdout asset {role}/{name}")
        return prior_v2
    return row


def acquire(*, scene: str, external_data_root: Path, workers: int = 4) -> Path | tuple[Path, Path]:
    """Verify development files or acquire holdout COGs and write separate v2 manifests."""
    if scene not in ("development", "final_holdout", "both"):
        raise ValueError("scene must be development, final_holdout, or both")
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    plan = load_plan()
    selected = ("development", "final_holdout") if scene == "both" else (scene,)
    produced: list[Path] = []
    for part in selected:
        manifest = MANIFESTS[part]
        rows = _read_rows(manifest, COLUMNS)
        v1_rows: dict[tuple[str, str], dict[str, str]] = {}
        if part == "development":
            v1_manifest = REPO_ROOT / plan["development"]["asset_manifest_path"]
            if _sha256(v1_manifest) != plan["development"]["asset_manifest_sha256"]:
                raise ValueError("Mae Sai v1 manifest SHA-256 differs from frozen v2 plan")
            v1_columns = (
                "scene_role", "item_id", "product_uri", "asset", "asset_url", "local_path_hint",
                "file_size_bytes", "sha256", "source_edition", "original_safe_sha256", "acquired_at_utc", "etag",
            )
            v1_rows = _read_rows(v1_manifest, v1_columns)
        expected_keys = {(item_id, name) for _, item_id, _ in _scene_ids(plan, part) for name in ASSETS}
        if rows.keys() - expected_keys:
            raise ValueError(f"v2 manifest has an unexpected item or asset: {manifest}")
        if part == "development" and v1_rows.keys() != expected_keys:
            raise ValueError("Mae Sai v1 manifest does not contain exactly the frozen development assets")
        for role, item_id, pinned_uri in _scene_ids(plan, part):
            if not pinned_uri:
                pinned_uri = v1_rows[(item_id, ASSETS[0])]["product_uri"]
            sensing = plan["final_holdout"].get(f"{role}_sensing_utc") if part == "final_holdout" else None
            item = _stac_item(item_id, pinned_uri, sensing)
            print(f"Verified {part}/{role}: {item_id}, {pinned_uri}", flush=True)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for name in ASSETS:
                    key = item_id, name
                    if part == "development":
                        future = executor.submit(
                            _verify_development_asset, plan, role, item, name, external_data_root,
                            v1_rows[key], rows.get(key),
                        )
                    else:
                        future = executor.submit(
                            _acquire_holdout_asset, plan, role, item, name, external_data_root,
                            rows.get(key),
                        )
                    futures[future] = key
                for future in as_completed(futures):
                    row = future.result()
                    key = futures[future]
                    rows[key] = row
                    _write_rows(manifest, rows)
                    print(f"Verified {part}/{role}/{row['asset']}: {row['file_size_bytes']} bytes SHA-256 {row['sha256']}", flush=True)
        if rows.keys() != expected_keys:
            raise ValueError(f"v2 manifest is incomplete: {manifest}")
        print(f"Manifest: {manifest} ({len(rows)} rows)", flush=True)
        produced.append(manifest)
    return (produced[0], produced[1]) if scene == "both" else produced[0]


def main() -> None:
    """Run exact-product, anonymous optical v2 acquisition."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=("development", "final_holdout", "both"), default="both")
    parser.add_argument("--external-data-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    acquire(scene=args.scene, external_data_root=args.external_data_root, workers=args.workers)


if __name__ == "__main__":
    main()
