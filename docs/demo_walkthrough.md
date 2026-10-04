# FloodGuard Demo Walkthrough

This walkthrough is for the static fixture-backed dashboard at `outputs/dashboard.html`. It is not an official warning, not real flood validation, and not real-data ML output.

The Mae Sai replay beat (60-90 seconds, on the web app's case replay) is the last section: [Mae Sai Replay Beat](#mae-sai-replay-beat-60-90-s).

## Setup

Regenerate the dashboard:

```powershell
uv run python scripts/generate_sample_priority.py
uv run python scripts/generate_sample_decision_outputs.py
uv run python scripts/smoke_dashboard.py
```

Serve locally:

```powershell
uv run python -m http.server 8000 -d outputs
```

Open:

```text
http://localhost:8000/dashboard.html
```

## 3-5 Minute Judge Path

1. Start on `FG-TB-001 / River Market`.
   - Point to FPPS `81.60`, action class `A`, confidence `high`, baseline 30-minute access loss, and equity gap.
   - Say: FloodGuard ranks local action priorities from flood, exposure, access, equity, and road-risk evidence. It is not just showing where water might be.

2. Explain the map.
   - Polygons are synthetic subdistrict priorities.
   - Road segments are synthetic road-risk outputs.
   - The map is fixture-backed and non-operational.

3. Open or point to the `Action Brief` panel.
   - Show the top reason and recommended local actions.
   - Mention that A/B/C briefs are generated for actionable subdistricts.

4. Switch to `FG-TB-002 / Bridge Junction`.
   - This is the best scenario demo row because the intervention and stress-test deltas are visible.

5. Toggle `temporary shelter delta`.
   - Explain that the temporary shelter reduces 30-minute access loss by `30` people in the fixture.
   - The dashboard shows the intervention effect without claiming it is a real deployment plan.

6. Toggle `road closure delta`.
   - Explain the stress case: closing the selected road increases people losing 30-minute access by `50` in the fixture.
   - This is why road-risk and access-loss are part of the decision layer.

7. Switch to `Mae Sai weak-reference candidate`.
   - At regional zoom, point out that only priority road candidates and ADM3 facility clusters are shown.
   - Select `TH570903 / Ko Chang`; the map zooms to selected-area detail, dims surrounding ADM3 units, and reveals typed candidate facilities and detailed roads.

8. Open `Sentinel-1 evidence`, then enter `Judge mode`.
   - Show the pre/post acquisition pair, selected-unit SAR change, flood-probability summaries, source quality, and compact provenance.
   - State that this is weak-reference candidate evidence, not official validation or field validation.
   - Use the English/Thai (`EN / TH`) toggle once to show bilingual readiness, then return to the presentation language.

## 10 Minute Expanded Path

1. Start with the status chips:
   - `Fixture demo`
   - `Non-operational`
   - `Real validation blocked`

2. Explain the FPPS inputs:
   - flood likelihood
   - exposure
   - access gap
   - road criticality
   - vulnerability/context

3. Show `FG-TB-001 / River Market`.
   - It is class A because high exposure and access loss require life-safety action.

4. Show `FG-TB-002 / Bridge Junction`.
   - It is class B because routes and access are the key decision issue.

5. Show `FG-TB-003 / Clinic Basin`.
   - It is class C because essential services are the policy focus.

6. Use action-class filters.
   - Temporarily hide `D` and `E` to focus on actionable A/B/C areas.

7. Use scenario mode:
   - `baseline`
   - `temporary shelter delta`
   - `road closure delta`
   - For `FG-TB-002`, say the temporary shelter improves 30-minute access by `30` people and the road-closure stress case worsens it by `50` people.

8. Use export buttons:
   - `Download current brief`
   - `Download filtered GeoJSON`

9. Switch to the Mae Sai weak-reference dataset and inspect a selected ADM3 unit.
   - Regional zoom intentionally suppresses low-priority road detail and clusters facilities.
   - Selected-area detail reveals all candidate roads and separate hospital, clinic, other healthcare, school, shelter, emergency-service, and community symbols where available.
   - The Sentinel-1 drawer reports derived ADM3 statistics from the real pre/post pair; it does not claim official validation.

10. Close in `Judge mode`:
   - Secondary controls and long reports are hidden, but the weak-reference warning, source quality, SAR evidence, and provenance remain visible.
   - THEOS-2, SAR quicklooks, and DEM previews remain context only.
   - Official validation remains blocked; current Mae Sai metrics are against a manually digitized weak-reference candidate and are not field validated.

## Exact Phrases To Use

- "This is a fixture-backed decision demo."
- "This is non-operational and not an official warning."
- "The context assets are not flood labels or reference masks."
- "The current real-data candidate is evaluated against a manual weak reference, not an official or field-validated mask."
- "The differentiator is turning flood information into access, equity, road risk, scenario effects, and local action briefs."

## Avoid Saying

- "Real-time detection"
- "Official warning"
- "Validated flood extent"
- "THEOS-2 confirms flooding"
- "Sentinel-1 quicklook proves flood water"
- "ML is ready"

## Mae Sai Replay Beat (60-90 s)

The replay of the September 2024 Mae Sai flood is a historical reconstruction for preparedness learning. Its water is a terrain-model reconstruction at an illustrative river stage, with low confidence. It gives no priority score and no action class. The beat below takes 60 to 90 seconds; every figure it says aloud is in `docs/demo/replay_numbers.md`, which is regenerated from the replay files after any re-bake.

### Before the beat

- **Primary until this branch is merged: the offline laptop.** `http://127.0.0.1:3100`, built from this branch after the steps in `docs/demo/offline_dry_run_checklist.md`. Every figure below, and `docs/demo/replay_numbers.md`, is this build's.
- **Online, unverified:** `https://flood-guard-tau.vercel.app` is production, built from master. Nobody has yet opened it logged out on a phone, and whether it is public is the owners' decision H8: check both before relying on it. Until this branch is merged and production rebuilt, production serves master's replay. The six links below use only parameters that master's replay already reads, so they open the same moments there, but two answers under "If asked" differ (marked there): production has no reported-depth layer, and its radar line shows the cross-track pair (6 Sep 18:31 ICT to 16 Sep 06:16 ICT, 23.57 km² newly water-like, IoU 0.07) instead of the same-track pair.
- **Venue fallback:** `docs/demo/mae-sai-replay-demo.mp4`, 73 s, 16:9, English, recorded with the page's own video export (see `docs/demo/README.md`). Play it if neither the network nor the laptop works, and say the same lines.
- **Screen:** a full-screen browser at 1920 × 1080, zoom 100%. Open each link from a bookmark; the page writes the same link back into the address bar once it has loaded.

### The six links

Append each path to the base above. Parameters: `t` replay hour since 9 Sep 00:00 ICT; `img` imagery (`auto` = the latest optical image at that hour); `wm` water view (`depth`, or `arrival` = first flooded); `wo` water opacity in percent; `rm` road view; `cmp` the two images of the swipe comparison; `lang` `en` or `th`; `layers` one letter per map layer (`t` subdistricts, `r` roads, `s` shelters reported in 2024, `c` ranked plan sites, `e` the 2024 season envelope); `set` the shelter set the map shows; `k` the plan size; `pop` whose access the equity block counts (`flooded` = residents whose homes flood at the peak).

| # | Moment | Path |
|---|---|---|
| 1 | Onset, 10 Sep 22:00 ICT, first-flooded view | `/studio/cases/mae-sai-2024/?t=46&img=auto&wm=arrival&wo=85&rm=state&lang=en&layers=trsc&set=reported&k=8&pop=flooded` |
| 2 | Peak, 12 Sep 12:00 ICT: access and the two shelter sets | `/studio/cases/mae-sai-2024/?t=84&img=auto&wm=depth&wo=85&rm=state&lang=en&layers=trsc&set=reported&k=8&pop=flooded` |
| 3 | 15 Sep 14:00 ICT: observed evidence, swipe 5 Sep against 15 Sep | `/studio/cases/mae-sai-2024/?t=158&img=auto&wm=depth&wo=85&rm=state&cmp=s2-20240905,s2-20240915&lang=en&layers=trsc&set=reported&k=8&pop=flooded` |
| 4 | Peak with the 2024 season envelope (product 4009) and the checks | `/studio/cases/mae-sai-2024/?t=84&img=auto&wm=depth&wo=85&rm=state&lang=en&layers=trsce&set=reported&k=8&pop=flooded` |
| 5 | Exports, on the same page as link 4 | open "Sources, assumptions and limits" at the foot of the right column |
| 6 | The same peak in Thai | `/studio/cases/mae-sai-2024/?t=84&img=auto&wm=depth&wo=85&rm=state&lang=th&layers=trsc&set=reported&k=8&pop=flooded` |

### What to do, say and show

1. **Onset (0:00-0:15), link 1.**
   - Do: let the map settle; point at the purple areas of the "First flooded (model, local time)" legend.
   - Say: "Mae Sai, September 2024, replayed hour by hour. The water is a model reconstruction with low confidence, not observed and not real-time. By 22:00 on 10 September the model has 48.1 km² under water; purple flooded first."
   - พูด: "นี่คือแม่สาย เดือนกันยายน 2567 (2024) ย้อนดูทีละชั่วโมง น้ำที่เห็นเป็นการจำลองจากแบบจำลอง ความเชื่อมั่นต่ำ ไม่ใช่การสังเกตการณ์ และไม่ใช่ข้อมูลเรียลไทม์ เวลา 22:00 น. วันที่ 10 กันยายน แบบจำลองมีน้ำท่วม 48.1 ตร.กม. สีม่วงคือพื้นที่ที่ท่วมก่อน"
   - On screen: the banner "Historical reconstruction for preparedness learning — not real-time, not an official warning."; the readout "Tue 10 Sep 2024 · 22:00 ICT" and "Onset · assumed stage 1.26 m"; in the right column, the card "Impact (model)" with "Flooded area" 48.1 km² and the card "People in flood water (model)" with 8,211 "Modelled residents in reconstructed water, at this replay hour". (The one-line summary under the readout, "Onset · Model: 48.1 km² flooded · 8,211 residents in flood water", shows only on screens 1080 px wide or less.)
2. **Peak, access and the shelter comparison (0:15-0:35), link 2.**
   - Do: scroll the right column to "The two shelter sets side by side" (the map stays in view).
   - Say: "At the modelled peak, noon on 12 September, 88.7 km² and 16,060 residents are in water. Walking access is a T1 scenario: the shelters used in 2024 lose 21% of the people they could reach, the plan of eight loses 54% but reaches more homes that flood. Read both columns; we rank neither."
   - พูด: "ที่ระดับสูงสุดของแบบจำลอง เที่ยงวันที่ 12 กันยายน น้ำท่วม 88.7 ตร.กม. และผู้อยู่อาศัย 16,060 คนอยู่ในพื้นที่น้ำท่วม การเดินไปถึงที่พักพิงเป็นสถานการณ์จำลองระดับ T1 ที่พักพิงที่ใช้ในปี 2567 (2024) สูญเสียผู้ที่เคยเดินถึงได้ 21% แผน 8 แห่งสูญเสีย 54% แต่ไปถึงบ้านที่ถูกน้ำท่วมได้มากกว่า ต้องอ่านทั้งสองคอลัมน์ เราไม่จัดอันดับชุดใด"
   - On screen: the card label "T1 SCENARIO (MODEL) · EVACUATION ACCESS" and "CONFIDENCE: LOW"; "No single figure ranks the sets; read both columns. Hours from illustrative stage keyframes, not observed."; the rows "7,086 of 34,525 (21%)" and "13,429 of 24,910 (54%)", and "5,698 of 14,169" beside "7,580 of 14,169".
3. **15 September, observed evidence (0:35-0:50), link 3.**
   - Do: drag the swipe divider across the town; then scroll the right column to "Evidence for this moment".
   - Say: "On 15 September the satellites see again; Sentinel-2, VIIRS and the rain gauges are observed. Sentinel-2 sees 36.8 km² of water or mud, the model 18.0 km² in the same clear pixels; the larger area is consistent with water left after the river fell."
   - พูด: "วันที่ 15 กันยายน ดาวเทียมมองเห็นอีกครั้ง Sentinel-2 VIIRS และสถานีวัดฝนเป็นข้อมูลจากการสังเกตการณ์ Sentinel-2 เห็นน้ำหรือโคลน 36.8 ตร.กม. ส่วนแบบจำลองมี 18.0 ตร.กม. ในพิกเซลเดียวกันที่ไม่มีเมฆ พื้นที่ที่ใหญ่กว่าสอดคล้องกับน้ำที่เหลือหลังแม่น้ำลดลง"
   - On screen: the swipe labels "5 Sep 10:58 ICT · Sentinel-2" and "15 Sep 10:58 ICT · Sentinel-2"; "brown areas are consistent with mud left by floodwater (observed image; our reading)"; the rows "Sentinel-2 (observed)" (ending "This comparison is indicative.") and "VIIRS (observed)"; the chart title "River stage (assumed) and rain (observed)".
4. **The checks and the season envelope (0:50-1:10), link 4.**
   - Do: point at the hatched layer and its chip; scroll the right column through the checks under "Evidence for this moment" to "Season envelope comparison (scenario; plausibility, not validation)".
   - Say: "The checks are labelled: GISTDA is a calibration anchor; UNOSAT 3991 and the radar comparison are calibration-informed. The hatched layer is product 4009 from UNOSAT and GISTDA, a scenario envelope, not an observation for any day. Agreement with our peak is 0.48: plausibility, not validation, and a pointer to check Ko Chang and the town first."
   - พูด: "การตรวจสอบทุกรายการมีป้ายกำกับ GISTDA เป็นจุดอ้างอิงที่ใช้ปรับแบบจำลอง UNOSAT 3991 และการเทียบกับเรดาร์มีส่วนในการปรับแบบจำลอง ชั้นลายเส้นทแยงคือผลิตภัณฑ์ 4009 ของ UNOSAT และ GISTDA เป็นขอบเขตสถานการณ์จำลอง ไม่ใช่การสังเกตการณ์ของวันใด ค่าความสอดคล้องกับระดับสูงสุดของเราคือ 0.48 เป็นการดูความเป็นไปได้ ไม่ใช่การยืนยันความถูกต้อง และชี้ว่าควรตรวจเกาะช้างและตัวเมืองก่อน"
   - On screen: the chip "Scenario (SCN-ENV): 2024 season envelope"; the caption under the map with "FloodGuard did not validate it.", "not an observation for any replay day" and "Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009."; the map credit "UNOSAT and GISTDA · CC BY-SA 4.0"; the headings "Calibration anchor (not an independent check)" and "Size checks (calibration-informed, not independent)"; the line "Radar size comparison (... calibration-informed, not an independent check)"; "agreement (IoU) 0.48".
5. **Exports (1:10-1:20), on the same page.**
   - Do: open "Sources, assumptions and limits", scroll to "Download the tables (for spreadsheets and GIS)" and click "Modelled road inundation by hour, one row per OpenStreetMap way (modelled, not observed)"; point at "Save PNG of this moment" under "Share and export".
   - Say: "Every table downloads, in Thai and English, stamped modelled, low confidence and non-operational, and works offline."
   - พูด: "ตารางทุกไฟล์ดาวน์โหลดได้ มีทั้งภาษาไทยและภาษาอังกฤษ ระบุว่าเป็นค่าจากแบบจำลอง ความเชื่อมั่นต่ำ ไม่ใช้ในการปฏิบัติการ และใช้ได้แม้ออฟไลน์"
   - On screen: "T1 scenario (model): modelled, not observed."; the download saved as `modelled_road_inundation_by_hour.csv`.
6. **Thai (1:20-1:30), link 6 or the "ไทย" button in the header.**
   - Say: "And the whole page switches to Thai. The replay gives no priority score and no action class; those belong to the planning overlay."
   - พูด: "และทั้งหน้าเปลี่ยนเป็นภาษาไทยได้ การย้อนดูนี้ไม่ให้คะแนนลำดับความสำคัญและไม่กำหนดระดับการดำเนินการ ซึ่งเป็นงานของชั้นข้อมูลวางแผน"
   - On screen: the readout "พฤ. 12 ก.ย. 2567 (2024) · 12:00 น."; the banner "การจำลองย้อนหลังเพื่อการเรียนรู้ด้านการเตรียมพร้อม — ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่คำเตือนอย่างเป็นทางการ"; the footer "ไม่มีการคำนวณคะแนนลำดับความสำคัญด้านการเตรียมพร้อมรับน้ำท่วม (FPPS) และไม่มีการกำหนดกลุ่มการดำเนินการ (A–E)".

### Labels that must be said or seen

| Label | Where it is on screen | Said aloud in |
|---|---|---|
| Water is a model reconstruction with low confidence | the banner; "Water: Model reconstruction from terrain ... not an observation" and "Confidence LOW" under "Evidence for this moment"; the legend "Water depth (model)" | beat 1 |
| VIIRS, rain and imagery are observed | "VIIRS (observed)"; "River stage (assumed) and rain (observed)"; the imagery caption and swipe labels; "Sentinel-2 (observed)" | beat 3 |
| Access is a T1 scenario | "T1 SCENARIO (MODEL) · EVACUATION ACCESS"; "Access: T1 scenario (model), not observed evacuation outcomes" | beat 2 |
| GISTDA is a calibration anchor | "Calibration anchor (not an independent check)" | beat 4 |
| UNOSAT 3991 and the Sentinel-1 comparison are calibration-informed | "Size checks (calibration-informed, not independent)"; "Radar size comparison (... calibration-informed, not an independent check)" | beat 4 |
| Product 4009 is a scenario envelope | the chip "Scenario (SCN-ENV): 2024 season envelope"; the caption; "Season envelope comparison (scenario; plausibility, not validation)" | beat 4 |
| The replay is not real-time | the banner, in English and in Thai; the video's title card: "not real-time, not an official warning" | beat 1 |
| No priority score or action class on the replay | the footer; "How to read these numbers": "it gives no priority score and no action class"; card labels "No action class assigned" | beat 6 |

### If asked

- About the river level: the stage is an illustrative keyframe curve shaped to the event chronology; no public hourly gauge record for September 2024 was found.
- About how close the model is: the radar comparison agrees on size only (IoU 0.065 on location, on this branch's build); the season envelope comparison is plausibility, not validation; the news reports give 21 place records from 17 statements in 14 articles (a statement that names three communities is recorded once per community), and the model is dry at 9 of them over their time window, mostly records from the morning of 10 September, before the modelled rise; only 1 reported number is reached, and 2 storey or body references are wet in the model with no depth compared.
  - On production before the merge: the radar line shows the cross-track pair instead (IoU 0.07), and there is no reported-depth layer to point to; say that the reported-depth check is in the next build.
- About population: residents are WorldPop 2020 modelled estimates, not the 2024 population.
- About where the scored ranking is: in the planning overlay, under the signed protocol; the replay never computes or copies it.

## Replay Beat: Words To Avoid

The shared wording lint (`apps/web/src/lib/replay-wording-rules.json`) flags every phrase on the left; say the words on the right instead.

| Do not say | Say instead |
|---|---|
| "real-time flood map" | "historical reconstruction, not real-time" |
| "live data" | "dated observations" |
| "flood forecast" | "model reconstruction at an illustrative stage" |
| "flood warning for Mae Sai" | "not an official warning" |
| "the model is validated" | "agreement 0.48: plausibility, not validation" |
| "model accuracy" | "agreement (IoU)" |
| "precision and recall against 4009" | "share of the modelled water inside the envelope" |
| "the September extent" | "the 2024 season envelope, August to October" |
| "GISTDA's map" | "product 4009 from UNOSAT and GISTDA" |
| "the envelope observed in September" | "a scenario envelope, not an observation for any day" |
| "a 100-year flood" | "a what-if level around an illustrative peak" |
| "the road closure schedule" | "modelled road inundation by hour" |
| "the better plan" | "read both columns; we rank neither" |
| "the last safe time to leave" | "the modelled access cut-off hour" |
| "open these shelters" | "candidates to verify on the ground" |
| "confirmed by news reports" | "reported in news, not surveyed" |
| "21 news reports read dry" | "the model is dry at 9 of 21 place records" |
