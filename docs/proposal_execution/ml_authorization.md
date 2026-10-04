# M11 multi-event and holdout authorization engineering

Status: **PARTIAL engineering; real learned experiment BLOCKED.** No learned model was fitted or evaluated in this work.

## Current governing contracts

`src/floodguard/multi_event_partitions.py` defines four roles: training, model-probability calibration, development and final holdout. It requires at least five distinct heterogeneous event/episode groups, with spatial/overlap and source/target leakage checks. Version 1 deliberately accepts only `fixture_demo` partition manifests. Its existing validated-release projections may be supplied by a caller and therefore do not themselves prove file-backed qualified labels or source lineage.

`src/floodguard/label_factory/qualified_label_release.py` can validate a purpose-bound synthetic fixture release. Candidate/official v1 release construction and validation explicitly stop until a canonical attributable signed release-authority receipt validator exists. The current candidate-only Mae Sai scene is not a qualified member of a five-event training programme. A model selected for a report does not confer accepted flood, FPPS or action-class authority.

## New bounded preflight

`src/floodguard/label_factory/multi_event_preflight.py` reopens every supplied release/formal-review/review-pair/reference file, passes them to the canonical qualified-label and reference validators, and rehashes the exact reference raster and analysis-grid bytes against the qualified-reference receipt. If acquisition lineage names pre-event SAR, post-event SAR or reference-mask hashes, the caller must supply exactly those source files; each is streamed and rehashed. Unknown paths, missing files, symlinks, parent traversal, changed bytes or substituted review evidence fail closed. The result is explicitly `validated_synthetic_fixture_only` and `eligible_for_real_experiment=false`. It is a preparation check, not a new release-authority path or alternate projection ingress.

`src/floodguard/label_factory/holdout_opening.py` verifies an exact-scope Ed25519 opening receipt against public keys supplied by an external trusted registry. It checks the frozen partition, release-set and final-holdout hashes; one final-evaluation scope; unopened-reference declaration; custodian role; issuance, validity and expiry. A separate consumption function creates one exclusive local marker per final-holdout partition and rejects a replay or a second receipt for that partition. The marker records the signed receipt hash and consumption time and is never overwritten by this code. The result says `real_experiment_authorized=false`.

**Storage limit:** an exclusive local marker prevents replay while the ledger remains intact; it is not a WORM or independently governed custody store. A person with write/delete access to the directory could remove it. The actual custodian must provide a trusted key registry and append-only/immutable externally governed store, with backup/audit controls, before real custody is claimed. The verification code never creates keys, signs an authority receipt or endorses a claimed custodian identity. Test keys and dates are explicitly synthetic.

## Reproducible checks

```powershell
uv run --extra evidence pytest -q tests/test_multi_event_preflight.py tests/test_holdout_opening.py
uvx ruff check src/floodguard/label_factory/multi_event_preflight.py src/floodguard/label_factory/holdout_opening.py tests/test_multi_event_preflight.py tests/test_holdout_opening.py
```

The synthetic fixtures include a fully revalidated fixture release and matching on-disk reference raster/grid, then alter source bytes, review lineage, source-role coverage and paths. Custody fixtures sign only test payloads and exercise tampering, wrong trusted role, wrong frozen hash, expiry, unsafe scope, duplicate opening and immutable local marker contents. These tests demonstrate software rejection paths. They are not human review, real key provenance, event independence or final-holdout evaluation evidence.

## Exact remaining gates

1. Independently source at least five purpose-compatible, heterogeneous Thai events/episodes with rights, source rasters, qualified references and purpose-specific frozen label releases. One episode cannot be multiplied into five by using multiple scene wrappers.
2. Add and review the currently missing canonical attributable signed release-authority validator. A real release must be revalidated against its original on-disk source chain and purpose-specific human/reviewer/adjudication evidence. The new preflight intentionally cannot bypass the current fixture-only stop.
3. Design and approve a versioned non-fixture multi-event manifest/qualified-release projection ingress that binds the canonical loader result, four roles, feature plan and leakage controls. Preserve the existing fixture-only schema until this is reviewed.
4. Obtain actual trusted custodian keys, signed opening/consumption authority and immutable ledger ownership. Freeze evaluation plan, reference purpose, abstention/strata/metrics, threshold/promotion policy and source hashes before a final holdout is opened. No such real signature, approval, custody receipt or accepted scene ID is present in this package.
5. Only then run the agreed deterministic SAR baseline, weak-label logistic comparator and authorized GeoAI family on independent partitions. Training transforms use training data only; probability calibration, development and final holdout keep their distinct roles. A family change (for example to RF/XGBoost) needs an explicit versioned method decision. Report both observation and downstream consequence comparisons without promoting a report-only candidate to accepted FPPS.

No current output from these modules is an operational warning, accepted historical observation, accepted FPPS or A-E action class.
