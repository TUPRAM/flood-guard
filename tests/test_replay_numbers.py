"""Figures a deck or a speaker may quote about the Mae Sai replay (``docs/demo/replay_numbers.md``, roadmap P4-1).

The committed document must be exactly what ``scripts/build_replay_numbers.py`` writes from the replay files the page
serves, so a re-bake that moves a figure fails here until the document is regenerated and the deck re-read. The other
tests pin the figures the page, the roadmap and the stage reports state, check the page's rounding, refuse files that
do not match the manifest, and keep the lanes, the licence of the season-envelope section and the wording rules.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from floodguard import replay_numbers as numbers
from floodguard.wording_lint import find_violations, load_rules

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "demo" / "replay_numbers.md"
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")


@pytest.fixture(scope="module")
def files() -> numbers.ReplayFiles:
    return numbers.load_replay_files(ROOT)


@pytest.fixture(scope="module")
def text(files: numbers.ReplayFiles) -> str:
    return numbers.render_markdown(files, numbers.replay_numbers(files))


def test_the_committed_document_is_what_the_script_writes_from_the_served_files(text: str) -> None:
    committed = DOCUMENT.read_bytes().decode("utf-8")
    assert "\r" not in committed, "the document must keep LF line endings"
    assert committed == text, "docs/demo/replay_numbers.md is stale: run scripts/build_replay_numbers.py and re-read the deck's figures"


def test_the_script_check_mode_agrees() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_replay_numbers.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "matches the replay files" in result.stdout


def test_the_document_names_the_files_it_was_made_from(files: numbers.ReplayFiles, text: str) -> None:
    assert files.manifest_path.endswith("/timeline.json")
    for digest in (files.manifest_sha256, files.envelope_sha256, files.nodes_sha256, files.tambons_sha256):
        assert digest and f"`{digest}`" in text
    assert f"revision {files.manifest['revision']}, generated {files.manifest['generated_at']}" in text
    assert "accepted_fpps null; accepted_action_class null" in text and "non_operational; confidence low" in text


@pytest.mark.parametrize("figure", [
    # The peak (12 Sep 12:00 ICT, 3.5 m), as the moment line and the impact card show it.
    "| 88.7 km² | `88.704` |", "| 16,060 | `16060` |", "| 163.8 km | `163.77` |", "| 4 of 42 |", "| 14.0 of 88.7 km² |",
    # The demo's hours: the GISTDA anchor hour, the onset link and the 15 Sep link (the page's moment line).
    "| 42 | 10 Sep 18:00 ICT", "| 0.10 m | 13.6 km² | 2,667 |", "| 1.26 m | 48.1 km² | 8,211 |", "| 0.24 m | 19.6 km² | 3,559 |",
    # The shelter-set comparison (P2-4): both denominators and the cut-off hours.
    "| 34,525 of 81,799 | 27,439 | 7,086 (21%) |", "| 5,698 of 14,169 | 299 | 5,400 (95%) | 10 Sep 22:00 ICT (hour 46)",
    "| 24,910 of 81,799 | 11,481 | 13,429 (54%) | 11 Sep 10:00 ICT (hour 58)", "| 7,580 of 14,169 | 460 | 7,120 (94%) | 10 Sep 23:00 ICT (hour 47)",
    # The equity gap (R8, option B): within-reach denominators.
    "| 320 of 373 (85.77%) | 13,109 of 24,537 (53.42%) | 1.61× (higher)", "| 0 of 2,440 | 7,086 of 32,085 (22.08%) |",
    # Capacity bounds (P2-9) and the what-if levels (C-1).
    "| 7,580 | 495 | 1,057 | 13,112 to 13,674 |", "| 3,283 | 1,805 | 2,441 | 11,728 to 12,364 |", "| not counted | 2,366 | 3,900 | 10,269 to 11,803 |",
    "| 8,426 | 2,673 | 4,149 | 10,020 to 11,496 |", "| 10,333; 95 sites |", "| 16,069; 94 sites |", "| 5 of 8 |",
    # Sentinel-2 on 15 Sep (P2-7) and VIIRS.
    "| 36.8 km² (61% of the district clear) |", "| 13.8 km² (86% clear) |", "| 25.3 km² (of 177.3 km² clear on both dates) |",
    "| 18.0 km²; 21.4 km² |", "| 7.3 km²; IoU 0.155; 20% |", "| 15 Sep<br>15 ก.ย. | 4% | 292.2 | 46.2 | 19.5 |",
    # Calibration and calibration-informed checks, and the same-track radar pair (P2-10).
    "9.9 km² reported (Mae Sai 6,182 rai); model 13.6 km² at 0.10 m", "about 70 km² and 13,600 people; model 72.2 km² and 12,813 residents in water at 2.65 m",
    "| 19.54 km²; 0.10 m; 22.54 km²; IoU 0.065 |", "| 23.57 km²; 0.10 m; 22.54 km²; IoU 0.074 |",
    # Reported depths (C-2).
    "| 12 (9 points) |", "| 3 | 0 | 9 | 9 |", "| 6 | 3 | 3 | 9 |",
    # The season envelope comparison (P2-3).
    "| IoU 0.48; 60.5%; 70.4% |", "| IoU 0.46; 64.5%; 61.1% |", "| 59.3% against 60.8% |", "| about 17,927; 17,344; 16,060 |", "| 77.74 km²; 76.29 km² |",
    # The export pack (P3-1, P3-2).
    "The export pack: 9 files, 906,375 bytes, ODbL 1.0",
])
def test_the_figures_the_page_and_the_stage_reports_state(text: str, figure: str) -> None:
    assert figure in text


def test_rounding_follows_the_page() -> None:
    # JavaScript toFixed and Math.round round half up on the exact binary value; Python's round would give 0.2 and 2.
    assert numbers.fixed(0.25, 1) == "0.3" and numbers.fixed(2.5, 0) == "3" and numbers.fixed(88.704, 1) == "88.7"
    assert numbers.fixed(1.005, 2) == "1.00"  # 1.005 is just below 1.005 in binary, as in JavaScript
    assert numbers.whole(34524.5) == "34,525" and numbers.whole(7085.7) == "7,086" and numbers.whole(0) == "0"
    assert numbers.percent(0.2052) == "21%" and numbers.percent(0.8577, 2) == "85.77%"


def test_the_stage_follows_the_page_between_and_outside_keyframes() -> None:
    anchors = [{"t": 1.0, "stage_m": 0.0}, {"t": 2.0, "stage_m": 2.0}, {"t": 3.0, "stage_m": 1.0}]
    assert numbers.stage_at(0.0, anchors) == 0.0 and numbers.stage_at(5.0, anchors) == 1.0
    assert numbers.stage_at(1.5, anchors) == 1.0 and numbers.stage_at(2.0, anchors) == 2.0 and numbers.stage_at(2.5, anchors) == 1.5


def test_flooded_area_counts_codes_under_the_stage_without_channel_or_never_cells() -> None:
    histogram = [0.0] * 256
    histogram[0], histogram[1], histogram[2], histogram[255] = 1000, 10, 20, 5000
    assert numbers.wet_sum(histogram, 0.1, 0.05) == 10  # code 2 * 0.05 = 0.1 is not under 0.1
    assert numbers.wet_sum(histogram, 0.11, 0.05) == 30
    with pytest.raises(numbers.ReplayNumbersError, match="256 bins"):
        numbers.wet_sum([0.0] * 10, 1.0, 0.05)


def test_the_python_rules_reproduce_every_baked_day_or_nothing_is_written(files: numbers.ReplayFiles) -> None:
    numbers._check_day_stats(files.manifest)
    broken = copy.deepcopy(dict(files.manifest))
    broken["days"][3]["stats"]["flooded_km2"] += 0.001
    with pytest.raises(numbers.ReplayNumbersError, match="flooded area"):
        numbers._check_day_stats(broken)


def test_a_replay_with_an_accepted_score_or_class_is_refused(files: numbers.ReplayFiles) -> None:
    for key in ("accepted_fpps", "accepted_action_class"):
        manifest = {**files.manifest, key: "A"}
        changed = numbers.ReplayFiles(**{**files.__dict__, "manifest": manifest})
        with pytest.raises(numbers.ReplayNumbersError, match="no accepted priority score"):
            numbers.replay_numbers(changed)


def _copy_served_files(tmp_path: Path) -> Path:
    """A minimal copy of the repository: the manifest constant and the four files the figures read."""
    lib = tmp_path / "apps" / "web" / "src" / "lib"
    lib.mkdir(parents=True)
    shutil.copy(ROOT / "apps" / "web" / "src" / "lib" / "flood-timeline.ts", lib / "flood-timeline.ts")
    manifest_path = numbers.served_manifest_path(ROOT)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hrefs = [manifest["season_envelope"]["files"]["statistics"]["href"], manifest["access"]["nodes"]["href"], manifest["vectors"]["tambons"]["href"]]
    for path in [manifest_path, *(ROOT / "apps" / "web" / "public" / href.lstrip("/") for href in hrefs)]:
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, target)
    return tmp_path


def test_files_that_do_not_match_the_manifest_are_refused(tmp_path: Path) -> None:
    root = _copy_served_files(tmp_path)
    assert numbers.build(root) == DOCUMENT.read_text(encoding="utf-8")
    manifest = json.loads(numbers.served_manifest_path(root).read_text(encoding="utf-8"))
    nodes = root / "apps" / "web" / "public" / manifest["access"]["nodes"]["href"].lstrip("/")
    data = bytearray(nodes.read_bytes())
    data[-1] ^= 1
    nodes.write_bytes(bytes(data))
    with pytest.raises(numbers.ReplayNumbersError, match="access-nodes.bin does not match"):
        numbers.build(root)
    nodes.unlink()
    with pytest.raises(numbers.ReplayNumbersError, match="access-nodes.bin is missing"):
        numbers.build(root)


def test_every_figure_has_a_known_lane_a_source_and_a_thai_label(files: numbers.ReplayFiles) -> None:
    sections = numbers.replay_numbers(files)
    keys = [figure.key for section in sections for figure in section.figures] + [table.key for section in sections for table in section.tables]
    assert len(keys) == len(set(keys)) and len(keys) > 40
    thai = re.compile("[฀-๿]")
    for section in sections:
        assert thai.search(section.title_th) and thai.search(section.note_th), section.key
        for figure in section.figures:
            assert figure.lane in numbers.LANES and figure.source and figure.quote, figure.key
            assert thai.search(figure.label_th), figure.key
        for table in section.tables:
            assert table.lane in numbers.LANES and table.source and thai.search(table.caption_th), table.key
            assert all(len(row) == len(table.header) for row in table.rows), table.key
    lanes = {section.key: {figure.lane for figure in section.figures} | {table.lane for table in section.tables} for section in sections}
    assert lanes["envelope"] == {"SCN-ENV"} and lanes["reported"] == {"REP"} and lanes["calibration"] == {"CAL"}
    assert lanes["access"] == {"SCN"} and lanes["capacity"] == {"SCN"} and "OBS" in lanes["observed"]


def test_season_envelope_figures_keep_their_own_section_credit_and_licence(files: numbers.ReplayFiles, text: str) -> None:
    sections = numbers.replay_numbers(files)
    envelope = next(section for section in sections if section.key == "envelope")
    assert envelope.licence and "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009" in envelope.licence
    assert "CC BY-SA 4.0" in envelope.licence and "Changed by FloodGuard" in envelope.licence
    assert envelope.title_en == "Season envelope comparison (scenario; plausibility, not validation)"
    # No figure of another section is read from the envelope's statistics file.
    for section in sections:
        if section.key != "envelope":
            assert all("envelope.json" not in figure.source for figure in section.figures)
            assert all("envelope.json" not in table.source for table in section.tables)
    assert text.index("## Season envelope comparison") < text.index("Figures in this section are derived from")


def test_no_priority_score_or_action_class_is_quoted(text: str) -> None:
    assert "FPPS" not in text and "Priority Score" not in text
    for match in re.finditer(r"action class", text):
        sentence = text[max(0, match.start() - 60):match.end()]
        assert "no action class" in sentence or "accepted_action_class" in sentence or "no priority score and no action class" in sentence.lower(), sentence


def test_the_document_passes_the_shared_wording_rules(text: str) -> None:
    assert [finding.describe() for finding in find_violations(text, RULES, "replay_numbers.md")] == []
    # Seeded: a figure called an accuracy, or the envelope called observed, is caught in this document too.
    assert find_violations(text.replace("plausibility, not validation", "accuracy 0.48", 1), RULES)
    assert find_violations(text + "\nThe observed envelope covers the town.", RULES)
