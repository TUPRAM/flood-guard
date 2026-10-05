"""The owner decision sheet of 5 October 2026 (``docs/owner_decision_sheet_2026-10-05.md``).

The sheet is a dated list of questions for the owners. It decides nothing and no code reads it. These tests hold
five things about it. Its wording passes the shared lint. It places every open point that the engine, radar and
file-format tasks had on that date, and names none that does not exist. Its own counts are the counts of its items.
It says that nothing on it is decided, cites only decisions the decision log records, and names files that exist.
And what a review of 5 October 2026 found is still mended: the sentences it quotes are the sentences of the files
it names, no reply id can be taken for a plan task or a class, and no recommendation rests on a reading that a
source does not hold.

The list of open points below is the list of that date: a point opened later belongs on a later sheet, not here.
Nothing in this file opens a flood layer or computes a value for a real unit.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re

from floodguard.wording_lint import find_violations, load_rules, markdown_section

ROOT = Path(__file__).resolve().parents[1]
SHEET_PATH = ROOT / "docs" / "owner_decision_sheet_2026-10-05.md"
SHEET = SHEET_PATH.read_text(encoding="utf-8")
FLAT = " ".join(SHEET.split())
README = (ROOT / "outputs" / "planning_v1" / "README.md").read_text(encoding="utf-8")
OVERLAY_PAGE = (ROOT / "docs" / "planning_assessment_overlay.md").read_text(encoding="utf-8")
DECISION_LOG = (ROOT / "docs" / "decision-log-d1-d16.md").read_text(encoding="utf-8")
DRAFTS = ROOT / "docs" / "proposal_execution"
V1A = json.loads((DRAFTS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")

OPEN_POINT = re.compile(r"(?<![A-Za-z0-9])(?:E1|E5|E6|E7|E8|E10|A1|A2|A4)-OP\d+(?![0-9])")
OVERLAY_POINT = re.compile(r"(?<![A-Za-z0-9])E11-\d+(?![0-9])")
# A drive letter that is not the end of a web address scheme, or a home folder.
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|\\Users\\|/home/")
# The open points of 5 October 2026: how many each task had in outputs/planning_v1/README.md.
POINTS_PER_TASK = {"E1": 11, "E5": 8, "E6": 7, "E7": 3, "E8": 9, "E10": 12, "A1": 11, "A2": 2, "A4": 9}
OVERLAY_POINTS = 24
PARTS = {"1": ("## Part 1. ", "## Part 2. "), "2": ("## Part 2. ", "## Part 3. "),
         "3": ("## Part 3. ", "## Where the answer is"), "4": ("## Part 4. ", "## Things only a person can do")}
QUESTIONS = 55
ACTIONS = 18


def expected_points() -> set[str]:
    points = {f"{task}-OP{number}" for task, count in POINTS_PER_TASK.items() for number in range(1, count + 1)}
    return points | {f"E11-{number}" for number in range(1, OVERLAY_POINTS + 1)}


def part_text(part: str) -> str:
    start, end = PARTS[part]
    return SHEET[SHEET.index(start):SHEET.index(end)]


def item_text(number: int) -> str:
    """The text of one question of parts 1 to 3: from its heading to the next heading."""

    start = re.search(rf"^### Q{number}[ .]", SHEET, flags=re.MULTILINE)
    assert start is not None, f"Q{number} has no heading"
    following = re.search(r"^##+ ", SHEET[start.end():], flags=re.MULTILINE)
    return SHEET[start.start():start.end() + (following.start() if following else len(SHEET))]


def points_in(text: str) -> set[str]:
    return set(OPEN_POINT.findall(text)) | set(OVERLAY_POINT.findall(text))


def count_table() -> dict[str, tuple[int, int]]:
    """Items and named open points of each part, as the table at the head of the sheet states them."""

    rows = {}
    for line in markdown_section(SHEET, "## How many items, and how to answer").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] in PARTS:
            rows[cells[0]] = (int(cells[2]), int(cells[4]))
    return rows


def test_the_sheet_passes_the_shared_wording_lint_and_names_no_machine_path() -> None:
    assert [finding.describe() for finding in find_violations(SHEET, RULES, SHEET_PATH.name)] == []
    # The standing denials are really there, so passing is not an empty result.
    assert "not an official warning" in SHEET and "class E never means" in SHEET and "not an observation of any day" in SHEET
    data = SHEET_PATH.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n"), "LF line endings"
    assert not LOCAL_PATH.search(SHEET), "the sheet names a path on one machine"


def test_every_open_point_of_that_date_is_placed_and_none_is_invented() -> None:
    expected = expected_points()
    assert len(expected) == 96
    # The list of that date is the list the sources hold: every id is in the README, and the page has 24 points.
    assert {point for point in expected if not point.startswith("E11-")} <= set(OPEN_POINT.findall(README))
    numbered = re.findall(r"^(\d+)\. \*\*", markdown_section(OVERLAY_PAGE, "## Points the protocols leave open"), flags=re.MULTILINE)
    assert [int(number) for number in numbered] == list(range(1, OVERLAY_POINTS + 1))
    placed = set().union(*(points_in(part_text(part)) for part in PARTS))
    assert expected - placed == set(), "an open point of 5 October 2026 is in no item"
    assert points_in(SHEET) - expected == set(), "the sheet names an open point that no source has"


def test_the_counts_at_the_head_of_the_sheet_are_the_counts_of_its_items() -> None:
    stated = count_table()
    assert set(stated) == set(PARTS)
    # One run of numbers through the whole sheet: headings in parts 1 to 3, table rows in part 4.
    first = 1
    for part in "123":
        headings = [int(number) for number in re.findall(r"^### Q(\d+)[ .]", part_text(part), flags=re.MULTILINE)]
        assert headings == list(range(first, first + stated[part][0])), part
        first += stated[part][0]
    rows = [int(number) for number in re.findall(r"^\| Q(\d+) ", part_text("4"), flags=re.MULTILINE)]
    assert rows == list(range(first, first + stated["4"][0])) and rows[-1] == QUESTIONS
    assert f"numbered Q1 to Q{QUESTIONS}" in SHEET
    for part in PARTS:
        assert len(points_in(part_text(part))) == stated[part][1], part
    total = sum(named for _items, named in stated.values())
    assert f"adds up to {total}" in SHEET
    assert f"Part 3 names {stated['3'][1]} of the 96 open points" in SHEET
    summary = markdown_section(SHEET, "## Summary in ten lines").splitlines()
    assert [line.split(".")[0] for line in summary if re.match(r"\d+\. ", line)] == [str(number) for number in range(1, 11)]
    actions = re.findall(r"^\| (\d+) \|", markdown_section(SHEET, "## Things only a person can do"), flags=re.MULTILINE)
    assert [int(number) for number in actions] == list(range(1, ACTIONS + 1))
    assert f"(not questions) | {ACTIONS} | actions 1 to {ACTIONS} |" in SHEET
    # Each change that needs a new protocol version is listed once, and the summary gives their number.
    changes = [line for line in markdown_section(SHEET, "## Where the answer is a new protocol version (v2)").splitlines()
               if line.startswith("|") and not line.startswith(("| Change", "|---"))]
    assert len(changes) == 7 and "Seven possible changes are marked **v2**" in SHEET


def test_the_sheet_decides_nothing_and_cites_only_what_exists() -> None:
    assert "Status: **PENDING**" in SHEET and "A recommendation is not a decision." in SHEET
    # The three drafts it names exist. Whether each is still pending is held by tests/test_owner_unblocker_records.py:
    # this sheet is dated, and an owner's later answer changes the draft and that test, not this file.
    for name in ("rights_basis_sentinel1_v1.json", "rights_basis_sentinel1_v1_NOTICE.txt", "age_data_purpose_review_v1.md",
                 "walking_build_compute_window_v1.md"):
        assert name in SHEET and (DRAFTS / name).is_file(), name
    # Every decision the sheet cites is a row of the decision log; it cites none that the log does not record.
    # ("plan task R2b" is a task of the plan, not a decision.)
    cited = set(re.findall(r"(?<![A-Za-z0-9-])(?<!task )([DR]\d+)(?![0-9])", SHEET))
    recorded = set(re.findall(r"^\| ([DR]\d+b?) \|", DECISION_LOG, flags=re.MULTILINE))
    assert cited and cited <= recorded, sorted(cited - recorded)
    # No tambon stands beside a score or a class: a line that names a tambon code states no class.
    for line in SHEET.splitlines():
        if re.search(r"TH57\d{4}", line):
            assert not re.search(r"(?<![A-Za-z])class [A-E](?![A-Za-z])|FPPS", line), line


# --- What the review of 5 October 2026 found, held so that it stays mended --------------------------------------


def test_no_reply_id_can_be_taken_for_a_plan_task_a_class_or_a_decision() -> None:
    """Questions are Q and a number. A1, A4, C7, D6 and the letters A to E mean other things in the same text."""

    headings = re.findall(r"^#{2,3} (.+)$", SHEET, flags=re.MULTILINE)
    assert not [heading for heading in headings if re.match(r"[A-D]-?\d+[ .(]|[A-D]\. ", heading)]
    body = SHEET[:SHEET.index("- **Ids of the first version.**")]
    assert not re.search(r"^\| (?:[A-D]-?\d+|P\d+) [|(]", body, flags=re.MULTILINE), "a table row has an id of the first version"
    # A reply names a question and "yes", "seen" or an option number, never a letter that could be a class.
    replies = re.findall(r"`(Q\d+[^`]*)`", SHEET)
    assert len(replies) > QUESTIONS - 21
    for reply in replies:
        assert not re.search(r"^Q\d+ [A-Ea-e](?![a-z])", reply), reply
    # Every question of parts 1 to 3 says how to answer it, and the table of first-version ids is there for old answers.
    for number in range(1, 35):
        assert re.search(rf"`Q{number} ", item_text(number)), f"Q{number} gives no reply"
    assert "| A4, A5, A6 | Q7, Q8, Q9 |" in SHEET and "| D-1 to D-21 | Q35 to Q55 |" in SHEET
    # The words the sheet uses are explained once, in one line each.
    words = markdown_section(SHEET, "## Words used")
    for word in ("Anchor", "P10 and P90", "default cell", "Closure level", "Leave-one-out", "Lane", "Tier T0 to T4", "Would-be class",
                 "Skill bar", "Parser; fixture", "superseding run", "`--replace --reason`", "Lineage", "Guardrail", "DR-B04", "DDPM; JRC",
                 "Raster, vector", "warp; control points", "second-order polynomial", "affine", "Radar shadow, layover", "GEOID sample",
                 "UTM zone 47N", "UN-SPIDER, M1-literal, M1-v2", "| dB |", "Bake", "Knot", "Parity fixture", "Equity 2.0",
                 "Referrer header", "Level-5 check", "squash, rebase", "Git hook", "scenarios S3", "SE2-dist",
                 "15 September 2024, 23:16 UTC, which is 16 September, 06:16 in Thailand"):
        assert word in words, word


def test_the_sentinel1_question_quotes_both_manifest_notes_word_for_word() -> None:
    """Q7 asks about a note. The manifest has two copies with two wordings, and decision R14 quotes one of them."""

    question = " ".join(item_text(7).split())
    manifest_path = ROOT / "outputs" / "cdse_mae_sai_acquisition_manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    committed = {row["reason_blocked"] for row in rows}
    assert len(rows) == 2 and len(committed) == 1 and {row["processing_allowed"] for row in rows} == {"False"}
    receipt = json.loads((ROOT / "outputs" / "planning_v1" / "radar_o1_mae_sai_v1_receipt.json").read_text(encoding="utf-8"))
    outside = {receipt["inputs"][key]["acquisition_manifest"]["reason_in_the_manifest"] for key in ("pre_event_safe", "post_event_safe")}
    assert len(outside) == 1 and committed != outside
    for words, sha256 in ((committed.pop(), hashlib.sha256(manifest_path.read_bytes()).hexdigest()),
                          (outside.pop(), receipt["inputs"]["acquisition_manifest"]["sha256"])):
        assert f'"{words}"' in question and f"`{sha256}`" in question
    # R14 quotes the words of the copy outside Git, and the sheet says so instead of calling the two one note.
    r14 = next(line for line in DECISION_LOG.splitlines() if line.startswith("| R14 |"))
    assert "do not run baseline yet" in r14 and "decision-eligible" not in r14
    assert "Decision R14 quotes the words of the copy outside Git" in question and "the same note" not in question
    assert 'is loading an O1 candidate into a planning score (an FPPS and a class) "decision-eligible processing"' in question
    assert "**Part 1 depends on your reading, so there are two branches.**" in question
    # What the scope local stops, the replay's use of one of the two archives, the register's last cell and E1-OP9.
    assert "| What scope `local` stops | The O1 chip on Command can never fill" in question
    timeline = (ROOT / "scripts" / "build_mae_sai_flood_timeline.py").read_text(encoding="utf-8")
    record = json.loads((DRAFTS / "rights_basis_sentinel1_v1.json").read_text(encoding="utf-8"))
    assert next(scene["file_name"] for scene in record["scenes"] if scene["role"] == "pre_event") in timeline
    assert "reads the 3 September archive of this record (the same file)" in question
    register = (DRAFTS / "SOURCES_AND_RIGHTS.md").read_text(encoding="utf-8")
    row = next(line for line in register.splitlines() if line.startswith("| Copernicus Sentinel-1 original SAFE |"))
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    assert len(cells) == 6 and cells[5] == "Separate accepted-input receipt required"
    for cell in cells[1:]:
        assert f'"{cell}"' in question, cell
    assert "E1-OP9" in question and "For Sentinel-1 every candidate is refused today" in question
    assert "four on the Copernicus legal notice and one on the terms page of the Copernicus Data Space" in question
    assert "five on the Copernicus legal notice" not in FLAT


def test_the_age_question_says_what_pitch_use_only_costs_and_quotes_the_register() -> None:
    question = " ".join(item_text(2).split())
    assert "keeps the pitch whole" not in FLAT
    assert "no page of the site can read a score: not the Command columns, not the public band, not the briefs" in question
    assert "Scores can appear on slides or screenshots only" in question
    gr6 = next(item for item in V1A["guardrails"] if item["id"] == "GR6_publication_eligibility")
    assert "Only public overlays may be written to apps/web/public/" in gr6["rule"]
    register = (DRAFTS / "SOURCES_AND_RIGHTS.md").read_text(encoding="utf-8")
    for cell in ("Catalog states CC BY 4.0 with an ODbL caveat for some building/OSM-derived products; hosted age derivatives still "
                 "await product-specific attribution/share-alike review. Age bytes and detailed results remain in configured external roots.",
                 "Age-vulnerability score and accepted group access remain unavailable; a mixed-vintage scenario sensitivity may be "
                 "shown only with its own label."):
        assert cell in register and f'"{cell}"' in question
    assert register.startswith("# Source and purpose status for the proposed release\n\nChecked 23 September 2026.")
    assert "checked 23 September 2026" in question and "whether it replaces these two statements" in question


def test_the_order_the_dates_and_the_single_points_the_review_asked_for() -> None:
    # The gate of R18, the older ranking of R17 and the rights record of product 4009 stand in part 1, before the radar items.
    titles = {int(number): title for number, title in re.findall(r"^### Q(\d+) (.+)$", SHEET, flags=re.MULTILINE)}
    assert "decision R18" in titles[4] and "decision R17, point g" in titles[5] and "product 4009" in titles[6]
    assert "Sentinel-1" in titles[7] and "walking build" in titles[8] and "radar layers" in titles[9]
    # The dated list opens the sheet, before the summary.
    dates = markdown_section(SHEET, "## Dates first")
    assert SHEET.index("## Dates first") < SHEET.index("## Summary in ten lines")
    for words in ("Overdue (was due Fri 2 Oct)", "| Tue 6 Oct |", "| Sat 10 Oct |"):
        assert words in dates, words
    assert "by when (the roadmap says by Tue 6 Oct)" in DECISION_LOG
    assert "If you have ten minutes" not in SHEET
    # The preview that exists and the page that has none are two questions, and the page's question gives the commands.
    assert "PR #43 waits for the owner to look at its preview." in DECISION_LOG and '"PR #43 waits for the owner to look at its preview."' in item_text(10)
    assert "no preview of it exists" in item_text(11) and "`pnpm --filter @floodguard/web dev`" in item_text(11)
    assert "The agent does not push without your approval." in item_text(11)
    # Point h of R17 is asked, and the terrain mask of the signed protocol has its own answer.
    assert "(h) The compact form of the map-background notice on the Public page" in DECISION_LOG
    assert "decision R17, point h" in titles[19]
    limits = V1A["geoid_split"]["limits"]
    sentence = next(item for item in limits if "HAND/slope mask is applied on Mae Sai" in item)
    assert f'"{sentence}"' in " ".join(item_text(30).split())
    assert points_in(item_text(30)) == {"A4-OP2"} and "A4-OP2" not in item_text(29)
    assert "**1. Record the deviation.**" in item_text(30) and "**2. v2 with limits.**" in item_text(30)
    # Three places where the first version said more than its source.
    assert "your own choice 12" not in FLAT and "the reasoning of your yes" not in FLAT
    assert "R17 records your yes and gives no reason of yours" in " ".join(item_text(5).split())
    assert "fit for use at road level" not in FLAT and "It is the only run on disk without the 680 m shift." in item_text(9)
    assert "nobody on the team can check" not in FLAT and "goes against the plan's own recommendation" in item_text(17)
    # What the README says of the stability rule: retention over the re-runs made is a choice it leaves to the owners.
    assert "The owners say whether retention may be taken over the cells that can be run" in " ".join(README.split())
    assert "**Part 5 (E10-OP1), a choice the README lists as yours:**" in item_text(3) and "within its tambon" in item_text(3)
    assert "Whether a 2020 count of the frame lies in a 1 km cell with no 2024 total was not measured here." in README
    assert 'the plan lists its conditional cuts "in order".' in item_text(3)
    # The four actions the review missed.
    actions = markdown_section(SHEET, "## Things only a person can do")
    for words in ("approve the push for a preview, or run it locally", "access gap and road criticality are both 100",
                  "Rachmania owns this lane and has not yet reviewed the runs", "Install the Git hook of the guard"):
        assert words in actions, words
    diagnosis = (DRAFTS / "automated_track" / "WHY_THRESHOLD_ONLY_FAILED.md").read_text(encoding="utf-8")
    assert "Rachmania owns this lane and has not yet reviewed the runs" in " ".join(diagnosis.split())
