# Mae Sai Weak-Reference Action Brief - Ko Chang (TH570903)

> **Safety status / สถานะความปลอดภัย:** Based on weak-reference candidate flood analysis. Non-operational. Not official warning. Use only for planning/demo.

## Executive Summary / บทสรุปสำหรับผู้ตัดสินใจ

- **Decision / ข้อสรุป:** Class E - Monitor conditions, verify field data, and improve source confidence before escalation. FPPS is 53.65/100 with low confidence.
- **Evidence / หลักฐาน:** Real CDSE Sentinel-1 pre/post imagery produced a mean non-ML flood-probability proxy of 19.4% inside the HDX COD-AB ADM3 candidate aggregation unit.
- **Interpretation / การตีความ:** Class E means monitor and verify. Real admin, population, road, facility, terrain, access, and proxy-equity context is joined, but flood calibration and operational source verification remain low confidence.

## Priority / ลำดับความสำคัญ

- FPPS: 53.65/100
- Action class: E
- Confidence: low
- Top reason: Monitor and verify because confidence is low.
- Component status: flood likelihood 19.38/100; relative exposure 99.88/100; modeled access gap 86.37/100; road criticality 37.04/100; proxy vulnerability 0.37/100.
- These are candidate model outputs from open context sources; they are not observed emergency impacts or official operational data.

## Flood Evidence / หลักฐานน้ำท่วม

- Source: CDSE Sentinel-1; HDX COD-AB; WorldPop 2020; OSM/Geofabrik; Copernicus DEM GLO-30
- Pre-event Sentinel-1 product: `aaaef3af-fa49-4115-bf0f-f54175e7aedf`
- Post-event Sentinel-1 product: `5251b74b-0bbd-4365-9eb4-fa33292e175a`
- Observation timestamp: 2024-09-15T23:16:01Z
- Mean flood-probability proxy: 19.4%
- Thresholded flood-positive sample: 978 of 5,336 pixels.
- Cross-border calibration reference-positive sample: 12,557 pixels.
- Reference candidate: `MS-MANUAL-CROSSBORDER-001` (MULTIPOLYGON, EPSG:4326).
- Reference status: manual cross-border weak-reference candidate used for calibration only; it does not overlap the Thailand ADM3 candidate geometry.

## Candidate Validation Metrics / ตัวชี้วัดการตรวจสอบแบบอ้างอิงอย่างอ่อน

- Cross-border weak-reference full-sample non-ML threshold candidate: IoU 0.087; F1/Dice 0.160; precision 0.188; recall 0.139; area error -26.2%.
- The negative full-sample area error means the threshold baseline substantially under-detected the manual weak-reference area.
- Current-pair spatial-holdout ML comparison: unavailable. The legacy weak-label experiment used the retired COG pair and is intentionally excluded from this active-source brief.

## Likely Road Risks / ความเสี่ยงถนนที่อาจเกิดขึ้น

- ถนนเหมืองแดง (`1114870835`): 40.5% candidate risk; bridge-tagged; Highest road-risk driver is surrounding inundation.
- OSM way `423682161`: 38.5% candidate risk; bridge-tagged; Highest road-risk driver is surrounding inundation.
- OSM way `423682199`: 38.5% candidate risk; bridge-tagged; Highest road-risk driver is surrounding inundation.

## Access Loss / การสูญเสียการเข้าถึง

- People losing 15-minute access: 5,404
- People losing 30-minute access: 5,794
- People losing 60-minute access: 3,390

## Equity Gap / ช่องว่างความเสมอภาคในการอพยพ

- Equity gap ratio: 1.090
- Interpretation: Access-loss rates are broadly similar between groups.
- Vulnerability basis: terrain/remoteness proxy: WorldPop cell is proxy-vulnerable when sampled slope is at least 8 degrees or nearest drivable OSM road is at least 750 m away; this is not demographic vulnerability.

## Recommended Local Actions / ข้อเสนอการปฏิบัติในพื้นที่

- Policy class guidance: Monitor conditions, verify field data, and improve source confidence before escalation.
- แนวทางตามระดับนโยบาย: ติดตามสถานการณ์ ตรวจสอบข้อมูลภาคสนาม และปรับปรุงความเชื่อมั่นของแหล่งข้อมูลก่อนยกระดับการดำเนินการ
- Verify candidate flood areas against local observations and an independent reference before any operational decision.
- ตรวจสอบพื้นที่น้ำท่วมที่เป็นผลลัพธ์เบื้องต้นกับข้อมูลภาคสนามและแหล่งอ้างอิงอิสระ ก่อนใช้ตัดสินใจเชิงปฏิบัติการ
- Field-verify the highest-risk OSM road and bridge candidates, and confirm that mapped facilities are valid emergency destinations.
- ตรวจสอบถนนและสะพาน OSM ที่มีความเสี่ยงสูงในภาคสนาม และยืนยันว่าสถานที่ที่ทำแผนที่ไว้ใช้เป็นจุดหมายฉุกเฉินได้จริง
- Replace the terrain/remoteness vulnerability proxy with current demographic and local-service data before equity decisions.
- แทนที่ตัวแทนความเปราะบางด้านภูมิประเทศและความห่างไกลด้วยข้อมูลประชากร และบริการท้องถิ่นปัจจุบันก่อนตัดสินใจด้านความเสมอภาค
- Do not issue warnings, closures, evacuations, or shelter decisions from this brief alone.
- ห้ามใช้เอกสารฉบับนี้เพียงอย่างเดียวเพื่อออกคำเตือน ปิดถนน สั่งอพยพ หรือตัดสินใจเปิดศูนย์พักพิง

## Assumptions And Limitations / สมมติฐานและข้อจำกัด

- Real open context joined at COD-AB ADM3 grain. Flood probability is a non-ML Sentinel-1 candidate calibrated only against a nearby cross-border manual weak reference. Exposure is a relative WorldPop probability proxy; road disruption and access loss are heuristic; vulnerability is a terrain/remoteness proxy. Non-operational and not official validation.
- SAR extraction assumption: Cross-border calibration metrics against a manually digitized weak-reference mask; not Mae Sai Thailand ADM3 validation. Non-operational. Not official validation. Not field validated. The active GDAL subdataset is uncalibrated amplitude, converted with 20*log10(amplitude); it is not Sigma0/Beta0/Gamma0 calibrated. Sentinel-1 SAFE GCP georeferencing is approximated for this first baseline.
- Manual-reference allowed use: cross-border calibration metrics only; visual QA; non-operational demo reporting.
- Manual-reference prohibited use: official validation truth; official warning; redistributed source data claim; unqualified ML labels.
- Current geometry is an HDX COD-AB ADM3 boundary; flood calibration still depends on a nearby cross-border manual weak reference.
- SAR layover/shadow, permanent water, urban double-bounce, manual-mask uncertainty, and date mismatch may affect results.

> **Final warning / คำเตือน:** Based on weak-reference candidate flood analysis. Non-operational. Not official warning. Use only for planning/demo.
