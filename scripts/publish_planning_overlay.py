"""Publish the planning assessment overlay of one case under the public web folder, or check a published copy.

Protocol v1a, guardrail GR6: "Only public overlays may be written to apps/web/public/". The overlay of a case whose
whole lineage is public is written into Git by ``scripts/build_planning_assessment.py``
(``outputs/planning_v1/overlays/``). This script copies that file, byte for byte, to the address the pages read
(``apps/web/public/planning-overlays/<study>/<case>.json``) and writes a ``LICENSE`` beside it that names the
licence, the credit and the change notice of every input, taken from the overlay itself. It computes nothing.

It refuses, and writes nothing, unless all of these hold:

* both protocols are in force and the overlay parser, bound to them, accepts the file;
* the overlay is a portfolio case of the asked case, not a fixture, and its publication level is ``public``;
* every input of its lineage is at the level ``public``;
* the overlay is the file the registered run receipt of plan task E8 binds by SHA-256, and that receipt says the
  run wrote it into Git at the public level;
* the rights registry allows a public write of the flood layer the frame names for the case.

An overlay is planning guidance for preparedness and for prioritisation after an event. It is not an official
warning, not an observation of a flood and not an operational product. A scenario result is not an observation,
and class E never means safe.

Usage::

    python scripts/publish_planning_overlay.py --case SE1 --frame mae_sai [--verify]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import planning_assessment, rights  # noqa: E402
from floodguard.planning_overlay import (  # noqa: E402
    FIXTURE_MODE,
    PORTFOLIO_KIND,
    SCHEMA_RELATIVE_PATH,
    load_overlay,
    load_overlay_schema,
)

PUBLIC_FOLDER = "planning-overlays"
"""The folder under ``apps/web/public/`` the pages read a published overlay from."""
STUDY_FOLDERS: dict[str, str] = {"mae_sai": "mae-sai-2024"}
"""The study folder of each frame set, as the pages name it."""
LICENCE_FILE = "LICENSE"
DOCS = Path("docs") / "proposal_execution"
EXIT_PUBLISHED, EXIT_REFUSED = 0, 2


class PublishError(ValueError):
    """Raised when an overlay may not be published, or a published copy is not the overlay of record."""


def _builder() -> Any:
    """Load ``scripts/build_planning_assessment.py`` as a module: it holds the frame sets and the receipt paths."""

    path = Path(__file__).resolve().with_name("build_planning_assessment.py")
    spec = importlib.util.spec_from_file_location("build_planning_assessment", path)
    if spec is None or spec.loader is None:
        raise PublishError("the planning assessment builder could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def published_path(case_id: str, frame: str, root: Path = ROOT) -> Path:
    """Return the address under the public web folder the overlay of a case is published at."""

    if frame not in STUDY_FOLDERS:
        raise PublishError(f"no study folder is declared for frame {frame!r}")
    return root / rights.PUBLIC_WEB_ROOT / PUBLIC_FOLDER / STUDY_FOLDERS[frame] / f"{case_id.lower()}.json"


def licence_text(overlay: dict[str, Any], *, published_name: str, source_label: str, source_sha256: str) -> str:
    """Return the licence notice of a published overlay: licence, credit and change notice of every input."""

    case = overlay["case"]
    lines = [
        "FloodGuard Thailand",
        f"Licence notice for the planning assessment overlay of case {case['case_id']} ({case['title_en']})",
        "",
        "1. Files this notice covers",
        f"   - {published_name}",
        f"   - {LICENCE_FILE}",
        "",
        "2. What the file is",
        "   A planning assessment for preparedness and for prioritisation after an event. It is not an official warning,",
        "   not an observation of a flood and not an operational product. A scenario result is not an observation.",
        "   Class E never means safe. FloodGuard did not validate the flood layer it uses.",
        f"   It is a byte-for-byte copy of {source_label}",
        f"   SHA-256: {source_sha256}",
        f"   Source period of the flood input: {overlay['source_timestamp']}; generated at {overlay['generated_at']}.",
        "",
        "3. Inputs, with the licence and the credit of each",
    ]
    for item in overlay["inputs"]:
        lines.append(f"   - {item['name']} ({item['input_id']})")
        lines.append(f"     Licence: {item['licence']}")
        lines.append(f"     Credit: {item['attribution']}")
        if item.get("change_notice"):
            lines.append(f"     {item['change_notice']}")
    share_alike = sorted({str(item["licence"]) for item in overlay["inputs"] if "SA" in str(item["licence"]).split("(")[0]})
    lines += [
        "",
        "4. Licence of this file",
        "   The file holds values derived from every input above, so the terms of each apply to it.",
    ]
    if share_alike:
        lines.append(f"   It is shared under {share_alike[0]}, as the run receipt of plan task E8 states: anyone who shares or adapts")
        lines.append("   it must give the credits above, say what was changed and share the result under the same licence.")
        lines.append("   Where an input is under the ODbL, its terms for a derived database apply as well.")
    lines.append("")
    return "\n".join(lines)


def check_overlay_of_record(case_id: str, frame: str, root: Path, registry: rights.RightsRegistry | None = None) -> tuple[Path, bytes, dict[str, Any]]:
    """Return the overlay of record of a case, its bytes and its parsed content, or refuse.

    Raises:
        PublishError: for any condition of the module docstring that does not hold.
    """

    builder = _builder()
    frame_set = builder.FRAME_SETS.get(frame)
    if frame_set is None:
        raise PublishError(f"frame {frame!r} is not a frame set of the builder")
    output_dir = root / "outputs" / "planning_v1"
    receipt_path = builder.receipt_path_for(case_id, frame_set, output_dir)
    registered = output_dir / "run_register" / receipt_path.name
    if not receipt_path.is_file() or not registered.is_file():
        raise PublishError(f"case {case_id} has no registered run receipt of plan task E8 ({receipt_path.name})")
    # A register entry names the receipt of record by its path and its SHA-256.
    entry = json.loads(registered.read_text(encoding="ascii"))
    if entry.get("path") != receipt_path.relative_to(root).as_posix() or entry.get("sha256") != hashlib.sha256(receipt_path.read_bytes()).hexdigest():
        raise PublishError(f"the receipt of case {case_id} is not the one the run register names ({receipt_path.name})")
    receipt = json.loads(receipt_path.read_text(encoding="ascii"))
    result = receipt["result"]
    if not result.get("overlay_written") or receipt["rights"].get("publication_eligibility") != rights.PUBLIC_LEVEL:
        raise PublishError(f"the run of record of case {case_id} wrote no overlay at the public level")
    files = receipt["outputs"]["overlay"]["files"]
    bound = next((item for item in files if item.get("what") == "planning_assessment_overlay"), None)
    if bound is None or not bound.get("in_git"):
        raise PublishError(f"the run of record of case {case_id} did not write its overlay into Git")
    source = root / bound["path"]
    if not source.is_file():
        raise PublishError(f"the overlay the receipt binds is not at {bound['path']}")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != bound["sha256"]:
        raise PublishError("the overlay in Git is not the file the registered receipt binds (SHA-256 differs)")
    docs = root / DOCS
    rules = planning_assessment.load_assessment_rules(
        docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    schema = load_overlay_schema(root / SCHEMA_RELATIVE_PATH)
    overlay = load_overlay(source, schema, binding=rules.binding)
    case = overlay["case"]
    if case["kind"] != PORTFOLIO_KIND or overlay["dataset_mode"] == FIXTURE_MODE or case["case_id"] != case_id:
        raise PublishError(f"the file is not the overlay of portfolio case {case_id}")
    if overlay["publication_eligibility"] != rights.PUBLIC_LEVEL:
        raise PublishError("guardrail GR6: only an overlay at the public level may be written under apps/web/public/")
    below = sorted(item["input_id"] for item in overlay["inputs"] if item["rights_level"] != rights.PUBLIC_LEVEL)
    if below:
        raise PublishError(f"guardrail GR6: inputs below the public level: {', '.join(below)}")
    registry = registry or rights.RightsRegistry(root)
    # The layer of the flood input, as the run of record asked the registry about it.
    layer = (receipt["inputs"].get("rights_record") or {}).get("layer")
    try:
        registry.require_public_write(frame_set.rights_input[case_id], layer=layer)
    except rights.RightsRefusedError as error:
        raise PublishError(f"the rights registry refuses a public write: {error}") from error
    return source, data, overlay


def publish(case_id: str, frame: str, *, root: Path = ROOT, verify: bool = False,
            registry: rights.RightsRegistry | None = None) -> dict[str, Any]:
    """Copy the overlay of record of a case under the public web folder, or compare a published copy with it.

    Returns:
        What was written or compared: the two paths, the SHA-256 of the overlay and of the notice.

    Raises:
        PublishError: when the overlay may not be published, or (with ``verify``) a published file differs.
    """

    source, data, overlay = check_overlay_of_record(case_id, frame, root, registry)
    target = published_path(case_id, frame, root)
    source_label = source.relative_to(root).as_posix()
    digest = hashlib.sha256(data).hexdigest()
    notice = licence_text(overlay, published_name=target.name, source_label=source_label, source_sha256=digest).encode("utf-8")
    licence_path = target.with_name(LICENCE_FILE)
    summary = {
        "case_id": case_id, "published": target.relative_to(root).as_posix(), "copy_of": source_label,
        "sha256": digest, "licence_file": licence_path.relative_to(root).as_posix(),
        "licence_sha256": hashlib.sha256(notice).hexdigest(), "publication_eligibility": overlay["publication_eligibility"],
        "official_warning": overlay["official_warning"], "source_timestamp": overlay["source_timestamp"],
    }
    if verify:
        same = target.is_file() and target.read_bytes() == data and licence_path.is_file() and licence_path.read_bytes() == notice
        if not same:
            raise PublishError(f"{summary['published']} or its {LICENCE_FILE} is not the published form of {source_label}")
        return {**summary, "verified": True}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    licence_path.write_bytes(notice)
    return {**summary, "written": True}


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--case", required=True)
    parser.add_argument("--frame", required=True, choices=sorted(STUDY_FOLDERS))
    parser.add_argument("--verify", action="store_true", help="compare the published copy with the overlay of record; write nothing")
    args = parser.parse_args(arguments)
    try:
        summary = publish(args.case, args.frame, verify=args.verify)
    except (PublishError, ValueError) as error:
        print(json.dumps({"refused": str(error)}, ensure_ascii=True))
        return EXIT_REFUSED
    print(json.dumps(summary, ensure_ascii=True))
    return EXIT_PUBLISHED


if __name__ == "__main__":
    raise SystemExit(main())
