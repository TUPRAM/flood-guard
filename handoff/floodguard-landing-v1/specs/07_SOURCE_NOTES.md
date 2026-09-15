# Source notes and decision provenance

## Uploaded-source facts

The original `STORYBOARD.md`, verification record, 24 PNGs, and two supplied scene specifications are preserved under `references/storyboard-original/`. They supply the scene IDs, story framing, exact narrative language, visual targets, asset limitations, and the distinction between illustrative geography and historical evidence. Source image hashes were rechecked. The material says there is no editable 3D model, motion implementation, accessible text layer, or exact pixel registration.

The original generation-prompts file is retained only as provenance. Do not treat it as a current instruction to run paid image generation or overwrite assets. Original absolute Windows paths identify where the source package was made; use the local relative paths in this handoff instead.

## New decisions in this handoff

Pre-rendered DOM/SVG composition, WebP variants, native-pixel overlay helper, two-stage fade-to-paper transitions, repository integration gates, QA hooks, and the no-destructive installer are engineering decisions proposed for this implementation. They are not claims that the original artwork contained geometry, rigs, or a tested site.

The provided anchor/path JSON is a manually proposed starting trace. It is not measured GIS data and still requires visual calibration. The null shoreline path intentionally avoids inventing a precise polygon. The responsive crop is also a starting composition, not a source-authored camera calibration.

## Technical references checked 15 September 2026

Use official docs for the actual installed versions. These sources support tooling behavior, not a guarantee of visual quality.

- OpenAI, custom instructions with AGENTS.md: https://developers.openai.com/codex/guides/agents-md (redirects to official ChatGPT Learn documentation).
- OpenAI Cookbook, Using PLANS.md for multi-hour problem solving: https://developers.openai.com/cookbook/articles/codex_exec_plans . Persistent plans make multi-step work reviewable/resumable; they do not guarantee completion in a single uninterrupted run.
- Next.js, Static Exports: https://nextjs.org/docs/app/guides/static-exports . Static hosting and image-optimization constraints guide local preoptimized asset use.
- GSAP, matchMedia: https://gsap.com/docs/v3/GSAP/gsap.matchMedia()/ . Responsive/reduced-motion setup and reversion guide lifecycle cleanup when GSAP is used.
- Playwright, Visual comparisons: https://playwright.dev/docs/test-snapshots . Screenshot expectations support regression testing; reference fidelity still needs visual inspection and appropriate baselines.

## Repository inspection

GitHub connector reads of TUPRAM/flood-guard default-branch page/package/config/offline-builder informed `06_REPOSITORY_NOTES.md`. The local checkout may contain newer work. This handoff does not claim a full app audit or a successful project build.
