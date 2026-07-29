# Research manifest

The only tracked file in `research/`. Everything else here is gitignored.

## What this directory is

The **ungoverned** landing zone for exploration: `geoai-skills` output,
downloaded open benchmarks, scratch rasters, one-off comparisons.

A result in here is a **hypothesis**. It has no checksum, no `ModelRun`, no
registry entry, and no `official_warning=false` marker, so it cannot back a
published claim. Discarding a research result is the normal outcome and is a
success, not a failure — a negative result recorded here is far cheaper than a
wrong claim published.

## The rule

> **Skills explore. `realpipeline` claims.**

| | `research/` | `evidence/` |
| --- | --- | --- |
| Produced by | any tool, any environment | `realpipeline` under the frozen runtime |
| Provenance | none | `ModelRun v2` + `ModelEvaluation v2` + checksum |
| Spatial holdout | not required | required (`blocks.py`) |
| Receipt | none | signed, via `trusted_zonal_adapter` |
| Read by `services/api` | **never** (asserted in CI) | yes |
| Read by `apps/web` | **never** (asserted in CI) | yes |
| Git | ignored | tracked |

Promotion is a **re-run**, never a file copy. Copying an artifact from here into
`evidence/` is the single failure mode this directory exists to prevent, and
`services/api/tests/test_research_boundary.py` fails the build if the API can
resolve a `research/` path.

## Layout

```
research/
├── MANIFEST.md          this file — tracked
├── skills/              geoai-skills output — ignored
├── benchmarks/          downloaded open datasets — ignored
└── .geoai-skills/       skill session state — ignored
```

## Environment

Most exploration needs the GeoAI stack, which is **not installed by default**:

```
uv sync --project services/geoai-runner --extra geoai
```

Component ★ (OmniWaterMask) needs a *separate* environment, because
`omniwatermask` requires `numpy>=2.0,<2.4` and the runner is frozen at
`numpy==2.4.2`:

```
uv venv .venv-research --python 3.12
uv pip install --python .venv-research -r services/geoai-runner/requirements-research.txt
```

Output from that environment carries no frozen-environment receipt and is
research tier by construction.

## Log

Add one block per experiment. Record the negative results too — they are the
ones that stop the same dead end being explored twice.

```markdown
## YYYY-MM-DD · Component X · one-line question
Skill/cmd:  /geoai-skills:... or the script invoked
Environment: runner geoai extra | .venv-research | none
Output:      research/skills/...           (untracked)
Question:    what this was meant to settle
Result:      what actually happened, including numbers
Decision:    promote | discard | rerun — and why
```

---

## 2026-07-29 · Setup · sandbox created

Environment: none
Output:      —
Question:    Where should ungoverned exploratory output live so it cannot be
             mistaken for evidence?
Result:      `research/` created, gitignored except this manifest. Boundary
             asserted by `services/api/tests/test_research_boundary.py` and
             `tests/test_research_boundary_web.py`, which fail if the API or
             the web app can read from here.
Decision:    Adopted. See audit §8A.5 and ADR-I.

---

## 2026-07-29 · Setup · GeoAI toolchain installed and verified (D-33)

Skill/cmd:   `/geoai-skills:install-geoai --check --extras`
Environment: `services/geoai-runner/.venv-geoai` (new; `.venv` left light)
Output:      —
Question:    Can any GeoAI component actually run in this checkout?

Result:      Yes, for the first time. Previously `import geoai` failed in all
             three environments (audit §8A.3).

```
geoai 0.41.1 · numpy 2.4.2 · geopandas 1.1.4 · rasterio 1.4.4
rioxarray 0.22.0 · shapely 2.1.2 · leafmap 0.63.0 · pandas 3.0.3
torch 2.13.0+cpu · torchvision 0.28.0+cpu · transformers 5.14.0
timm 1.0.28 · segmentation_models_pytorch 0.5.0
CUDA: not available (CPU only)
```

Three findings worth carrying forward:

1. **`geoai_runner.environment.inspect_environment()` issued a receipt.** The
   project's own frozen-environment gate passes: Python 3.12.13, geoai-py
   0.41.1, declared commit matched. That gate had never been exercised here.
2. **CPU-only torch despite an RTX 3060 (6 GB) being present.** PyPI's Windows
   wheels ship without CUDA. Component B training and the `detect-objects`
   models will run, but slowly. Switching to a CUDA wheel means leaving the
   frozen pin, so it is a decision, not a fix.
3. **All 30 `geoai` APIs the skills call exist** on 0.41.1 — the skill contract
   holds against this pinned version.

             Isolation verified intact after install: the dependency-light
             `.venv` and the root `.venv` still cannot import `geoai` or
             `torch`, so CI job `geoai-normal` is unaffected.

Decision:    Adopted. `.venv-geoai` is the research-tier environment.
             Nothing produced here is evidence until re-run under the governed
             runner.
