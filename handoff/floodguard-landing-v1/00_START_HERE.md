# FloodGuard — Codex implementation handoff

Prepared 15 September 2026. This is an implementation brief, artwork package, and engineering toolkit. It is not a claim that the website has already been implemented or deployed.

## What to do

Extract this folder into the existing repository as `handoff/floodguard-landing-v1/`. Open the actual local FloodGuard repository in Codex, not an empty project. Paste `01_CODEX_IMPLEMENTATION_PROMPT.md` into one task. The full prompt tells Codex to inspect the repository, implement, test, compare, and refine in the same task. Do not paste all the documents separately.

Expected layout:

```text
<existing FloodGuard repository>/
  apps/web/
  ... existing project ...
  handoff/floodguard-landing-v1/
    00_START_HERE.md
    01_CODEX_IMPLEMENTATION_PROMPT.md
    specs/
    data/
    runtime/
    references/storyboard-original/
    implementation-kit/
    tools/
    qa/
    reports/
```

The original `STORYBOARD.md` contains the creator's Windows paths. They are provenance, not paths to use in the application. All usable inputs are included here with relative paths. The exact spelling or location of your local repository is not assumed.

## The rendering decision

Implement a pre-rendered editorial composition: supplied clean neighborhood plates + supplied transparent portraits + accessible HTML typography/cards + registered SVG analytical overlays + restrained DOM animation. No new low-poly town. No Blender requirement, image-generation API, runtime model inference, or WebGL requirement for this implementation. The style may look three-dimensional without being rendered as 3D in the browser.

The 18 full-page desktop/mobile PNGs are visual references, not website sections. Rebuild their text, navigation, controls, labels, and panels as real components. Use the three clean plates and two isolated portraits as runtime art.

## Contents

- `specs/02_RENDERING_AND_ASSETS.md`: asset strategy, source limits, transition contract, and future true-3D path.
- `specs/03_DESIGN_AND_STORY.md`: layout, story sequence, controls, and lower-page scope.
- `specs/04_ENGINEERING.md`: integration architecture, accessibility, static export, motion, and offline behavior.
- `specs/05_ACCEPTANCE.md`: scene-by-scene visual gates and regression tests.
- `specs/06_REPOSITORY_NOTES.md`: limited public-default-branch inspection; the local checkout still governs.
- `specs/07_SOURCE_NOTES.md`: uploaded-source facts versus new decisions and official technical references.
- `data/story.json`: exact scene copy and declarative state definitions; nine compositions inside one hero/four chapters.
- `data/anchors.json`: native-pixel coordinate starting points; visual calibration required.
- `data/assets.json`: ready-to-serve WebP variants, sizes, hashes, and source lineage.
- `runtime/`: only the production artwork derivatives; no fonts, full-page screenshots, or 3D models.
- `implementation-kit/`: pure tested coordinate/state helpers, a React plate-composition example, scoped CSS tokens, and test skeletons. These are integration aids, not a finished application.
- `tools/verify-package.mjs`: package integrity checks.
- `tools/install-assets.mjs`: dry-run-by-default runtime installer, with conflict protection.
- `tools/capture-review.mjs`: browser review capture harness; requires the implemented page and the project's Playwright installation.
- `qa/index.html`: local artwork/reference and anchor-calibration workbench. Open directly in a browser, or serve the handoff folder locally when browser policy disallows file URLs.
- `references/storyboard-original/`: all 24 original PNGs plus the original documentation and generation records.
- `reports/`: integrity and toolkit-test results from this handoff preparation.

## Optional local checks

From this handoff directory:

```sh
node tools/verify-package.mjs
node --test implementation-kit/story-math.test.mjs
node tools/install-assets.mjs --repo "<absolute path to existing repository>"
```

To serve the optional workbench locally from this directory, run `python -m http.server 8765 --bind 127.0.0.1` and open `http://127.0.0.1:8765/qa/`. Stop that local server when finished. This is an authoring tool, not the website.

The third command is a dry run. Codex should inspect its output before adding `--apply`. It copies runtime assets only. It does not edit page code, install packages, change the service worker, or modify a branch.

## What is and is not assured

All original images and their source hashes are retained. Runtime derivatives are generated without upscaling or creative retouching. All website code, motion, browser behavior, and production-profile integration still require Codex implementation and tests. A single initiating task does not guarantee uninterrupted completion, aesthetic approval, or zero debugging; the execution plan and verification gates make the task resumable and the outcome inspectable.

Do not commit or deploy this entire handoff folder automatically. Only selected runtime assets and the implemented code belong in the deployed site. Keep references and QA outputs outside the public asset directory. Do not push or deploy without the owner's separate instruction.
