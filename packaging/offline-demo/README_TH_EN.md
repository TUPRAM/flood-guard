# FloodGuard Thailand - Offline Proposal Demo

## ภาษาไทย

ชุดสาธิตนี้เป็นข้อมูลตัวอย่างสำหรับการวางแผนเท่านั้น ไม่ใช่ระบบปฏิบัติการ ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ และไม่ใช่ระบบนำทางอพยพแบบสด

วิธีเปิดใช้งานบน Windows:

1. แตกไฟล์ ZIP ทั้งหมด
2. คลิกขวา `serve-demo.ps1` แล้วเลือก **Run with PowerShell** หรือเปิด PowerShell ในโฟลเดอร์นี้แล้วรัน `./serve-demo.ps1`
3. เปิด `http://127.0.0.1:8000/public/`

หน้าสาธิต:

- ประชาชน: `http://127.0.0.1:8000/public/`
- ศูนย์บัญชาการ: `http://127.0.0.1:8000/command/`
- สตูดิโอข้อมูลและ GeoAI: `http://127.0.0.1:8000/studio/`

ข้อมูลและทรัพยากรของหน้าเว็บรวมอยู่ในชุดนี้ การติดต่อสายด่วนหรือการเปิดเว็บไซต์อ้างอิงยังต้องใช้อินเทอร์เน็ตและเป็นการกระทำของผู้ใช้โดยตรง

## English

This bundle is a fixture-backed planning demonstration. It is non-operational, is not an official warning, and is not a live evacuation navigator.

To run on Windows:

1. Extract the complete ZIP.
2. Right-click `serve-demo.ps1` and choose **Run with PowerShell**, or run `./serve-demo.ps1` from PowerShell in this directory.
3. Open `http://127.0.0.1:8000/public/`.

Demo routes:

- Public preparedness: `http://127.0.0.1:8000/public/`
- Planning command center: `http://127.0.0.1:8000/command/`
- Data and GeoAI studio: `http://127.0.0.1:8000/studio/`

All application data and rendering assets are bundled locally. Following a hotline or reference website link still requires a network connection and is an explicit user action.

The bundle manifest, `offline-bundle-manifest.json`, records the exact Git commit and SHA-256 checksum of every packaged file.
