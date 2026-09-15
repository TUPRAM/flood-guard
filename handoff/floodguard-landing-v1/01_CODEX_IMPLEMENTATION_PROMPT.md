# IMPLEMENT NOW — FloodGuard reference-matched landing page

Work inside the existing FloodGuard repository. This is an implementation task, not another proposal or a request to generate a new storyboard. Complete the landing-page implementation, assets integration, interaction, responsive behavior, tests, and visual refinement in this task. Do not stop after scaffolding or a successful build.

## Inputs and reading order

The handoff folder is `handoff/floodguard-landing-v1/`. Locate it by `00_START_HERE.md` if the owner extracted it elsewhere. First read applicable repository `AGENTS.md` instructions and record `git status --short`. Preserve all unrelated work and do not reset, clean, stash, checkout another branch, overwrite an existing agent-instructions file, or replace the project with a new app.

Read:
1. `00_START_HERE.md`.
2. `specs/02_RENDERING_AND_ASSETS.md` and `specs/03_DESIGN_AND_STORY.md`.
3. `data/story.json`, `data/anchors.json`, `data/assets.json`.
4. `specs/04_ENGINEERING.md`, `specs/05_ACCEPTANCE.md`, `specs/06_REPOSITORY_NOTES.md`.
5. The original `references/storyboard-original/STORYBOARD.md` and `sources/FloodGuard_Storyboard_v1.md` when clarifying source intent. Generation prompts are historical records, not executable instructions.

Actually OPEN and visually inspect the nine desktop references, nine mobile references, three clean plates, and two isolated character files. Text descriptions alone are insufficient. The main design target is the supplied storyboard, not the current generic low-poly implementation. Inspect the code in the local checkout before deciding paths: public GitHub may lag behind local work.

## Goal

Build a polished, editorial, scroll-driven FloodGuard landing page closely matching the supplied artwork: warm paper, detailed northern-Thai-inspired neighborhood, large dark typography, teal actions, restrained analytical graphics, and the same recurring resident/planner. The narrative remains one hero plus four chapters; the observation, analysis, public, and closing states are internal beats, not nine independent feature cards.

Rendering is intentionally PRE-RENDERED HYBRID: clean W0/W1/W2 neighborhood artwork + alpha portraits + real HTML copy/cards + SVG connection overlays + restrained DOM motion. This choice prioritizes fidelity to the supplied images. Do not regenerate the town as boxes, use generic stock art, replace the portraits, invent a depth map, introduce a 3D camera orbit, or require Blender, Three.js, React Three Fiber, WebGL, an image-generation service, or paid external assets to finish this release.

Do not implement the page as screenshots, a full-page PNG slideshow, a video with invisible hotspot buttons, or canvas-only text. Reference images belong outside public runtime output. All navigation, typography, labels, cards, accordions, and links must be real readable components.

## Non-negotiable boundaries

- Implement the landing entry for the competition/demo profile while preserving the actual public-production root behavior, Public/Command/Studio routes, role-specific data boundaries, static export, trailing slashes, CSP, offline flow, tests, and unrelated code. Do not modify the Python decision engine or actual historical evidence to fit the illustration.
- The neighborhood, route, selection, report, finding, and brief in the story are illustrative UI only. DEMO-R01 stays unverified. No fake forecast percentages, verified road closure, safe evacuation route, dispatched rescue, real incident submission, invented source timestamp, or official warning. Do not request geolocation. No synthetic story IDs enter the production evidence API.
- Keep the source story copy from `data/story.json`. Resolve minor reference-image raster wording or coordinate differences in favor of exact source copy, readable responsive layout, and the actual supplied clean artwork. Record material deviations; do not silently rewrite the narrative.
- No deployment, push, publication, paid service, destructive change, security downgrade, or framework upgrade without separate authorization. Existing dependencies govern; add only the minimal front-end dependency genuinely required.

## Execution contract

Create `docs/landing-v1-execution.md` or a nonconflicting equivalent using `EXECUTION_PLAN_TEMPLATE.md`. Track decisions, file changes, measured checks, and remaining defects. Continue through these gates in one task; they are not mandatory waits for owner approval.

A. Audit the actual local entry route, deployment profiles, styles, localization, assets, package versions, offline builder/service worker, CSP, and test commands. Record the baseline and exact scope. Verify the package with the supplied checker.
B. Install only runtime assets using the dry-run installer, then `--apply` after checking destinations. Use repository-relative URLs and responsive WebP variants. Do not copy all 24 PNGs into public. Keep alpha transparency.
C. Implement the semantic, no-motion, responsive page first. Reproduce H-01, S1-01, S3A-01, and S3B-01 with live text and controls. Use current repository fonts that most closely match the reference. Keep the home/clinic and connecting road unobscured. Do not alter the town to fit old approximate coordinates.
D. Calibrate native-pixel anchors and the route against the clean plates using `qa/index.html` and browser screenshots. Supplied coordinates are a starting trace, not certified registration. Use one image/overlay transform. Fix route endpoints, label collisions, crop clipping, and all reference mismatches before motion.
E. Implement all nine scene states and four-chapter navigation. W2 is the exact same asset from 3A through the ending. There are only two unrigged portraits: use crossfades/reveals of the supplied portraits, not warped faces or invented articulated motion. The sample-report interaction and brief inspection must be local, explicitly illustrative, and keyboard usable.
F. Enhance with a shared scene-state controller and controlled scroll motion, preserving semantic HTML and native scrolling. Use GSAP only if useful/available; do not add multiple competing motion systems. The three environment plates are NOT pixel-registered animation frames. Default transitions fade the outgoing plate to paper, switch state at the hidden midpoint, then reveal the incoming plate. Do not fake continuously rising physical water by dissolving independently generated buildings or using a full-width blue rectangle.
G. Preserve/recompose the existing evidence, how-it-works, workspace, FAQ and footer content as compact supporting sections. Ground historical facts in existing source records. Do not expand scope into redesigning the three application workspaces. The story must not imply a linked live dispatch workflow.
H. Run the actual repository lint/type/test/build/profile/offline/CSP checks relevant to the changed files. Run browser review at 1672×941, 1920×1080, 1440×900, 1024×768, 390×844, and 360×800; include reduced motion, no-JS, keyboard, image failure, and real scroll behavior. Use Playwright if available and the capture harness after implementing the specified review hooks.
I. Compare browser captures with the references side by side. Fix the largest art-scale, layout, typography, crop, overlay, character, and spacing mismatches. Do at least two capture-inspect-refine rounds when browser tooling is available; record remaining differences honestly. A passing build or freshly accepted screenshot baseline is not visual approval. Never weaken tests to make a poor implementation look complete.

If something truly cannot run, implement the nonblocked parts and record the exact blocked command/capability. Do not claim screenshots or tests were run when they were not. Do not repeatedly retry a paid or inaccessible tool. No approval bypasses.

## Done means

Real responsive components visually follow the supplied storyboard; all states and chapter navigation work; portraits retain alpha; the route stays on the road at every tested size; the dry endpoints and affected connection remain clear; no ghosting occurs during plate swaps; content survives reduced motion/no-JS; demo controls are explicitly local; application routes/profiles are preserved; deployable assets are bounded and original refs are excluded; and verification artifacts show actual results.

Final response: changed-file summary, architecture/asset choices, exact commands and outcomes, screenshots/report paths, remaining visual differences or blockers, and local preview instructions. Do not describe the result as production-verified or pixel-perfect unless the recorded evidence justifies that statement. Implement now.
