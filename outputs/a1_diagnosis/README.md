# outputs/a1_diagnosis

Figures of the abstention diagnosis (restructuring plan v2, task A1): why
threshold-only change detection failed at the Sentinel-1 pass of 15 September
2024, 23:16 UTC. They are explained in
`docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md`.

Each file holds the figures of one script under `scripts/diagnostics/` and is
bound, by path and SHA-256, in the run receipt
`outputs/planning_v1/a1_diagnosis_<figure>.json`. Do not edit a file by hand:
run its script with `--replace --reason`.

Every file carries `generated_at_utc`, `source_timestamp`, `confidence_class`
(always `low`), `confidence_basis`, `assumptions`, `limits`, `does_not_show`,
`official_warning: false` and `operational_status: non_operational`. None holds
an FPPS, an A-E class, a flood candidate or a value for a single tambon. None
is an observation of a flood, and no figure says how correct a method is.

| File | Figure | Measured against |
|---|---|---|
| `bvf_unimodal_gaussian.json` | What one bell-shaped population gives the 0.72 histogram gate | nothing: theory and simulation |
| `m2_windows_mae_sai.json` | The 81 windows of the retired M2 run at Mae Sai | nothing: the run's own records |
| `m2_windows_geoid.json` | The M2 decision rule on 29 GEOID-Flood tiles | nothing: no label is opened |
| `sentinel1_pass_gap.json` | Sentinel-1 passes over Mae Sai in September 2024 | nothing: catalogue metadata |
| `pilot_grid_vs_envelope.json` | Share of the season envelope the M2 pilot grid leaves out | a season envelope, not an event map |
| `darkening_auc_vs_envelope.json` | Separation of the VH darkening against the season envelope | a season envelope, not an event map |
| `terrain_auc_vs_envelope.json` | Separation of low and flat ground against the season envelope | a season envelope, not an event map |

The last three files hold figures derived from the accumulated layer of
UNOSAT/GISTDA product 4009 and are shared under CC BY-SA 4.0. Credit: UNOSAT
and GISTDA, FL20240912THA, UNOSAT product 4009. Each states what FloodGuard
changed (`licence.change_notice`). The layer is an unvalidated preliminary
agency extent (Field_Validation=0), used as provided; FloodGuard did not
validate it. It is a 2024 season envelope, not an event map and not a
reference. The darkening figure contains modified Copernicus Sentinel data
2024.
