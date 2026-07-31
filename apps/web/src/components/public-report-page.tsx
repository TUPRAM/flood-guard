"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

import { PublicFloodHeightPicker } from "@/components/public-flood-height-picker";
import {
  PUBLIC_REPORT_NOTES_MAX_LENGTH,
  type PublicReportWaterDepth,
  publicReportDepthBand,
  publicReportWaterDepthLabel,
  reportsForPlanningArea,
  type PublicReportArea,
} from "@/lib/public-report";
import type { Language } from "@/lib/types";
import { usePublicReports } from "@/lib/use-public-reports";

interface PublicReportPageProps {
  language: Language;
  selectedArea?: PublicReportArea;
  areas: PublicReportArea[];
  onSelectArea: (areaId: string) => void;
}

const DEPTH_ICONS: Record<PublicReportWaterDepth, string> = {
  ankle: "≋",
  knee: "◉",
  waist: "≋",
  chest: "⌁",
};

/**
 * Illustrative feed entries showing how a community feed would read once
 * reports are shared beyond the device. Nothing here is an observation and no
 * report on this device is ever reviewed or confirmed by an authority, so the
 * block is fenced with data-example and labelled on screen. Never present these
 * as real reports, and never reuse this status vocabulary for stored reports.
 */
/**
 * The three stages a report moves through, shown on the placeholder "your
 * latest report" card. "done" stages are complete, "current" is where the
 * example report sits now, "pending" is still ahead.
 */
const REPORT_STATUS_STEPS = [
  { id: "received", en: "Received", th: "ได้รับแล้ว", state: "done" },
  { id: "verified", en: "Verified", th: "ตรวจสอบแล้ว", state: "current" },
  { id: "resolved", en: "Resolved", th: "แก้ไขแล้ว", state: "pending" },
] as const;

const FEED_EXAMPLES = [
  {
    id: "example-main-st",
    en: "Knee-deep water on Main St",
    th: "น้ำสูงระดับเข่าบนถนนสายหลัก",
    ageEn: "2 mins ago",
    ageTh: "2 นาทีที่แล้ว",
    statusEn: "Verified",
    statusTh: "ตรวจสอบแล้ว",
    tone: "confirmed",
  },
  {
    id: "example-school-drain",
    en: "Blocked drain near the school",
    th: "ท่อระบายน้ำอุดตันใกล้โรงเรียน",
    ageEn: "15 mins ago",
    ageTh: "15 นาทีที่แล้ว",
    statusEn: "Resolved",
    statusTh: "แก้ไขแล้ว",
    tone: "resolved",
  },
] as const;

export function PublicReportPage({
  language,
  selectedArea,
  areas,
  onSelectArea,
}: PublicReportPageProps) {
  const th = language === "th";
  const { reports, addReport } = usePublicReports();
  const [waterDepthCm, setWaterDepthCm] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [areaPickerOpen, setAreaPickerOpen] = useState(false);
  const photoPreviewUrlRef = useRef<string | null>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  const areaReports = useMemo(
    () => reportsForPlanningArea(reports, selectedArea?.area_id ?? ""),
    [reports, selectedArea?.area_id],
  );

  useEffect(() => {
    return () => {
      if (photoPreviewUrlRef.current) URL.revokeObjectURL(photoPreviewUrlRef.current);
    };
  }, []);

  const clearPhotoPreview = () => {
    if (photoPreviewUrlRef.current) {
      URL.revokeObjectURL(photoPreviewUrlRef.current);
      photoPreviewUrlRef.current = null;
    }
    setPhoto(null);
    setPhotoPreviewUrl(null);
    if (photoInputRef.current) photoInputRef.current.value = "";
  };

  const handlePhoto = (event: ChangeEvent<HTMLInputElement>) => {
    const nextPhoto = event.target.files?.[0] ?? null;
    if (photoPreviewUrlRef.current) {
      URL.revokeObjectURL(photoPreviewUrlRef.current);
      photoPreviewUrlRef.current = null;
    }
    setPhoto(null);
    setPhotoPreviewUrl(null);

    if (nextPhoto?.type.startsWith("image/")) {
      const previewUrl = URL.createObjectURL(nextPhoto);
      photoPreviewUrlRef.current = previewUrl;
      setPhoto(nextPhoto);
      setPhotoPreviewUrl(previewUrl);
    } else {
      event.target.value = "";
    }
    setFormMessage(null);
  };

  const submitReport = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!selectedArea) {
      setFormMessage(th
        ? "เลือกพื้นที่กว้างจากหน้าแรกก่อนบันทึกรายงาน"
        : "Choose a broad area on Home before saving a report.");
      return;
    }
    if (waterDepthCm === null) {
      setFormMessage(th ? "ตั้งระดับน้ำก่อนบันทึก" : "Set the water depth before saving.");
      return;
    }

    addReport({
      area: selectedArea,
      waterDepth: publicReportDepthBand(waterDepthCm),
      waterDepthCm,
      notes,
      photoAttached: photo !== null,
    });

    setWaterDepthCm(null);
    setNotes("");
    clearPhotoPreview();
    setFormMessage(th
      ? `บันทึกรายงานไว้ในอุปกรณ์นี้สำหรับ ${selectedArea.area_name_th}`
      : `Report saved on this device for ${selectedArea.area_name_en}.`);
  };

  return (
    <section className="public-report-page" aria-labelledby="public-report-title">
      <div className="public-report-heading">
        <h1 id="public-report-title">{th ? "ส่งรายงานสถานการณ์" : "Submit a situation report"}</h1>
      </div>

      <form className="public-report-form" onSubmit={submitReport}>
        <section className="public-report-area" aria-labelledby="public-report-area-title">
          <p id="public-report-area-title">
            <span>{th ? "พื้นที่รายงาน:" : "Report area:"}</span>
            <strong>
              {selectedArea
                ? (th ? selectedArea.area_name_th : selectedArea.area_name_en)
                : (th ? "ยังไม่ได้เลือก" : "Not selected")}
            </strong>
          </p>
          {areas.length > 0 && (
            <>
              <button
                type="button"
                className="public-report-area-change"
                aria-expanded={areaPickerOpen}
                aria-controls="public-report-area-select"
                onClick={() => setAreaPickerOpen((open) => !open)}
              >
                {areaPickerOpen
                  ? (th ? "ปิด" : "Close")
                  : (th ? "เปลี่ยน" : "Change")}
              </button>
              {areaPickerOpen && (
                <label className="public-report-area-picker" htmlFor="public-report-area-select">
                  <span className="sr-only">
                    {th ? "เลือกพื้นที่รายงาน" : "Choose the report area"}
                  </span>
                  <select
                    id="public-report-area-select"
                    value={selectedArea?.area_id ?? ""}
                    onChange={(event) => {
                      onSelectArea(event.target.value);
                      setAreaPickerOpen(false);
                      setFormMessage(null);
                    }}
                  >
                    <option value="">
                      {th ? "เลือกพื้นที่" : "Choose an area"}
                    </option>
                    {areas.map((area) => (
                      <option key={area.area_id} value={area.area_id}>
                        {th ? area.area_name_th : area.area_name_en}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </>
          )}
        </section>

        <PublicFloodHeightPicker
          language={language}
          value={waterDepthCm}
          onChange={(depth) => {
            setWaterDepthCm(depth);
            setFormMessage(null);
          }}
        />

        <div className="public-report-photo">
          <label htmlFor="public-report-photo-input">
            <span className="public-report-photo-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M4 7.5h3l1.5-2h7l1.5 2h3v11H4v-11Z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </span>
            <strong>{th ? "ถ่ายภาพหรือเลือกภาพ" : "Take or choose a photo"}</strong>
          </label>
          <input
            ref={photoInputRef}
            id="public-report-photo-input"
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handlePhoto}
          />
          {photoPreviewUrl && (
            <figure className="public-report-photo-preview">
              {/* A temporary blob URL is required for a device-local user-selected preview. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={photoPreviewUrl}
                alt={th ? "ตัวอย่างภาพที่เลือกสำหรับรายงาน" : "Preview of the selected report photo"}
              />
              <figcaption>
                <span>{th ? "แสดงตัวอย่างในอุปกรณ์" : "Device-local preview"}</span>
                <button type="button" onClick={clearPhotoPreview}>
                  {th ? "นำภาพออก" : "Remove photo"}
                </button>
              </figcaption>
            </figure>
          )}
        </div>

        <label className="public-report-notes" htmlFor="public-report-notes">
          <span>{th ? "หมายเหตุ" : "Notes"}</span>
          <textarea
            id="public-report-notes"
            value={notes}
            maxLength={PUBLIC_REPORT_NOTES_MAX_LENGTH}
            placeholder={th ? "อธิบายสิ่งที่คุณพบ..." : "Describe what you observed..."}
            onChange={(event) => {
              setNotes(event.target.value);
              setFormMessage(null);
            }}
          />
          <small>{notes.length}/{PUBLIC_REPORT_NOTES_MAX_LENGTH}</small>
        </label>

        <button
          className="public-report-submit"
          type="submit"
          disabled={!selectedArea}
        >
          {th ? "บันทึกรายงาน" : "Save report"}
        </button>

        <p
          className="public-report-form-status"
          role="status"
          aria-live="polite"
        >
          {formMessage ?? ""}
        </p>
      </form>

      <section className="public-report-feed" aria-labelledby="public-report-feed-title">
        <div className="public-report-feed-heading">
          <h2 id="public-report-feed-title">
            {th ? "รายงานในพื้นที่" : "Community feed"}
          </h2>
          {selectedArea && (
            <span>{th ? selectedArea.area_name_th : selectedArea.area_name_en}</span>
          )}
        </div>

        {areaReports.length === 0 ? (
          <p className="public-report-feed-empty">
            {selectedArea
              ? (th
                ? "ยังไม่มีรายงานที่บันทึกไว้ในอุปกรณ์นี้สำหรับพื้นที่ที่เลือก"
                : "No reports are saved on this device for the selected area.")
              : (th
                ? "เลือกพื้นที่กว้างจากหน้าแรกเพื่อดูรายงานในอุปกรณ์"
                : "Choose a broad area on Home to view device-local reports.")}
          </p>
        ) : (
          <ol className="public-report-feed-list">
            {areaReports.map((report) => (
              <li key={report.report_id}>
                <div className="public-report-feed-icon" aria-hidden="true">
                  {DEPTH_ICONS[report.water_depth]}
                </div>
                <div className="public-report-feed-copy">
                  <h3>
                    {report.water_depth_cm === undefined
                      ? publicReportWaterDepthLabel(report.water_depth, language)
                      : `${report.water_depth_cm} ${th ? "ซม." : "cm"} · ${
                        publicReportWaterDepthLabel(report.water_depth, language)}`}
                  </h3>
                  {report.notes && <p>{report.notes}</p>}
                  <small>
                    {new Intl.DateTimeFormat(th ? "th-TH" : "en-GB", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(report.created_at))}
                    {report.photo_attached
                      ? (th ? " · มีภาพตัวอย่างขณะบันทึก" : " · Photo preview used when saved")
                      : ""}
                  </small>
                </div>
                <span className="public-report-feed-status">
                  {th ? "ในอุปกรณ์" : "On device"}
                </span>
              </li>
            ))}
          </ol>
        )}

        {/*
          Illustrative only, and fenced so it can never be mistaken for — or
          matched alongside — real report content. See FEED_EXAMPLES.
        */}
        <div className="public-report-feed-example" data-example="true">
          {/* Kept for assistive tech and the safety guard; visually removed. */}
          <p className="sr-only">
            {th
              ? "ตัวอย่างสถานะรายงาน ไม่ใช่รายงานจริง"
              : "Example report statuses. Not real reports."}
          </p>

          <section className="public-report-status-card">
            <p className="public-report-status-title">
              {th ? "สถานะรายงานล่าสุดของคุณ" : "Your latest report status"}
            </p>
            <ol className="public-report-status-track" aria-hidden="true">
              {REPORT_STATUS_STEPS.map((step) => (
                <li key={step.id} data-state={step.state}>
                  <span className="public-report-status-dot">
                    {step.state !== "pending" && (
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          d="m5 12.5 4.2 4.2L19 7"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </span>
                  <span>{th ? step.th : step.en}</span>
                </li>
              ))}
            </ol>
          </section>

          <ol className="public-report-feed-list">
            {FEED_EXAMPLES.map((example) => (
              <li key={example.id}>
                <div className="public-report-feed-icon" aria-hidden="true">≋</div>
                <div className="public-report-feed-copy">
                  <h3>{th ? example.th : example.en}</h3>
                  <small>{th ? example.ageTh : example.ageEn}</small>
                </div>
                <span
                  className="public-report-feed-status"
                  data-tone={example.tone}
                >
                  {th ? example.statusTh : example.statusEn}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </section>
  );
}
