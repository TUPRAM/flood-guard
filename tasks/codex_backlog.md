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

Acceptance: outputs segment-level `road_disruption_probability_0_1`.

## Task 04 - Access-Loss Prototype

Given a road graph, shelters, hospitals, and population points, compare normal versus disrupted access.

Acceptance: outputs people losing 15-, 30-, and 60-minute access.

## Task 05 - Evacuation Equity Gap

Implement vulnerable versus non-vulnerable access-loss rates and ratio.

Acceptance: handles zero denominators and produces interpretation text.

## Task 06 - Action Brief Generator

Generate a Markdown one-page brief for a selected subdistrict.

Acceptance: includes score, class, reasons, confidence, and recommended actions.

## Task 07 - Dashboard-Ready Export

Export priority subdistricts and road-risk segments to GeoJSON.

Acceptance: files open in QGIS or a web-map viewer.

## Task 08 - Validation Report

Generate a simple validation summary with metrics placeholders:

- IoU
- F1/Dice
- precision
- recall
- area error
- score sensitivity

Acceptance: report can be generated from sample fixtures.
