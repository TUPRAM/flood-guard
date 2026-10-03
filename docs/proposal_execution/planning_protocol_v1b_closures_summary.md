# Protocol v1b: the closures, on one screen

For Putu and Rachmania, before you attest "I have read each closure". Written by an AI coding agent on 3 October 2026. v1b is `draft_for_signature`: every item is closed and every parameter is filled in, but nothing is signed and nothing is in force. No FPPS, A-E class or ensemble has been computed. The full text of each closure is in `planning_protocol_v1b.json` under `open_items[].closure`.

The table covers the 17 items that were open when you approved v1b in principle (R11), plus OI-11, which closed on 2 October.

| Item | Final value (or where it lives) | Decided by | Evidence |
|---|---|---|---|
| OI-01 | Corridor polygon `outputs/planning_v1/corridor_of_record.geojson` (827.4 km², one polygon). Demand area: the eight-tambon union clipped to AOI-02 | Choice 21; run of record | [C] |
| OI-02 | Route rule: buffer the whole fastest path to each of the three hospitals by 3 km, with its seven sub-rules | Choice 1 (B) | [R] |
| OI-03 | 4 distinct named hospitals (6 OSM objects); the three named ways in context; 65,328 edges; 2.92 min; 2.44 GiB peak working set; 371 grade splits; no-route share 0.075% | Choice 22; run of record | [E] |
| OI-04 | Grade-join tolerance 0 m. Join log `grade_join_log_of_record.json`: 345 joins | Choice 20; run of record | [J] |
| OI-05 | Closure thresholds: motorway 50 m, residential 30 m, unclassified 30 m. Strict level delays with k = 2. `culvert=*` not read. Regression exact (1,824 walking, 1,738 vehicle) | Choices 4\*, 5, 23 | [R] |
| OI-06 | Main-road entry: nearest trunk or primary node. Shelter match distance 150 m. Mae Sai Hospital is way/371233866. Counts: 6 OSM hospital objects, 6 matched to DGA, 82 located shelters, 48 corroborated (20 by a building) | Choices 8, 19; run of record | [E] |
| OI-07 | Ranking destinations: hospitals and main-road entry. The ranking is bound in the first run receipt | Choices 9, 10 | [R] |
| OI-08 | National anchors, rule A: P5 0.313095, P10 0.351416, P75 0.454083, P90 0.477677, P95 0.494407 (7,425 units) | Choice 6\* | [A] |
| OI-09 | pf-07: the 16 tambons of Mueang Chiang Rai. SE2 routing: the frame plus 3 km (2,422 km², 17 hospital objects). SE2-blind: TH570513 and the 5 Phan tambons that touch it | Choice 15\*; agent build | [F] |
| OI-10 | Reference cell: the default cell. S3b: k = 3. E3: rule C | Choices 3, 17, 18 | [R] |
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
| [E] | `outputs/planning_v1/e0_context_run_of_record.json` (run receipt) | `e038546b84e96715bac5b649a3996201cfaf5c9c67d7f6dcd6b0f88b316c678d` |
| [J] | `outputs/planning_v1/grade_join_log_of_record.json` | `25450c57b829c274921ca5dd21385f6411b12cc7d921696bdea971cfea8fab0a` |
| [A] | `outputs/planning_v1/national_vulnerability_anchors_v1.json` | `2ad161d4c67cbe1567fbb853fe951da3ffb257f06088fbc80e8e297938c73a59` |
| [F] | `resources/planning_frames/planning_frames_v1_receipt.json` | `86f31d8a748be13b7a5a30ce7e46f988d8cbfc53c76f2bf3a96aebf533b130b3` |
| [V] | `docs/proposal_execution/planning_protocol_v1a.json` (signed) | `b6dc549ce9430e0d540fcd0490db1a5dc332758b8cc0a513f773880d0951a954` |

The closure regression of OI-05 is in `closure_rule_v1_regression.json` (`3659efc2…9953`).

## The compute window of the run of record

Recorded in full under `corridor_polygon.run_of_record.compute_window`.

- **When:** 3 October 2026, from 10:36:18 to 10:40:20 at UTC+08:00 (02:36:18 to 02:40:20 UTC). The run itself took 10:36:36 to 10:40:10.
- **Who declared it:** the AI coding agent, under R12 ("the agent first closes every open item, including the corridor run of record in a declared compute window"). **You did not name the window yourselves.** If you do not accept it, say so before signing, and the run can be repeated in a window you name.
- **Checked:** `tasklist` before and after. No python, node, pnpm, GDAL or SNAP job of the project was running. Ten idle helpers ran throughout: an Adobe node helper, two blender-mcp servers and three Codex node servers.
- **Watched:** a process monitor sampled the machine about every 2.4 s. It saw the run's Python process and its nine ogr2ogr steps, one after another. It also saw one python process tree of 5 MB and 11 MB for a single sample at 10:37:33. Its parent had exited and its command could not be read. It was not a heavy job, so the run was not stopped. No run was aborted.
- **Memory:** free memory stayed between 1.0 and 3.5 GB of 15.2 GiB, because desktop applications were open. That can change time and memory. It cannot change the figures: the run gave the same corridor, joins and context as the whole-path candidate of 2 October.
- **The agent's other commands:** only short read-only commands to watch progress, with no test, build or download.

## Worth knowing before you sign

- **Hospitals:** the count of 4 meets the plan's minimum exactly. All six OSM objects stay destinations, including the unnamed one.
- **Corroborated shelters:** OSM buildings are sparse around the corridor (1,134 objects tagged as buildings in the extract box). So 28 of the 48 corroborated shelters match an amenity only.
- **Plan task E4:** `build_planning_context.py` does not exist on this lineage. The context of record was built by the spike script through the unchanged builder and is named by its SHA-256 (`62749072…1c10`). A later E4 build must reproduce that hash and the joins, or say why it does not.
- **Rachmania:** please review the pf-07 build (OI-09).
- **Signing:** the eight drafter readings (DR-B01 to DR-B08) still await your confirmation in the signing edit. Follow section 7 of `planning_protocol_v1_signing.md`.
