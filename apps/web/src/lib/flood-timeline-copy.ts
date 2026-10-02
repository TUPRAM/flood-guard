/**
 * Thai renderings of manifest sentences the Mae Sai replay shows in its own panels, plus the page's plain-language
 * clean-up of manifest text (internal ids such as data-set codes are not user copy). The manifest is English and
 * frozen per revision; a sentence without an entry here is shown in its English original, marked `lang="en"`.
 */

import type { Language } from "./flood-timeline";

/**
 * Manifest text with internal identifiers replaced by plain words: the access-set id "reported_2024", WorldPop's
 * product code "(tha_ppp_2020)", field names such as "late_cumulative_share", "model_coverage" or "m=false", and the
 * project's internal decision numbers ("per decision D3", "(D2)", "(decision D7)"). On this page "k" is the plan
 * size, so the manifest's symbol for the depth factor is never shown: the factor is named in words and written "f"
 * where a formula needs a symbol ("depth factor f = clip(…)", "h + 0.3/f"). "km2" is written "km²".
 */
export function plainManifestText(text: string): string {
  return text
    .replace(/\bThe reported_2024 access set\b/g, "The reported-shelter access set")
    .replace(/\breported_2024\b/g, "reported-shelter")
    .replace(/\s*\(tha_ppp_2020\)/g, "")
    .replace(/\s*\(see model_coverage\)/g, "")
    .replace(/\s+are flagged m=false and\s+/g, " are ")
    .replace(/\blate_cumulative_share\b/g, "the late-evacuation share")
    .replace(/\s*\((?:scenario )?per decision D\d+\)/g, "")
    .replace(/\s+\((?:decision )?D\d+\)/g, "")
    .replace(/\bk x stage\b/g, "to a fraction of the stage")
    .replace(/\b(depth factor) k\b/gi, "$1 f")
    .replace(/\bthe exported k\b/g, "the exported depth factor f")
    .replace(/\bscaled by k\b/g, "scaled by the depth factor f")
    .replace(/\bk = clip\(/g, "depth factor f = clip(")
    .replace(/(\d)\/k\b/g, "$1/f")
    .replace(/\bkm2\b/g, "km²");
}

/** A standalone "k" (the plan-size symbol) in a piece of text; the Sources panel must show none from the manifest. */
export const STANDALONE_K = /(?<![A-Za-z0-9_])k(?![A-Za-z0-9_])/;

export const KNOWN_THAI: Readonly<Record<string, string>> = {
  "Copernicus DEM tiles N20E099 and N20E100 cover the whole district.":
    "แผ่นข้อมูล Copernicus DEM N20E099 และ N20E100 ครอบคลุมพื้นที่ทั้งอำเภอ",
  "Low-HAND zone (HAND < 6 m, channel excluded) across the full image footprint, both sides of the border.":
    "พื้นที่ HAND ต่ำ (HAND < 6 ม. ไม่รวมร่องน้ำ) ทั่วทั้งขอบเขตภาพ ทั้งสองฝั่งชายแดน",
  "Water extents are a terrain-model reconstruction with illustrative stages; the late-recession size was tuned to one radar pass rather than checked independently, and spatial agreement there is weak.":
    "ขอบเขตน้ำจำลองจากแบบจำลองภูมิประเทศด้วยระดับน้ำสมมุติ ขนาดพื้นที่ช่วงท้ายของน้ำลดปรับตามภาพเรดาร์หนึ่งภาพ ไม่ได้ตรวจสอบอย่างอิสระ และตำแหน่งยังสอดคล้องกันน้อย",
  "No public hourly Sai River water-level record for Sep 2024 was found (HII MYA004 installed 2025; RID Kh.50 closed; DWR Ban Mae Sai EWS unverified), so stage values remain illustrative.":
    "ไม่พบข้อมูลระดับน้ำแม่น้ำสายรายชั่วโมงที่เปิดเผยสำหรับเดือน ก.ย. 2567 (2024) (สถานี MYA004 ของ สสน. ติดตั้งปี 2568 (2025) สถานี Kh.50 ของกรมชลประทานปิดแล้ว และระบบเตือนภัยบ้านแม่สายของกรมทรัพยากรน้ำยังไม่ได้ยืนยัน) ค่าระดับน้ำจึงยังเป็นค่าเพื่อการอธิบาย",
  "375 m optical data under-detects narrow, shallow, urban or vegetated flooding and sees nothing under cloud; agreement or disagreement is indicative only.":
    "ข้อมูลเชิงแสงความละเอียด 375 ม. ตรวจพบน้ำท่วมที่แคบ ตื้น อยู่ในเมือง หรืออยู่ใต้พืชพรรณได้น้อยกว่าจริง และมองไม่เห็นพื้นที่ใต้เมฆ ความสอดคล้องหรือความต่างจึงเป็นเพียงข้อบ่งชี้",
  "Daily composite of early-afternoon passes; compared with the model at 13:30 ICT.":
    "ภาพรวมรายวันจากการโคจรผ่านช่วงบ่าย เทียบกับแบบจำลอง ณ เวลา 13:30 น.",
  "District only, clear-sky pixels only, permanent water excluded; VIIRS area = sum of flood fraction x pixel area; model area = modelled out-of-channel wet fraction averaged onto the same 375 m pixels.":
    "เฉพาะในอำเภอและเฉพาะพิกเซลที่ท้องฟ้าโปร่ง ไม่รวมแหล่งน้ำถาวร พื้นที่ของ VIIRS = ผลรวมของสัดส่วนน้ำท่วม × พื้นที่พิกเซล พื้นที่ของแบบจำลอง = สัดส่วนพื้นที่เปียกนอกร่องน้ำจากแบบจำลอง เฉลี่ยลงบนพิกเซล 375 ม. เดียวกัน",
  "mm per hour; index 0 = 9 Sep 00:00-01:00 ICT":
    "มม. ต่อชั่วโมง ดัชนี 0 = 9 ก.ย. 00:00–01:00 น.",
  // Evacuation access scenario (the "Sources, assumptions and limits" panel).
  "T1 scenario (model), not observed evacuation outcomes":
    "สถานการณ์จำลองระดับ T1 (แบบจำลอง) ไม่ใช่ผลการอพยพที่สังเกตได้จริง",
  "A resident node loses access when no open, dry shelter of the chosen set is reachable within the threshold on roads that are still passable, having been reachable before the flood.":
    "จุดผู้อยู่อาศัยสูญเสียการเข้าถึงเมื่อไม่มีที่พักพิงที่เปิดและแห้งของชุดที่เลือกซึ่งไปถึงได้ภายในระยะเกณฑ์บนถนนที่ยังสัญจรได้ ทั้งที่ก่อนน้ำท่วมเคยไปถึงได้",
  "walking on passable roads (about 30 min at 4 km/h)":
    "เดินบนถนนที่สัญจรได้ (ประมาณ 30 นาทีที่ความเร็ว 4 กม./ชม.)",
  "Observed rainfall (forcing), not flooding.":
    "ปริมาณฝนที่ตรวจวัดได้ (ปัจจัยที่ทำให้เกิดน้ำ) ไม่ใช่ขอบเขตน้ำท่วม",
  // Confidence reasons, status lines and source timestamps of the scenario cards.
  "Built on the reconstructed water, WorldPop 2020 residents at road nodes, an OSM road graph with assumed walking access and shelters assumed open for the whole replay.":
    "สร้างจากน้ำที่จำลองขึ้น ผู้อยู่อาศัยตาม WorldPop 2020 ที่จุดถนน โครงข่ายถนนจาก OSM โดยสมมุติการเดินเท้า และสมมุติว่าที่พักพิงเปิดตลอดช่วงการย้อนดู",
  "Candidates are OSM public buildings with sparse footprints; eligibility and coverage use the reconstructed peak and walking distance, not site surveys.":
    "สถานที่ที่เป็นไปได้คืออาคารสาธารณะใน OSM ซึ่งมีข้อมูลขอบเขตอาคารน้อย เกณฑ์และความครอบคลุมใช้ระดับน้ำสูงสุดที่จำลองและระยะเดิน ไม่ได้มาจากการสำรวจพื้นที่",
  "Reported use from public sources; not an official register. Locations are OSM matches where possible; low-confidence locations are approximate.":
    "การใช้งานตามรายงานจากแหล่งข้อมูลสาธารณะ ไม่ใช่ทะเบียนทางการ ตำแหน่งจับคู่กับ OSM เท่าที่ทำได้ ตำแหน่งที่มีความเชื่อมั่นต่ำเป็นค่าประมาณ",
  "The reported-shelter access set counts located sites reported as overnight shelters by 15 Sep; the command centre and sites first used after 12 Sep are shown on the map but not counted. Opening times within 10-12 Sep are not modelled.":
    "ชุดการเข้าถึงของที่พักพิงที่มีรายงานนับเฉพาะสถานที่ที่มีตำแหน่งและมีรายงานว่าใช้พักค้างคืนภายใน 15 ก.ย. ศูนย์บัญชาการและสถานที่ที่เริ่มใช้หลัง 12 ก.ย. แสดงบนแผนที่แต่ไม่นับรวม ไม่ได้จำลองเวลาเปิดในช่วง 10–12 ก.ย.",
  "OSM roads and sites 2026-07-09; WorldPop 2020; water model 2024-09-09/2024-09-19 ICT":
    "ถนนและสถานที่จาก OSM 2026-07-09 · WorldPop 2020 · แบบจำลองน้ำ 2024-09-09/2024-09-19 เวลาประเทศไทย",
  "OSM extract 2026-07-09; reported shelters compiled 2026-09-27 from reports dated 2024-09-11 to 2024-10-11":
    "ข้อมูล OSM 2026-07-09 · รวบรวมที่พักพิงที่มีรายงานเมื่อ 2026-09-27 จากรายงานลงวันที่ 2024-09-11 ถึง 2024-10-11",
  "FloodGuard team summary of public reporting; not independently verified in this study":
    "สรุปรายงานสาธารณะโดยทีม FloodGuard ยังไม่ได้ตรวจสอบอย่างอิสระในการศึกษานี้",
  // Why each reported site is, or is not, in the reported-shelter access set.
  "Reported in use by 15 Sep (ICC 9-15 Sep list or earlier reports); exact opening time not modelled.":
    "มีรายงานว่าใช้ภายใน 15 ก.ย. (รายชื่อของศูนย์บัญชาการฯ 9–15 ก.ย. หรือรายงานก่อนหน้า) ไม่ได้จำลองเวลาเปิดที่แน่นอน",
  "The temple was itself flooded and evacuated at the peak; it served as a shelter from 21 Sep.":
    "วัดถูกน้ำท่วมและต้องอพยพในช่วงระดับน้ำสูงสุด แล้วจึงใช้เป็นที่พักพิงตั้งแต่ 21 ก.ย.",
  "Incident command centre and relief kitchens; not a documented overnight shelter in Sep 2024.":
    "ศูนย์บัญชาการเหตุการณ์และโรงครัว ไม่มีหลักฐานว่าใช้เป็นที่พักค้างคืนในเดือน ก.ย. 2567 (2024)",
  "Prepared as a shelter for vulnerable groups by 14 Sep, after the peak.":
    "เตรียมเป็นที่พักพิงสำหรับกลุ่มเปราะบางภายใน 14 ก.ย. หลังช่วงระดับน้ำสูงสุด",
  // GISTDA and UNOSAT size checks.
  "GISTDA RADARSAT-2 flood analysis, 10 Sep 2024 18:15 (time zone not stated; assumed ICT)":
    "การวิเคราะห์น้ำท่วมจาก RADARSAT-2 ของ GISTDA 10 ก.ย. 2567 (2024) 18:15 น. (ไม่ระบุเขตเวลา สมมุติเป็นเวลาประเทศไทย)",
  "Mae Sai 6,182 rai": "แม่สาย 6,182 ไร่",
  "Calibration anchor for the 10 Sep 18:15 knot, not an independent check.":
    "เป็นจุดอ้างอิงที่ใช้ปรับจุดระดับน้ำ 10 ก.ย. 18:15 น. ไม่ใช่การตรวจสอบอิสระ",
  "UNOSAT product 3991: cumulative satellite-detected water 13-19 Sep 2024 over Mae Sai District (Pleiades, RCM, TerraSAR-X, Sentinel, Landsat, PlanetScope)":
    "ผลิตภัณฑ์ UNOSAT 3991: น้ำสะสมที่ตรวจพบจากดาวเทียม 13–19 ก.ย. 2567 (2024) ในอำเภอแม่สาย (Pleiades, RCM, TerraSAR-X, Sentinel, Landsat, PlanetScope)",
  "about 70 km² flood-affected within a 305 km² analysed area; about 13,600 people exposed (WorldPop 2020); preliminary, not field-validated":
    "พื้นที่ได้รับผลกระทบจากน้ำท่วมประมาณ 70 ตร.กม. จากพื้นที่วิเคราะห์ 305 ตร.กม. ประชากรที่อยู่ในพื้นที่น้ำท่วมประมาณ 13,600 คน (WorldPop 2020) เป็นผลเบื้องต้น ยังไม่ได้ตรวจสอบภาคสนาม",
  "Magnitude check over the same window only; UNOSAT is a cumulative multi-sensor observation, not a spatial validation of the model. Calibration-informed, not independent: this figure was known while the stage keyframes were tuned (owner decision, 30 Sep 2026). Its people figure is an exposure estimate, a different measure from the model's residents in water.":
    "ใช้ตรวจขนาดในช่วงเวลาเดียวกันเท่านั้น UNOSAT เป็นการสังเกตสะสมจากดาวเทียมหลายดวง ไม่ใช่การยืนยันตำแหน่งของแบบจำลอง ตัวเลขนี้มีส่วนในการปรับแบบจำลอง จึงไม่ใช่การตรวจสอบอิสระ เพราะทราบตัวเลขนี้แล้วขณะปรับจุดระดับน้ำ ตามมติของเจ้าของโครงการเมื่อ 30 ก.ย. 2569 (2026) ตัวเลขประชากรของ UNOSAT เป็นค่าประมาณผู้ได้รับผลกระทบ ซึ่งวัดต่างจากจำนวนผู้อยู่อาศัยในน้ำตามแบบจำลอง",
  "Largest modelled extent within 13-19 Sep ICT (the start of the UNOSAT window)":
    "ขอบเขตที่จำลองได้มากที่สุดในช่วง 13–19 ก.ย. (ต้นช่วงเวลาของ UNOSAT)",
  // Residents and low-confidence water.
  "Modelled residential population, not a census count or the 2024 population.":
    "ประชากรที่อยู่อาศัยตามแบบจำลอง ไม่ใช่ตัวเลขสำมะโนหรือประชากรปี 2567 (2024)",
  "Dead-flat or filled low ground in the elevation model: HAND ~ 0, so it reads as wet at almost any stage. Real low paddies or ponds are possible, but so are elevation artefacts.":
    "พื้นที่ต่ำที่ราบเรียบหรือถูกถมในแบบจำลองความสูง: HAND เกือบเป็นศูนย์ จึงแสดงว่าเปียกแทบทุกระดับน้ำ อาจเป็นนาหรือบ่อน้ำจริง แต่ก็อาจเป็นความคลาดเคลื่อนของข้อมูลความสูง",
  // Assumptions (the "Sources, assumptions and limits" panel).
  "Daily water surfaces are a HAND (height above nearest drainage) threshold reconstruction, not observations.":
    "ผิวน้ำรายวันเป็นการจำลองด้วยเกณฑ์ HAND (ความสูงเหนือร่องน้ำที่ใกล้ที่สุด) ไม่ใช่การสังเกตการณ์",
  "Stage keyframes (metres above the mapped channel) are illustrative values shaped to the event chronology; no gauge record was used. The stage is held at 0 through 9 Sep and rises through the night of 10 Sep.":
    "จุดกำหนดระดับน้ำ (เมตรเหนือร่องน้ำในแผนที่) เป็นค่าเพื่อการอธิบายที่ปรับให้สอดคล้องกับลำดับเหตุการณ์ ไม่ได้ใช้ข้อมูลจากสถานีวัดน้ำ ระดับน้ำคงที่ที่ 0 ตลอดวันที่ 9 ก.ย. และสูงขึ้นตลอดคืนวันที่ 10 ก.ย.",
  "The stage is the assumed Sai main-stem level at the Mae Sai bridges; tributaries rise to a fraction of the stage (see the next assumption). Real water levels still differed reach by reach.":
    "ระดับน้ำคือระดับสมมุติของลำน้ำหลักแม่น้ำสายที่สะพานแม่สาย ลำน้ำสาขาสูงขึ้นเพียงบางส่วนของระดับนี้ (ดูสมมติฐานถัดไป) ระดับน้ำจริงยังแตกต่างกันไปในแต่ละช่วงลำน้ำ",
  "Drainage channels are cells with at least 25 km² of upstream area on the 30 m Copernicus DSM; buildings and trees in the DSM bias HAND upward in town.":
    "ร่องน้ำคือช่องที่มีพื้นที่รับน้ำด้านเหนือน้ำอย่างน้อย 25 ตร.กม. บน Copernicus DSM ความละเอียด 30 ม. อาคารและต้นไม้ใน DSM ทำให้ค่า HAND ในเขตเมืองสูงกว่าจริง",
  "Roads are impassable when reconstructed depth reaches 0.3 m at any 10 m sample along a 120 m piece (per-sample depth factor; the exported depth factor f makes h + 0.3/f equal the earliest sample closure); river-channel samples on bridges are ignored.":
    "ถนนสัญจรไม่ได้เมื่อความลึกจำลองถึง 0.3 ม. ที่จุดตัวอย่างใดก็ตามซึ่งห่างกันทุก 10 ม. ตามถนนช่วงละ 120 ม. (ใช้ตัวคูณความลึกรายจุด ตัวคูณความลึก f ที่ส่งออกทำให้ h + 0.3/f เท่ากับเวลาที่จุดตัวอย่างแรกถูกปิด) ไม่นับจุดตัวอย่างในร่องน้ำบนสะพาน",
  "Bridge decks are not modelled: a bridge's road state reflects the ground at its approaches and beside it, so a raised deck can stay passable while the model shows the way impassable. Read a bridge's impassable hours as unknown.":
    "ไม่ได้จำลองพื้นสะพาน: สถานะถนนของสะพานสะท้อนระดับพื้นดินบริเวณคอสะพานและข้างสะพาน พื้นสะพานที่ยกสูงจึงอาจยังสัญจรได้แม้แบบจำลองแสดงว่าสัญจรไม่ได้ ให้ถือว่าชั่วโมงที่สะพานสัญจรไม่ได้เป็นค่าที่ไม่ทราบ",
  "Road pieces whose lowest HAND exceeds 4 m never flood under these keyframes and are omitted, except trunk, primary and secondary roads.":
    "ถนนช่วงที่ค่า HAND ต่ำสุดเกิน 4 ม. ไม่ถูกน้ำท่วมภายใต้จุดกำหนดระดับน้ำเหล่านี้จึงไม่แสดง ยกเว้นทางหลวงสายหลัก ถนนสายหลัก และถนนสายรอง",
  "The recession keyframes were re-tuned to the 16 September 06:16 ICT Sentinel-1 pass (best-fit stage 0.10 m), so that radar comparison is calibration-informed, not an independent check. It constrains the size of the late-recession extent only; the two radar passes use different orbit directions.":
    "จุดกำหนดระดับน้ำช่วงน้ำลดปรับใหม่ตามภาพ Sentinel-1 วันที่ 16 กันยายน 06:16 น. (ระดับน้ำที่เข้ากันดีที่สุด 0.10 ม.) การเทียบกับเรดาร์นี้จึงมีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ ภาพนี้ใช้กำหนดขนาดของขอบเขตน้ำช่วงท้ายของการลดลงเท่านั้น และภาพเรดาร์ทั้งสองภาพถ่ายจากทิศทางวงโคจรต่างกัน",
  "The onset is shaped by GISTDA's RADARSAT-2 figure for 10 Sep 18:15 (about 9.9 km² flooded in Mae Sai) and reports of an overnight surge; the 11 Sep 02:00 knot (2.5 m) is illustrative. The model's smallest non-zero extent (flat land within 5 cm of channel level) already exceeds 9.9 km², so the 18:15 knot is set to the closest level (0.1 m).":
    "ช่วงเริ่มท่วมปรับตามตัวเลขจาก RADARSAT-2 ของ GISTDA ณ 10 ก.ย. 18:15 น. (น้ำท่วมในแม่สายประมาณ 9.9 ตร.กม.) และรายงานน้ำหลากในช่วงกลางคืน จุดกำหนด 11 ก.ย. 02:00 น. (2.5 ม.) เป็นค่าเพื่อการอธิบาย ขอบเขตน้ำท่วมที่เล็กที่สุดที่ไม่เป็นศูนย์ของแบบจำลอง (พื้นที่ราบที่สูงจากระดับร่องน้ำไม่เกิน 5 ซม.) เกิน 9.9 ตร.กม. อยู่แล้ว จุดกำหนด 18:15 น. จึงตั้งไว้ที่ระดับที่ใกล้ที่สุด (0.1 ม.)",
  "Cells that drain off the hydrology domain before meeting a mapped channel use their outlet on the domain edge as the HAND reference (the edge lies outside the replay area).":
    "ช่องที่น้ำไหลออกนอกขอบเขตการคำนวณทางอุทกวิทยาก่อนถึงร่องน้ำในแผนที่ ใช้จุดทางออกที่ขอบเขตนั้นเป็นจุดอ้างอิงของ HAND (ขอบเขตนี้อยู่นอกพื้นที่การย้อนดู)",
  "Where flow routing leaves no path to a channel (large flats), HAND falls back to height above the nearest channel cell.":
    "ในพื้นที่ที่การคำนวณทิศทางการไหลไม่พบเส้นทางไปยังร่องน้ำ (พื้นที่ราบกว้าง) ค่า HAND ใช้ความสูงเหนือช่องร่องน้ำที่ใกล้ที่สุดแทน",
  "Stage varies along the river: each cell's water rise is scaled by the depth factor f = clip((A / A_Sai) ** 0.3, 0.35, 1), where A is the upstream area of its drainage channel and A_Sai the Sai main stem at the Mae Sai bridges (downstream hydraulic geometry). The Ruak east of Mae Sai is inside the hydrology domain (DEM tiles N20E099 + N20E100).":
    "ระดับน้ำแปรผันตามลำน้ำ: การสูงขึ้นของน้ำในแต่ละช่องคูณด้วยตัวคูณความลึก f = clip((A / A_Sai) ** 0.3, 0.35, 1) โดย A คือพื้นที่รับน้ำด้านเหนือน้ำของร่องน้ำของช่องนั้น และ A_Sai คือค่าของลำน้ำหลักแม่น้ำสายที่สะพานแม่สาย (เรขาคณิตชลศาสตร์ด้านท้ายน้ำ) แม่น้ำรวกทางตะวันออกของแม่สายอยู่ในขอบเขตการคำนวณทางอุทกวิทยา (แผ่นข้อมูล DEM N20E099 + N20E100)",
  "People in water uses WorldPop 2020 (100 m, spread evenly over 10 m cells); it is modelled residential population, not the 2024 population or tourists and traders at the border market.":
    "ประชากรในพื้นที่น้ำท่วมใช้ WorldPop 2020 (100 ม. กระจายเท่ากันลงในช่อง 10 ม.) เป็นประชากรที่อยู่อาศัยตามแบบจำลอง ไม่ใช่ประชากรปี 2567 (2024) หรือนักท่องเที่ยวและผู้ค้าที่ตลาดชายแดน",
  "Evacuation access uses the repo road graph and walking distance: a resident node has access when an open, dry shelter is within 2 km along roads still passable (about 30 minutes on foot); a road closes at 0.3 m of reconstructed depth and a shelter stops serving once water reaches it. Levels are evaluated every 0.05 m of stage.":
    "การเข้าถึงการอพยพใช้โครงข่ายถนนของโครงการและระยะเดิน: จุดผู้อยู่อาศัยเข้าถึงได้เมื่อมีที่พักพิงที่เปิดและแห้งภายใน 2 กม. ตามถนนที่ยังสัญจรได้ (เดินประมาณ 30 นาที) ถนนปิดเมื่อน้ำจำลองลึก 0.3 ม. และที่พักพิงหยุดใช้งานเมื่อน้ำถึง ประเมินทุก 0.05 ม. ของระดับน้ำ",
  "Shelter candidates are OpenStreetMap public buildings and grounds (schools, places of worship, government offices, community centres; OSM amenity=shelter huts are excluded). A candidate is eligible only if it keeps 0.5 m freeboard at the modelled peak and a road node lies within 400 m. Ranking is greedy maximal coverage of residents whose homes are wet at the peak, within 2 km walking on normal roads (pre-emptive evacuation); the late-evacuation share repeats the check on roads still open at 1.0 m stage.":
    "สถานที่ที่อาจใช้เป็นที่พักพิงคืออาคารและพื้นที่สาธารณะใน OpenStreetMap (โรงเรียน ศาสนสถาน หน่วยงานราชการ ศูนย์ชุมชน ไม่รวมศาลาที่พักประเภท amenity=shelter) สถานที่จะเข้าเกณฑ์เมื่อมีระยะพ้นน้ำ 0.5 ม. ที่ระดับสูงสุดของแบบจำลองและมีจุดถนนภายใน 400 ม. การจัดอันดับใช้วิธีละโมบเพื่อครอบคลุมผู้อยู่อาศัยที่บ้านเปียกที่ระดับสูงสุดให้ได้มากที่สุดภายในระยะเดิน 2 กม. บนถนนปกติ (อพยพล่วงหน้า) สัดส่วนการอพยพล่าช้าตรวจซ้ำบนถนนที่ยังเปิดที่ระดับน้ำ 1.0 ม.",
  "Shelter capacity = mapped OSM building footprint within the site x 0.5 usable share / 3.5 m² per person (Sphere minimum covered space); OSM building coverage in Mae Sai is sparse, so many capacities are unknown or underestimated.":
    "ความจุที่พักพิง = พื้นที่อาคารใน OSM ภายในสถานที่ × สัดส่วนที่ใช้ได้ 0.5 ÷ 3.5 ตร.ม. ต่อคน (พื้นที่ในร่มขั้นต่ำตามเกณฑ์ Sphere) ข้อมูลอาคารใน OSM ของแม่สายยังมีน้อย ความจุหลายแห่งจึงไม่ทราบหรือต่ำกว่าจริง",
  "The capacity-aware plan assigns residents of homes that flood at the modelled peak to eligible sites within the 2 km walk without exceeding a site's capacity. It gives two bounds: an unknown capacity counts as 0 (lower) or as the median estimate of its site kind (upper). Demand is an upper bound (many people stay with relatives) and the sites are candidates to verify.":
    "แผนแบบคิดความจุจัดให้ผู้อยู่อาศัยในบ้านที่ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลองไปยังสถานที่ที่เข้าเกณฑ์ภายในระยะเดิน 2 กม. โดยไม่เกินความจุของแต่ละแห่ง และให้ค่าสองขอบเขต: ความจุที่ไม่ทราบนับเป็น 0 (ขอบเขตล่าง) หรือใช้ค่ามัธยฐานของค่าประมาณของสถานที่ประเภทเดียวกัน (ขอบเขตบน) ความต้องการเป็นค่าขอบเขตบน (หลายคนไปพักกับญาติ) และสถานที่เหล่านี้เป็นสถานที่ที่ควรตรวจสอบ",
  "The two capacity bounds differ only in what a site without a mapped footprint is assumed to hold. Neither is a limit on who fits: a site with a footprint counts at its estimate in both, and that estimate is too low where buildings are unmapped.":
    "ขอบเขตความจุทั้งสองต่างกันเพียงว่าสมมุติให้สถานที่ที่ไม่มีขอบเขตอาคารในแผนที่รับได้เท่าใด ทั้งสองไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้ สถานที่ที่มีขอบเขตอาคารนับตามค่าประมาณทั้งสองขอบเขต และค่าประมาณนั้นต่ำกว่าจริงในบริเวณที่อาคารยังไม่ถูกทำแผนที่",
  "Plan robustness repeats the coverage ranking at 2.5 m, 3.5 m and 4.0 m: what-if levels around an illustrative peak, not return periods.":
    "การตรวจความคงทนของแผนจัดอันดับความครอบคลุมซ้ำที่ระดับ 2.5 ม. 3.5 ม. และ 4.0 ม. ซึ่งเป็นระดับน้ำสมมุติรอบ ๆ ระดับสูงสุดที่ใช้เพื่อการอธิบาย ไม่ใช่คาบการเกิดซ้ำ",
  // Capacity-aware plan and what-if levels: confidence reasons, source timestamps and the what-if label.
  "Capacity is a footprint estimate from sparse OpenStreetMap buildings, unverified, and unknown for most candidates; demand is a modelled upper bound; nothing was checked on the ground.":
    "ความจุเป็นค่าประมาณจากขอบเขตอาคารใน OpenStreetMap ซึ่งมีข้อมูลน้อย ยังไม่ได้ตรวจสอบ และไม่ทราบสำหรับสถานที่ส่วนใหญ่ ความต้องการเป็นค่าขอบเขตบนจากแบบจำลอง และยังไม่ได้ตรวจสอบสิ่งใดในพื้นที่",
  // The same reason once a local check has been returned: it stops saying that nothing was checked.
  "Capacity is a footprint estimate from sparse OpenStreetMap buildings, unverified, and unknown for most candidates; demand is a modelled upper bound; the local check that was returned is reported by role and is not used in these figures.":
    "ความจุเป็นค่าประมาณจากขอบเขตอาคารใน OpenStreetMap ซึ่งมีข้อมูลน้อย ยังไม่ได้ตรวจสอบ และไม่ทราบสำหรับสถานที่ส่วนใหญ่ ความต้องการเป็นค่าขอบเขตบนจากแบบจำลอง ผลการตรวจสอบในพื้นที่ที่ส่งกลับมาเป็นข้อมูลที่รายงานตามบทบาท และตัวเลขเหล่านี้ไม่ได้ใช้ผลดังกล่าว",
  // The local check of the shelter candidates (shown once a verification sheet has been returned).
  "One local check per site, reported by role and not audited by the project team.":
    "ตรวจสอบในพื้นที่หนึ่งครั้งต่อสถานที่ รายงานตามบทบาท และทีมโครงการไม่ได้ตรวจทาน",
  // The export pack's source timestamp (the downloads footer).
  "OSM extract 2026-07-09; WorldPop 2020; reported shelters compiled 2026-09-27; illustrative stage keyframes for 2024-09-09/2024-09-19 ICT":
    "ข้อมูล OSM 2026-07-09 · WorldPop 2020 · รวบรวมที่พักพิงที่มีรายงานเมื่อ 2026-09-27 · จุดกำหนดระดับน้ำเพื่อการอธิบายสำหรับ 2024-09-09/2024-09-19 เวลาประเทศไทย",
  "OSM extract 2026-07-09 (building footprints and sites); WorldPop 2020; reconstructed peak 2024-09-12 ICT":
    "ข้อมูล OSM 2026-07-09 (ขอบเขตอาคารและสถานที่) · WorldPop 2020 · ระดับน้ำสูงสุดที่จำลอง 2024-09-12 เวลาประเทศไทย",
  "The peak stage is illustrative (no gauge record); the levels show how the ranking moves if it were lower or higher.":
    "ระดับน้ำสูงสุดเป็นค่าเพื่อการอธิบาย (ไม่มีข้อมูลสถานีวัดน้ำ) ระดับเหล่านี้แสดงว่าการจัดอันดับเปลี่ยนไปอย่างไรหากระดับน้ำต่ำหรือสูงกว่านี้",
  "OSM extract 2026-07-09; WorldPop 2020; what-if design stages around the illustrative 2024-09-12 ICT peak":
    "ข้อมูล OSM 2026-07-09 · WorldPop 2020 · ระดับน้ำสมมุติรอบ ๆ ระดับสูงสุดเพื่อการอธิบายของวันที่ 2024-09-12 เวลาประเทศไทย",
  "What-if levels around an illustrative peak, not return periods.":
    "ระดับน้ำสมมุติรอบ ๆ ระดับสูงสุดที่ใช้เพื่อการอธิบาย ไม่ใช่คาบการเกิดซ้ำ",
  "VIIRS daily flood maps (375 m) are compared with the reconstruction only in clear-sky pixels at a nominal 13:30 ICT; they cannot see flooding under cloud or at street scale.":
    "แผนที่น้ำท่วมรายวัน VIIRS (375 ม.) เทียบกับการจำลองเฉพาะพิกเซลที่ท้องฟ้าโปร่ง ณ เวลาประมาณ 13:30 น. และมองไม่เห็นน้ำท่วมใต้เมฆหรือในระดับถนน",
  "Flash-flood velocity, debris and mud deposition are not modelled.":
    "ไม่ได้จำลองความเร็วของน้ำหลาก เศษวัสดุ และการทับถมของโคลน",
  "The Sentinel-2 water check counts water or saturated mud (MNDWI above 0) on the clear pixels of the 5 Sep and 15 Sep scenes, inside the district and outside mapped channels; its comparison with the model is indicative.":
    "การตรวจน้ำด้วยภาพ Sentinel-2 นับพื้นที่น้ำหรือโคลนอิ่มน้ำ (ค่า MNDWI มากกว่า 0) ในพิกเซลที่ไม่มีเมฆบังของภาพวันที่ 5 ก.ย. และ 15 ก.ย. เฉพาะในเขตอำเภอและนอกร่องน้ำในแผนที่ การเปรียบเทียบกับแบบจำลองเป็นเพียงข้อบ่งชี้",
  // Sentinel-2 water check (15 Sep): what it measures, how, and what it is consistent with.
  "MNDWI = (green - swir16) / (green + swir16) on surface reflectance (digital number / 10000, nothing subtracted). The 10 m green band is averaged onto the 20 m grid of the short-wave infrared band.":
    "MNDWI = (green - swir16) / (green + swir16) คำนวณจากค่าการสะท้อนที่พื้นผิว (ค่าดิจิทัล ÷ 10000 โดยไม่ลบค่าใด) แถบสีเขียวความละเอียด 10 ม. ถูกเฉลี่ยลงบนกริด 20 ม. ของแถบอินฟราเรดคลื่นสั้น",
  "A clear pixel counts as water or saturated mud when its MNDWI is above 0.":
    "พิกเซลที่ไม่มีเมฆบังนับเป็นน้ำหรือโคลนอิ่มน้ำเมื่อค่า MNDWI มากกว่า 0",
  "A pixel is clear when its scene classification is not no data (0), cloud shadow (3), cloud (8, 9) or thin cirrus (10), and both bands hold data.":
    "พิกเซลถือว่าไม่มีเมฆบังเมื่อการจำแนกฉาก (SCL) ไม่ใช่ไม่มีข้อมูล (0) เงาเมฆ (3) เมฆ (8, 9) หรือเมฆซีร์รัสบาง (10) และทั้งสองแถบมีข้อมูล",
  "Mapped drainage-channel cells are left out on both dates: the same out-of-channel rule as the model's flooded area. No land-cover map is used, so ponds and reservoirs count on both dates; the new-water figure leaves them out.":
    "ไม่นับช่องที่เป็นร่องน้ำในแผนที่ทั้งสองวัน ซึ่งเป็นเกณฑ์นอกร่องน้ำเดียวกับพื้นที่น้ำท่วมของแบบจำลอง ไม่ได้ใช้แผนที่สิ่งปกคลุมดิน บ่อน้ำและอ่างเก็บน้ำจึงถูกนับทั้งสองวัน แต่ตัวเลขน้ำที่เพิ่มขึ้นใหม่ไม่รวมแหล่งน้ำเหล่านี้",
  "The model figures are the modelled out-of-channel water at the acquisition time of the 15 Sep scene, counted in the pixels that scene saw clearly. The overlap ratio says how far the two areas coincide, not which one is right.":
    "ตัวเลขของแบบจำลองคือน้ำนอกร่องน้ำจากแบบจำลอง ณ เวลาถ่ายภาพของวันที่ 15 ก.ย. นับเฉพาะพิกเซลที่ภาพนั้นมองเห็นได้ชัด อัตราส่วนการซ้อนทับบอกว่าพื้นที่ทั้งสองตรงกันมากน้อยเพียงใด ไม่ได้บอกว่าฝ่ายใดถูก",
  "A positive MNDWI also flags saturated mud and wet sediment, so the area is water or saturated mud, not a flood extent. The scene classification can miss thin cloud and cloud shadow, and cloud hid part of the district on both dates. The comparison with the model is indicative only.":
    "ค่า MNDWI ที่เป็นบวกรวมถึงโคลนอิ่มน้ำและตะกอนเปียกด้วย พื้นที่นี้จึงเป็นน้ำหรือโคลนอิ่มน้ำ ไม่ใช่ขอบเขตน้ำท่วม การจำแนกฉากอาจพลาดเมฆบางและเงาเมฆ และเมฆบังพื้นที่อำเภอบางส่วนทั้งสองวัน การเปรียบเทียบกับแบบจำลองเป็นเพียงข้อบ่งชี้เท่านั้น",
  "The larger observed area is consistent with water or saturated mud left after the river fell; the terrain-only model cannot hold water once the river level drops.":
    "พื้นที่ที่สังเกตได้ซึ่งกว้างกว่าสอดคล้องกับน้ำหรือโคลนอิ่มน้ำที่ยังค้างอยู่หลังระดับแม่น้ำลดลง แบบจำลองที่ใช้เฉพาะภูมิประเทศไม่สามารถกักน้ำไว้ได้เมื่อระดับแม่น้ำลดลง",
  "A day later the VIIRS map shows less flood water than the model in its clear pixels, so the larger area on the day of the scene is consistent with saturated mud or short-lived water rather than lasting ponding.":
    "หนึ่งวันถัดมา แผนที่ VIIRS พบน้ำท่วมน้อยกว่าแบบจำลองในพิกเซลที่ท้องฟ้าโปร่ง พื้นที่ที่กว้างกว่าในวันที่ถ่ายภาพจึงสอดคล้องกับโคลนอิ่มน้ำหรือน้ำที่ค้างอยู่ช่วงสั้น ๆ มากกว่าน้ำขังที่คงอยู่นาน",
  // The reading as an earlier r4 bake worded it (it named a land cover that no input of the bake supports).
  "Water or saturated mud standing on fields after the river fell is consistent with the larger observed area; the terrain-only model cannot hold water once the river level drops.":
    "น้ำหรือโคลนอิ่มน้ำที่ยังค้างอยู่หลังระดับแม่น้ำลดลง สอดคล้องกับพื้นที่ที่สังเกตได้ซึ่งกว้างกว่า แบบจำลองที่ใช้เฉพาะภูมิประเทศไม่สามารถกักน้ำไว้ได้เมื่อระดับแม่น้ำลดลง",
  "One index threshold on two partly cloudy scenes, with no field check: a positive index also flags saturated mud and wet sediment, the scene classification can miss thin cloud and cloud shadow, and the ground under cloud was not seen.":
    "ใช้เกณฑ์ดัชนีค่าเดียวกับภาพสองภาพที่มีเมฆบางส่วน และไม่มีการตรวจภาคสนาม ค่าดัชนีที่เป็นบวกรวมถึงโคลนอิ่มน้ำและตะกอนเปียก การจำแนกฉากอาจพลาดเมฆบางและเงาเมฆ และมองไม่เห็นพื้นดินใต้เมฆ",
  "The eight Mae Sai subdistricts, on the replay's 10 m grid.":
    "8 ตำบลของอำเภอแม่สาย บนกริด 10 ม. ของการย้อนดู",
  // Limitations.
  "Not a real-time product or an official warning; for preparedness learning and post-event prioritisation only.":
    "ไม่ใช่ผลิตภัณฑ์เรียลไทม์หรือคำเตือนทางการ ใช้เพื่อการเรียนรู้ด้านการเตรียมพร้อมและการจัดลำดับความสำคัญหลังเกิดเหตุเท่านั้น",
  "No high-resolution satellite image exists for 10-14 September over Mae Sai in these inputs; VIIRS (375 m) was cloud-covered on 10-11 Sep and mostly cloud-covered on 12-14 Sep, so onset and peak extents are not observed.":
    "ข้อมูลชุดนี้ไม่มีภาพดาวเทียมความละเอียดสูงของแม่สายในวันที่ 10–14 กันยายน VIIRS (375 ม.) มีเมฆปกคลุมในวันที่ 10–11 ก.ย. และมีเมฆมากในวันที่ 12–14 ก.ย. จึงไม่มีการสังเกตขอบเขตน้ำช่วงเริ่มท่วมและช่วงสูงสุด",
  "Statistics cover only the modelled parts of the eight Mae Sai subdistricts; roads and facilities outside the model are excluded.":
    "ตัวเลขครอบคลุมเฉพาะส่วนที่จำลองของ 8 ตำบลในอำเภอแม่สาย ถนนและสถานที่นอกแบบจำลองไม่นับรวม",
  "No ponding or storage after the river falls: the terrain-only model dries every cell as soon as the assumed river level drops below it, so water or saturated mud left behind after the river falls is not reconstructed.":
    "ไม่จำลองน้ำขังหรือการกักเก็บน้ำหลังระดับแม่น้ำลดลง: แบบจำลองที่ใช้เฉพาะภูมิประเทศทำให้ทุกช่องแห้งทันทีที่ระดับแม่น้ำสมมุติลดต่ำกว่าช่องนั้น จึงไม่ได้จำลองน้ำหรือโคลนอิ่มน้ำที่ยังค้างอยู่หลังระดับแม่น้ำลดลง",
  // The same limitation as an earlier r4 bake worded it.
  "No ponding or storage after the river falls: the terrain-only model dries every cell as soon as the assumed river level drops below it, so water or saturated mud left standing on fields is not reconstructed.":
    "ไม่จำลองน้ำขังหรือการกักเก็บน้ำหลังระดับแม่น้ำลดลง: แบบจำลองที่ใช้เฉพาะภูมิประเทศทำให้ทุกช่องแห้งทันทีที่ระดับแม่น้ำสมมุติลดต่ำกว่าช่องนั้น จึงไม่ได้จำลองน้ำหรือโคลนอิ่มน้ำที่ยังค้างอยู่หลังระดับแม่น้ำลดลง",
  "Filled pits and dead-flat ground in the elevation model that end up less than 0.1 m above their channel (flagged in the raster's B channel) read as wet at almost any stage; they are shown as low-confidence water.":
    "หลุมที่ถูกถมและพื้นที่ราบเรียบในแบบจำลองความสูงที่สูงจากร่องน้ำไม่ถึง 0.1 ม. (ระบุไว้ในช่อง B ของภาพ) จะแสดงว่าเปียกแทบทุกระดับน้ำ จึงแสดงเป็นน้ำที่มีความเชื่อมั่นต่ำ",
  // Evidence envelope (r4): permitted use and what the source-timestamp span covers.
  "Preparedness learning, planning exercises and post-event prioritisation discussion in competition and preview builds. Not for emergency response, evacuation orders or any operational decision; not an official warning.":
    "ใช้เพื่อการเรียนรู้ด้านการเตรียมพร้อม การฝึกซ้อมวางแผน และการหารือจัดลำดับความสำคัญหลังเกิดเหตุ ในรุ่นสำหรับการแข่งขันและรุ่นทดลองเท่านั้น ไม่ใช้สำหรับการรับมือเหตุฉุกเฉิน คำสั่งอพยพ หรือการตัดสินใจเชิงปฏิบัติการใด ๆ และไม่ใช่คำเตือนทางการ",
  "Span of the dated event observations shown: from the Sentinel-2 image of 5 Sep 03:58 UTC to the end of the last HII rain hour (19 Sep 24:00 ICT). Sentinel-1 (6 and 15 Sep UTC) and VIIRS (10-18 Sep) fall inside it. Inputs dated outside the event (elevation 2011-2015, WorldPop 2020, boundaries 2022, OpenStreetMap 2026-07-09, reported shelters compiled 2026-09-27) are dated per evidence block and in sources.":
    "ช่วงเวลาของข้อมูลสังเกตการณ์ของเหตุการณ์ที่แสดง: ตั้งแต่ภาพ Sentinel-2 วันที่ 5 ก.ย. 03:58 UTC ถึงสิ้นชั่วโมงสุดท้ายของข้อมูลฝน สสน. (19 ก.ย. 24:00 น.) ภาพ Sentinel-1 (6 และ 15 ก.ย. ตามเวลา UTC) และ VIIRS (10–18 ก.ย.) อยู่ในช่วงนี้ ข้อมูลนำเข้าที่ลงวันที่นอกช่วงเหตุการณ์ (ความสูงภูมิประเทศ 2011–2015, WorldPop 2020, ขอบเขตการปกครอง 2022, OpenStreetMap 2026-07-09, ที่พักพิงที่มีรายงานรวบรวมเมื่อ 2026-09-27) ระบุวันที่ไว้ในแต่ละส่วนของหลักฐานและในรายการแหล่งข้อมูล",
  // Licence per input: terms, conditions of use and the status of product 4009.
  "Use under the Copernicus DEM licence terms, with the DLR and Airbus attribution.":
    "ใช้ตามเงื่อนไขสัญญาอนุญาต Copernicus DEM พร้อมแสดงที่มาของ DLR และ Airbus",
  "Use under the Copernicus Sentinel data terms, with the modified-data notice.":
    "ใช้ตามเงื่อนไขข้อมูล Copernicus Sentinel พร้อมข้อความแจ้งว่าข้อมูลถูกดัดแปลง",
  "Attribution and share-alike: files derived from the OpenStreetMap database stay under ODbL 1.0.":
    "ต้องแสดงที่มาและอนุญาตแบบเดียวกัน: ไฟล์ที่ได้จากฐานข้อมูล OpenStreetMap ยังอยู่ภายใต้ ODbL 1.0",
  "Attribution.": "ต้องแสดงที่มา",
  "Attribution to OCHA / HDX.": "ต้องแสดงที่มาว่า OCHA / HDX",
  "Shown with attribution; reuse beyond this page is not cleared.":
    "แสดงพร้อมที่มา การนำไปใช้ต่อนอกหน้านี้ยังไม่ได้รับอนุญาต",
  "Non-commercial use with attribution; keep rain values out of any combined table or export.":
    "ใช้ได้เฉพาะที่ไม่ใช่เชิงพาณิชย์พร้อมแสดงที่มา ไม่นำค่าฝนไปรวมในตารางหรือไฟล์ส่งออกรวม",
  "Facts quoted with their sources; coordinates matched to OpenStreetMap stay under ODbL 1.0.":
    "ข้อเท็จจริงที่อ้างพร้อมแหล่งที่มา พิกัดที่จับคู่กับ OpenStreetMap ยังอยู่ภายใต้ ODbL 1.0",
  "Team summary of public reporting, shown with its compile date.":
    "สรุปรายงานสาธารณะโดยทีมงาน แสดงพร้อมวันที่รวบรวม",
  "Quoted as reported, with a link to each source.":
    "อ้างตามที่รายงาน พร้อมลิงก์ไปยังแต่ละแหล่ง",
  "Attribution, share-alike and a change notice on every derived file; kept in its own folder.":
    "ไฟล์ที่ได้จากข้อมูลนี้ทุกไฟล์ต้องแสดงที่มา อนุญาตแบบเดียวกัน และระบุสิ่งที่เปลี่ยนแปลง โดยเก็บไว้ในโฟลเดอร์ของตนเอง",
  "Not yet shown; rights record pending owner confirmation.":
    "ยังไม่แสดง รอเจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูล",
  "Competition and preview builds, non-commercial, with the attributions listed in sources.":
    "ใช้ในรุ่นสำหรับการแข่งขันและรุ่นทดลอง ไม่ใช่เชิงพาณิชย์ พร้อมแสดงที่มาตามรายการแหล่งข้อมูล",
  "HII rain data are CC BY-NC: the replay as a whole is for non-commercial use, and rain values stay out of any combined table or export.":
    "ข้อมูลฝนของ สสน. ใช้สัญญาอนุญาต CC BY-NC การย้อนดูทั้งหมดจึงใช้ได้เฉพาะที่ไม่ใช่เชิงพาณิชย์ และไม่นำค่าฝนไปรวมในตารางหรือไฟล์ส่งออกรวม",
  "The VIIRS provider states no licence: the maps are shown with attribution, and reuse beyond this page is not cleared.":
    "ผู้ให้บริการ VIIRS ไม่ได้ระบุสัญญาอนุญาต แผนที่จึงแสดงพร้อมที่มา และการนำไปใช้ต่อนอกหน้านี้ยังไม่ได้รับอนุญาต",
  "OpenStreetMap-derived files (roads, facilities, shelter candidates and the access node positions) stay under ODbL 1.0: attribution and share-alike.":
    "ไฟล์ที่ได้จาก OpenStreetMap (ถนน สถานที่สำคัญ สถานที่ที่อาจใช้เป็นที่พักพิง และตำแหน่งจุดถนน) ยังอยู่ภายใต้ ODbL 1.0 ต้องแสดงที่มาและอนุญาตแบบเดียวกัน",
  "UNOSAT/GISTDA product 4009 (CC BY-SA 4.0) is not shown; it may appear only after the owners confirm the rights record.":
    "ผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA (CC BY-SA 4.0) ยังไม่แสดง จะแสดงได้หลังจากเจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลแล้วเท่านั้น",
  // Licence wording the project wrote itself. Published licence names ("CC BY 4.0", "ODbL 1.0") stay as published.
  "Project summary text": "ข้อความสรุปของโครงการ",
  "Cited figures with links; no data copied": "ตัวเลขที่อ้างอิงพร้อมลิงก์ ไม่ได้คัดลอกข้อมูล",
  "Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)":
    "ข้อเท็จจริงพร้อมการอ้างอิง พิกัดที่ได้จาก OSM © ผู้ร่วมสร้าง OpenStreetMap (ODbL)",
  "Facts with citations": "ข้อเท็จจริงพร้อมการอ้างอิง",
  "No licence stated by the provider": "ผู้ให้บริการไม่ได้ระบุสัญญาอนุญาต",
  "No licence stated by the provider; attribution given": "ผู้ให้บริการไม่ได้ระบุสัญญาอนุญาต จึงแสดงที่มาไว้",
  "NOAA JPSS Proving Ground product; no licence stated on the site, attribution given":
    "ผลิตภัณฑ์ของ NOAA JPSS Proving Ground เว็บไซต์ไม่ได้ระบุสัญญาอนุญาต จึงแสดงที่มาไว้",
  "Copernicus DEM licence (free, attribution)": "สัญญาอนุญาต Copernicus DEM (ใช้ได้โดยไม่มีค่าใช้จ่าย ต้องแสดงที่มา)",
  "Copernicus Sentinel data terms (free, full and open)": "เงื่อนไขข้อมูล Copernicus Sentinel (ใช้ได้โดยไม่มีค่าใช้จ่าย ครบถ้วนและเปิดกว้าง)",
  "CC BY-NC (per the HII open-data catalogue)": "CC BY-NC (ตามบัญชีข้อมูลเปิดของ สสน.)",
  // What was used, or already known, while the model was tuned.
  "Which external figures were used, or already known, while the stage keyframes and the depth factor were set. A figure used or known during tuning cannot serve as an independent check.":
    "ตัวเลขจากภายนอกใดบ้างที่ใช้หรือทราบอยู่แล้วขณะกำหนดจุดระดับน้ำและตัวคูณความลึก ตัวเลขที่ใช้หรือทราบขณะปรับแบบจำลองไม่อาจนับเป็นการตรวจสอบอิสระ",
  "GISTDA's RADARSAT-2 figure for 10 Sep 18:15 (9.9 km² flooded in Mae Sai) was used on purpose to set the onset stage knot (10 Sep 18:15, 0.1 m).":
    "ตัวเลขจาก RADARSAT-2 ของ GISTDA ณ 10 ก.ย. 18:15 น. (น้ำท่วมในแม่สาย 9.9 ตร.กม.) ถูกนำมาใช้โดยตั้งใจเพื่อกำหนดจุดระดับน้ำช่วงเริ่มท่วม (10 ก.ย. 18:15 น., 0.1 ม.)",
  "The Sentinel-1 pass of 16 Sep 06:16 ICT was used to re-tune the recession keyframes (best-fit stage 0.10 m), so the radar size comparison is calibration-informed, not an independent check.":
    "ภาพ Sentinel-1 วันที่ 16 ก.ย. 06:16 น. ถูกใช้ปรับจุดกำหนดระดับน้ำช่วงน้ำลดใหม่ (ระดับน้ำที่เข้ากันดีที่สุด 0.10 ม.) การเทียบขนาดกับเรดาร์จึงมีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ",
  "UNOSAT 3991 (about 70 km² over 13-19 Sep) was known while the stage keyframes were tuned, so its size comparison is calibration-informed, not independent.":
    "ทราบตัวเลขของ UNOSAT 3991 (ประมาณ 70 ตร.กม. ในช่วง 13–19 ก.ย.) อยู่แล้วขณะปรับจุดกำหนดระดับน้ำ การเทียบขนาดกับตัวเลขนี้จึงมีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ",
  "The VIIRS daily comparison was not used for tuning. It was first computed in the change of 29 Sep 2026 (commit 129ff03) that also moved the 10 Sep 18:15 knot from 0.12 m to 0.1 m, the model's closest level to GISTDA's figure. The build history does not record which came first within that change, so the comparison is not presented as an independent check.":
    "การเทียบกับ VIIRS รายวันไม่ได้ใช้ปรับแบบจำลอง การเทียบนี้คำนวณครั้งแรกในการแก้ไขเมื่อ 29 ก.ย. 2569 (2026) (commit 129ff03) ซึ่งเป็นการแก้ไขเดียวกับที่ย้ายจุดกำหนดระดับน้ำ 10 ก.ย. 18:15 น. จาก 0.12 ม. เป็น 0.1 ม. อันเป็นระดับของแบบจำลองที่ใกล้ตัวเลขของ GISTDA ที่สุด ประวัติการสร้างข้อมูลไม่ได้บันทึกว่าขั้นตอนใดเกิดก่อนในการแก้ไขนั้น จึงไม่นำการเทียบนี้มาแสดงเป็นการตรวจสอบอิสระ",
  "The depth factor f = clip((A / A_Sai) ** 0.3, 0.35, 1) was added on 28 Sep 2026, when the GISTDA and UNOSAT 3991 figures were already known. Its exponent and floor follow a hydraulic-geometry rule of thumb; the build history records no fit to an external figure.":
    "ตัวคูณความลึก f = clip((A / A_Sai) ** 0.3, 0.35, 1) เพิ่มเข้ามาเมื่อ 28 ก.ย. 2569 (2026) ซึ่งขณะนั้นทราบตัวเลขของ GISTDA และ UNOSAT 3991 แล้ว เลขชี้กำลังและค่าต่ำสุดเป็นไปตามหลักประมาณของเรขาคณิตชลศาสตร์ ประวัติการสร้างข้อมูลไม่มีบันทึกว่าปรับให้เข้ากับตัวเลขภายนอกใด",
  "The Sentinel-2 water check (MNDWI on the 5 Sep and 15 Sep scenes) was computed after the keyframes were final and was not used for tuning: the last keyframe change is commit 129ff03 of 29 Sep 2026, and the check entered the bake on 2 Oct 2026. The two true-colour images have been on the page since the first revision, so they were seen while the keyframes were set, but no water area had been derived from them.":
    "การตรวจน้ำด้วยภาพ Sentinel-2 (ค่า MNDWI ของภาพวันที่ 5 ก.ย. และ 15 ก.ย.) คำนวณหลังจากจุดกำหนดระดับน้ำเสร็จสมบูรณ์แล้ว และไม่ได้ใช้ปรับแบบจำลอง การแก้ไขจุดกำหนดระดับน้ำครั้งสุดท้ายคือ commit 129ff03 เมื่อ 29 ก.ย. 2569 (2026) ส่วนการตรวจนี้เข้าสู่ขั้นตอนสร้างข้อมูลเมื่อ 2 ต.ค. 2569 (2026) ภาพสีจริงทั้งสองภาพอยู่บนหน้านี้ตั้งแต่ข้อมูลรุ่นแรก ทีมงานจึงเห็นภาพเหล่านี้ขณะกำหนดจุดระดับน้ำ แต่ยังไม่เคยคำนวณพื้นที่น้ำจากภาพ",
  "No keyframe, depth-factor or terrain change may be tuned to VIIRS, the Sentinel-2 water check or product 4009 from here on; if one is, that comparison is relabelled calibration-informed.":
    "นับจากนี้จะไม่ปรับจุดกำหนดระดับน้ำ ตัวคูณความลึก หรือข้อมูลภูมิประเทศให้เข้ากับ VIIRS การตรวจน้ำด้วยภาพ Sentinel-2 หรือผลิตภัณฑ์ 4009 หากมีการปรับ การเทียบนั้นจะถูกระบุใหม่ว่ามีส่วนในการปรับแบบจำลอง",
  // The same rule as an earlier r4 bake worded it, before the Sentinel-2 water check existed.
  "No keyframe, depth-factor or terrain change may be tuned to VIIRS or product 4009 from here on; if one is, that comparison is relabelled calibration-informed.":
    "นับจากนี้จะไม่ปรับจุดกำหนดระดับน้ำ ตัวคูณความลึก หรือข้อมูลภูมิประเทศให้เข้ากับ VIIRS หรือผลิตภัณฑ์ 4009 หากมีการปรับ การเทียบนั้นจะถูกระบุใหม่ว่ามีส่วนในการปรับแบบจำลอง",
  // Sentences of revision r3 that r4 reworded, kept for a client that still holds the r3 manifest in its offline copy.
  "Water extents are a terrain-model reconstruction with illustrative stages; only the late-recession size is checked against radar, and spatial agreement there is weak.":
    "ขอบเขตน้ำจำลองจากแบบจำลองภูมิประเทศด้วยระดับน้ำสมมุติ ตรวจสอบกับเรดาร์ได้เฉพาะขนาดพื้นที่ช่วงน้ำลด และตำแหน่งยังสอดคล้องกันน้อย",
  "The 16 September 06:16 ICT Sentinel-1 pass constrains the size of the late-recession extent only; the two radar passes use different orbit directions.":
    "ภาพ Sentinel-1 วันที่ 16 กันยายน 06:16 น. ใช้กำหนดขนาดของขอบเขตน้ำช่วงท้ายของการลดลงเท่านั้น ภาพเรดาร์ทั้งสองภาพถ่ายจากทิศทางวงโคจรต่างกัน",
  "Season envelope; not shown until the CC BY-SA rights record is signed.":
    "ขอบเขตน้ำตลอดฤดู ยังไม่แสดงจนกว่าจะลงนามบันทึกสิทธิ์การใช้ข้อมูลตามสัญญาอนุญาต CC BY-SA",
  // The same statement as the r4 bakes worded it before product 4009 was shown.
  "The comparison with UNOSAT/GISTDA product 4009 was computed after the keyframes were final and was not used for tuning; product 4009 is not shown in this revision.":
    "การเทียบกับผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA คำนวณหลังจากจุดกำหนดระดับน้ำเสร็จสมบูรณ์แล้ว และไม่ได้ใช้ปรับแบบจำลอง ผลิตภัณฑ์ 4009 ยังไม่แสดงในข้อมูลรุ่นนี้",
  // --- The 2024 season envelope (UNOSAT and GISTDA product 4009), a scenario layer: manifest and statistics file. ---
  "Scenario (SCN-ENV): 2024 season envelope": "สถานการณ์จำลอง (SCN-ENV): ขอบเขตน้ำตลอดฤดูปี 2567 (2024)",
  "UNOSAT and GISTDA product 4009: accumulated water, August to October 2024 (the layer name ends 12 Oct; the product is described to 22 Oct); includes August and early-October water; not an observation for any replay day. Clipped to Mae Sai district and rasterised to the replay grid by FloodGuard.":
    "ผลิตภัณฑ์ 4009 ของ UNOSAT และ GISTDA: น้ำสะสมตั้งแต่สิงหาคมถึงตุลาคม 2567 (2024) (ชื่อชั้นข้อมูลสิ้นสุดวันที่ 12 ต.ค. ส่วนคำอธิบายผลิตภัณฑ์ครอบคลุมถึง 22 ต.ค.) รวมน้ำของเดือนสิงหาคมและต้นเดือนตุลาคมด้วย ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู FloodGuard ตัดให้เหลือเฉพาะอำเภอแม่สายและแปลงเป็นราสเตอร์บนกริดของการย้อนดู",
  "Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.":
    "ขอบเขตน้ำเบื้องต้นจากหน่วยงานที่ยังไม่ได้ตรวจสอบในพื้นที่จริง (ผลิตภัณฑ์ UNOSAT หมายเลข 4009 ร่วมกับ GISTDA; Field_Validation=0) ใช้ตามที่เผยแพร่ภายใต้สัญญาอนุญาต CC BY-SA 4.0 FloodGuard ก็ไม่ได้ตรวจสอบเช่นกัน",
  "Season envelope comparison (scenario; plausibility, not validation)":
    "การเทียบกับขอบเขตน้ำตลอดฤดู (สถานการณ์จำลอง; ดูความสมเหตุสมผล ไม่ใช่การยืนยันความถูกต้อง)",
  "Plausibility against a season envelope, not a validation. The envelope also holds August and early-October water and the modelled peak is illustrative, so the figures say where the two differ, not which one is right.":
    "เป็นการดูความสมเหตุสมผลเทียบกับขอบเขตน้ำตลอดฤดู ไม่ใช่การยืนยันความถูกต้อง ขอบเขตนี้รวมน้ำของเดือนสิงหาคมและต้นเดือนตุลาคมด้วย และระดับสูงสุดของแบบจำลองเป็นค่าเพื่อการอธิบาย ตัวเลขจึงบอกว่าทั้งสองต่างกันที่ใด ไม่ได้บอกว่าข้อมูลใดถูกต้อง",
  "The 2024 season envelope (UNOSAT/GISTDA product 4009) is a scenario layer with its own toggle: accumulated water from August to October 2024, never an observation for a replay day. Setting the modelled water beside it is a plausibility comparison, not a validation.":
    "ขอบเขตน้ำตลอดฤดูปี 2567 (2024) (ผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA) เป็นชั้นข้อมูลสถานการณ์จำลองที่เปิดปิดได้เอง แสดงน้ำสะสมตั้งแต่สิงหาคมถึงตุลาคม 2567 (2024) และไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู การนำน้ำจากแบบจำลองมาเทียบกับขอบเขตนี้เป็นการดูความสมเหตุสมผล ไม่ใช่การยืนยันความถูกต้อง",
  "The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.":
    "แบบจำลองพื้นผิวความละเอียด 30 ม. ทำให้ระดับพื้นดินในเขตสิ่งปลูกสร้างสูงกว่าจริง น้ำจากแบบจำลองและจำนวนผู้อยู่อาศัยในน้ำในเขตเมืองจึงน่าจะต่ำกว่าความเป็นจริง",
  "The comparison with UNOSAT/GISTDA product 4009 was computed after the keyframes were final and was not used for tuning. Recorded rule: no keyframe or elevation change is tuned to product 4009 afterwards; if one is, the comparison is relabelled as calibration.":
    "การเทียบกับผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA คำนวณหลังจากจุดกำหนดระดับน้ำเสร็จสมบูรณ์แล้ว และไม่ได้ใช้ปรับแบบจำลอง กฎที่บันทึกไว้: หลังจากนี้จะไม่ปรับจุดกำหนดระดับน้ำหรือข้อมูลความสูงให้เข้ากับผลิตภัณฑ์ 4009 หากมีการปรับ การเทียบนี้จะถูกระบุใหม่ว่าเป็นการปรับเทียบแบบจำลอง",
  "The modelled peak (illustrative stage, 12 Sep 2024)": "ระดับสูงสุดของแบบจำลอง (ระดับน้ำเพื่อการอธิบาย 12 ก.ย. 2567 (2024))",
  "Largest modelled extent within 13-19 Sep ICT": "ขอบเขตน้ำท่วมจากแบบจำลองที่กว้างที่สุดในช่วง 13–19 ก.ย. (เวลาประเทศไทย)",
  "Not computed: no land-cover map is among the replay's inputs, so the share of the envelope reached is not split by built-up land and cropland.":
    "ไม่ได้คำนวณ: ข้อมูลนำเข้าของการย้อนดูไม่มีแผนที่สิ่งปกคลุมดิน จึงไม่ได้แยกสัดส่วนของขอบเขตน้ำตลอดฤดูที่แบบจำลองไปถึงตามพื้นที่สิ่งปลูกสร้างและพื้นที่เพาะปลูก",
  "The envelope is used as provided: a preliminary agency product that was not checked in the field (Field_Validation=0). FloodGuard did not validate it.":
    "ใช้ขอบเขตนี้ตามที่เผยแพร่: เป็นผลิตภัณฑ์เบื้องต้นของหน่วยงานที่ยังไม่ได้ตรวจสอบในพื้นที่จริง (Field_Validation=0) FloodGuard ก็ไม่ได้ตรวจสอบเช่นกัน",
  "The envelope holds water mapped at some time from August to October 2024, with no date per patch. It includes August and early-October water, so it is not the water of 9 to 19 September.":
    "ขอบเขตนี้คือน้ำที่ทำแผนที่ไว้ในช่วงใดช่วงหนึ่งตั้งแต่สิงหาคมถึงตุลาคม 2567 (2024) โดยไม่มีวันที่กำกับแต่ละพื้นที่ จึงรวมน้ำของเดือนสิงหาคมและต้นเดือนตุลาคมด้วย และไม่ใช่น้ำของวันที่ 9 ถึง 19 กันยายน",
  "The modelled peak is illustrative (no gauge record), so the comparison says where the two differ, not which one is right.":
    "ระดับสูงสุดของแบบจำลองเป็นค่าเพื่อการอธิบาย (ไม่มีข้อมูลจากสถานีวัดน้ำ) การเทียบจึงบอกว่าทั้งสองต่างกันที่ใด ไม่ได้บอกว่าข้อมูลใดถูกต้อง",
  "Both masks are counted on the replay's 10 m grid inside the eight Mae Sai subdistricts and outside mapped drainage channels, the rule of every flooded area in the replay.":
    "นับพื้นที่ทั้งสองบนกริด 10 ม. ของการย้อนดู ภายใน 8 ตำบลของอำเภอแม่สายและนอกร่องน้ำในแผนที่ ซึ่งเป็นเกณฑ์เดียวกับพื้นที่น้ำท่วมทุกค่าในการย้อนดู",
  "Residents are WorldPop 2020 modelled estimates spread evenly over 10 m cells, the replay's own exposure rule: not a census count and not the 2024 population.":
    "จำนวนผู้อยู่อาศัยเป็นค่าประมาณจากแบบจำลอง WorldPop 2020 ที่กระจายเท่ากันลงบนช่อง 10 ม. ตามเกณฑ์เดียวกับการย้อนดู ไม่ใช่ข้อมูลสำมะโนประชากรและไม่ใช่ประชากรปี 2567 (2024)",
  "No land-cover map is among the replay's inputs, so the share of the envelope reached is not split by built-up land and cropland.":
    "ข้อมูลนำเข้าของการย้อนดูไม่มีแผนที่สิ่งปกคลุมดิน จึงไม่ได้แยกสัดส่วนของขอบเขตน้ำตลอดฤดูที่แบบจำลองไปถึงตามพื้นที่สิ่งปลูกสร้างและพื้นที่เพาะปลูก",
  "The comparison was computed after the stage keyframes were final and was not used for tuning.":
    "การเทียบนี้คำนวณหลังจากจุดกำหนดระดับน้ำเสร็จสมบูรณ์แล้ว และไม่ได้ใช้ปรับแบบจำลอง",
  "No keyframe or elevation change is tuned to product 4009 afterwards; if one is, this comparison is relabelled as calibration.":
    "หลังจากนี้จะไม่ปรับจุดกำหนดระดับน้ำหรือข้อมูลความสูงให้เข้ากับผลิตภัณฑ์ 4009 หากมีการปรับ การเทียบนี้จะถูกระบุใหม่ว่าเป็นการปรับเทียบแบบจำลอง",
  "A preliminary agency product that was not checked in the field, set beside an illustrative model: the envelope spans August to October with no date per patch, and the modelled stages come from no gauge record.":
    "เป็นผลิตภัณฑ์เบื้องต้นของหน่วยงานที่ยังไม่ได้ตรวจสอบในพื้นที่จริง นำมาเทียบกับแบบจำลองเพื่อการอธิบาย ขอบเขตนี้ครอบคลุมสิงหาคมถึงตุลาคมโดยไม่มีวันที่กำกับแต่ละพื้นที่ และระดับน้ำของแบบจำลองไม่ได้มาจากข้อมูลสถานีวัดน้ำ",
  "Not an observation for any replay day: the layer has no date per patch and no replay day selects it.":
    "ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู: ชั้นข้อมูลนี้ไม่มีวันที่กำกับแต่ละพื้นที่ และไม่มีวันใดในการย้อนดูที่เลือกแสดงชั้นข้อมูลนี้",
  "The layer's name ends 12 October 2024, while the product is described to 22 October 2024.":
    "ชื่อชั้นข้อมูลสิ้นสุดวันที่ 12 ตุลาคม 2567 (2024) ส่วนคำอธิบายผลิตภัณฑ์ครอบคลุมถึงวันที่ 22 ตุลาคม 2567 (2024)",
  "The third-party satellite imagery UNOSAT and GISTDA used to make the product is not relicensed by these files.":
    "ไฟล์เหล่านี้ไม่ได้ให้สิทธิ์ใหม่ในภาพถ่ายดาวเทียมของบุคคลที่สามที่ UNOSAT และ GISTDA ใช้จัดทำผลิตภัณฑ์",
  "UNOSAT and GISTDA do not endorse FloodGuard or its use of the product.":
    "UNOSAT และ GISTDA ไม่ได้รับรอง FloodGuard หรือการใช้ผลิตภัณฑ์นี้ของ FloodGuard",
  "Not an official warning and not legal advice; for preparedness learning and planning exercises only.":
    "ไม่ใช่การเตือนภัยอย่างเป็นทางการ และไม่ใช่คำแนะนำทางกฎหมาย ใช้เพื่อการเรียนรู้ด้านการเตรียมพร้อมและการฝึกซ้อมวางแผนเท่านั้น",
};

/** A manifest sentence in Thai when a translation is known, otherwise the English original marked as such (ids removed). */
export function localizedText(text: string, language: Language): { text: string; lang: Language } {
  const plain = plainManifestText(text);
  const thai = language === "th" ? KNOWN_THAI[plain] ?? thaiPattern(plain) : undefined;
  return thai ? { text: thai, lang: "th" } : { text: plain, lang: "en" };
}

const THAI_MONTHS: Readonly<Record<string, string>> = {
  Jan: "ม.ค.", Feb: "ก.พ.", Mar: "มี.ค.", Apr: "เม.ย.", May: "พ.ค.", Jun: "มิ.ย.", Jul: "ก.ค.", Aug: "ส.ค.", Sep: "ก.ย.", Oct: "ต.ค.", Nov: "พ.ย.", Dec: "ธ.ค.",
};
/** A manifest date such as "30 Sep 2026": day, English month abbreviation and CE year. */
const DATE = "(\\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \\d{4})";
/** "30 Sep 2026" as "30 ก.ย. 2569 (2026)": the Buddhist-era year with the CE year in brackets, as everywhere on the page. */
export function thaiManifestDate(text: string): string {
  const [day, month, year] = text.split(" ");
  return `${day} ${THAI_MONTHS[month] ?? month} ${Number(year) + 543} (${year})`;
}

/**
 * Manifest sentences whose dates (or quoted words) come from a record at bake time, e.g. a source timestamp
 * "compiled 2026-09-27" or the status of product 4009, which the bake reads from the rights record: pending or
 * confirmed but not shown in the earlier r4 bakes (a client may still hold one in its offline copy), and shown as a
 * season envelope scenario layer, with the confirmation date, from the bake that ships its files.
 */
const THAI_PATTERNS: readonly [RegExp, (match: RegExpMatchArray) => string][] = [
  [/^compiled (\d{4}-\d{2}-\d{2})$/, (m) => `รวบรวมเมื่อ ${m[1]}`],
  // Source timestamp of a returned local check of the shelter candidates: the range of the dates of the checks.
  [/^checks dated (\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2})$/, (m) => (m[1] === m[2] ? `ตรวจสอบเมื่อ ${m[1]}` : `ตรวจสอบระหว่าง ${m[1]} ถึง ${m[2]}`)],
  [new RegExp(`^Season envelope\\. The CC BY-SA 4\\.0 rights decision was signed on ${DATE} and UNOSAT replied "([^"]+)" \\(relayed by a project owner on ${DATE}\\); shown only after the owners confirm the rights record\\.$`),
    (m) => `ขอบเขตน้ำตลอดฤดู มติเรื่องสิทธิ์การใช้ข้อมูลตามสัญญาอนุญาต CC BY-SA 4.0 ลงนามเมื่อ ${thaiManifestDate(m[1])} และ UNOSAT ตอบว่า "${m[2]}" (เจ้าของโครงการแจ้งคำตอบนี้ต่อทีมเมื่อ ${thaiManifestDate(m[3])}) จะแสดงหลังจากเจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลแล้วเท่านั้น`],
  [new RegExp(`^Season envelope\\. The CC BY-SA 4\\.0 rights decision was signed on ${DATE} and UNOSAT replied "([^"]+)" \\(relayed by a project owner on ${DATE}\\); the owners confirmed the rights record on ${DATE}\\. Not shown in this revision\\.$`),
    (m) => `ขอบเขตน้ำตลอดฤดู มติเรื่องสิทธิ์การใช้ข้อมูลตามสัญญาอนุญาต CC BY-SA 4.0 ลงนามเมื่อ ${thaiManifestDate(m[1])} และ UNOSAT ตอบว่า "${m[2]}" (เจ้าของโครงการแจ้งคำตอบนี้ต่อทีมเมื่อ ${thaiManifestDate(m[3])}) เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ ${thaiManifestDate(m[4])} ยังไม่แสดงในข้อมูลรุ่นนี้`],
  [new RegExp(`^Not shown in this revision; the owners confirmed the rights record on ${DATE}\\.$`),
    (m) => `ยังไม่แสดงในข้อมูลรุ่นนี้ เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ ${thaiManifestDate(m[1])}`],
  [new RegExp(`^UNOSAT/GISTDA product 4009 \\(CC BY-SA 4\\.0\\) is not shown in this revision; the owners confirmed the rights record on ${DATE}\\.$`),
    (m) => `ผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA (CC BY-SA 4.0) ยังไม่แสดงในข้อมูลรุ่นนี้ เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ ${thaiManifestDate(m[1])}`],
  // Product 4009 shown as a season envelope scenario layer (the revision that ships its files).
  [new RegExp(`^Shown as a season envelope scenario layer; the owners confirmed the rights record on ${DATE}\\.$`),
    (m) => `แสดงเป็นชั้นข้อมูลสถานการณ์จำลองขอบเขตน้ำตลอดฤดู เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ ${thaiManifestDate(m[1])}`],
  [new RegExp(`^UNOSAT/GISTDA product 4009 \\(CC BY-SA 4\\.0\\) is shown as a season envelope scenario layer: its derived files keep their own folder, credit, licence and change notice; the owners confirmed the rights record on ${DATE}\\.$`),
    (m) => `ผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA (CC BY-SA 4.0) แสดงเป็นชั้นข้อมูลสถานการณ์จำลองขอบเขตน้ำตลอดฤดู ไฟล์ที่ดัดแปลงจากผลิตภัณฑ์นี้เก็บในโฟลเดอร์ของตนเอง พร้อมเครดิต สัญญาอนุญาต และประกาศการเปลี่ยนแปลง เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ ${thaiManifestDate(m[1])}`],
  [new RegExp(`^Season envelope\\. The CC BY-SA 4\\.0 rights decision was signed on ${DATE} and UNOSAT replied "([^"]+)" \\(relayed by a project owner on ${DATE}\\); the owners confirmed the rights record on ${DATE}\\. Shown from this revision as a scenario layer\\.$`),
    (m) => `ขอบเขตน้ำตลอดฤดู มติเรื่องสิทธิ์การใช้ข้อมูลตามสัญญาอนุญาต CC BY-SA 4.0 ลงนามเมื่อ ${thaiManifestDate(m[1])} และ UNOSAT ตอบว่า "${m[2]}" (เจ้าของโครงการแจ้งคำตอบนี้ต่อทีมเมื่อ ${thaiManifestDate(m[3])}) เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ ${thaiManifestDate(m[4])} แสดงเป็นชั้นข้อมูลสถานการณ์จำลองตั้งแต่ข้อมูลรุ่นนี้`],
];
function thaiPattern(text: string): string | undefined {
  for (const [pattern, render] of THAI_PATTERNS) {
    const match = text.match(pattern);
    if (match) return render(match);
  }
  return undefined;
}

/** English (transliterated) labels for the named roads in the OpenStreetMap extract; Thai stays in brackets. */
export const ROAD_NAMES_EN: Readonly<Record<string, string>> = {
  "ถนนพหลโยธิน": "Phahonyothin Rd (Hwy 1)",
  "ถนนเลี่ยงเมืองแม่สาย": "Mae Sai bypass",
  "ถนนห้วยไคร้ - ห้วยน้ำริน": "Huai Khrai – Huai Nam Rin Rd",
  "ถนนฤทธิประศาสน์": "Ritthiprasat Rd",
  "ถนนเหมืองแดง": "Mueang Daeng Rd",
};

const THAI_SCRIPT = /[฀-๿]/;
const LATIN_LETTER = /[A-Za-z]/;

/** True when a name is written in Thai script only (no Latin letters), so English readers need a label beside it. */
export const thaiOnly = (name: string): boolean => THAI_SCRIPT.test(name) && !LATIN_LETTER.test(name);

/**
 * A road name for the page language: in English, the known English label with the Thai name in brackets, or the
 * name as mapped; in Thai, the name as mapped.
 */
export function roadNameText(name: string, language: Language): { primary: string; secondary: string | null } {
  const english = ROAD_NAMES_EN[name];
  if (language === "th" || !english) return { primary: name, secondary: null };
  return { primary: english, secondary: name };
}

/** English type of a Thai-script place name from its leading word ("วัด…" is a temple), or null. */
const THAI_NAME_TYPES: readonly [RegExp, string][] = [
  [/^มัสยิด/, "Mosque"],
  [/^(โบสถ์|คริสตจักร)/, "Church"],
  [/^(วัด|สำนักสงฆ์|พระธาตุ)/, "Temple"],
  [/^มูลนิธิ/, "Foundation"],
  [/^(โรงเรียน|ศูนย์พัฒนาเด็กเล็ก)/, "School"],
  [/^(สำนักงาน)?(องค์การบริหารส่วนตำบล|อบต\.)/, "Subdistrict Administrative Organisation"],
  [/^(สำนักงาน)?เทศบาล/, "Municipality office"],
  [/^ที่ว่าการอำเภอ/, "District office"],
  [/^(โรงพยาบาล|รพ\.สต\.|สถานีอนามัย)/, "Health facility"],
  [/^(ศาลา|หอประชุม|ศูนย์)/, "Community hall"],
];

export function thaiNameType(name: string): string | null {
  const trimmed = name.trim();
  for (const [pattern, label] of THAI_NAME_TYPES) if (pattern.test(trimmed)) return label;
  return null;
}

/**
 * A place name for the page language. In English a Thai-only name gets an English type label first
 * ("Mosque · มัสยิด…"), from its leading word or else `fallbackType`; every other name is kept as mapped.
 */
export function placeNameText(name: string, language: Language, fallbackType: string): string {
  const trimmed = name.trim();
  if (language !== "en" || !thaiOnly(trimmed)) return trimmed;
  return `${thaiNameType(trimmed) ?? fallbackType} · ${trimmed}`;
}

// --- Glossary: short definitions behind the page's technical terms ------------------------------

export type GlossaryId = "stage" | "hand" | "freeboard" | "road_nodes" | "t1" | "low_confidence";

/** Term and one-sentence definition in both languages; the page shows them on hover or focus and in "How to read". */
export const GLOSSARY: Readonly<Record<GlossaryId, { term: { en: string; th: string }; definition: { en: string; th: string } }>> = {
  stage: {
    term: { en: "Stage", th: "ระดับน้ำ" },
    definition: {
      en: "The assumed river level at the Mae Sai border bridges, in metres above the mapped channel. It is illustrative, not a gauge reading.",
      th: "ระดับแม่น้ำสมมุติที่สะพานข้ามแดนแม่สาย เป็นเมตรเหนือร่องน้ำในแผนที่ เป็นค่าเพื่อการอธิบาย ไม่ใช่ค่าจากสถานีวัดน้ำ",
    },
  },
  hand: {
    term: { en: "HAND", th: "HAND" },
    definition: {
      en: "Height above nearest drainage: how high each 10 m cell of terrain sits above the stream it drains to. A cell is shown wet when the assumed stage there rises above it.",
      th: "ความสูงเหนือร่องน้ำที่ใกล้ที่สุด: ภูมิประเทศแต่ละช่อง 10 ม. สูงกว่าลำน้ำที่ไหลลงไปเท่าใด ช่องจะแสดงว่าเปียกเมื่อระดับน้ำสมมุติ ณ ที่นั้นสูงกว่าค่านี้",
    },
  },
  freeboard: {
    term: { en: "Freeboard", th: "ระยะพ้นน้ำ" },
    definition: {
      en: "How far a site stands above the modelled water surface at the peak. The plan only uses sites with at least the required margin.",
      th: "ความสูงของสถานที่เหนือผิวน้ำจำลองที่ระดับสูงสุด แผนนี้ใช้เฉพาะสถานที่ที่สูงกว่าผิวน้ำอย่างน้อยตามเกณฑ์",
    },
  },
  road_nodes: {
    term: { en: "Road nodes", th: "จุดถนน" },
    definition: {
      en: "Points on the OpenStreetMap road network. Residents of each population-grid cell are counted at a nearby node, so walking distances follow the roads.",
      th: "จุดบนโครงข่ายถนนของ OpenStreetMap ผู้อยู่อาศัยในแต่ละช่องของกริดประชากรนับรวมที่จุดใกล้เคียง ระยะเดินจึงวัดตามถนน",
    },
  },
  t1: {
    term: { en: "T1 scenario", th: "สถานการณ์จำลองระดับ T1" },
    definition: {
      en: "A planning scenario computed on the reconstructed water with stated assumptions: a model result, not observed evacuation outcomes.",
      th: "สถานการณ์เพื่อการวางแผนที่คำนวณจากน้ำที่จำลองขึ้นตามสมมติฐานที่ระบุ เป็นผลจากแบบจำลอง ไม่ใช่ผลการอพยพที่สังเกตได้จริง",
    },
  },
  low_confidence: {
    term: { en: "Low-confidence water", th: "น้ำที่มีความเชื่อมั่นต่ำ" },
    definition: {
      en: "Filled pits and dead-flat ground less than 0.1 m above its channel in the elevation model. It reads as wet at almost any stage, so it may be real low paddies or ponds, or an elevation artefact.",
      th: "หลุมที่ถูกถมและพื้นที่ราบเรียบที่สูงจากร่องน้ำไม่ถึง 0.1 ม. ในแบบจำลองความสูง จะแสดงว่าเปียกแทบทุกระดับน้ำ จึงอาจเป็นนาหรือบ่อน้ำที่ต่ำจริง หรือเป็นความคลาดเคลื่อนของข้อมูลความสูง",
    },
  },
};
export const GLOSSARY_ORDER: readonly GlossaryId[] = ["stage", "hand", "low_confidence", "road_nodes", "t1", "freeboard"];
