"""Reopen a checksummed public-data inventory without changing its inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(root: Path, manifest: Path) -> dict[str, object]:
    """Validate every manifest path, size and current SHA-256; retain failures."""
    root = root.resolve(strict=True)
    if not root.is_dir() or not manifest.is_file():
        raise ValueError("Source root or manifest is unavailable")
    failures: list[dict[str, str]] = []
    checked = 0
    total_bytes = 0
    seen: set[str] = set()
    with manifest.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["path", "bytes", "sha256"]:
            raise ValueError("Inventory manifest columns differ from path,bytes,sha256")
        for row in reader:
            raw = row["path"]
            normalized = PurePosixPath(raw)
            path_parts = normalized.parts
            if (not raw or "\\" in raw or ":" in raw or raw.startswith("/")
                or any(part in {".", ".."} for part in raw.split("/"))
                or normalized.is_absolute() or raw.lower() in seen):
                failures.append({"path": raw, "reason": "unsafe_or_duplicate_path"})
                continue
            seen.add(raw.lower())
            expected_size = row["bytes"]
            expected_sha = row["sha256"]
            if not expected_size.isdecimal() or not SHA256.fullmatch(expected_sha):
                failures.append({"path": raw, "reason": "invalid_manifest_identity"})
                continue
            path = root.joinpath(*path_parts)
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                failures.append({"path": raw, "reason": "missing_or_linked_file"})
                continue
            actual_size = path.stat().st_size
            if actual_size != int(expected_size):
                failures.append({"path": raw, "reason": "size_mismatch"})
                continue
            if _digest(path) != expected_sha:
                failures.append({"path": raw, "reason": "sha256_mismatch"})
                continue
            checked += 1
            total_bytes += actual_size
    return {
        "schema_version": "floodguard.public_source_inventory_check.v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": _digest(manifest),
        "status": "PASS" if not failures else "FAIL",
        "files_checked": checked,
        "bytes_checked": total_bytes,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.root, args.manifest)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
