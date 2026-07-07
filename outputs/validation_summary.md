# FloodGuard Validation Summary

Generated from fixture-backed outputs. This is not a real flood validation report.

## Decision Narrative

- Current status: fixture-backed decision demo for prioritization, scenario comparison, access loss, equity gap, road risk, and action briefs.
- The dashboard and this report show the decision layer working end to end, but they do not prove real flood-detection accuracy.
- This output is non-operational, not an official warning, and not a real-time sensor.

## What The Fixture Proves

- FPPS scoring, A-E action class assignment, and top-reason generation are deterministic.
- Road-risk, access-loss, equity-gap, scenario, and sensitivity outputs can be joined into dashboard-ready GeoJSON.
- Actionable brief selection favors A/B/C decision classes over a low-confidence numeric score leader.

## Data Readiness Narrative

- Local THEOS-2, Sentinel-1, and DEM assets are cataloged as context/readiness lanes with checksums or blocker states where available.
- Sentinel-1 and DEM context quicklooks are not flood labels, not reference masks, and not agency flood products.
- Real Mae Sai validation is blocked because provider response pending items still control reference-mask use, local processing, and redistribution/reference-only terms.

## What Remains Blocked

- Real IoU, F1/Dice, precision, recall, and area error remain blocked until a legal reference mask exists.
- Real Sentinel-1 baseline processing remains blocked until local paths, checksums, timing, provenance, and reference-mask gates pass.
- Real-data ML remains blocked until the non-ML baseline and legal label gates pass.

## Real Mae Sai Gate Update

- Required before real validation: geometry access, local validation permission, derived metrics permission, screenshots/demo permission, redistribution or reference-only status, ML-label use status, citation, and disclaimers.
- Provider response pending: update `docs/reference_mask_licensing_log.md` and `docs/licensing_outreach_status.md` when UNOSAT/UNITAR or GISTDA replies arrive.

## Fixture Coverage

- Priority rows: 5
- Road-risk rows: 3
- Access-loss rows: 5
- Equity-gap rows: 5

## Priority Score Summary

- Top actionable subdistrict: FG-TB-001 / River Market
- Top actionable class: A
- Top actionable FPPS: 81.60
- Max FPPS: 86.25
- Mean FPPS: 66.96
- Action-class counts: A=1, B=1, C=1, D=1, E=1
- Confidence counts: high=2, medium=2, low=1

## Road Risk Summary

- High-risk road count (>= 0.70): 2
- Max road risk: 0.832
- Mean road risk: 0.699

## Access Loss Summary

- People losing 15-minute access: 100
- People losing 30-minute access: 190
- People losing 60-minute access: 160
- Worst 30-minute access-loss subdistrict: FG-TB-001 / River Market (100 people)

## Equity Gap Summary

- Max numeric equity-gap ratio: 5.999
- Strongest equity-gap subdistrict: FG-TB-002 / Bridge Junction

## Sensitivity Summary

- Stable rank count: 5
- Unstable rank count: 0
- Max rank range: 0
- All fixture ranks are stable because every rank_range is 0.
- Top numeric FPPS row: FG-TB-005 / Unverified Hillside (class E, confidence low). It is not used as the top actionable brief target.

## Future Validation Metrics

- IoU: pending real reference data.
- F1/Dice: pending real reference data.
- precision: pending real reference data.
- recall: pending real reference data.
- area error: pending real reference data.
- Brier score: pending real reference data.
- calibration: pending real reference data.
- road closure precision/recall: pending real reference data.
- score sensitivity: implemented for fixtures; real calibration remains pending.

## Assumptions

- Current metrics are generated from synthetic fixtures only.
- Road-risk outputs are heuristic probabilities, not observed closures.
- Flood extent metrics remain placeholders until real reference masks exist.
