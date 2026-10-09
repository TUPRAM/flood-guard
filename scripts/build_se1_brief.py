"""Write the printable Thai and English brief of case SE1 from its published result file.

The proposal promises a printable bilingual brief with the class, the reason, the source time, the confidence and
the planning-only line. This script makes it from the published result file of case SE1 and from nothing else, as
Markdown and as one self-contained HTML page that prints on one sheet (A4, landscape). It changes no published
file. The brief is planning guidance, not an official warning.

Beside the published values the brief carries one note that is not in the published file: what the report-only
ensemble run of decision log R38 found about the stability of the classes. The note is labelled as such.

Example::

    python scripts/build_se1_brief.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import planning_brief  # noqa: E402

PUBLISHED = "outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json"
STABILITY = "outputs/uncertainty_ensemble_rescaled/se1_mae_sai_v1.json"
OUTPUT_DIR = "outputs/planning_brief"
NAME = "se1_mae_sai_brief"


def stability_note(overlay: dict, record: dict) -> tuple[str, str] | None:
    """One sentence in each language on what the report-only ensemble run found, or nothing when every class holds."""

    thai = {row["unit_id"]: row["unit_name_th"] for row in overlay["rows"]}
    unstable = [unit for unit in record["units"] if unit["headline_stability"]["status"] == "unstable_verify"]
    if not unstable:
        return None
    holding = len(record["units"]) - len(unstable)
    cells = record["summary"]["cells_run"]
    names_en = ", ".join(unit["unit_name_en"] for unit in unstable)
    names_th = " ".join(thai[unit["unit_id"]] for unit in unstable)
    return (f"A report-only check that is not part of the published result: over {cells} runs {holding} classes hold. The class of {names_en} does not: "
            "it depends on the population data. Verify before use.",
            f"การตรวจสอบเพิ่มเติมแบบรายงานเท่านั้น ไม่ใช่ส่วนหนึ่งของผลที่เผยแพร่: จากการคำนวณ {cells} รอบ ระดับของ {holding} ตำบลคงเดิม "
            f"ส่วนระดับของตำบล{names_th}ไม่คงเดิมและขึ้นกับข้อมูลประชากร ควรตรวจสอบก่อนใช้งาน")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.parse_args()
    source = ROOT / PUBLISHED
    source_bytes = source.read_bytes()
    overlay = json.loads(source_bytes.decode("utf-8"))
    digest = hashlib.sha256(source_bytes).hexdigest()
    stability_path = ROOT / STABILITY
    note, stability_sha = None, None
    if stability_path.exists():
        note = stability_note(overlay, json.loads(stability_path.read_text(encoding="utf-8")))
        stability_sha = hashlib.sha256(stability_path.read_bytes()).hexdigest()
    arguments = {"source_sha256": digest, "source_path": PUBLISHED, "stability_note": note}
    files = {f"{NAME}.md": planning_brief.render_markdown(overlay, **arguments).encode("utf-8"),
             f"{NAME}.html": planning_brief.render_html(overlay, **arguments).encode("utf-8")}
    folder = ROOT / OUTPUT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)  # LF bytes
    rows = planning_brief.rows_of(overlay)
    record = {
        "schema": "floodguard.planning_brief_record.v1",
        "what_this_is": "The record of the printable brief of case SE1: what it was made from, and that it changes nothing published.",
        "source_timestamp": planning_brief.flood_window(overlay),
        "result_generated_at": overlay["generated_at"],
        "confidence_classes_of_the_rows": sorted({row["confidence"] for row in rows}),
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "made_from": {"path": PUBLISHED, "sha256": digest},
        "stability_note_from": None if note is None else {"path": STABILITY, "sha256": stability_sha,
                                                          "what": "A report-only run (decision log R38). The note is labelled on the brief as not part of the published result."},
        "files": [{"name": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in files.items()],
        "classes_on_the_brief": {row["unit_id"]: row["class"] for row in rows},
        "assumptions": [english for english, _thai in planning_brief.ASSUMPTIONS],
        "thai_text": planning_brief.THAI_NOTE[0],
        "how_to_print": "Open the HTML file in a browser and print: A4, landscape, one sheet.",
    }
    (folder / f"{NAME}_record.json").write_bytes((json.dumps(record, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print(files[f"{NAME}.md"].decode("utf-8"))


if __name__ == "__main__":
    main()
