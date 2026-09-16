# Mae Sai historical planning rehearsal: evidence and acceptance

This preview is a reproducible **non-operational planning rehearsal**. It is not a validated reconstruction of the 2024 event, an official warning, a resident reporting service or safe-route guidance. No local reference accuracy or operating-partner acceptance is claimed.

## Reproduce the committed package

From the repository root:

```powershell
uv sync --project services/api --group dev --frozen
uv run --project services/api --frozen python scripts/build_mae_sai_planning_demo.py
uv run --project services/api --frozen python scripts/build_mae_sai_planning_demo.py --check
uv run --project services/api --frozen pytest tests/test_mae_sai_planning_demo.py tests/test_scenarios.py
```

The builder calls the existing `MaeSaiCandidateAdapter` and Python access/equity engine. The adapter validates immutable input manifests, checksums, columns, graph joins and registered scenario identities. The resulting JSON is imported by the browser; changing the selected scenario does not execute a browser implementation of the model. `--check` regenerates all results and compares the exact UTF-8 output. The package digest covers canonical JSON excluding its own digest; source files and computational code have individual SHA-256 digests. The release-record timestamp is fixed for deterministic regeneration and is separate from source acquisition and original input-processing timestamps.

## What the numbers mean

The baseline already contains heuristic disruption. New access loss means a population node had access to at least one pooled candidate facility within 30 minutes on the normal graph and loses that access on the disrupted graph. Baseline underserved population has no such normal-network access and is counted separately, not included as newly losing access. Population comes from WorldPop modelled estimates, including fractional values, not a census headcount. API loss counts are rounded to whole people and overall totals may differ slightly from sums of separately rounded area results.

The graph uses all eight committed Mae Sai areas and allows cross-area connectivity. Its recomputed baseline loss results match the archived ADM3 priority summaries within whole-person rounding. The UI retains the original FPPS values and action classes as separately labelled historical context; `fpps_recalculated=false` is mandatory. Graph population and archived source population have small rounding differences and remain separately identified. Do not substitute scenario loss into FPPS or silently overwrite the published baseline.

The closure scenario removes the registered candidate connection, `MS-EDGE-0008687`. The facility scenario adds the registered candidate location, `N-99.9742609-20.4457677`, to both normal and disrupted graphs, matching existing engine semantics. Therefore its change compares scenario-specific access-loss definitions, not a fixed cohort of people rescued or allocated a shelter place. Facility capacity, function-specific demand, queueing, transport constraints and safe routes are not modelled. Facilities are unverified candidates and service types are pooled.

Equity is a ratio of loss rates for a terrain/remoteness proxy versus its complement. It is not independently measured demographic equity. A ratio of 1 when both groups lose nobody is an existing engine convention, not affirmative evidence of equal service provision. Undefined ratios remain unavailable.

## External local-validation protocol — not completed

1. Agree one intended claim and its geography with a responsible reviewer: water at a specified acquisition, newly inundated land, or cumulative event extent. Record the reference's licence, permission, identity and acquisition time before using it. A blocked reference remains blocked.
2. Reconcile dates before evaluating: this case combines a September 2024 Sentinel-1 observation, WorldPop 2020 and a July 2026 OSM extract. Obtain event-time road/facility evidence or explicitly restrict the task to a retrospective planning scenario. Current road geometry cannot establish event-time connectivity.
3. Predefine independent held-out sampling across flooded/non-flooded areas, permanent water, built-up areas, vegetation and difficult/unknown coverage. Fix interpretation rules, adjudication and exclusions before measuring accuracy. Report numerator, denominator, uncertainty and coverage; do not translate a non-Thai benchmark into local accuracy.
4. Validate downstream claims independently: identify the actual road/bridge represented by graph edges, its time-specific passability and alternative links; confirm facility location, function, operating status and access. Separate observed evidence from heuristic delay and closure assumptions. Verify pre-existing lack of access separately from new disruption.
5. Review population suitability and the proxy vulnerability definition with the intended users. A defensible hydrological observation does not automatically validate population exposure, graph access, demographic equity or the FPPS policy.
6. Run a supervised exercise with a named local role and an agreed planning decision. Observe whether users distinguish historical context from current conditions, correctly interpret new loss and existing underservice, choose the decision-sensitive uncertainty and document a reasoned next action. Record misunderstanding, task time, unresolved evidence and reviewer ownership.
7. Promotion requires separately recorded scientific review and operating-partner acceptance. Successful software checks only establish engineering reproducibility. Shared staff workflows, response staffing, retention and operational publication are later pilot requirements.

## Acceptance checks included in this preview

The tests bind package and source digests, preserve original FPPS/action classes and non-operational gates, check registered scenario directions and internally consistent access/equity deltas, and exercise a small open graph where existing underservice must not be counted as new loss. An alternate-connection test shows that closing one edge need not remove service access. Run `--check` in addition to the tests to verify complete recomputation; tests alone do not establish that full regeneration was executed.
