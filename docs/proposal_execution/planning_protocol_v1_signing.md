# Planning protocol v1a and v1b: reading guide and signing procedure

For Putu and Rachmania. Drafted by an AI coding agent on 1 October 2026, on owner go-ahead R5.

**Status: both files are drafts. Nothing here is in force.** No receipt has been written. Agents draft, humans sign: an agent never fills a signature entry and never appends the receipt on its own.

| File | What it is | Status |
|---|---|---|
| `planning_protocol_v1a.json` | Decision rules (plan row G7a) | `draft_for_signature` |
| `planning_protocol_v1b.json` | Engineering addendum (plan row G7b) | `incomplete_draft`: 11 open items |
| `planning_protocol_v1a.schema.json`, `planning_protocol_v1b.schema.json` | Shape checks for the two files | n/a |
| `tests/test_planning_protocol.py` | Tests that tie the files to the signed decisions and to `scoring.py` | n/a |

Both files are a "declared protocol after exploratory analysis". They are never called preregistered or confirmatory.

## 1. What v1a decides

- **Evidence tiers and lanes.** T0 engine test, T1 scenario, T2 own detector, T3 dated agency map, T4 qualified (locked). Lanes OBS, SCN, SCN-ENV and ENG, and what each may and may not claim.
- **Date rule (D3).** An input counts as observed only within ±3 days of the case date. The accumulated 4009 layer is a season-envelope scenario only. The 22 Oct layer is its own case, O2.
- **Confidence rule v1.** Eight conditions for "medium". "High" is never assigned in this release. Rights are not part of confidence.
- **Scoring frame (D4).** Weights 0.30 / 0.25 / 0.20 / 0.15 / 0.10. Flood anchor 0.20, with 0.10 and 0.30 as sensitivity and the disclosure that 0.20 was chosen after seeing the data. Share-only exposure. National P10/P90 vulnerability anchors. WorldCover class 80 for permanent water.
- **Class rules (D6).** v1 is the unchanged `scoring.py` and is binding. v2 is a labelled secondary axis.
- **Nine guardrails** from plan section 2.3, including the blinding rule: no FPPS, class or ensemble until v1b is in force.
- **Cases (D7)** and the case-selection disclosure for SE2.
- **GEOID split, the T2 skill bar and the demo-tambon rule.**
- **Exploratory-knowledge disclosure.** Sixteen items the team had already seen, where each lives and which rule it could have shaped.
- **Change control.** After signing, any change needs a v2 with a written reason, and every run is reported.

## 2. What v1b decides

The corridor polygon, the grade-join policy (D13), closure rule v1, the facility sets and the corroboration rule, critical-link selection, the national vulnerability anchors, the ensemble grid (540 cells per lane) and the selection rules for the scenario and engine cells.

Everything the plan fixes is filled in. The rest are open items (section 4).

## 3. What to check before signing v1a

1. **Read the exploratory-knowledge disclosure first.** Add anything you have seen that is not listed. This is the section a critic will read.
2. **Confirm four readings the drafting agent had to make.** The plan does not state them:
   - GEOID split: tile IDs sorted ascending, first 15 development (9–33), last 14 test (35–50).
   - Leave-one-component-out: the dropped component's weight is set to 0 and the other four are renormalised.
   - Demo tambon tie-break: lowest `subdistrict_id`.
   - Accumulated 4009 layer: the file names the layer `CHIANGRAI_20240801_20241012_AccumulatedFlood`; the decisions call it "Aug–Oct".
3. **Check one figure.** Plan section 3.4 says the 0.05 anchor saturated in "5 of 8" tambons. The envelope shares in the scratch file `whatif.py` look like six tambons above 5%. The draft repeats the plan's figure. Correct it if it is wrong.
4. **State whether any M1-v2 tuning on GEOID tiles has already been run.** The plan wants the split declared before tuning. If tuning has started, add it to the disclosure.
5. **Open decisions.** D5, D8, D10 and D14–D16 are listed as "undefined in the plan files". Supply the wording or record them as withdrawn. They do not block signing.
6. **Rachmania signs her own entry.** The decision log records her signature through Putu. This file needs her own.
7. **Schedule.** The plan had v1a on 28 Sep. This draft is dated 1 Oct, and the disclosure lists what was seen in between.

## 4. Open items in v1b

v1b cannot be signed until all of these are closed. None needs a download.

| ID | What is missing | What produces it | Who |
|---|---|---|---|
| OI-01 | The corridor polygon file and its SHA-256 | E0 spike, then E4 | Agent with Putu |
| OI-02 | The rule that picks the trunk/primary routes to the three hospitals (a proposal is in the file) | Owner decision | Putu |
| OI-03 | E0 spike values: hospitals (≥4), the three hospital ways in context, edges, time, RAM, grade splits, no-route share (≤10%) | E0 spike | Agent with Putu |
| OI-04 | Grade-join tolerance (proposal: 0 m) and the logged join list | E4 | Agent with Putu |
| OI-05 | Closure rule: length thresholds for motorway, residential and unclassified roads; the delay rule under "strict"; the regression result (1,824 walking / 1,738 vehicle) | Owner decision; E3 | Putu; agent |
| OI-06 | Main-road entry definition; shelter match distance; facility counts in the corridor; Mae Sai Hospital's OSM ID | Owner decision; E4 | Putu; agent |
| OI-07 | Destination set for the critical-link ranking; the ranking output and its SHA-256 | Owner decision; E6 | Putu; agent, Rachmania reviews |
| OI-08 | National anchors P5, P10, P75, P90, P95; the tambon set and percentile method | E2 (run once) | Agent, Putu reviews |
| OI-09 | The Mueang Chiang Rai frame pf-07 (file, tambon list, routing and hospitals); the SE2-blind district | P1; a population ranking | Rachmania; agent |
| OI-10 | Four unstated points: reference cell for class retention, k for S3b, base case for S8, selection rule for E3 | Owner decision | Putu, Rachmania |
| OI-11 | The recorded SHA-256 of the signed v1a | Signing v1a | Putu, Rachmania |

On OI-07: plan row G7b lists only E0 and E4 as dependencies, but plan 6.3 says links and nodes are fixed before any scoring. Choose one: run E6 before signing and bind its output here, or sign with the rule alone and bind the output in the first run receipt.

### Inputs for the national anchors

The WorldPop 2024 1 km age rasters are **not** under `C:/Users/iputu/Documents/FloodGuard_external_data`. They are already on disk at `C:/Users/iputu/Documents/Project Support/FloodGuard/open-data/2026-09-23-worldpop-age-2024-r2025a-1km-ua/`: 20 files `tha_t_{band}_2024_CN_1km_R2025A_UA_v1.tif`, 51,593,135 bytes, manifest SHA-256 `f7a16987…8356c`, status PASS. The national tambon boundaries (COD-AB `tha_admin3`) are under `FloodGuard_external_data/open_context/hdx_cod_ab/`. **No download is needed for the anchors.**

### Downloads that need your approval

None is needed to close a v1b open item. Each is needed later.

| ID | File | Source | Size | Needed for |
|---|---|---|---|---|
| DL-1 | JRC Global Surface Water v1.4 `occurrence_90E_20Nv1_4_2021.tif` (seasonality optional) | JRC download page | about 70–100 MB (+30 MB) | JRC sensitivity note and v2 class D fallback south of 20°N (SE2) |
| DL-2 | JRC `occurrence_100E_30Nv1_4_2021.tif` (seasonality optional) | JRC download page | about 70–100 MB (+30 MB) | The same, for the strip of Mae Sai east of 100°E. Not in the prep pack; found from tile bounds |
| DL-3 | `Copernicus_DSM_COG_10_N19_00_E099_00_DEM.tif` | AWS `copernicus-dem-30m` | about 40–60 MB | Terrain south of 20°N. Not used by any v1b parameter |
| DL-4 | One Sentinel-1 GRD SAFE, 18 Sep 2024 | CDSE (login) | about 1.3 GB | D12 fallback, only without a GEE account |

## 5. How to sign and record the hash

### What exists on this lineage

No script writes `RECEIPTS.jsonl`. Its 49 lines were appended by hand, one JSON object per line, with `schema_version` `floodguard.proposal_execution_receipt.v1`. The automated track binds a protocol to a commit by reading it with `git show <commit>:<path>` (`scripts/acquire_earth_search_automated_optical_v2.py`). The procedure below follows both conventions.

Three rules:

- **The hash is taken over the committed JSON bytes, after the signature block is filled.** The file never contains its own hash.
- **A file is in force only when its line is in `RECEIPTS.jsonl`.** The status field alone does not make it so.
- **After the receipt, the file is not edited again.** One changed byte breaks the hash. A change needs `planning_protocol_v2`.

The decision log says the hash goes into `RECEIPTS.jsonl` on the `codex/thai-event-selection` lineage. This draft sits on `claude/planning-protocol-v1`, cut from that branch. A human decides how the branch lands.

### Steps for v1a

Run from the repository root. `python` means the project environment (`uv run python`, or the venv's `python.exe`).

1. **Amend and sign.** Edit `docs/proposal_execution/planning_protocol_v1a.json`:
   - Make any amendments. List each one, in a sentence, in `signature_block.amendments_at_signing`.
   - Set `"status": "signed"`.
   - Replace `status_note` with: `"Signed. In force only once the SHA-256 of this committed file is recorded in docs/proposal_execution/RECEIPTS.jsonl."`
   - Each signer fills their own entry: `signed_by` (full name), `signed_at_utc` (like `2026-10-02T03:00:00Z`) and `attestation` (one sentence confirming the three statements in `attestations_required`).
   - Keep the two-space indent, ASCII characters, LF line endings and one final newline.
2. **Tell the tests.** In `tests/test_planning_protocol.py` set `EXPECTED_STATUS["v1a"]` to `"signed"`.
3. **Run the tests.**

   ```bash
   python -m pytest -q tests/test_planning_protocol.py tests/test_scoring.py tests/test_scoring_sensitivity.py
   ```

4. **Make the signing commit.** Only these two files.

   ```bash
   git add docs/proposal_execution/planning_protocol_v1a.json tests/test_planning_protocol.py
   git commit -m "docs(protocol): sign planning protocol v1a"
   git status --short   # must print nothing for these files
   ```

5. **Build the receipt line from the committed bytes.** Save the script below as a temporary file outside the repository and run it with `v1a` as its argument. It reads the file with `git show`, so it hashes exactly what was committed. Do not pipe `git show` through PowerShell to hash it: PowerShell 5.1 re-encodes the bytes.

   ```python
   import hashlib, json, subprocess, sys
   from datetime import datetime, timezone

   name = sys.argv[1]                      # "v1a" or "v1b"
   tests_passed = sys.argv[2]              # the pytest summary, e.g. "45 passed"
   doc = f"docs/proposal_execution/planning_protocol_{name}.json"
   schema = f"docs/proposal_execution/planning_protocol_{name}.schema.json"

   def git(*args):
       return subprocess.run(["git", *args], check=True, capture_output=True).stdout

   commit = git("rev-parse", "HEAD").decode().strip()
   tree = git("rev-parse", "HEAD^{tree}").decode().strip()
   committed = lambda path: hashlib.sha256(git("show", f"{commit}:{path}")).hexdigest()
   on_disk = hashlib.sha256(open(doc, "rb").read()).hexdigest()
   assert committed(doc) == on_disk, "working file differs from the committed bytes"
   assert json.loads(git("show", f"{commit}:{doc}"))["status"] == "signed"

   inputs = {
       f"planning_protocol_{name}_schema_sha256": committed(schema),
       "scoring_py_sha256": committed("src/floodguard/scoring.py"),
   }
   if name == "v1b":
       inputs["planning_protocol_v1a_sha256"] = committed("docs/proposal_execution/planning_protocol_v1a.json")

   receipt = {
       "schema_version": "floodguard.proposal_execution_receipt.v1",
       "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "result": "PASS",
       "source_commit": commit,
       "source_tree": tree,
       "source_state": "Exact clean signing commit. The protocol bytes are those of this commit; this receipt line is added in the next commit.",
       "input_hashes": inputs,
       "output_hashes": {f"planning_protocol_{name}_sha256": committed(doc)},
       "commands_actually_run": [
           "python -m pytest -q tests/test_planning_protocol.py tests/test_scoring.py tests/test_scoring_sensitivity.py",
           f"git show {commit}:{doc} | sha256 (read as bytes by the signing script)",
       ],
       "command_record_status": "PASS",
       "tests_or_checks": [
           f"Protocol and scoring tests: {tests_passed}",
           "SHA-256 of the committed file equals SHA-256 of the working file",
       ],
       "scientific_acceptance": False,
       "human_acceptance": False,
       "official_warning": False,
       "operational_status": "non_operational",
       "milestone": f"P0-{name}",
       "scientific_evidence": "None. A declared protocol after exploratory analysis. No planning-tier FPPS, A-E class or ensemble exists at this receipt.",
       "human_evidence": "Team governance signature by Putu (owner) and Rachmania (method co-signer), recorded in the file's signature block. Not an independent review.",
       "limitations": "Rules were declared after exploratory analysis, as disclosed in v1a. Decisions D5, D8, D10 and D14-D16 remain open.",
       "next_dependencies": "v1a: close the v1b open items, then sign v1b. v1b: planning-tier scoring may start.",
       "eligible_claim": f"Planning protocol {name} is signed and its committed bytes are bound by SHA-256.",
   }
   line = json.dumps(receipt, separators=(",", ":"), ensure_ascii=False)
   sys.stdout.buffer.write(line.encode("utf-8") + bytes([10]))   # raw bytes: one line, one LF, UTF-8
   ```

   `human_acceptance` stays `false`, as in every earlier receipt: in this file it means independent or downstream acceptance, which a team governance signature is not.

6. **Read the printed line, then append it.** It must be one line. Append it to the end of `docs/proposal_execution/RECEIPTS.jsonl`, followed by one LF and no CR, and change nothing above it. The script writes raw bytes so that Windows does not add a CR.

   ```bash
   python sign_receipt.py v1a "<N> passed"                                             # read the line first
   python sign_receipt.py v1a "<N> passed" >> docs/proposal_execution/RECEIPTS.jsonl   # Git Bash, not PowerShell
   python -c "print(list(open('docs/proposal_execution/RECEIPTS.jsonl','rb').read()[-2:]))"  # must print [125, 10]
   git diff --stat docs/proposal_execution/RECEIPTS.jsonl                              # must show 1 insertion
   ```

7. **Commit the receipt.**

   ```bash
   python -m pytest -q tests/test_planning_protocol.py
   git add docs/proposal_execution/RECEIPTS.jsonl
   git commit -m "docs(protocol): record the planning protocol v1a hash"
   ```

8. **Check it.** The last receipt's `output_hashes.planning_protocol_v1a_sha256` must equal the SHA-256 of `git show <source_commit>:docs/proposal_execution/planning_protocol_v1a.json`. From this commit on, v1a is in force.

### Steps for v1b

1. Close every open item. For each one, write the value into its field, set the item's `status` to `"closed"` and add a `closure` object (`closed_on`, `closed_by`, `value_or_location`, `evidence_sha256`). Set the section's `status` to `"fixed"` when none of its items is open.
2. Copy the recorded v1a hash into `depends_on.v1a_sha256`.
3. Set `"status": "draft_for_signature"` and commit. The schema refuses this while any item is open.
4. Follow steps 1–8 above with `v1b` in place of `v1a`, and set `EXPECTED_STATUS["v1b"]` to `"signed"`.

**Only after the v1b receipt is committed may any FPPS, A–E class or ensemble be computed for a real unit.**

## 6. What the agent did not do

- It did not append to `RECEIPTS.jsonl`, sign anything, push, merge or download.
- It did not compute any FPPS, class, ensemble or national anchor.
- It did not run the E0 spike or any context build.
