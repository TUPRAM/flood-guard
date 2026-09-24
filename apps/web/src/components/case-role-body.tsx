"use client";

import { useSyncExternalStore } from "react";
import { readCaseSelection } from "@/lib/case-selection";
import { useLanguage } from "@/lib/use-language";
import { CommandWorkspace } from "./command-workspace";
import { EvidenceLibrary } from "./evidence-library";
import { StudioWorkspace } from "./studio-workspace";
import styles from "./candidate-case-context.module.css";

/** Keep a deep-linked case on its own verified evidence path. */
function subscribeCaseUrl(notify: () => void) {
  window.addEventListener("popstate", notify);
  return () => window.removeEventListener("popstate", notify);
}
function hasExplicitCase() {
  const selection = readCaseSelection(window.location.search);
  return Boolean(selection.aoi || selection.event || selection.version || selection.service || selection.mode || selection.scenario || selection.origin);
}
export function CaseRoleBody({ role }: { role: "planning" | "studio" }) {
  const [language] = useLanguage("en");
  const th = language === "th";
  const explicitCase = useSyncExternalStore(subscribeCaseUrl, hasExplicitCase, () => false);

  if (explicitCase) {
    return role === "planning" ? <EvidenceLibrary view="brief" role="planning" /> : <>
      <p className={styles.scopeNote}>{th ? "กรณีที่เลือกเป็นชุดหลักฐานผู้สมัคร ข้อมูลแหล่งที่มา ความเชื่อมั่น ค่าคะแนนที่ยังขาด และที่มาด้านล่างเป็นของพื้นที่และเหตุการณ์นี้เท่านั้น ผลตรวจสอบทางเทคนิคแม่สายอีกชุดไม่ได้รับรองกรณีนี้" : "The selected case is a candidate evidence package. Source review, confidence, missing score inputs and provenance below belong to that exact area and event. A separate Mae Sai technical baseline does not validate this selected package."}</p>
      <EvidenceLibrary view="evidence" role="studio" />
    </>;
  }
  return role === "planning" ? <><p className={styles.scopeNote}>{th ? "พื้นที่วางแผนแม่สายย้อนหลังด้านล่างใช้บริบทหลักฐานของตนเอง เลือกกรณีด้านบนเพื่อเปิดผลเปรียบเทียบที่ตรวจสอบ checksum แล้ว" : "The historical Mae Sai planning workspace below has its own evidence context. Select a case above to open its checksum-verified comparison."}</p><CommandWorkspace /></> : <><p className={styles.scopeNote}>{th ? "รายงานทางเทคนิคด้านล่างเป็นบริบทหลักฐานแม่สายเดิม เลือกกรณีด้านบนเพื่อตรวจสอบแพ็กเกจผู้สมัครของกรณีนั้น รายงานนี้ไม่ได้อนุมัติแพ็กเกจดังกล่าว" : "The technical report below is the existing Mae Sai evidence context. Select a case above to inspect its own candidate package; this report does not grant that package acceptance."}</p><StudioWorkspace /></>;
}
