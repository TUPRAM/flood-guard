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
# generated_at: 2026-10-02T14:33:00+07:00
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
# input_receipt: docs/mae_sai_timeline_r4_input_receipt.json lists every input file of the bake with its SHA-256 (also timeline.json input_sha256); input_set_sha256=1ae21d84263d6b75e150c89b2f8029d551ac4d9a3155d6e8da10214170c6df89
# git_commit: null: a file cannot hold the hash of the commit that adds it; git log -1 --format=%H -- apps/web/public/studies/mae-sai-2024-timeline/r4/exports/README_licences.txt

FLOODGUARD MAE SAI SEPTEMBER 2024 REPLAY: EXPORT PACK
ชุดไฟล์ส่งออกของการย้อนดูน้ำท่วมแม่สาย กันยายน 2567 (2024) โดย FloodGuard

1. WHAT THIS IS / ไฟล์ชุดนี้คืออะไร

Tables and one map layer written from a model replay of the September 2024 flood in Mae Sai District. They are for
preparedness planning and exercises. Every table is modelled, not observed: it is not a forecast, not an observed
closure record and not an official warning, and it must not be used for emergency response or evacuation orders.
Confidence is low and nothing was checked on the ground.

ตารางและชั้นข้อมูลแผนที่หนึ่งชั้นที่เขียนจากการย้อนดูด้วยแบบจำลองของเหตุการณ์น้ำท่วมอำเภอแม่สายเดือนกันยายน 2567 (2024)
ใช้สำหรับการวางแผนเตรียมความพร้อมและการฝึกซ้อม ทุกตารางเป็นค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้ ไม่ใช่การพยากรณ์
ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง และไม่ใช่การเตือนภัยอย่างเป็นทางการ ห้ามใช้ในการตอบสนองเหตุฉุกเฉินหรือการสั่งอพยพ
ความเชื่อมั่นอยู่ในระดับต่ำ และยังไม่มีการตรวจสอบในพื้นที่

2. FILES / รายการไฟล์

shelter_plan_reported_2024.csv
  Shelters reported in use in Mae Sai in September 2024, with a model check of each located site (not an official register)
  ที่พักพิงที่มีรายงานว่าใช้ในแม่สายเดือนกันยายน 2567 (2024) พร้อมผลเทียบกับแบบจำลองของสถานที่ที่ระบุตำแหน่งได้ (ไม่ใช่ทะเบียนทางการ)
  21,874 bytes; 19 rows; 35 provenance lines before the column header; SHA-256 6af029a6ea9307af9e7c51ddfa60ed64f8b69daa150ee64ca141f98dddf8074a
  Lanes: REP, SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

shelter_plan_k.csv
  Modelled shelter coverage ranking, sites 1 to N: a plan of any size is its first rows (candidates to verify)
  การจัดอันดับความครอบคลุมของที่พักพิงตามแบบจำลอง ลำดับ 1 ถึง N แผนขนาดใดก็ตามคือแถวแรกตามจำนวนนั้น (สถานที่ที่ควรตรวจสอบ)
  12,754 bytes; 12 rows; 38 provenance lines before the column header; SHA-256 c67a43b5a909dc939b0b40611f2b42943aa633703988aa56047fef6977711c13
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

shelter_plan_capacitated.csv
  Capacity-aware shelter ranking under two capacity bounds: who fits (candidates to verify)
  การจัดอันดับที่พักพิงแบบคิดความจุภายใต้ขอบเขตล่างและขอบเขตบน: รองรับได้กี่คน (สถานที่ที่ควรตรวจสอบ)
  16,031 bytes; 25 rows; 37 provenance lines before the column header; SHA-256 1fd77def8f373f5d433648f3b16fda9e971d9c865e9f68eddcf0f616b8fbfb61
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

shelter_sites.geojson
  Shelter sites as points: every modelled candidate and every located site reported in use in September 2024
  ตำแหน่งที่พักพิงแบบจุด: สถานที่ที่เป็นไปได้ทุกแห่งตามแบบจำลอง และสถานที่ที่มีรายงานว่าใช้ในเดือนกันยายน 2567 (2024) ที่ระบุตำแหน่งได้
  88,448 bytes; 128 features; SHA-256 07148d0474d72dd6c193f854958a4a333e49ef37ca21ade7d13c4b95c6e5153e
  Lanes: SCN, REP. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)).

modelled_road_inundation_by_hour.csv
  Modelled road inundation by hour, one row per OpenStreetMap way (modelled, not observed)
  ถนนที่น้ำท่วมตามแบบจำลองรายชั่วโมง หนึ่งแถวต่อหนึ่งเส้นทางใน OpenStreetMap (ค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้)
  345,264 bytes; 3,478 rows; 37 provenance lines before the column header; SHA-256 d04d3b45fba261df12249eb06b41466ba3eab8add057b6b8c77adc579add92c2
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); HDX Thailand COD-AB subdistrict boundaries v01 (CC BY-IGO).

modelled_access_loss_by_hour.csv
  Modelled loss of walking access to a shelter by hour, one row per subdistrict and replay hour
  การสูญเสียการเข้าถึงที่พักพิงด้วยการเดินตามแบบจำลองรายชั่วโมง หนึ่งแถวต่อตำบลและชั่วโมงของการย้อนดู
  241,197 bytes; 2,112 rows; 38 provenance lines before the column header; SHA-256 2f84b43259c8ed50ba11a82dd4187d489bb9ddc94abf7999053f4dd202331c76
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); WorldPop Thailand 100 m population 2020, unconstrained top-down (tha_ppp_2020) (CC BY 4.0); HDX Thailand COD-AB subdistrict boundaries v01 (CC BY-IGO); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)); Shelters reported in use in September 2024 (FloodGuard desk research) (Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)).

shelter_candidate_verification_sheet.csv
  Shelter-candidate verification sheet: a blank checklist for a local checker (no check has been conducted)
  แบบตรวจสอบสถานที่ที่อาจใช้เป็นที่พักพิง: รายการตรวจที่ยังว่างสำหรับผู้ตรวจสอบในพื้นที่ (ยังไม่มีการตรวจสอบ)
  22,074 bytes; 95 rows; 43 provenance lines before the column header; SHA-256 de8041b54142886e788c62868227c097628c45932dfd1021fe7f779ed711d2cc
  Lanes: SCN. Licence: ODbL 1.0. Derived from: OpenStreetMap roads and candidate facilities (Geofabrik extract) (ODbL 1.0); Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution)).

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

ไฟล์ CSV เข้ารหัสแบบ UTF-8 พร้อมเครื่องหมาย BOM โปรแกรม Excel จึงแสดงข้อความภาษาไทยได้เมื่อเปิดไฟล์โดยตรง ทุกไฟล์ CSV
เริ่มด้วยบรรทัดข้อมูลกำกับ (ช่องแรกขึ้นต้นด้วย #) ซึ่งบอกว่าตารางคืออะไรและไม่ใช่อะไร และจะติดไปกับตารางเมื่อส่งต่อ
บรรทัดที่สองบอกจำนวนบรรทัดดังกล่าว จากนั้นเป็นหัวคอลัมน์ ซึ่งแต่ละช่องเป็นชื่อคอลัมน์ภาษาอังกฤษตามด้วยคำอธิบายภาษาไทยในวงเล็บ
ใน QGIS ให้กำหนดจำนวนบรรทัดหัวตารางที่ต้องข้ามตามจำนวนนั้น ส่วนไฟล์ GeoJSON เปิดใน QGIS ได้ทันที
ค่า yes และ no เขียนเป็นภาษาอังกฤษ ช่องว่างหมายถึงไม่ทราบหรือไม่เกี่ยวข้อง

6. THE SHELTER-CANDIDATE VERIFICATION SHEET / แบบตรวจสอบสถานที่ที่อาจใช้เป็นที่พักพิง

shelter_candidate_verification_sheet.csv is a blank checklist. No check has been conducted for this revision.
A local checker fills in the last five columns and returns the file to the project team; a returned check is labelled
'Checked by <role> on <date>; not an official shelter register'. Give a role code, never a name: ddpm_officer, local_government_officer, village_leader, site_staff, project_team, other_local_contact.
Do not add names of people, phone numbers, ID numbers or new columns. The returned file is kept outside the project's
repository; only its hash and the checked columns are kept.

ไฟล์ shelter_candidate_verification_sheet.csv เป็นรายการตรวจที่ยังว่าง ยังไม่มีการตรวจสอบสำหรับข้อมูลรุ่นนี้
ผู้ตรวจสอบในพื้นที่กรอกห้าคอลัมน์สุดท้าย
แล้วส่งไฟล์กลับให้ทีมโครงการ ผลที่ส่งกลับมาจะระบุว่า 'ตรวจสอบโดย <บทบาท> เมื่อ <วันที่> ไม่ใช่ทะเบียนที่พักพิงทางการ'
โปรดระบุรหัสบทบาท ไม่ใช่ชื่อ: ddpm_officer = เจ้าหน้าที่ ปภ. · local_government_officer = เจ้าหน้าที่ อบต. หรือเทศบาล · village_leader = ผู้ใหญ่บ้านหรือกำนัน · site_staff = เจ้าหน้าที่ของสถานที่ · project_team = ทีมโครงการ FloodGuard · other_local_contact = ผู้ประสานงานในพื้นที่อื่น ๆ
โปรดอย่าใส่ชื่อบุคคล หมายเลขโทรศัพท์ เลขประจำตัว หรือเพิ่มคอลัมน์ ไฟล์ที่ส่งกลับจะเก็บไว้นอกคลังรหัสของโครงการ เก็บไว้เพียงค่าแฮชและคอลัมน์ที่ตรวจสอบ
