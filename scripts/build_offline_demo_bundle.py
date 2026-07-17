"""Build a reproducible, self-contained FloodGuard proposal demo ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_SITE_FILES = (
    "index.html",
    "public/index.html",
    "command/index.html",
    "studio/index.html",
    "manifest.webmanifest",
    "sw.js",
    "offline-demo/bundle.json",
    "offline-demo/areas.geojson",
)
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".svg", ".txt"}
PRIVATE_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]", re.IGNORECASE),
    re.compile(r"file://", re.IGNORECASE),
)
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _validate_site(site_root: Path) -> None:
    missing = [relative for relative in REQUIRED_SITE_FILES if not (site_root / relative).is_file()]
    if missing:
        raise ValueError(f"Static export is incomplete; missing: {', '.join(missing)}")

    for path in sorted(candidate for candidate in site_root.rglob("*") if candidate.is_file()):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in PRIVATE_PATH_PATTERNS:
            if pattern.search(text):
                relative = path.relative_to(site_root).as_posix()
                raise ValueError(f"Private local path found in static export: {relative}")


def _write_reproducible_zip(source_root: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def build_bundle(
    *,
    repository_root: Path,
    site_root: Path,
    template_root: Path,
    output_zip: Path,
    generated_at: str,
    git_commit: str,
) -> dict[str, object]:
    _validate_site(site_root)
    required_templates = ("README_TH_EN.md", "serve-demo.ps1", "serve-demo.py")
    missing_templates = [name for name in required_templates if not (template_root / name).is_file()]
    if missing_templates:
        raise ValueError(f"Offline packaging templates are missing: {', '.join(missing_templates)}")

    with tempfile.TemporaryDirectory(prefix="floodguard-offline-") as temporary:
        package_root = Path(temporary) / "FloodGuard_Offline_Demo"
        shutil.copytree(site_root, package_root / "site")
        for name in required_templates:
            shutil.copy2(template_root / name, package_root / name)

        packaged_files = []
        for path in sorted(candidate for candidate in package_root.rglob("*") if candidate.is_file()):
            packaged_files.append(
                {
                    "relative_path": path.relative_to(package_root).as_posix(),
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )

        manifest: dict[str, object] = {
            "schema_version": "floodguard.offline-demo-bundle.v1",
            "generated_at": generated_at,
            "git_commit": git_commit,
            "dataset_mode": "fixture_demo",
            "operational_status": "non_operational",
            "official_warning": False,
            "entrypoint": "site/public/index.html",
            "files": packaged_files,
        }
        manifest_path = package_root / "offline-bundle-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _write_reproducible_zip(package_root, output_zip)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, default=Path("apps/web/out"))
    parser.add_argument("--template-root", type=Path, default=Path("packaging/offline-demo"))
    parser.add_argument("--output", type=Path, default=Path("dist/FloodGuard_Proposal_Offline_Demo.zip"))
    parser.add_argument("--generated-at")
    parser.add_argument("--git-commit")
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    generated_at = args.generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    git_commit = args.git_commit or _git_commit(repository_root)
    manifest = build_bundle(
        repository_root=repository_root,
        site_root=(repository_root / args.site_root).resolve(),
        template_root=(repository_root / args.template_root).resolve(),
        output_zip=(repository_root / args.output).resolve(),
        generated_at=generated_at,
        git_commit=git_commit,
    )
    print(json.dumps({"output": args.output.as_posix(), "file_count": len(manifest["files"]), "git_commit": git_commit}))


if __name__ == "__main__":
    main()
