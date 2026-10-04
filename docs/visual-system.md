# Landing Visual System

Stage 3, September 12, 2026. The implemented key frames are rendered from one
authored model, not independently generated dry and flooded pictures.

## Identity And Typography

- Preserve the Public workspace shield logo and primary blue `#0f4c81`.
- Text `#0f172a`, supporting text `#475569`, paper `#eff4fb`, white working surfaces.
- Amber `#9a4309` text / `#c47722` analytical accent means an assumed interruption or uncertainty, never verified urgency.
- Instrument Sans is the free display alternative to F37 Analog, not an exact copy. Weight 500 for the hero, 550 for chapter headings; normal width and zero letter spacing.
- Existing Inter remains body/interface type; the existing Public brand typography is retained.
- Font source: https://github.com/Instrument/instrument-sans ; SIL Open Font License 1.1 retained with the self-hosted asset. No F37 font is copied.

## Composition

The main scene is an unframed geographic stage, with a consistent 24px
viewport inset. The hero reveals its lower part before the topographic copy
area recedes. A stable left reading area accompanies the analytical scene;
the focal homes, crossing, and service occupy the center/right. Labels are
projected from those objects, not guessed screen positions.

The user-supplied topography is a quiet contextual texture in margins and
the opening. Dense result text, product screenshots, and evidence rows use
plain high-contrast surfaces. Product sections are full-width bands with
constrained content, not nested cards. No decorative gradient orbs or
unrelated illustration.

At widths above 680px, the landing's connectivity/offline control sits in
document flow after the footer. It must not float over story controls or FAQ
text. Compact screens retain the existing opaque bottom status band. Public,
Planning, and Studio retain their own availability-control presentation.

## State Vocabulary

| State | Physical representation | Analytical representation |
| --- | --- | --- |
| Baseline | Dry streets, same fixed buildings and terrain | Continuous blue connection with labeled home and service endpoints |
| Flood evidence | Muted, irregular river-connected water across low ground | Explicit illustrative footprint; overlap alone is not a closure |
| Assumed disruption | Water remains unchanged | Amber dashed segment and a text label identifying the assumed interrupted link |
| Finding | Same flooded neighborhood, subdued surrounding context | Finding, reason, uncertainty, and reviewable next step; no fabricated real quantities |

## Assets And Evidence

- Authored source: `apps/web/src/components/landing/scene/drone-scene.ts`.
- Controlled graph: `apps/web/src/lib/landing/illustrative-scenario.ts`.
- Matched scene exports: `apps/web/public/landing/desktop-v4/`.
- Actual product captures: `apps/web/public/landing/product/`, with capture provenance and hashes.
- Optical evidence image: existing committed Sentinel-2 February 18, 2024 context; never styled or captioned as a September before/after match.

The scene manifest records source identities, inferred geography, authored
flooding, stable landmarks, and non-operational scope. The screenshot
manifest identifies real captured UI states separately from synthetic art.

## Interaction And Accessibility

Use native scrolling and the already requested fading native scrollbar.
Cross-workspace links use native document navigation, matching the existing
workspace links and preserving rapid Back navigation before hydration.
Keep chapter labels meaningful, links directly usable, controls at least
44px high, keyboard focus visible, and header/menu content out of the scene
labels. The latest review's motion-control request is implemented as a
compact icon-only Reduce motion / Enable motion control, not the former
large View without animation button. Animation is the default for eligible
desktops; operating-system reduced motion is honored automatically. All
semantic content and static figures remain available without WebGL or
JavaScript.

## Approval Boundary

Finished local key frames and browser inspection establish a reviewable
implementation. They do not establish external design sign-off, unfamiliar
user comprehension, scientific validation, or production authorization.
