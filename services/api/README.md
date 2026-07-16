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
