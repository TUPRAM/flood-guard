"""Demo readiness documents for the Mae Sai replay (roadmap P4-1).

- Every figure the walkthrough's replay beat says aloud is one ``docs/demo/replay_numbers.md`` lists, so a re-bake that
  moves a figure fails here (through that file's own test) instead of reaching the deck.
- The "words to avoid" table stays in step with the shared wording lint: each phrase on the left is flagged and each
  phrase on the right passes.
- The venue-fallback video recorded in ``docs/demo/README.md`` is the committed file: size, SHA-256, a progressive
  MP4 (seekable, its duration in the header) of 60-90 s at 16:9, and under the 15 MB limit for Git.
- The offline dry-run checklist records the automated result and has a line for the person who signs the dry run.
The links themselves are checked against the page's parser in ``apps/web/src/lib/demo-links.test.ts``.
"""

from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

import pytest

from floodguard.wording_lint import find_violations, load_rules, markdown_section

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
WALKTHROUGH = (ROOT / "docs" / "demo_walkthrough.md").read_text(encoding="utf-8")
STORY = (ROOT / "docs" / "demo_story.md").read_text(encoding="utf-8")
NUMBERS = (DEMO / "replay_numbers.md").read_text(encoding="utf-8")
README = (DEMO / "README.md").read_text(encoding="utf-8")
CHECKLIST = (DEMO / "offline_dry_run_checklist.md").read_text(encoding="utf-8")
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
BEAT = markdown_section(WALKTHROUGH, "## Mae Sai Replay Beat (60-90 s)")
AVOID = markdown_section(WALKTHROUGH, "## Replay Beat: Words To Avoid")
STORY_BEAT = markdown_section(STORY, "## Replay Beat (60-90 s)")
FIGURE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+%")
"""A figure worth checking: a number with a thousands separator, a decimal point or a percent sign."""


def spoken_lines(text: str) -> list[str]:
    """The quoted lines to say aloud, in English ("Say:") and Thai ("พูด:")."""
    return re.findall(r'^\s*- (?:Say|พูด): "(.+)"$', text, flags=re.MULTILINE)


def test_the_beat_has_six_stops_each_with_english_and_thai_lines() -> None:
    lines = spoken_lines(BEAT)
    assert len(lines) == 12
    assert len(re.findall(r"^\d\. \*\*", BEAT, flags=re.MULTILINE)) == 6
    assert all(re.search("[฀-๿]", line) for line in lines[1::2])


def test_the_spoken_lines_fit_a_60_to_90_second_beat() -> None:
    english = spoken_lines(BEAT)[0::2]
    words = sum(len(line.split()) for line in english)
    # At about 160 words a minute, a measured delivery, 160 to 240 words is 60 to 90 seconds.
    assert 160 <= words <= 240, words


def test_every_figure_said_aloud_is_in_the_numbers_file() -> None:
    figures = {figure for line in spoken_lines(BEAT) for figure in FIGURE.findall(line)}
    assert {"48.1", "88.7", "16,060", "21%", "54%", "36.8", "18.0", "0.48"} <= figures
    missing = [figure for figure in sorted(figures) if figure not in NUMBERS]
    assert missing == []
    asked = markdown_section(BEAT, "### If asked")
    assert [figure for figure in FIGURE.findall(asked) if figure not in NUMBERS] == []


def test_the_beat_names_every_label_the_roadmap_requires() -> None:
    for label in ("model reconstruction with low confidence", "observed", "T1 scenario", "calibration anchor", "calibration-informed",
                  "scenario envelope", "not real-time", "no priority score and no action class"):
        assert label in BEAT, label
    for on_screen in ("Calibration anchor (not an independent check)", "Size checks (calibration-informed, not independent)",
                      "Scenario (SCN-ENV): 2024 season envelope", "T1 SCENARIO (MODEL) · EVACUATION ACCESS",
                      "River stage (assumed) and rain (observed)", "Season envelope comparison (scenario; plausibility, not validation)"):
        assert on_screen in BEAT, on_screen


def test_the_replay_sections_pass_the_shared_wording_rules() -> None:
    for source, text in (("demo_walkthrough.md replay beat", BEAT), ("demo_story.md replay beat", STORY_BEAT),
                         ("replay_numbers.md", NUMBERS), ("demo/README.md", README), ("offline_dry_run_checklist.md", CHECKLIST)):
        assert [finding.describe() for finding in find_violations(text, RULES, source)] == [], source


def avoid_rows() -> list[tuple[str, str]]:
    rows = re.findall(r'^\| "(.+)" \| "(.+)" \|$', AVOID, flags=re.MULTILINE)
    assert len(rows) >= 12
    return rows


@pytest.mark.parametrize("phrase", [bad for bad, _ in avoid_rows()])
def test_every_phrase_to_avoid_is_flagged_by_the_lint(phrase: str) -> None:
    assert find_violations(phrase, RULES), phrase


@pytest.mark.parametrize("phrase", [good for _, good in avoid_rows()])
def test_every_phrase_to_say_instead_passes_the_lint(phrase: str) -> None:
    assert find_violations(phrase, RULES) == [], phrase


def test_the_words_to_avoid_cover_every_rule_of_the_lint() -> None:
    covered = {finding.rule for bad, _ in avoid_rows() for finding in find_violations(bad, RULES)}
    missing = [rule for rule in RULES.rule_ids if rule not in covered and rule not in {"equity_denominator", "corroboration", "envelope_verdict"}]
    assert missing == []


def mp4_boxes(data: bytes, start: int = 0, end: int | None = None) -> list[tuple[str, int, int]]:
    """Top-level boxes of an MP4: (type, start, size)."""
    end = len(data) if end is None else end
    boxes, at = [], start
    while at < end:
        size, kind = struct.unpack(">I4s", data[at:at + 8])
        if size == 1:
            size = struct.unpack(">Q", data[at + 8:at + 16])[0]
        boxes.append((kind.decode("latin-1"), at, size))
        at += size
    return boxes


def test_the_video_recorded_in_the_readme_is_the_committed_file() -> None:
    video = DEMO / "mae-sai-replay-demo.mp4"
    data = video.read_bytes()
    assert len(data) < 15_000_000, "over 15 MB the video belongs outside Git (see docs/demo/README.md)"
    assert f"| Size | {len(data):,} bytes |" in README
    assert f"| SHA-256 | `{hashlib.sha256(data).hexdigest()}` |" in README
    kinds = [kind for kind, _, _ in mp4_boxes(data)]
    # A progressive ("fast start") MP4: header first, no fragments, so players can seek and show the length.
    assert kinds[:2] == ["ftyp", "moov"] and "mdat" in kinds and "moof" not in kinds
    _, moov_at, moov_size = mp4_boxes(data)[1]
    mvhd = next((at, size) for kind, at, size in mp4_boxes(data, moov_at + 8, moov_at + moov_size) if kind == "mvhd")
    version = data[mvhd[0] + 8]
    timescale, duration = (struct.unpack(">IQ", data[mvhd[0] + 28:mvhd[0] + 40]) if version == 1
                           else struct.unpack(">II", data[mvhd[0] + 20:mvhd[0] + 28]))
    seconds = duration / timescale
    assert 60 <= seconds <= 90, seconds
    assert f"| Duration | {seconds:.1f} s |" in README
    # The frame size is read from the video track's header, not taken from the README: 16:9, and the size the README gives.
    width, height = video_frame_size(data, moov_at, moov_size)
    assert width * 9 == height * 16, (width, height)
    assert f"{width} × {height} (16:9)" in README and "| Language | English |" in README


def video_frame_size(data: bytes, moov_at: int, moov_size: int) -> tuple[int, int]:
    """Width and height of the video track: the last 8 bytes of its ``tkhd`` box, 16.16 fixed point (ISO/IEC 14496-12).

    Only a track whose ``mdia/hdlr`` handler is ``vide`` counts, and exactly one is expected.
    """
    sizes = []
    for kind, at, size in mp4_boxes(data, moov_at + 8, moov_at + moov_size):
        if kind != "trak":
            continue
        children = {child: (child_at, child_size) for child, child_at, child_size in mp4_boxes(data, at + 8, at + size)}
        mdia_at, mdia_size = children["mdia"]
        hdlr_at = next(child_at for child, child_at, _ in mp4_boxes(data, mdia_at + 8, mdia_at + mdia_size) if child == "hdlr")
        if data[hdlr_at + 16:hdlr_at + 20] != b"vide":  # size, type, version and flags, pre_defined, then the handler type
            continue
        tkhd_at, tkhd_size = children["tkhd"]
        width, height = struct.unpack(">II", data[tkhd_at + tkhd_size - 8:tkhd_at + tkhd_size])
        sizes.append((width >> 16, height >> 16))
    assert len(sizes) == 1, sizes
    return sizes[0]


def test_the_frame_size_reader_takes_the_video_track_header() -> None:
    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I4s", 8 + len(payload), kind) + payload

    def trak(handler: bytes, width: int, height: int) -> bytes:
        tkhd = box(b"tkhd", bytes(4 + 20 + 8 + 8 + 36) + struct.pack(">II", width << 16, height << 16))  # version 0 layout
        hdlr = box(b"hdlr", bytes(8) + handler + bytes(12) + b"\0")
        return box(b"trak", tkhd + box(b"mdia", box(b"mdhd", bytes(24)) + hdlr))

    for size in ((1280, 720), (1080, 1080), (720, 1280)):
        moov = box(b"moov", box(b"mvhd", bytes(100)) + trak(b"soun", 0, 0) + trak(b"vide", *size))
        data = box(b"ftyp", b"isom") + moov
        assert video_frame_size(data, 12, len(moov)) == size
    # The square and portrait shapes the export can also record are not 16:9.
    assert [w * 9 == h * 16 for w, h in ((1280, 720), (1080, 1080), (720, 1280))] == [True, False, False]


def test_the_checklist_records_the_automated_result_and_a_signature_line() -> None:
    assert "`pnpm test:offline`" in CHECKLIST and "**Result:** exit 0" in CHECKLIST
    assert "browser offline smoke:" in CHECKLIST and "Dry run done by" in CHECKLIST and "ผู้ทดสอบ" in CHECKLIST
    for step in ("pnpm build:web", "node scripts/preview-static.mjs 3100", "Airplane mode", "4009", "Thai", "modelled_road_inundation_by_hour.csv"):
        assert step in CHECKLIST, step
