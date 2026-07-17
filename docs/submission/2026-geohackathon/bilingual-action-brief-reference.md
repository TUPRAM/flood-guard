# Mae Sai candidate planning brief / สรุปการวางแผนพื้นที่แม่สายจากข้อมูลผู้สมัคร

> **Safety status / สถานะความปลอดภัย:** Candidate planning evidence only.
> Non-operational. Not an official warning. Use for demonstration and planning
> review only. / เป็นหลักฐานผู้สมัครสำหรับการวางแผนเท่านั้น ไม่ใช่ระบบปฏิบัติการ
> และไม่ใช่คำเตือนอย่างเป็นทางการ ใช้เพื่อการสาธิตและทบทวนแผนเท่านั้น

## Area / พื้นที่

- Wiang Phang Kham, Mae Sai / เวียงพางคำ อำเภอแม่สาย
- Area ID: `TH570906`
- Source timestamp / เวลาข้อมูลต้นทาง: `2024-09-15T23:16:01Z`
- Confidence / ระดับความเชื่อมั่น: low / ต่ำ
- Dataset mode / โหมดข้อมูล: candidate / ข้อมูลผู้สมัคร
- Operational status / สถานะการใช้งาน: non-operational / ไม่ใช่ระบบปฏิบัติการ

## Decision summary / สรุปสำหรับการตัดสินใจ

- FPPS: `31.74/100`.
- Recommended class / ระดับคำแนะนำ: **E - Monitor and Verify / ติดตามและตรวจสอบ**.
- Top reason / เหตุผลหลัก: confidence is low; verify source and field
  conditions before escalation. / ความเชื่อมั่นยังต่ำ ควรตรวจสอบแหล่งข้อมูลและ
  สภาพพื้นที่ก่อนยกระดับการดำเนินการ
- Candidate mean flood-probability proxy / ค่าตัวแทนความน่าจะเป็นน้ำท่วมเฉลี่ย:
  `7.1%` within the selected ADM3 aggregation unit. This is not an observed
  inundation percentage. / ภายในหน่วยพื้นที่ ADM3 ที่เลือก ค่านี้ไม่ใช่สัดส่วน
  น้ำท่วมที่ตรวจยืนยันแล้ว

## Access and equity evidence / หลักฐานการเข้าถึงและความเสมอภาค

- Modeled people losing 30-minute access / จำนวนประชากรที่แบบจำลองระบุว่า
  สูญเสียการเข้าถึงภายใน 30 นาที: `0` in this selected area.
- Equity-gap ratio / อัตราส่วนช่องว่างการเข้าถึง: `1.000` because both modeled
  groups have zero measured loss in this area. / เนื่องจากทั้งสองกลุ่มไม่มี
  การสูญเสียการเข้าถึงตามแบบจำลองในพื้นที่นี้
- Vulnerability is currently a terrain/remoteness proxy, not current
  demographic vulnerability. / ความเปราะบางในปัจจุบันเป็นตัวแทนจากภูมิประเทศ
  และความห่างไกล ไม่ใช่ข้อมูลประชากรเปราะบางปัจจุบัน

## Recommended checks / ข้อเสนอแนะสำหรับการตรวจสอบ

1. Verify candidate flood areas against local observations and an independent
   qualified reference. / ตรวจสอบพื้นที่น้ำท่วมผู้สมัครด้วยข้อมูลภาคสนามและ
   แหล่งอ้างอิงอิสระที่ผ่านคุณสมบัติ
2. Field-check the highest-ranked OSM road and bridge candidates. / ตรวจสอบ
   ถนนและสะพาน OSM ที่มีลำดับความเสี่ยงสูงในภาคสนาม
3. Confirm that mapped hospitals, shelters and other facilities are current
   and valid emergency destinations. / ยืนยันว่าโรงพยาบาล ศูนย์พักพิง และ
   สถานที่สำคัญบนแผนที่เป็นข้อมูลปัจจุบันและใช้งานได้จริง
4. Replace the terrain/remoteness vulnerability proxy with current local
   demographic and service data before equity decisions. / ใช้ข้อมูลประชากร
   และบริการท้องถิ่นปัจจุบันแทนตัวแทนความเปราะบางก่อนตัดสินใจด้านความเสมอภาค
5. Do not issue warnings, road closures, evacuations or shelter-opening orders
   from this brief alone. / ห้ามใช้เอกสารนี้เพียงอย่างเดียวเพื่อออกคำเตือน
   ปิดถนน สั่งอพยพ หรือเปิดศูนย์พักพิง

## Evidence and limitations / หลักฐานและข้อจำกัด

The brief is derived from the committed candidate output
`outputs/mae_sai_action_brief_TH570906.md`. Sentinel-1 flood calibration uses a
nearby cross-border manual weak reference; road, access, population and terrain
context are derived/modelled and not observed impacts. SAR shadow/layover,
permanent water, urban double-bounce, reference uncertainty and event timing
may affect results.

เอกสารนี้อ้างอิงจากผลลัพธ์ผู้สมัครที่บันทึกไว้ในโครงการ การปรับเทียบ Sentinel-1
ใช้ขอบเขตอ้างอิงแบบอ่อนที่วาดด้วยมือในพื้นที่ใกล้เคียงข้ามพรมแดน ข้อมูลถนน
การเข้าถึง ประชากร และภูมิประเทศเป็นข้อมูลอนุมานหรือแบบจำลอง ไม่ใช่ผลกระทบที่
ตรวจยืนยันแล้ว เงาเรดาร์ น้ำถาวร การสะท้อนในเมือง ความไม่แน่นอนของขอบเขตอ้างอิง
และช่วงเวลาเหตุการณ์อาจส่งผลต่อผลลัพธ์

> **Final warning / คำเตือนสุดท้าย:** Do not use this brief for public alerting
> or operational response without official validation and local authority
> review. / ห้ามใช้เอกสารนี้เพื่อแจ้งเตือนประชาชนหรือสั่งการปฏิบัติการโดยไม่มี
> การตรวจสอบอย่างเป็นทางการและการทบทวนจากหน่วยงานท้องถิ่น
