"use client";

import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from "react";

import {
  PUBLIC_REPORT_DEPTH_BANDS,
  PUBLIC_REPORT_DEPTH_MAX_CM,
  PUBLIC_REPORT_DEPTH_MIN_CM,
  publicReportDepthBand,
  publicReportWaterDepthLabel,
} from "@/lib/public-report";
import type { Language } from "@/lib/types";

interface PublicFloodHeightPickerProps {
  language: Language;
  /** Reported depth in centimetres, or null before the reader sets one. */
  value: number | null;
  onChange: (centimetres: number) => void;
}

/**
 * Waterline height for a given depth, as (centimetres, percentage up from the
 * bottom of the illustration). Measured against the figure in flood-height.png
 * — its feet sit at 7.1% and the top of its head at 78.8% — so the water meets
 * the drawing's own ankle, knee, waist and chest rather than arbitrary
 * fractions of the frame. Between anchors the level is interpolated.
 * Re-measure these if the illustration is ever recropped.
 */
const LEVEL_ANCHORS: ReadonlyArray<readonly [number, number]> = [
  [0, 7.11],
  [15, 11.55],
  [50, 26.78],
  [100, 48.98],
  [130, 60.41],
  [170, 78.81],
];

function levelForCm(centimetres: number): number {
  const cm = Math.min(Math.max(centimetres, 0), PUBLIC_REPORT_DEPTH_MAX_CM);
  for (let index = 1; index < LEVEL_ANCHORS.length; index += 1) {
    const [lowCm, lowLevel] = LEVEL_ANCHORS[index - 1];
    const [highCm, highLevel] = LEVEL_ANCHORS[index];
    if (cm <= highCm) {
      const span = highCm - lowCm;
      const ratio = span === 0 ? 0 : (cm - lowCm) / span;
      return lowLevel + ratio * (highLevel - lowLevel);
    }
  }
  return LEVEL_ANCHORS[LEVEL_ANCHORS.length - 1][1];
}

/** Inverse of {@link levelForCm}, used when dragging on the illustration. */
function cmForLevel(level: number): number {
  if (level <= LEVEL_ANCHORS[0][1]) return PUBLIC_REPORT_DEPTH_MIN_CM;
  for (let index = 1; index < LEVEL_ANCHORS.length; index += 1) {
    const [lowCm, lowLevel] = LEVEL_ANCHORS[index - 1];
    const [highCm, highLevel] = LEVEL_ANCHORS[index];
    if (level <= highLevel) {
      const span = highLevel - lowLevel;
      const ratio = span === 0 ? 0 : (level - lowLevel) / span;
      return lowCm + ratio * (highCm - lowCm);
    }
  }
  return PUBLIC_REPORT_DEPTH_MAX_CM;
}

function clampCm(centimetres: number): number {
  return Math.min(
    Math.max(Math.round(centimetres), PUBLIC_REPORT_DEPTH_MIN_CM),
    PUBLIC_REPORT_DEPTH_MAX_CM,
  );
}

export function PublicFloodHeightPicker({
  language,
  value,
  onChange,
}: PublicFloodHeightPickerProps) {
  const th = language === "th";
  const stageRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  // Before the reader sets a depth the water rests at ground level and the
  // slider shows its start, so nothing implies a reading that was not given.
  const hasValue = value !== null;
  const centimetres = hasValue ? value : PUBLIC_REPORT_DEPTH_MIN_CM;
  const band = publicReportDepthBand(centimetres);
  const level = levelForCm(centimetres);

  const applyPointer = useCallback((clientY: number) => {
    const stage = stageRef.current;
    if (!stage) return;
    const box = stage.getBoundingClientRect();
    if (box.height === 0) return;
    const fromBottom = ((box.bottom - clientY) / box.height) * 100;
    onChange(clampCm(cmForLevel(fromBottom)));
  }, [onChange]);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    draggingRef.current = true;
    try {
      // Capture keeps the drag alive outside the picture. It throws when the
      // pointer is not one the browser is tracking, which must not stop the
      // tap from registering.
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      /* Dragging still works without capture. */
    }
    applyPointer(event.clientY);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    applyPointer(event.clientY);
  };

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    draggingRef.current = false;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      /* Nothing to release. */
    }
  };

  const bandLabel = publicReportWaterDepthLabel(band, language);

  return (
    <fieldset className="flood-height">
      <legend>{th ? "ระดับน้ำ" : "Flood height"}</legend>

      {/*
        Pointer affordance for the same value the slider below carries, so it is
        hidden from assistive technology rather than duplicated into it.
      */}
      <div
        ref={stageRef}
        className="flood-height-stage"
        aria-hidden="true"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div className="flood-height-scene" />
        {/* Geometry is set inline: one source of truth for the waterline, and
            no custom-property indirection between the value and the paint. */}
        <div className="flood-height-water" style={{ height: `${level}%` }} />
        <div className="flood-height-line" style={{ bottom: `${level}%` }}>
          <span className="flood-height-handle" />
        </div>
        <span
          className="flood-height-chip"
          style={{ bottom: `calc(${level}% + 10px)` }}
        >
          {hasValue
            ? `${centimetres} ${th ? "ซม." : "cm"} · ${bandLabel}`
            : (th ? "ลากเพื่อตั้งระดับน้ำ" : "Drag to set the water level")}
        </span>
      </div>

      <label className="flood-height-slider">
        <span className="sr-only">
          {th ? "ความลึกของน้ำเป็นเซนติเมตร" : "Water depth in centimetres"}
        </span>
        <input
          type="range"
          min={PUBLIC_REPORT_DEPTH_MIN_CM}
          max={PUBLIC_REPORT_DEPTH_MAX_CM}
          step={1}
          value={centimetres}
          aria-valuetext={hasValue
            ? `${centimetres} ${th ? "เซนติเมตร" : "centimetres"} · ${bandLabel}`
            : (th ? "ยังไม่ได้ตั้งระดับน้ำ" : "No water level set")}
          onChange={(event) => onChange(clampCm(Number(event.target.value)))}
        />
        <span className="flood-height-scale" aria-hidden="true">
          <span>{PUBLIC_REPORT_DEPTH_MIN_CM} {th ? "ซม." : "cm"}</span>
          <span>{PUBLIC_REPORT_DEPTH_MAX_CM} {th ? "ซม." : "cm"}</span>
        </span>
      </label>

      <div className="flood-height-steps">
        {PUBLIC_REPORT_DEPTH_BANDS.map((option) => (
          <button
            key={option.id}
            type="button"
            className={hasValue && band === option.id ? "selected" : ""}
            aria-pressed={hasValue && band === option.id}
            onClick={() => onChange(option.referenceCm)}
          >
            {publicReportWaterDepthLabel(option.id, language)}
          </button>
        ))}
      </div>

      <small className="flood-height-note">
        {th
          ? "ลากบนภาพหรือเลื่อนแถบเพื่อตั้งความลึก ระดับด้านล่างจะเปลี่ยนตามค่าที่เลือก"
          : "Drag on the picture or move the slider to set the depth. The level below follows the value you choose."}
      </small>
    </fieldset>
  );
}
