from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
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
        packaged_manifest_bytes = archive.read("offline-bundle-manifest.json")
        packaged_manifest = json.loads(packaged_manifest_bytes)
    assert b"\r\n" not in packaged_manifest_bytes
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
        "C:/Users/private/source.tif",
        r"\\server\private-share\source.tif",
        r"\\server\share\source.tif",
        "/home/private/source.tif",
        "/Users/private/source.tif",
        "/root/private/source.tif",
        "/tmp/private-run/source.tif",
        "/var/private/source.tif",
        "/private/source.tif",
        "file:///private/source.tif",
        "file:///C:/Users/private/source.tif",
        r"file:\/\/\/home/private/source.tif",
        'const source="https://www.arcgis.com/home/item.html";const local="/home/private/a.tif";',
        "https://example.org/home/item.html?source=/home/private/source.tif",
        "https://example.org/home/item.html#source=/tmp/private/source.tif",
        "https://example.org/C:/Users/private/source.tif",
        "https://example.org/file:///private/source.tif",
        r"https://example.org/asset?source=\\server\share\source.tif",
        "https:///home/private/source.tif",
        "https://example.org:invalid/home/private/source.tif",
        "https://user:password@example.org/home/private/source.tif",
    ],
)
def test_build_bundle_rejects_private_absolute_paths(tmp_path: Path, private_path: str) -> None:
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
    assert not (tmp_path / "bundle.zip").exists()


@pytest.mark.parametrize(
    "public_reference",
    [
        "https://www.arcgis.com/home/item.html",
        'const source="https://www.arcgis.com/home/item.html?id=public-item";',
        r'{"source":"https:\/\/www.arcgis.com\/home\/item.html"}',
        '<a href="https://example.org/Users/documentation">Reference</a>',
        "https://example.org/tmp/reference/var/data/private/docs/root/index.html",
        "HTTPS://WWW.ARCGIS.COM:443/home/item.html",
    ],
)
def test_build_bundle_allows_public_https_reference_paths(
    tmp_path: Path, public_reference: str
) -> None:
    site = tmp_path / "site"
    templates = tmp_path / "templates"
    _make_site(site)
    script = site / "public-source.js"
    script.write_text(public_reference, encoding="utf-8")
    templates.mkdir()
    _make_templates(templates)
    output = tmp_path / "bundle.zip"

    build_bundle(
        repository_root=tmp_path,
        site_root=site,
        template_root=templates,
        output_zip=output,
        generated_at="2026-09-21T13:44:35Z",
        git_commit="c" * 40,
    )

    with zipfile.ZipFile(output) as archive:
        assert archive.read("site/public-source.js").decode("utf-8") == public_reference


def _finals_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    site = tmp_path / "site"
    _make_site(site)
    for route in ("studio/brief/index.html", "studio/library/index.html"):
        path = site / route
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic scenario page.", encoding="utf-8")
    library = site / "evidence-library"
    (library / "packages").mkdir(parents=True)
    (library / "catalog.json").write_text(
        json.dumps({"package_version": "synthetic-version"}), encoding="utf-8"
    )
    (library / "packages/aoi-01_mae_sai_core_mae_sai_2024.json").write_text(
        json.dumps(
            {
                "decision_brief": {
                    "finals_analysis": {
                        "status": "scenario_only",
                        "analysis_sha256": "d" * 64,
                        "routes": {"origins": [{"id": "synthetic-origin"}]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    templates = tmp_path / "templates"
    shutil.copytree(SCRIPT.parents[1] / "packaging/offline-demo", templates)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/mae_sai_finals_guide.md").write_text(
        "Synthetic finals guide.", encoding="utf-8"
    )
    # Detailed export validity is covered by evidence-validation tests. These
    # focused packaging fixtures verify that the mandatory verifier is invoked.
    from floodguard import evidence_validation

    monkeypatch.setattr(
        evidence_validation,
        "verify_evidence_library",
        lambda root: {"status": "passed"} if root == library else {"status": "failed"},
    )
    return {
        "repository_root": tmp_path,
        "site_root": site,
        "template_root": templates,
        "generated_at": "2026-09-21T13:44:35Z",
        "git_commit": "f" * 40,
        "finals": True,
    }


def _serve_module() -> object:
    path = SCRIPT.parents[1] / "packaging/offline-demo/serve-finals.py"
    spec = importlib.util.spec_from_file_location("serve_finals_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_finals_bundle_is_reproducible_and_opens_the_correct_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _finals_inputs(tmp_path, monkeypatch)
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    manifest = build_bundle(output_zip=first, **kwargs)
    build_bundle(output_zip=second, **kwargs)
    assert first.read_bytes() == second.read_bytes()
    assert manifest["dataset_mode"] == "scenario"
    assert manifest["entrypoint"] == "site/studio/brief/index.html"
    assert manifest["finals_analysis_sha256"] == "d" * 64
    assert (
        manifest["evidence_catalog_sha256"]
        == hashlib.sha256(
            (kwargs["site_root"] / "evidence-library/catalog.json").read_bytes()
        ).hexdigest()
    )
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(first) as archive:
        archive.extractall(extracted)
        assert b"controlled model change" in archive.read("README_TH_EN.md")
        assert b"Synthetic finals guide" in archive.read("FINALS_GUIDE.md")
        assert b"validate_bundle" in archive.read("serve-demo.py")
    assert _serve_module().validate_bundle(extracted) == MODULE.FINALS_START_URL


@pytest.mark.parametrize(
    "missing",
    ["studio/brief/index.html", "studio/library/index.html", "evidence-library/catalog.json"],
)
def test_finals_requires_its_routes_and_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    kwargs = _finals_inputs(tmp_path, monkeypatch)
    (kwargs["site_root"] / missing).unlink()
    with pytest.raises(ValueError, match="Finals static export"):
        build_bundle(output_zip=tmp_path / "blocked.zip", **kwargs)
    assert not (tmp_path / "blocked.zip").exists()


def test_finals_rejects_failed_public_allowlist_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _finals_inputs(tmp_path, monkeypatch)
    from floodguard import evidence_validation

    def reject(_root: Path) -> None:
        raise ValueError("Restricted derivative rejected by public verifier")

    monkeypatch.setattr(evidence_validation, "verify_evidence_library", reject)
    with pytest.raises(ValueError, match="Restricted derivative"):
        build_bundle(output_zip=tmp_path / "blocked.zip", **kwargs)
    assert not (tmp_path / "blocked.zip").exists()


def test_finals_rejects_an_older_package_without_route_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _finals_inputs(tmp_path, monkeypatch)
    path = kwargs["site_root"] / "evidence-library/packages/aoi-01_mae_sai_core_mae_sai_2024.json"
    path.write_text('{"decision_brief": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing the explicit Mae Sai"):
        build_bundle(output_zip=tmp_path / "blocked.zip", **kwargs)


def test_extracted_finals_server_rejects_changed_bytes_and_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _finals_inputs(tmp_path, monkeypatch)
    output = tmp_path / "bundle.zip"
    build_bundle(output_zip=output, **kwargs)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extracted)
    server = _serve_module()
    (extracted / "site/studio/brief/index.html").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="changed packaged file"):
        server.validate_bundle(extracted)
    manifest_path = extracted / "offline-bundle-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].insert(
        0, {"relative_path": "../outside", "size_bytes": 1, "sha256": "0" * 64}
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe"):
        server.validate_bundle(extracted)


@pytest.mark.parametrize("concrete_path", [None, "file:///ROOT/private.tif", "file:///C:/Users/private/a.tif"])
def test_turbopack_virtual_root_helper_is_not_a_private_path(tmp_path, concrete_path):
    site = tmp_path / "site"
    _make_site(site)
    runtime = site / "_next/static/chunks/turbopack-test.js"
    runtime.parent.mkdir(parents=True)
    helper = 'k.F=function(e){return e?`file:///ROOT/${e.split("/").map(encodeURIComponent).join("/")}`:"file:///ROOT/"}'
    runtime.write_text(helper + (concrete_path or ""), encoding="utf-8")
    if concrete_path:
        with pytest.raises(ValueError, match="Private local path"):
            MODULE._validate_site(site)
    else:
        MODULE._validate_site(site)
