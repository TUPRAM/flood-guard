# Rendering and asset contract

## Decision: match the rendered references, not a fashionable stack

Use the supplied high-detail rendered artwork directly. A 2.5D appearance is an art direction; it does not require low-poly geometry or a real-time 3D engine. Here the target camera is substantially fixed, so the existing high-quality rendering is the most direct visual source.

The browser composition has four independent layers: background paper; the clean scene plate; registered path/selection/report overlays; and HTML text/cards/portraits. The result should feel like the supplied editorial illustration, not a dashboard pasted over a toy map.

True 3D can support camera motion and physically consistent water, but the supplied package contains no editable geometry, camera, material, depth, or segmentation passes. Constructing those from scratch would be a different asset-production project with a new visual acceptance process. Do not substitute it for this release.

## What is supplied, and what it proves

There are 24 original PNGs: nine desktop references (1672×941), nine mobile references (853×1844), three clean plates (1536×1024), a paired character sheet (1536×1024), and two actual RGBA vignettes (1374×1145). The full-frame text is baked into the references. The artwork documentation explicitly says continuity is reference-derived rather than exact pixel registration. These are concept images, not measured Mae Sai geography.

All original image hashes were independently checked against the supplied CSV. WebP derivatives are file-format/downsampling derivatives, not a creative revision. No new geography, faces, or flood frames were generated for this handoff. Review lossy derivatives on paper at realistic CSS sizes; revert a particular variant to the original or increase its quality only when an actual artifact is visible.

## Runtime inventory

| Art | Variants | Source |
|---|---|---|
| W0 | 768, 1152, 1536 px wide | `plates/FG_Master_W0.png` |
| W1 | 768, 1152, 1536 px wide | `plates/FG_Master_W1.png` |
| W2 | 768, 1152, 1536 px wide | `plates/FG_Master_W2.png` |
| Resident | 480, 800, 1374 px wide, alpha | `characters/FG_Resident_R01_Transparent.png` |
| Planner | 480, 800, 1374 px wide, alpha | `characters/FG_Planner_P01_Transparent.png` |

See `data/assets.json` for exact dimensions, byte sizes, public URLs, SHA-256, and source paths. The sum of all 15 raster derivatives is 3,485,414 bytes; this is the complete variant set, not the expected transfer for one visitor. Do not download all variants. Browser selection and staging should fetch only the chosen width for a used asset.

The original 24 PNGs remain in `references/storyboard-original/`. Do not serve the complete reference compositions as website content. Do not ship the 52 MiB reference folder, generation prompts, manifest copies, or QA contact sheets into `public/`, the service worker, or the production build.

## Resolution ceiling

The clean art has 1536 native horizontal pixels, not 4K. A 1100 CSS-pixel scene at DPR 1 may look strong; at DPR 2 it would ideally need 2200 source pixels for a native-resolution match. Enlarging this file does not add detail. Use sensible composition/crop/zoom, maintain the editorial scale, and report the remaining high-DPR softness. Do not replace detail with a poor procedural model in the name of resolution.

Use the matching source set; do not generate 3840-wide derivatives by interpolation and call them original 4K. A later independently approved master-render project can provide 3072–4096-wide plates with identical geometry. The first website implementation must not depend on that optional upgrade.

## Layout versus source conflicts

The written storyboard specified approximate viewport percentages and 35–45 buildings. The actual provided clean art is the spatial authority for integration: do not add or move houses to enforce the old approximate layout. Exact narrative copy remains governed by the written spec/data, while the actual plate controls road/landmark positions. Record the difference as source reconciliation, not silent correction.

The mobile references are separately generated concept compositions, not pixel-exact crops of the desktop plate. Preserve the same canonical world in the website, using responsive framing and larger labels; do not switch to an independently generated mobile town just to chase a pixel-difference score. Accept controlled responsive reflow when it preserves the visual intent and improves legibility.

The portraits are unrigged stills. They include a tabletop and plants. Do not remove the tabletop and leave a floating torso, stretch the face, mirror text on a phone, or animate a hand by deforming a flat raster. Crop consistently and animate entry/opacity only.

## Coordinate contract

Author in the native 1536×1024 plate space. `data/anchors.json` contains a proposed route, anchors, selected-area shape, and crops. Its `needsVisualAcceptance` flag must remain true until the implementation has been inspected. The report marker is deliberately offset from the line.

The main route begins at the household gate and ends at the clinic entrance. Background streets are not a verified network. The selected-area perimeter is a narrative selection—not a measured flood boundary, modeled catchment, or risk class. The supplied optional shoreline path is null: leave it absent unless a precise, reviewed trace is made from the illustrated water edge. A nonexistent mask is not permission to draw an arbitrary blue rectangle.

The same crop and camera transform must apply to the image and SVG path. DOM labels are projected from that same coordinate space, but remain readable in CSS pixels. Their backing boxes and leader lines must not cover the main buildings or road. Do not position labels relative to the outer viewport when the image is letterboxed inside it.

## Water-state transitions

W0→W1 and W1→W2 are changes between three distinct artwork states. They do not form a measured flood-time sequence or a hydraulic simulation. The artwork changes foliage, texture and small shapes. A long opacity blend exposes double roofs and walking trees.

Default transition: at the chapter boundary, fade the outgoing environment layer toward the paper background (about 140–180 ms), switch the rendered state while fully obscured, then fade the new environment in (about 160–220 ms). Suppress the path/labels across the swap and reveal the matching overlay with the destination plate. The transition must be reversible and cancelable: a quick scroll to another chapter cancels the old transition and settles on the latest state. The map cannot disappear for seconds while text has already advanced.

The rendered state, overlay state, and image availability form one atomic scene update. Never show W2 labels on a W1 road. Do not wait on offscreen decorative assets before rendering the core content. If the next plate cannot load, retain a readable fallback caption and explicitly identify the failed illustration state; do not represent the previous plate as the new condition.

From 3A to the final frame, retain precisely the same W2 URL/crop. Do not crossfade between six different full-frame W2 screenshots. Changes are portraits, HTML panels, SVG styles, and selection markers only. No water drains away and no triumphant sunshine implies resolution.

## Cosmetic motion allowed

A very small whole-scene translation or scale adjustment at the hero transition is acceptable if all overlays share the transform. Use parent transforms rather than independent parallax of roofs, trees, and roads. Keep the scene fixed from S1 through analysis. A subtle opacity/translate entrance for a vignette and path-drawing in S1 is sufficient. Do not apply wobble, pulsing floodwater, continuous route dots, storms, animated paper grain, flashing lightning, or moving vehicles on the affected segment.

## Optional future: genuine cinematic asset pipeline

Only pursue in a separate approved task: reconstruct one scene in Blender from a real modeled road topology and approved references; lock camera, materials, scale, light and object IDs; render W0/W1/W2 from that same scene; export beauty, foreground/occlusion, depth and water masks; validate that nonwater geometry is pixel-registered; generate an appropriately budgeted transition sequence or a single water-masked effect; approve native-resolution masters and mobile crops. A glTF runtime alternative needs baked materials/lighting, LODs, compression, measured mobile performance and a raster fallback.

That future workflow enables actual camera changes and physically consistent progression. It is not required to closely reproduce the existing fixed-view references. The current handoff contains no Blender scene, depth pass, segmentation mask, rig, or image sequence; never claim otherwise.
