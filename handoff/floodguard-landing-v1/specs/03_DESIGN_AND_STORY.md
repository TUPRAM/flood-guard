# Design, narrative, and interface behavior

## Authoritative design target

Use all nine supplied desktop compositions and mobile counterparts as the appearance reference. The aim is a detailed, softly rendered environment and restrained editorial UI—not a generic agency template. Desktop source frames are 1672×941. Also support 1920×1080 without pretending the images have become higher resolution.

Content/state authority is `data/story.json`. It preserves the supplied exact wording and scene order. IDs are H-01, S1-01, S2-01, S3A-01, S3B-OBS, S3B-01, S4-01, S4-PUBLIC and S4-END. Four main chapters remain 01 Everyday connections, 02 Conditions change, 03 Connections affected, 04 Next steps. The observation is a beat in 03; Public and Closing are beats in 04.

## Layout tokens

Warm paper #F3F1E8, primary text #24332F, brand teal #006F78, analytical blue #3C6F8A, review amber #9A5D0C. Reference artwork has its own cream paper pixels. Do not globally tint the artwork to force a token match. Blend the outer edge subtly or use the closest neutral surface and document a minor tonal difference. Do not make the whole town transparent to remove its paper background.

Use a modern geometric sans with heavy but not inflated headings. Existing local Manrope/Plus Jakarta/Inter assets are candidates, not proof of the reference font's identity. Test the existing fonts; choose the closest letter shape and line break. Do not download or bundle font files supplied by this handoff; none are included. Preserve existing Thai fonts and localization behavior. Never fake an EN/TH switch that only changes its label.

Desktop container max approximately 1840 px with 32–64 px side margins. Navigation approximately 1020–1100 px wide, centered, 64–72 px high, 20–36 px below the viewport top. Reserve its actual occupied height. Rounded corners are restrained (4–10 px), thin neutral borders, subtle shadows, not giant SaaS pill shapes. Nav can be sticky but must not cover headings, focus, or chapter targets.

At 1672×941, the story rail is roughly 30–32% of the composition and artwork 68–70%. At 1920×1080 the rail can be 520–560 px. Do not squash the plate into the exact card aspect ratio of a full-frame concept. Preserve the native perspective; use a registered crop where needed. Primary story heading 46–58 px at typical desktop widths, hero 70–92 px; body 18–22 px. On mobile: title 34–42 px, body 16–18 px, button targets at least 44 CSS px. Do not shrink text to replicate illegible raster microcopy.

The table-and-portrait fills the lower part of the text rail. For brief/analysis scenes, place the HTML finding card over the clean upper-right paper area of the illustration, not over the clinic. Card width usually 300–390 px, depending on art viewport. At tablet widths/short viewports, put the card below the map rather than allow it to cover critical geometry. On mobile use title→map→finding/card→portrait; the portrait is subordinate to the explanation.

## Hero

An open header area with two-line headline and concise support. The clean W0 neighborhood forms the lower illustration; no resident portrait. Keep a subtle status directly under the actions: Historical planning demonstration · Illustrative neighborhood. Primary CTA goes to the existing planning demo. Secondary CTA goes to the first story chapter. No delayed splash, loader, scroll instruction blocking the CTA, or full-screen animation before the product statement.

The hero can use a wider registered crop. A DOM translation into the main story is optional. Do not invent a flying camera. The same home, clinic and watercourse must still be identifiable.

## S1: everyday connections

W0; resident; preparedness card. Draw the usual connection along the road; a single brief movement dot is optional and must disappear before W1. Labels Homes, Usual connection, Clinic. Preserve gate-to-entrance endpoints. The clinic is not an evacuation shelter. The household portrait is fictional and not a representation of a real disaster survivor.

The preparedness card is real text. A secondary action can open the existing Public route; do not simulate a submitted plan unless a real plan feature already exists and the owner asked to integrate it.

## S2: conditions changing

Use W1, not a procedural flood surface over W0. Keep the same framing and resident. Update the card only. This is illustrative preparedness information; no forecast percent, live siren, current timestamp, fake agency attribution or notification permission request. No new motion is required from the static portrait. W1 must visually show the road still dry in this illustration.

## S3A: connection affected

Switch to W2 and stop physical progression. The home and clinic remain outside the illustrated water. The affected part of the normal connection becomes amber/dashed, with a neutral illustrated-state label. The line over water is obviously an analytical overlay, not a real painted road surface. The amber segment follows the water span shown in the supplied art; do not shorten it solely to match an old approximate L01 point.

Allow the consequence to be read before the analysis card appears. No alternate green route, emergency dispatch, or automated severity score. The resident's question is real HTML, not a baked speech bubble.

## S3B-OBS: local observation

Keep W2 and resident. A hollow marker appears near the connection with DEMO-R01 and Not verified. This can reveal with scroll, but should also be selectable with an explicit local 'Inspect sample observation' button/details control. Keyboard users can inspect the same example. No network submission, geolocation, photo upload, notification, or success receipt. Avoid the word 'Submit' for a decorative demo. The copy must say that the example is illustrative.

## S3B: explained finding

Keep the exact W2 plate. Change resident to planner. Add the narrative selection outline and finding card from `data/story.json`. Show its basis, local input, and review needs; do not display a invented model score. Clicking/tapping the selected connection can focus or expand the explanation but never hide the canonical readable summary. A semantic list/detail is available without a pointer.

The selected-area outline is not a computed catchment or measured extent. A separate precise shoreline outline is optional; the clean plate already communicates the water. Do not add a misleading polygon just because a concept screenshot includes one.

## S4: planning next step

Same W2 and planner. Replace the finding with the review brief; 'Inspect the review brief' expands real local details or an accessible dialog of the same illustrative brief. It must not be a dead button, a misleading download, or a jump into a nonexistent real evidence record. Escape, focus return, keyboard activation, and text selection must work.

## S4-PUBLIC: household view

Use the resident and a simpler public-preparedness card. Explain parallel responsibilities, not a planner instantly issuing a live message. Public actions link only to existing appropriate Public surfaces. Official contact details come from the app's existing verified source; do not hardcode guessed phone numbers. Staff road geometry is not sent to the Public application as a new dataset.

## S4-END: closing

Water remains. Remove the large portrait and show a concise next step with real links to Public, Planning and Studio. Reuse W2 and the open questions. No all-clear color, rescue arrival, sunburst, confetti, or resolved badge. Do not create a second long hero competing with the first.

## Supporting page sections

Preserve useful content already present after the story, redesigning only its presentation. If absent locally, implement compact sections as follows, without making up historical metrics:

1. How it works: 'From observations to planning questions.' Three columns: Check the evidence; Examine possible consequences; Review planning options. Measured information, modeled results, and human decisions remain distinct.
2. Historical evidence: 'A specific case to inspect.' Link to the existing Mae Sai evidence view. Draw dates/status/coverage from the current approved repository record, not a string copied from this package. If no qualified case information is available, state the limitation and link to Studio; no fabricated metrics or decorative satellite image represented as analysis.
3. Workspaces: Public preparedness, Planning command center, Research and validation studio. Existing role routes and capability descriptions govern. Three concise useful cards, not another long repeated workflow.
4. FAQ: current conditions? No; illustrated/historical demonstration. Flood forecast? No. Rescue submission? The story does not submit or dispatch anything. Keep answers consistent with the current app.
5. Footer: small brand, role links, historical/non-operational scope, Teambits attribution as present in the project.

Do not require generating more pictures for these sections. Prefer actual existing product previews or clean typography. The nine story concepts are already enough imagery.

## Interactions and states

Four named chapter anchors; current chapter is set from the same scene controller as the picture. Previous/next within a chapter must reach the microstates without numbering them as extra main chapters. Provide Skip to workspaces and Reduce motion separately. No scroll hijacking, mandatory autoplay, looping progress, or anonymous 01–08 navigation. Native links remain usable when scripts fail.

Links are visible destinations, not green confidence signals. A mock sample report and brief are interactive local explanations, not a fake operational backend. No invented evidence record IDs or opaque developer jargon in main copy.

## Responsive and accessibility decisions

Below about 1024 px or when available viewport height is too small for the reference composition, use normal stacked flow. Do not keep a dense desktop pinned stage on a narrow phone. Body text stays readable, every image has reserved dimensions, and full content can extend below a screen. The 390×844 design target is not a requirement to squeeze every scene into 844 px.

Use the same canonical plate with `data/anchors.json` mobile crop as a starting point. Move labels/cards if needed while retaining all three main anchors. Mobile source screenshots are appearance guides, not alternative real-world maps.

One h1; coherent chapter heading hierarchy; readable text equivalents for the map; visible focus; no hover-only information. Decorative character images can have empty alt text because the action is explained next to them. The geographic illustration needs an appropriate caption/description including its illustrative state. Avoid live regions announcing scroll progress continuously.
