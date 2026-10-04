"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import type { EvidenceLibraryCatalog } from "@floodguard/contracts";

import {
  EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES, evidenceActivity, megabyteLabel, readEvidenceAreas, removeEvidenceArea, saveEvidenceArea,
  subscribeEvidenceActivity, WORKER_INSTALL_WAIT_MS,
  type EvidenceAreaStatus, type EvidenceAreaWork, type EvidencePackageFailure,
} from "@/lib/evidence-offline";
import { useOnline } from "@/lib/use-online";

import styles from "./evidence-offline.module.css";

export { useOnline };

/**
 * A counter that advances when the connection returns while `waiting` is true. A page adds it to the dependencies of
 * the effect that loads a package, so a package that could not be reached is requested again once the device is online.
 */
export function useRetryWhenOnline(waiting: boolean): number {
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!waiting) return;
    const retry = () => setAttempt((value) => value + 1);
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [waiting]);
  return attempt;
}

const SAVE_LABEL = { en: "Save this area for offline use", th: "บันทึกพื้นที่นี้ไว้ใช้แบบออฟไลน์" } as const;
/** The size up to which a study area is saved when it is opened, as shown to the reader ("20 MB"). */
const SAVE_ON_OPEN_LIMIT = megabyteLabel(EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES);

/**
 * Why a study area's package is not shown. Offline with no saved copy, the page says exactly that and shows nothing
 * of the package; `brief` is the one-line form for a second block on the same page.
 */
export function EvidencePackageNotice({ failure, th, className, invalidLabel, brief = false }: {
  failure: EvidencePackageFailure; th: boolean; className?: string; invalidLabel: string; brief?: boolean;
}) {
  if (failure.kind === "invalid") return <p className={className} role="alert">{invalidLabel}: {failure.message}</p>;
  const offline = failure.kind === "offline_not_saved";
  const text = brief
    ? offline
      ? (th ? "ไม่แสดงผล: ขณะนี้ออฟไลน์ และยังไม่ได้บันทึกพื้นที่ศึกษานี้ไว้ในอุปกรณ์" : "Not shown: you are offline, and this study area is not saved on this device.")
      : (th ? "ไม่แสดงผล: เข้าถึงข้อมูลของพื้นที่ศึกษานี้ไม่ได้ และยังไม่ได้บันทึกไว้ในอุปกรณ์" : "Not shown: this study area's data could not be reached, and it is not saved on this device.")
    : offline
      ? (th
        ? `ขณะนี้ออฟไลน์ และยังไม่ได้บันทึกพื้นที่ศึกษานี้ไว้ในอุปกรณ์ จึงไม่แสดงข้อมูลของพื้นที่นี้ เชื่อมต่ออินเทอร์เน็ตเพื่อเปิดดู เมื่อเปิดดูขณะเชื่อมต่อ พื้นที่นี้จะถูกบันทึกไว้ในอุปกรณ์ ส่วนพื้นที่ที่ใหญ่กว่า ${SAVE_ON_OPEN_LIMIT} จะบันทึกเมื่อเลือก “${SAVE_LABEL.th}”`
        : `You are offline, and this study area is not saved on this device, so none of its data is shown. Connect to the internet to open it. Opening it while connected saves it on this device; an area larger than ${SAVE_ON_OPEN_LIMIT} is saved when you choose “${SAVE_LABEL.en}”.`)
      : (th
        ? "ไม่สามารถเข้าถึงข้อมูลของพื้นที่ศึกษานี้ได้ และยังไม่ได้บันทึกไว้ในอุปกรณ์ จึงไม่แสดงข้อมูลของพื้นที่นี้ ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
        : "This study area's data could not be reached, and it is not saved on this device, so none of its data is shown. Check the connection and try again.");
  return <p className={className} role={brief ? "status" : "alert"} data-evidence-unavailable={failure.kind}>{text}</p>;
}

/**
 * The offline copy of a study area: its saved state, the reader's request to keep it ("Save this area for offline
 * use") and its removal. An area up to 20 MB is saved when it is opened while connected, so the control then shows
 * that save and its result; a larger one is saved with the button. With `list`, every study area of the catalogue is
 * listed below the selected one. Renders nothing until the service worker has answered (and nothing at all where no
 * worker runs).
 */
export function EvidenceOfflineControl({ catalog, aoiId, th, list = false, className }: {
  catalog: EvidenceLibraryCatalog; aoiId: string | null | undefined; th: boolean; list?: boolean; className?: string;
}) {
  const online = useOnline();
  const [areas, setAreas] = useState<EvidenceAreaStatus[] | null>(null);
  // Saves and removals of this page view, whoever started them: the reader here, or opening the area.
  const activity = useSyncExternalStore(subscribeEvidenceActivity, evidenceActivity, evidenceActivity);

  useEffect(() => {
    let active = true;
    // On a first visit the worker may still be installing: the control appears once it is active. Areas share a
    // file (the report), so every area's state is read again when a save or a removal starts or ends.
    readEvidenceAreas(WORKER_INSTALL_WAIT_MS).then((next) => { if (active) setAreas(next); }).catch(() => undefined);
    return () => { active = false; };
  }, [online, activity]);

  const change = useCallback((id: string, action: EvidenceAreaWork) => {
    void (action === "saving" ? saveEvidenceArea(id) : removeEvidenceArea(id));
  }, []);

  if (!areas) return null;
  const selected = aoiId ? areas.find((area) => area.aoiId === aoiId) : undefined;
  const listed = list ? areas.filter((area) => area.total > 0 && catalog.aois.some((aoi) => aoi.id === area.aoiId)) : [];
  if ((!selected || selected.total === 0) && listed.length === 0) return null;
  const areaName = (id: string) => {
    const aoi = catalog.aois.find((item) => item.id === id);
    return (th ? aoi?.name_th ?? aoi?.name : aoi?.name) ?? id;
  };

  const row = (status: EvidenceAreaStatus, named: boolean) => {
    const working = activity.busy[status.aoiId];
    const failed = activity.failed[status.aoiId] ?? 0;
    const interrupted = activity.interrupted[status.aoiId];
    const onRequestOnly = status.bytes > EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES;
    const size = megabyteLabel(status.bytes);
    const name = areaName(status.aoiId);
    const message = working === "saving"
      ? (th ? "กำลังบันทึกและตรวจสอบแต่ละไฟล์…" : "Saving and checking each file…")
      : working === "removing"
        ? (th ? "กำลังลบสำเนาที่บันทึกไว้…" : "Removing the saved copy…")
        : status.state === "saved"
          ? (th ? `บันทึกไว้ในอุปกรณ์นี้แล้ว: ${status.total} ไฟล์ ${size} ทุกไฟล์ตรงกับค่า SHA-256 ของตน` : `Saved on this device: ${status.total} files, ${size}. Each file matched its SHA-256.`)
          : status.state === "partial"
            ? (th ? `สำเนาที่บันทึกไว้ไม่ครบหรือเป็นรุ่นเก่า: ${status.cached} จาก ${status.total} ไฟล์ จึงยังเปิดแบบออฟไลน์ไม่ได้` : `Saved copy incomplete or out of date: ${status.cached} of ${status.total} files. It does not open offline yet.`)
            : (th ? "ยังไม่ได้บันทึกไว้ในอุปกรณ์นี้ เปิดดูได้เฉพาะเมื่อมีการเชื่อมต่อ" : "Not saved on this device. It opens only with a connection.");
    return <div key={status.aoiId} className={styles.row} data-evidence-offline-area={status.aoiId} data-state={working ?? status.state}
      data-interrupted={!working && interrupted ? interrupted : undefined}>
      <p className={styles.state} role="status" aria-live="polite">
        {named ? <strong>{name}</strong> : <strong>{th ? "สำเนาออฟไลน์" : "Offline copy"}</strong>}
        <span>{message}</span>
        {!working && status.state === "none" && onRequestOnly ? <span>{th
          ? `พื้นที่นี้ใหญ่กว่า ${SAVE_ON_OPEN_LIMIT} จึงบันทึกเฉพาะเมื่อคุณสั่ง`
          : `This area is larger than ${SAVE_ON_OPEN_LIMIT}, so it is saved only when you ask.`}</span> : null}
        {!working && interrupted ? <span className={styles.failed}>{interrupted === "saving"
          ? (th ? "การบันทึกหยุดก่อนเสร็จสิ้น ไฟล์ที่ผ่านการตรวจสอบแล้วยังเก็บไว้ โปรดลองอีกครั้งขณะเชื่อมต่อ" : "The save stopped before it finished. Files that passed their check are kept. Try again while connected.")
          : (th ? "การลบหยุดก่อนเสร็จสิ้น โปรดลองอีกครั้ง" : "The removal stopped before it finished. Try again.")}</span> : null}
        {!working && failed > 0 ? <span className={styles.failed}>{th
          ? `${failed} จาก ${status.total} ไฟล์ดาวน์โหลดไม่ได้หรือไม่ตรงกับค่า SHA-256 จึงไม่ได้บันทึก`
          : `${failed} of ${status.total} files could not be downloaded or did not match their SHA-256, and were not saved.`}</span> : null}
        {!working && status.state !== "saved" && !online ? <span>{th ? "เชื่อมต่ออินเทอร์เน็ตเพื่อบันทึกพื้นที่นี้" : "Connect to the internet to save this area."}</span> : null}
      </p>
      <div className={styles.actions}>
        {status.state !== "saved" ? <button type="button" data-action="save" disabled={Boolean(working) || !online}
          aria-label={named ? (th ? `บันทึก ${name} ไว้ใช้แบบออฟไลน์ (${size})` : `Save ${name} for offline use (${size})`) : undefined}
          onClick={() => change(status.aoiId, "saving")}>
          {named ? (th ? "บันทึกไว้ใช้แบบออฟไลน์" : "Save for offline use") : SAVE_LABEL[th ? "th" : "en"]} ({size})
        </button> : null}
        {status.state !== "none" ? <button type="button" data-action="remove" className={styles.secondary} disabled={Boolean(working)}
          aria-label={named ? (th ? `ลบสำเนาที่บันทึกไว้ของ ${name}` : `Remove the saved copy of ${name}`) : undefined}
          onClick={() => change(status.aoiId, "removing")}>
          {th ? "ลบสำเนาที่บันทึกไว้" : "Remove saved copy"}
        </button> : null}
      </div>
    </div>;
  };

  const savedCount = listed.filter((area) => area.state === "saved").length;
  return <section className={[styles.control, className].filter(Boolean).join(" ")} data-evidence-offline-control="true"
    aria-label={th ? "สำเนาออฟไลน์ของพื้นที่ศึกษา" : "Offline copies of study areas"}>
    {selected && selected.total > 0 ? row(selected, false) : null}
    <p className={styles.note}>{th
      ? `พื้นที่ศึกษาขนาดไม่เกิน ${SAVE_ON_OPEN_LIMIT} จะบันทึกไว้ในอุปกรณ์นี้เมื่อเปิดดูขณะเชื่อมต่อ ส่วนพื้นที่ที่ใหญ่กว่านั้นจะบันทึกเมื่อคุณสั่ง สำเนาที่คุณลบจะไม่ถูกบันทึกอีกจนกว่าคุณจะสั่ง สำเนาที่บันทึกมีข้อมูลหน้าเว็บ ภาพภูมิประเทศ และรายงานของพื้นที่นั้น ส่วนไฟล์ฐานข้อมูลสำหรับดาวน์โหลดไม่ได้บันทึกไว้และต้องใช้การเชื่อมต่อ`
      : `A study area up to ${SAVE_ON_OPEN_LIMIT} is saved on this device when you open it while connected; a larger one is saved when you ask. A copy you remove is not saved again until you ask. A saved copy holds the area's page data, terrain preview and report. The database files offered for download are not saved and need a connection.`}</p>
    {listed.length > 0 ? <details className={styles.list} data-evidence-offline-list="true">
      <summary>{th ? `พื้นที่ศึกษาทั้งหมด: บันทึกไว้ในอุปกรณ์นี้ ${savedCount} จาก ${listed.length} พื้นที่` : `All study areas: ${savedCount} of ${listed.length} saved on this device`}</summary>
      {listed.map((area) => row(area, true))}
    </details> : null}
  </section>;
}
