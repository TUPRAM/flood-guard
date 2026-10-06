# Architectural District Art Source

`terrain-scene.ts` is the editable master for the eight-chapter illustration.
It contains 46 varied buildings and one service complex, a continuous street
network, field parcels, vegetation, human-scale residents and integrated review
desks. Original Three.js geometry, vertex-color materials, lighting and small
Canvas2D annotation textures are authored here. No Illoca assets, downloaded
models, external marks or private geographic records are included.

## Provenance and Limits

The opening image is the user-supplied `ChatGPT Image Sep 9, 2026, 11_04_51 AM.png`.
Its source location, date, photographer or generation process are not verified.
It is photo-style concept context, not documentary evidence of Mae Sai. The
generator preserves its full composition and only resizes and encodes WebP.
The manifest records the original filename, exact input SHA-256, input size and
the output hashes. The separately supplied flooded aerial was a visual mood
reference only; it was not used as a registered flood image or published asset.

The illustrative district is informed by the lower-central region of the
opening image: pixels x=650..1290 and y=310..885 in the 1672x941 source. Its
curving main road, lower arterial junction, pale-roof complex, western roof
cluster and northeast field retain broad visual relationships from that region.
This is an authored interpretation, not a traced survey, exact reconstruction,
validated extraction, photogrammetric asset or geographically registered map.
The service building's function and the flood footprint are illustrative.

Neither image ownership/license clearance nor geographic/scientific validity is
established by the technical pipeline. The supplied-image publication decision
remains an owner acceptance item. No Blender project, external art-director
approval, real flood depth, hydraulic model or agency acceptance is claimed.

## Reproduce

From `apps/web`:

```powershell
node scripts/render-landing-assets.mjs --context-image '<path to supplied aerial>'
```

`FLOODGUARD_CONTEXT_IMAGE` is an alternative input. A full run fails clearly
without this input, preventing an unrelated older hero from being retained with
new provenance. `--preview` renders only dry/flood previews into
`test-results/landing-art-preview`; it never changes public assets or their
manifest. Rerun the full command to publish an accepted art change. The manifest
also hashes the editable terrain, camera/state sampler and generator sources.

The script uses existing Playwright, Vite/esbuild and Next/Sharp installations.
A temporary local server bundles this exact Three.js source, Chromium renders
the scene, and WebP posters plus indexed GLBs are written to `public/landing`.
Every GLB is reimported with GLTFLoader before inclusion in the manifest. The
browser and server close when the command finishes. No production server or
Next build is required, and the runtime does not download these GLB handoff files.

Eight alpha-backed chapter posters are 1200x900, with 640x480 variants. The
photographic context hero preserves its original 1672x941 aspect ratio; its
mobile variant is resized to 900 pixels wide without creative alteration.
Older v1 GLBs are retained as unreferenced prior-work artifacts and explicitly
identified in the manifest. They are not current scene sources or runtime loads.

## State and Registration

Coordinates use +Y up and an XZ ground plane, bounded by x[-9,9], z[-6,6]. Units
are arbitrary illustration units, not meters. `DISTRICT_PLAN` records the
building plan, reference selection and roads. Four stable named anchors are
`Junction_A`, `Service_A`, `Neighborhood_A` and `Field_A`. The source and GLBs
include these objects as well as semantic camera and role anchors.

The dry, flood and access chapters use the same geometry and exact orthographic
camera. Only the illustrative water and connection state change. The water rises
over the authored lowland mask, stops below the service apron, and remains at
that level through report acknowledgment, evidence review and closure. A report
or task presentation cannot drain water, restore a road, publish a model or write
operational data. Reverse seeks restore material/visibility state directly.

Runtime `reading-column` composition offsets the camera frustum to reserve the
left reading column. Poster composition is centered. These are presentation
differences, not a second plan. `getSceneTelemetry` projects the actual four
anchor objects through the current camera for registration checks; it does not
provide evidence of correspondence to real-world coordinates.

All annotation text is decorative within the canvas; essential meaning, scope
and workflow state remain accessible HTML. The renderer uses demand frames,
explicit store invalidation, a current-frame readiness handoff and static
fallbacks. There are no animation clocks or autoplay actions in the art source.
Triangle/draw statistics are local laboratory evidence, not field performance.
