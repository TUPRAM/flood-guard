"use client";

import type { GeoJSON as LeafletGeoJson, Layer, LayerGroup, Map as LeafletMap, Path } from "leaflet";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import type { DatasetMode } from "@floodguard/contracts";

import { formatConfidence } from "@/lib/format";
import {
  ACTION_CLASS_COLORS,
  SCENARIO_TONE_COLORS,
  formatServerDelta,
  scenarioMapPresentation,
} from "@/lib/scenario-presentation";
import type { AreaRecord, FeatureCollection, GeoFeature, Language, ScenarioId } from "@/lib/types";

const ACTION_CLASS_LABELS = {
  A: { en: "Protect lives now", th: "ปกป้องชีวิตทันที" },
  B: { en: "Keep routes open", th: "รักษาเส้นทางให้ใช้งานได้" },
  C: { en: "Protect essential services", th: "คุ้มครองบริการจำเป็น" },
  D: { en: "Build resilience", th: "เสริมความยืดหยุ่น" },
  E: { en: "Monitor and verify", th: "ติดตามและตรวจสอบ" },
} as const;

type LeafletModule = typeof import("leaflet");
type FeatureLayer = Layer & {
  feature?: { properties?: Record<string, unknown> };
  getBounds?: () => import("leaflet").LatLngBounds;
  setStyle?: (style: import("leaflet").PathOptions) => void;
};

interface GeoMapProps {
  areas: AreaRecord[];
  selectedId: string;
  onSelect: (areaId: string) => void;
  language: Language;
  showRoads?: boolean;
  showFacilities?: boolean;
  showAccess?: boolean;
  classFilter?: Set<string>;
  height?: string;
  areaFeatures: FeatureCollection;
  roadFeatures: FeatureCollection;
  regionalRoadCount?: number;
  roadDatasetTotal?: number;
  roadDetailState?: "bundled" | "loading" | "ready" | "unavailable";
  facilityFeatures?: FeatureCollection;
  accessFeatures?: FeatureCollection;
  datasetMode: DatasetMode;
  scenarioId?: ScenarioId;
  showSelectionSheet?: boolean;
  contextFeatures?: FeatureCollection;
  attributions?: string[];
}

export function GeoMap({
  areas,
  selectedId,
  onSelect,
  language,
  showRoads = true,
  showFacilities = true,
  showAccess = true,
  classFilter,
  height = "100%",
  areaFeatures,
  roadFeatures,
  regionalRoadCount = roadFeatures.features.length,
  roadDatasetTotal = roadFeatures.features.length,
  roadDetailState = "bundled",
  facilityFeatures = EMPTY_FEATURE_COLLECTION,
  accessFeatures = EMPTY_FEATURE_COLLECTION,
  datasetMode,
  scenarioId = "baseline",
  showSelectionSheet = true,
  contextFeatures = EMPTY_FEATURE_COLLECTION,
  attributions = [],
}: GeoMapProps) {
  const mapElement = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<LeafletModule | null>(null);
  const areaLayerRef = useRef<LeafletGeoJson | null>(null);
  const contextLayerRef = useRef<LayerGroup | null>(null);
  const roadLayerRef = useRef<LayerGroup | null>(null);
  const facilityLayerRef = useRef<LayerGroup | null>(null);
  const accessLayerRef = useRef<LayerGroup | null>(null);
  const hasFitRegionalBounds = useRef(false);
  const previousSelectedId = useRef(selectedId);
  const selectionSheetId = useId();
  const [mapReady, setMapReady] = useState(false);
  const [selectionSheetOpen, setSelectionSheetOpen] = useState(true);
  const [visibleRoadCount, setVisibleRoadCount] = useState(0);
  const [facilityPresentation, setFacilityPresentation] = useState<"clusters" | "features">("clusters");
  const selectedArea = areas.find((area) => area.area_id === selectedId);
  const selectedScenarioResult = selectedArea?.scenario_results[scenarioId];
  const selectedPresentation = selectedArea
    ? scenarioMapPresentation(selectedArea.action_class, scenarioId, selectedScenarioResult)
    : undefined;

  useEffect(() => {
    let disposed = false;
    let mountedMap: LeafletMap | null = null;
    let resizeTimer: number | undefined;

    async function mountMap() {
      const L = await import("leaflet");
      if (disposed || !mapElement.current) return;
      mapElement.current.replaceChildren();
      mountedMap = L.map(mapElement.current, {
        attributionControl: false,
        zoomControl: true,
        minZoom: 9,
        maxZoom: 17,
        keyboard: true,
        preferCanvas: true,
      });
      mountedMap.setView([20.36, 99.89], 10);
      mapRef.current = mountedMap;
      leafletRef.current = L;
      setMapReady(true);
      resizeTimer = window.setTimeout(() => mountedMap?.invalidateSize(), 60);
    }

    void mountMap();
    return () => {
      disposed = true;
      if (resizeTimer !== undefined) window.clearTimeout(resizeTimer);
      setMapReady(false);
      areaLayerRef.current = null;
      contextLayerRef.current = null;
      roadLayerRef.current = null;
      facilityLayerRef.current = null;
      accessLayerRef.current = null;
      leafletRef.current = null;
      mapRef.current = null;
      mountedMap?.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!mapReady || !map || !L) return;
    areaLayerRef.current?.remove();
    const visible: FeatureCollection = {
      ...areaFeatures,
      features: areaFeatures.features.filter((feature) => {
        const actionClass = String(feature.properties.action_class ?? "E");
        return !classFilter || classFilter.has(actionClass);
      }),
    };
    const layer = L.geoJSON(visible as Parameters<typeof L.geoJSON>[0], {
      style: (feature) => areaStyle(
        String(feature?.properties?.area_id ?? ""),
        String(feature?.properties?.action_class ?? "E"),
        selectedId,
        scenarioId,
        areas,
      ),
      onEachFeature: (feature, featureLayer) => {
        const id = String(feature.properties?.area_id ?? "");
        const area = areas.find((item) => item.area_id === id);
        if (!area) return;
        const name = language === "th" ? area.area_name_th : area.area_name_en;
        const result = area.scenario_results[scenarioId];
        const scenarioText = scenarioId === "baseline"
          ? ""
          : language === "th"
            ? ` · ผลต่างการเข้าถึงจากเซิร์ฟเวอร์ ${formatServerDelta(result.delta)}`
            : ` · server access delta ${formatServerDelta(result.delta)}`;
        bindTextTooltip(featureLayer, `${name} · ${area.action_class} · FPPS ${area.fpps_0_100.toFixed(1)}${scenarioText}`, { sticky: true });
        featureLayer.on("click", () => onSelect(id));
      },
    }).addTo(map);
    areaLayerRef.current = layer;
    if (!hasFitRegionalBounds.current && layer.getLayers().length > 0) {
      map.fitBounds(layer.getBounds(), { padding: [28, 28] });
      hasFitRegionalBounds.current = true;
      previousSelectedId.current = selectedId;
    }
    return () => {
      layer.remove();
      if (areaLayerRef.current === layer) areaLayerRef.current = null;
    };
  }, [areaFeatures, areas, classFilter, language, mapReady, onSelect, scenarioId, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = areaLayerRef.current;
    if (!mapReady || !map || !layer || previousSelectedId.current === selectedId) return;
    previousSelectedId.current = selectedId;
    let selectedBounds: import("leaflet").LatLngBounds | undefined;
    layer.eachLayer((candidate) => {
      const featureLayer = candidate as FeatureLayer;
      if (String(featureLayer.feature?.properties?.area_id ?? "") === selectedId) {
        selectedBounds = featureLayer.getBounds?.();
      }
    });
    if (selectedBounds?.isValid()) {
      map.fitBounds(selectedBounds, { animate: false, maxZoom: 13, padding: [42, 42] });
    }
  }, [mapReady, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!mapReady || !map || !L) return;
    contextLayerRef.current?.remove();
    const group = L.layerGroup().addTo(map);
    contextLayerRef.current = group;
    if (contextFeatures.features.length > 0) {
      L.geoJSON(contextFeatures as Parameters<typeof L.geoJSON>[0], {
        style: (feature) => contextStyle(String(feature?.properties?.context_type ?? "context")),
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
          radius: String(feature.properties?.context_type ?? "") === "facility" ? 6 : 4,
          color: "#527083",
          fillColor: "#dcebf0",
          fillOpacity: 0.92,
          weight: 2,
        }),
        onEachFeature: (feature, featureLayer) => {
          const fallback = String(feature.properties?.context_type ?? "Geographic context");
          const label = language === "th"
            ? String(feature.properties?.name_th ?? feature.properties?.name_en ?? fallback)
            : String(feature.properties?.name_en ?? feature.properties?.name_th ?? fallback);
          bindTextTooltip(featureLayer, `${label} · ${datasetMode === "fixture_demo" ? "Synthetic offline context · not verified" : "Geographic context"}`);
        },
      }).addTo(group);
      group.eachLayer((candidate) => {
        if (candidate instanceof L.Path) (candidate as Path).bringToBack();
      });
    }
    return () => {
      group.remove();
      if (contextLayerRef.current === group) contextLayerRef.current = null;
    };
  }, [contextFeatures, datasetMode, language, mapReady]);

  const renderRoads = useCallback(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!map || !L) return;
    roadLayerRef.current?.remove();
    if (!showRoads) {
      roadLayerRef.current = null;
      setVisibleRoadCount(0);
      return;
    }
    const detailMode = map.getZoom() >= 13;
    const visibleFeatures = roadFeatures.features.filter((feature) => {
      const properties = feature.properties;
      if (detailMode) return String(properties.area_id ?? "") === selectedId;
      const highway = String(properties.osm_highway ?? properties.road_class ?? "");
      return Boolean(properties.bridge_flag)
        || ["trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary"].includes(highway);
    });
    const group = L.layerGroup().addTo(map);
    L.geoJSON({ ...roadFeatures, features: visibleFeatures } as Parameters<typeof L.geoJSON>[0], {
      style: (feature) => {
        const probability = Number(feature?.properties?.road_disruption_probability_0_1 ?? 0);
        const bridge = Boolean(feature?.properties?.bridge_flag);
        return {
          color: probability >= 0.45 ? "#9b2c20" : probability >= 0.25 ? "#b75d24" : "#31586b",
          weight: bridge ? 4 : detailMode ? 2.4 : 2.8,
          dashArray: bridge ? undefined : detailMode ? undefined : "7 5",
          opacity: bridge ? 0.95 : detailMode ? 0.76 : 0.82,
        };
      },
      onEachFeature: (feature, featureLayer) => {
        const properties = feature.properties ?? {};
        const name = String(properties.road_name || properties.road_id || "road candidate");
        const probability = Number(properties.road_disruption_probability_0_1 ?? 0);
        const warning = language === "th"
          ? "ความเสี่ยงเชิงแบบจำลอง · ไม่ใช่การปิดถนนที่สังเกตจริง"
          : "modelled candidate risk · not an observed closure";
        bindTextTooltip(featureLayer, `${name} · ${(probability * 100).toFixed(1)}% · ${warning}`, { sticky: true });
      },
    }).addTo(group);
    roadLayerRef.current = group;
    setVisibleRoadCount(visibleFeatures.length);
  }, [language, roadFeatures, selectedId, showRoads]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    renderRoads();
    map.on("zoomend", renderRoads);
    return () => {
      map.off("zoomend", renderRoads);
      roadLayerRef.current?.remove();
      roadLayerRef.current = null;
    };
  }, [mapReady, renderRoads]);

  const renderFacilities = useCallback(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!map || !L) return;
    facilityLayerRef.current?.remove();
    if (!showFacilities) {
      facilityLayerRef.current = null;
      return;
    }
    const detailMode = map.getZoom() >= 13;
    const group = L.layerGroup().addTo(map);
    if (detailMode) {
      setFacilityPresentation("features");
      const visible = facilityFeatures.features.filter((feature) => String(feature.properties.area_id ?? "") === selectedId);
      L.geoJSON({ ...facilityFeatures, features: visible } as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
          radius: 6,
          color: "#415961",
          fillColor: "#ffffff",
          fillOpacity: 0.96,
          weight: 2,
        }),
        onEachFeature: (feature, featureLayer) => {
          const properties = feature.properties ?? {};
          const name = String(properties.facility_name || properties.facility_id || "Facility candidate");
          const warning = language === "th"
            ? "สถานที่จากข้อมูลเปิด · บทบาทฉุกเฉินและการเปิดใช้งานยังไม่ยืนยัน"
            : "Open-context candidate · emergency role and current operation unverified";
          bindTextTooltip(featureLayer, `${name} · ${warning}`, { sticky: true });
        },
      }).addTo(group);
    } else {
      setFacilityPresentation("clusters");
      for (const cluster of facilityClusters(facilityFeatures, accessFeatures)) {
        const marker = L.marker(cluster.latlng, {
          icon: L.divIcon({
            className: "facility-cluster-marker",
            html: `<span aria-hidden="true">${cluster.count}</span>`,
            iconSize: [34, 34],
            iconAnchor: [17, 17],
          }),
          keyboard: true,
          title: `${cluster.count} unverified facility candidates`,
        }).addTo(group);
        const label = language === "th"
          ? `${cluster.count} สถานที่ผู้สมัครจากข้อมูลเปิด · ยังไม่ยืนยัน`
          : `${cluster.count} open-context facility candidates · unverified`;
        bindTextTooltip(marker, label);
      }
    }
    facilityLayerRef.current = group;
  }, [accessFeatures, facilityFeatures, language, selectedId, showFacilities]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    renderFacilities();
    map.on("zoomend", renderFacilities);
    return () => {
      map.off("zoomend", renderFacilities);
      facilityLayerRef.current?.remove();
      facilityLayerRef.current = null;
    };
  }, [mapReady, renderFacilities]);

  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!mapReady || !map || !L) return;
    accessLayerRef.current?.remove();
    if (!showAccess) {
      accessLayerRef.current = null;
      return;
    }
    const group = L.layerGroup().addTo(map);
    L.geoJSON(accessFeatures as Parameters<typeof L.geoJSON>[0], {
      pointToLayer: (feature, latlng) => {
        const selected = String(feature.properties?.area_id ?? "") === selectedId;
        return L.circleMarker(latlng, {
          radius: selected ? 11 : 7,
          color: selected ? "#6f4300" : "#96631d",
          fillColor: "#f4bc4f",
          fillOpacity: selected ? 0.72 : 0.42,
          weight: selected ? 3 : 2,
          dashArray: "4 3",
        });
      },
      onEachFeature: (feature, featureLayer) => {
        const properties = feature.properties ?? {};
        const count = Number(properties.people_losing_30_min_access ?? 0);
        const warning = language === "th"
          ? "หลักฐานการเข้าถึงเชิงแบบจำลอง · ไม่ใช่การหยุดบริการที่สังเกตจริง"
          : "modelled access evidence · not an observed service outage";
        bindTextTooltip(featureLayer, `${count.toLocaleString()} ${language === "th" ? "คนสูญเสียการเข้าถึง 30 นาที" : "people lose 30-min access"} · ${warning}`);
      },
    }).addTo(group);
    accessLayerRef.current = group;
    return () => {
      group.remove();
      if (accessLayerRef.current === group) accessLayerRef.current = null;
    };
  }, [accessFeatures, language, mapReady, selectedId, showAccess]);

  return (
    <div
      className={`geo-map-shell ${attributions.length > 0 ? "has-attribution" : ""}`}
      data-map-ready={mapReady}
      data-scenario-id={scenarioId}
      data-scenario-tone={selectedPresentation?.tone ?? "unavailable"}
      data-selected-area={selectedId}
      data-road-feature-count={roadFeatures.features.length}
      data-regional-road-count={regionalRoadCount}
      data-road-dataset-total={roadDatasetTotal}
      data-road-detail-state={roadDetailState}
      data-visible-road-count={visibleRoadCount}
      data-facility-feature-count={facilityFeatures.features.length}
      data-facility-presentation={facilityPresentation}
      data-access-feature-count={accessFeatures.features.length}
    >
      <div
        className="geo-map"
        ref={mapElement}
        style={{ height }}
        role="region"
        aria-label={mapProvenanceLabel(language, datasetMode)}
      />
      {(roadDetailState === "loading" || roadDetailState === "unavailable") && (
        <p className={`map-detail-notice ${roadDetailState}`} role="status" aria-live="polite">
          {roadDetailState === "loading"
            ? (language === "th" ? "กำลังโหลดรายละเอียดถนนของพื้นที่ที่เลือก โดยยังแสดงถนนผู้สมัครระดับภูมิภาค" : "Loading selected-area road detail; bounded regional candidates remain visible.")
            : (language === "th" ? "ไม่มีรายละเอียดถนนของพื้นที่ที่เลือก ขณะนี้แสดงเฉพาะถนนผู้สมัครระดับภูมิภาคที่จำกัดจำนวน" : "Selected-area road detail unavailable; showing bounded regional candidates.")}
        </p>
      )}
      {showSelectionSheet && selectedArea && (
        <aside className={`map-selection-sheet ${selectionSheetOpen ? "open" : "closed"}`} aria-label={language === "th" ? "พื้นที่รายงานที่เลือก" : "Selected reporting area"}>
          <button
            type="button"
            className="map-selection-sheet-toggle"
            aria-expanded={selectionSheetOpen}
            aria-controls={selectionSheetId}
            onClick={() => setSelectionSheetOpen((open) => !open)}
          >
            <span><small>{language === "th" ? "พื้นที่รายงานที่เลือก" : "Selected reporting area"}</small><b>{language === "th" ? selectedArea.area_name_th : selectedArea.area_name_en}</b></span>
            <strong className={`class-${selectedArea.action_class.toLowerCase()}`}>{language === "th" ? "ชั้น" : "Class"} {selectedArea.action_class}</strong>
            <span aria-hidden="true">{selectionSheetOpen ? "−" : "+"}</span>
          </button>
          <div id={selectionSheetId} className="map-selection-sheet-body" hidden={!selectionSheetOpen} aria-live="polite">
            <dl>
              <div><dt>FPPS</dt><dd>{selectedArea.fpps_0_100.toFixed(1)}</dd></div>
              <div><dt>{language === "th" ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selectedArea.confidence_class, language)}</dd></div>
              <div><dt>{language === "th" ? "เวลาข้อมูล" : "Source time"}</dt><dd>{selectedArea.source_timestamp}</dd></div>
              {scenarioId !== "baseline" && selectedScenarioResult && <div><dt>{language === "th" ? "ผลต่างการเข้าถึงจากเซิร์ฟเวอร์" : "Server-produced access delta"}</dt><dd className={`scenario-${selectedPresentation?.tone ?? "unavailable"}`}>{formatServerDelta(selectedScenarioResult.delta)}</dd></div>}
            </dl>
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
        {showRoads && <span><i className="road-swatch" />{language === "th" ? `ความเสี่ยงถนนเชิงแบบจำลอง · แสดง ${visibleRoadCount.toLocaleString()}` : `Modelled road risk · ${visibleRoadCount.toLocaleString()} shown`}</span>}
        {showFacilities && facilityFeatures.features.length > 0 && <span><i className="facility-swatch" />{language === "th" ? "สถานที่ผู้สมัครที่ยังไม่ยืนยัน" : "Unverified facility candidates"}</span>}
        {showAccess && accessFeatures.features.length > 0 && <span><i className="access-swatch" />{language === "th" ? "หลักฐานการเข้าถึงเชิงแบบจำลอง" : "Modelled access evidence"}</span>}
        {contextFeatures.features.length > 0 && <span><i className="context-swatch" />{datasetMode === "fixture_demo" ? (language === "th" ? "บริบทสังเคราะห์ออฟไลน์" : "Synthetic offline context") : (language === "th" ? "บริบทภูมิศาสตร์" : "Geographic context")}</span>}
      </div>
      {attributions.length > 0 && (
        <p className="map-attribution" aria-label={language === "th" ? "แหล่งที่มาของข้อมูลแผนที่" : "Map data attribution"}>
          <strong>{language === "th" ? "แหล่งข้อมูล:" : "Data attribution:"}</strong>{" "}
          {attributions.map((attribution, index) => (
            <span key={attribution}>
              {index > 0 && " · "}
              {attribution === "© OpenStreetMap contributors"
                ? <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="license noopener noreferrer">{attribution}</a>
                : attribution}
            </span>
          ))}
        </p>
      )}
      <span className={`map-provenance-badge ${datasetMode}`}>{mapGeometryDisclosure(language, datasetMode)}</span>
      <details className="map-text-alternative">
        <summary>{language === "th" ? "ข้อความทดแทนแผนที่" : "Map text alternative"}</summary>
        <p>{mapProvenanceLabel(language, datasetMode)}</p>
        <p>{language === "th"
          ? `${areaFeatures.features.length} พื้นที่ · ${roadFeatures.features.length.toLocaleString()} ถนนผู้สมัคร · ${facilityFeatures.features.length} สถานที่ผู้สมัคร · ${accessFeatures.features.length} จุดหลักฐานการเข้าถึง`
          : `${areaFeatures.features.length} areas · ${roadFeatures.features.length.toLocaleString()} road candidates · ${facilityFeatures.features.length} facility candidates · ${accessFeatures.features.length} access-evidence points`}</p>
        {datasetMode === "candidate" && <p className="map-candidate-warning">{language === "th" ? "สถานที่และถนนเป็นหลักฐานผู้สมัคร ไม่ใช่ที่พักพิงหรือการปิดถนนที่ยืนยันแล้ว" : "Facilities and roads are candidate evidence, not confirmed shelters or observed closures."}</p>}
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

const EMPTY_FEATURE_COLLECTION: FeatureCollection = { type: "FeatureCollection", name: "empty", features: [] };

function areaStyle(areaId: string, actionClass: string, selectedId: string, scenarioId: ScenarioId, areas: AreaRecord[]): import("leaflet").PathOptions {
  const area = areas.find((item) => item.area_id === areaId);
  const presentation = scenarioMapPresentation(actionClass, scenarioId, area?.scenario_results[scenarioId]);
  return {
    color: areaId === selectedId ? "#052e3b" : presentation.outlineColor,
    weight: areaId === selectedId ? 4 : scenarioId === "baseline" ? 2 : 3,
    fillColor: presentation.fillColor,
    fillOpacity: areaId === selectedId ? 0.82 : scenarioId === "baseline" ? 0.5 : 0.64,
  };
}

function contextStyle(contextType: string): import("leaflet").PathOptions {
  if (contextType === "river" || contextType === "drainage") {
    return { color: contextType === "river" ? "#5ca8c6" : "#87bed2", weight: contextType === "river" ? 5 : 3, opacity: 0.76 };
  }
  if (contextType === "principal_road") return { color: "#83939c", weight: 3, opacity: 0.72 };
  return { color: "#78909c", weight: 2, dashArray: "5 5", fillColor: "#dfecef", fillOpacity: 0.18 };
}

function bindTextTooltip(layer: Layer, text: string, options?: import("leaflet").TooltipOptions): void {
  const node = document.createElement("span");
  node.textContent = text;
  layer.bindTooltip(node, options);
}

export function facilityClusters(facilities: FeatureCollection, access: FeatureCollection): Array<{ areaId: string; count: number; latlng: [number, number] }> {
  const accessCoordinates = new Map<string, [number, number]>();
  for (const feature of access.features) {
    if (feature.geometry.type !== "Point") continue;
    const [longitude, latitude] = feature.geometry.coordinates as [number, number];
    if (Number.isFinite(longitude) && Number.isFinite(latitude)) {
      accessCoordinates.set(String(feature.properties.area_id ?? ""), [latitude, longitude]);
    }
  }
  const grouped = new Map<string, GeoFeature[]>();
  for (const feature of facilities.features) {
    const areaId = String(feature.properties.area_id ?? "");
    grouped.set(areaId, [...(grouped.get(areaId) ?? []), feature]);
  }
  return [...grouped.entries()].flatMap(([areaId, features]) => {
    const points = features
      .filter((feature) => feature.geometry.type === "Point")
      .map((feature) => feature.geometry.coordinates as [number, number])
      .filter(([longitude, latitude]) => Number.isFinite(longitude) && Number.isFinite(latitude));
    if (points.length > 0) {
      const longitude = points.reduce((sum, point) => sum + point[0], 0) / points.length;
      const latitude = points.reduce((sum, point) => sum + point[1], 0) / points.length;
      return [{ areaId, count: features.length, latlng: [latitude, longitude] }];
    }
    const accessPoint = accessCoordinates.get(areaId);
    return accessPoint ? [{ areaId, count: features.length, latlng: accessPoint }] : [];
  });
}

function mapGeometryDisclosure(language: Language, datasetMode: DatasetMode): string {
  if (datasetMode === "fixture_demo") return language === "th" ? "เรขาคณิตสาธิต · ไม่ใช่เขตปกครอง" : "Synthetic geometry · not an administrative boundary";
  if (datasetMode === "candidate") return language === "th" ? "ขอบเขตแม่สายจากข้อมูลเปิด · ผู้สมัคร · ไม่ใช่ระบบปฏิบัติการ" : "Mae Sai open-context boundary · candidate · non-operational";
  return language === "th" ? "เรขาคณิตจากข้อมูลนำเข้าทางการ" : "Official-input geometry";
}

function mapProvenanceLabel(language: Language, datasetMode: DatasetMode): string {
  if (datasetMode === "fixture_demo") return language === "th" ? "แผนที่ GeoJSON สาธิตแบบออฟไลน์" : "Offline map from fixture-demo GeoJSON";
  if (datasetMode === "candidate") return language === "th" ? "แผนที่แม่สายจากข้อมูลเปิดที่ติดตามแหล่งที่มา สถานะผู้สมัครและไม่ใช่ระบบปฏิบัติการ" : "Mae Sai map from provenance-tracked open context; candidate and non-operational";
  return language === "th" ? "แผนที่จากข้อมูลนำเข้าทางการ" : "Map from official-input GeoJSON";
}
