# floodguard_export: README_licences.txt
# title: Licences, attributions and reading notes of the export pack (read this first)
# title_th: สัญญาอนุญาต การแสดงที่มา และข้อควรรู้ในการอ่านชุดไฟล์ส่งออก (โปรดอ่านก่อน)
# tier: T1 scenario (model) replay of a reconstructed 2024 event for preparedness planning and exercises; illustrative stage keyframes; not a forecast, not an observed closure record, not an official warning; non_operational; accepted_* null
# tier_th: การย้อนดูสถานการณ์จำลองระดับ T1 (แบบจำลอง) ของเหตุการณ์ปี 2567 (2024) ที่จำลองขึ้นใหม่ เพื่อการวางแผนเตรียมความพร้อมและการฝึกซ้อม ใช้จุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่การพยากรณ์ ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง ไม่ใช่การเตือนภัยอย่างเป็นทางการ ไม่ใช้ในการปฏิบัติการ และไม่มีคะแนนหรือระดับการดำเนินการที่ยอมรับ (accepted_* เป็น null)
# operational_status: non_operational
# confidence_class: low
# confidence_reason: The tables come from a terrain-model reconstruction with illustrative stages, WorldPop 2020 residents, OpenStreetMap roads and sites, and unverified capacity estimates; nothing was checked on the ground.
# confidence_reason_th: ตารางมาจากการจำลองด้วยแบบจำลองภูมิประเทศและระดับน้ำสมมุติ ผู้อยู่อาศัยตาม WorldPop 2020 ถนนและสถานที่จาก OpenStreetMap และค่าประมาณความจุที่ยังไม่ได้ตรวจสอบ ยังไม่มีการตรวจสอบในพื้นที่
# lanes: REP, SCN
# source_timestamp: OpenStreetMap extract 2026-07-09; WorldPop 2020; reported shelters compiled 2026-09-27; illustrative stage keyframes for 2024-09-09/2024-09-19 ICT
# generated_at: 2026-10-03T17:47:00+07:00
# generated_by: scripts/build_mae_sai_flood_timeline.py
# study: mae-sai-2024-flood-timeline r4
# accepted: accepted_fpps=null; accepted_action_class=null (no priority score and no action class is computed)
# licence: ODbL 1.0 (https://opendatacommons.org/licenses/odbl/1-0/): OpenStreetMap-derived, attribution and share-alike
# licence_th: ODbL 1.0: ดัดแปลงจาก OpenStreetMap ต้องแสดงที่มาและเผยแพร่งานดัดแปลงภายใต้สัญญาอนุญาตเดียวกัน
# attribution: © OpenStreetMap contributors; FloodGuard desk research of public reporting, sources linked per site; © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA; WorldPop (www.worldpop.org), University of Southampton; OCHA / HDX Thailand COD-AB
# licence_inputs: OpenStreetMap roads and candidate facilities (Geofabrik extract): ODbL 1.0; Shelters reported in use in September 2024 (FloodGuard desk research): Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100): Copernicus DEM licence (free, attribution); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020): CC BY 4.0; HDX Thailand COD-AB subdistrict boundaries v01: CC BY-IGO
# not_included: No HII rain values (CC BY-NC), nothing from a source without a stated licence and nothing from UNOSAT/GISTDA product 4009 is in this file.
# not_included_th: ไฟล์นี้ไม่มีค่าปริมาณฝนของ สสน. (CC BY-NC) ไม่มีข้อมูลจากแหล่งที่ไม่ระบุสัญญาอนุญาต และไม่มีข้อมูลใดจากผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA
# assumption_1: The water is a HAND terrain-model reconstruction driven by illustrative stage keyframes (no gauge record was used): modelled, not observed.
# assumption_1_th: น้ำเป็นการจำลองจากแบบจำลองภูมิประเทศ HAND ด้วยจุดกำหนดระดับน้ำเพื่อการอธิบาย (ไม่ได้ใช้ข้อมูลจากสถานีวัดน้ำ) เป็นค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้
# assumption_2: Hours are replay hours on an hourly grid: hour 0 is 9 Sep 2024 00:00 ICT (UTC+7) and hour 263 is 19 Sep 2024 23:00; the assumed stage is sampled at the start of each hour.
# assumption_2_th: ชั่วโมงคือชั่วโมงของการย้อนดูแบบรายชั่วโมง ชั่วโมง 0 คือ 9 ก.ย. 2567 (2024) 00:00 น. เวลาประเทศไทย (UTC+7) และชั่วโมง 263 คือ 19 ก.ย. 2567 (2024) 23:00 น. ใช้ระดับน้ำสมมุติ ณ ต้นชั่วโมง
# input_receipt: docs/mae_sai_timeline_r4_input_receipt.json lists every input file of the bake with its SHA-256 (also timeline.json input_sha256); input_set_sha256=d56c09f9d9c9551eda1e3b6fbfbff145e0d1358ad7faeec9b8c0612657f75110
# git_commit: null: a file cannot hold the hash of the commit that adds it; git log -1 --format=%H -- apps/web/public/studies/mae-sai-2024-timeline/r4/exports/README_licences.txt

FLOODGUARD MAE SAI SEPTEMBER 2024 REPLAY: EXPORT PACK
ชุดไฟล์ส่งออกของการย้อนดูน้ำท่วมแม่สาย กันยายน 2567 (2024) โดย FloodGuard

1. WHAT THIS IS / ไฟล์ชุดนี้คืออะไร

Tables, one map layer and one per-subdistrict summary written from a model replay of the September 2024 flood in Mae Sai
District. They are for preparedness planning and exercises. Every table is modelled, not observed: it is not a forecast,
not an observed closure record and not an official warning, and it must not be used for emergency response or evacuation
orders.
Confidence is low and nothing was checked on the ground.

ตาราง ชั้นข้อมูลแผนที่หนึ่งชั้น และสรุปรายตำบลหนึ่งไฟล์ที่เขียนจากการย้อนดูด้วยแบบจำลองของเหตุการณ์น้ำท่วมอำเภอแม่สายเดือนกันยายน 2567 (2024)
ใช้สำหรับการวางแผนเตรียมความพร้อมและการฝึกซ้อม ทุกตารางเป็นค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้ ไม่ใช่การพยากรณ์
ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง และไม่ใช่การเตือนภัยอย่างเป็นทางการ ห้ามใช้ในการตอบสนองเหตุฉุกเฉินหรือการสั่งอพยพ
ความเชื่อมั่นอยู่ในระดับต่ำ และยังไม่มีการตรวจสอบในพื้นที่

Bridges: the deck of a bridge is not modelled. In the road table a row with bridge_flag = yes reflects the ground at the
bridge's approaches, so read its hours as unknown. Capacity bounds: neither the lower nor the upper bound is a limit on
who fits; a footprint estimate can be too low where buildings are unmapped.

สะพาน: ไม่ได้จำลองพื้นสะพาน ในตารางถนน แถวที่ bridge_flag = yes สะท้อนระดับพื้นดินบริเวณคอสะพาน ให้ถือว่าชั่วโมงของแถวนั้นเป็นค่าที่ไม่ทราบ
ขอบเขตความจุ: ทั้งขอบเขตล่างและขอบเขตบนไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้ ค่าประมาณจากขอบเขตอาคารอาจต่ำกว่าจริงในบริเวณที่อาคารยังไม่ถูกทำแผนที่

2. FILES / รายการไฟล์

shelter_plan_reported_2024.csv
  Shelters reported in use in Mae Sai in September 2024, with a model check of each located site (not an official register)
  ที่พักพิงที่มีรายงานว่าใช้ในแม่สายเดือนกันยายน 2567 (2024) พร้อมผลเทียบกับแบบจำลองของสถานที่ที่ระบุตำแหน่งได้ (ไม่ใช่ทะเบียนทางการ)
  28,398 bytes; 19 rows; 35 provenance lines before the column header; SHA-256 baccab26efd83583efed97203557055a3e6246323a6b354e4de58bac3b871d94
  Lanes: REP, SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

shelter_plan_k.csv
  Modelled shelter coverage ranking, sites 1 to N: a plan of any size is its first rows (candidates to verify)
  การจัดอันดับความครอบคลุมของที่พักพิงตามแบบจำลอง ลำดับ 1 ถึง N แผนขนาดใดก็ตามคือแถวแรกตามจำนวนนั้น (สถานที่ที่ควรตรวจสอบ)
  13,604 bytes; 12 rows; 38 provenance lines before the column header; SHA-256 8fc514d185351607c37ff3fc795ddab0789bf4eb6b348c19cb808323e5ed313a
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

shelter_plan_capacitated.csv
  Capacity-aware shelter ranking under two capacity bounds: who fits (candidates to verify)
  การจัดอันดับที่พักพิงแบบคิดความจุภายใต้ขอบเขตล่างและขอบเขตบน: รองรับได้กี่คน (สถานที่ที่ควรตรวจสอบ)
  19,081 bytes; 25 rows; 39 provenance lines before the column header; SHA-256 3b815f3b08ec92db8f6fd845bd3ce553301a6367e164495ee665b3b596d42c86
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

shelter_sites.geojson
  Shelter sites as points: every modelled candidate and every located site reported in use in September 2024
  ตำแหน่งที่พักพิงแบบจุด: สถานที่ที่เป็นไปได้ทุกแห่งตามแบบจำลอง และสถานที่ที่มีรายงานว่าใช้ในเดือนกันยายน 2567 (2024) ที่ระบุตำแหน่งได้
  99,373 bytes; 128 features; SHA-256 e09dcecbc041fd946b626b48190d0c9911b80e36250e4b999c5a28775b7e7b12
  Lanes: SCN, REP. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)).

modelled_road_inundation_by_hour.csv
  Modelled road inundation by hour, one row per OpenStreetMap way (modelled, not observed)
  ถนนที่น้ำท่วมตามแบบจำลองรายชั่วโมง หนึ่งแถวต่อหนึ่งเส้นทางใน OpenStreetMap (ค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้)
  346,104 bytes; 3,478 rows; 39 provenance lines before the column header; SHA-256 a899fc24c87ec4100a56f54bea9b61e1c2a23fe20cfb045fb259dc9c051d50f4
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); HDX Thailand COD-AB subdistrict boundaries v01 (CC BY-IGO).

modelled_access_loss_by_hour.csv
  Modelled loss of walking access to a shelter by hour, one row per subdistrict and replay hour
  การสูญเสียการเข้าถึงที่พักพิงด้วยการเดินตามแบบจำลองรายชั่วโมง หนึ่งแถวต่อตำบลและชั่วโมงของการย้อนดู
  241,197 bytes; 2,112 rows; 38 provenance lines before the column header; SHA-256 b319c639934c37ce18a0d2a2dfdb0efa0c76143509f2de4a77a8ab11e40fffec
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); HDX Thailand COD-AB subdistrict boundaries v01 (CC BY-IGO); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)).

shelter_candidate_verification_sheet.csv
  Shelter-candidate verification sheet: a blank checklist for a local checker (no check has been conducted)
  แบบตรวจสอบสถานที่ที่อาจใช้เป็นที่พักพิง: รายการตรวจที่ยังว่างสำหรับผู้ตรวจสอบในพื้นที่ (ยังไม่มีการตรวจสอบ)
  31,025 bytes; 95 rows; 47 provenance lines before the column header; SHA-256 86af04b69f3a24af1ec72b9d40416c31aa23dc14d5d008fc3fa55290023a5258
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

tambon_replay_summary.json
  Per-subdistrict replay summary at the modelled peak: water, residents, roads and walking access (modelled, not observed)
  สรุปผลการย้อนดูรายตำบล ณ ระดับน้ำสูงสุดตามแบบจำลอง: น้ำ ผู้อยู่อาศัย ถนน และการเดินถึงที่พักพิง (ค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้)
  99,614 bytes; 8 records; SHA-256 c055b0d7a282e99d6f002e6a216764f0f4335d02d6941bde040416c3f0f4ede2
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); HDX Thailand COD-AB subdistrict boundaries v01 (CC BY-IGO); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)).

3. LICENCE AND ATTRIBUTION / สัญญาอนุญาตและการแสดงที่มา

Every file in this folder is derived from the OpenStreetMap database and is made available under the Open Database License
(ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/
You may copy, share and adapt the files if you keep the attributions below and offer any adapted database under the same
licence. Each file has one licence lineage: OpenStreetMap (share-alike) plus the attribution-only inputs listed for it.

ทุกไฟล์ในโฟลเดอร์นี้ดัดแปลงจากฐานข้อมูล OpenStreetMap และเผยแพร่ภายใต้สัญญาอนุญาต Open Database License (ODbL) 1.0
ท่านคัดลอก เผยแพร่ และดัดแปลงไฟล์ได้ หากคงข้อความแสดงที่มาด้านล่างไว้ และเผยแพร่ฐานข้อมูลที่ดัดแปลงภายใต้สัญญาอนุญาตเดียวกัน
แต่ละไฟล์มีสายสัญญาอนุญาตเดียว คือ OpenStreetMap (ต้องใช้สัญญาอนุญาตแบบเดียวกัน) ร่วมกับข้อมูลที่กำหนดเพียงให้แสดงที่มาตามที่ระบุไว้ของไฟล์นั้น

Attributions to keep / ข้อความแสดงที่มาที่ต้องคงไว้:
  - OpenStreetMap roads and candidate facilities (Geofabrik extract): ODbL 1.0. © OpenStreetMap contributors.
  - Shelters reported in use in September 2024 (FloodGuard desk research): Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL). FloodGuard desk research of public reporting, sources linked per site.
  - Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100): Copernicus DEM licence (free, attribution). © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA.
  - WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020): CC BY 4.0. WorldPop (www.worldpop.org), University of Southampton.
  - HDX Thailand COD-AB subdistrict boundaries v01: CC BY-IGO. OCHA / HDX Thailand COD-AB.
  - Model and tables: FloodGuard Thailand, Mae Sai September 2024 flood replay (terrain-model reconstruction).

4. WHAT IS NOT IN THIS FOLDER / สิ่งที่ไม่มีในโฟลเดอร์นี้

  - No rain values. The HII rain gauge data shown on the replay page are CC BY-NC and stay out of every table here.
  - Nothing from a source without a stated licence (the VIIRS daily flood maps shown on the page).
  - Nothing from UNOSAT/GISTDA product 4009.
  - No listed capacity from a shelter register, no occupancy count and no personal data.
  - No Flood Preparedness Priority Score and no action class: the replay computes neither.

  - ไม่มีค่าปริมาณฝน ข้อมูลสถานีวัดฝนของ สสน. ที่แสดงในหน้าการย้อนดูใช้สัญญาอนุญาต CC BY-NC จึงไม่อยู่ในตารางใดในโฟลเดอร์นี้
  - ไม่มีข้อมูลจากแหล่งที่ไม่ระบุสัญญาอนุญาต (แผนที่น้ำท่วมรายวันของ VIIRS ที่แสดงในหน้าเว็บ)
  - ไม่มีข้อมูลใดจากผลิตภัณฑ์ 4009 ของ UNOSAT/GISTDA
  - ไม่มีความจุจากทะเบียนที่พักพิง ไม่มีจำนวนผู้เข้าพัก และไม่มีข้อมูลส่วนบุคคล
  - ไม่มีคะแนนลำดับความสำคัญด้านการเตรียมความพร้อมรับน้ำท่วม และไม่มีระดับการดำเนินการ การย้อนดูไม่ได้คำนวณทั้งสองอย่าง

5. HOW TO OPEN THE FILES / วิธีเปิดไฟล์

The CSV files are UTF-8 with a byte-order mark, so Excel shows the Thai text correctly when you open them directly. Each
CSV starts with provenance lines (the first cell starts with #): they say what the table is and is not, and they stay
with the table when it is forwarded. The second line gives their number. The column header follows; each header cell is
the English key and then the Thai label in brackets. In QGIS (Add Delimited Text Layer) set 'Number of header lines to
discard' to that number; in pandas pass skiprows. The GeoJSON file opens in QGIS as it is and carries the same fields
in its metadata member. Values yes and no are written in English; an empty cell means unknown or not applicable.
tambon_replay_summary.json is one JSON document: the same fields in its metadata member, then one record per subdistrict. Each
record repeats its lane, tier, confidence, timestamps and assumptions so that it can be used on its own, for example in
a one-page brief.

ไฟล์ CSV เข้ารหัสแบบ UTF-8 พร้อมเครื่องหมาย BOM โปรแกรม Excel จึงแสดงข้อความภาษาไทยได้เมื่อเปิดไฟล์โดยตรง ทุกไฟล์ CSV
เริ่มด้วยบรรทัดข้อมูลกำกับ (ช่องแรกขึ้นต้นด้วย #) ซึ่งบอกว่าตารางคืออะไรและไม่ใช่อะไร และจะติดไปกับตารางเมื่อส่งต่อ
บรรทัดที่สองบอกจำนวนบรรทัดดังกล่าว จากนั้นเป็นหัวคอลัมน์ ซึ่งแต่ละช่องเป็นชื่อคอลัมน์ภาษาอังกฤษตามด้วยคำอธิบายภาษาไทยในวงเล็บ
ใน QGIS ให้กำหนดจำนวนบรรทัดหัวตารางที่ต้องข้ามตามจำนวนนั้น ส่วนไฟล์ GeoJSON เปิดใน QGIS ได้ทันที
ค่า yes และ no เขียนเป็นภาษาอังกฤษ ช่องว่างหมายถึงไม่ทราบหรือไม่เกี่ยวข้อง
tambon_replay_summary.json เป็นเอกสาร JSON หนึ่งไฟล์ มีข้อมูลกำกับเดียวกันในส่วน metadata ตามด้วยหนึ่งรายการต่อหนึ่งตำบล
แต่ละรายการระบุช่องทางของหลักฐาน ระดับ ความเชื่อมั่น เวลา และสมมติฐานซ้ำไว้ จึงนำไปใช้แยกได้ เช่น ในเอกสารสรุปหนึ่งหน้า

6. THE SHELTER-CANDIDATE VERIFICATION SHEET / แบบตรวจสอบสถานที่ที่อาจใช้เป็นที่พักพิง

shelter_candidate_verification_sheet.csv is a blank checklist. No check has been conducted for this revision.
A local checker fills in the last five columns and returns the file to the project team; a returned check is labelled
'Checked by <role> on <date>; not an official shelter register'. Give a role code, never a name: ddpm_officer, local_government_officer, village_leader, site_staff, project_team, other_local_contact.
Do not add names of people, phone numbers, ID numbers or new columns. Keep the lines that start with # and the first
eight columns as they are: they tie each answer to its site, and a file without them is refused. The returned file is
kept outside the project's repository; only its hash and the checked columns are kept. Access notes are never published
or kept: only the fact that a note was given is recorded.

ไฟล์ shelter_candidate_verification_sheet.csv เป็นรายการตรวจที่ยังว่าง ยังไม่มีการตรวจสอบสำหรับข้อมูลรุ่นนี้
ผู้ตรวจสอบในพื้นที่กรอกห้าคอลัมน์สุดท้าย
แล้วส่งไฟล์กลับให้ทีมโครงการ ผลที่ส่งกลับมาจะระบุว่า 'ตรวจสอบโดย <บทบาท> เมื่อ <วันที่> ไม่ใช่ทะเบียนที่พักพิงทางการ'
โปรดระบุรหัสบทบาท ไม่ใช่ชื่อ: ddpm_officer = เจ้าหน้าที่ ปภ. · local_government_officer = เจ้าหน้าที่ อบต. หรือเทศบาล · village_leader = ผู้ใหญ่บ้านหรือกำนัน · site_staff = เจ้าหน้าที่ของสถานที่ · project_team = ทีมโครงการ FloodGuard · other_local_contact = ผู้ประสานงานในพื้นที่อื่น ๆ
โปรดอย่าใส่ชื่อบุคคล หมายเลขโทรศัพท์ เลขประจำตัว หรือเพิ่มคอลัมน์ โปรดคงบรรทัดที่ขึ้นต้นด้วย # และแปดคอลัมน์แรกไว้ตามเดิม
เพราะข้อมูลส่วนนี้ผูกคำตอบแต่ละแถวกับสถานที่ ไฟล์ที่ไม่มีข้อมูลส่วนนี้จะถูกปฏิเสธ ไฟล์ที่ส่งกลับจะเก็บไว้นอกคลังรหัสของโครงการ
เก็บไว้เพียงค่าแฮชและคอลัมน์ที่ตรวจสอบ หมายเหตุการเข้าถึงจะไม่ถูกเผยแพร่หรือเก็บไว้ บันทึกเพียงว่ามีการให้หมายเหตุหรือไม่
