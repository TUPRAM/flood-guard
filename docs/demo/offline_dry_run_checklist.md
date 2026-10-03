# Offline dry run: the Mae Sai replay on the demo laptop

Use this when the venue network may fail. The laptop serves its own production build, so the replay, the season envelope layer, the download files and the Thai page work with no internet; only the street basemap needs a connection, and the page says so. The beat to rehearse is in `docs/demo_walkthrough.md` (section "Mae Sai Replay Beat (60-90 s)"); replace the online base with `http://127.0.0.1:3100`.

ใช้รายการนี้เมื่อเครือข่ายในสถานที่จัดงานอาจใช้ไม่ได้ แล็ปท็อปให้บริการหน้าเว็บจากชุดที่สร้างไว้ในเครื่อง การย้อนดู ชั้นขอบเขตน้ำตลอดฤดู ไฟล์ดาวน์โหลด และหน้าภาษาไทยจึงใช้ได้โดยไม่ต้องมีอินเทอร์เน็ต มีเพียงแผนที่ถนนพื้นฐานที่ต้องใช้อินเทอร์เน็ต และหน้าเว็บแจ้งไว้

## 0. Days before, while online

1. Check out the commit that will be shown and install once: `pnpm install --frozen-lockfile` (needs the network; never at the venue).
2. Have Chrome or Edge on the laptop, and Playwright's Chromium for the automated check in step 2 (`pnpm --filter @floodguard/web exec playwright install chromium`, needs the network).
3. Copy `docs/demo/mae-sai-replay-demo.mp4` to the desktop as the venue fallback.

## 1. Build (from the repository root)

```powershell
pnpm build:web
git checkout -- apps/web/next-env.d.ts
```

`pnpm build:web` builds the competition profile into `apps/web/out` (the profile that has the case replay and the policy page) and ends with the profile smoke. The build rewrites `apps/web/next-env.d.ts`; the second line restores it.

## 2. Automated offline check

```powershell
pnpm test:offline
```

It must exit 0 and end with the three summary lines shown under "Recorded result" below. It serves `apps/web/out` on a random local port, saves the replay through the service worker, switches the browser offline and replays: the peak, the residents and access figures, the VIIRS maps, the reported depths, the season envelope (hatched and credited at 1440 px and 390 px) and every download file, byte for byte.

## 3. Serve the build on the laptop

```powershell
cd apps/web
node scripts/preview-static.mjs 3100
```

It prints `FloodGuard static preview: http://127.0.0.1:3100/ (production CSP; local only)`. Keep this window open for the whole demo.

## 4. Save the offline copy in the presenting browser

1. Open `http://127.0.0.1:3100/` once, then link 2 of the walkthrough (`http://127.0.0.1:3100/studio/cases/mae-sai-2024/?t=84&img=auto&wm=depth&wo=85&rm=state&lang=en&layers=trsc&set=reported&k=8&pop=flooded`).
2. Open "Sources, assumptions and limits" and wait for both lines: "Offline copy: this replay's 25 data files are saved on this device" and "Offline copy: the 9 download files are saved on this device too".
3. Bookmark the six links of the walkthrough with the base `http://127.0.0.1:3100`.

## 5. Airplane mode

Turn airplane mode on (Windows: Quick Settings, Airplane mode). Check that no Wi-Fi or cable network is connected.

## 6. What must still work (tick each)

- [ ] Links 1, 2, 3, 4 and 6 open from the bookmarks; the readouts show "Tue 10 Sep 2024 · 22:00 ICT", "Thu 12 Sep 2024 · 12:00 ICT" and "Sun 15 Sep 2024 · 14:00 ICT". / ลิงก์ 1 2 3 4 และ 6 เปิดได้จากบุ๊กมาร์ก
- [ ] The only thing missing is the street basemap, and the map says "The street basemap could not load; it needs an internet connection. Imagery, the water model and roads still show from this device." / ขาดเพียงแผนที่ถนนพื้นฐาน และแผนที่แจ้งเหตุผลไว้
- [ ] Replay with the 4009 layer (link 4): the hatched layer, the chip "Scenario (SCN-ENV): 2024 season envelope", the caption ending "Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.", the map credit "UNOSAT and GISTDA · CC BY-SA 4.0", and "Season envelope comparison (scenario; plausibility, not validation)" with "agreement (IoU) 0.48". / ชั้นข้อมูล 4009 แสดงเป็นลายเส้นทแยง พร้อมป้าย คำอธิบาย และเครดิต
- [ ] Exports: under "Download the tables (for spreadsheets and GIS)", "Modelled road inundation by hour, one row per OpenStreetMap way (modelled, not observed)" saves `modelled_road_inundation_by_hour.csv` (346,104 bytes), which opens in Excel with its Thai column labels; "Save PNG of this moment" saves `mae-sai-flood-2024-09-12-1200-ict.png`. / ดาวน์โหลดตารางและบันทึกภาพ PNG ได้
- [ ] Thai (link 6, or "ไทย" in the header): the readout "พฤ. 12 ก.ย. 2567 (2024) · 12:00 น." and the Thai banner; "English" switches back. / หน้าภาษาไทยแสดงครบและสลับกลับเป็นภาษาอังกฤษได้
- [ ] The fallback video plays full screen in the laptop's player for 73 s. / วิดีโอสำรองเล่นได้ครบ 73 วินาที
- [ ] Optional: stop the server (Ctrl+C) and reload link 2: the replay still opens from the saved copy. / ไม่บังคับ: หยุดเซิร์ฟเวอร์แล้วโหลดลิงก์ 2 ใหม่ หน้ายังเปิดได้จากสำเนาที่บันทึกไว้

## 7. After the demo

Turn airplane mode off and stop the server (Ctrl+C).

## Recorded result of the automated check

- **When and what:** 3 Oct 2026, 16:34 ICT, on the working tree of branch `claude/mae-sai-next` (parent commit `f2bbe1c`), against the competition build made at 15:50 ICT the same day from the same web sources; Windows 11, Node 24.14.1, Playwright Chromium 149.0.7827.55.
- **Command:** `pnpm test:offline`. **Result:** exit 0 in 24.6 s; the policy test 8 of 8 passed.
- **Summary lines:**
  - `offline smoke: 5 polished routes and 15 core assets verified; case replay route precached with 25 deferred data files (6.3 MB, opt-in) and 9 export files (0.91 MB of a 1.0 MB export budget); internal safety contracts retained and no external runtime resources`
  - `browser offline smoke: 5 routes rendered from a content-versioned service-worker cache; the case replay and its 25 opt-in data files replayed offline, the season envelope's raster, statistics and licence notice among them (toggle on, hatched and credited: 1440 px: hatch period 9.1 px; 390 px: hatch period 9 px), the reported depths' nine markers and counts table from the saved manifest, and its 9 export files downloaded offline (906375 of 1000000 export-budget bytes); approved basemaps failed gracefully and no unapproved external requests occurred`
  - `legacy dashboard offline smoke: embedded Leaflet vectors, text equivalent, and dataset control verified`
- **Not covered by the automated check:** it switches the browser offline instead of the laptop's network, and it does not open the Thai page offline or play the fallback video. Steps 5 and 6 cover those, by hand.

## Sign-off (by the person who ran steps 1 to 7 on the demo laptop)

ลงนามโดยผู้ที่ทำขั้นตอน 1 ถึง 7 บนแล็ปท็อปที่ใช้สาธิต

Dry run done by / ผู้ทดสอบ: ______________________ Date / วันที่: ____________ Laptop / เครื่อง: ______________ Browser / เบราว์เซอร์: ______________ Commit: ____________ Result / ผล: pass ผ่าน / fail ไม่ผ่าน

Notes / หมายเหตุ: ________________________________________________
