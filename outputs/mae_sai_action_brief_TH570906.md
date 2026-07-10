# Mae Sai Weak-Reference Action Brief - Wiang Phang Kham (TH570906)

> **Safety status / สถานะความปลอดภัย:** Based on weak-reference candidate flood analysis. Non-operational. Not official warning. Use only for planning/demo.

## Executive Summary / บทสรุปสำหรับผู้ตัดสินใจ

- **Decision / ข้อสรุป:** Class E - Monitor conditions, verify field data, and improve source confidence before escalation. FPPS is 31.74/100 with low confidence.
- **Evidence / หลักฐาน:** Real CDSE Sentinel-1 pre/post imagery produced a mean non-ML flood-probability proxy of 7.1% inside the official COD-AB ADM3 aggregation unit.
- **Interpretation / การตีความ:** Class E means monitor and verify. Real admin, population, road, facility, terrain, access, and proxy-equity context is joined, but flood calibration and operational source verification remain low confidence.
- **District cross-check / การตรวจสอบระดับอำเภอ:** Ko Chang has the highest modeled 30-minute access loss (190 people) and proxy equity-gap ratio 2.018.

## Priority / ลำดับความสำคัญ

- FPPS: 31.74/100
- Action class: E
- Confidence: low
- Top reason: Monitor and verify because confidence is low.
- Component status: flood likelihood 7.11/100; relative exposure 100.00/100; modeled access gap 0.00/100; road criticality 19.39/100; proxy vulnerability 17.01/100.
- These are candidate model outputs from open context sources; they are not observed emergency impacts or official operational data.

## Flood Evidence / หลักฐานน้ำท่วม

- Source: CDSE Sentinel-1; HDX COD-AB; WorldPop 2020; OSM/Geofabrik; Copernicus DEM GLO-30
- Pre-event Sentinel-1 product: `b09f96ca-4a60-43e7-9b8d-158022f0e5bf`
- Post-event Sentinel-1 product: `20a9c3b8-37df-46d5-81d8-d63c7e460225`
- Observation timestamp: 2024-09-15T23:16:01Z
- Mean flood-probability proxy: 7.1%
- Thresholded flood-positive sample: 281 of 5,087 pixels.
- Cross-border calibration reference-positive sample: 12,557 pixels.
- Reference candidate: `MANUAL-QGIS-MAE-SAI-2024` (POLYGON, EPSG:4326).
- Reference status: manual cross-border weak-reference candidate used for calibration only; it does not overlap the official Thailand ADM3 geometry.

## Candidate Validation Metrics / ตัวชี้วัดการตรวจสอบแบบอ้างอิงอย่างอ่อน

- Cross-border weak-reference full-sample non-ML threshold candidate: IoU 0.006; F1/Dice 0.012; precision 0.038; recall 0.007; area error -81.4%.
- The negative full-sample area error means the threshold baseline substantially under-detected the manual weak-reference area.

| Metric | Non-ML threshold (holdout) | Weak-label logistic model (holdout) |
|---|---:|---:|
| IoU | 0.005 | 0.223 |
| F1 / Dice | 0.009 | 0.365 |
| Precision | 0.025 | 0.235 |
| Recall | 0.006 | 0.812 |
| Area error | -77.1% | +245.0% |

- The cross-border ML candidate improves overlap and recall on its spatial holdout, but its positive area error shows severe overprediction. Treat it as a screening signal, not confirmed flood extent.

## Weak-Label ML Cross-Check / การตรวจสอบด้วย ML ป้ายกำกับอย่างอ่อน

- Model: logistic_regression_from_scratch with spatial_block_holdout.
- Holdout sample: 16,384 pixels.
- Candidate decision threshold: 0.44.
- Decision-layer eligibility flag: true; the current FPPS still uses the non-ML mean probability proxy and has not been rescored from ML output.
- Warning: Weak-label experiment against manually digitized weak-reference mask. Non-operational. Not official labels. Not field validation.

## Likely Road Risks / ความเสี่ยงถนนที่อาจเกิดขึ้น

- ถนนเลี่ยงเมืองแม่สาย (`1112439817`): 25.0% candidate risk; bridge-tagged; Highest road-risk driver is road class.
- OSM way `1456754170`: 25.0% candidate risk; bridge-tagged; Highest road-risk driver is road class.
- ถนนพหลโยธิน (`1112437371`): 20.0% candidate risk; Highest road-risk driver is road class.

## Access Loss / การสูญเสียการเข้าถึง

- People losing 15-minute access: 0
- People losing 30-minute access: 0
- People losing 60-minute access: 0

## Equity Gap / ช่องว่างความเสมอภาคในการอพยพ

- Equity gap ratio: 1.000
- Interpretation: No measured access-loss gap; both groups have zero loss.
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
- SAR extraction assumption: Candidate metrics against manually digitized weak-reference mask. Non-operational. Not official validation. Not field validated. Sentinel-1 SAFE GCP georeferencing is approximated for this first baseline.
- Manual-reference allowed use: candidate validation metrics; visual QA; non-operational demo reporting.
- Manual-reference prohibited use: official validation truth; official warning; redistributed source data claim; unqualified ML labels.
- Current geometry is an HDX COD-AB ADM3 boundary; flood calibration still depends on a nearby cross-border manual weak reference.
- SAR layover/shadow, permanent water, urban double-bounce, manual-mask uncertainty, and date mismatch may affect results.

> **Final warning / คำเตือน:** Based on weak-reference candidate flood analysis. Non-operational. Not official warning. Use only for planning/demo.
