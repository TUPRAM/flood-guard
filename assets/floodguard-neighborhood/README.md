# FloodGuard editable neighborhood

This source scene was constructed for the continuous FloodGuard landing story. It represents one invented neighborhood in every view. It does not represent surveyed Thai buildings, a measured flood, a hydraulic simulation, or a road-closure decision.

## Deliverables

The 188,853,451-byte `.blend` master is a generated local deliverable and is excluded from Git because it exceeds GitHub's ordinary file limit. Its SHA-256 is `4bd1f8706a90830a3932f27c2368042d2e66e749ea17acc6f405dbd05d88a921`. The six authoring/packaging Python modules and the optimized browser images are committed. A fresh checkout can rebuild the editable master using the commands below; the original local master is preserved.

- `floodguard-neighborhood.blend`: editable Blender 5.1 master with procedural materials, lighting, detailed roof tiles, window/shutter/teak details, garden walls and gates, individual leaf geometry, terrain, road surfaces, and a separate water surface.
- `../../tools/neighborhood/architecture.py`: deterministic house and clinic authoring module.
- `../../tools/neighborhood/vegetation.py`: deterministic broadleaf trees, banana clumps, and shrubs.
- `../../tools/neighborhood/build_scene.py`: composition, terrain, roads, water, lighting, camera and projected story attachment points.
- `../../tools/neighborhood/package_renders.py`: WebP derivatives and SHA-256 provenance.
- `../../outputs/landing-v2-assets/renders/`: high-resolution dry/rising/flooded stills and the rendered camera sequence.
- `../../apps/web/public/landing/floodguard-v2/`: browser derivatives and the build-time scene manifest.

The website delivers rendered 3D with real responsive HTML and transparent 2D illustrated portraits. It does not run a live WebGL neighborhood. The original resident/planner artwork remains in the v1 character directory; it is not baked into the landscape.

## Edit the master

The six named parent groups organize terrain, road/access surfaces, architecture/parcels, landscape, water, and story attachment points. Building and plant roots own their children; moving one root moves that complete asset. Materials start with `FG_`.

The camera and water have editable timeline keyframes:

| Frame | State |
| --- | --- |
| 1 | Wide drone overview, dry channel |
| 48 | Closer neighborhood framing, W0 |
| 96 | W1 rising water |
| 144 | W2 affected connection |

`Controllable_water_surface.location.z` selects the illustrative water height. The river basin is part of the terrain; water is separate geometry and buildings remain fixed. Named empties `Anchor_Home_gate`, `Anchor_Clinic_gate`, and `Anchor_Observation` identify the story locations. The route and selected area are projected from world positions into the manifest, so HTML/SVG controls register against the final camera.

The source geometry is deliberately detailed. Rendered images are the optimized browser exports; the full source is not downloaded by a visitor. Blender procedural material nodes are authoritative for appearance and need baking before a separate real-time model can reproduce them faithfully.

## Reproduce from the repository root

PowerShell, with Blender 5.1 on this machine:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --python tools/neighborhood/build_scene.py -- --mode build
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --python tools/neighborhood/build_scene.py -- --load --mode production
python tools/neighborhood/package_renders.py
python tools/neighborhood/validate_renders.py
python tools/neighborhood/review_board.py
```

Pillow is required only for packaging; the Blender modules use Blender's own Python. Run `--mode probe` for lower-resolution review frames before a production render. Camera/render ranges can also be requested independently with `--mode camera --start 0 --end 16` and `--mode states`.

The deterministic scene seed is `41127`. Asset hashes, exact dimensions, byte sizes and native-render hashes are in `outputs/landing-v2-assets/asset-provenance.json` after packaging. This pipeline modifies only local source/artwork; it does not publish or deploy the site.
