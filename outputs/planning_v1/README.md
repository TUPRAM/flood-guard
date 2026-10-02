# outputs/planning_v1

Small committed outputs of the planning overlay (restructuring plan v2, section 3.1). On 3 October 2026 this folder holds only the receipts of the engineering runs made for protocol v1b. Protocol v1b is **not signed**: no FPPS, no A–E class and no ensemble has been computed, and no file here holds a value for a single tambon.

Every JSON receipt carries `source_timestamp`, `confidence_class` (always `low`), `assumptions`, `official_warning: false` and its input hashes. None of these outputs is an official warning or an observation of a flood.

| File | What it is | Status | Written by |
|---|---|---|---|
| `national_vulnerability_anchors_v1.json` | National percentiles of the dependent share (P5, P10, P75, P90, P95) over 7,425 `tha_admin3` units | Evidence for closed item OI-08. Computed once; `--verify` recomputes and compares | `scripts/build_national_vulnerability_anchors.py` |
| `closure_rule_v1_regression.json` | The permissive closure level reproduces the AOI-01 finals closed edges: 1,824 walking, 1,738 vehicle, exact match | Evidence for `closure_rule_v1.regression.result` (OI-05, still open) | `scripts/check_closure_rule_regression.py` |
| `se2_blind_district_ranking.json` | Chiang Rai districts ranked by WorldPop 2020 residents; the SE2-blind district is Phan (TH5705) | Evidence for `se2_frame.se2_blind_district` (OI-09, still open) | `scripts/rank_chiang_rai_district_population.py` |
| `e0_context_spike_proposal.json`, `e0_context_spike_whole_path.json` | The E0 context spike under two candidate route rules | **Candidates.** The route rule (OI-02) is an owner decision | `scripts/run_planning_context_spike.py` |
| `corridor_candidate_proposal.geojson`, `corridor_candidate_whole_path.geojson` | The two candidate corridor polygons | **Candidates.** Neither is the corridor of record | the same script |
| `grade_join_log_candidate_proposal.json`, `grade_join_log_candidate_whole_path.json` | The endpoint joins (decision D13) each spike context would get | **Candidates.** The log of record comes from the E4 context build | the same script |

The inputs are read-only files outside Git. Their locations are arguments of each script, and their SHA-256 values are in each receipt. The owner decisions these candidates wait on are in `docs/proposal_execution/planning_protocol_v1b_owner_choices.md`.
