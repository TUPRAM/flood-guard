"""Build a reproducible FloodGuard offline ZIP; finals packaging is explicit."""

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
from urllib.parse import urlsplit

REQUIRED_SITE_FILES = (
    "index.html",
    "public/index.html",
    "command/index.html",
    "studio/index.html",
    "manifest.webmanifest",
    "sw.js",
    "offline-demo/bundle.json",
    "offline-demo/areas.geojson",
    "offline-demo/roads.geojson",
    "offline-demo/context.geojson",
)
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".svg", ".txt"}
PRIVATE_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][A-Za-z0-9._ -]+"),
    re.compile(r"\\\\[A-Za-z0-9][A-Za-z0-9._-]*\\[A-Za-z0-9$._-]+"),
    re.compile(r"file://", re.IGNORECASE),
)
UNIX_PRIVATE_PATH_PATTERNS = (
    re.compile(r"/(?:Users|home|tmp|var|private)/", re.IGNORECASE),
    re.compile(r"/root/"),
)
HTTPS_URL_PATTERN = re.compile(r"(?<![A-Za-z0-9+.-])https://[^\s<>\"'`\\]+", re.IGNORECASE)
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
FINALS_START_URL = "/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024"


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


def _mask_https_path(match: re.Match[str]) -> str:
    """Exclude URL paths, while keeping query/fragment local paths visible."""
    value = match.group()
    try:
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return value
        # Accessing port also validates malformed/non-numeric authority ports.
        _ = parsed.port
    except ValueError:
        return value
    start = len(parsed.scheme) + 3 + len(parsed.netloc)
    return value[:start] + (" " * len(parsed.path)) + value[start + len(parsed.path) :]


def _validate_site(site_root: Path) -> None:
    missing = [relative for relative in REQUIRED_SITE_FILES if not (site_root / relative).is_file()]
    if missing:
        raise ValueError(f"Static export is incomplete; missing: {', '.join(missing)}")

    for path in sorted(candidate for candidate in site_root.rglob("*") if candidate.is_file()):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # A public URL such as arcgis.com/home/item.html is not a local /home
        # path. Drive paths, UNC paths and file URLs are never exempted.
        # Turbopack emits this virtual-root helper, not a host filesystem path.
        # Exempt only its complete expression in a runtime chunk; concrete file
        # URLs (including paths under /ROOT) remain prohibited.
        if path.name.startswith("turbopack-") and path.suffix == ".js":
            text = text.replace(
                'e?`file:///ROOT/${e.split("/").map(encodeURIComponent).join("/")}`:"file:///ROOT/"',
                'e?"virtual-root":"virtual-root"',
            )
        unix_text = HTTPS_URL_PATTERN.sub(_mask_https_path, text)
        if any(pattern.search(text) for pattern in PRIVATE_PATH_PATTERNS) or any(
            pattern.search(unix_text) for pattern in UNIX_PRIVATE_PATH_PATTERNS
        ):
            relative = path.relative_to(site_root).as_posix()
            raise ValueError(f"Private local path found in static export: {relative}")


def _write_reproducible_zip(source_root: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(
            candidate for candidate in source_root.rglob("*") if candidate.is_file()
        ):
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def _validate_finals(site_root: Path) -> dict[str, object]:
    from floodguard.evidence_validation import verify_evidence_library

    for relative in (
        "studio/brief/index.html",
        "studio/library/index.html",
        "evidence-library/catalog.json",
    ):
        if not (site_root / relative).is_file():
            raise ValueError(f"Finals static export is incomplete; missing: {relative}")
    library = site_root / "evidence-library"
    # Reuse the complete public allowlist, hashes, contracts and compressed-database checks.
    receipt = verify_evidence_library(library)
    if receipt.get("status") != "passed":
        raise ValueError("Finals public evidence verification did not pass")
    catalog = json.loads((library / "catalog.json").read_text(encoding="utf-8"))
    package_path = library / "packages/aoi-01_mae_sai_core_mae_sai_2024.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    analysis = package.get("decision_brief", {}).get("finals_analysis")
    if not isinstance(analysis, dict) or analysis.get("status") != "scenario_only":
        raise ValueError("Finals package is missing the explicit Mae Sai scenario analysis")
    if not analysis.get("routes", {}).get("origins"):
        raise ValueError("Finals package has no prepared public starting places")
    return {
        "evidence_package_version": catalog["package_version"],
        "evidence_catalog_sha256": _sha256(library / "catalog.json"),
        "evidence_package_sha256": _sha256(package_path),
        "finals_analysis_sha256": analysis["analysis_sha256"],
    }


def build_bundle(
    *,
    repository_root: Path,
    site_root: Path,
    template_root: Path,
    output_zip: Path,
    generated_at: str,
    git_commit: str,
    finals: bool = False,
) -> dict[str, object]:
    _validate_site(site_root)
    finals_identity = _validate_finals(site_root) if finals else {}
    required_templates = {
        "README_TH_EN.md": "README_FINALS_TH_EN.md" if finals else "README_TH_EN.md",
        "serve-demo.ps1": "serve-demo.ps1",
        "serve-demo.py": "serve-finals.py" if finals else "serve-demo.py",
    }
    missing_templates = [
        name for name in required_templates.values() if not (template_root / name).is_file()
    ]
    if missing_templates:
        raise ValueError(f"Offline packaging templates are missing: {', '.join(missing_templates)}")

    with tempfile.TemporaryDirectory(prefix="floodguard-offline-") as temporary:
        package_root = Path(temporary) / "FloodGuard_Offline_Demo"
        shutil.copytree(site_root, package_root / "site")
        for target, name in required_templates.items():
            shutil.copy2(template_root / name, package_root / target)
        if finals:
            guide = repository_root / "docs/mae_sai_finals_guide.md"
            if not guide.is_file():
                raise ValueError("Finals presentation guide is missing")
            shutil.copy2(guide, package_root / "FINALS_GUIDE.md")

        packaged_files = []
        for path in sorted(
            candidate for candidate in package_root.rglob("*") if candidate.is_file()
        ):
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
            "dataset_mode": "scenario" if finals else "fixture_demo",
            "operational_status": "non_operational",
            "official_warning": False,
            "entrypoint": "site/studio/brief/index.html" if finals else "site/public/index.html",
            "files": packaged_files,
            **finals_identity,
        }
        if finals:
            manifest["start_url"] = FINALS_START_URL
        manifest_path = package_root / "offline-bundle-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _write_reproducible_zip(package_root, output_zip)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, default=Path("apps/web/out"))
    parser.add_argument("--template-root", type=Path, default=Path("packaging/offline-demo"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generated-at")
    parser.add_argument("--git-commit")
    parser.add_argument(
        "--finals",
        action="store_true",
        help="Require the verified Mae Sai finals package and start at the scenario brief.",
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(
            "dist/FloodGuard_Mae_Sai_Finals_Offline_Demo.zip"
            if args.finals
            else "dist/FloodGuard_Proposal_Offline_Demo.zip"
        )

    repository_root = Path(__file__).resolve().parents[1]
    generated_at = args.generated_at or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    git_commit = args.git_commit or _git_commit(repository_root)
    manifest = build_bundle(
        repository_root=repository_root,
        site_root=(repository_root / args.site_root).resolve(),
        template_root=(repository_root / args.template_root).resolve(),
        output_zip=(repository_root / args.output).resolve(),
        generated_at=generated_at,
        git_commit=git_commit,
        finals=args.finals,
    )
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "file_count": len(manifest["files"]),
                "git_commit": git_commit,
            }
        )
    )


if __name__ == "__main__":
    main()
