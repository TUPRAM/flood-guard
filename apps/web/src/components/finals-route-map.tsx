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
    let resize: ResizeObserver | undefined;
    async function mount() {
      const L = await import("leaflet");
      if (disposed || !container.current) return;
      const bounds = L.latLngBounds([[origin.latitude, origin.longitude]]);
      for (const route of [comparison.baseline, comparison.after]) {
        for (const point of [...route.coordinates, ...route.connectors.flat()]) bounds.extend([point[1], point[0]]);
      }
      map = L.map(container.current, { scrollWheelZoom: false, preferCanvas: true, zoomAnimation: false });
      const fitRoutes = () => {
        if (!map) return;
        const size = map.getSize();
        map.fitBounds(bounds, { padding: [Math.min(35, size.x * .1), Math.min(35, size.y * .15)], maxZoom: 16, animate: false });
      };
      fitRoutes();
      resize = new ResizeObserver(() => {
        if (!disposed && map) {
          map.invalidateSize({ animate: false });
          fitRoutes();
        }
      });
      resize.observe(container.current);
      for (const layer of layers) {
        if (layer.data && layer.id === "sar-candidate_extent") L.geoJSON(layer.data as MapGeometry, {
          style: { color: "#356bb8", weight: .5, fillColor: "#356bb8", fillOpacity: .2 },
        }).addTo(map);
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
      const startLabel = label(th ? "จุดเริ่มต้น" : "Start");
      startLabel.dataset.routeStartLabel = "true";
      L.circleMarker([origin.latitude, origin.longitude], { radius: 9, color: "#17384b", weight: 3, fillColor: "#f4bf43", fillOpacity: 1 }).bindTooltip(startLabel, { permanent: true, direction: "top" }).addTo(map);
      map.attributionControl.setPrefix("Leaflet · FloodGuard");
      map.attributionControl.addAttribution('© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · Reporting boundaries: HDX Thailand COD-AB');
      const sentinelAttribution = layers.find((layer) => layer.id === "sar-candidate_extent")?.reason?.match(/Contains modified Copernicus Sentinel data \(\d{4}\)/)?.[0];
      if (sentinelAttribution) map.attributionControl.addAttribution(sentinelAttribution);
    }
    mount().catch(() => { if (!disposed) setFailed(true); });
    return () => { disposed = true; resize?.disconnect(); map?.remove(); };
  }, [origin, comparison, layers, view, th]);
  return <div className={styles.routeMapFrame}><p className={styles.hint} data-route-origin><strong>{th ? "จุดเริ่มต้น · หมุดสีเหลือง" : "Start · yellow marker"}:</strong> {origin.name}</p><div ref={container} className={`${styles.map} ${styles.routeMap}`} role="region" aria-label={th ? "เส้นทางก่อนและหลังการเปลี่ยนแปลงสมมติ" : "Routes before and after an imposed disruption"} />{failed ? <p role="alert">{th ? "แผนที่ไม่พร้อม ผลเส้นทางยังแสดงอยู่ เปิดรายละเอียดเส้นทางเพื่อดูข้อมูลแบบข้อความ" : "Map unavailable. Route results remain available; open Route details for the text record."}</p> : null}</div>;
}
