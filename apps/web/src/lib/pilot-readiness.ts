import type { PilotReadiness } from "@floodguard/contracts";

import type { Language } from "./types";

export interface PilotReadinessCopy {
  title: string;
  status: string;
  identity: string;
  acceptance: string;
  audit: string;
  retention: string;
  protocol: string;
  reason: string;
  boundary: string;
}

export function pilotReadinessCopy(
  readiness: PilotReadiness,
  language: Language,
): PilotReadinessCopy {
  const th = language === "th";
  return {
    title: th ? "ความพร้อมโครงการนำร่องหน่วยงาน" : "Bounded agency pilot",
    status: th
      ? readiness.agency_operational_allowed
        ? "มีใบรับรองที่ตรวจสอบแล้ว"
        : "ยังไม่อนุญาตให้ปฏิบัติการ"
      : readiness.agency_operational_allowed
        ? "Verified acceptance receipt"
        : "Not authorized for operation",
    identity: th ? "ข้อมูลประจำตัว" : "Identity",
    acceptance: th ? "ใบรับรองการยอมรับ" : "Acceptance receipt",
    audit: th ? "บันทึกตรวจสอบ" : "Audit chain",
    retention: th ? "การเก็บรักษา" : "Retention",
    protocol: th ? "ระเบียบตรวจสอบภาคสนาม" : "Field protocol",
    reason: th ? readiness.reason_blocked_th : readiness.reason_blocked_en,
    boundary: th
      ? "การแสดงบทบาทในหน้านี้ไม่ใช่การอนุญาต API จะตรวจสิทธิ์ซ้ำทุกคำขอ"
      : "Role display is not authorization; the API rechecks every protected request.",
  };
}
