"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import type { EvidenceLibraryLayer, FinalsRoute, FinalsRoutes, FinalsServiceId, FinalsTravelMode } from "@floodguard/contracts";
import type { RouteView } from "./finals-route-map";
import styles from "./evidence-library.module.css";

const RouteMap = dynamic(() => import("./finals-route-map").then((module) => module.FinalsRouteMap), { ssr: false });
const n = (value: number | null, th: boolean, digits = 1) => value === null ? (th ? "ยังไม่มี" : "Unavailable") : value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: digits });

function RouteSummary({ route, after, th }: { route: FinalsRoute; after: boolean; th: boolean }) {
  return <article data-route-result={after ? "after" : "baseline"} className={after ? styles.afterRoute : styles.beforeRoute}><p className={styles.eyebrow}>{after ? (th ? "หลังการเปลี่ยนแปลงสมมติ" : "AFTER IMPOSED DISRUPTION") : (th ? "กรณีฐานก่อนเปลี่ยนแปลง" : "BEFORE IMPOSED DISRUPTION")}</p>
    <h3>{route.status === "available" ? route.destination_name : (th ? "ยังไม่มีเส้นทางที่คำนวณได้" : "No modelled route available")}</h3>
    {route.status === "available" ? <><div className={styles.routeTime}><b data-route-total-minutes>{n(route.total_minutes, th)}</b> <span>{th ? "นาที" : "min"}</span><small><b data-route-distance-km>{n((route.distance_m ?? 0) / 1000, th, 2)}</b> {th ? "กม." : "km"}</small></div><p>{th ? "บนถนน / จุดเชื่อมต่อ" : "Network / assumed connectors"}: {n(route.network_minutes, th)} / {n(route.connector_minutes, th)} {th ? "นาที" : "min"}</p></> : <p>{route.reason}</p>}
    <p className={styles.hint}>{th ? "จุดหมายที่ใช้เวลาต่ำสุดในบริการที่เลือก ไม่ได้ยืนยันว่าเปิดให้บริการหรือเดินทางได้ปลอดภัย" : "Minimum-time candidate in the selected service, not a confirmed open destination or a safe route."}</p>
  </article>;
}

export function FinalsRouteComparisonPanel({ routes, service, mode, layers, th }: { routes: FinalsRoutes; service: FinalsServiceId; mode: FinalsTravelMode; layers: EvidenceLibraryLayer[]; th: boolean }) {
  const [originId, setOriginId] = useState(routes.origins[0]?.id ?? "");
  const [kind, setKind] = useState<"close_edge" | "remove_destination">("close_edge");
  const [view, setView] = useState<RouteView>("both");
  const origin = routes.origins.find((item) => item.id === originId);
  const comparison = routes.comparisons.find((item) => item.origin_id === originId && item.service_type === service && item.travel_mode === mode && item.scenario_kind === kind);
  return <section className={`${styles.panel} ${styles.routePanel}`} aria-labelledby="route-comparison-title" data-route-comparison="true" data-route-id={comparison?.id}>
    <p className={styles.eyebrow}>{th ? "เริ่มจากสถานที่จริง · เปลี่ยนเงื่อนไขอย่างชัดเจน" : "A REAL STARTING PLACE · AN EXPLICIT SCENARIO"}</p>
    <h2 id="route-comparison-title">{th ? "จากจุดนี้ เส้นทางเปลี่ยนอย่างไร?" : "From this place, how does the route change?"}</h2>
    <p>{th ? "เปรียบเทียบเส้นทางที่ใช้เวลาน้อยที่สุดไปยังบริการที่เลือก ก่อนและหลังการปิดถนนหรือหยุดให้บริการจุดหมายตามสมมติฐาน ไม่ใช่เส้นทางน้ำท่วมก่อนและหลังที่ตรวจวัดจริง" : "Compare the minimum-time route to the selected service before and after an imposed road closure or destination removal. These are model comparisons, not observed before-and-after flood conditions."}</p>
    {routes.status === "available" ? <>
      <div className={styles.selectors}><label>{th ? "จุดเริ่มต้นสาธารณะ" : "Public starting place"}<select value={originId} onChange={(event) => setOriginId(event.target.value)}>{routes.origins.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>{th ? "การเปลี่ยนแปลงที่กำหนด" : "Imposed change"}<select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="close_edge">{th ? "ปิดช่วงถนนบนเส้นทางกรณีฐาน" : "Close a baseline route link"}</option><option value="remove_destination">{th ? "หยุดให้บริการจุดหมายกรณีฐาน" : "Remove the baseline destination"}</option></select></label></div>
      {origin && comparison ? <>
        <div className={styles.routeToolbar}><fieldset><legend>{th ? "แสดงเส้นทาง" : "Show routes"}</legend>{(["both", "baseline", "after"] as const).map((option) => <label key={option}><input type="radio" name="route-map-view" checked={view === option} onChange={() => setView(option)} />{option === "both" ? (th ? "ทั้งสองกรณี" : "Both") : option === "baseline" ? (th ? "ก่อน" : "Before") : (th ? "หลัง" : "After")}</label>)}</fieldset><a href={origin.source_url} target="_blank" rel="noopener noreferrer">{th ? "แหล่งข้อมูลจุดเริ่มต้น" : "Starting-place source"}</a></div>
        <RouteMap origin={origin} comparison={comparison} layers={layers} view={view} th={th} />
        <ul className={styles.routeLegend} aria-label={th ? "สัญลักษณ์เส้นทาง" : "Route legend"}><li><span className={styles.beforeLine} />{th ? "เส้นทึบสีเขียว: กรณีฐาน" : "Solid green: baseline"}</li><li><span className={styles.afterLine} />{th ? "เส้นประสีม่วง: หลังเปลี่ยนแปลง" : "Dashed purple: after change"}</li><li><span className={styles.closedLine} />{th ? "สีส้ม: กำหนดให้ปิด" : "Orange: imposed closure"}</li><li>{th ? "เส้นจุด: จุดเชื่อมต่อตามสมมติฐาน" : "Dotted lines: assumed connectors"}</li></ul>
        <div className={styles.scenarios}><RouteSummary route={comparison.baseline} after={false} th={th} /><RouteSummary route={comparison.after} after th={th} /></div>
        <p className={styles.routeOutcome} role="status">{comparison.delta_minutes !== null ? `${th ? "เวลาเดินทางเปลี่ยน" : "Travel-time change"}: ${comparison.delta_minutes > 0 ? "+" : ""}${n(comparison.delta_minutes, th, 2)} ${th ? "นาที" : "minutes"}. ${comparison.delta_minutes === 0 ? (th ? "ไม่พบความต่างในกรณีนี้" : "No difference in this case.") : ""}` : (th ? "อย่างน้อยหนึ่งกรณีไม่มีเส้นทาง จึงไม่มีผลต่างเวลา ไม่ได้แทนเวลาที่ไม่ทราบด้วยศูนย์" : "At least one case has no modelled route, so a time difference is unavailable. Missing time is not zero.")}</p>
        <p className={styles.hint}>{th ? "หมุดระบุสถานที่จากข้อมูลสาธารณะ ยังไม่ได้ตรวจทางเข้า สิ่งกีดขวาง หรือความปลอดภัย ตัวเลือกนี้ใช้เพื่ออธิบายวิธี ไม่ใช่ตัวอย่างประเมินประสิทธิภาพแบบอิสระ" : "The pin identifies a public place; its entrance, barriers and safety remain unverified. This is an explanatory case, not an independent performance evaluation."}</p>
        <details><summary>{th ? "เหตุผลและรายละเอียดเส้นทางแบบข้อความ" : "Selection rationale and text route record"}</summary><p>{comparison.selection_method}</p><p>{th ? "หมุด" : "Pin"}: {origin.latitude.toFixed(6)}, {origin.longitude.toFixed(6)} · {origin.geometry_role} · {origin.location_status}</p><p>{th ? "รหัสที่เปลี่ยน" : "Changed IDs"}: {comparison.changed_ids.join(", ") || "—"}</p><p>{th ? "เส้นทางกรณีฐาน: ช่วงถนนตามลำดับ" : "Baseline route: road edges in travel order"}: {comparison.baseline.edge_ids.join(" → ") || "—"}</p><p>{th ? "เส้นทางหลังเปลี่ยน: ช่วงถนนตามลำดับ" : "After route: road edges in travel order"}: {comparison.after.edge_ids.join(" → ") || "—"}</p><p className={styles.hash}>{comparison.id} · {comparison.context_sha256}</p><ul>{routes.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
      </> : <p className={styles.empty}>{th ? "ไม่มีผลเส้นทางสำหรับตัวเลือกนี้ จะไม่ใช้จุดเริ่มต้นหรือบริการอื่นแทน" : "No route comparison exists for this selection. Another origin or service is not substituted."}</p>}
    </> : <p className={styles.empty}>{th ? "ยังไม่มีจุดเริ่มต้นที่ตรวจสอบย้อนกลับได้" : "No traceable public starting place is available."}</p>}
  </section>;
}
