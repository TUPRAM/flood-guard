# scripts/diagnostics

Diagnosis scripts of plan task A1 (restructuring plan v2, section 4.2 and row
8.1 A1): why threshold-only change detection failed at the Sentinel-1 pass of
15 September 2024, 23:16 UTC (16 September 06:16 in Thailand). The write-up is
`docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md`.

One script computes one figure. Each script starts with a README header that
says what it reads, what it computes and what it does not show. None computes
an FPPS, an A-E class or a flood candidate. A diagnosis figure is not an
observation of a flood and not an official warning.

| Script | Figure | Reads outside Git | Measured against |
|---|---|---|---|
| `bvf_unimodal_gaussian.py` | What one bell-shaped population gives the 0.72 histogram gate: theory, and simulation through the frozen M2 kernel | nothing | nothing: arithmetic |
| `m2_windows_mae_sai.py` | The 81 windows of the retired M2 run at Mae Sai against the gate | the M2 run's own receipt | nothing: the run's own records |
| `m2_windows_geoid.py` | The M2 decision rule on the 29 GEOID-Flood tiles, window by window | 58 radar tiles of the GEOID-Flood sample | nothing: no label is opened |
| `sentinel1_pass_gap.py` | The Sentinel-1 passes over Mae Sai in September 2024 and the gap between them | nothing (a committed catalogue snapshot) | nothing: metadata |
| `pilot_grid_vs_envelope.py` | Share of the 2024 season envelope inside AOI-01 that the M2 pilot grid leaves out | product 4009 archive; the M2 receipt | a season envelope, not an event map |
| `darkening_auc_vs_envelope.py` | Separation of the VH darkening at the pass against the season envelope | product 4009 archive; the stored sigma0 rasters of tasks A2 and A4; boundaries; JRC and WorldCover water | a season envelope, not an event map |
| `terrain_auc_vs_envelope.py` | Separation of low and flat ground against the season envelope | product 4009 archive; the GLO-30 tile; boundaries; JRC and WorldCover water | a season envelope, not an event map |

## Running a script

The scripts have their own optional extra, which the default CI sync leaves
out (`.github/workflows/ci.yml`: `--no-extra diagnostics`):

```text
uv sync --extra diagnostics --extra dev
python scripts/diagnostics/<script>.py --external-data <external data root> --verify
```

The external data root comes from `--external-data` or from the environment
variable `FLOODGUARD_EXTERNAL_DATA`. No script holds a machine path.

- `--verify` computes the figure again and compares it with the committed run.
  It writes nothing.
- A run writes three files: the figures under `outputs/a1_diagnosis/`, the run
  receipt under `outputs/planning_v1/` and the register entry of the receipt
  under `outputs/planning_v1/run_register/`.
- A second run of a figure needs `--replace --reason "<why>"`. Its receipt names
  the receipt and the figures file it supersedes by SHA-256, and copies of both
  are kept under `<external data root>/proposal_execution/planning_v1/a1_diagnosis/superseded_runs/`.
- A run is refused unless planning protocols v1a and v1b are in force.

Every run is reported: `outputs/planning_v1/README.md` lists them.

## Rules the scripts keep

- **Cleared inputs only.** Product 4009 is read through the rights registry
  (`floodguard.rights`) and `floodguard.flood_inputs.load_se1`; only its
  accumulated layer is read, which the confirmed rights record names. Each
  figure derived from it carries CC BY-SA 4.0, the credit "UNOSAT and GISTDA,
  FL20240912THA, UNOSAT product 4009" and a change notice.
- **A season envelope is not an event map.** The accumulated layer holds every
  area mapped as water at some time between 1 August and October 2024. It is a
  comparison layer, never a reference. A figure against it is not a validation.
- **Two flood products are not read at all.** No provider has granted them.
  `tests/test_ait_mbrsc_guard.py` fails when a script here names either product
  or its folder (planning protocol v1a, guardrail GR9).
- **No radar layer and no flood layer is written.** The scripts write numbers.

The arithmetic is in `src/floodguard/abstention_diagnosis.py`, the layer
handling in `src/floodguard/diagnosis_layers.py` and the receipts in
`src/floodguard/diagnosis_run.py`. They are tested on invented data in
`tests/test_abstention_diagnosis.py` and `tests/test_diagnosis_layers.py`; the
committed runs are checked in `tests/test_a1_diagnosis_outputs.py`.
