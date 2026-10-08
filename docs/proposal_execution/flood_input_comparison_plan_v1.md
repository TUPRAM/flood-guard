# How the decision inputs change with the flood input: plan v1

**Status: plan, committed before the comparison was run.** It follows the
proposal's rule of pre-specification (section 3.6.5) and its list of downstream
comparison metrics (section 3.6.2). The result is report-only. It computes
counts of land, residents and road edges. It computes no component, no FPPS and
no A-E class, issues no case, and is not an official warning.

- Written: 7 October 2026, by the AI coding agent under decision-log rows R20
  and R27 (work package 2). The owners can overturn it.
- Area: the eight tambons of Mae Sai district (the reporting frame of protocol
  v1a).

## 1. The question

The planning result of case SE1 reads one flood input: the 2024 season layer of
UNOSAT and GISTDA. The project also has three radar flood candidates of its
own for the Sentinel-1 pass of 15 September 2024, 23:16 UTC. The question is
how far the things a planner would act on (who is in the water, which roads
close, who loses access) depend on which flood input is read.

None of the inputs is a reference for another. The season layer holds every
area mapped as water between 1 August and October 2024; a radar candidate
describes one pass, 3.8 days after the modelled peak. They are not expected to
agree, and a difference is not an error of either.

## 2. Flood inputs, fixed here

| Name | What it is | Where it comes from |
|---|---|---|
| `season_layer_whole_corridor` | The accumulated layer of product 4009, as provided, over the whole routing corridor | The extent written by plan task E1; this is the input of the SE1 run of record |
| `season_layer_in_frame` | The same layer inside the eight tambons only | The reporting-frame extent written by plan task E1 |
| `un_spider` | UN-SPIDER recommended practice, quotient 1.25 | The candidate raster of the height-aware run of 4 October 2026 |
| `m1_literal` | M1-literal | the same run |
| `m1_v2` | M1-v2, frozen configuration | the same run |

The radar rasters are the files the committed receipt
`outputs/planning_v1/radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json`
binds by SHA-256. The height-aware run is used because the layers of the run
of record lie about 680 m from their true place, which is more than a road is
wide; the receipt of that run measured about 10 m for this one. A radar raster
covers the eight tambons only, so a radar input is set beside
`season_layer_in_frame`, not beside the whole corridor.

A radar raster becomes a flood extent as protocol v1b says for a T2 raster:
its flood cells are made into polygons and polygons under 5 cells are dropped.
The protocol does not say which cells form one polygon; the 4-neighbour rule is
used and stated. A cell with no answer is not flooded and not dry: it closes
no road here, and the share of the frame with no answer is reported.

## 3. What is computed for each flood input

With the functions and the context of record that plan tasks E1, E4 and E5 use,
unchanged (`floodguard.flood_inputs`, `floodguard.closure_rules`,
`floodguard.access_diff`, `scripts/build_access_diff.py`):

For each tambon and for the frame:

1. land inside the extent, outside permanent water (ESA WorldCover class 80),
   in km² and as a share of the tambon's land;
2. residents whose population cell centre is inside the extent (WorldPop 2020,
   the demand cells of the context of record);
3. road edges closed by closure rule v1 at each level (strict, central,
   permissive), vehicle graph;
4. residents who newly lose a hospital within 30 minutes and a main-road entry
   within 15 minutes by vehicle, and residents who lose every route, at each
   closure level.

**A check on the method.** `season_layer_whole_corridor` must reproduce, to the
last resident, the committed table of the SE1 run of record
(`outputs/planning_v1/e5_access_diff_se1_mae_sai_public_services.json`). If it
does not, nothing is reported.

## 4. Comparison figures, fixed here

For each radar input against `season_layer_in_frame`, at the central closure
level:

- flooded land and residents inside the extent, as a ratio of the two totals;
- the closed road edges of the two inputs: how many are closed by both, by one
  only, and the share of the union closed by both;
- residents losing every route: the two totals, and the rank correlation
  (Spearman) of the eight tambons;
- the rank correlation of the eight tambons by residents inside the extent;
- whether the tambon with the most residents losing every route is the same.

And `season_layer_in_frame` against `season_layer_whole_corridor`, to show how
much of the SE1 access loss comes from water outside the district.

## 5. What it may and may not be used for

- It may be shown as the answer to "what would change if we read our own radar
  and not the agency layer?".
- It is not case O1. Case O1 of protocol v1a needs a confirmed rights record
  for the Sentinel-1 data in the rights registry and runs of plan tasks E1, E5
  and E8 for the radar candidates. None of that is done here, and the registry
  is untouched.
- It gives no class. What confidence rule v1 says of a radar input is already
  recorded: an own candidate that does not meet the skill bar has low
  confidence (`outputs/planning_v1/radar_o1_mae_sai_v1.json`,
  `outcome_of_record: not_met`), and low confidence gives class E whatever the
  counts are.
- No input is selected or tuned on the result.

## 6. Outputs

- `outputs/flood_input_comparison/mae_sai_v1.json`: the counts and the
  comparison figures, with `generated_at_utc`, `source_timestamp`,
  `confidence_class`, `assumptions`, `limits`, `official_warning: false` and
  `operational_status: non_operational`.
- `outputs/flood_input_comparison/mae_sai_v1_receipt.json`: the SHA-256 of
  every input and of this plan.
- `docs/flood_input_comparison.md`: the result in plain words.

Credits: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0;
figures derived from it are shared under the same licence). Contains modified
Copernicus Sentinel data 2024. Roads and hospitals © OpenStreetMap contributors
(ODbL 1.0). Residents: WorldPop 2020 (CC BY 4.0). Land cover: ESA WorldCover
2021 v200 (CC BY 4.0).
