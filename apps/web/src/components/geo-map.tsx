"use client";

import { useEffect, useRef } from "react";

import type { DatasetMode } from "@floodguard/contracts";

import { formatConfidence } from "@/lib/format";
import type { AreaRecord, FeatureCollection, Language } from "@/lib/types";

const CLASS_COLORS: Record<string, string> = {
  A: "#b42318",
  B: "#c65d16",
  C: "#b88700",
  D: "#25766d",
  E: "#5d6b78",
};

export function GeoMap({
  areas,
  selectedId,
  onSelect,
  language,
  showRoads = true,
  classFilter,
  height = "100%",
  areaFeatures,
  roadFeatures,
  datasetMode,
}: {
  areas: AreaRecord[];
  selectedId: string;
  onSelect: (areaId: string) => void;
  language: Language;
  showRoads?: boolean;
  classFilter?: Set<string>;
  height?: string;
  areaFeatures: FeatureCollection;
  roadFeatures: FeatureCollection;
  datasetMode: DatasetMode;
}) {
  const mapElement = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    let mapInstance: { remove: () => void } | undefined;
    let resizeTimer: number | undefined;

    async function mountMap() {
      const L = await import("leaflet");
      if (disposed || !mapElement.current) return;
      mapElement.current.replaceChildren();
      const map = L.map(mapElement.current, {
        attributionControl: false,
        zoomControl: true,
        minZoom: 10,
        maxZoom: 16,
        keyboard: true,
      });
      mapInstance = map;

      const visible = {
        ...areaFeatures,
        features: areaFeatures.features.filter((feature) => {
          const actionClass = String(feature.properties.action_class ?? "E");
          return !classFilter || classFilter.has(actionClass);
        }),
      };
      const areaLayer = L.geoJSON(visible as Parameters<typeof L.geoJSON>[0], {
        style: (feature) => {
          const actionClass = String(feature?.properties?.action_class ?? "E");
          const id = String(feature?.properties?.area_id ?? "");
          return {
            color: id === selectedId ? "#062f3d" : "#ffffff",
            weight: id === selectedId ? 4 : 2,
            fillColor: CLASS_COLORS[actionClass],
            fillOpacity: id === selectedId ? 0.9 : 0.68,
          };
        },
        onEachFeature: (feature, layer) => {
          const id = String(feature.properties?.area_id ?? "");
          const area = areas.find((item) => item.area_id === id);
          if (area) {
            const name = language === "th" ? area.area_name_th : area.area_name_en;
            layer.bindTooltip(`${name} · ${area.action_class} · FPPS ${area.fpps_0_100.toFixed(1)}`);
            layer.on("click", () => onSelect(id));
          }
        },
      }).addTo(map);

      if (showRoads) {
        L.geoJSON(roadFeatures as Parameters<typeof L.geoJSON>[0], {
          style: (feature) => ({
            color: Number(feature?.properties?.road_disruption_probability_0_1 ?? 0) >= 0.7 ? "#7a271a" : "#294c60",
            weight: 5,
            dashArray: "8 6",
            opacity: 0.9,
          }),
          onEachFeature: (feature, layer) => {
            const roadId = String(feature.properties?.road_id ?? "road");
            const probability = Number(feature.properties?.road_disruption_probability_0_1 ?? 0);
            layer.bindTooltip(`${roadId}: ${(probability * 100).toFixed(1)}% modelled disruption risk — not an observed closure`);
          },
        }).addTo(map);
      }

      if (areaLayer.getLayers().length > 0) {
        map.fitBounds(areaLayer.getBounds(), { padding: [28, 28] });
      } else {
        map.setView([18.02, 100.03], 12);
      }
      resizeTimer = window.setTimeout(() => map.invalidateSize(), 50);
    }

    void mountMap();
    return () => {
      disposed = true;
      if (resizeTimer !== undefined) window.clearTimeout(resizeTimer);
      mapInstance?.remove();
    };
  }, [areaFeatures, areas, classFilter, language, onSelect, roadFeatures, selectedId, showRoads]);

  return (
    <div className="geo-map-shell">
      <div
        className="geo-map"
        ref={mapElement}
        style={{ height }}
        role="region"
        aria-label={mapProvenanceLabel(language, datasetMode)}
      />
      <div className="map-legend" aria-label={language === "th" ? "คำอธิบายแผนที่" : "Map legend"}>
        {Object.entries(CLASS_COLORS).map(([key, color]) => (
          <span key={key}><i style={{ backgroundColor: color }} />{key}</span>
        ))}
        {showRoads && <span><i className="road-swatch" />{language === "th" ? "ความเสี่ยงถนนเชิงแบบจำลอง" : "Modelled road risk"}</span>}
      </div>
      <span className={`map-provenance-badge ${datasetMode}`}>
        {mapGeometryDisclosure(language, datasetMode)}
      </span>
      <details className="map-text-alternative">
        <summary>{language === "th" ? "ข้อความทดแทนแผนที่" : "Map text alternative"}</summary>
        <p>{mapProvenanceLabel(language, datasetMode)}</p>
        <ul>
          {areas.filter((area) => !classFilter || classFilter.has(area.action_class)).map((area) => (
            <li key={area.area_id}>
              <button type="button" onClick={() => onSelect(area.area_id)}>
                {language === "th" ? area.area_name_th : area.area_name_en}: {language === "th" ? "ชั้น" : "class"} {area.action_class}, FPPS {area.fpps_0_100.toFixed(1)}, {formatConfidence(area.confidence_class, language)}
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function mapGeometryDisclosure(language: Language, datasetMode: DatasetMode): string {
  if (datasetMode === "fixture_demo") {
    return language === "th"
      ? "เรขาคณิตสาธิต · ไม่ใช่เขตปกครอง"
      : "Synthetic geometry · not an administrative boundary";
  }
  if (datasetMode === "candidate") {
    return language === "th" ? "เรขาคณิตผู้สมัคร · ต้องตรวจสอบแหล่งที่มา" : "Candidate geometry · verify provenance";
  }
  return language === "th" ? "เรขาคณิตจากข้อมูลนำเข้าทางการ" : "Official-input geometry";
}

function mapProvenanceLabel(language: Language, datasetMode: DatasetMode): string {
  const labels = {
    fixture_demo: { th: "ข้อมูล GeoJSON สาธิต", en: "fixture-demo GeoJSON" },
    candidate: { th: "ข้อมูล GeoJSON ผู้สมัคร", en: "candidate-data GeoJSON" },
    official_input: { th: "ข้อมูล GeoJSON นำเข้าทางการ", en: "official-input GeoJSON" },
  } as const;
  return language === "th"
    ? `แผนที่เชิงพื้นที่จาก${labels[datasetMode].th}`
    : `Geospatial map from ${labels[datasetMode].en}`;
}
