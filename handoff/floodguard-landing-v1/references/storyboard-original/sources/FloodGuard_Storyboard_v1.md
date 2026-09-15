# FloodGuard — Storyboard Specification v1.0

## Production intent

**Story:** An ordinary connection changes when flooding reaches the neighborhood. FloodGuard helps people inspect what that change could mean and identify a planning next step.

**Structure:** One hero plus four stages. Stage 3 has two beats: the consequence (3A) and the analytical explanation (3B). Stage 4 has planner, public, and closing microstates, not three additional chapters.

**Format:** Desktop artboards at 1920 × 1080, with a coordinated mobile composition at 390 × 844. These are design targets, not statements about generated-image output dimensions.

**Visual combination:** A single 2.5D architectural neighborhood, flat analytical overlays, and two recurring half-body editorial characters. All images are concept artwork; no image generation is part of this specification.

**Evidence boundary:** The scene has fictional geography and an illustrative flood sequence inspired by Mae Sai. It is not a measured reconstruction, a flood forecast, a live situation display, or an operational route recommendation. The historical case and its evidence belong in a separate section. Every interface fragment described here is proposed concept UI until matched to an implemented capability.

**Main composition IDs:** H-01, S1-01, S2-01, S3A-01, S3B-01, S4-01.

**Supplemental continuity IDs:** S3B-OBS, S4-PUBLIC, S4-END. These are within-chapter microstates, not extra main chapters.

---

# 1. Locked neighborhood

## 1.1 Setting

Create a fictional northern-Thai-inspired neighborhood with approximately 35–45 low-rise buildings, not a metropolis or a miniature of all Thailand. Favor one- and two-storey buildings, occasional three-storey background buildings, modest shopfronts, irregular plots, shaded verandas, and a mix of tiled and restrained metal roofs. The layout should feel inhabited rather than generated from a uniform square grid.

Compose the foreground and middle ground around one household, one clinic, one usual connection, and one low road segment. Use approximately eight building archetypes with controlled variations. Detail is concentrated around the story anchors; peripheral buildings are quieter.

No national flags, recognizable real agency buildings, invented precise street names, dramatic skyline, cultural landmark added merely as decoration, or exact latitude/longitude labels.

## 1.2 Canonical projected composition

Coordinates below are percentages of the **illustration viewport**, not the full webpage. They specify the intended composition in S1 through S3B. They are not geographic coordinates or a surveyed plan. Once the approved base scene is built, these positions should be the result of one consistent camera and model, not independently positioned objects in each frame.

| ID | Anchor | Approximate x, y | Locked appearance and purpose |
|---|---|---:|---|
| H01 | Main household | 29%, 36% | Cream two-storey home, muted terracotta hipped roof, shaded front veranda, one asymmetrical tree on its left. |
| G-H | Household connection origin | 31%, 42% | The gate/driveway connection, not the roof center. |
| R01 | Surrounding household cluster | 20–37%, 27–47% | Three to five related homes; stays outside the final illustrated flood footprint. |
| J01 | Left road junction | 44%, 56% | Recognizable road bend/junction leading into the lower connection. |
| L01 | Low road segment | 58%, 60% | The central piece of the usual connection affected in the final illustrated scenario. It is at grade, not an elevated bridge. |
| J02 | Right road junction | 70%, 63% | The route continuation toward the clinic. |
| G-C | Clinic connection endpoint | 77%, 66% | Clinic entrance/forecourt connection; do not end the line at its roof. |
| C01 | Clinic | 82%, 65% | White two-storey building, muted teal roof, entrance canopy, teal medical identifier, one driveway. Remains outside the illustrated flood footprint. |
| W01 | Watercourse | Lower left, roughly x 0–34%, y 72–94% | A shallow, visible channel with vegetated banks, curving toward the lower edge. |
| F01 | Low-lying ground | Lower middle | Receives water beyond the channel and includes L01, while stopping short of the home cluster and clinic. |
| P01 | Small neighborhood shop | 42%, 35% | A desaturated blue roof and short awning provide a secondary orientation anchor. |

The main connection follows actual modeled road centerlines from G-H through J01, L01, and J02 to G-C. Approximate projected guide points: (31,42), (39,53), (44,56), (58,60), (70,63), (77,66). Do not draw a straight flight path across buildings.

Background roads may remain visible. The story does not assert that there is no alternative route or that every household is isolated. It concerns the **usual illustrated connection**, whose status needs review.

## 1.3 Terrain and flood states

| State | Physical content | Used in |
|---|---|---|
| W0 — dry context | Water remains within W01. Ground and roads outside the channel are dry. | H-01, S1-01 |
| W1 — changing conditions | Watercourse visibly fuller, narrow ponding develops beside the low-lying ground. L01 is not yet depicted as inundated. | S2-01 |
| W2 — illustrative inundation | A connected, irregular flood area spreads from W01 across F01 and reaches L01. Water remains below the raised ground supporting H01/R01 and C01. | S3A-01 through S4-END |

The W2 water footprint is identical in S3A, S3B, and S4. Those scenes change understanding, not the physical event.

Water must connect plausibly to the low ground and sit consistently relative to roads, curbs, plots, and building foundations. Do not leave submerged road markings shining through opaque water. An analytical connection line above water must look unmistakably like an overlay.

No numerical depths, timestamps, rain accumulation, forecast probabilities, or implied hydrodynamic simulation. Terrain is designed for explanatory clarity, not claimed as measured terrain.

---

# 2. Art direction and page composition

## 2.1 Overall aesthetic

**Tactile architectural model + cartographic editorial design.**

Use believable building proportions, softened small edges, roof thickness, recessed windows, shallow eaves, subtle surface texture, and restrained contact shadows. It should look carefully designed, not like a toy city with identical boxes or a glossy game environment.

The scene remains softly stylized. The water has mild surface variation and broad, low-contrast reflections; it is neither a plastic brown slab nor cinematic ocean water. Trees use shaped foliage masses with subtle shading rather than obvious low-polygon spheres.

Do not use exaggerated depth of field, tilt-shift blur over the relevant road, bloom, holographic beams, neon network effects, or heavy outlines around every building.

## 2.2 Proposed palette

| Role | Color |
|---|---|
| Paper canvas | #F3F1E8 |
| Primary text | #24332F |
| Brand teal / primary action | #006F78 |
| Neutral analytical blue | #3C6F8A |
| Vegetation / terrain | #95A88E |
| Roof blue-gray | #A7B8BD |
| Household roof / warm accent | #BF8064 |
| Sediment water | #A88B68 |
| Review / uncertainty accent | #9A5D0C |
| Thin separators | #C9D2CC |

Color is supplemented by labels, line patterns, and shapes. Teal identifies brand or selection; it does not mean safe. Amber identifies review/uncertainty, not an automatically verified hazard severity.

## 2.3 Camera and light

Use one orthographic or near-orthographic camera, initially composed approximately 40 degrees downward from the horizontal. Lock azimuth after the master scene is approved. Scene composition and legibility take precedence over matching an arbitrary angle precisely.

H-01 uses a wider fit of the same world. S1 through S3B use the same canonical view. S4 keeps that view until its final microstate, where a modest pullback is permitted. No yaw reversal, free orbit, or new neighborhood layout.

Daylight comes from the upper-left of the composition. W0 uses softly warm daylight. W1 introduces a broad cloud shadow and cooler fill, reducing direct-light intensity rather than changing the sun to the opposite side. W2 remains softly overcast and readable. The resolution does not return to sunny weather.

## 2.4 Desktop artboard: 1920 × 1080

Use a warm paper background, 48-pixel outer margin, and sparse unlabeled contour texture in open margins only. Text surfaces remain quiet.

**Shared navigation:** approximate x 352, y 28, width 1216, height 72. Content: FloodGuard wordmark; The story; Workspaces; Evidence; primary action Explore the planning demo. Use the existing brand mark rather than inventing an agency emblem. Navigation must not overlap the scene headline or selected map anchors.

**Hero:** centered headline group above a panoramic model viewport at approximately x 48, y 500, width 1824, height 516. The hero map fit is wider than the story view but contains the same landmarks.

**Story frames:** left editorial rail x 64, y 156, width 528. Right illustration viewport x 640, y 148, width 1232, height 860. Keep that split through S1, S2, S3A, S3B, and the main S4 planner frame.

Within the left rail: eyebrow, headline, short supporting copy, then one character/interface vignette. Proposed vignette bounds: x 64, y 616, width 528, height 320. Treat these as guides; long headings must be typeset without overlapping the vignette. For S3B and S4, reserve a dedicated analytical-card position in the upper-right map margin: approximately x 1440, y 184, width 400, height 392. It does not cover H01, L01, or C01. The character remains in the editorial rail; do not add a second duplicate card beside the character.

**Typography proposal at this artboard size:** hero heading 80–88 px; story heading 54–58 px (use 54 px for the longest headline); paragraph 22–24 px; card heading 20–22 px; card body 17–19 px; map labels 16–18 px; captions 14–16 px. Set final type in HTML/vector layers, not as baked texture.

**Persistent illustration label:** “Illustrative scenario · Not current conditions.” Place it at the lower-left inside the illustration viewport on a quiet backed strip. The separate historical case receives its own labels later.

**Chapter navigation:** 01 Everyday connections; 02 Conditions change; 03 Connections affected; 04 Next steps. 3A and 3B share chapter 03. The hero is not a numbered chapter.

## 2.5 Character vignette design

Use half-body **2D editorial illustration**, with anatomically credible proportions, soft two-tone shading, subtle linework, and the same warm/cool balance as the scene. Keep the characters flatter than the buildings and the UI crispest of all.

Torso crops end at a panel edge, table, or desk. Characters never stand at giant scale inside the map. A household pin can associate the resident with H01 without a literal wire from the face to the roof.

A vignette contains one person, one short question/action, and one interface fragment. A phone can be visible, but the readable UI is enlarged next to it; do not squeeze the product story onto a tiny device screen. No speech balloons with cartoon tails.

### Resident R-01

Fictional adult woman, approximately 30–40, medium-tan skin, dark brown chin-length hair tucked behind one ear. Muted terracotta/ochre overshirt over a cream top; dark slate phone case. No brand logos, uniforms, or stereotyped costume.

S1: seated or standing beside a home table, shoulders relaxed, checking a paper plan and phone.

S2: same position/clothes/phone; attention shifts to the phone, expression attentive.

S3A: thoughtful concern, looking toward the connection finding; no panic or crying.

S3B-OBS: same safe interior setting while a sample observation appears in the demonstration.

S4-PUBLIC: reviewing preparedness information, not celebrating or setting out on a supposedly guaranteed route.

### Planner P-01

Fictional adult man, approximately 40–50, medium-tan skin, short dark hair with subtle gray at the temples, muted dark-teal overshirt, no institutional insignia. Seated behind a light warm-gray desk with a dark slate tablet/laptop.

S3B: a small selection gesture, followed by attention to the explanation card.

S4: reviewing a compact connection brief; neutral, focused expression. Do not make the interface look like a live dispatch console.

---

# 3. Scene H-01 — Place and promise

## Communication objective

The viewer should recognize a planning product concerned with flood consequences, not only an attractive town model.

## Exact copy

**Eyebrow:** FLOOD EVIDENCE → LOCAL PLANNING

**Headline:**
See the flood.
Understand what it changes.

**Supporting copy:**
FloodGuard connects flood evidence with communities, roads, and essential services to support informed local planning.

**Primary action:** Explore the planning demo

**Secondary action:** See how it works

**Context line:** Historical planning demonstration · Illustrative neighborhood

The illustration itself carries the persistent fictional-scenario label. Do not insert a historical date into the invented animation.

## Main still composition

Warm editorial canvas and floating navigation. Headline is large and centered above the model. The panoramic model occupies the lower portion, with the terracotta-roof household left of center, clinic to the right, and watercourse lower left. Secondary buildings extend outward so it feels like a neighborhood rather than three isolated props.

Water state W0. Soft daylight. No characters, report pins, flood footprint, network diagnosis, probability gauge, or status dashboard.

The relevant road can be recognizable through composition alone. At most, use two small backed labels, “Homes” and “Clinic”; save the emphasized line for S1.

## Entrance and exit

The headline and poster must make sense without animation. Optional entrance: a slight model fade/settle, no aerial flight. On scroll, the same model viewport adapts into the right-side story stage while the camera fit moves toward the canonical view. Finish that movement before asking the viewer to read detailed road labels.

## Approval criterion

The viewer notices the product promise before the neighborhood detail and can recognize the same home and clinic in S1.

---

# 4. Scene S1-01 — An ordinary day

## Communication objective

Establish one usual home-to-clinic connection while the neighborhood is dry.

## Exact copy

**Eyebrow:** 01 / EVERYDAY CONNECTIONS

**Headline:**
Everyday life
depends on
connections.

**Supporting copy:**
Homes, care, supplies, and support are linked through the same local network.

**Resident card:**
Household preparedness
Review your plan and the information available for your area.

**Resident action label:** Checking a household plan

**Map labels:** Homes; Usual connection; Clinic

## Main still composition

Use the canonical right-side map with W0. H01 and C01 are visually distinct. The connection line follows road centerlines, starts at G-H, ends at G-C, and is approximately 4–5 px in the final 1920 artboard. Use neutral analytical blue with a quiet cream halo where needed. Endpoint labels explain its meaning; the line is not a safe-route instruction.

Left rail contains the heading and copy. Below it, R-01 appears beside a modest table with a folded paper plan and phone. A single preparedness card sits adjacent to her, not across the map.

The rest of the town retains material detail but lower contrast than the anchors. Avoid a bright colored ring around every building.

## Motion beats

1. Settle the camera and show home/clinic labels.
2. Draw the connection once, home to clinic.
3. Permit one small neutral journey marker to traverse the line once, then disappear.
4. Bring in the resident vignette and preparedness card. Hold the diagram still for reading.

## Exit

Do not alter the camera. Fade the resident card into its next message only after the ordinary connection has been established. Begin weather transition in the background.

## Approval criterion

The connection is unambiguous even with the resident vignette hidden. The physical road and analytical line follow the same path.

---

# 5. Scene S2-01 — Conditions change

## Communication objective

Show an environmental change and a preparation question without implying an invented forecast or alert.

## Exact copy

**Eyebrow:** 02 / CONDITIONS CHANGE

**Headline:**
When conditions
change, the next
question becomes
local.

**Supporting copy:**
Which places and connections might need attention?

**Concept preparedness card:**
Conditions are changing
Review available updates and your household plan.

**Card label:** Illustrative preparedness view

**Map annotations:** Rising water in this illustration; Usual connection

## Main still composition

Same camera, house, clinic, trees, road geometry, and connection. W1 watercourse is fuller and ponding is visible on adjoining low ground, but L01 is not yet shown underwater.

A broad, soft cloud shadow crosses the lower-middle ground. The image is cooler and slightly less sunlit, not dark or nightlike. A small amount of cloud edge may be visible at the distant upper edge if composition permits; overhead cartoon cloud icons are not required. No lightning flashes or dense rain obscuring the roads.

R-01 wears the same clothes, holds the same phone, and looks at it attentively. The preparedness card remains a concept, not an official notification.

## Motion beats

1. Cloud shadow slowly changes the light.
2. Water moves from W0 toward W1.
3. The resident shifts attention to the phone.
4. The card becomes readable and motion settles.

No synchronized sequence that visually claims “cloud detected → FloodGuard predicts flood.” Physical atmosphere and product copy are separate explanatory layers.

## Exit

Retain the same camera and anchors. Reduce the emphasis on the resident so the next water/connection change is the focus.

## Approval criterion

The frame is recognizably later than S1, but it does not show an invented chance percentage, danger threshold, official alert, evacuation order, or verified closure.

---

# 6. Scene S3A-01 — The less-obvious consequence

## Communication objective

Make the core insight obvious: a home and clinic can remain outside the illustrated water while the usual connection between them is affected.

## Exact copy

**Eyebrow:** 03 / CONNECTIONS AFFECTED

**Headline:**
A place can remain
dry while its usual
connection is
disrupted.

**Supporting copy:**
The flood footprint does not tell the whole story of access.

**Resident question:**
What does this mean for our access to care?

**Map labels:**
Homes outside the illustrated flood
Connection affected in this scenario
Clinic outside the illustrated flood

Use short visible labels “Homes,” “Affected connection,” and “Clinic” when the long versions would overlap; place the fuller meaning in one callout or accessible text.

## Main still composition

Canonical view, W2, softly overcast light. Home cluster remains dry upper-left; clinic remains dry lower-right; the irregular water footprint occupies the lower middle and reaches L01.

The usual connection remains readable to either side of L01. At L01, change the line to a short amber dashed section with a small bracket/callout identifying the scenario effect. This is an analytical annotation, not visible road paint or a verified closure symbol. Never put a solid green detour alongside it.

The resident sits in the left vignette, attentive and concerned, with her question as a clean caption. No navigation instructions on her phone. No full analytical panel yet: the question must land before the answer.

## Motion beats

1. Hold camera. Advance W1 to W2.
2. Stop the water progression.
3. Change the L01 overlay style; keep both endpoints readable.
4. Reveal the resident question and hold.

Do not launch a character entrance, water rise, camera move, and evidence-card transition together.

## Exit

W2 remains fixed for the rest of the story. The next change is the appearance of structured analytical information, not higher water.

## Approval criterion

With the body paragraph covered, a viewer can identify both dry endpoints and the affected middle connection. The scene does not claim complete isolation or that the clinic is operating.

---

# 7. Scene S3B-01 — The analytical explanation

## Communication objective

Show FloodGuard making a concern inspectable by connecting the illustrated flood, network, area, and local observation.

## Exact copy

**Eyebrow:** 03 / CONNECTIONS AFFECTED

**Headline:**
Connect the
evidence to the
consequences.

**Supporting copy:**
Examine the affected connection, the communities linked to it, and the questions that still need review.

**Main card:**
ILLUSTRATIVE ACCESS FINDING
The usual connection may be affected.
It crosses the flooded part of this scenario.

Basis
Flood footprint + road connection

Local input
DEMO-R01 · Not verified

Needs review
Road condition, other connections, and clinic status

**Report pin label:** Reported — not yet verified

**Selected area label:** Selected for review

## Main still composition

Canonical camera and identical W2. Preserve material colors. Make the footprint's boundary slightly more legible using a restrained blue-gray outline distinct from the amber connection annotation. Reduce unselected neighborhood contrast modestly, without fading the whole scene to near white.

Selected anchors: household cluster, L01, clinic, and a thin perimeter identifying the area being examined. The selected-area mark represents focus, not a generated severity score. A hollow report marker sits beside L01, offset so it does not obscure the connection. Show its expanded label during S3B-OBS; in the main planner frame, collapse it to a DEMO-R01 badge and put the unverified status in the finding card so map text does not accumulate.

P-01 now occupies the left vignette. The planner's gesture and gaze lead toward one readable finding card. Place the finding card in the reserved upper-right map margin (approximately x 1440, y 184, width 400, height 392); never place it across H01, L01, or C01.

Do not duplicate a full dashboard. This is one focused explanation, not a map covered with charts.

## Within-scene microstate S3B-OBS

Before the planner composition, briefly retain R-01 in the same safe interior. Show a sample observation card:

DEMO-R01 / SAMPLE OBSERVATION
Water reported near the lower connection.
Not verified.

A neutral linking motion connects the card to the hollow marker. Keep “sample” readable. There is no actual form submission, backend acknowledgment, official closure, or rescue notification implied by the concept image.

## Motion beats

1. Outline the illustrated flood footprint.
2. Clarify the relevant network and endpoints.
3. Introduce the sample observation microstate and hollow marker.
4. Crossfade the resident vignette into the planner vignette.
5. Planner selects the area; the finding card appears.
6. Hold long enough to inspect basis and open questions.

All map selections and cards refer to the same objects. This scene gets more narrative emphasis than the weather transition.

## Approval criterion

The viewer sees what FloodGuard adds beyond water and pins: an explained connection concern. The local report is visibly unverified and does not change the map into a verified closure state.

---

# 8. Scene S4-01 — A more informed next step

## Communication objective

Resolve the story with a specific reviewable output, not the appearance of solved flooding or automatically dispatched help.

## Exact copy

**Eyebrow:** 04 / NEXT STEPS

**Headline:**
A clearer picture
of what needs
attention.

**Supporting copy:**
Review the connection, record the open questions, and prepare the next planning step.

**Planner card:**
ILLUSTRATIVE REVIEW BRIEF
Homes–clinic connection

Reason for review
Scenario flooding intersects the usual connection.

Next check
Review road condition and other connections.

Still unknown
Clinic operating status.

**Optional concept control:** Inspect the review brief

## Main still composition

Same W2 and canonical camera. P-01 remains at the desk. The explanation card becomes a compact brief: one selected connection, a reason, a next check, and an unknown. It remains a proposed illustrative output, not a claim that an actual agency accepted a task.

The household marker, connection callout, and clinic label remain visible in the map. Use “Review needed” rather than an unexplained score or an urgent ranking. Do not invent population counts, travel times, evaluation scores, or verified shelter capacities.

## Within-scene microstate S4-PUBLIC

Briefly return to R-01 in the same home setting. Replace the staff finding/brief with a simpler public concept card:

HOUSEHOLD PREPAREDNESS
Review your household plan.
Check available official updates.
Find official contact information.

Staff access-analysis geometry is not mirrored into the phone screen. No evacuation route, fake emergency phone number, dispatch receipt, or “all clear” badge. The resident is focused, not celebrating.

This microstate shows another role-specific view. It is not an animated claim that the planner sent an official instruction to the resident.

## Within-scene microstate S4-END

Withdraw the large portraits and perform a slight pullback of the same model, keeping all anchors visible. W2 water and overcast light remain unchanged. Retain one compact summary of the selected concern and its open questions.

Closing copy:
See the flood. Understand the impact.
Support the next planning step.

Primary action: Explore the planning demo
Secondary links: Public preparedness; Inspect the evidence

These controls lead to the actual workspaces when wired into the application. Do not animate a journey through an unverified route as an ending.

## Approval criterion

The outcome is visible as clearer reasoning and a reviewable next step. The scene ends without water receding, a surprise rescue arrival, a safe-route guarantee, or uncertain information turning into certainty.

---

# 9. Semantic overlay system

| Meaning | Visual treatment | Important distinction |
|---|---|---|
| Usual illustrative connection | Thin continuous analytical-blue line, labeled endpoints | Not a safe-route recommendation. |
| Segment affected in the illustration | Short amber dashed section and backed text callout | Not an independently verified closure. |
| Flood footprint | Muddy illustrated water plus restrained blue-gray outline when analytical view appears | Physical water and analytical boundary are different layers. |
| Local sample observation | Hollow marker, “DEMO-R01,” unverified label | Not a sensor observation, official alert, or automatically accepted fact. |
| Area selected for review | Thin neutral/teal perimeter and “Selected for review” | Not a probability, urgency rank, or danger class. |
| Missing knowledge | Explicit “Unknown” or “Needs review” text | Absence of information never appears as a safe/clear status. |

If an optional planning alternative is ever added, keep it staff-only, dashed, and labeled “Planning alternative — requires verification.” It is excluded from this v1.0 core sequence so that the central explanation stays focused.

---

# 10. Continuity and motion rules

| Transition | Changes | Does not change |
|---|---|---|
| Hero → S1 | Viewport layout, camera fit, introduction of one line and resident | Neighborhood identity, sun direction, dry state |
| S1 → S2 | Light softness, channel/ponding state, resident attention | Camera, road geometry, home, clinic, clothing |
| S2 → S3A | W1 to W2, central connection overlay, resident question | Camera, destinations, illustration identity |
| S3A → S3B | Analytical boundaries, sample report, planner, explanation | W2 footprint, geography, road location |
| S3B → S4 | Finding becomes brief, role-specific public microstate, final modest pullback | Water, uncertainty, no verified operational outcome |

Proposed share of story attention excluding the hero: S1 18%, S2 12%, S3A 22%, S3B 28%, S4 20%. These are storyboard priorities, not a requirement to lock scrolling or force a fixed viewing time.

Keep each scene useful as a static frame. For reduced motion, use the approved W0/W1/W2 stills, persistent explanations, and direct chapter navigation. Pause background movement while meaningful text is being introduced. Do not allow UI state and illustration state to drift apart during reverse scrolling.

The illustration needs one authoritative scene state for camera, water, selected features, character, and active copy. The renderer should not derive evidence status from water height or animation progress; semantic states are authored for this illustrative story.

---

# 11. Mobile storyboard variant

Target a 390 × 844 reference artboard. Do not simply scale the desktop scene down.

Order content as chapter label/headline, diagram, then character/interface vignette. A chapter may extend below one screen; do not compress the whole desktop composition into 844 pixels.

For the dry-to-flooded comparison, keep one registered image crop that retains H01, L01, and C01. Remove peripheral buildings from the crop, not the three anchors. Use backed labels of readable size. Do not put a floating portrait across the diagram.

S3B's finding and S4's brief sit below the map at full content width. Keep the sample-report qualification with the report. Navigation is compact: current chapter title plus accessible previous/next actions and a direct workspace entry. Narrative content remains available without animation or WebGL.

---

# 12. Image-generation and approval package

## 12.1 Generation order

1. Approve the clean canonical W0 neighborhood, without characters or UI. This is the location master, derived from S1.
2. Approve R-01 and P-01 as a paired style sheet with locked clothing, props, and anatomy.
3. Approve the composited S1-01 frame to test scene/character/UI compatibility.
4. Derive S3A-01 by modifying the approved location into W2 without changing geography.
5. Derive S2-01 as the intermediate W1 state.
6. Derive S3B-01 and S4-01 from the identical approved W2 base.
7. Compose the wider hero from the same world; add S4-PUBLIC and S4-END only after the main sequence is approved.

Use an approved image as a visual reference for later variations. Do not independently generate each frame from text and expect exact geographic or character continuity. Any resulting drift in buildings, road topology, camera, or flood footprint must be corrected before the sequence is approved.

## 12.2 Frame naming

- FG_H01_Hero_W0
- FG_S101_Everyday_W0
- FG_S201_Changing_W1
- FG_S3A01_Connection_W2
- FG_S3B01_Analysis_W2
- FG_S401_Planning_W2
- FG_S3B_OBS_SampleReport_W2 (supplemental)
- FG_S4_PUBLIC_Preparedness_W2 (supplemental)
- FG_S4_END_Closing_W2 (supplemental)

## 12.3 Desired outputs for each principal frame

A clean environmental plate, character vignette asset where needed, a finished full-page concept composition, and text/overlay specifications. These are production targets, not an assumption that a generator will directly output layered source files.

Set exact text in the frontend or a layout editor for final production. Image-generation text is provisional. Do not accept misspelled labels, fake tiny data, duplicated fingers, impossible devices, or invented official insignia as harmless background detail.

## 12.4 Shared exclusion list

No emergency-response victory scene; no rescue vehicle appearing because of a button tap; no forecast percentages; no real-looking current timestamp; no fake field validation; no numerical road depths; no live routing arrow; no medical facility turning into a shelter; no homes moving between frames; no disconnected water islands without a designed cause; no complete-isolation claim while other routes remain visible; no floating character at map scale; no stock-dashboard clutter; no exaggerated storm drama.

## 12.5 Acceptance checks

**Comprehension:** With the explanatory paragraph hidden, S3A still shows dry endpoints and an affected connection. S3B shows why the concern is worth inspecting. S4 shows a specific next step.

**Continuity:** Household, clinic, roads, shop, tree, watercourse, camera orientation, clothing, and props remain consistent. W2 matches across all flooded solution frames.

**Hierarchy:** One primary focus per frame. Map anchors are never covered by the character, finding card, navigation, or decorative texture.

**Claim consistency:** Illustration, concept UI, local report, and historical evidence are distinguishable. No visual implies verified routing, warning authority, or dispatch integration.

**Standalone usefulness:** Each approved still is legible without narration, scrolling, or animation. Text remains an accessible interface layer rather than a baked visual dependency.

**Strongest approval test:** Compare S1-01 and S3A-01. The viewer should immediately recognize the same place and understand the change in the usual home–clinic connection.
