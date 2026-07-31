import { formatConfidence, formatSourceTime } from "@/lib/format";
import type { FloodGuardData, Language } from "@/lib/types";

const DATASET_LABELS = {
  fixture_demo: { th: "ชุดข้อมูลการวิจัยและตรวจสอบ", en: "Research validation data" },
  candidate: { th: "ข้อมูลการวางแผนแม่สาย", en: "Mae Sai planning data" },
  official_input: { th: "ข้อมูลจากหน่วยงาน", en: "Agency data input" },
} as const;

const DATA_STATE_LABELS = {
  loading: { th: "กำลังตรวจสอบข้อมูลล่าสุด", en: "Checking for updates" },
  ready: { th: "ข้อมูลพร้อมสำหรับการวางแผน", en: "Available for planning" },
  stale: { th: "โปรดยืนยันสภาพปัจจุบัน", en: "Confirm current conditions" },
  stale_offline: { th: "ใช้ข้อมูลที่บันทึกล่าสุด", en: "Using latest saved data" },
  blocked: { th: "การอัปเดตยังไม่พร้อม", en: "Updates pending" },
  unavailable: { th: "การอัปเดตไม่พร้อมใช้", en: "Updates unavailable" },
} as const;

export function StatusBar({ data, language, compact = false }: { data: FloodGuardData; language: Language; compact?: boolean }) {
  const th = language === "th";
  const dataset = DATASET_LABELS[data.status.dataset_mode][language];
  const source = data.status.dataset_mode === "candidate"
    ? (th ? "HDX COD-AB · OpenStreetMap · WorldPop · Copernicus DEM · Sentinel-1" : "HDX COD-AB · OpenStreetMap · WorldPop · Copernicus DEM · Sentinel-1")
    : data.status.dataset_mode === "fixture_demo"
      ? (th ? "แหล่งข้อมูลสำหรับการวิจัยของ FloodGuard" : "FloodGuard research sources")
      : data.status.source_name;
  return (
    <section className={`status-bar ${compact ? "compact" : ""}`} aria-label={th ? "\u0e2a\u0e16\u0e32\u0e19\u0e30\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25" : "Data status"}>
      <div className="status-context">
        <span aria-hidden="true" />
        <div><b>{dataset}</b><small>{DATA_STATE_LABELS[data.dataState][language]}</small></div>
      </div>
      <div className="status-meta">
        <span><b>{th ? "\u0e40\u0e27\u0e25\u0e32\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25" : "Source time"}</b> {formatSourceTime(data.status.source_timestamp, language)} ICT</span>
        <span><b>{th ? "\u0e04\u0e27\u0e32\u0e21\u0e40\u0e0a\u0e37\u0e48\u0e2d\u0e21\u0e31\u0e48\u0e19" : "Confidence"}</b> {formatConfidence(data.status.confidence_class, language)}</span>
        {!compact && <span><b>{th ? "\u0e41\u0e2b\u0e25\u0e48\u0e07\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25" : "Sources"}</b> {source}</span>}
      </div>
      {data.fallbackReason && (
        <p className="fallback-reason" role="status">
          {th ? "ไม่สามารถตรวจสอบการอัปเดตได้ในขณะนี้ ข้อมูลล่าสุดที่บันทึกไว้ยังพร้อมใช้งาน" : "Updates cannot be checked right now. The latest saved data remains available."}
        </p>
      )}
      {data.degradedReason && (
        <p className="fallback-reason" role="status">
          {th ? "บริการข้อมูลบางส่วนกำลังอัปเดต หน้าจอนี้ใช้ข้อมูลล่าสุดที่พร้อมใช้งาน" : "Some data services are updating. This view uses the latest available data."}
        </p>
      )}
    </section>
  );
}
