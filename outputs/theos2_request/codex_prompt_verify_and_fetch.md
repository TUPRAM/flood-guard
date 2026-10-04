# Codex prompt — verify the search plan, then fetch useful open data

Copy everything below the line. It stands alone and assumes no prior context.

---

You are working in the FloodGuard Thailand repository
(`github.com/TUPRAM/flood-guard`), on the `landing-page-revised` branch.

FloodGuard is a non-operational geospatial decision-support prototype that turns
flood extent into subdistrict-level action priorities. It is currently blocked on
acquiring legally usable reference data. Study areas are Mae Sai in Chiang Rai
(September 2024 flood), Hat Yai in Songkhla (November 2025), and the lower Chao
Phraya in Ayutthaya and Pathum Thani (2024 and 2025). AOI polygons are in
`resources/aoi/upload/*.geojson`.

## What I want

**1. Sanity-check the THEOS-2 search plan.** Read
`outputs/theos2_request/theos2_search_plan.csv` and
`outputs/theos2_request/theos2_scene_selection_log.csv`. Tell me whether the plan
is internally consistent and whether the log is complete enough to send to
GISTDA. Use your own judgement on what to check — dates inside their windows,
missing IDs, contradictions, anything that looks wrong. Report only; don't edit
the log.

One thing worth knowing: `portal_cloud_pct` is scene-level cloud measured over a
whole satellite footprint, while `aoi_visual_clarity` is a human's read of cloud
over our much smaller AOI. The two diverge by up to 60 points in both directions,
so a high cloud percentage is not by itself a reason to reject a scene.

**2. Find and download open data that would genuinely help this project.**
GISTDA suggested ThaiWater gauge stations (`thaiwater.net/water/wl`) and DOPA
population. OpenStreetMap and WorldPop are already in the pipeline, so skip
those. Beyond that, use your judgement — the project needs flood reference
extents, official shelter and healthcare locations, road condition records,
terrain and drainage, and age-banded population. Fetch what you can actually get.

## Limits

- **Don't order imagery through `awagad.gistda.or.th`.** Our THEOS-2 access is
  arranged directly with GISTDA: we email them scene IDs and they provision the
  data. The portal is only for browsing the catalogue to identify those IDs, and
  a human is doing that part. Nothing there needs downloading.
- No credentials, no account creation.
- **Nothing binary goes into git.** Source rasters, archives and bulk downloads
  go to the external data workspace described in the README (the
  `FLOODGUARD_EXTERNAL_WORKSPACE` directory — ask if it isn't configured in your
  environment). The repo gets only a manifest row with a redacted path hint and a
  SHA-256. Follow the column pattern in
  `outputs/open_context_data_file_manifest.csv`.
- A dataset with unresolved licence terms is blocked from entering the analysis.
  Record the terms you find and set `processing_allowed=False` where they are
  unclear. Never assume permission — this repo's gates treat an informal yes as
  blocked.
- This is a shared repo with work in progress on it. Don't force-push, don't
  rewrite history, and don't modify existing manifests.

## Output

A short report on the plan check, plus a manifest CSV covering whatever you
fetched and a list of what you couldn't get and why.
