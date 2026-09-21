"use client";

import dynamic from "next/dynamic";
import { useRef, useState, type ReactNode } from "react";
import type { EvidenceLibraryLayer, FinalsRoute, FinalsRoutes, FinalsServiceId, FinalsTravelMode } from "@floodguard/contracts";
import type { RouteView } from "./finals-route-map";
import styles from "./evidence-library.module.css";

const RouteMap = dynamic(() => import("./finals-route-map").then((module) => module.FinalsRouteMap), { ssr: false });
const n = (value: number | null, th: boolean, digits = 1) => value === null ? (th ? "ยังไม่มี" : "Unavailable") : value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: digits });

function RouteSummary({ route, after, th }: { route: FinalsRoute; after: boolean; th: boolean }) {
  return <article data-route-result={after ? "after" : "baseline"} className={after ? styles.afterRoute : styles.beforeRoute}>
    <p className={styles.eyebrow}>{after ? (th ? "หลัง · สมมติให้เปลี่ยน" : "AFTER · IMPOSED CHANGE") : (th ? "ก่อน · กรณีฐาน" : "BEFORE · BASELINE")}</p>
    <h3>{route.status === "available" ? route.destination_name : (th ? "ยังไม่มีเส้นทางที่คำนวณได้" : "No modelled route available")}</h3>
    {route.status === "available" ? <><div className={styles.routeTime}><b data-route-total-minutes>{n(route.total_minutes, th)}</b> <span>{th ? "นาที" : "min"}</span><small><b data-route-distance-km>{n((route.distance_m ?? 0) / 1000, th, 2)}</b> {th ? "กม." : "km"}</small></div><p className={styles.routeBreakdown}>{th ? "ถนน / จุดเชื่อม" : "Network / connectors"}: {n(route.network_minutes, th)} / {n(route.connector_minutes, th)} {th ? "นาที" : "min"}</p></> : <p className={styles.routeMissing}>{th ? "ดูเหตุผลในรายละเอียดเส้นทาง" : "See the reason in Route details."}</p>}
  </article>;
}

export function FinalsRouteComparisonPanel({ routes, service, mode, layers, th, controls, actions }: { routes: FinalsRoutes; service: FinalsServiceId; mode: FinalsTravelMode; layers: EvidenceLibraryLayer[]; th: boolean; controls?: ReactNode; actions?: ReactNode }) {
  const detailDialog = useRef<HTMLDialogElement>(null);
  const [originId, setOriginId] = useState(routes.origins[0]?.id ?? "");
  const [kind, setKind] = useState<"close_edge" | "remove_destination">("close_edge");
  const [view, setView] = useState<RouteView>("both");
  const origin = routes.origins.find((item) => item.id === originId);
  const comparison = routes.comparisons.find((item) => item.origin_id === originId && item.service_type === service && item.travel_mode === mode && item.scenario_kind === kind);
  return <section className={styles.routeWorkspace} aria-labelledby="route-comparison-title" data-route-comparison="true" data-route-id={comparison?.id}>
    <h2 id="route-comparison-title" className={styles.visuallyHidden}>{th ? "จากจุดนี้ เส้นทางเปลี่ยนอย่างไร?" : "From this place, how does the route change?"}</h2>
    <div className={styles.routeControls}>{controls}
      <label>{th ? "จุดเริ่มต้นสาธารณะ" : "Public starting place"}<select value={originId} onChange={(event) => setOriginId(event.target.value)}>{routes.origins.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>{th ? "การเปลี่ยนแปลงที่กำหนด" : "Imposed change"}<select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="close_edge">{th ? "ปิดช่วงถนนบนเส้นทางกรณีฐาน" : "Close a baseline route link"}</option><option value="remove_destination">{th ? "หยุดให้บริการจุดหมายกรณีฐาน" : "Remove the baseline destination"}</option></select></label>
    </div>
    <div className={styles.workspaceActions}>{actions}<button type="button" aria-haspopup="dialog" onClick={() => detailDialog.current?.showModal()}>{th ? "รายละเอียดเส้นทาง" : "Route details"}</button></div>
    {routes.status === "available" && origin && comparison ? <div className={styles.routeStage}>
      <div className={styles.routeCanvas}>
        <fieldset className={styles.routeViews}><legend>{th ? "แสดงเส้นทาง" : "Show routes"}</legend>{(["both", "baseline", "after"] as const).map((option) => <label key={option}><input type="radio" name="route-map-view" checked={view === option} onChange={() => setView(option)} />{option === "both" ? (th ? "ทั้งสองกรณี" : "Both") : option === "baseline" ? (th ? "ก่อน" : "Before") : (th ? "หลัง" : "After")}</label>)}</fieldset>
        <RouteMap origin={origin} comparison={comparison} layers={layers} view={view} th={th} />
        <ul className={styles.compactLegend} aria-label={th ? "สัญลักษณ์เส้นทาง" : "Route legend"}><li><span className={styles.beforeLine} />{th ? "ก่อน" : "Before"}</li><li><span className={styles.afterLine} />{th ? "หลัง" : "After"}</li><li><span className={styles.closedLine} />{th ? "สมมติให้ปิด" : "Imposed closure"}</li><li>{th ? "เส้นจุด: จุดเชื่อมสมมติ" : "Dotted: assumed connectors"}</li></ul>
      </div>
      <aside className={styles.routeResults} aria-label={th ? "เปรียบเทียบผลเส้นทาง" : "Route comparison results"}>
        <div className={styles.routeCards}><RouteSummary route={comparison.baseline} after={false} th={th} /><RouteSummary route={comparison.after} after th={th} /></div>
        <p className={styles.routeOutcome} data-route-outcome role="status">{comparison.delta_minutes !== null ? `${th ? "เวลาเปลี่ยน" : "Travel-time change"}: ${comparison.delta_minutes > 0 ? "+" : ""}${n(comparison.delta_minutes, th, 2)} ${th ? "นาที" : "minutes"}${comparison.delta_minutes === 0 ? (th ? " · ไม่ต่างในกรณีนี้" : " · No difference in this case.") : ""}` : (th ? "ผลต่างเวลาไม่มี: อย่างน้อยหนึ่งกรณีไม่มีเส้นทาง ไม่ใช่ศูนย์" : "Time difference unavailable: at least one case has no route. Missing time is not zero.")}</p>
        <p className={styles.routeCaution}>{th ? "จุดหมายใช้เวลาต่ำสุดตามแบบจำลอง ยังไม่ยืนยันทางเข้า การเปิดใช้งาน หรือความปลอดภัย" : "Minimum-time candidate. Entrance, event-time availability and route safety remain unverified."}</p>
      </aside>
    </div> : <p className={styles.empty}>{th ? "ไม่มีผลเส้นทางสำหรับตัวเลือกนี้ จะไม่ใช้จุดเริ่มต้นหรือบริการอื่นแทน" : "No route comparison exists for this selection. Another origin or service is not substituted."}</p>}
    <dialog ref={detailDialog} className={styles.workspaceDialog} aria-labelledby="route-detail-title">
      <div className={styles.workspaceDialogHeader}><h2 id="route-detail-title">{th ? "รายละเอียดเส้นทาง" : "Route details"}</h2><button type="button" onClick={() => detailDialog.current?.close()}>{th ? "ปิด" : "Close"}</button></div>
      <div className={styles.workspaceDialogBody}>
        <p>{th ? "เปรียบเทียบเส้นทางที่ใช้เวลาน้อยที่สุดก่อนและหลังการเปลี่ยนแปลงสมมติ ไม่ใช่สภาพน้ำท่วมก่อนและหลังที่สังเกตจริง" : "Minimum-time routes before and after an imposed change; not observed before-and-after flood conditions."}</p>
        <p>{mode === "walking" ? (th ? "สมมติเดิน 5 กม./ชม. ยังไม่ยืนยันสิ่งกีดขวางหรือการเดินได้จริง" : "Walking assumes 5 km/h. Barriers and walkability are unverified.") : (th ? "แบบจำลองยานพาหนะใช้ความเร็วตามประเภทถนน ไม่รวมวันเวย์ ข้อห้ามเลี้ยว หรือการผ่านได้ช่วงเหตุการณ์" : "The vehicle model uses road-class speeds, without one-way rules, turn restrictions or event passability.")}</p>
        {origin && comparison ? <><h3>{origin.name}</h3><a href={origin.source_url} target="_blank" rel="noopener noreferrer">{th ? "แหล่งข้อมูลจุดเริ่มต้น" : "Starting-place source"}</a><p>{comparison.selection_method}</p><p>{th ? "หมุด" : "Pin"}: {origin.latitude.toFixed(6)}, {origin.longitude.toFixed(6)} · {origin.geometry_role} · {origin.location_status}</p>
          <p>{th ? "หมุดระบุสถานที่ ไม่ใช่ทางเข้าที่ตรวจแล้ว กรณีนี้ใช้อธิบายวิธี ไม่ใช่การประเมินอิสระ" : "The pin identifies a public place, not a verified entrance. This is an explanatory case, not an independent performance evaluation."}</p>
          <p>{th ? "รหัสที่เปลี่ยน" : "Changed IDs"}: {comparison.changed_ids.join(", ") || "—"}</p>
          {(["baseline", "after"] as const).map((key) => <section key={key} data-route-detail-result={key}><h3>{key === "baseline" ? (th ? "ก่อน" : "Before") : (th ? "หลัง" : "After")}</h3><p>{comparison[key].reason}</p><p>{th ? "นาทีบนถนน / จุดเชื่อมต่อสมมติ / รวม" : "Network / assumed connectors / total minutes"}: {n(comparison[key].network_minutes, th)} / {n(comparison[key].connector_minutes, th)} / {n(comparison[key].total_minutes, th)}</p><p>{th ? "ช่วงถนนตามลำดับ" : "Road edges in travel order"}: {comparison[key].edge_ids.join(" → ") || "—"}</p></section>)}
          <p className={styles.hash}>{comparison.id} · {comparison.context_sha256}</p></> : <p>{th ? "ไม่มีผลสำหรับตัวเลือกนี้" : "No result for this selection."}</p>}
        <ul>{routes.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </dialog>
  </section>;
}
