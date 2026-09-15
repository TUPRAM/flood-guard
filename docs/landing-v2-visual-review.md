# FloodGuard continuous neighborhood — visual review

Repository evidence includes the final production browser captures and report, the cleanup captures, and the contact sheets linked below. Earlier v1 screenshots, intermediate refinement rounds, raw renders, and duplicate recordings are preserved in the original local worktree and are not all included in a fresh clone. Historical execution records retain their original local evidence paths. The generated Blender master is also local; its committed source scripts and checksum are documented in the asset README.

## Delivered composition

The opening starts with a wide drone view of one modeled neighborhood. Scrolling approaches the homes and clinic, then reduces the artwork window to create space on the left. Paper enters that space first, followed by the resident and narration. The same paper remains through all nine story states. The same resident remains through the early explanations; the planner replaces her for analysis and the brief.

The modeled neighborhood contains 26 homes and one clinic, with tiled roofs, ridge/hip details, balconies, shutters, glazing, foundations, access ramps, gates and garden boundaries. Curved-leaf broadleaf trees, banana planting, shrubs, grasses and riverbank plants provide layered vegetation. Water is independent geometry. Buildings and the route remain in the same place through dry, rising and affected-connection states.

The original clean neighborhood plates and transparent resident/planner illustrations were opened during the work. Their warm paper, teal accents, editorial restraint and illustrated people guided the new composition. The portraits remain separate transparent artwork. The new neighborhood is a consistent Blender source rather than a reconstruction of every independently illustrated building in the older plates.

## Browser inspection

Actual local production captures were reviewed at 1672×941, 636×728, 390×844 and 320×800. Additional checks cover an 844×390 landscape viewport, no JavaScript, reduced motion and doubled root text.

Reviewed moments include the hero, quarter/mid/three-quarter camera approach, half-shrunken artwork, empty paper, first portrait, all settled story states, the observation dialog and expanded brief. Key refinements from those captures:

- Increased portrait scale and corrected compact artwork framing.
- Removed overlap between the phone observation marker and the affected-route label.
- Matched the affected SVG segment to the modeled road portion covered by the W2 water plane.
- Moved the selected-area button outside the cropped world and moved the compact online-status control away from the story controls.
- Corrected history/reload restoration and focus-induced horizontal movement.
- Made long explanations keyboard-scrollable within the persistent panel.
- Registered adjacent camera images against actual projected ground references before blending. This substantially reduces doubled roof/road edges. Feathered raster edges remove seams exposed by the registration transforms.
- Prepared both portraits after the first paint and strengthened capture readiness to await decoded pixels and require visible portrait geometry at each assigned reading hold.

The automated browser harness checks DOM continuity, geometry, opacity, decoded artwork, native interactions, accessibility fallbacks and console/CSP errors. Visual quality is assessed separately from those assertions.

## Art and motion limits

- This delivery uses rendered 3D images from the editable master. It has a restrained 16-view camera approach, three registered water states and responsive HTML. It does not expose free camera orbit or a live fluid simulation.
- Camera interpolation uses an affine ground-plane approximation. Independent projected probes measure a worst adjacent midpoint residual of 2.72 native pixels on the ground and 3.39 at the clinic roof. Minor perspective/height parallax remains during movement; settled story views are single, untransformed images.
- Phone layouts put the persistent panel below the artwork. Compact desktop layouts keep the requested left/right arrangement. Long analysis/brief content scrolls inside the panel so the paper and portrait can remain stable.
- Short landscapes, enlarged text, reduced motion and no-JavaScript mode use a readable sequence of sections with the same neighborhood artwork.
- The final appearance is a detailed architectural render in the existing editorial palette. It is intentionally not pixel-identical to the earlier independent illustrations.
- Browser testing here uses local Chromium. Safari/Firefox and physical phone testing were not performed. Recorded FCP/CLS/transfer values describe this local test environment, not field performance or a calibrated device benchmark.

## Review outputs

- [Machine-readable browser report](visual-qa/landing-v2/browser-acceptance-production/continuous-browser-results.json)
- [Opening](visual-qa/landing-v2/browser-acceptance-production/1672x941-hero.png)
- [Empty paper before the person and text](visual-qa/landing-v2/browser-acceptance-production/1672x941-empty-paper.png)
- [Affected connection and resident](visual-qa/landing-v2/browser-acceptance-production/1672x941-settled-S3B-OBS.png)
- [Planner analysis](visual-qa/landing-v2/browser-acceptance-production/1672x941-settled-S3B-01.png)
- [Compact expanded brief](visual-qa/landing-v2/browser-acceptance-production/636x728-opened-review-brief.png)
- [Phone expanded brief](visual-qa/landing-v2/browser-acceptance-production/390x844-opened-review-brief.png)
- [Three water states](../outputs/landing-v2-assets/neighborhood-states.png)
- [Opening sequence contact sheet](../outputs/landing-v2-assets/opening-sequence-contact-sheet.png)
- [All nine desktop scenes](../outputs/landing-v2-assets/desktop-story-contact-sheet.png)
- [All nine phone scenes](../outputs/landing-v2-assets/phone-story-contact-sheet.png)
- [24-second scroll preview](../outputs/landing-v2-assets/scroll-preview.webm)
- [Frames extracted from the scroll recording](../outputs/landing-v2-assets/scroll-video-contact-sheet.png)
- [Editable master and reproduction instructions](../assets/floodguard-neighborhood/README.md)
- [Execution and verification record](landing-v2-execution.md)

The browser report identifies the exact recorded video and all additional captures. Earlier interrupted and pre-refinement reports remain explicitly named as iteration evidence in the same review directory.
