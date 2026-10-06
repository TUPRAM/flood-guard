# Hat Yai transfer study: candidate road-closure sensitivity

Status: **PASS for a bounded, source-bound candidate sensitivity check; BLOCKED for qualified event transfer.** The experiment reuses the existing November 2025 Hat Yai candidate, reviewed general-hospital destination set, 2020 residential demand and fixed road graph. It varies only the **hypothetical rule** that closes a road segment after its centreline intersects the candidate extent. No Mae Sai accuracy or downstream acceptance is transferred.

## Source and evidence status

The selected Sentinel-1 SAFE acquisitions are `2025-11-11T23:03:09.801147Z` and `2025-11-23T23:03:09.290537Z` (12 and 24 November local time). The source archives were previously checked against public catalog sizes/MD5 and locally recorded SHA-256. The linked candidate manifest SHA-256 is `c9298b1b950e973e5ab524652eb7c7ba2a44c4822d1ddd545f8e77316c03b709`. It declares a **20 m, GCP-warped, uncalibrated amplitude-drop** method and transfers the fixed 2.25 dB exploratory threshold without Hat Yai tuning. Its positive geometry is 7.6688 km². A `valid_fraction` of 1.0 applies to selected raster pixels; 173 demand-cell centres totaling about 1,130 residents are outside the clipped observation footprint and remain unobserved. The candidate's source timestamp is the post acquisition above, not the event peak.

This is separate from the proposed physically calibrated Beta0-to-Gamma0, terrain-corrected path and from an independently evaluated flood model. The Hat Yai lane lacks radiometric/terrain correction, speckle and permanent-water treatment, measured local alignment residuals, independent event reference, qualified reviewers and downstream decision acceptance. Candidate overlap population is a WorldPop 2020 cell-centre count, not observed flood victims. Seven reviewed **general-hospital candidates** remain after two point/site duplicates and unsuitable or unresolved roles were excluded in the existing `resources/finals/hat_yai_destinations.json`. Their mapped representatives and event-time operation are not verified entrances or service availability.

The immutable external output is `C:/Users/iputu/Documents/Project Support/FloodGuard/research-runs/2026-09-23-hat-yai-transfer-closure-v1/transfer_sensitivity.json` (SHA-256 `cc609fe1f7aade4556201f45dfc13da6d213b231ab4d1de245235ddce014a183`). Its `run_receipt.json` (SHA-256 `548de51639de13be3c3ac2ed074db9ec21370184340acee59ce28d42e84c3598`) lists source/output sizes and hashes, builder SHA-256 `a97c420f758b5c68419b5a3f525eb7527bed7188856e837a7da1236d93cb11f5`, source commit `14df822e8161cef4edd253f371a89c09d0e5fac9`, and source tree `7817fb8f58d77028dc8e59f99bbd44e592efb715`. The output internal identity is `83dac9e8fc81183467e65dca854ee41b1b0bb2db140a0545a9b13201bb81acd6`.

## Prespecified comparison and results

The old scenario closes **every positive-length** road-centreline overlap with the unchanged candidate, including mapped bridges. The alternatives require at least 20 m (one candidate grid cell) or 50 m (2.5 cells) of overlap. A fourth scenario keeps OSM-tagged bridges and tunnels open under the 20 m rule. These are deliberately simple uncertainty checks, not measured closure thresholds or evidence that a bridge was passable. The candidate geometry, destinations, AOI demand and each mode's graph are otherwise fixed. The script rejects changed input hashes, invalid or duplicate edge intersections, and a failure to reproduce the previous any-positive result.

All people figures below are modelled residents, rounded only for display. The full Hat Yai AOI denominator is 264,044.9 WorldPop 2020 residents. The unchanged candidate overlaps 10,656.9 at cell centres; 1,130.3 are unobserved by the clipped footprint. Threshold losses and all-route losses overlap and must not be added. Walking and modelled-vehicle graphs and time assumptions are distinct.

| Mode | Closure rule | Closed segments | New 15-min loss | New 30-min loss | New 60-min loss | New all-route loss |
|---|---|---:|---:|---:|---:|---:|
| Walking | Any positive overlap | 3,643 | 1,476.7 | 9,940.3 | 29,000.6 | 24,434.1 |
| Walking | At least 20 m | 1,220 | 678.9 | 6,825.4 | 11,880.2 | 12,538.3 |
| Walking | At least 50 m | 195 | 85.7 | 373.6 | 219.8 | 2,215.4 |
| Walking | At least 20 m, mapped grade left open | 1,210 | 678.9 | 6,825.4 | 11,880.2 | 12,538.3 |
| Modelled vehicle | Any positive overlap | 3,604 | 19,082.4 | 23,105.0 | 23,105.0 | 23,105.0 |
| Modelled vehicle | At least 20 m | 1,245 | 8,422.0 | 11,099.9 | 11,040.1 | 11,040.1 |
| Modelled vehicle | At least 50 m | 207 | 366.1 | 2,127.8 | 2,127.8 | 2,127.8 |
| Modelled vehicle | At least 20 m, mapped grade left open | 1,230 | 8,422.0 | 11,099.9 | 11,040.1 | 11,040.1 |

The walking 30-minute loss falls from about 9,940 under any positive overlap to 6,825 at 20 m and 374 at 50 m. Modelled-vehicle loss falls from about 23,105 to 11,100 and 2,128. This large variation shows that the current consequence headline is **not robust to the closure-length assumption**. The 20 m grade alternative excludes 10 walking and 15 vehicle tagged segments without changing these aggregate counts; that does not verify bridge passability or rule out a local route effect. Under the 50 m walking scenario, 60-minute newly lost access is lower than 30-minute newly lost access because some residents can still reach a hospital within 60 minutes after disruption. These threshold-loss sets are not nested.

The old any-positive result was reproduced within its stored four-decimal display precision: walking 30-minute loss 9,940.3487 and all-route loss 24,434.1221; modelled vehicle 23,104.9796 for both. The candidate overlap and unobserved population stay the same across scenarios. Mean finite-route delay has its own comparable-person denominator, recorded separately in the machine-readable output; a person losing all routes is not assigned a finite delay.

## Reproduction, tests and remaining gates

The command actually run, using the verified implementation worktree and existing permitted local inputs, was:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'C:\Users\iputu\Documents\Flood Guard\.venv\Scripts\python.exe' -u scripts/hat_yai_transfer_sensitivity.py `
  --finals-dir 'C:\Users\iputu\Documents\Project Support\FloodGuard\evidence-demo\2026-09-22-shared-cases\study_finals\aoi-03_hat_yai_core' `
  --candidate-dir 'C:\Users\iputu\Documents\Project Support\FloodGuard\evidence-demo\2026-09-22-shared-cases\flood_candidates\aoi-03_hat_yai_core' `
  --output-dir 'C:\Users\iputu\Documents\Project Support\FloodGuard\research-runs\2026-09-23-hat-yai-transfer-closure-v1'
```

The output directory is immutable: a reproduction uses a **new** external path. No laptop path is embedded in application code. The focused test command is `python -m pytest tests/test_hat_yai_transfer_sensitivity.py tests/test_evidence_flood_scenario.py -q`. Input checks and the old-scenario reproduction ran successfully; the closure selectors and effect accounting use open synthetic fixtures in tests. The output remains local research evidence and has not replaced the public case package.

Next scientific work: run calibrated/terrain-corrected Hat Yai preprocessing with source-aligned QA; acquire an independent event reference with purpose-qualified rights; inspect urban/permanent-water and road-grade error strata; review highest-demand hospital components and dated facility entrances/operation; and compare the same frozen road rule against independently assessed candidate/reference extents. Without these gates, Hat Yai remains a transfer **candidate/scenario**, and qualified event accuracy, accepted FPPS, age equity and operational directions remain unavailable.
