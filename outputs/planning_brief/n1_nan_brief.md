# Case N1: own radar flood map (M1-z), Nan, Mueang Nan, Phu Phiang and Wiang Sa (35 tambons)
## กรณี N1: แผนที่น้ำท่วมจากเรดาร์ของ FloodGuard (M1-z) จังหวัดน่าน อำเภอเมืองน่าน ภูเพียง และเวียงสา (35 ตำบล)

> **Planning guidance. Not an official warning, and not real-time: one radar pass, tested once against another map before it fed the score.**
>
> **ข้อมูลประกอบการวางแผน ไม่ใช่คำเตือนอย่างเป็นทางการ และไม่ใช่ข้อมูลแบบเรียลไทม์ ใช้ภาพเรดาร์รอบเดียว ซึ่งทดสอบกับแผนที่อื่นหนึ่งครั้งก่อนนำมาคำนวณคะแนน**

What this case is: our own radar flood map (method M1-z on one Copernicus Sentinel-1C pass), frozen before any Nan reference was scored, then tested once against another satellite's map (JAXA ALOS-2 Flood Proxy Map of 2025-07-28 (layer FLDEXT as water, inside layer REGION), L-band radar) before it fed the score. This is test 1 of record under amendment 2 of the protocol (decision log R53). A first run, against GFM's map of the same Sentinel-1A pass of 31 July (not independent), also missed its bar (IoU 0.068); amendment 2 came after it, and the first run is kept beside it.

กรณีนี้คืออะไร: แผนที่น้ำท่วมจากเรดาร์ของโครงการเอง (วิธี M1-z จากภาพ Copernicus Sentinel-1C หนึ่งรอบ) ตรึงค่าวิธีไว้ก่อนนำไปเทียบกับแผนที่อ้างอิงใดๆ ของน่าน แล้วทดสอบหนึ่งครั้งกับแผนที่จากดาวเทียมอีกดวงหนึ่ง (JAXA ALOS-2 Flood Proxy Map of 2025-07-28 (layer FLDEXT as water, inside layer REGION) เรดาร์ย่าน L) ก่อนนำมาคำนวณคะแนน การทดสอบนี้เป็นการทดสอบที่ 1 ที่ใช้ตัดสินผลตามการแก้ไขโพรโทคอลครั้งที่ 2 (บันทึกการตัดสินใจ R53) การทดสอบรอบแรกกับแผนที่ GFM จากภาพ Sentinel-1A รอบเดียวกันของวันที่ 31 กรกฎาคม (ไม่เป็นอิสระจากแผนที่ของเรา) ก็ไม่ผ่านเกณฑ์เช่นกัน (IoU 0.068) การแก้ไขครั้งที่ 2 ทำขึ้นหลังรอบนั้น และเก็บผลรอบแรกไว้ข้างกัน

**Test outcome: test 1 did not meet its bar, so every class is E (low confidence), with its would-be class beside it. Test 1, agreement with JAXA ALOS-2 Flood Proxy Map of 2025-07-28 (layer FLDEXT as water, inside layer REGION), not a ground check: IoU 0.23, 95% interval 0.17 to 0.28 (bar ≥ 0.40), no answer on 2.2% of the compared cells (bar ≤ 20%). Dry control (first run, Sentinel-1A pass of 2025-07-31 23:08 UTC) on hills where the THEOS-2 image shows no water: 0.04% of the answered cells flagged (bar ≤ 5%).**

**ผลการทดสอบ: การทดสอบที่ 1 ไม่ผ่านเกณฑ์ ทุกตำบลจึงได้ระดับ E (ความเชื่อมั่นต่ำ) โดยแสดงระดับที่จะได้ไว้ข้างกัน การทดสอบที่ 1 ความสอดคล้องกับ JAXA ALOS-2 Flood Proxy Map of 2025-07-28 (layer FLDEXT as water, inside layer REGION) ไม่ใช่การตรวจสอบภาคสนาม: IoU 0.23 ช่วง 95% 0.17 ถึง 0.28 (เกณฑ์ ≥ 0.40) ไม่มีคำตอบใน 2.2% ของเซลล์ที่เปรียบเทียบ (เกณฑ์ ≤ 20%) พื้นที่ควบคุม (รอบแรก ภาพ Sentinel-1A 2025-07-31 23:08 UTC) บนเนินเขาที่ภาพ THEOS-2 ไม่แสดงน้ำ: ระบุเป็นน้ำ 0.04% ของเซลล์ที่มีคำตอบ (เกณฑ์ ≤ 5%)**

### Read with care / ข้อควรระวัง

- Terrain answered 95% of the compared cells before the radar was read (more than 5 m above drainage, or a slope of 5° or more); the radar decided 2.4%. The low no-answer share comes from that, not from the radar seeing the land. / ภูมิประเทศให้คำตอบ 95% ของเซลล์ที่เปรียบเทียบก่อนอ่านค่าเรดาร์ (สูงกว่าทางระบายน้ำเกิน 5 ม. หรือลาดชัน 5° ขึ้นไป) ส่วนเรดาร์ตัดสิน 2.4% สัดส่วนที่ไม่มีคำตอบต่ำจึงมาจากส่วนนี้ ไม่ใช่เพราะเรดาร์มองเห็นพื้นที่
- Of the JAXA water the map does not flag, 71% was ruled out by the terrain screen before the radar was read (counted after the test, report only). / ในพื้นที่น้ำตามแผนที่ JAXA ที่แผนที่ของเราไม่ได้ระบุ 71% ถูกตัดออกโดยเกณฑ์ภูมิประเทศก่อนอ่านค่าเรดาร์ (นับหลังการทดสอบ รายงานเท่านั้น)
- Test 1 measured 74% of the frame's land, inside JAXA's REGION; the rest feeds the classes untested. There, 12% of the compared cells have no radar value on this pass, and the map answers 99% of those by terrain alone. / การทดสอบที่ 1 วัดได้ 74% ของพื้นที่บกในกรอบ (ภายในชั้น REGION ของ JAXA) ส่วนที่เหลือใช้คำนวณระดับโดยไม่ได้ทดสอบ ภายในพื้นที่นั้น 12% ของเซลล์ที่เปรียบเทียบไม่มีค่าเรดาร์จากภาพรอบนี้ และแผนที่ให้คำตอบ 99% ของเซลล์เหล่านั้นจากภูมิประเทศเพียงอย่างเดียว
- Dry control: terrain answered 99% of its answered cells; of the 262 cells the radar decided, it flagged 8 (3.1%). It mostly tests the terrain screen. / พื้นที่ควบคุม: ภูมิประเทศให้คำตอบ 99% ของเซลล์ที่มีคำตอบ ในเซลล์ 262 เซลล์ที่เรดาร์ตัดสิน ระบุเป็นน้ำ 8 เซลล์ (3.1%) จึงเป็นการทดสอบเกณฑ์ภูมิประเทศเป็นส่วนใหญ่
- One event, one frame. The Sentinel-1C pass is raised by 0.79 dB to match its Sentinel-1A dry season (amendment 1). / เหตุการณ์เดียว พื้นที่เดียว ค่าภาพ Sentinel-1C ถูกปรับเพิ่ม 0.79 dB ให้ตรงกับฤดูแล้งของ Sentinel-1A (การแก้ไขครั้งที่ 1)
- A tambon in class E, or a cell with no flag, was not shown to be dry: news records of 24 to 27 July 2025 report water at Nan Hospital, and the map answers the whole site 'not flooded' by terrain (test 4). / ตำบลระดับ E หรือเซลล์ที่ไม่ได้ระบุเป็นน้ำ ไม่ได้แสดงว่าพื้นที่แห้ง ข่าวระหว่างวันที่ 24 ถึง 27 กรกฎาคม 2025 รายงานว่ามีน้ำที่โรงพยาบาลน่าน แต่แผนที่ให้คำตอบว่า "ไม่ท่วม" ทั้งพื้นที่จากภูมิประเทศ (การทดสอบที่ 4)

- Source times: radar pass 2025-07-28 11:20 UTC (2025-07-28 18:20 Thai time), Sentinel-1C, relative orbit 99, 0 days from the case reference date 2025-07-28. Test run 2026-10-14T19:13:29Z. Result made 2026-10-14T19:32:52Z. Roads: OpenStreetMap retrieved 2026-07-10T02:46:49Z. Residents: WorldPop 2020 (modelled).
- เวลาของข้อมูล: ภาพเรดาร์ 2025-07-28 11:20 UTC (2025-07-28 18:20 เวลาประเทศไทย) Sentinel-1C วงโคจรสัมพัทธ์ 99 ห่างจากวันอ้างอิงของกรณี (2025-07-28) 0 วัน ทดสอบเมื่อ 2026-10-14T19:13:29Z จัดทำผลเมื่อ 2026-10-14T19:32:52Z ถนน: OpenStreetMap ดึงข้อมูลเมื่อ 2026-07-10T02:46:49Z ผู้อยู่อาศัย: WorldPop 2020 (ค่าจากแบบจำลอง)
- Confidence: 0 of 35 tambons medium, 35 low. Class in effect: E in 35. Would-be class (not binding): E in 33; 2 have no score, so no would-be class. High confidence is never given in this release. / ความเชื่อมั่น: ปานกลาง 0 ตำบล ต่ำ 35 ตำบล จากทั้งหมด 35 ตำบล ระดับที่มีผล: E 35 ตำบล ระดับที่จะได้ (ไม่มีผล): E 33 ตำบล ไม่มีคะแนน 2 ตำบล จึงไม่มีระดับที่จะได้ รุ่นนี้ไม่มีการให้ความเชื่อมั่นระดับสูง

| Tambon / ตำบล | FPPS / คะแนน | Class / ระดับ | Binding or would-be / มีผลหรือจะได้ | Confidence / ความเชื่อมั่น | No answer / ไม่มีคำตอบ | Reason / เหตุผล | Holds / คงเดิม |
|---|---|---|---|---|---|---|---|
| Nam Muap / น้ำมวบ | 28.0 | E | would-be / จะได้ | low / ต่ำ | 0.7% | C1 | 87% |
| Khueng / ขึ่ง | 24.1 | E | would-be / จะได้ | low / ต่ำ | 1.4% | C1 | 100% |
| Muang Tuet / ม่วงตึ๊ด | 24.1 | E | would-be / จะได้ | low / ต่ำ | 14% | C1 C4 | 100% |
| Tha Nao / ท่าน้าว | 22.4 | E | would-be / จะได้ | low / ต่ำ | 5.8% | C1 C4 | 100% |
| Klang Wiang / กลางเวียง | 15.6 | E | would-be / จะได้ | low / ต่ำ | 6.9% | C1 | 100% |
| Tan Chum / ตาลชุม | 13.6 | E | would-be / จะได้ | low / ต่ำ | 8.2% | C1 | 100% |
| Nam Pua / น้ำปั้ว | 12.2 | E | would-be / จะได้ | low / ต่ำ | 8.7% | C1 | 100% |
| Mae Sa / แม่สา | 11.9 | E | would-be / จะได้ | low / ต่ำ | 3.1% | C1 | 100% |
| Thuem Tong / ถืมตอง | 10.5 | E | would-be / จะได้ | low / ต่ำ | 10% | C1 | 100% |
| Chom Chan / จอมจันทร์ | 10.2 | E | would-be / จะได้ | low / ต่ำ | 0.6% | C1 | 100% |
| Kong Khwai / กองควาย | 10.1 | E | would-be / จะได้ | low / ต่ำ | 5.8% | C1 | 100% |
| San / ส้าน | 9.8 | E | would-be / จะได้ | low / ต่ำ | 1.7% | C1 | 100% |
| Lai Nan / ไหล่น่าน | 9.7 | E | would-be / จะได้ | low / ต่ำ | 0.6% | C1 | 100% |
| Na Lueang / นาเหลือง | 9.6 | E | would-be / จะได้ | low / ต่ำ | 4.7% | C1 | 100% |
| Chai Sathan / ไชยสถาน | 9.4 | E | would-be / จะได้ | low / ต่ำ | 16% | C1 | 100% |
| Na Pang / นาปัง | 9.2 | E | would-be / จะได้ | low / ต่ำ | 6.6% | C1 | 100% |
| Pong Sanuk / ปงสนุก | 9.2 | E | would-be / จะได้ | low / ต่ำ | 2.0% | C1 | 100% |
| Du Tai / ดู่ใต้ | 9.2 | E | would-be / จะได้ | low / ต่ำ | 9.8% | C1 | 100% |
| Ai Na Lai / อ่ายนาไลย | 8.7 | E | would-be / จะได้ | low / ต่ำ | 2.5% | C1 | 100% |
| Mae Sakhon / แม่สาคร | 8.0 | E | would-be / จะได้ | low / ต่ำ | 2.3% | C1 | 100% |
| Thung Si Thong / ทุ่งศรีทอง | 8.0 | E | would-be / จะได้ | low / ต่ำ | 1.9% | C1 | 100% |
| Yap Hua Na / ยาบหัวนา | 7.9 | E | would-be / จะได้ | low / ต่ำ | 0.9% | C1 C7 | 100% |
| Rueang / เรือง | 5.9 | E | would-be / จะได้ | low / ต่ำ | 1.1% | C1 | 100% |
| Fai Kaeo / ฝายแก้ว | 5.8 | E | would-be / จะได้ | low / ต่ำ | 1.4% | C1 | 100% |
| Bo Suak / บ่อสวก | 5.5 | E | would-be / จะได้ | low / ต่ำ | 1.7% | C1 | 100% |
| Nam Kian / น้ำเกี๋ยน | 5.5 | E | would-be / จะได้ | low / ต่ำ | 1.6% | C1 | 100% |
| Nam Kaen / น้ำแก่น | 5.3 | E | would-be / จะได้ | low / ต่ำ | 0.8% | C1 | 100% |
| Mueang Chang / เมืองจัง | 5.3 | E | would-be / จะได้ | low / ต่ำ | 1.3% | C1 | 100% |
| Nai Wiang / ในเวียง | 4.8 | E | would-be / จะได้ | low / ต่ำ | 35% | C1 C3 C4 | 100% |
| Na Sao / นาซาว | 4.3 | E | would-be / จะได้ | low / ต่ำ | 3.8% | C1 | 100% |
| Sanian / สะเนียน | 4.0 | E | would-be / จะได้ | low / ต่ำ | 1.0% | C1 | 100% |
| Bo / บ่อ | 3.6 | E | would-be / จะได้ | low / ต่ำ | 0.7% | C1 | 100% |
| Pha Sing / ผาสิงห์ | 3.6 | E | would-be / จะได้ | low / ต่ำ | 1.9% | C1 | 100% |
| Sanna Nong Mai / ส้านนาหนองใหม่ | n/a | E | binding / มีผล | low / ต่ำ | 0.2% | C1 C5 | 100% |
| Mae Khaning / แม่ขะนิง | n/a | E | binding / มีผล | low / ต่ำ | 1.1% | C1 C5 | 100% |

- Binding: the class stands at its confidence. Would-be (striped): confidence is low, so the class in effect is E; the class shown is what the score would give at medium confidence, never binding. Check on the ground first. / มีผล: ระดับนี้ใช้ได้ตามความเชื่อมั่นที่ระบุ  จะได้ (ลายทาง): ความเชื่อมั่นต่ำ ระดับที่มีผลจึงเป็น E ส่วนระดับที่แสดงคือระดับที่คะแนนจะให้หากความเชื่อมั่นปานกลาง ไม่มีผลบังคับใช้ ควรตรวจสอบในพื้นที่ก่อน
- Holds: the share of the ensemble's runs that keep the class shown (a would-be class: at medium confidence). * under 60%: verify before use. / คงเดิม: สัดส่วนของรอบการคำนวณที่ให้ระดับเดียวกับที่แสดง (ระดับที่จะได้: เมื่อความเชื่อมั่นปานกลาง) * ต่ำกว่า 60%: ควรตรวจสอบก่อนใช้งาน
- No answer: the share of the tambon's land outside permanent water where the radar map gives no answer, such as trees or buildings on low ground. / ไม่มีคำตอบ: สัดส่วนพื้นที่ของตำบล (ไม่รวมแหล่งน้ำถาวร) ที่แผนที่เรดาร์ไม่ให้คำตอบ เช่น ต้นไม้หรือสิ่งปลูกสร้างบนที่ต่ำ

### What each class asks / แต่ละระดับหมายถึงอะไร

- **E: Monitor and verify / ติดตามและตรวจสอบ.** Lower relative priority on this radar pass, or low confidence. Keep watching and check on the ground. / ลำดับความสำคัญต่ำกว่าเมื่อเทียบกันจากภาพเรดาร์รอบนี้ หรือความเชื่อมั่นต่ำ เฝ้าติดตามและตรวจสอบในพื้นที่

**Class E never means safe. It means lower relative priority, or low confidence, in this case.** / **ระดับ E ไม่ได้หมายความว่าปลอดภัย หมายถึงลำดับความสำคัญต่ำกว่าเมื่อเทียบกัน หรือความเชื่อมั่นต่ำ ในกรณีนี้**

### Conditions not met / เงื่อนไขที่ไม่ผ่าน

- C1: the case test, or the tambon's own radar answer: no answer on over 20% of its land, an answer on under 80%, or a pass over 3 days from the case reference date. / C1: ผลการทดสอบของกรณี หรือคำตอบจากเรดาร์ของตำบลเอง: ไม่มีคำตอบเกิน 20% ของพื้นที่ มีคำตอบน้อยกว่า 80% หรือภาพเรดาร์ห่างจากวันอ้างอิงของกรณีเกิน 3 วัน
- C3: less than 80% of the tambon's land has an answer. / C3: พื้นที่ของตำบลที่มีคำตอบน้อยกว่า 80%
- C4: the share of residents inside the mapped water moves by over 15 points when the map grows or shrinks by one 20 m cell. / C4: สัดส่วนผู้อยู่อาศัยในพื้นที่น้ำท่วมเปลี่ยนเกิน 15 จุด เมื่อขยายหรือหดแผนที่หนึ่งเซลล์ (20 ม.)
- C5: a component of the score could not be computed. / C5: องค์ประกอบบางส่วนของคะแนนคำนวณไม่ได้
- C7: more than 10% of the connected residents have no modelled road route to a hospital even without flooding. / C7: ผู้อยู่อาศัยที่เชื่อมกับโครงข่ายถนนเกิน 10% ไม่มีเส้นทางถนนไปโรงพยาบาลตามแบบจำลองแม้ไม่มีน้ำท่วม

### Stability / ความเสถียร

- Stability over the ensemble (report-only): 180 runs of the chain, every combination of the flood map (3 levels), the closure level (3), the population data (2: WorldPop 2020 and its 2024 rescale), the vulnerability anchors (2) and the weights (5). / ความเสถียรจากชุดการคำนวณ (รายงานเท่านั้น): คำนวณซ้ำ 180 รอบ ทุกชุดค่าผสมของแผนที่น้ำท่วม (3 ระดับ) ระดับการปิดถนน (3) ข้อมูลประชากร (2: WorldPop 2020 และที่ปรับเป็นปี ค.ศ. 2024) เกณฑ์ความเปราะบาง (2) และชุดน้ำหนัก (5)
- The class shown holds in at least 60% of the runs for all 35 tambons. / ระดับที่แสดงคงเดิมอย่างน้อย 60% ของรอบในทั้ง 35 ตำบล
- Counting every no-answer cell as flooded changes the class read in 20 of 35 tambons (report only): the low scores rest on counting no answer as not flooded. / หากนับเซลล์ที่ไม่มีคำตอบทั้งหมดเป็นน้ำท่วม ระดับที่อ่านได้จะเปลี่ยนใน 20 จาก 35 ตำบล (รายงานเท่านั้น) คะแนนที่ต่ำจึงขึ้นกับการนับเซลล์ที่ไม่มีคำตอบว่าไม่ท่วม

### Assumptions / สมมติฐาน

- One flood input drives 4 of 5 components (90% of weight). / ข้อมูลน้ำท่วมชุดเดียวกำหนดองค์ประกอบ 4 ใน 5 ของคะแนน (90% ของน้ำหนัก)
- Road closures are modelled from the radar map by closure rule v1. No closure was observed. / การปิดถนนเป็นการจำลองจากแผนที่เรดาร์ตามกฎการปิดถนน v1 ไม่ใช่การปิดถนนที่สังเกตได้จริง
- Residents are modelled counts (WorldPop 2020). / จำนวนผู้อยู่อาศัยเป็นค่าจากแบบจำลอง (WorldPop 2020)
- The radar map is the project's own map, frozen before the test and used as computed. Where the radar gives no answer, a cell counts as not flooded. / แผนที่เรดาร์เป็นแผนที่ของโครงการเอง ตรึงค่าไว้ก่อนการทดสอบและใช้ตามที่คำนวณได้ เซลล์ที่เรดาร์ไม่มีคำตอบนับว่าไม่ท่วม
- Radar does not see water under trees, between buildings or under crops, nor water that drained before the pass. / เรดาร์มองไม่เห็นน้ำใต้ต้นไม้ ระหว่างอาคาร หรือใต้พืชผล และน้ำที่ระบายไปแล้วก่อนดาวเทียมโคจรผ่าน
- Every test figure is agreement with another map, not a ground check. The score is not accepted for decisions (accepted_fpps stays null). / ตัวเลขผลการทดสอบทุกตัวเป็นความสอดคล้องกับแผนที่อื่น ไม่ใช่การตรวจสอบภาคสนาม คะแนนนี้ยังไม่ได้รับการยอมรับให้ใช้ตัดสินใจ (accepted_fpps เป็นค่าว่าง)

In an emergency follow the announcements of the DDPM and the Thai Meteorological Department. / ในเหตุฉุกเฉินโปรดปฏิบัติตามประกาศของกรมป้องกันและบรรเทาสาธารณภัย (ปภ.) และกรมอุตุนิยมวิทยา

---

Credits: Flood map: Contains modified Copernicus Sentinel data (2025), processed by FloodGuard (Copernicus Sentinel data, free, full and open access (Copernicus data policy)). Test 1 reference: JAXA ALOS-2 Flood Proxy Map, Provided by JAXA (Sentinel Asia): only figures computed from it are shown, no part of the map. Dry control: the area of a THEOS-2 image of 31 July 2025 (GISTDA sample), figures only. Roads © OpenStreetMap contributors (ODbL 1.0); residents WorldPop 2020 and age counts 2024 (CC BY 4.0); permanent water ESA WorldCover 2021 (CC BY 4.0); boundaries HDX Thailand COD-AB.

Made from `outputs/nan_case/planning_result_n1_nan_v1.json` (SHA-256 `903d96df99b357f12ce3e79e40eb11c13f1416c16fa3ccdb6d9fdb726342ef7c`); `outputs/nan_case/test_1_jaxa_v1.json` (SHA-256 `a823139f833bfcc6d54c8543e3fc596f5c9f172bb990e9e23d9dfc3362e8ce06`); `outputs/nan_case/test_result_v1.json` (SHA-256 `6f67d4e37d8a98d28b5a48e19a88263122a2540ffd2b2aed46b55dd9200eab89`); `outputs/nan_case/post_test_reasons_v1.json` (SHA-256 `0bd45cdd4827765a64f2b820113a0b8c36430a0dc5be1269b1417b71cc153148`); `outputs/nan_case/planning_result_n1_nan_v1_record.json` (SHA-256 `36c5d7afc304da4b005bd83b4d54165e3b70c699dbbd051557ff0f872636c991`).

Thai text written by the project's assistant; not reviewed by a native speaker. / ข้อความภาษาไทยเขียนโดยผู้ช่วยของโครงการ ยังไม่ได้ตรวจทานโดยเจ้าของภาษา
