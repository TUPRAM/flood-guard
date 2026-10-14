# Journey v2: brief for the people (Meshy)

The scene is now the real town of Mae Sai; the people are fictional. Today Lalita and Narin are rigged models generated
with Meshy, and Mali, Dao and Pim are simple stand-ins built in code, so the family does not look like one family. This
brief is for making the missing people (and, if wanted, a new Lalita) in the same pipeline, so all five match.

Nothing here is run automatically: generating in Meshy needs the owner's account (the plan's licence must cover
publishing; see `floodguard-3d-pipeline-gotchas`: on the free plan Meshy owns the output under CC BY 4.0).

## One look for everyone

- Same style as the existing Lalita and Narin: realistic proportions, soft stylised textures, no photographic skin.
- Everyday clothes of a northern Thai town in the rainy season; no costumes, no uniforms with real insignia, no logos or
  text on clothing.
- Neutral, calm expressions. These are ordinary people on an ordinary street; nothing about them should read as a
  caricature of an ethnic group or of age.
- One person per model, standing on the ground plane, facing +Z, in an A-pose for rigging (arms about 45° down).

## The people

| Model | Who | Look | Poses (clips) |
|---|---|---|---|
| `lalita` (optional remake) | Resident, about 35 | Straight black hair tied back, light-brown skin; short-sleeved cotton blouse in a warm terracotta, dark trousers, rubber sandals; a phone in her right hand | `PhoneHold` (reading, as now), `Relaxed` |
| `mali` | Lalita's mother, about 68 | Grey hair in a low bun, slightly stooped; loose pale-green blouse, ankle-length patterned sarong-style skirt (pha sin) in muted colours, sandals; a small cloth bag on her shoulder (her medicine) | `Stand`, `HoldBag` (hand on the bag strap) |
| `dao` | Lalita's daughter, 8 | Child proportions (head about 1/6 of height, height about 1.28 m); white school blouse, navy shorts or skirt, black school shoes; short black hair | `Stand`, `LookUp` (head tilted toward an adult on her right) |
| `pim` | District planning coordinator, about 45 | Hair in a bun; muted purple blouse, dark trousers, flat shoes; a lanyard without text | `LeanTable` (both hands on a table edge at about 0.95 m, leaning in), `Stand` |
| `narin` (as now) | Planning officer, about 40 | As delivered | `Typing` (as now) |

### Prompts (text-to-3D; adjust after the first draft)

- **mali:** "68-year-old Thai woman, grey hair in a low bun, slightly stooped, loose pale green cotton blouse, ankle-length
  muted patterned wrap skirt, rubber sandals, small cloth shoulder bag, calm expression, realistic proportions, soft
  stylised textures, A-pose, full body" · negative: "text, logo, jewellery, exaggerated features, caricature".
- **dao:** "8-year-old Thai girl, short black hair, white short-sleeved school blouse, navy blue skirt, white socks, black
  school shoes, child proportions, calm curious expression, soft stylised textures, A-pose, full body" · negative:
  "adult proportions, text, logo, caricature".
- **pim:** "45-year-old Thai woman, hair in a bun, muted purple blouse, dark grey trousers, flat shoes, plain lanyard,
  calm focused expression, realistic proportions, soft stylised textures, A-pose, full body" · negative: "uniform
  insignia, text, logo, caricature".
- **lalita (remake):** "35-year-old Thai woman, straight black hair tied back, warm terracotta short-sleeved cotton
  blouse, dark trousers, rubber sandals, smartphone in right hand, calm expression, realistic proportions, soft stylised
  textures, A-pose, full body".

## Delivery (so the existing build takes them)

- Rig with Meshy's auto-rig (humanoid; the bone names `Hips`, `Spine*`, `Neck`, `Head`, `LeftArm` ... `RightHand*` that
  `characters.ts` already reads). Add each pose as an animation clip with the names above (one held frame is enough).
- Export GLB with embedded textures, no Draco, no meshopt, no KTX2 (the site's CSP blocks their WebAssembly decoders).
- Put them at `deliver/<name>/<name>_rigged.glb` (about 300k triangles and 8K textures is fine: the build reduces them).
- Then add them to `CHARACTERS` in `apps/web/scripts/build-journey-characters.mjs` (targets: about 30k triangles for
  Mali and Pim, 22k for Dao; 2K textures) and run `node apps/web/scripts/build-journey-characters.mjs`.
- The stage places them where the stand-ins stand today (`LAYOUT_FAMILY` and `posePim` in `journey-stage.ts`); Dao's
  `LookUp` and Mali's hand on her bag give the family scene the contact it lacks now.

## What to check when they arrive

- The family reads as one family at the gate (skin tones, style, scale: Mali about 1.52 m, Lalita 1.60 m, Dao 1.28 m).
- No finger crosses Lalita's phone screen (the existing test in `characters.test.ts` checks it after a rebuild).
- Pim's hands rest on the table edge (two-bone fit, as for Narin's fingertips on the keys).
