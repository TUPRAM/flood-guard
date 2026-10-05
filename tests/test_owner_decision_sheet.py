"""The owner decision sheet of 5 October 2026 (``docs/owner_decision_sheet_2026-10-05.md``).

The sheet is a dated list of questions for the owners. It decides nothing and no code reads it. These tests hold
four things about it. Its wording passes the shared lint. It places every open point that the engine, radar and
file-format tasks had on that date, and names none that does not exist. Its own counts are the counts of its items.
And it says that nothing on it is decided, cites only decisions the decision log records, and names files that exist.

The list of open points below is the list of that date: a point opened later belongs on a later sheet, not here.
Nothing in this file opens a flood layer or computes a value for a real unit.
"""

from __future__ import annotations

from pathlib import Path
import re

from floodguard.wording_lint import find_violations, load_rules, markdown_section

ROOT = Path(__file__).resolve().parents[1]
SHEET_PATH = ROOT / "docs" / "owner_decision_sheet_2026-10-05.md"
SHEET = SHEET_PATH.read_text(encoding="utf-8")
README = (ROOT / "outputs" / "planning_v1" / "README.md").read_text(encoding="utf-8")
OVERLAY_PAGE = (ROOT / "docs" / "planning_assessment_overlay.md").read_text(encoding="utf-8")
DECISION_LOG = (ROOT / "docs" / "decision-log-d1-d16.md").read_text(encoding="utf-8")
DRAFTS = ROOT / "docs" / "proposal_execution"
RULES = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")

OPEN_POINT = re.compile(r"(?<![A-Za-z0-9])(?:E1|E5|E6|E7|E8|E10|A1|A2|A4)-OP\d+(?![0-9])")
OVERLAY_POINT = re.compile(r"(?<![A-Za-z0-9])E11-\d+(?![0-9])")
# A drive letter that is not the end of a web address scheme, or a home folder.
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|\\Users\\|/home/")
# The open points of 5 October 2026: how many each task had in outputs/planning_v1/README.md.
POINTS_PER_TASK = {"E1": 11, "E5": 8, "E6": 7, "E7": 3, "E8": 9, "E10": 12, "A1": 11, "A2": 2, "A4": 9}
OVERLAY_POINTS = 24
GROUPS = {"A": ("## A. ", "## B. "), "B": ("## B. ", "## C. "), "C": ("## C. ", "## Where the answer is"),
          "D": ("## D. ", "## Things only a person can do")}


def expected_points() -> set[str]:
    points = {f"{task}-OP{number}" for task, count in POINTS_PER_TASK.items() for number in range(1, count + 1)}
    return points | {f"E11-{number}" for number in range(1, OVERLAY_POINTS + 1)}


def group_text(group: str) -> str:
    start, end = GROUPS[group]
    return SHEET[SHEET.index(start):SHEET.index(end)]


def points_in(text: str) -> set[str]:
    return set(OPEN_POINT.findall(text)) | set(OVERLAY_POINT.findall(text))


def count_table() -> dict[str, tuple[int, int]]:
    """Items and named open points of each group, as the table at the head of the sheet states them."""

    rows = {}
    for line in markdown_section(SHEET, "## How many items, and how to answer").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] in GROUPS:
            rows[cells[0]] = (int(cells[2]), int(cells[3]))
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
    placed = set().union(*(points_in(group_text(group)) for group in GROUPS))
    assert expected - placed == set(), "an open point of 5 October 2026 is in no item"
    assert points_in(SHEET) - expected == set(), "the sheet names an open point that no source has"


def test_the_counts_at_the_head_of_the_sheet_are_the_counts_of_its_items() -> None:
    stated = count_table()
    assert set(stated) == set(GROUPS)
    for group in "ABC":
        headings = re.findall(rf"^### {group}(\d+)[ .]", group_text(group), flags=re.MULTILINE)
        assert [int(number) for number in headings] == list(range(1, stated[group][0] + 1)), group
    # The items of group D carry a hyphen (D-1), so that none reads as a decision D1 to D16 of the decision log.
    rows = re.findall(r"^\| D-(\d+) ", group_text("D"), flags=re.MULTILINE)
    assert [int(number) for number in rows] == list(range(1, stated["D"][0] + 1))
    assert not re.search(r"^\| D\d", group_text("D"), flags=re.MULTILINE)
    for group in GROUPS:
        assert len(points_in(group_text(group))) == stated[group][1], group
    assert "adds up to 105" in SHEET and sum(named for _items, named in stated.values()) == 105
    assert f"Group C names {stated['C'][1]} of the 96 open points" in SHEET
    summary = markdown_section(SHEET, "## Summary in ten lines").splitlines()
    assert [line.split(".")[0] for line in summary if re.match(r"\d+\. ", line)] == [str(number) for number in range(1, 11)]
    actions = re.findall(r"^\| P(\d+) \|", SHEET, flags=re.MULTILINE)
    assert [int(number) for number in actions] == list(range(1, 15)) and "(not questions) | 14 |" in SHEET
    # Each change that needs a new protocol version is listed once, and the summary gives their number.
    changes = [line for line in markdown_section(SHEET, "## Where the answer is a new protocol version (v2)").splitlines()
               if line.startswith("|") and not line.startswith(("| Change", "|---"))]
    assert len(changes) == 8 and "Eight possible changes are marked **v2**" in SHEET


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
