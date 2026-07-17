# Proposal claim-to-evidence matrix

This matrix is the wording boundary for the proposal, demo, pitch, and
application form. A claim may be strengthened only after its named evidence is
present and the final manifest re-hashes it.

| ID | Proposed claim | Repository or external evidence | Current status | Permitted wording |
|---|---|---|---|---|
| C01 | FloodGuard is a preparedness and rapid post-event prioritization tool. | `AGENTS.md`, `README.md`, public contract fields. | Implemented | Use exactly this boundary; do not call it an official warning or live evacuation system. |
| C02 | The platform has role-specific `/public`, `/command`, and `/studio` routes. | `apps/web/src/app/`, route smoke tests and final screenshots. | Implemented; final visual receipt pending | May say the routes exist and work with fixtures. |
| C03 | The web demo works without a hosted API or external network. | Committed offline bundle, service worker, static export, offline smoke. | Implemented; final clean-environment receipt pending | May say “offline fixture demo”; never imply live data. |
| C04 | FastAPI exposes versioned artifact and deterministic scenario contracts. | `services/api/src/floodguard_api/app.py`, Pydantic models, API tests. | Implemented; final test receipt pending | May say tested contract layer; do not imply the proposal demo requires a hosted API. |
| C05 | Service health and data freshness are separate. | `/api/v1/health`, `/api/v1/status`, repository tests. | Implemented | May describe healthy service plus stale/blocked/unavailable data states. |
| C06 | The access method is nearest-facility shortest-path threshold access. | `src/floodguard/access.py`, tests and architecture docs. | Implemented | Do not call the current method 2SFCA or capacity-aware accessibility. |
| C07 | FPPS weights and A-E action classes are transparent and tested. | `AGENTS.md`, `src/floodguard/scoring.py`, scoring tests. | Implemented | May list fixed weights and class meanings; they are planning recommendations, not orders. |
| C08 | GeoAI is isolated from root FloodGuard dependencies. | `services/geoai-runner/pyproject.toml`, root `pyproject.toml`, normal test command. | Implemented | May say normal root/API/web tests do not require GeoAI, PyTorch, GPU or network. |
| C09 | Raw negative SAR/terrain values do not pass through implicit `/255`. | GeoAI preprocessing contract, sidecar hash and tests. | Implemented | May describe explicit clip-and-encode `uint8` workflow. |
| C10 | The real GeoAI smoke invokes tile export and tiled inference. | `services/geoai-runner/tests/test_geoai_smoke.py`, generated proof receipt. | Implemented; final smoke receipt pending | May name `export_geotiff_tiles`, model construction and `predict_geotiff`. |
| C11 | GeoAI model training has been completed. | No executed `train_segmentation_model` evidence currently exists. | Not proven | Do not claim completed training. Say “training wrapper and model-construction proof.” |
| C12 | The synthetic output is a validated real flood detector. | Synthetic proof only; no qualified real reference. | False | State that it proves integration wiring, not accuracy. |
| C13 | Class-1 probability is explicit and grid validated. | `geoai_runner/infer.py`, smoke test and proof receipt. | Implemented | May describe one-band `flood_probability_0_1`, CRS/transform/shape/nodata/range checks. |
| C14 | Candidate GeoAI evidence feeds FPPS/action classes. | Candidate contract sets `can_feed_decision_layer=false`. | Blocked by design | Say aggregation is report-only and cannot feed decisions. |
| C15 | A trusted official-input zonal boundary exists. | `src/floodguard/trusted_zonal_adapter.py` and substitution/security tests. | Implemented, not exercised with accepted official data | May describe the adapter and its fail-closed tests; do not claim a candidate raster passed it. |
| C16 | A controlled real three-model experiment has run. | Controlled experiment gate receipt states `experiment_executed=false`. | Blocked | Do not publish real comparison metrics. Describe the post-selection method and blockers. |
| C17 | Mae Sai evidence is official validation. | Weak-reference candidate analysis and blocked gate receipt. | False | Call Mae Sai a candidate/planning demo or weak-reference engineering analysis. |
| C18 | Hat Yai is a completed validation/demo implementation. | Metadata and narrative planning only. | Not implemented | Call Hat Yai a future transfer and urban stress-test location. |
| C19 | Existing candidate metrics prove deployable accuracy. | Weak-reference baseline/logistic outputs are low-confidence screening evidence. | False | Do not use candidate metrics as official or field-validated accuracy. |
| C20 | Team capability fields are complete. | `submission-metadata.json`. | Blocked on owner input | Do not build final PDF until all three names, skills and evidence items are present. |
| C21 | A public demo URL and immutable proposal tag exist. | `submission-metadata.json`. | Blocked on deployment/release | Do not print or infer a URL/tag before they exist. |
| C22 | The official proposal close is 2 August 2026. | Official GISTDA GeoHackathon 2026 brief. | Externally verified for this package | Use with a final portal recheck before submission; internal target remains 30 July. |

## Required proposal corrections from the supplied source

- Replace “Mae Sai validation” with “Mae Sai candidate/planning demo” unless a
  qualified reference and all promotion gates pass.
- Move Hat Yai from “decision story” evidence to future transfer/stress test.
- Replace “semantic model training visible in prototype” with “training wrapper
  and model-construction proof” unless an actual bounded training receipt is
  added.
- Do not show synthetic perfect metrics from fixture contracts as model
  performance.
- Replace the old `248 passing tests` sentence with the exact fresh test
  receipt only after final verification.
- Keep the current access method description as nearest-facility shortest-path
  threshold analysis.
