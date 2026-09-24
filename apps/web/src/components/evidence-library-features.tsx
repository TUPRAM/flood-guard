"use client";

import { useId, useState } from "react";
import type { EvidenceGeometry, EvidenceLibraryLayer } from "@floodguard/contracts";
import styles from "./evidence-library.module.css";

const PAGE_SIZE = 50;

function scalar(properties: Record<string, unknown> | null, keys: string[]): string | null {
  for (const key of keys) {
    const value = properties?.[key];
    if ((typeof value === "string" && value.trim()) || (typeof value === "number" && Number.isFinite(value))) return String(value);
  }
  return null;
}

function geometryBounds(geometry: EvidenceGeometry | null): number[] | null {
  let west = Infinity; let south = Infinity; let east = -Infinity; let north = -Infinity;
  function coordinates(value: unknown) {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && Number.isFinite(value[0]) && typeof value[1] === "number" && Number.isFinite(value[1])) {
      west = Math.min(west, value[0]); south = Math.min(south, value[1]);
      east = Math.max(east, value[0]); north = Math.max(north, value[1]);
    } else value.forEach(coordinates);
  }
  function visit(item: EvidenceGeometry | null) {
    if (!item) return;
    coordinates(item.coordinates);
    item.geometries?.forEach(visit);
  }
  visit(geometry);
  return Number.isFinite(west) ? [west, south, east, north] : null;
}

/** Pagination covers every published feature, including records with missing geometry. */
export function evidenceFeaturePage(layers: EvidenceLibraryLayer[], layerId: string, requestedPage: number) {
  const layer = layers.find((item) => item.id === layerId) ?? null;
  const features = layer?.data?.features ?? [];
  const total = features.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.min(pages - 1, Math.max(0, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 0));
  const start = page * PAGE_SIZE;
  return { layer, total, page, pages, rows: features.slice(start, start + PAGE_SIZE).map((feature, index) => ({
    position: start + index + 1,
    // The package checksum fixes feature order; this key also distinguishes duplicate source IDs.
    recordId: `${layerId}:feature:${start + index + 1}`,
    sourceId: scalar(feature.properties, ["edge_id", "facility_id", "osm_id", "id", "record_id"]),
    name: scalar(feature.properties, ["name", "name_th", "name_en", "title"]),
    geometryType: feature.geometry?.type ?? null,
    bounds: geometryBounds(feature.geometry),
  })) };
}

function coordinate(value: number): string { return String(Number(value.toFixed(6))); }

export function EvidenceFeatureBrowser({ layers, th }: { layers: EvidenceLibraryLayer[]; th: boolean }) {
  const id = useId();
  const [selection, setSelection] = useState({ layerId: layers.find((layer) => layer.data)?.id ?? layers[0]?.id ?? "", page: 0 });
  const view = evidenceFeaturePage(layers, selection.layerId, selection.page);
  const unavailable = th ? "ไม่มีข้อมูล" : "Unavailable";
  return <details className={styles.featureBrowser} data-feature-browser="true">
    <summary>{th ? "ดูรายละเอียดวัตถุบนแผนที่ในรูปแบบตาราง" : "Browse mapped features as a table"}</summary>
    <p>{th ? "ตารางนี้เข้าถึงรายการวัตถุทั้งหมดที่เผยแพร่ในชุดข้อมูล แสดงครั้งละ 50 รายการ พิกัดเรียงตามลองจิจูด ละติจูด" : "Every published feature is accessible here, 50 records per page. Coordinates are longitude, latitude in degrees."}</p>
    <label className={styles.featureSelect} htmlFor={`${id}-layer`}>{th ? "ชั้นข้อมูลในตาราง" : "Table layer"}
      <select id={`${id}-layer`} value={selection.layerId} onChange={(event) => setSelection({ layerId: event.target.value, page: 0 })}>
        {!layers.length ? <option value="">{th ? "ไม่มีชั้นข้อมูล" : "No layers"}</option> : null}
        {layers.map((layer) => <option key={layer.id} value={layer.id}>{layer.title}</option>)}
      </select>
    </label>
    {view.layer ? <>
      <p><b>{th ? "บทบาท" : "Role"}:</b> {view.layer.role} · <b>{th ? "รหัสชั้นข้อมูล" : "Layer ID"}:</b> {view.layer.id}</p>
      {view.layer.reason ? <p>{view.layer.reason}</p> : null}
      {view.layer.image_url && view.layer.bounds ? <p className={styles.hint}>{th ? "ขอบเขตภาพภูมิประเทศ [ตะวันตก, ใต้] → [ตะวันออก, เหนือ]" : "Terrain image coverage [west, south] → [east, north]"}: [{coordinate(view.layer.bounds[0][1])}, {coordinate(view.layer.bounds[0][0])}] → [{coordinate(view.layer.bounds[1][1])}, {coordinate(view.layer.bounds[1][0])}]. {th ? "ภาพนี้เป็นภาพตัวอย่างสี ไม่ได้ให้ค่าระดับความสูงรายจุด" : "This is a color preview, not a point elevation measurement."}</p> : null}
      {view.layer.attribution ? <p className={styles.hint}>{view.layer.attribution}</p> : null}
      {view.layer.data ? <>
        <div className={styles.pagination}>
          <button type="button" disabled={view.page === 0} onClick={() => setSelection({ ...selection, page: view.page - 1 })}>{th ? "หน้าก่อนหน้า" : "Previous page"}</button>
          <p role="status" aria-live="polite">{th ? `รายการ ${view.total ? view.page * PAGE_SIZE + 1 : 0}–${Math.min((view.page + 1) * PAGE_SIZE, view.total)} จาก ${view.total} · หน้า ${view.page + 1}/${view.pages}` : `Records ${view.total ? view.page * PAGE_SIZE + 1 : 0}–${Math.min((view.page + 1) * PAGE_SIZE, view.total)} of ${view.total} · Page ${view.page + 1}/${view.pages}`}</p>
          <button type="button" disabled={view.page + 1 >= view.pages} onClick={() => setSelection({ ...selection, page: view.page + 1 })}>{th ? "หน้าถัดไป" : "Next page"}</button>
        </div>
        {view.total ? <div className={styles.tableWrap} tabIndex={0} role="region" aria-label={th ? "ตารางรายละเอียดวัตถุ เลื่อนแนวนอนได้" : "Feature details table; scroll horizontally"}><table>
          <caption>{view.layer.title} · {th ? "วัตถุที่เผยแพร่ในชุดข้อมูลนี้" : "Features published in this package"}</caption>
          <thead><tr><th scope="col">#</th><th scope="col">{th ? "รหัสรายการ / แหล่งข้อมูล" : "Record / source ID"}</th><th scope="col">{th ? "ชื่อ" : "Name"}</th><th scope="col">{th ? "ชนิดรูปทรง" : "Geometry type"}</th><th scope="col">{th ? "พิกัดหรือขอบเขต [ตะวันตก, ใต้] → [ตะวันออก, เหนือ]" : "Coordinate or bounds [west, south] → [east, north]"}</th></tr></thead>
          <tbody>{view.rows.map((row) => <tr key={row.recordId}><td>{row.position}</td><th scope="row"><code>{row.recordId}</code><small>{th ? "รหัสแหล่งข้อมูล" : "Source ID"}: {row.sourceId ?? unavailable}</small></th><td>{row.name ?? unavailable}</td><td>{row.geometryType ?? unavailable}</td><td>{row.bounds ? row.geometryType === "Point" ? `[${coordinate(row.bounds[0])}, ${coordinate(row.bounds[1])}]` : `[${coordinate(row.bounds[0])}, ${coordinate(row.bounds[1])}] → [${coordinate(row.bounds[2])}, ${coordinate(row.bounds[3])}]` : unavailable}</td></tr>)}</tbody>
        </table></div> : <p>{th ? "ชั้นข้อมูลที่เผยแพร่นี้มี 0 รายการ" : "This published feature collection contains 0 records."}</p>}
      </> : <p>{th ? "ไม่มีรายการวัตถุเวกเตอร์ที่เผยแพร่สำหรับชั้นข้อมูลนี้ ข้อมูลที่ไม่มีไม่ได้หมายถึงไม่มีสิ่งนั้นในพื้นที่จริง" : "No vector feature records are published for this layer. Missing records do not establish absence on the ground."}</p>}
    </> : <p>{th ? "ไม่มีชั้นข้อมูลที่เลือก" : "No selected layer is available."}</p>}
  </details>;
}
