"""The publish step of a planning assessment overlay (protocol v1a, guardrail GR6).

``scripts/publish_planning_overlay.py`` copies the overlay of record of a public case under the public web folder
and writes a licence notice beside it. These tests read committed files only; nothing is computed for a tambon.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from floodguard import rights
from floodguard.wording_lint import find_violations, load_rules

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "apps" / "web" / "public" / "planning-overlays" / "mae-sai-2024"


def _script() -> Any:
    path = ROOT / "scripts" / "publish_planning_overlay.py"
    spec = importlib.util.spec_from_file_location("publish_planning_overlay", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_published_copy_of_case_se1_is_the_overlay_of_record_with_its_licence_notice() -> None:
    publisher = _script()
    summary = publisher.publish("SE1", "mae_sai", verify=True)
    assert summary["verified"] is True and summary["publication_eligibility"] == "public" and summary["official_warning"] is False
    assert summary["published"] == "apps/web/public/planning-overlays/mae-sai-2024/se1.json"
    assert summary["copy_of"] == "outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json"
    assert hashlib.sha256((PUBLISHED / "se1.json").read_bytes()).hexdigest() == summary["sha256"]
    overlay = json.loads((PUBLISHED / "se1.json").read_text(encoding="ascii"))
    assert overlay["case"]["case_id"] == "SE1" and overlay["accepted_fpps"] is None and overlay["accepted_action_class"] is None
    assert overlay["source_timestamp"] and overlay["generated_at"] and overlay["assumptions"]
    notice = (PUBLISHED / "LICENSE").read_text(encoding="utf-8")
    # Every input of the lineage is named with its licence and its credit; the limits of the file are stated.
    for item in overlay["inputs"]:
        assert item["rights_level"] == "public"
        assert item["input_id"] in notice and f"Licence: {item['licence']}" in notice and f"Credit: {item['attribution']}" in notice
    assert "CC BY-SA 4.0" in notice and "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009" in notice
    assert "It is not an official warning" in notice and "Class E never means safe" in notice
    assert "A scenario result is not an observation" in notice and summary["sha256"] in notice
    # The index lists what is published, so a page asks for no file that is not there.
    index = json.loads((PUBLISHED / "index.json").read_text(encoding="ascii"))
    assert index["schema"] == publisher.INDEX_SCHEMA and index["official_warning"] is False
    assert index["cases"] == [{"case_id": "SE1", "file": "se1.json", "sha256": summary["sha256"]}]
    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    assert find_violations(notice, rules, "licence notice of the published overlay") == []


def test_a_case_below_the_public_level_is_refused_and_nothing_is_written() -> None:
    publisher = _script()
    with pytest.raises(publisher.PublishError, match="wrote no overlay at the public level"):
        publisher.publish("O2", "mae_sai")
    assert not (PUBLISHED / "o2.json").exists()
    assert publisher.main(["--case", "O2", "--frame", "mae_sai"]) == publisher.EXIT_REFUSED == 2


def test_a_changed_copy_and_a_changed_overlay_are_found(tmp_path: Path) -> None:
    """On a copy of the files the publish step reads: a published file that was edited, and an overlay that is not the receipt's."""

    publisher = _script()
    root = tmp_path / "repo"
    for relative in ("docs/proposal_execution", "outputs/planning_v1", "packages/contracts/schemas",
                     "apps/web/public/planning-overlays"):
        shutil.copytree(ROOT / relative, root / relative)
    registry = rights.RightsRegistry(ROOT)
    assert publisher.publish("SE1", "mae_sai", root=root, verify=True, registry=registry)["verified"] is True
    published = root / "apps/web/public/planning-overlays/mae-sai-2024/se1.json"
    published.write_bytes(published.read_bytes().replace(b'"action_class": "E"', b'"action_class": "A"', 1))
    with pytest.raises(publisher.PublishError, match="is not the published form"):
        publisher.publish("SE1", "mae_sai", root=root, verify=True, registry=registry)
    # Publishing again restores the copy of record.
    assert publisher.publish("SE1", "mae_sai", root=root, registry=registry)["written"] is True
    assert publisher.publish("SE1", "mae_sai", root=root, verify=True, registry=registry)["verified"] is True
    # An overlay in Git that is not the file the registered receipt binds is refused before anything is written.
    source = root / "outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json"
    source.write_bytes(source.read_bytes().replace(b'"action_class": "E"', b'"action_class": "A"', 1))
    with pytest.raises(publisher.PublishError, match="not the file the registered receipt binds"):
        publisher.publish("SE1", "mae_sai", root=root, registry=registry)
