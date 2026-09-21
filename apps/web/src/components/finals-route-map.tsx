"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap } from "leaflet";
import type { EvidenceLibraryLayer, FinalsOrigin, FinalsRouteComparison } from "@floodguard/contracts";
import styles from "./evidence-library.module.css";

export type RouteView = "both" | "baseline" | "after";
type MapGeometry = Parameters<typeof import("leaflet").geoJSON>[0];

export function FinalsRouteMap({ origin, comparison, layers, view, th }: { origin: FinalsOrigin; comparison: FinalsRouteComparison; layers: EvidenceLibraryLayer[]; view: RouteView; th: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let disposed = false;
    let map: LeafletMap | undefined;
    async function mount() {
      const L = await import("leaflet");
      if (disposed || !container.current) return;
      const bounds = L.latLngBounds([[origin.latitude, origin.longitude]]);
      for (const route of [comparison.baseline, comparison.after]) {
        for (const point of [...route.coordinates, ...route.connectors.flat()]) bounds.extend([point[1], point[0]]);
      }
      map = L.map(container.current, { scrollWheelZoom: false, preferCanvas: true });
      map.fitBounds(bounds, { padding: [45, 45], maxZoom: 16 });
      for (const layer of layers) {
        if (layer.data && ["road_geojson", "reporting-subdistricts"].includes(layer.id)) L.geoJSON(layer.data as MapGeometry, {
          style: { color: layer.id === "road_geojson" ? "#a7bbc4" : "#6b8895", weight: layer.id === "road_geojson" ? 1.2 : 1, fillOpacity: 0, dashArray: layer.id === "reporting-subdistricts" ? "5 6" : undefined },
        }).addTo(map);
      }
      const label = (text: string) => { const span = document.createElement("span"); span.textContent = text; return span; };
      for (const [key, color] of [["baseline", "#087f73"], ["after", "#853cb0"]] as const) {
        const route = comparison[key];
        if (route.status !== "available" || (view !== "both" && view !== key)) continue;
        const title = key === "baseline" ? (th ? "ก่อนเพิ่มการเปลี่ยนแปลงสมมติ" : "Before imposed disruption") : (th ? "หลังเพิ่มการเปลี่ยนแปลงสมมติ" : "After imposed disruption");
        if (route.coordinates.length > 1) L.polyline(route.coordinates.map(([x, y]) => [y, x] as [number, number]), { color, weight: key === "baseline" ? 7 : 4, opacity: .85, dashArray: key === "after" ? "10 6" : undefined }).bindTooltip(label(title)).addTo(map);
        for (const connector of route.connectors) L.polyline(connector.map(([x, y]) => [y, x] as [number, number]), { color, weight: 2, dashArray: "2 6" }).bindTooltip(label(th ? "จุดเชื่อมต่อตามสมมติฐาน" : "Assumed connector")).addTo(map);
        const destination = route.connectors[1]?.[1];
        if (destination) L.circleMarker([destination[1], destination[0]], { radius: key === "baseline" ? 10 : 6, color, weight: 3, fillColor: "white", fillOpacity: 1 }).bindTooltip(label(`${title}: ${route.destination_name}`), { direction: "top" }).addTo(map);
      }
      if (comparison.scenario_kind === "close_edge") for (const edge of comparison.changed_ids) {
        const index = comparison.baseline.edge_ids.indexOf(edge);
        const segment = comparison.baseline.coordinates.slice(index, index + 2);
        if (index >= 0 && segment.length === 2) L.polyline(segment.map(([x, y]) => [y, x] as [number, number]), { color: "#b64221", weight: 9, dashArray: "4 5" }).bindTooltip(label(th ? "ถนนที่กำหนดให้ปิดในสถานการณ์สมมติ" : "Road link closed in this scenario")).addTo(map);
      }
      L.circleMarker([origin.latitude, origin.longitude], { radius: 9, color: "#17384b", weight: 3, fillColor: "#f4bf43", fillOpacity: 1 }).bindTooltip(label(`${th ? "จุดเริ่มต้น" : "Start"}: ${origin.name}`), { permanent: true, direction: "top" }).addTo(map);
      map.attributionControl.setPrefix("Leaflet · FloodGuard");
      map.attributionControl.addAttribution('© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · Reporting boundaries: HDX Thailand COD-AB');
    }
    mount().catch(() => { if (!disposed) setFailed(true); });
    return () => { disposed = true; map?.remove(); };
  }, [origin, comparison, layers, view, th]);
  return <div><div ref={container} className={`${styles.map} ${styles.routeMap}`} role="region" aria-label={th ? "เส้นทางก่อนและหลังการเปลี่ยนแปลงสมมติ" : "Routes before and after an imposed disruption"} />{failed ? <p role="alert">{th ? "แผนที่ไม่พร้อม ดูผลและรหัสเส้นทางในตารางด้านล่าง" : "Map unavailable. Route results and identities remain available in the table below."}</p> : null}</div>;
}
