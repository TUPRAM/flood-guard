"""Verify and serve the extracted Mae Sai scenario comparison on localhost."""

from __future__ import annotations

import hashlib
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath

START_URL = "/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024"


def validate_bundle(root: Path) -> str:
    """Reject incomplete or changed package files before binding the local server."""
    root = root.resolve()
    manifest = json.loads((root / "offline-bundle-manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("dataset_mode") != "scenario"
        or manifest.get("official_warning") is not False
        or manifest.get("operational_status") != "non_operational"
        or manifest.get("entrypoint") != "site/studio/brief/index.html"
        or manifest.get("start_url") != START_URL
    ):
        raise ValueError("The manifest does not identify the non-operational finals brief.")
    if not manifest.get("files"):
        raise ValueError("The bundle has no file inventory.")
    seen = set()
    for row in manifest["files"]:
        name = row["relative_path"]
        path = root / name
        if (
            not isinstance(name, str)
            or "\\" in name
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or name in seen
            or not path.resolve().is_relative_to(root)
        ):
            raise ValueError("The bundle contains an unsafe or repeated file identity.")
        seen.add(name)
        if not path.is_file() or path.stat().st_size != row["size_bytes"]:
            raise ValueError(f"Missing or changed packaged file: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Packaged checksum differs: {name}")
    if manifest["entrypoint"] not in seen:
        raise ValueError("The finals entrypoint is not in the file inventory.")
    return START_URL


def main() -> None:
    root = Path(__file__).resolve().parent
    try:
        start = validate_bundle(root)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SystemExit(f"Offline bundle verification failed: {error}") from error
    os.chdir(root / "site")
    server = ThreadingHTTPServer(("127.0.0.1", 8000), SimpleHTTPRequestHandler)
    print(f"FloodGuard Mae Sai scenario: http://127.0.0.1:8000{start}")
    print("Non-operational. Not an official warning. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
