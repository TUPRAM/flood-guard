# FloodGuard artifact API

This FastAPI service exposes committed FloodGuard decision artifacts through
strict response models. It does not recalculate FPPS in the browser and does
not turn fixture or candidate data into an official warning.

The API reads the repository's small CSV, GeoJSON, and Markdown artifacts. It
never serves source rasters, external workspaces, or local filesystem paths.
Service health (`/api/v1/health`) is deliberately separate from dataset state
(`/api/v1/status`). A healthy process can therefore report blocked,
unavailable, or stale data without conflating those conditions.

## Run locally

```powershell
uv sync --project services/api --group dev
uv run --project services/api uvicorn floodguard_api.app:app --app-dir services/api/src --host 127.0.0.1 --port 8000
```

The safe default accepts browser requests from `localhost:3000` and
`127.0.0.1:3000`. For a judging or hosted web origin, set a comma-separated
allowlist before starting the API, for example:

```powershell
$env:FLOODGUARD_CORS_ORIGINS = "https://judge.example.org,http://localhost:3100"
```

The value accepts exact HTTP(S) origins only; paths, credentials, wildcards,
queries, and fragments are rejected.

## Test

```powershell
uv run --project services/api pytest services/api/tests
```

Scenario requests are restricted to the service-owned registry. The temporary
shelter capacity is preserved as planning metadata because the tested access
engine is nearest-facility shortest-path threshold analysis and does not model
capacity. No scenario response is an evacuation route or live condition.

## Study-area profiles

The default profile remains `fixture_thailand_demo`. The real-coordinate,
provenance-tracked Mae Sai context is selected explicitly:

```text
GET /api/v1/status?study_area=mae_sai_candidate_v1
GET /api/v1/areas?study_area=mae_sai_candidate_v1
GET /api/v1/layers?study_area=mae_sai_candidate_v1
GET /api/v1/layer-data/road_risk?study_area=mae_sai_candidate_v1&detail=regional
GET /api/v1/layer-data/facilities?study_area=mae_sai_candidate_v1&area_id=TH570901
GET /api/v1/scenarios?study_area=mae_sai_candidate_v1
```

The Mae Sai profile validates the study-area manifest and exact layer bytes
before serving them. It contains eight ADM3 reporting areas, modeled road-risk
candidates, open-context facility candidates, and modeled access evidence. It
is historic candidate context, not current road-closure, shelter-availability,
field-validation, or official-warning data.

Mae Sai scenario requests also include
`"study_area":"mae_sai_candidate_v1"` and may use only the parameter defaults
or allowed values returned by its scenario catalog. Their compact graph,
population, and facility inputs are bound by an immutable self-hashed manifest.
Responses expose that manifest hash and receipt hash, retain
`fpps_recalculated=false`, and contain access/equity deltas only. A missing or
substituted candidate artifact blocks the selected profile or scenario; the API
does not silently replace it with fixture data.

## Bounded agency pilot

The `/api/v1/pilot/*` routes add server-enforced identity, role capabilities,
signed acceptance receipts, tamper-evident audit logging, governed retention,
and deployment monitoring. FastAPI revalidates authorization on every protected
request; a browser role display is never sufficient.

The default installation has no pilot key material, pre-provisioned audit
ledger, independently mounted audit anchor, governed retention root/private
quarantine, current signed retention catalog, or acceptance receipt and
therefore remains non-operational. Configuration must come from an external
secret manager and external artifact workspace. The service stores and exposes
key IDs only.

The JSONL audit implementation is single-process. A configured audit path
requires `FLOODGUARD_PILOT_AUDIT_ANCHOR`,
`FLOODGUARD_PILOT_AUDIT_WRITER_MODE=single_process`, and a single API worker.
Provision the empty ledger and signed genesis anchor once with
`scripts/provision_audit_ledger.py`; normal startup never creates or repairs
them. Use a transactional append store before multi-worker deployment.

Retention requests name signed-catalog artifact IDs only. The catalog supplies
server-owned paths, categories, creation times, legal holds, and SHA-256 values;
it expires within 30 days and must cover the mandatory pilot evidence set. The
mandatory entries must resolve to the exact configured ledger, anchor, served
manifest, field receipt, and—after installation—acceptance receipt. Audit roles
bind to the signed immutable audit-instance ID; immutable evidence binds exact
bytes. The bootstrap acceptance target must contain the exact signed sentinel
bytes, and one descriptor-bound manifest/field snapshot is reused through each
acceptance or promotion decision. Dummy files, mid-check substitutions, and
identical copies at different paths are rejected.
Agency-operational responses additionally require exact canonical-response
membership in the accepted served-response manifest, including source time,
data version, and underlying artifact hashes. Monitoring evaluates the exact
current status payload through that same membership check.

See:

- `docs/agency-pilot-architecture.md`;
- `docs/agency-pilot-deployment-runbook.md`;
- `docs/agency-pilot-acceptance-criteria.md`;
- `docs/agency-pilot-field-validation-protocol.md`;
- `docs/agency-pilot-retention-policy.md`.
