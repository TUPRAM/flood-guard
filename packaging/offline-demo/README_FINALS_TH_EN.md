# FloodGuard Thailand — Mae Sai offline scenario demonstration

## ภาษาไทย

ชุดนี้เป็นการเปรียบเทียบเส้นทางตามสถานการณ์สมมติจากสถานที่สาธารณะในแม่สาย
ไม่ใช่ประกาศเตือนภัย ไม่ใช่ผลตรวจสอบน้ำท่วมจริง และไม่ใช่เส้นทางอพยพที่ยืนยันความปลอดภัย
คะแนนเหตุการณ์ที่ยอมรับ จำนวนผู้ประสบภัย ความจุจริง และความเท่าเทียมตามอายุยังไม่พร้อม

1. แตกไฟล์ ZIP ทั้งหมดลงในโฟลเดอร์เดียวกัน
2. ใช้ Python 3 เปิด `./serve-demo.ps1` ใน PowerShell หรือรัน `python serve-demo.py`
3. เปิด `http://127.0.0.1:8000/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024`
4. เริ่มที่สำนักงานเทศบาลแม่สาย เลือกโรงพยาบาลและการเดิน แล้วเปรียบเทียบกรณีฐานกับการปิดถนนสมมติ

ก่อน/หลังหมายถึงการเปลี่ยนเงื่อนไขในแบบจำลอง ไม่ใช่เส้นทางก่อนและหลังน้ำท่วมที่สังเกตจริง
หมุดเป็นตำแหน่งจากแหล่งข้อมูลสาธารณะ ยังไม่ได้ยืนยันทางเข้า การเปิดบริการ หรือการผ่านได้จริง
หากไม่มีเส้นทาง เวลาจะแสดงว่าไม่พร้อม ไม่ใช่ศูนย์ บริการประเภทอื่นจะไม่ถูกใช้แทนโดยเงียบ

ดูรายละเอียดและแหล่งข้อมูลที่ `/studio/library/` และอ่าน `FINALS_GUIDE.md`
หน้า Command และผล GeoAI เดิมเป็นงานวิจัยที่เก็บไว้เพื่อเปรียบเทียบ ไม่ใช่ลำดับรับมือเหตุการณ์ที่ยอมรับ
ลิงก์ไปยังหน่วยงานภายนอกต้องใช้อินเทอร์เน็ต ส่วนแผนที่เส้นทางและข้อมูลสาธิตหลักรวมอยู่ใน ZIP

## English

This package demonstrates conditional route and service-access comparisons from
prepared public places in Mae Sai. It is non-operational, not an official warning,
not independently validated flood impact, and not safe evacuation navigation.
Accepted event FPPS/action class, flood-affected population, actual shelter
capacity/demand and age equity remain unavailable where evidence is missing.

1. Extract the complete ZIP into one directory. Keep `site/`, the manifest and launchers together.
2. With Python 3 installed, run `./serve-demo.ps1` in PowerShell, or `python serve-demo.py`.
3. Open `http://127.0.0.1:8000/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024`.
4. Start at Mae Sai Municipal Office, select Hospital care and Walking model, and compare the baseline with an imposed route-link closure.

The server checks the manifest's packaged-file hashes before serving on localhost.
Open the HTTP URL, not the HTML file directly. Stop the server with Ctrl+C. No
external API, Node.js runtime or Python package installation is needed to view
the extracted site; Python 3's standard library is sufficient.

“Before” and “after” describe a controlled model change, not observed historical
pre/post-flood road conditions. Public site markers are not verified entrances.
An unavailable route has unavailable time, not zero. Hospitals, primary care,
pharmacies and shelters remain separate service sets.

The evidence library is at `http://127.0.0.1:8000/studio/library/`. Read
`FINALS_GUIDE.md` for the prepared case, claim boundaries and reproduction inputs.
Retained Command/GeoAI scores are research comparisons, not accepted priorities.
The main route map and data are bundled; visiting source websites still requires
an internet connection and an explicit user action.

`offline-bundle-manifest.json` records the Git commit, scenario entrypoint,
evidence identities and SHA-256 checksums. File integrity checks do not establish
scientific accuracy, field review, or compliance with competition submission rules.
