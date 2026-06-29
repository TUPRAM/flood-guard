# Codex Backlog - FloodGuard Thailand

## Task 01 - Project Scaffold

Create a Python package layout for FloodGuard. Add `pyproject.toml`, `src/floodguard/`, `tests/`, durable docs, and sample fixtures.

Acceptance: `pytest` runs successfully with at least one real scoring test.

## Task 02 - FPPS Scoring

Implement the Flood Preparedness Priority Score from `docs/model_contract.md`.

Acceptance: scoring tests pass and sample output is generated.

## Task 03 - Road-Disruption Probability

Implement a simple road-risk function using:

- flood probability
- road class
- surrounding inundation proxy
- bridge flag if available

Acceptance: outputs segment-level `road_disruption_probability_0_1` from sample fixtures.

## Task 04 - Access-Loss Prototype

Given a road graph, shelters, hospitals, and population points, compare normal versus disrupted access.

Acceptance: outputs people losing 15-, 30-, and 60-minute access from a deterministic sample graph.

## Task 05 - Evacuation Equity Gap

Implement vulnerable versus non-vulnerable access-loss rates and ratio.

Acceptance: handles zero denominators and produces interpretation text.

## Task 06 - Source Registry

Create a source registry before real study-area data ingestion.

Acceptance: documents candidate sources, licensing/access notes, resolution, time coverage, study-area relevance, and confidence notes.

## Task 07 - Action Brief Generator

Generate a Markdown one-page brief for a selected subdistrict.

Acceptance: includes score, class, reasons, confidence, and recommended actions.

## Task 08 - Dashboard-Ready Export

Export priority subdistricts and road-risk segments to GeoJSON.

Acceptance: files open in QGIS or a web-map viewer.

## Task 09 - Validation Report

Generate a simple validation summary with metrics placeholders:

- IoU
- F1/Dice
- precision
- recall
- area error
- score sensitivity

Acceptance: report can be generated from sample fixtures.

## Task 10 - Action Brief Generator

Generate a one-page Markdown action brief for the highest actionable fixture subdistrict.

Acceptance: includes score, action class, top reason, confidence, access loss, equity gap, road risks, assumptions, and recommended actions.

## Task 11 - Scenario Toggle Prototype

Implement fixture-backed `add_temporary_shelter` and `close_road` scenarios.

Acceptance: reruns access loss and equity gap and writes before/after scenario summaries.

## Task 12 - FPPS Sensitivity Analysis

Run deterministic FPPS weight scenarios and flag unstable rankings.

Acceptance: writes sensitivity rows and rank-instability summary from sample fixtures.

## Task 13 - Study-Area Data Inventory

Document real data acquisition needs for Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025.

Acceptance: inventory is source-backed and explicitly avoids real downloads or remote-sensing model work.

## Task 14 - Bilingual Action Brief V2

Add Thai/English section labels and field-ready non-operational wording to the generated one-page action brief.

Acceptance: `outputs/action_brief_FG-TB-001.md` stays compact, keeps class-specific recommended actions, and says it is not an official warning.

## Task 15 - Scenario GeoJSON Comparison

Merge baseline, temporary-shelter, and road-closure comparison fields into `priority_subdistricts.geojson`.

Acceptance: each priority subdistrict has scenario comparison fields before GeoJSON export; missing comparison rows fail clearly.

## Task 16 - Validation Summary V2

Add a sensitivity section to the validation summary.

Acceptance: `outputs/validation_summary.md` reports stable/unstable rank counts, max rank range, and the low-confidence numeric-top disclaimer.

## Task 17 - Static Dashboard Prototype

Generate a standalone Leaflet dashboard from generated GeoJSON and Markdown outputs.

Acceptance: `outputs/dashboard.html` opens from disk, embeds GeoJSON directly, has layer toggles, and requires no backend.

## Task 18 - Chiang Rai Inventory V2

Record exact candidate Sentinel-1 CDSE metadata for the Mae Sai 2024 planning tile.

Acceptance: inventory lists candidate product ids, access/license status, no-download status, and unresolved flood-mask/licensing blockers.
