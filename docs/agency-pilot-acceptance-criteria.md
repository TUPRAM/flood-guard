# เกณฑ์ยอมรับโครงการนำร่อง / Agency pilot acceptance criteria

Version: `agency-pilot-acceptance-v1`
Default decision: not accepted; non-operational

Every required row must have immutable evidence, an accountable reviewer, and a
recorded date. A passing user-interface demonstration alone is not acceptance.

| ID | เกณฑ์ภาษาไทย | English criterion | Required evidence |
|---|---|---|---|
| `AC-SAFETY-01` | ข้อความไทยและอังกฤษระบุว่า FloodGuard เป็นเครื่องมือสนับสนุนการเตรียมพร้อมและการวางแผน ไม่ใช่ประกาศเตือนภัยทางการ ระบบตรวจจับแบบรับประกัน หรือระบบนำทางอพยพสด | Thai and English copy identifies FloodGuard as preparedness and planning support, not an official warning, guaranteed detector, or live evacuation navigator. | Approved copy inventory and viewport QA receipt |
| `AC-DATA-02` | หน้าจอตัดสินใจทุกหน้าจอแสดงเวลาข้อมูล ความเชื่อมั่น สมมติฐาน แหล่งที่มา รุ่นข้อมูล และสถานะการปฏิบัติการ | Every decision surface shows source time, confidence, assumptions, provenance, data version, and operating state. | Accessibility and visual-QA report |
| `AC-OFFLINE-03` | ชุดข้อมูลสาธิต แคชออฟไลน์ และข้อมูล candidate ต้องเป็น `non_operational` และ `official_warning=false` | Fixture, cached-offline, and candidate data remain `non_operational` with `official_warning=false`. | Offline browser smoke test and contract receipt |
| `AC-AUTH-04` | API ตรวจสอบข้อมูลประจำตัว อายุ credential ลายเซ็น และสิทธิ์ตามบทบาทซ้ำในทุกคำขอที่ได้รับการป้องกัน | The API rechecks credential identity, expiry, signature, and role capability on every protected request. | API role-matrix, expiry, and tamper tests |
| `AC-FIELD-05` | การตรวจสอบภาคสนามตาม `field-validation-v1` เสร็จสมบูรณ์และผูกกับ manifest ที่ไม่เปลี่ยนแปลง | `field-validation-v1` is complete and bound to the immutable artifact manifest. | Signed field-validation receipt and manifest checksum |

## Additional release conditions

- Source license, product ID, checksum, acquisition time, CRS, resolution, and
  bounds are confirmed for every official input.
- The qualified reference mask and reviewer-calibration evidence pass their
  contracts.
- Spatial-holdout metrics and error categories are accepted for the named study
  area; evidence from another scope is not substituted.
- The trusted probability-raster zonal receipt matches the immutable model run
  and reporting geometry.
- Audit logging, artifact retention, backup, monitoring, and key rotation have
  named owners.
- A Thai-speaking operational reviewer and an English-speaking technical
  reviewer approve the same data version.
- Rollback removes the installed acceptance receipt and returns the service to
  planning/non-operational state.

## Approval record

The acceptance record must name roles, not embed personal data in public
artifacts:

| Responsibility | Required sign-off |
|---|---|
| Agency data owner | Confirms provenance, license, and data version |
| Emergency-operations owner | Confirms language and bounded intended use |
| Geospatial reviewer | Confirms grid, reporting geometry, and zonal receipt |
| Model-validation reviewer | Confirms holdout, metrics, calibration, and errors |
| Information-security owner | Confirms identity, keys, audit, retention, and monitoring |

The API's signed receipt references criterion IDs and evidence hashes. It does
not store signatures, credentials, or reviewer private details in the browser.
