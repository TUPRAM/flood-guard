# Protocol v1b: the closures, on one screen

For Putu and Rachmania, before you attest "I have read each closure". Written by an AI coding agent on 3 October 2026, corrected the same day after a review, brought up to date after decision log R13 and the E4 build of record, and corrected again after a review of the E4 build. **v1b is `draft_for_signature`.** All 18 items are closed and every section is fixed. Nothing is signed and nothing is in force. No FPPS, A-E class or ensemble has been computed. The full text of each closure is in `planning_protocol_v1b.json` under `open_items[].closure`.

The table covers the 17 items that were open when you approved v1b in principle (R11), plus OI-11, which closed on 2 October.

| Item | Final value (or where it lives) | Decided by | Evidence |
|---|---|---|---|
| OI-01 | Corridor polygon `outputs/planning_v1/corridor_of_record.geojson` (827.4 km², one polygon). Demand area: the eight-tambon union clipped to AOI-02 | Choice 21; run of record | [C] |
| OI-02 | Route rule: buffer the whole fastest path to each of the three hospitals by 3 km, with its seven sub-rules | Choice 1 (B) | [R] |
| OI-03 | 4 distinct named hospitals (6 OSM objects); the three named ways in context; 65,328 edges; 2.92 min; 2.44 GiB peak working set; 371 grade splits; no-route share 0.075%. Made in a compute window the agent declared and you accepted in R13 | Choice 22; run of record | [E] |
| OI-04 | Grade-join tolerance 0 m. Join log of record `outputs/planning_v1/grade_join_log_e4_se1_vehicle.json`: 345 joins, the same joins as the spike run | Choice 20; E4 build (entry 24: A) | [J] |
| OI-05 | Closure thresholds: motorway 50 m, residential 30 m, unclassified 30 m. Strict level delays with k = 2. `culvert=*` not read. Regression exact (1,824 walking, 1,738 vehicle) | Choices 4\*, 5, 23 | [R] |
| OI-06 | Main-road entry: the nearest trunk or primary node, links included. Shelter match distance 150 m. Mae Sai Hospital is OSM way/371233866. Counts from E4: 6 OSM hospital objects, 6 with a DGA record within 150 m, 82 located shelters, 48 corroborated (20 by a building) | Choices 8, 19; E4 build (entry 24: A) | [E4] |
| OI-07 | Ranking destinations: hospitals and main-road entry. The ranking is bound in the first run receipt | Choices 9, 10 | [R] |
| OI-08 | National anchors, rule A: P5 0.313095, P10 0.351416, P75 0.454083, P90 0.477677, P95 0.494407 (7,425 units) | Choice 6\* | [A] |
| OI-09 | pf-07: the 16 tambons of Mueang Chiang Rai. SE2 routing: the frame plus 3 km (2,422 km², 17 hospital objects). SE2-blind: TH570513 and the 5 Phan tambons that touch it | Choice 15\* for the rules; the agent's build, which Rachmania accepted as built (R13) | [F] |
| OI-10 | Reference cell: the default cell. S3b: 3 bridge edges per tambon, assigned to a tambon as in S3. E3: rule C | Choices 3, 17, 18 | [R] |
| OI-11 | v1a SHA-256 `b6dc549c…0a954` | v1a signing | [V] |
| OI-12 | Terrain proxy: the code definition, no anchor | Choice 13\* | [R] |
| OI-13 | 2024 demand rescaled within each 1 km cell | Choice 12 | [R] |
| OI-14 | Detector levels and A6′ threshold as proposed. A default only: the numbers were made up | Choice 14 | [R] |
| OI-15 | One pixel = 20 m for the plus level and for vector products | Choice 2 | [R] |
| OI-16 | Shelters in the ensemble: walking, 30 min, pitch level. Public retention over the 180 public cells | Choice 7 | [R] |
| OI-17 | S5 node list bound in the first run receipt. Selection by the binding v1 class of the SE1 reference cell | Choice 16 | [R] |
| OI-18 | Class v2 triggers: (a) option A; (b) option A, with the 100 residents tied to GR1; (c) option B at 20%, with 10% and 30% reported beside it | Choice 11 | [R] |

\* Outcome-aware: values for real tambons bearing on the choice had been seen. You gave no reason of your own. The closure quotes the recommendation's reason and says that none was given.

**Evidence (SHA-256):**

| Key | What | SHA-256 |
|---|---|---|
| [R] | R12 row of the decision log (line 45 at commit 522194e) | `8c3f7e20cedabb8f4593311f1f3603880595cc40994006b6253e0b92cc579f50` |
| [C] | `outputs/planning_v1/corridor_of_record.geojson` | `4e49d5eca2f7522e2de10cf81cc68b4ebcbea036225d1b862f4a80cb1affbac2` |
| [E] | `outputs/planning_v1/e0_context_run_of_record.json` (receipt of the corridor run of record) | `e038546b84e96715bac5b649a3996201cfaf5c9c67d7f6dcd6b0f88b316c678d` |
| [E4] | `outputs/planning_v1/e4_planning_context_se1_vehicle.json` (receipt of the E4 build of record) | `690add44186d02cb501dccb152678fbf03cf109acc041a5c782af705993f2ad2` |
| [J] | `outputs/planning_v1/grade_join_log_e4_se1_vehicle.json` (join log of record, written by E4) | `a337fee5c17d81b1b61fc64114c09e59103174282702aa01e33905d051fb636e` |
| [A] | `outputs/planning_v1/national_vulnerability_anchors_v1.json` | `2ad161d4c67cbe1567fbb853fe951da3ffb257f06088fbc80e8e297938c73a59` |
| [F] | `resources/planning_frames/planning_frames_v1_receipt.json` | `86f31d8a748be13b7a5a30ce7e46f988d8cbfc53c76f2bf3a96aebf533b130b3` |
| [V] | `docs/proposal_execution/planning_protocol_v1a.json` (signed) | `b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954` |
| [R13] | R13 row of the decision log (line 46 at commit c4f255d) | `58b46b20a9e58fa4dd0bc16154803b9c64c4216a575b1371bd9ad59580118808` |

The closure regression of OI-05 is in `closure_rule_v1_regression.json` (`3659efc2…9953`). The spike run's own join log, `grade_join_log_of_record.json` (`25450c57…ab0a`), is kept beside the slot; it is not the protocol's join log.

## Did E4 reproduce the spike exactly?

Yes. R13 lets the signing go ahead only if it did. The E4 receipt compares itself with `corridor_polygon.run_of_record.e4_reproduction_check`:

| Value | Spike run of record | E4 build of record | Same |
|---|---|---|---|
| Grade joins | 345 | 345 | yes |
| Joins SHA-256 | `d289f728…e357` | `d289f728…e357` | yes |
| Edges | 65,328 | 65,328 | yes |
| Grade splits | 371 | 371 | yes |
| OSM hospital objects | 6 | 6 | yes |
| With a DGA record within 150 m | 6 | 6 | yes |
| Located DDPM shelters | 82 | 82 | yes |
| Corroborated shelters | 48 | 48 | yes |
| Corridor geometry, Mae Sai Hospital object, seven input file hashes | | | yes, all |

- **One hash differs, as expected.** The context SHA-256 is `0b2672b6…51a6` for E4 and `62749072…1c10` for the spike. The context hash covers the facilities supplied to the builder. The spike supplied none; E4 supplies the 82 located shelters, as plan P2 says. The road graph, the joins and the counts are the same.
- **Plan row E4 is met:** 4 distinct named hospitals, the three named ways in context, no-route share 0.075% (1.41% without the joins), the PII whitelist enforced and tested, and `load_aois` still returning 6 in both AOI folders.
- **It rebuilds the same.** After the window, `--verify` rebuilt the case in a temporary folder and got the same bytes for the join log, the facility table and the receipt (without its run section), and the same context hash. A review found that those first runs compared the retained context only through the hash written at its end, not its content. The builder now compares the retained context with the rebuild byte for byte, leaving out only the build time. Run that way (14:15 to 14:17), it found everything the same, the retained context included. The builder's later changes alter no byte of the build (`e4_build_of_record.code_changed_after_the_build`).
- **What stays outside Git.** The facility table and the context hold DDPM rows, so they are pitch level and kept under the external data folder. The receipt names them by SHA-256.

## The two compute windows

Both are recorded in full in `planning_protocol_v1b.json`, and both acceptances are entered there.

**Corridor run of record** (`corridor_polygon.run_of_record.compute_window`)

- **When:** 3 October 2026, 10:36:18 to 10:40:20 at UTC+08:00 (02:36:18 to 02:40:20 UTC).
- **Declared by** the agent under R12, the minute the run started. **You accepted it in R13.**
- A tasklist check before and after found no project job. One small unidentified python process (5 and 11 MB) appeared in one sample at 10:37:33; the run was not stopped. The run receipt's claim that the agent "runs nothing else" was not kept to the letter (short read-only checks); v1b corrects it in `run_of_record.receipt_corrections`.
- **Correction, not in the record you accepted in R13:** the record names ten idle helpers, but twelve were running. Two Codex `node_repl` helpers (started 2 October, about 3 MB each) ran throughout; the run's checks did not look for `node_repl`. They are not project jobs. The correction is in `run_of_record.compute_window.helpers_not_named_in_this_record`.

**E4 build of record** (`corridor_polygon.e4_build_of_record.compute_window`)

- **When:** 3 October 2026, 13:26:50 to 13:29:08 at UTC+08:00 (05:26:50 to 05:29:08 UTC). The build ran from 13:26:53 to 13:29:06 by its own clock and took 2.2 minutes.
- **Declared by** the agent under R13, where you accepted in advance a window the agent declares on two terms: no other project job running, and the window recorded.
- **Term 1, no other project job:** tasklist at 13:26:50 (384 processes) and 13:29:08 (387 processes) found no python, node, pnpm, GDAL or SNAP job of the project. Twelve idle helpers of other programs ran throughout: one Adobe node helper, two blender-mcp servers (six processes) and three Codex servers with two node_repl helpers. A sampler watched every 2.7 s (51 samples). It saw only the build's own processes (Python and five ogr2ogr steps, one after another) and those helpers.
- **Term 2, the window recorded:** start, end, checks, sampler figures and the declaration are in the file. During the window the agent ran no other command, not even a progress check.
- **Memory:** free memory stayed between 2.2 and 2.8 GB of 15.2 GiB. That can change time and memory, not the figures.
- **Nobody but the agent has checked this record yet.** You accepted the window in advance in R13, and the agent marked both terms met itself (`terms_of_r13_met`). No attestation covers this window. So there is one more question, in `e4_build_of_record.compute_window.owner_check_of_the_record`: **do you confirm, from this record, that both terms were met for 13:26:50 to 13:29:08?** The schema refuses a signature until an owner answers yes. If you answer no, the build is repeated in a window you name.

## Worth knowing before you sign

- **Hospitals:** the count of 4 meets the plan's minimum exactly. All six OSM objects stay destinations, including the unnamed one: the facility rule takes every OSM hospital, and the sheet's question about the unnamed object had no recommendation and is not answered.
- **Corroborated shelters:** OSM buildings are sparse around the corridor (1,134 objects tagged as buildings in the extract box). So 28 of the 48 corroborated shelters match an amenity only.
- **Main-road entries:** E4 lists every node on a trunk or primary edge (1,939 nodes), so a route ends at the nearest one, as choice 8 says.
- **The corridor run receipt has two wrong sentences and one incomplete list**, corrected in `run_of_record.receipt_corrections`: it says the run replaced the candidate files (it did not), and that the agent ran nothing else in the window. Its list of running helpers leaves out the two `node_repl` helpers.
- **Every run is listed.** `blinding.runs_before_v1b_is_in_force` now also lists the real-data runs made while the E4 builder was written: the 4 km clip test (twice), two OSM extractions on a 2 km box, and one read of the two cases' geometries. It also lists all four `--verify` runs, the review's included. None wrote anything in Git, read a flood layer or computed a score.
- **The builder no longer cites R13 by default.** A later build of record (SE2, walking, or a rerun) records the decision-log entry that accepts its window, or says the window awaits your acceptance. The E4 build's own receipt cites R13 correctly and is unchanged.
- **Rachmania** accepted the pf-07 and SE2 frames as built (R13). Whether any M1-v2 tuning was run before the agent's is still not stated; it does not block v1b.
- **The attestations are unchanged:** the same five statements you attested in R13. The second covers the corridor window; the E4 window is accepted in the file under R13, and the schema refuses a signature unless both windows are accepted. No attestation covers the E4 window record, so it has its own question (above).
- **Signing:** the eight drafter readings (DR-B01 to DR-B08) still await your confirmation in the signing edit. DR-B06 covers S3b too. R13 authorises the agent to enter both signatures and record the hash now that E4 matched exactly, but the agent has not done it. Please first: (1) confirm this summary, including the corridor-window correction above; (2) confirm the five attestations; (3) answer the E4 window question above. Then follow section 7 of `planning_protocol_v1_signing.md`, including the merge into `codex/thai-event-selection` before signing.
