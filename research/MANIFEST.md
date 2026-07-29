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

**No experiments have been run yet.** The GeoAI stack is not installed in any
environment in this checkout (audit §8A.3, D-33), so the first entry after this
one should be the output of `/geoai-skills:install-geoai --check --extras`.
