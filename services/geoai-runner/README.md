# FloodGuard isolated GeoAI runner

This service is the only FloodGuard environment allowed to install or import
`geoai-py`. The root decision package, API, web application, and normal root
test suite remain independent of GeoAI, PyTorch, GPU support, source rasters,
and network access.

The runner produces candidate evidence. It does not replace FloodGuard road
risk, nearest-facility access loss, equity, FPPS, or A–E action classes. It is
not an official warning system or a live evacuation navigator.

## Frozen environment

- Python: `3.12` exactly (`.python-version` and `requires-python`)
- GeoAI package: `geoai-py==0.41.1`
- semantic model dependency: `segmentation-models-pytorch==0.5.0`
- ML runtime: `torch==2.13.0` and `torchvision==0.28.0`
- raster boundary: `rasterio==1.4.4`
- numeric boundary: `numpy==2.4.2`
- reviewed source receipt declared by the supplied architecture package:
  `6833c8b71fb18f5b8ea17d5d9f8e0745157643c2`

The package version and lockfile are reproducible here. A PyPI wheel does not
prove a Git commit. The available source ZIP proves GeoAI version `0.41.1` but
does not contain `.git` metadata, so the commit above remains a declared source
receipt rather than independently re-proven local evidence. Do not strengthen
that claim without a commit-specific archive or Git checkout.

Create the dependency-light normal-test environment:

```powershell
uv sync --project services/geoai-runner --group test
```

Install the isolated GeoAI extra only for an explicit real smoke run:

```powershell
uv sync --project services/geoai-runner --group test --extra geoai
```

The service-local `uv.lock` resolves both the normal environment and the
optional GeoAI environment. Neither command changes the root dependencies.

## Auditable feature contract

The stock GeoAI 0.41.1 GeoTIFF semantic-training loader reads raster values as
`float32` and divides them by 255. Its generic tiled inference path first casts
windows to `float32`; its default preprocessing then conditionally divides by
255. Raw negative SAR dB, DEM, slope, HAND, or ratio values are therefore not
safe inputs.

FloodGuard uses one explicit path for both training and inference:

1. Validate a georeferenced 6–8-band physical stack with immutable band names.
2. Clip each band to the versioned physical range in `DEFAULT_TRANSFORMS`.
3. Encode to `uint8 [0,255]` and write a canonical transform sidecar with a
   SHA-256 receipt.
4. Train through GeoAI's stock GeoTIFF loader, which performs `/255`.
5. During inference, require exact integer-encoded values and explicitly
   perform the same `/255` transform through `preprocess_fn`.

The run contract also carries typed `physical_min`, `physical_max`, units, and
description fields for every ordered band. Preparation, training, and inference
all re-hash and parse the same sidecar immediately before use. Matching a
feature grid without matching sidecar bytes and transform statistics is a hard
failure.

The default eight-band order is:

1. pre-event VV dB;
2. post-event VV dB;
3. pre-event VH dB;
4. post-event VH dB;
5. VV change dB;
6. VH change dB;
7. slope in degrees;
8. permanent-water flag.

The encoder rejects non-finite cells and nodata. A fully valid common footprint
must be established before encoding. The aligned label raster must have the
same CRS, transform, dimensions, resolution, and bounds, with `0 = non-flood`,
`1 = flood`, and `255 = nodata`. Every exported label tile is re-opened before
manifesting. Because GeoAI 0.41.1 treats every positive raster value as a class,
FloodGuard gives the exporter a temporary derived 0/1 mask, compares every
valid exported class cell back to the checksum-bound original mask, and then
restores `255` only at the original nodata cells. Nodata metadata must finish as
exactly `255`, values must remain in `{0,1,255}`, and at least one valid class
cell must exist. Training passes `ignore_index=255` explicitly so GeoAI cannot
reinterpret nodata as flood.

## GeoAI call boundaries

The wrappers import GeoAI lazily only when no injected test double is supplied:

- `prepare.export_training_tiles` validates all grids and then calls
  `geoai.utils.training.export_geotiff_tiles`;
- `train.train_segmentation_candidate` checks the external workspace and
  checksum-bound tile membership, then calls
  `geoai.train.train_segmentation_model` with `encoder_weights=None`. It wraps
  stock GeoAI's raw `best_model.pth` state dictionary in a FloodGuard envelope
  containing architecture, encoder, channels, model revision, source-state
  hash, GeoAI receipt, FloodGuard commit, and five canonical training-lineage
  receipts: prepared tile manifest, preprocessing sidecar, encoded feature
  stack, reference mask, and input manifest;
- `infer.run_prediction` re-hashes the feature, sidecar, prepared manifest, and
  packaged checkpoint. It requires every lineage receipt returned by the model
  loader to match the completed run contract before calling
  `geoai.inference.predict_geotiff` with the frozen preprocessing function and
  an explicit two-logit softmax/class-1 postprocessor. It never accepts an
  unrelated or lineage-substituted in-memory model object.

The final probability raster is one `float32` band named
`flood_probability_0_1`, uses `-9999` nodata, retains the feature grid, and must
contain only finite valid values in `[0,1]`. `geoai.water.segment_water` is not
used because its optical open-water workflow is not the Sentinel-1 event-flood
model.

Input-manifest receipts are canonical SHA-256 hashes over all typed input rows,
sorted by role and product ID, so row ordering cannot create a different
lineage while any product, checksum, timestamp, or permission substitution
does. The checkpoint envelope schema is `1.1`; older envelopes without the
five lineage receipts fail closed.

GeoAI's internal random training split is monitoring evidence only. The run
contract requires non-overlapping train and holdout polygons represented by
committed bounds. After stock GeoAI tile export, FloodGuard derives each tile's
spatial group from its georeferenced bounds. It moves holdout pairs to a
separate directory, moves boundary-crossing or unassigned pairs to a rejected
directory, and writes only fully contained training pairs to the prepared tile
manifest. The manifest records relative paths, the derived spatial group, and
both file hashes. The returned manifest hash must be placed in a new immutable
`prepared` or `running` contract revision. Training re-hashes the manifest and
sidecar, requires exact directory coverage, and rejects duplicate, unlisted,
renamed, mutated, holdout, or boundary-crossing tiles. Final comparison
evidence must come from the untouched spatial holdout directory.

## Gates and outputs

Every run contract records immutable input roles, product IDs and SHA-256
values, reference-mask status and bytes, encoded-feature bytes,
CRS/resolution/bounds, model identity and checksum, typed preprocessing
statistics and sidecar, source time, confidence, assumptions, processing scope,
and promotion gates. Processing requires pre-event SAR, post-event SAR, and
reference-mask provenance plus each ancillary terrain/permanent-water receipt
implied by the channel list. Pre/post timing is ordered and bounded by the run
source time. A carried-forward boolean cannot override a blocked input row or
an unconfirmed reference mask.

Large rasters, tiles, checkpoints, and manifests must stay under the declared
absolute external workspace. Public manifests redact that location to
`external-workspace/<run-id>` and are validated against a versioned bundled
copy of the shared model-run schema before any write. A drift test requires the
bundled and repository-owned schemas to remain identical.
Candidate manifests always set `official_warning=false` and cannot feed the
decision layer. The FloodGuard aggregation bridge only accepts them with its
explicit report-only option.

No real training should start until product provenance, timing, licensing,
checksums, reference-mask use, and the spatial holdout all pass. The currently
available Mae Sai weak reference does not clear those real-training gates.

## CLI

The CLI covers dependency-free validation/encoding and the guarded GeoAI tile
export boundary:

```powershell
$workspace = $env:FLOODGUARD_GEOAI_WORKSPACE
$physical = Join-Path $workspace "physical.tif"
$encoded = Join-Path $workspace "encoded.tif"
$sidecar = Join-Path $workspace "transform.json"
$mask = Join-Path $workspace "mask.tif"
$tiles = Join-Path $workspace "tiles"
$manifest = Join-Path $workspace "run-manifest.json"
uv run --project services/geoai-runner floodguard-geoai validate-contract --contract run.json
uv run --project services/geoai-runner floodguard-geoai encode --workspace $workspace --input $physical --output $encoded --sidecar $sidecar
uv run --project services/geoai-runner floodguard-geoai validate-grid --contract run.json --features $encoded --mask $mask --sidecar $sidecar
uv run --project services/geoai-runner floodguard-geoai export-tiles --contract run.json --features $encoded --mask $mask --sidecar $sidecar --output-dir $tiles
uv run --project services/geoai-runner floodguard-geoai write-manifest --contract run.json --evidence validation.json --output $manifest
```

Training, checkpoint packaging, and model construction are intentionally
programmatic. Spatial membership is derived from raster bounds, never inferred
from filenames or accepted from caller assertions. The safe sequence is:
export and partition tiles from an unprepared contract; capture the generated
manifest receipt in a `prepared` or `running` contract revision; train and
package; then create a `completed` contract revision with both the manifest and
packaged-checkpoint SHA-256 receipts before inference. Inference also requires
the prepared manifest artifact itself so its bytes can be re-hashed; supplying
a different manifest or input-manifest lineage cannot be authorized merely by
changing the completed contract.

## Tests

Normal tests use tiny temporary georeferenced rasters and injected GeoAI
callables. They exercise encoding, alignment, tile-export arguments, training
arguments, explicit class-1 probability extraction, metrics, manifests, CLI,
lineage-substitution rejection, real `255` label nodata handling, and the root
report-only aggregation bridge without importing GeoAI or using a network:

```powershell
uv run --project services/geoai-runner pytest services/geoai-runner/tests -m "not geoai_smoke"
```

The real opt-in smoke imports the pinned package and invokes its actual tile
exporter on the same tiny synthetic raster. It is never part of normal tests:

```powershell
$env:RUN_GEOAI_SMOKE = "1"
uv run --project services/geoai-runner --extra geoai pytest services/geoai-runner/tests/test_geoai_smoke.py -m geoai_smoke
```

The smoke proves environment and wiring only. Synthetic metrics do not establish
real flood accuracy or decision-layer eligibility.

For a proposal evidence build, the same opt-in smoke can emit only a small,
path-redacted JSON receipt and probability thumbnail. The receipt records that
the model was constructed with deterministic seed 42 but was not trained, and
binds the actual GeoAI tile-export and tiled-inference calls to report-only
FloodGuard aggregation:

```powershell
$env:RUN_GEOAI_SMOKE = "1"
$env:FLOODGUARD_PROOF_COMMIT = git rev-parse HEAD
$env:GEOAI_PROOF_OUTPUT_DIR = Join-Path (Get-Location) "services/geoai-runner/evidence"
uv run --project services/geoai-runner --extra geoai pytest services/geoai-runner/tests/test_geoai_smoke.py -m geoai_smoke
```

The generated receipt says `training_execution=model_construction_only`,
`aggregation.status=report_only`, and `can_feed_decision_layer=false`. It does
not retain the temporary raster, tiles, or checkpoint and contains no private
workspace path. Re-run it against the final pinned commit before packaging the
proposal evidence manifest.

## Executable real-data pipeline (`realpipeline/`)

The `geoai_runner.realpipeline` package is the end-to-end GeoAI implementation
for the competition: it fetches **real** data and runs every model component,
producing the interactive `outputs/geoai/geoai.html` showcase, per-sub-district
priority inputs, and annotated evidence figures. It still honours the service
boundary — all `geoai-py`, PyTorch, rasterio, and network access live here, never
in the root decision engine, which the pipeline only *imports* (for FPPS scoring).

Real inputs, all fetched live at run time:

| Component | Book ch. | Real source |
|-----------|----------|-------------|
| A SAR flood extent | Ch. 12 | Sentinel-1 RTC pre/post (Microsoft Planetary Computer) |
| B U-Net water mask | Ch. 9 | Sentinel-2 L2A + MNDWI labels, ImageNet-pretrained ResNet |
| C Susceptibility | Ch. 13 | Copernicus DEM GLO-30 + DWR rivers, vs JRC Global Surface Water |
| D Infrastructure | Ch. 14 | OpenStreetMap building footprints |
| F Few-shot | Ch. 16 | Sentinel-2 features + real labels |
| Decision bridge | — | DOPA sub-district boundaries (NGIS) |

```powershell
uv sync --project services/geoai-runner --extra realpipeline
uv run --project services/geoai-runner python -m geoai_runner.realpipeline        # all-real
uv run --project services/geoai-runner python -m geoai_runner.realpipeline --fast # fewer U-Net epochs
```

Unlike the fail-closed proposal smoke above, this path is the "actually executed
on real imagery" evidence: it reports real metrics (SAR flood extent, U-Net IoU,
susceptibility AUC vs JRC) with honest limitations (e.g. the nearest post-event
same-orbit Sentinel-1 scene is ~4 days after the flood peak, so extent is
residual). It is still non-operational and not an official warning. Network-free
component tests live in `tests/test_realpipeline.py`. Methodology:
`docs/geoai_methodology.md`.
