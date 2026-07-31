import type { EvidenceDecisionRow, EvidenceDecisionStage } from "@/lib/studio-evidence";
import type { Language, ReadinessRow } from "@/lib/types";

const DECISION_REASON_TH: Record<
  EvidenceDecisionStage,
  Partial<Record<EvidenceDecisionRow["state"], string>>
> = {
  processing_execution: {
    recorded: "แพ็กเกจหลักฐานมี checksum มาตรฐานสำหรับตรวจสอบความสมบูรณ์",
    not_recorded: "ยังไม่มีการบันทึกแพ็กเกจหลักฐานที่มี checksum",
  },
  technical_verification: {
    recorded: "มีการประเมินที่ตรวจสอบด้วย checksum และผูกกับบริบทหลักฐานนี้",
    not_recorded: "ยังไม่มีการประเมินโมเดลที่ตรวจสอบด้วย checksum และผูกกับบริบทหลักฐานนี้",
  },
  observed_event_validation: {
    recorded: "มีบันทึกการยืนยันเหตุการณ์ด้วยข้อมูลสังเกตการณ์สำหรับบริบทหลักฐานนี้",
    not_recorded: "ยังไม่มีบันทึกการยืนยันเหตุการณ์ด้วยข้อมูลสังเกตการณ์สำหรับบริบทหลักฐานนี้",
  },
  governance_decision: {
    recorded: "มีการบันทึกผู้มีอำนาจตัดสินใจและเวลาตัดสินใจ",
    not_recorded: "ยังไม่มีการบันทึกผู้มีอำนาจตัดสินใจและเวลาตัดสินใจ",
  },
  operational_authorization: {
    authorized: "บันทึกหลักฐานอนุญาตให้ใช้งานเชิงปฏิบัติการอย่างชัดเจน",
    blocked: "บันทึกหลักฐานไม่ได้อนุญาตให้ใช้งานเชิงปฏิบัติการ",
  },
};

const READINESS_REASON_TH: Record<string, string> = {
  facility_verification: "หน่วยงานยังไม่ได้ยืนยันบทบาทฉุกเฉิน การเปิดให้บริการ ความจุ และการเข้าถึงสถานที่",
  segment_raster_intersection: "ข้อมูลความเสี่ยงถนนปัจจุบันมาจากข้อมูลสรุประดับพื้นที่ และยังไม่ผ่านการรับรองการเชื่อมโยงความน่าจะเป็นระดับช่วงถนน",
  reference_mask: "ข้อมูลอ้างอิงที่มีอยู่ยังไม่ผ่านเกณฑ์เป็นข้อมูลจริงสำหรับยืนยันเหตุการณ์น้ำท่วมในประเทศไทย",
  reviewer_calibration: "ยังไม่มีใบรับรองการปรับเทียบและการตัดสินโดยผู้ตรวจสอบแบบปกปิดที่ผ่านเกณฑ์",
  sentinel1_provenance: "ยังระบุรหัสผลิตภัณฑ์และเวลารับข้อมูล Sentinel-1 ได้ไม่ครบถ้วน",
  geographic_generalization: "ข้อมูลอ้างอิงเพียงฉากเดียวยังยืนยันการใช้ผลกับเหตุการณ์หรือลุ่มน้ำอื่นไม่ได้",
  weak_reference_seed_scope: "ยังไม่มีข้อมูลอ้างอิงเหตุการณ์ในพื้นที่ที่ผ่านเกณฑ์พร้อมบันทึกสิทธิ์ใช้งาน",
  cleared_training_labels: "ยังไม่มีใบรับรองการอนุมัติป้ายกำกับฝึกสอนที่ตรวจสอบได้",
  reviewer_calibration_complete: "ยังไม่มีใบรับรองการปรับเทียบผู้ตรวจสอบอิสระที่ผ่านเกณฑ์",
  blind_double_review: "ยังไม่มีบันทึกการตรวจสอบซ้ำแบบปกปิดและเป็นอิสระที่ครบถ้วน",
  immutable_training_labelset: "ยังไม่มีใบรับรองชุดป้ายกำกับแบบคงที่พร้อม checksum",
  query_model_safety_boundary: "ยังไม่มีใบรับรองการแยกข้อมูลฝึกสอนและข้อมูลประเมินที่ตรวจสอบโดยอิสระ",
};

const READINESS_READY_TH: Record<string, string> = {
  real_open_context: "มีบันทึกแหล่งข้อมูลเปิดและที่มาที่ตรวจสอบความสมบูรณ์ได้",
  canonical_projected_grid: "การจัดแนวกริดฉายภาพผ่านการตรวจสอบที่ทำซ้ำได้",
};

const BLOCKER_TH: Record<string, string> = {
  "No qualified Thailand event-flood reference evaluation is published.": "ยังไม่มีการเผยแพร่ผลประเมินอ้างอิงเหตุการณ์น้ำท่วมในประเทศไทยที่ผ่านเกณฑ์",
  "Facility roles and current operation are not agency verified.": "หน่วยงานยังไม่ได้ยืนยันบทบาทและการเปิดให้บริการปัจจุบันของสถานที่",
  "Road evidence is area-summary context, not segment-raster intersection.": "หลักฐานถนนเป็นบริบทสรุประดับพื้นที่ ไม่ใช่การเชื่อมโยงช่วงถนนกับราสเตอร์",
  "No agency operational acceptance is recorded.": "ยังไม่มีการบันทึกการยอมรับให้ใช้งานเชิงปฏิบัติการจากหน่วยงาน",
};

export function decisionReasonPresentation(row: EvidenceDecisionRow, language: Language): string {
  if (language === "en") return row.reason;
  return DECISION_REASON_TH[row.stage][row.state]
    ?? "สถานะนี้มาจากบันทึกหลักฐานที่ผูกกับบริบทนี้";
}

export function readinessReasonPresentation(row: ReadinessRow, language: Language): string {
  if (language === "en") return row.reason_blocked;
  if (row.status === "ready") {
    return READINESS_READY_TH[row.check_id]
      ?? "มีบันทึกหลักฐานตามข้อกำหนดนี้แล้ว";
  }
  return READINESS_REASON_TH[row.check_id]
    ?? "หลักฐานที่จำเป็นสำหรับข้อกำหนดนี้ยังไม่ครบถ้วน";
}

export function blockerPresentation(blocker: string, language: Language): string {
  if (language === "en") return blocker;
  return BLOCKER_TH[blocker]
    ?? "มีข้อจำกัดเพิ่มเติมที่บันทึกไว้ในหลักฐานฉบับมาตรฐาน";
}
