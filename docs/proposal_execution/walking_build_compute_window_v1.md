# Compute window for a walking context build of record (draft v1)

Status: **PENDING** (draft, pending acceptance by both owners)

For Putu and Rachmania. Written by an AI coding agent on 5 October 2026. The team rule is "agents draft, humans sign":
this page is not a decision. **No build was run for this page, and none will be run until you accept a window.** No
code reads this page. `tests/test_owner_unblocker_records.py` fails if a walking build of record appears, or if the
builders start treating the walking context as accepted, while this page is pending.

Every figure below is copied from a committed file, which is named. Nothing was computed.

## 1. What you are asked for, in one paragraph

The shelter part of the planning work needs a road network built for walking. One such network exists, but it was
built on 4 October without the formality the plan asks for, so it only counts as a "candidate", and the shelter
tables that rest on it may not be used by the later tasks. To make it count, the same build has to be run once more
inside a **declared compute window**: a few minutes in which no other FloodGuard job runs on the machine, written
down in the build's receipt. For the vehicle network you accepted such windows in decision R13. R13 covered the
vehicle builds only. This page asks whether you accept one for the walking build, on the same terms.

## 2. Where the rule comes from

- **The plan** (restructuring plan v2, section 5, item 1): "Builds run serially in a declared compute window with no
  concurrent SNAP jobs." The signed protocol v1b carries the same sentence (`corridor_polygon.compute_window`).
- **Decision R13** (3 October 2026): you accepted the window of the corridor run, and "in advance that the agent
  declares the E4 build's window on the same terms: no other project job running, and the window recorded". The
  builder reads that as covering the first vehicle build of record of case se1 and nothing else: not walking mode,
  not case se2, not a build that replaces a record (`scripts/build_planning_context.py`).
- **Decision R14** (3 October 2026): you confirmed the record of that vehicle window.
- **Open point E5-OP5** (`outputs/planning_v1/README.md`): "The owners are asked for a walking build of record in a
  declared window they accept, with its receipt here; then task E5 is run again. Until then the shelter tables are
  not inputs of task E8."

Why walking at all: protocol v1b keeps hospitals and main-road entries in vehicle mode and says that, inside the
ensemble, "the shelter service is walking, 30 minutes" (owner choice 7, decision R12). In what is built today, one
thing reads the walking network: the shelter service of task E5.

## 3. What would be run

One build, once, alone: the E4 builder in walking mode for the Mae Sai case.

```text
python scripts/build_planning_context.py --case se1 --travel-mode walking \
    --context-root <external data root> \
    --ddpm-shelters <open data>/shelters/dpm-gd002_final2.csv \
    --dga-facilities <open data>/healthcare/thailand_health_facilities_th.geojson \
    --reviewed-junctions <finals run>/review/osm_junction_review.json \
    --work-dir <a scratch folder outside Git> \
    --compute-window "<the declaration: who, when, what was checked>" \
    --window-authority "<the decision-log row in which you accept the window>"
```

- **What it does.** It reads the road map, the residents, the boundaries and the shelter and hospital lists, and
  writes a network with travel times on foot. It reads no flood layer. It computes no closure, no access loss, no
  FPPS, no A-E class and no ensemble; its only access figure is the share of connected residents with no route to a
  hospital at baseline, for the whole frame (the builder's own description).
- **The builder.** The files below have today the SHA-256 that the candidate build of 4 October named, so today's
  builder is the builder that made the candidate.

  | File | SHA-256 |
  |---|---|
  | `scripts/build_planning_context.py` | `32115d7e71203f97f8b03fb84028dfac3f2884d423405f84e6dd45d0c2e13ec5` |
  | `src/floodguard/planning_context.py` | `f2f56151fd20527b8a0aa159fc76a68a5339b6179cef26fbf7c63ad9deb819a8` |
  | `src/floodguard/evidence_context.py` | `3e85955494e0bf2d4592ea772322afcb20a7a5cdf00036e52a4e33d1263c2994` |
  | `src/floodguard/grade_join.py` | `87247e54da2acbdbbf5e00f5353b0aedf68e471eb463df99b46d9163aec7d634` |
  | `src/floodguard/ddpm_shelters.py` | `c2f0e646497f1ee85676c8aac821d589071713ec43cdf61e40fa3618386a15bf` |
  | `src/floodguard/shelter_corroboration.py` | `89734526dc966e96beb9deba8782e7cbd58cce640090e63b46102ade20a30efc` |
  | `src/floodguard/hospital_counts.py` | `ffe39f1d95e09d3507b9acbe54db3a635e25f0801fbe231b17beb0102b0f316e` |

- **What it writes.** In Git: a receipt (`outputs/planning_v1/e4_planning_context_se1_walking.json`) and a join log
  (`outputs/planning_v1/grade_join_log_e4_se1_walking.json`). Outside Git, because they hold DDPM shelter rows (pitch
  level): the network itself and the facility table, under
  `<external_data_workspace>/proposal_execution/planning_v1/se1_mae_sai/e4_walking/`.

## 4. How long it takes

| | Wall time | Source |
|---|---|---|
| The candidate walking build, 4 October 2026, 13:07:10 to 13:09:33 UTC | **2.38 minutes** | `outputs/planning_v1/e5_walking_context_build_report_se1_mae_sai.json`, `timestamps` |
| The vehicle build of record, 3 October 2026 | 2.21 minutes; the Python process peaked at 0.58 GiB (its child processes are left out) | `outputs/planning_v1/e4_planning_context_se1_vehicle.json`, `run` |

So the build itself should take about two and a half minutes. The vehicle window was 2 minutes 18 seconds long for
a build of 2 minutes 13 seconds: a check of the running processes just before, the build, and the same check just
after. The committed report of the candidate build gives no memory figure.

**What the window costs you:** about ten quiet minutes on the machine (the drafter's estimate: the build, the two
checks and a margin). Every other FloodGuard session has to be idle for that time: no test suite, no bake, no other
build. The window that is recorded is the few minutes actually used.

## 5. Inputs, by SHA-256

The eight files the candidate build read. They are the files the vehicle context of record was built from
(`same_input_files_as_the_vehicle_context_of_record: true` in the report; the two lists of hashes are equal).

| Input | File | SHA-256 |
|---|---|---|
| Roads and hospitals | OpenStreetMap extract for Thailand, `thailand-latest.osm.pbf`, retrieved 10 July 2026 | `b7f46018249638413b1d318bc86519f140c27af20cac7c00d42fe03775b7add1` |
| Residents | WorldPop 2020, 100 m, `tha_ppp_2020.tif` | `fb39d85dd150c45c7b25771f29bcd548e611afa0967224ac6d8ca05727230e20` |
| Boundaries | HDX Thailand COD-AB, `tha_admin_boundaries.gdb.zip`, valid on 22 January 2022 | `09e62345481bb80030ff6779e074bfb2c16629b70ae1e373ebd31945f1c6e0d8` |
| Listed shelters | DDPM list, `dpm-gd002_final2.csv`, open-data folder of 21 September 2026 | `91a8f26a5dd2446b68b562dcda13024d1bd4981720f985722a6467d4edeef9d7` |
| Health facilities | DGA records, `thailand_health_facilities_th.geojson` | `15d208b7c269562c9444f5f034f5e16c3a33a2e069a19637264b2ddc2f1ee58d` |
| Reviewed junctions | The 20 reviewed AOI-01 junctions, `osm_junction_review.json` | `43de4cc50efc790af1aa502e820e178856389041b568ff61bf2c463cfe240f07` |
| Demand area | `resources/aoi/aoi-02_mae_sai_district.geojson` (in Git) | `d49de53e86264c06218fd9a03cc2b5da1549085a49fae2f3cd288bf6334f5a56` |
| Routing corridor | `outputs/planning_v1/corridor_of_record.geojson` (in Git) | `4e49d5eca2f7522e2de10cf81cc68b4ebcbea036225d1b862f4a80cb1affbac2` |

The file names are the ones the builder and protocol v1b give. The receipts record each SHA-256 under a key
(`osm_pbf_sha256`, `worldpop_2020_sha256` and so on), not under a file name. The six files outside Git were not
opened for this page.

Both protocol files are in force: v1a `b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954`,
v1b `6ed7d7e93c86df6ed0cf30b3a3383582632b5efbb678b377ca2ee1990fb393e7`.

What the candidate build produced, for comparison (same report):

| | Candidate build of 4 October 2026 |
|---|---|
| Network, canonical SHA-256 (it leaves out the time of the build) | `1c317916610567672507ba3a436591c6835ffa58934b8ce1e9c4f9310ae3586e` |
| Grade joins | 359, joins SHA-256 `238864d3f616ce4ae343402f0c65e07d66b16ddb77eaa523d19c265bb16bbaea` |
| Edges; road nodes; demand cells | 69,095; 66,537; 36,765 |
| Located DDPM shelters supplied; snapped to the network within 100 m | 82; 81 |

A build of record from the same inputs and the same builder should give the same four lines. Section 7 proposes
that it must.

## 6. What it unblocks, and what it does not

A walking context of record is the first step for three things. It is needed for each and enough for none.

| What | What else stands in the way |
|---|---|
| **The shelter service at pitch level.** Task E5 is run again (about 20 minutes; its last run took 19.53), and its shelter tables then rest on a context of record and may say that task E8 can use them. They hold DDPM data and stay outside Git. | Nothing else for the tables. |
| **360 of the 540 ensemble cells of each lane** (task E10): the two facility sets that add shelters. | No access table exists for the smaller of the two sets, which keeps only the shelters with a mapped building or amenity within 150 m. The builders refuse the pitch level today. Half of the 360 also need the 2024-rescaled demand, which waits for your answer to E10-OP2. |
| **The pitch overlay** (task E8 with shelters). | The builder has to learn to name the walking context and the shelter list in its lineage and to compare the walking context (guardrail GR3). The SE1 overlay also waits for E8-OP1 at any level. |

What it does **not** unblock: a headline for a public class. For a public overlay, protocol v1b takes retention over
the 180 cells of the public facility set, which need no shelter. The 90 of them that are missing wait for the
2024-rescaled demand (E10-OP2), not for this build. Which cells count for a result that is not a public overlay is
open point E10-OP11; under its other reading, all 540 cells, the shelter cells would count too.

## 7. The sentence you would confirm

Tick one. Nothing is ticked: a recommendation is not a decision.

- [ ] **A. Accept in advance, on the terms of R13.**

  > We accept in advance that the AI coding agent declares one compute window for one walking build of record of
  > the Mae Sai planning context (case se1, travel mode walking), on the terms we accepted for the vehicle build in
  > decision R13: no other FloodGuard job running on the machine, and the window recorded. The build reads the eight
  > input files named by SHA-256 in `docs/proposal_execution/walking_build_compute_window_v1.md`. It is the walking
  > context of record only if it reproduces the candidate build of 4 October 2026: the same canonical SHA-256 of the
  > network, the same 359 grade joins with the same joins SHA-256, 69,095 edges, and 81 of the 82 located shelters
  > snapped. Any difference comes back to us before anything is built on it.

- [ ] **B. We name the window ourselves.** Date and time: ____________. Everything else as in A.
- [ ] **C. No walking build of record.** The shelter tables stay candidates, the 360 shelter cells of each lane stay
  not run, and no pitch-level result is produced.

The condition "only if it reproduces the candidate build" is the drafter's proposal, modelled on what you asked of
the vehicle build in R13. Strike it if you do not want it.

## 8. Two things to settle before the build, found while drafting

**8.1 The receipt, as the builder writes it today, would fail the folder's own tests.** The E4 builder names
protocol v1b only, and its join log names neither protocol. Since v1b came into force, every file in
`outputs/planning_v1/` has to name both protocol files by SHA-256 and has to be a run receipt or be bound by one, and
every such run has to be registered (`tests/test_planning_v1_outputs.py`, `tests/test_planning_protocol.py`). The
vehicle build passed because it was made before v1b came into force. So a walking build of record needs a small
change first, to what the builder writes about itself, not to how it builds the network. Then the builder's SHA-256
is no longer the one in section 3; the check in section 7 (same network, same joins) is what shows the network was
built the same way. That change is not made here. It would be reviewed, and tried on invented data only.

**8.2 Task E5 does not look at who accepted a window.** It reads the walking context as "of record" as soon as the
build was made with `--compute-window`, even when no decision-log row is cited and the receipt says the window
"awaits owner acceptance" (`scripts/build_access_diff.py`, `load_walking_context`). Today this harms nothing: no
walking build of record exists. Before one is made, task E5 should refuse a walking context whose receipt names no
authority. That guard is not built here either.

## 9. What the agent would do after you accept, and what it would not

It would:

1. Record your answer as a new row of the decision log after R18.
2. Make the two changes of section 8, each reviewed and tried on invented data.
3. Check that no other FloodGuard job is running, declare the window, run the one build, check again, and write
   the window into the receipt with the decision-log row as its authority.
4. Compare the result with the four lines of section 5. If they are the same, commit the receipt and the join log
   and register them. If one differs, stop and bring it to you.

It would not, without asking again: run the build a second time, run task E5, E8 or E10, or replace a record.
`--verify` rebuilds the network into a temporary folder and compares; for the vehicle build it was run outside the
window. Say if you want it inside.

## 10. Signature block

Left empty on purpose. Fill it in yourselves, or tell the agent your answer and it records the decision-log row
that says how the answer was given.

| | Putu | Rachmania |
|---|---|---|
| Option chosen (A, B or C) | | |
| If B: date and time of the window | | |
| Keep the condition "only if it reproduces the candidate build" (yes or no) | | |
| Date | | |

Decision-log row: _none yet_

## 11. About this page

- **Source timestamp:** the candidate build ran on 4 October 2026 from 13:07:10 to 13:09:33 UTC; its report was
  written at 15:38:45 UTC. Road map retrieved 10 July 2026; residents for 2020; boundaries valid on 22 January 2022;
  shelter list from the open-data folder of 21 September 2026.
- **Confidence: low** for the network itself (unverified map and list records, modelled walking speeds; the report
  says so). **Medium** for the figures on this page: each is copied from a committed file and checked by a test, but
  the expected duration rests on one earlier build on the same machine.
- **Assumptions:** the eight input files are still on disk with these SHA-256 values (they are outside Git and were
  not opened for this page); the machine is the one the earlier builds ran on; a walking context is a planning
  model, not an observation of who can reach a shelter.
- This page is not legal advice and not an official warning.
