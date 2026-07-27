"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

import {
  PUBLIC_REPORT_CATEGORIES,
  PUBLIC_REPORT_NOTES_MAX_LENGTH,
  PUBLIC_REPORT_WATER_DEPTHS,
  publicReportCategoryLabel,
  publicReportWaterDepthLabel,
  reportsForPlanningArea,
  type PublicReportArea,
  type PublicReportCategory,
  type PublicReportWaterDepth,
} from "@/lib/public-report";
import type { Language } from "@/lib/types";
import { usePublicReports } from "@/lib/use-public-reports";

interface PublicReportPageProps {
  language: Language;
  selectedArea?: PublicReportArea;
}

const DEPTH_ICONS: Record<PublicReportWaterDepth, string> = {
  ankle: "≋",
  knee: "◉",
  waist: "≋",
  chest: "⌁",
};

export function PublicReportPage({
  language,
  selectedArea,
}: PublicReportPageProps) {
  const th = language === "th";
  const { reports, addReport } = usePublicReports();
  const [waterDepth, setWaterDepth] = useState<PublicReportWaterDepth | "">("");
  const [category, setCategory] = useState<PublicReportCategory | "">("");
  const [notes, setNotes] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);
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
    if (!waterDepth || !category) {
      setFormMessage(th
        ? "เลือกระดับน้ำและประเภทของรายงาน"
        : "Choose a water depth and report category.");
      return;
    }

    addReport({
      area: selectedArea,
      waterDepth,
      category,
      notes,
      photoAttached: photo !== null,
    });

    setWaterDepth("");
    setCategory("");
    setNotes("");
    clearPhotoPreview();
    setFormMessage(th
      ? `บันทึกรายงานไว้ในอุปกรณ์นี้สำหรับ ${selectedArea.area_name_th}`
      : `Report saved on this device for ${selectedArea.area_name_en}.`);
  };

  return (
    <section className="public-report-page" aria-labelledby="public-report-title">
      <div className="public-report-heading">
        <p className="eyebrow">{th ? "รายงานจากชุมชน" : "COMMUNITY REPORT"}</p>
        <h1 id="public-report-title">{th ? "ส่งรายงานสถานการณ์" : "Submit a situation report"}</h1>
        <p>
          {th
            ? "บันทึกสิ่งที่คุณพบในพื้นที่กว้างที่เลือก โดยไม่ขอพิกัดหรือที่อยู่ที่แน่นอน"
            : "Record what you observed in the selected broad area without providing exact coordinates or a home address."}
        </p>
      </div>

      <form className="public-report-form" onSubmit={submitReport}>
        <section className="public-report-area" aria-labelledby="public-report-area-title">
          <div>
            <p className="eyebrow">{th ? "พื้นที่รายงาน" : "REPORT AREA"}</p>
            <h2 id="public-report-area-title">
              {selectedArea
                ? (th ? selectedArea.area_name_th : selectedArea.area_name_en)
                : (th ? "ยังไม่ได้เลือกพื้นที่กว้าง" : "No broad area selected")}
            </h2>
          </div>
          <p>
            {th
              ? "รายงานจะเก็บชื่อพื้นที่กว้างเท่านั้น และจะไม่เก็บตำแหน่งที่แน่นอน"
              : "Only the broad area name is stored; an exact location is not recorded."}
          </p>
        </section>

        <div className="public-report-photo">
          <label htmlFor="public-report-photo-input">
            <span className="public-report-photo-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M4 7.5h3l1.5-2h7l1.5 2h3v11H4v-11Z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </span>
            <strong>{th ? "ถ่ายภาพหรือเลือกภาพ" : "Take or choose a photo"}</strong>
            <small>
              {th
                ? "ภาพใช้แสดงตัวอย่างบนอุปกรณ์นี้เท่านั้น"
                : "The image is used only for a local preview."}
            </small>
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

        <fieldset className="public-report-depth">
          <legend>{th ? "ระดับน้ำ" : "Water depth"}</legend>
          <div className="public-report-choice-grid">
            {PUBLIC_REPORT_WATER_DEPTHS.map((option) => (
              <label key={option.id} className={waterDepth === option.id ? "selected" : ""}>
                <input
                  type="radio"
                  name="public-report-water-depth"
                  value={option.id}
                  checked={waterDepth === option.id}
                  onChange={() => {
                    setWaterDepth(option.id);
                    setFormMessage(null);
                  }}
                  required
                />
                <span aria-hidden="true">{DEPTH_ICONS[option.id]}</span>
                <b>{option[language]}</b>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="public-report-category">
          <legend>{th ? "ประเภท" : "Category"}</legend>
          <div className="public-report-category-options">
            {PUBLIC_REPORT_CATEGORIES.map((option) => (
              <label key={option.id} className={category === option.id ? "selected" : ""}>
                <input
                  type="radio"
                  name="public-report-category"
                  value={option.id}
                  checked={category === option.id}
                  onChange={() => {
                    setCategory(option.id);
                    setFormMessage(null);
                  }}
                  required
                />
                <span>{option[language]}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="public-report-notes" htmlFor="public-report-notes">
          <span>{th ? "หมายเหตุเพิ่มเติม (ไม่บังคับ)" : "Optional notes"}</span>
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
          {formMessage ?? (th
            ? "รายงานนี้เก็บไว้ในอุปกรณ์ของคุณ และไม่ส่งข้อมูลไปยังหน่วยงาน"
            : "This report stays on your device and is not sent to an authority.")}
        </p>
      </form>

      <section className="public-report-feed" aria-labelledby="public-report-feed-title">
        <div className="public-report-feed-heading">
          <div>
            <p className="eyebrow">{th ? "ฟีดในพื้นที่" : "AREA FEED"}</p>
            <h2 id="public-report-feed-title">{th ? "รายงานในอุปกรณ์นี้" : "Reports on this device"}</h2>
          </div>
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
                    {publicReportWaterDepthLabel(report.water_depth, language)}
                    {" · "}
                    {publicReportCategoryLabel(report.category, language)}
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
      </section>
    </section>
  );
}
