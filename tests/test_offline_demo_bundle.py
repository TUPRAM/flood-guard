from __future__ import annotations

import json
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_offline_demo_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_offline_demo_bundle", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REQUIRED_SITE_FILES = MODULE.REQUIRED_SITE_FILES
build_bundle = MODULE.build_bundle


def _make_site(root: Path) -> None:
    for relative in REQUIRED_SITE_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture demo; non-operational; not an official warning", encoding="utf-8")


def _make_templates(root: Path) -> None:
    for name in ("README_TH_EN.md", "serve-demo.ps1", "serve-demo.py"):
        (root / name).write_text(name, encoding="utf-8")


def test_build_bundle_is_reproducible_and_records_safe_status(tmp_path: Path) -> None:
    site = tmp_path / "site"
    templates = tmp_path / "templates"
    output_a = tmp_path / "a.zip"
    output_b = tmp_path / "b.zip"
    _make_site(site)
    templates.mkdir()
    _make_templates(templates)

    kwargs = {
        "repository_root": tmp_path,
        "site_root": site,
        "template_root": templates,
        "generated_at": "2026-07-30T00:00:00Z",
        "git_commit": "a" * 40,
    }
    manifest = build_bundle(output_zip=output_a, **kwargs)
    build_bundle(output_zip=output_b, **kwargs)

    assert output_a.read_bytes() == output_b.read_bytes()
    assert manifest["dataset_mode"] == "fixture_demo"
    assert manifest["operational_status"] == "non_operational"
    assert manifest["official_warning"] is False

    with zipfile.ZipFile(output_a) as archive:
        names = set(archive.namelist())
        assert "site/public/index.html" in names
        assert "README_TH_EN.md" in names
        packaged_manifest = json.loads(archive.read("offline-bundle-manifest.json"))
    assert packaged_manifest["git_commit"] == "a" * 40
    assert all(not item["relative_path"].startswith("/") for item in packaged_manifest["files"])


def test_build_bundle_rejects_missing_route(tmp_path: Path) -> None:
    site = tmp_path / "site"
    templates = tmp_path / "templates"
    _make_site(site)
    (site / "studio" / "index.html").unlink()
    templates.mkdir()
    _make_templates(templates)

    with pytest.raises(ValueError, match="studio/index.html"):
        build_bundle(
            repository_root=tmp_path,
            site_root=site,
            template_root=templates,
            output_zip=tmp_path / "bundle.zip",
            generated_at="2026-07-30T00:00:00Z",
            git_commit="b" * 40,
        )


@pytest.mark.parametrize(
    "private_path",
    [
        r"C:\Users\private\source.tif",
        r"D:\data\private\source.tif",
        r"\\server\private-share\source.tif",
        "/home/private/source.tif",
        "/Users/private/source.tif",
        "/root/private/source.tif",
        "/tmp/private-run/source.tif",
        "file:///private/source.tif",
    ],
)
def test_build_bundle_rejects_private_absolute_paths(
    tmp_path: Path, private_path: str
) -> None:
    site = tmp_path / "site"
    templates = tmp_path / "templates"
    _make_site(site)
    (site / "index.html").write_text(private_path, encoding="utf-8")
    templates.mkdir()
    _make_templates(templates)

    with pytest.raises(ValueError, match="Private local path"):
        build_bundle(
            repository_root=tmp_path,
            site_root=site,
            template_root=templates,
            output_zip=tmp_path / "bundle.zip",
            generated_at="2026-07-30T00:00:00Z",
            git_commit="c" * 40,
        )
