"""Wording lint for the Mae Sai replay (Python side).

Scans the text the bake and the documents put in front of a reader with the rules shared with the web tests
(``apps/web/src/lib/replay-wording-rules.json``): the served manifest, the strings of the bake scripts (the
next manifest) and of the export and shelter-check modules, the reported-shelter source file, the replay documents,
the product 4009 rights record and its notice, and the header of every committed export file. It must pass on the
current text and fail on one seeded bad string per rule.
The web twin is ``apps/web/src/lib/replay-wording-lint.test.tsx``.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from floodguard import replay_exports
from floodguard.wording_lint import (
    WordingRulesError,
    find_violations,
    json_strings,
    lint_texts,
    load_rules,
    markdown_section,
    normalise,
    python_strings,
)

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
RULES_PATH = WEB / "src" / "lib" / "replay-wording-rules.json"
RULES = load_rules(RULES_PATH)
BAKE_SCRIPTS = ("scripts/build_mae_sai_flood_timeline.py", "scripts/mae_sai_timeline_evacuation.py", "scripts/mae_sai_timeline_observations.py",
                # The season-envelope stage writes the product 4009 files: its strings are their text.
                "scripts/mae_sai_timeline_unosat4009.py",
                # The export pack's wording, the returned-sheet messages and the import script's output reach a reader too.
                "src/floodguard/replay_exports.py", "src/floodguard/shelter_validation.py", "scripts/import_shelter_validation.py")
JSON_DOCUMENTS = ("outputs/mae_sai_reported_shelters_2024.json", "docs/proposal_execution/rights_basis_4009_v1.json",
                  "docs/mae_sai_timeline_r4_input_receipt.json", "apps/web/src/lib/__fixtures__/mae-sai-equity-access-parity.json")
TEXT_DOCUMENTS = ("docs/decision-log-d1-d16.md", "docs/proposal_execution/rights_basis_4009_v1_NOTICE.txt")
STUDY_LIBRARY = "docs/studio-study-library.md"
REPLAY_SECTION = "### Case replay: links, exports and offline copy"
EXPORT_HEADER = ("T1 scenario (model) replay of a reconstructed 2024 event for preparedness planning and exercises; illustrative stage "
                 "keyframes; not a forecast, not an observed closure record, not an official warning; non_operational; accepted_* null")


def export_headers() -> list[tuple[str, str]]:
    """Header text of every committed export file: the provenance lines and column header of a CSV, the metadata of
    the GeoJSON layer and the whole README. Data rows are place names and numbers, not copy."""
    folder = manifest_path().parent / replay_exports.EXPORT_FOLDER
    items = []
    for path in sorted(folder.iterdir()):
        data = path.read_bytes()
        if path.suffix == ".csv":
            fields, _, _ = replay_exports.read_export_csv(data)
            text = "\n".join(data.decode("utf-8-sig").split("\n")[:int(fields["header_lines"]) + 1])
        elif path.suffix == ".geojson":
            text = json.dumps(json.loads(data)["metadata"], ensure_ascii=False)
        else:
            text = data.decode("utf-8")
        items.append((f"exports/{path.name} header", text))
    return items


def envelope_files() -> list[tuple[str, str]]:
    """Text of the files derived from product 4009 (``unosat4009/``): every string of the statistics file and the
    whole licence notice. They are 4009 text: precision, recall, accuracy, a validated model and corroboration are
    refused there like anywhere else."""
    folder = manifest_path().parent / "unosat4009"
    document = json.loads((folder / "envelope.json").read_text(encoding="utf-8"))
    return [*((f"unosat4009/envelope.json {path}", text) for path, text in json_strings(document)),
            ("unosat4009/LICENSE", (folder / "LICENSE").read_text(encoding="utf-8"))]


def manifest_path() -> Path:
    """The manifest the page serves, from the one constant in ``flood-timeline.ts``."""
    source = (WEB / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    href = re.search(r'TIMELINE_MANIFEST_URL = "([^"]+)"', source).group(1)
    return WEB / "public" / href.lstrip("/")


def corpus() -> list[tuple[str, str]]:
    """Every ``(source, text)`` the Python side is responsible for."""
    items: list[tuple[str, str]] = []
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    items += [(f"timeline.json {path}", text) for path, text in json_strings(manifest)]
    for script in BAKE_SCRIPTS:
        items += [(script, text) for text in python_strings((ROOT / script).read_text(encoding="utf-8"))]
    for document in JSON_DOCUMENTS:
        items += [(f"{document} {path}", text) for path, text in json_strings(json.loads((ROOT / document).read_text(encoding="utf-8")))]
    for document in TEXT_DOCUMENTS:
        items.append((document, (ROOT / document).read_text(encoding="utf-8")))
    library = (ROOT / STUDY_LIBRARY).read_text(encoding="utf-8")
    items.append((f"{STUDY_LIBRARY} (case replay section)", markdown_section(library, REPLAY_SECTION)))
    items += [(f"{STUDY_LIBRARY} (route table)", line) for line in library.splitlines() if "/studio/cases/mae-sai-2024/" in line]
    items.append(("export header (P3-1 standard sentence)", EXPORT_HEADER))
    items += export_headers()
    items += envelope_files()
    return items


def ids(findings) -> list[str]:
    return sorted({finding.rule for finding in findings})


# --- The shared rules ---------------------------------------------------------------------------------


def test_rules_cover_the_six_banned_groups_and_the_shelter_comparison_rules() -> None:
    assert RULES.rule_ids == (
        "real_time", "live", "forecast", "warning",  # affirmative real-time, live, forecast or warning
        "validation_as_agreement",  # validated, validation or accuracy used for agreement
        "precision_recall",  # precision or recall for product 4009
        "corroboration",  # the season envelope "corroborating" the model, or the reverse
        "envelope_verdict",  # "the model is too low" or "too high" against the season envelope
        "september_extent",  # "September extent", "GISTDA's map"
        "return_period",  # 25-year, 100-year
        "road_schedule",  # schedule or closure plan for modelled roads
        "set_ranking",  # a shelter set or plan called better, best or worse (P2-4)
        "safe_departure",  # the modelled cut-off hour presented as a safe time to leave (P2-4)
        "shelter_directive",  # "open these shelters": the plans list candidates to verify (P2-9)
        "equity_denominator",  # the equity rates stated over all residents counted, not those within reach before the flood (R8)
    )
    assert len(RULES.allow) >= 8


def test_patterns_mean_the_same_in_python_and_javascript() -> None:
    document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    for item in (*document["rules"], *document["allow"]):
        # \b, \w, \d and \s differ between the two engines once Thai text is involved.
        assert not re.search(r"\\[bBwWdDsS]", item["pattern"]), item["id"]


def test_every_seeded_bad_string_is_flagged_with_its_own_rule() -> None:
    for rule in RULES.rules:
        for bad in rule.bad:
            assert rule.id in ids(find_violations(bad, RULES)), f"{rule.id}: {bad}"


def test_every_allowlisted_negation_passes() -> None:
    for allowance in RULES.allow:
        for ok in allowance.ok:
            assert [finding.describe() for finding in find_violations(ok, RULES)] == [], f"{allowance.id}: {ok}"


def test_a_negation_does_not_excuse_an_affirmative_claim_in_the_same_text() -> None:
    assert len(RULES.mixed) >= 5
    for text, expected in RULES.mixed:
        assert ids(find_violations(text, RULES)) == sorted(expected), text


def test_text_is_normalised_like_the_web_linter() -> None:
    assert normalise("GISTDA’s  map\n(see https://gistda.or.th/live/forecast) real‑time") == "GISTDA's map (see ) real-time"
    assert ids(find_violations("GISTDA’s map, real‑time", RULES)) == ["real_time", "september_extent"]
    # En dashes, figure dashes and minus signs read as hyphens, so "real–time" cannot slip past as another word.
    assert normalise("real–time, real‒time, real−time, 10–14 Sep") == "real-time, real-time, real-time, 10-14 Sep"
    assert ids(find_violations("A real–time view", RULES)) == ["real_time"]
    finding = find_violations("x" * 60 + " a live map " + "y" * 60, RULES, "seed")[0]
    assert (finding.rule, finding.match, finding.source) == ("live", "live", "seed")
    assert len(finding.context) == 84 and "live" in finding.describe()


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("แผนที่น้ำท่วมตามเวลาจริง", "real_time"), ("คาดการณ์น้ำท่วม", "forecast"), ("ทำนายระดับน้ำ", "forecast"),
        ("แบบจำลองแม่นยำ 48%", "validation_as_agreement"), ("ผ่านการตรวจสอบแล้ว", "validation_as_agreement"),
        ("ประกาศเตือน", "warning"), ("คาบการเกิดซ้ำ 100 ปี", "return_period"), ("รอบ ๑๐๐ ปี", "return_period"), ("รอบ ๒๕ ปี", "return_period"),
        ("100 yr flood", "return_period"), ("Flood alert", "warning"), ("the plan is the better option", "set_ranking"),
    ],
)
def test_the_usual_thai_renderings_of_a_banned_claim_are_flagged(text: str, rule: str) -> None:
    # A translator's wording of a banned English claim must fail too, not only the one spelling listed first.
    assert rule in ids(find_violations(text, RULES)), text


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("Precision against product 4009: 0.61", "precision_recall"), ("Recall of the season envelope: 0.70", "precision_recall"),
        ("Accuracy against the season envelope: 48%", "validation_as_agreement"), ("The model is validated by product 4009", "validation_as_agreement"),
        ("The season envelope corroborates the modelled peak", "corroboration"), ("59% corroboration of the low-confidence water", "corroboration"),
        ("Against the envelope the model is too low in town", "envelope_verdict"), ("The model is likely too high in Ban Dai", "envelope_verdict"),
        ("Ban Dai is over-predicted", "envelope_verdict"), ("Compared with the September extent of product 4009", "september_extent"),
        ("GISTDA's map of the season", "september_extent"),
        ("ขอบเขตน้ำตลอดฤดูช่วยยืนยันแบบจำลอง", "corroboration"), ("แบบจำลองต่ำเกินไปในเขตเมือง", "envelope_verdict"),
    ],
)
def test_text_about_the_season_envelope_may_not_claim_a_score_or_a_verdict(text: str, rule: str) -> None:
    assert rule in ids(find_violations(text, RULES)), text


def test_the_season_envelope_wording_that_is_asked_for_passes() -> None:
    for allowed in (
        "Plausibility against a season envelope, not a validation.",
        "Season envelope comparison (scenario; plausibility, not validation)",
        "60% of the modelled water lies inside the envelope; the modelled water reaches 70% of the envelope.",
        "The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.",
        "Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.",
    ):
        assert find_violations(allowed, RULES) == [], allowed


def test_a_denial_covers_only_what_it_denies() -> None:
    for denial in ("ไม่ใช่แผนที่ตามเวลาจริง", "ไม่ใช่การคาดการณ์", "ยังไม่ผ่านการตรวจสอบภาคสนาม", "ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ", "ไม่ใช่ความแม่นยำ",
                   "It is a model, not real-time or a warning.", "not real-time, not an official warning"):
        assert find_violations(denial, RULES) == [], denial
    # "not real-time" does not excuse a warning joined with a comma or "and"; only "or" shares the one "not".
    assert ids(find_violations("not real-time, warning: flooding expected", RULES)) == ["warning"]
    assert ids(find_violations("This is not real-time and an official warning", RULES)) == ["warning"]
    assert ids(find_violations("ไม่ใช่ข้อมูลเรียลไทม์และคำเตือนอย่างเป็นทางการ", RULES)) == ["warning"]
    document = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    assert "has not signed the list off yet" in document["thai_terms_review"]


def test_a_malformed_rules_file_is_refused(tmp_path: Path) -> None:
    def refuse(document: dict, message: str) -> None:
        path = tmp_path / "rules.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(WordingRulesError, match=message):
            load_rules(path)

    rule = {"id": "live", "pattern": "live", "message": "m", "bad": ["live"]}
    refuse({"rules": []}, "non-empty rules")
    refuse({"rules": [{**rule, "pattern": "("}]}, "does not compile")
    refuse({"rules": [{**rule, "bad": []}]}, "at least one example")
    refuse({"rules": [rule, rule]}, "unique")
    refuse({"rules": [{**rule, "message": " "}]}, "non-empty message")


# --- Current text -----------------------------------------------------------------------------------------


def test_corpus_covers_manifest_bake_scripts_documents_and_export_header() -> None:
    sources = [source for source, _ in corpus()]
    assert sum(source.startswith("timeline.json") for source in sources) > 100
    for needle in (*BAKE_SCRIPTS, *TEXT_DOCUMENTS, "export header", "exports/modelled_road_inundation_by_hour.csv header", "exports/README_licences.txt header"):
        assert any(source.startswith(needle) for source in sources), needle
    for document in JSON_DOCUMENTS:
        assert any(source.startswith(document) for source in sources), document
    text = "\n".join(text for _, text in corpus())
    # The corpus really holds the standing disclaimers, so passing is not an empty result.
    assert "Not a real-time product or an official warning" in text
    assert "not a spatial validation of the model" in text
    assert "not field-validated" in text
    assert "ไม่ใช่การเตือนภัยอย่างเป็นทางการ" in text
    assert "never a validation" in text
    # Product 4009 text is in the corpus: the stage's strings, the statistics file and the licence notice.
    assert sum(source.startswith("unosat4009/envelope.json") for source in sources) > 30 and "unosat4009/LICENSE" in sources
    assert "Plausibility against a season envelope, not a validation." in text
    assert "Season envelope comparison (scenario; plausibility, not validation)" in text


def test_no_banned_wording_in_todays_replay_text() -> None:
    findings = lint_texts(corpus(), RULES)
    assert [finding.describe() for finding in findings] == []


@pytest.mark.parametrize("rule_id", RULES.rule_ids)
def test_lint_fails_on_one_seeded_bad_string_per_rule(rule_id: str) -> None:
    rule = next(rule for rule in RULES.rules if rule.id == rule_id)
    items = corpus()
    targets = ("timeline.json $.limitations[0]", "scripts/build_mae_sai_flood_timeline.py", "docs/decision-log-d1-d16.md",
               "export header (P3-1 standard sentence)",
               # Product 4009 text: the stage's strings, the statistics file and the licence notice.
               "scripts/mae_sai_timeline_unosat4009.py", "unosat4009/envelope.json $.comparison.use", "unosat4009/LICENSE")
    for target in targets:
        index = next(i for i, (source, _) in enumerate(items) if source == target)
        seeded = list(items)
        seeded[index] = (target, f"{items[index][1]} {rule.bad[0]}")
        findings = lint_texts(seeded, RULES)
        assert rule_id in ids(findings), f"{rule_id} planted in {target}"
        assert {finding.source for finding in findings} == {target}


def test_export_headers_are_linted_like_any_other_text() -> None:
    assert find_violations(EXPORT_HEADER, RULES, "header") == []
    # The sentence the roadmap fixed is the one the writer puts into every file.
    assert replay_exports.EXPORT_TIER == EXPORT_HEADER
    headers = export_headers()
    assert len(headers) == 8 and all(EXPORT_HEADER in text for _, text in headers)
    assert all(replay_exports.EXPORT_TIER_TH in text for _, text in headers)
    seeded = [(source, text.replace("not an observed closure record", "the road closure schedule")) for source, text in headers]
    assert ids(lint_texts(seeded, RULES)) == ["road_schedule"]
    assert ids(find_violations("# road_closure_schedule.csv - road closure schedule by hour", RULES)) == ["road_schedule"]
    assert ids(find_violations("# modelled_road_inundation_by_hour.csv - modelled, not observed", RULES)) == []
    assert ids(find_violations("# 100-year flood; forecast for district officers", RULES)) == ["forecast", "return_period"]


# --- What counts as text ---------------------------------------------------------------------------------------


def test_python_strings_skip_docstrings_and_keep_literals_and_f_strings() -> None:
    source = '''
"""Module docstring: not a validated extent, a real-time product or a warning."""

LIMITS = ["Not a real-time product or an official warning."]

def describe(stage):
    """Function docstring with a live forecast."""
    return f"Stage {stage} m, live"  # A comment with a warning.
'''
    assert sorted(python_strings(source)) == ["Not a real-time product or an official warning.", "Stage  {...}  m, live"]


def test_json_strings_skip_addresses_and_hashes_and_never_read_keys() -> None:
    document = {"official_warning": False, "note": "A live map", "url": "https://example.org/live", "urls": ["https://example.org/forecast"],
                "layers": [{"href": "/studies/live.png", "sha256": "ab", "label": {"en": "Flood forecast"}}]}
    assert list(json_strings(document)) == [("$.note", "A live map"), ("$.layers[0].label.en", "Flood forecast")]


def test_markdown_section_stops_at_the_next_heading_of_the_same_level() -> None:
    text = "# Title\n\n### A\nfirst\n#### A.1\ninner\n### B\nsecond\n"
    assert markdown_section(text, "### A") == "### A\nfirst\n#### A.1\ninner"
    assert markdown_section(text, "### B") == "### B\nsecond"
    with pytest.raises(WordingRulesError, match="heading not found"):
        markdown_section(text, "### C")
    library = (ROOT / STUDY_LIBRARY).read_text(encoding="utf-8")
    assert "TIMELINE_MANIFEST_URL" in markdown_section(library, REPLAY_SECTION)
