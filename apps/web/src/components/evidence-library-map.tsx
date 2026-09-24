"use client";

import type { Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";
import type { EvidenceLibraryAoi, EvidenceLibraryLayer } from "@floodguard/contracts";
import styles from "./evidence-library.module.css";

const COLORS = ["#087e8b", "#c16d19", "#7b53a0", "#c84752", "#387338", "#395da8"];
type MapGeometry = Parameters<typeof import("leaflet").geoJSON>[0];

function escapeLabel(value: string): string {
  const element = document.createElement("span");
  element.textContent = value;
  return element.innerHTML;
}
export function EvidenceLibraryMap({ aoi, layers, th, collapsedLayers = false }: { aoi: EvidenceLibraryAoi; layers: EvidenceLibraryLayer[]; th: boolean; collapsedLayers?: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let map: LeafletMap | undefined;
    async function mount() {
      const L = await import("leaflet");
      if (disposed || !container.current) return;
      map = L.map(container.current, { scrollWheelZoom: false, preferCanvas: true });
      const boundary = L.geoJSON(aoi.geometry as MapGeometry, { style: { color: "#183c53", weight: 2, dashArray: "6 5", fillOpacity: 0.025 } }).addTo(map);
      const bounds = boundary.getBounds();
      if (!bounds.isValid()) throw new Error("AOI geometry has no map bounds.");
      map.fitBounds(bounds, { padding: [24, 24] });
      const overlays: Record<string, import("leaflet").Layer> = {};
      for (const [index, layer] of layers.entries()) {
        const color = COLORS[index % COLORS.length];
        if (layer.image_url && layer.bounds) {
          overlays[escapeLabel(layer.title)] = L.imageOverlay(layer.image_url, layer.bounds, { opacity: 0.62, attribution: layer.attribution ? escapeLabel(layer.attribution) : undefined }).addTo(map);
        }
        if (layer.data) {
          overlays[escapeLabel(layer.title)] = L.geoJSON(layer.data as MapGeometry, {
            attribution: layer.attribution ? escapeLabel(layer.attribution) : undefined,
            style: { color, weight: 2, fillOpacity: 0.2 },
            pointToLayer: (_feature, location) => L.circleMarker(location, { radius: 5, color, fillOpacity: 0.8 }),
            onEachFeature: (feature, item) => {
              const label = document.createElement("span");
              label.textContent = `${layer.title} · ${String(feature.properties?.name ?? feature.properties?.name_th ?? feature.properties?.edge_id ?? feature.properties?.facility_id ?? feature.properties?.osm_id ?? feature.properties?.id ?? layer.role)}`;
              item.bindTooltip(label);
            },
          }).addTo(map);
        }
      }
      L.control.layers(undefined, overlays, { collapsed: collapsedLayers }).addTo(map);
      map.attributionControl.setPrefix("Leaflet · FloodGuard candidate evidence");
    }
    mount().catch((error: unknown) => { if (!disposed) setFailure(error instanceof Error ? error.message : "Map unavailable"); });
    return () => { disposed = true; map?.remove(); };
  }, [aoi, layers, collapsedLayers]);

  return <div>
    <div className={styles.map} ref={container} role="region" aria-label={th ? "แผนที่หลักฐานในพื้นที่ศึกษา" : "Study-area evidence map"} />
    {failure ? <p role="alert">{th ? "ไม่สามารถแสดงแผนที่ได้" : "Map unavailable"}: {failure}</p> : null}
    <p className={styles.hint}>{th ? "เส้นประคือกรอบค้นหา ไม่ใช่เขตตำบล · แสดงเฉพาะข้อมูลที่มีสิทธิ์เผยแพร่ · ไม่มีแผนที่ฐานภายนอก" : "Dashed outline: search AOI, not a subdistrict boundary. Only cleared geometry is shown. No external basemap required."}</p>
  </div>;
}
