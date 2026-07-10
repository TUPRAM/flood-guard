# Mae Sai Weak-Reference Action Brief - Mae Sai Weak-Reference Review Area (MS-WR-001)

> **Safety status / สถานะความปลอดภัย:** Based on weak-reference candidate flood analysis. Non-operational. Not official warning. Use only for planning/demo.

## Executive Summary / บทสรุปสำหรับผู้ตัดสินใจ

- **Decision / ข้อสรุป:** Class E - Monitor conditions, verify field data, and improve source confidence before escalation. FPPS is 6.19/100 with low confidence.
- **Evidence / หลักฐาน:** Real CDSE Sentinel-1 pre/post imagery produced a mean non-ML flood-probability proxy of 4.7% inside the weak-reference review sample.
- **Interpretation / การตีความ:** Class E means monitor and verify. It does not mean no flood risk; real administrative, population, road, access, and vulnerability joins are incomplete.

## Priority / ลำดับความสำคัญ

- FPPS: 6.19/100
- Action class: E
- Confidence: low
- Top reason: Monitor and verify because confidence is low.
- Component status: flood likelihood 4.66/100; exposure proxy 19.16/100.
- Access gap, road criticality, and vulnerability/context are unjoined placeholders in this run, not measured zero impact.

## Flood Evidence / หลักฐานน้ำท่วม

- Source: CDSE Sentinel-1 weak-reference SAR baseline
- Pre-event Sentinel-1 product: `b09f96ca-4a60-43e7-9b8d-158022f0e5bf`
- Post-event Sentinel-1 product: `20a9c3b8-37df-46d5-81d8-d63c7e460225`
- Observation timestamp: 2024-09-15T23:16:01Z
- Mean flood-probability proxy: 4.7%
- Thresholded flood-positive sample: 2,338 of 65,536 pixels.
- Manual weak-reference positive sample: 12,557 pixels.
- Reference candidate: `MANUAL-QGIS-MAE-SAI-2024` (POLYGON, EPSG:4326).
- Reference status: manually digitized weak-reference candidate; not official validation truth and not field validated.

## Candidate Validation Metrics / ตัวชี้วัดการตรวจสอบแบบอ้างอิงอย่างอ่อน

- Full-sample non-ML threshold candidate: IoU 0.006; F1/Dice 0.012; precision 0.038; recall 0.007; area error -81.4%.
- The negative full-sample area error means the threshold baseline substantially under-detected the manual weak-reference area.

| Metric | Non-ML threshold (holdout) | Weak-label logistic model (holdout) |
|---|---:|---:|
| IoU | 0.005 | 0.223 |
| F1 / Dice | 0.009 | 0.365 |
| Precision | 0.025 | 0.235 |
| Recall | 0.006 | 0.812 |
| Area error | -77.1% | +245.0% |

- The ML candidate improves overlap and recall on the spatial holdout, but its positive area error shows severe overprediction. Treat it as a screening signal, not confirmed flood extent.

## Weak-Label ML Cross-Check / การตรวจสอบด้วย ML ป้ายกำกับอย่างอ่อน

- Model: logistic_regression_from_scratch with spatial_block_holdout.
- Holdout sample: 16,384 pixels.
- Candidate decision threshold: 0.44.
- Decision-layer eligibility flag: true; the current FPPS still uses the non-ML mean probability proxy and has not been rescored from ML output.
- Warning: Weak-label experiment against manually digitized weak-reference mask. Non-operational. Not official labels. Not field validation.

## Likely Road Risks / ความเสี่ยงถนนที่อาจเกิดขึ้น

- Unavailable: no real Mae Sai road segments have been joined.
- The FPPS road-criticality value of 0.00/100 is an unjoined placeholder, not evidence that roads are safe.

## Access Loss / การสูญเสียการเข้าถึง

- Unavailable: no real Mae Sai routing graph, facilities, or population nodes have been joined.
- The FPPS access-gap value of 0.00/100 is an unjoined placeholder, not evidence of uninterrupted access.

## Equity Gap / ช่องว่างความเสมอภาคในการอพยพ

- Unavailable: vulnerable and non-vulnerable access-loss denominators are not yet joined.
- The FPPS vulnerability/context value of 0.00/100 is an unjoined placeholder, not evidence of no equity gap.

## Recommended Local Actions / ข้อเสนอการปฏิบัติในพื้นที่

- Policy class guidance: Monitor conditions, verify field data, and improve source confidence before escalation.
- แนวทางตามระดับนโยบาย: ติดตามสถานการณ์ ตรวจสอบข้อมูลภาคสนาม และปรับปรุงความเชื่อมั่นของแหล่งข้อมูลก่อนยกระดับการดำเนินการ
- Verify candidate flood areas against local observations and an independent reference before any operational decision.
- ตรวจสอบพื้นที่น้ำท่วมที่เป็นผลลัพธ์เบื้องต้นกับข้อมูลภาคสนามและแหล่งอ้างอิงอิสระ ก่อนใช้ตัดสินใจเชิงปฏิบัติการ
- Join real admin boundaries, population, roads, facilities, terrain, and vulnerability data before revising FPPS or planning routes and shelters.
- เชื่อมข้อมูลเขตการปกครอง ประชากร ถนน สถานบริการ ภูมิประเทศ และกลุ่มเปราะบางจริง ก่อนปรับ FPPS หรือวางแผนเส้นทางและศูนย์พักพิง
- Do not issue warnings, closures, evacuations, or shelter decisions from this brief alone.
- ห้ามใช้เอกสารฉบับนี้เพียงอย่างเดียวเพื่อออกคำเตือน ปิดถนน สั่งอพยพ หรือตัดสินใจเปิดศูนย์พักพิง

## Assumptions And Limitations / สมมติฐานและข้อจำกัด

- Weak-reference Sentinel-1 non-ML candidate. Non-operational. Not official validation. Not field validated. Flood likelihood comes from the weak SAR probability proxy; exposure is a sampled inundation-share proxy; real population, road, access, and vulnerability context are not joined yet.
- SAR extraction assumption: Candidate metrics against manually digitized weak-reference mask. Non-operational. Not official validation. Not field validated. Sentinel-1 SAFE GCP georeferencing is approximated for this first baseline.
- Manual-reference allowed use: candidate validation metrics; visual QA; non-operational demo reporting.
- Manual-reference prohibited use: official validation truth; official warning; redistributed source data claim; unqualified ML labels.
- Current geometry is a weak-reference review area, not a confirmed official subdistrict boundary.
- SAR layover/shadow, permanent water, urban double-bounce, manual-mask uncertainty, and date mismatch may affect results.

> **Final warning / คำเตือน:** Based on weak-reference candidate flood analysis. Non-operational. Not official warning. Use only for planning/demo.
