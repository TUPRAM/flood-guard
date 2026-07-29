# Task 02 - FPPS Score

## Goal

Implement the first testable version of the Flood Preparedness Priority Score engine.

## Context

Read:

- `AGENTS.md`
- `docs/project_brief.md`
- `docs/model_contract.md`
- `tests/fixtures/sample_population.csv`

## Task

Create `src/floodguard/scoring.py` with functions that:

1. validate required input columns
2. compute the default FPPS score
3. assign A-E action classes
4. generate a short `top_reason` string
5. preserve `subdistrict_id`, `subdistrict_name`, and `confidence_class`

## Constraints

- Use pandas.
- Do not require real satellite data.
- Do not hard-code study-area names.
- Raise clear errors for missing columns.
- Keep functions deterministic.
- Add type hints and docstrings.

## Done When

- `pytest` passes.
- `tests/test_scoring.py` covers normal scoring, missing columns, boundary values, and class assignment.
- The sample fixture produces an output CSV with `fpps_0_100`, `action_class`, and `top_reason`.
