# Codex task: build the fully automated evidence track (no human steps)

Paste everything below the line into Codex, run on the machine that holds the
FloodGuard external data workspace, on branch `codex/open-data-evidence-demo`
(or a branch from it).

---

## Goal

The project owner has decided that the Mae Sai evidence chain must run with
**no human action**. Build an **automated track** that runs end to end:
reference → review → evaluation → landing indicators. It must never claim
human work that did not happen. The existing human track (Reference Authority,
Reviewers A/B, Adjudicator C, custodian keys) stays in the code untouched but
unused, so it can be revived later.

Read these first: `AGENTS.md`, `docs/proposal_execution/GATE_RESEARCH_DOSSIER.md`,
`docs/proposal_execution/signing_forms/README.md`, `docs/label_factory_runbook.md`,
`src/floodguard/observation_evaluation.py`, `src/floodguard/landing_gate_status.py`,
`apps/web/src/lib/landing/gate-status.ts`.

## Non-negotiable honesty rules

Breaking any of these would make the Preview claim something false to judges.

1. **Never invent people or human evidence.** Do not create `FG-HUM-*`,
   `FG-RA-*`, `FG-RV-*` or `FG-ADJ-*` identities. Do not create emails, PDFs,
   message exports, signatures or "accepted" appointments. Do not generate
   Ed25519 keys that pose as a custodian.
2. **Never feed automated artifacts into the human-track validators.** Do not
   weaken `human_roles`, `rights_clearance`, `reference_authority_approval`,
   `qualified_reference_release`, `qualified_label_release`,
   `multi_event_preflight` or `holdout_opening`. Add a parallel, separately
   named automated contract instead.
3. **Name things for what they are.** Use `automated_optical_reference` for
   the reference, `automated_cross_review` for the review, and
   `preregistered_automated_evaluation` for the evaluation. Never label any of
   them `qualified`, `human-reviewed`, `blind-reviewed`, `adjudicated` or
   `accepted`.
4. **Report a score as agreement, not accuracy.** Any score against the
   automated reference is **agreement with an automated optical map**. The UI
   and briefs must say so next to the number.
5. **Keep every safety flag false.** `official_warning=false`,
   `operational_status=non_operational`, and `can_feed_decision_layer=false`
   for evaluation outputs. The accepted FPPS / accepted A–E fields stay null;
   put automated values in new, clearly named `automated_candidate_*` fields.
6. **Record a negative result as it is.** If a step fails or the agreement is
   poor, record that. Do not tune thresholds after looking at the SAR
   comparison.

## Inputs

- **Sentinel-2 reference scene:** `S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143`
  (CDSE id `f1a638d2-3b8f-4f9a-a862-1b651d6662c3`). It has **not been
  downloaded yet**. Acquiring it is the first step of this task, before the
  pre-registration.
  - **Preferred: the original SAFE ZIP (1,157,904,758 bytes, provider MD5
    `43a17ba47b7235c47a72abbbcb5f27fa`).** If `CDSE_USERNAME` and
    `CDSE_PASSWORD` (or `CDSE_ACCESS_TOKEN`) are already set in the
    environment, run:

    ```
    uv run python scripts/acquire_cdse_mae_sai_sentinel2_reference.py --external-data-dir <external_data_workspace>/cdse/mae_sai_2024
    ```

    It downloads outside Git and checks the provider MD5, the ZIP structure and
    the CRCs. It then records the SHA-256 in
    `outputs/cdse_mae_sai_sentinel2_reference_acquisition_manifest.csv`;
    commit that CSV. The CDSE zipper does not support HTTP Range, so each
    stalled attempt restarts from zero. The script retries up to 8 times with a
    fresh token. Never write credentials into a file, a commit, a log or this
    prompt. If none are set, do not ask for them; use the fallback below.
  - **Fallback, with no credentials: read the same product anonymously from
    Earth Search.** Use `https://earth-search.aws.element84.com/v1`, item
    `S2B_47QNC_20240915_0_L2A`, and assert that `s2:product_uri` equals the
    product name. Download only the assets you need (`blue`, `green`, `red`,
    `nir`, `nir08`, `swir16`, `swir22`, `scl`; COGs with HTTP Range support).
    Store them in `<external_data_workspace>/earth_search/mae_sai_2024/`. Record
    each asset's URL, byte count and SHA-256 in
    `outputs/earth_search_mae_sai_sentinel2_reference_assets.csv`, marked
    `source_edition=element84_cog_of_l2a` and
    `original_safe_sha256=not_recorded`. `scripts/probe_optical_reference_candidates.py`
    already shows how to open these items.
- **Dry-context scene:** `S2B_47QNC_20240905_0_L2A`, used for permanent water.
- **SAR candidate(s)** from the existing external workspace: the M2 10 m
  EPSG:32647 Gamma0 Otsu run (receipt SHA-256
  `7814cfb5f936952a581ab72c40bde7ab14f638715834f39974dddfa81c5394fe`) and the
  20 m amplitude comparator.
- **AOI:** `resources/aoi/aoi-01_mae_sai_core.geojson`.
- **Grid:** 10 m EPSG:32647, snapped to the T47QNC origin (see
  `signing_forms/reference_procedure_v2_sentinel2_DRAFT.md`).

## Work items

### 1. Pre-registration (do this first, and commit before item 3)

Create `docs/proposal_execution/automated_track/preregistration_v1.json`. Fix
every choice in it before any SAR-vs-reference comparison exists:

- The two automated water methods in item 3 and their exact thresholds.
- The unobservable rule: SCL 0, 3, 8, 9, 10, plus a 20 m buffer.
- The permanent-water rule.
- The partition: reuse the draft plan values, 1 km blocks, 200 m halo, seed
  `mae-sai-2024-observation-eval-v1`, 0.5 development fraction.
- Metrics.
- Acceptance limits, chosen by the agent and justified in one sentence each.

Commit it alone. The commit SHA and timestamp are the pre-registration
evidence. Record `preregistered_by: "automated agent (Codex)"`, not a person.

### 2. Automated rights basis

Record the rights basis in `automated_track/rights_basis_v1.json`:

- The Copernicus legal notice purposes (a)–(d).
- The required attribution text.
- `signed_by_human: false`.

Do not touch `rights_clearance.py`.

### 3. Automated optical reference (`src/floodguard/automated_reference.py`)

1. Resample the 15 Sept bands to the grid.
2. Run **two independent automated water classifiers**. They must differ in
   method, not just in threshold. For example:
   - (A) a pretrained optical water model such as OmniWaterMask, run in the
     research environment described in `research/MANIFEST.md`;
   - (B) a fixed multi-index spectral rule, for example MNDWI + AWEI_sh +
     NDVI, using the thresholds pre-registered in item 1.

   Neither may see SAR data.
3. Compute `permanent_water` from the 5 September scene with the same methods.
4. Write a label raster using the `flood_label_v1` codes:
   - 0 dry: both methods dry;
   - 1 temporary flood: both methods water and not permanent;
   - 2 permanent water;
   - 3 uncertain: the methods disagree;
   - 4 unobservable: the SCL rule applies.
5. Write a self-hashed `automated_optical_reference_v1.json` receipt. It must
   include:
   - the input hashes;
   - the method versions;
   - the class counts;
   - the A/B agreement (Dice and Cohen's kappa via
     `label_factory.agreement.compute_agreement`);
   - `human_reviewed: false` and `official_warning: false`;
   - a `limitations` list. It must say that turbid floodwater is often missed
     by spectral rules, citing the repository's Component ★ finding that
     MNDWI > 0 flagged 8.7× the reference area.
6. Store rasters in the external workspace, and commit only small receipts and
   quicklooks.

### 4. Automated evaluation

Extend `observation_evaluation.py` with a **separate** entry point,
`evaluate_against_automated_reference(...)`. It must:

- require the pre-registration receipt and the automated reference receipt,
  and check that both hashes match;
- reuse `compute_observation_metrics`, `assign_partition` and
  `compare_to_limits`;
- run `development` first, then `final_holdout` exactly once. Enforce "once"
  with an exclusive local marker file, the same pattern as
  `holdout_opening.consume_*`, but named `automated_holdout_consumption`;
- produce a self-hashed result with
  `evidence_tier: "preregistered_automated_evaluation"`,
  `reference_kind: "automated_optical_reference"`, `human_reviewed: false`,
  `accepted_observation: false`, `official_warning: false`;
- carry the note: "Agreement with an automated optical map, not accuracy."

Leave `evaluate_observation` (the human path) unchanged.

### 5. Landing indicators

Extend `landing_gate_status.py` and `gate-status.ts` with a
`track: "automated"` status that has three **new** criteria ids:

| id | label on the page | met when |
| --- | --- | --- |
| `automated_optical_reference` | Automated optical reference (not human-qualified) | reference receipt self-hash verifies and its inputs match the manifest |
| `automated_cross_review` | Two-method automated cross-review (no human review) | A/B agreement recorded and pre-registered Dice/kappa limits met |
| `preregistered_holdout_evaluation` | Pre-registered hold-out evaluation (automated) | final-holdout result verifies against the pre-registration commit |

On the page, replace the three human-track criteria with these three. Keep a
one-line note: "Human qualification and blind review were not performed." Show
the final-holdout agreement score, with calibrated and raw values where they
apply, next to the words "agreement with an automated optical map, not
accuracy".

### 6. Downstream (optional, only if items 1–5 pass)

Compute `automated_candidate_fpps` and `automated_candidate_action_class`
using the default 30/25/20/15/10 weights and write them to new fields. Keep
`accepted_fpps` and `accepted_action_class` null. Class E still means
"Monitor and Verify", never "safe".

### 7. Documentation and release

- Update `STATUS.md`, `UNRESOLVED.md` and `CLAIMS.md` so the automated track
  and its limits are stated plainly.
- Keep the human-track rows as "not pursued".
- Update `GATE_RESEARCH_DOSSIER.md` with the results, including poor ones.

## Tests and verification (all must pass before pushing)

- Unit tests for every new function:
  - label-code assignment;
  - disagreement → code 3;
  - SCL → code 4;
  - pre-registration hash mismatch → refuse;
  - second final-holdout run → refuse;
  - tampered result → indicator off.
- A test asserting that no new file contains `FG-HUM-`, `FG-RA-`, `FG-RV-` or
  `FG-ADJ-` identifiers, and that no automated receipt has
  `human_reviewed: true`.
- Checks to run:
  - `uv run pytest`;
  - `uvx ruff check` on the new files;
  - `pnpm verify:frontend`;
  - a Preview check that the three new indicators and the "not accuracy" note
    render at 360 px and 1440 px.
- Commit in focused steps. Pre-registration must be the first commit of this
  work. Push to the branch and report the Vercel Preview URL.

## Report back

Include:

- the pre-registration commit SHA;
- the reference class counts and A/B agreement;
- the development and final-holdout metrics;
- which acceptance limits passed and which failed;
- the Preview URL.

Report failures and weak results exactly as they are.
