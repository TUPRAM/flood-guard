# M7 candidate FPPS sensitivity and component evidence

Status: **PARTIAL diagnostic tooling; accepted FPPS and A–E class BLOCKED.** The five fixed FPPS weights remain 30/25/20/15/10. Judging weights are unrelated. `src/floodguard/scoring.py` and its class order were not changed.

## Current candidate component meanings

The raw `candidate_flood_scenario` package in `src/floodguard/evidence_flood_scenario.py` currently derives the following for each **AOI intersection**, using modelled population cell centres and a candidate flood extent with imposed road closures:

| FPPS component | Current candidate interpretation | Qualification gap |
| --- | --- | --- |
| Flood likelihood 0–100 | `null` | A fixed SAR amplitude-drop/threshold or an abstaining Gamma0 candidate is not an empirically calibrated probability. A binary observed footprint would still need a versioned policy-severity decision if used as this component. |
| Exposure 0–100 | 100 × candidate-overlapping modelled residents / in-scope modelled residents, only with full candidate observation coverage | Candidate flood/refined population support, normalization frame, uncertainty and exact AOI denominator need review; whole cells are not building or person observations. |
| Access gap 0–100 | 100 × residents on accepted **modelled connectors** beyond 30 minutes or with no scenario route / connected residents | Destination role, connector/barrier, network context, speed and closure/penalty assumptions can dominate. A missing connector cannot be coded as observed no access. |
| Road criticality 0–100 | 100 × modelled residents losing all routes / residents with a baseline route | Reuses the same closure and network as access gap. A flood intersection does not prove road closure. Graph bridge counts are not physical bridge counts. |
| Vulnerability/context 0–100 | `null` | Compatible year/band/geography age counts and an explicit normalization/coverage policy are not yet accepted. District shares are not measured local counts. |

The current candidate exposure, access and road scores are useful scenario indicators, but all three can move with the **same flood geometry and road closure assumption**. Access gap and road criticality also reuse the same route graph and overlapping people. Adding their weighted contributions does not create three independent evidence sources. A later vulnerability term could overlap exposure if it uses raw population totals. Capacity/2SFCA is not a sixth FPPS component. These redundancies require a reviewed component specification and empirical sensitivity before accepted ranking.

## Frozen bounded stress design

`scripts/scoring_sensitivity.py` version `one_at_a_time_and_joint_v1` reads an existing source-bound candidate JSON or a self-hashed finals `analysis.json` with an explicit travel `--mode`. It validates the candidate-only status, event/provenance, area identities and null accepted scores. It records the exact input file SHA-256, context hash, candidate-provenance hash and finals analysis self-hash where applicable. It never opens a decision acceptance path.

The baseline completion **assumes 50** for each missing component while retaining every available candidate component. This is a scenario, not imputation or an accepted score. One-at-a-time variants set each missing component to 0 or 100, shift each known component by ±20 score points (clamped to 0–100), and multiply one requested policy weight by 0.5 or 1.5 before recording the normalized five-weight vector. The 20-point stress and weight multipliers are predeclared diagnostic choices; they are not uncertainty estimates or new defaults.

Four bounded joint variants examine dominant dependency directions: all missing/known components low; all high; high flood component with lower network components; and low flood component with higher network components. Access gap and road criticality shift together because they share road assumptions. This finite ensemble is **not** a confidence interval or a full cross-product. The report gives per-area score/rank ranges, class retention, and the largest one-at-a-time score shift. Source area IDs break rank ties deterministically; reported rank ranges are only within this plan. No scenario is selected as a headline from the size of its effect.

The unchanged scorer is called for every completed scenario. Low source confidence forces Class E with reason `low_confidence`, regardless of arithmetic score. Class E means *monitor and verify*, never safe. Exact class-order tests exercise A before B before C, the 35 score threshold and the low-confidence override. All diagnostic output declares `accepted_fpps=null`, `accepted_action_class=null`, `official_warning=false`, `operational=false`.

## Use and verified boundary

```powershell
uv run --extra evidence pytest -q tests/test_scoring_sensitivity.py
uvx ruff check scripts/scoring_sensitivity.py tests/test_scoring_sensitivity.py
uv run --extra evidence python scripts/scoring_sensitivity.py --input <external-frozen-finals-analysis.json> --mode walking --output <external-new-sensitivity.json>
```

The script uses exclusive output creation: an existing report is not replaced. The automated fixtures cover explicit missing-input assumptions, the hand-calculated 58-point baseline, low-confidence E at high arithmetic scores, weight normalization, rank reversal, exact class boundaries, tampered finals hash and accepted-looking candidate rejection.

An integration diagnostic was subsequently run on the **existing candidate** Mae Sai core package SHA-256 `2f51f7284496778660cde7d518bbc42952666076008040ee1668bd844fa5f93c`. Its embedded finals analysis self-hash is `9a586f224809f042e538ae0342c4d1a7b8ff9a2fd810bd0bf2fb38a0b44d62c2`; the separately extracted external analysis file SHA-256 is `f108cebfefdf8d21e1e15556bc9687c069ec8d448ed8019fddf2c94b7f3ba24b`. The external run at `Project Support/FloodGuard/execution/2026-09-23/mae-sai-scoring-sensitivity-v1` contains walking SHA-256 `086c12185ed9663435961d2fe27ef2a12671cd426c743a137207f6886de68f99` and modelled-vehicle SHA-256 `ab3711ab48f0135ee587e054d767a6e4b722b90c5fdb9c92364e2747b40f5593`. Both report six AOI-intersecting units, null accepted FPPS/class and low-confidence scenario Class E throughout. For example, TH570901's walking arithmetic score ranges 25.20–81.24 and rank 2–5 **within this fixed stress ensemble**. This wide span reflects assumed missing-component extremes and model choices; it is not a confidence interval, an accepted priority or an observed flood effect. No scenario was selected as a headline from its size.

Before an accepted FPPS: qualify the flood likelihood or approve a separate observation-severity policy version, establish compatible age/context, fix the five component denominators and coverage rules, review correlated indicators, obtain accepted downstream road/access/area decisions and satisfy the existing accepted-result ingress. A candidate scenario score or selected model report cannot substitute for those gates.
