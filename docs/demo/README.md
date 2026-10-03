# Demo materials for the Mae Sai replay

Roadmap item P4-1 (demo readiness). The replay is a historical reconstruction for preparedness learning: its water is a model reconstruction with low confidence, it is not real-time and not an official warning, and it gives no priority score and no action class.

| File | What it is |
|---|---|
| `../demo_walkthrough.md`, section "Mae Sai Replay Beat (60-90 s)" | The six deep links, what to do, say (English and Thai) and show, and the words to avoid |
| `../demo_story.md`, section "Replay Beat (60-90 s)" | The story of the beat in one paragraph and its path |
| `replay_numbers.md` | Every figure the deck or the speaker may quote, generated from the replay files by `scripts/build_replay_numbers.py`; `tests/test_replay_numbers.py` fails until it is regenerated after a re-bake |
| `offline_dry_run_checklist.md` | The steps to run the demo on the laptop without internet, the recorded `pnpm test:offline` result and the line for the person who signs the dry run |
| `mae-sai-replay-demo.mp4` | The venue-fallback video, below |

## Venue-fallback video

| Item | Value |
|---|---|
| Path | `docs/demo/mae-sai-replay-demo.mp4` (in Git: under the 15 MB limit) |
| Size | 8,058,422 bytes |
| SHA-256 | `4db742626ddee319dbae32cd5a67ac1a101bb0ca8552784e10c338d45299887e` |
| Format | MP4 (H.264), 1280 × 720 (16:9), about 24 frames per second, no sound |
| Duration | 73.1 s |
| Language | English |
| Recorded | 3 Oct 2026, from the local competition build of branch `claude/mae-sai-next` (parent commit `f2bbe1c`, replay revision r4 generated 2026-10-03T15:07:00+07:00), headless Playwright Chromium 149.0.7827.55 |

**How it was made.** `apps/web/scripts/record-replay-demo-video.mjs` serves `apps/web/out` on 127.0.0.1 with the production headers of `vercel.json`, opens the replay in English with its default view (water depth, no season envelope), chooses the 16:9 shape and presses the page's own "Record video" button; the browser's MediaRecorder records the export canvas. Every request to another host is blocked, so nothing came from the network.

- **Pace.** The built-in export plays the replay at 2 s per day (about 24 s in all). For a 60-90 s spoken beat the script ran the page clock (`performance.now` and the animation-frame timestamps) at one third of real speed while recording, so the export's own frames play at 6 s per day: a 3 s title card, 9 to 19 September in 66 s, then a 3 s end card. Nothing else in the frames changes.
- **Container.** The browser records MP4 as fragments whose header gives a wrong duration (3.7 s), so players could not seek or show the length. The script rewrote the file as a progressive MP4 with full sample tables (`apps/web/scripts/progressive-mp4.mjs`); the 1,778 frames are copied byte for byte, not re-encoded.
- **What it shows.** The export's frames: the dated Sentinel-2 image under the reconstructed water (depth view; low-confidence water washed out and hatched), roads by modelled state, subdistrict outlines, the reported 2024 shelters, a scale bar and a north arrow, and a caption with the moment, the assumed stage, the modelled flooded area, impassable road and residents in flood water, the imagery, and "Model reconstruction — not observed · FloodGuard · confidence: low · not real-time, not an official warning". The title and end cards repeat the disclaimer; the end card gives the modelled peak, 88.7 km² and 16,060 residents in flood water.
- **What it does not show.** The page's cards (access, the shelter comparison, the checks), the season envelope and the Thai page. Beats 2 to 6 of the walkthrough need the page or the slides; the video covers the map.
- **Credits drawn in every frame:** "Contains modified Copernicus Sentinel data 2024 · © OpenStreetMap contributors · Copernicus DEM © DLR e.V., Airbus DS · WorldPop". The envelope is not drawn, so its CC BY-SA credit is not needed in this video.

**Frames checked** (decoded back from the saved file by the script and looked at):

| Time in the video | What it shows |
|---|---|
| 1.5 s | The title card: "Mae Sai flood, September 2024 — day by day" and "Model reconstruction, not observed · not real-time, not an official warning · confidence: low" |
| 14.5 s | Tue 10 Sep 2024 · 22:00 ICT, onset, assumed stage 1.31 m: about 49 km² flooded and 8,377 residents in flood water in the caption (the frame falls between replay hours; the page's hourly figure at 22:00 is 48.1 km²) |
| 24 s | Thu 12 Sep 2024 · 12:00 ICT, peak, assumed stage 3.49 m: 88.7 km² flooded, 16,060 residents in flood water |
| 42.5 s | Sun 15 Sep 2024 · 14:00 ICT, receding: the 15 Sep Sentinel-2 image with brown mud, 19.6 km² flooded in the model |
| 72 s | The end card: "End of the replay: Thu 19 Sep 2024 · 23:00 ICT" and the modelled peak |

**Re-record it** after any re-bake, and once more after the numbers freeze on 23 Oct, from a fresh `pnpm build:web`:

```powershell
cd apps/web
node scripts/record-replay-demo-video.mjs --out ../../docs/demo/mae-sai-replay-demo.mp4 --frames <a scratch folder>
```

Then update the size, SHA-256 and frame notes above; `tests/test_demo_docs.py` compares this table with the file. If a recording ever exceeds 15 MB, keep it outside Git under `FloodGuard_external_data/demo/` and record its path, size and SHA-256 here instead.
