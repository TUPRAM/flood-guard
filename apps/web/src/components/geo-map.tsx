"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { DatasetMode } from "@floodguard/contracts";

import { formatConfidence } from "@/lib/format";
import {
  ACTION_CLASS_COLORS,
  SCENARIO_TONE_COLORS,
  formatServerDelta,
  scenarioMapPresentation,
} from "@/lib/scenario-presentation";
import type { AreaRecord, FeatureCollection, Language, ScenarioId } from "@/lib/types";

const ACTION_CLASS_LABELS = {
  A: { en: "Protect lives now", th: "ปกป้องชีวิตทันที" },
  B: { en: "Keep routes open", th: "รักษาเส้นทางให้ใช้งานได้" },
  C: { en: "Protect essential services", th: "คุ้มครองบริการจำเป็น" },
  D: { en: "Build resilience", th: "เสริมความยืดหยุ่น" },
  E: { en: "Monitor and verify", th: "ติดตามและตรวจสอบ" },
} as const;

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
  scenarioId = "baseline",
  showSelectionSheet = true,
  contextFeatures,
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
  scenarioId?: ScenarioId;
  showSelectionSheet?: boolean;
  contextFeatures?: FeatureCollection;
}) {
  const mapElement = useRef<HTMLDivElement>(null);
  const selectionSheetId = useId();
  const [selectionSheetOpen, setSelectionSheetOpen] = useState(true);
  const selectedArea = areas.find((area) => area.area_id === selectedId);
  const selectedScenarioResult = selectedArea?.scenario_results[scenarioId];
  const selectedPresentation = selectedArea
    ? scenarioMapPresentation(selectedArea.action_class, scenarioId, selectedScenarioResult)
    : undefined;

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

      if (contextFeatures?.features.length) {
        const lineContext = {
          ...contextFeatures,
          features: contextFeatures.features.filter((feature) => feature.geometry.type !== "Point"),
        };
        const contextLineLayer = L.geoJSON(lineContext as Parameters<typeof L.geoJSON>[0], {
          style: (feature) => {
            const contextType = String(feature?.properties?.context_type ?? "context");
            if (contextType === "river" || contextType === "drainage") {
              return {
                color: contextType === "river" ? "#5ca8c6" : "#87bed2",
                weight: contextType === "river" ? 5 : 3,
                opacity: 0.76,
              };
            }
            if (contextType === "principal_road") {
              return { color: "#83939c", weight: 3, opacity: 0.72 };
            }
            return {
              color: "#78909c",
              weight: 2,
              dashArray: "5 5",
              fillColor: "#dfecef",
              fillOpacity: 0.18,
            };
          },
          onEachFeature: (feature, layer) => {
            const fallback = String(feature.properties?.context_type ?? "Geographic context");
            const label = language === "th"
              ? String(feature.properties?.name_th ?? feature.properties?.name_en ?? fallback)
              : String(feature.properties?.name_en ?? feature.properties?.name_th ?? fallback);
            const disclosure = datasetMode === "fixture_demo"
              ? language === "th" ? "บริบทสังเคราะห์ออฟไลน์ · ยังไม่ยืนยัน" : "Synthetic offline context · not verified"
              : language === "th" ? "บริบทเชิงพื้นที่" : "Geographic context";
            layer.bindTooltip(`${label} · ${disclosure}`);
          },
        }).addTo(map);
        contextLineLayer.bringToBack();
      }

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
          const area = areas.find((item) => item.area_id === id);
          const presentation = scenarioMapPresentation(
            actionClass,
            scenarioId,
            area?.scenario_results[scenarioId],
          );
          return {
            color: id === selectedId ? "#062f3d" : presentation.outlineColor,
            weight: id === selectedId ? 4 : scenarioId === "baseline" ? 2 : 3,
            fillColor: presentation.fillColor,
            fillOpacity: id === selectedId ? 0.9 : scenarioId === "baseline" ? 0.68 : 0.74,
          };
        },
        onEachFeature: (feature, layer) => {
          const id = String(feature.properties?.area_id ?? "");
          const area = areas.find((item) => item.area_id === id);
          if (area) {
            const name = language === "th" ? area.area_name_th : area.area_name_en;
            const result = area.scenario_results[scenarioId];
            const scenarioText = scenarioId === "baseline"
              ? ""
              : language === "th"
                ? ` · ผลต่างการเข้าถึงจากเซิร์ฟเวอร์ ${formatServerDelta(result.delta)}`
                : ` · server access delta ${formatServerDelta(result.delta)}`;
            layer.bindTooltip(`${name} · ${area.action_class} · FPPS ${area.fpps_0_100.toFixed(1)}${scenarioText}`);
            layer.on("click", () => onSelect(id));
          }
        },
      }).addTo(map);

      if (contextFeatures?.features.some((feature) => feature.geometry.type === "Point")) {
        const pointContext = {
          ...contextFeatures,
          features: contextFeatures.features.filter((feature) => feature.geometry.type === "Point"),
        };
        L.geoJSON(pointContext as Parameters<typeof L.geoJSON>[0], {
          pointToLayer: (feature, latlng) => {
            const isFacility = String(feature.properties?.context_type ?? "settlement") === "facility";
            return L.circleMarker(latlng, {
              radius: isFacility ? 6 : 4,
              color: isFacility ? "#153f51" : "#527083",
              fillColor: isFacility ? "#ffffff" : "#dcebf0",
              fillOpacity: 0.95,
              weight: 2,
            });
          },
          onEachFeature: (feature, layer) => {
            const fallback = String(feature.properties?.context_type ?? "Geographic context");
            const label = language === "th"
              ? String(feature.properties?.name_th ?? feature.properties?.name_en ?? fallback)
              : String(feature.properties?.name_en ?? feature.properties?.name_th ?? fallback);
            const disclosure = datasetMode === "fixture_demo"
              ? language === "th" ? "บริบทสังเคราะห์ออฟไลน์ · ยังไม่ยืนยัน" : "Synthetic offline context · not verified"
              : language === "th" ? "บริบทเชิงพื้นที่" : "Geographic context";
            layer.bindTooltip(`${label} · ${disclosure}`);
          },
        }).addTo(map);
      }

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
  }, [areaFeatures, areas, classFilter, contextFeatures, datasetMode, language, onSelect, roadFeatures, scenarioId, selectedId, showRoads]);

  return (
    <div
      className="geo-map-shell"
      data-scenario-id={scenarioId}
      data-scenario-tone={selectedPresentation?.tone ?? "unavailable"}
      data-selected-area={selectedId}
    >
      <div
        className="geo-map"
        ref={mapElement}
        style={{ height }}
        role="region"
        aria-label={mapProvenanceLabel(language, datasetMode)}
      />
      {showSelectionSheet && selectedArea && (
        <aside className={`map-selection-sheet ${selectionSheetOpen ? "open" : "closed"}`} aria-label={language === "th" ? "พื้นที่รายงานที่เลือก" : "Selected reporting area"}>
          <button
            type="button"
            className="map-selection-sheet-toggle"
            aria-expanded={selectionSheetOpen}
            aria-controls={selectionSheetId}
            onClick={() => setSelectionSheetOpen((open) => !open)}
          >
            <span>
              <small>{language === "th" ? "พื้นที่รายงานที่เลือก" : "Selected reporting area"}</small>
              <b>{language === "th" ? selectedArea.area_name_th : selectedArea.area_name_en}</b>
            </span>
            <strong className={`class-${selectedArea.action_class.toLowerCase()}`}>
              {language === "th" ? "ชั้น" : "Class"} {selectedArea.action_class}
            </strong>
            <span aria-hidden="true">{selectionSheetOpen ? "−" : "+"}</span>
          </button>
          <div id={selectionSheetId} className="map-selection-sheet-body" hidden={!selectionSheetOpen} aria-live="polite">
            <dl>
              <div><dt>FPPS</dt><dd>{selectedArea.fpps_0_100.toFixed(1)}</dd></div>
              <div><dt>{language === "th" ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selectedArea.confidence_class, language)}</dd></div>
              <div><dt>{language === "th" ? "เวลาข้อมูล" : "Source time"}</dt><dd>{selectedArea.source_timestamp}</dd></div>
              {scenarioId !== "baseline" && selectedScenarioResult && (
                <div>
                  <dt>{language === "th" ? "ผลต่างการเข้าถึงจากเซิร์ฟเวอร์" : "Server-produced access delta"}</dt>
                  <dd className={`scenario-${selectedPresentation?.tone ?? "unavailable"}`}>{formatServerDelta(selectedScenarioResult.delta)}</dd>
                </div>
              )}
            </dl>
            {scenarioId !== "baseline" && (
              <p>{language === "th" ? "สีของพื้นที่ใช้ค่าผลต่างจากเอาต์พุตสถานการณ์ ไม่มีสูตรตัดสินใจในเบราว์เซอร์" : "Area color uses the scenario artifact delta; no decision formula runs in the browser."}</p>
            )}
          </div>
        </aside>
      )}
      <div className="map-legend" aria-label={language === "th" ? "คำอธิบายแผนที่" : "Map legend"}>
        {scenarioId !== "baseline" && (
          <div className="scenario-map-legend">
            <span><i style={{ backgroundColor: SCENARIO_TONE_COLORS.improves }} />{language === "th" ? "การสูญเสียการเข้าถึงลดลง" : "Access loss improves"}</span>
            <span><i style={{ backgroundColor: SCENARIO_TONE_COLORS.neutral }} />{language === "th" ? "ไม่เปลี่ยนแปลง" : "No change"}</span>
            <span><i style={{ backgroundColor: SCENARIO_TONE_COLORS.worsens }} />{language === "th" ? "การสูญเสียการเข้าถึงเพิ่มขึ้น" : "Access loss worsens"}</span>
          </div>
        )}
        <div className="action-class-legend">
          {Object.entries(ACTION_CLASS_COLORS).map(([key, color]) => {
            const label = ACTION_CLASS_LABELS[key as keyof typeof ACTION_CLASS_LABELS];
            return <span key={key}><i style={{ backgroundColor: color }} /><b>{key}</b><small>{label[language]}</small></span>;
          })}
        </div>
        {showRoads && <span><i className="road-swatch" />{language === "th" ? "ความเสี่ยงถนนเชิงแบบจำลอง" : "Modelled road risk"}</span>}
        {!!contextFeatures?.features.length && <span><i className="context-swatch" />{datasetMode === "fixture_demo" ? (language === "th" ? "บริบทสังเคราะห์ออฟไลน์" : "Synthetic offline context") : (language === "th" ? "บริบทภูมิศาสตร์" : "Geographic context")}</span>}
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
                {language === "th" ? area.area_name_th : area.area_name_en}: {language === "th" ? "ชั้น" : "class"} {area.action_class}, FPPS {area.fpps_0_100.toFixed(1)}, {formatConfidence(area.confidence_class, language)}{scenarioId !== "baseline" ? `, ${language === "th" ? "ผลต่างการเข้าถึงจากเซิร์ฟเวอร์" : "server access delta"} ${formatServerDelta(area.scenario_results[scenarioId].delta)}` : ""}
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
