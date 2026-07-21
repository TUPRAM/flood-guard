"use client";

import type { GeoJSON as LeafletGeoJson, Layer, LayerGroup, Map as LeafletMap, Path, TileLayer as LeafletTileLayer } from "leaflet";
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
  visualPalette?: "default" | "public-blue";
  enableBasemaps?: boolean;
}

type BasemapId = "street" | "satellite" | "terrain";

const BASEMAPS: Record<BasemapId, {
  url: string;
  maxZoom: number;
  labels: Record<Language, string>;
  attributions: string[];
}> = {
  street: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    maxZoom: 19,
    labels: { en: "Street", th: "ถนน" },
    attributions: ["© OpenStreetMap contributors"],
  },
  satellite: {
    url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxZoom: 19,
    labels: { en: "Satellite", th: "ดาวเทียม" },
    attributions: ["Esri World Imagery", "Esri and imagery contributors"],
  },
  terrain: {
    url: "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
    maxZoom: 17,
    labels: { en: "Terrain", th: "ภูมิประเทศ" },
    attributions: ["© OpenStreetMap contributors", "SRTM", "© OpenTopoMap (CC-BY-SA)"],
  },
};

const PUBLIC_ACTION_CLASS_COLORS: Record<string, string> = {
  A: "#08519C",
  B: "#3182BD",
  C: "#6BAED6",
  D: "#BDD7E7",
  E: "#F59E0B",
};

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
  visualPalette = "default",
  enableBasemaps = false,
}: GeoMapProps) {
  const mapElement = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<LeafletModule | null>(null);
  const areaLayerRef = useRef<LeafletGeoJson | null>(null);
  const basemapLayerRef = useRef<LeafletTileLayer | null>(null);
  const contextLayerRef = useRef<LayerGroup | null>(null);
  const roadLayerRef = useRef<LayerGroup | null>(null);
  const facilityLayerRef = useRef<LayerGroup | null>(null);
  const accessLayerRef = useRef<LayerGroup | null>(null);
  const hasFitRegionalBounds = useRef(false);
  const previousSelectedId = useRef(selectedId);
  const selectionSheetId = useId();
  const [mapReady, setMapReady] = useState(false);
  const [basemapId, setBasemapId] = useState<BasemapId>("street");
  const [basemapState, setBasemapState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [selectionSheetOpen, setSelectionSheetOpen] = useState(true);
  const [visibleRoadCount, setVisibleRoadCount] = useState(0);
  const [facilityPresentation, setFacilityPresentation] = useState<"clusters" | "features">("clusters");
  const selectedArea = areas.find((area) => area.area_id === selectedId);
  const selectedScenarioResult = selectedArea?.scenario_results[scenarioId];
  const selectedPresentation = selectedArea
    ? scenarioMapPresentation(selectedArea.action_class, scenarioId, selectedScenarioResult)
    : undefined;
  const actionClassColors = visualPalette === "public-blue" ? PUBLIC_ACTION_CLASS_COLORS : ACTION_CLASS_COLORS;
  const visibleAttributions = enableBasemaps
    ? [...new Set([...BASEMAPS[basemapId].attributions, ...attributions])]
    : attributions;

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
      basemapLayerRef.current = null;
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
    if (!mapReady || !map || !L || !enableBasemaps) return;
    basemapLayerRef.current?.remove();
    setBasemapState("loading");
    const definition = BASEMAPS[basemapId];
    const layer = L.tileLayer(definition.url, {
      minZoom: 9,
      maxZoom: definition.maxZoom,
      maxNativeZoom: definition.maxZoom,
      crossOrigin: true,
      updateWhenIdle: true,
      keepBuffer: 2,
    });
    let disposed = false;
    let hadTileError = false;
    layer.on("tileload", () => {
      if (!disposed && !hadTileError) setBasemapState("ready");
    });
    layer.on("load", () => {
      if (!disposed && !hadTileError) setBasemapState("ready");
    });
    layer.on("tileerror", () => {
      hadTileError = true;
      if (!disposed) setBasemapState("unavailable");
    });
    layer.addTo(map);
    layer.bringToBack();
    basemapLayerRef.current = layer;
    return () => {
      disposed = true;
      layer.remove();
      if (basemapLayerRef.current === layer) basemapLayerRef.current = null;
    };
  }, [basemapId, enableBasemaps, mapReady]);

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
        actionClassColors,
        visualPalette === "public-blue",
        enableBasemaps,
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
            ? ` · การเปลี่ยนแปลงการเข้าถึงเชิงแบบจำลอง ${formatServerDelta(result.delta)}`
            : ` · modelled access change ${formatServerDelta(result.delta)}`;
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
  }, [actionClassColors, areaFeatures, areas, classFilter, enableBasemaps, language, mapReady, onSelect, scenarioId, selectedId, visualPalette]);

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
          bindTextTooltip(featureLayer, `${label} · ${datasetMode === "fixture_demo" ? "Saved planning context · verify locally" : "Geographic context"}`);
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
        const name = String(properties.road_name || properties.road_id || "road segment");
        const probability = Number(properties.road_disruption_probability_0_1 ?? 0);
        const warning = language === "th"
          ? "ความเสี่ยงเชิงแบบจำลอง · ไม่ใช่การปิดถนนที่สังเกตจริง"
          : "modelled planning risk · verify current road status locally";
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
    const group = L.layerGroup().addTo(map);
    setFacilityPresentation("features");
    for (const feature of facilityFeatures.features) {
      if (feature.geometry.type !== "Point") continue;
      const [longitude, latitude] = feature.geometry.coordinates as [number, number];
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
      const properties = feature.properties ?? {};
      const facilityType = facilityDisplayCategory(String(properties.facility_type ?? "community_facility"));
      const name = String(properties.facility_name || properties.facility_id || (language === "th" ? "สถานที่สำคัญ" : "Important facility"));
      const typeLabel = facilityTypeLabel(facilityType, language);
      const marker = L.marker([latitude, longitude], {
        icon: L.divIcon({
          className: `facility-type-marker facility-${facilityType}`,
          html: facilityIconMarkup(facilityType),
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        }),
        keyboard: true,
        title: `${name} · ${typeLabel}`,
        zIndexOffset: String(properties.area_id ?? "") === selectedId ? 600 : 300,
      }).addTo(group);
      const verification = language === "th"
        ? "ตรวจสอบสถานะปัจจุบันกับหน่วยงานท้องถิ่น"
        : "verify current status with local authorities";
      bindTextTooltip(marker, `${name} · ${typeLabel} · ${verification}`, { sticky: true });
    }
    facilityLayerRef.current = group;
  }, [facilityFeatures, language, selectedId, showFacilities]);

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
      className={`geo-map-shell ${visibleAttributions.length > 0 ? "has-attribution" : ""}`}
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
      data-basemap={enableBasemaps ? basemapId : "none"}
      data-basemap-state={enableBasemaps ? basemapState : "disabled"}
    >
      <div
        className="geo-map"
        ref={mapElement}
        style={{ height }}
        role="region"
        aria-label={mapProvenanceLabel(language, datasetMode)}
      />
      {enableBasemaps && (
        <div className="map-basemap-switcher" role="group" aria-label={language === "th" ? "เลือกพื้นหลังแผนที่" : "Choose map background"}>
          {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => (
            <button
              key={id}
              type="button"
              aria-pressed={basemapId === id}
              className={basemapId === id ? "active" : ""}
              onClick={() => setBasemapId(id)}
            >
              {BASEMAPS[id].labels[language]}
            </button>
          ))}
        </div>
      )}
      {enableBasemaps && basemapState === "unavailable" && (
        <p className="map-basemap-notice" role="status">
          {language === "th"
            ? "พื้นหลังแผนที่ไม่พร้อมใช้งานชั่วคราว แต่ขอบเขตและข้อมูลการวางแผนยังแสดงอยู่"
            : "The map background is temporarily unavailable; planning boundaries and evidence remain visible."}
        </p>
      )}
      {(roadDetailState === "loading" || roadDetailState === "unavailable") && (
        <p className={`map-detail-notice ${roadDetailState}`} role="status" aria-live="polite">
          {roadDetailState === "loading"
            ? (language === "th" ? "กำลังโหลดรายละเอียดถนนของพื้นที่ที่เลือก โดยยังแสดงภาพรวมถนนระดับภูมิภาค" : "Loading selected-area road detail; the regional road overview remains visible.")
            : (language === "th" ? "รายละเอียดถนนของพื้นที่ที่เลือกไม่พร้อมใช้งาน ขณะนี้แสดงภาพรวมถนนระดับภูมิภาค" : "Selected-area road detail is unavailable; showing the regional road overview.")}
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
              {scenarioId !== "baseline" && selectedScenarioResult && <div><dt>{language === "th" ? "การเปลี่ยนแปลงการเข้าถึง" : "Scenario access change"}</dt><dd className={`scenario-${selectedPresentation?.tone ?? "unavailable"}`}>{formatServerDelta(selectedScenarioResult.delta)}</dd></div>}
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
          {Object.entries(actionClassColors).map(([key, color]) => {
            const label = ACTION_CLASS_LABELS[key as keyof typeof ACTION_CLASS_LABELS];
            return <span key={key}><i style={{ backgroundColor: color }} /><b>{key}</b><small>{label[language]}</small></span>;
          })}
        </div>
        {showRoads && <span><i className="road-swatch" />{language === "th" ? `ความเสี่ยงถนนเชิงแบบจำลอง · แสดง ${visibleRoadCount.toLocaleString()}` : `Modelled road risk · ${visibleRoadCount.toLocaleString()} shown`}</span>}
        {showFacilities && facilityFeatures.features.length > 0 && (
          <span className="facility-type-legend">
            {(Object.keys(FACILITY_LABELS) as FacilityCategory[]).map((type) => (
              <span key={type}><i className={`facility-symbol facility-${type}`} aria-hidden="true" />{facilityTypeLabel(type, language)}</span>
            ))}
          </span>
        )}
        {showAccess && accessFeatures.features.length > 0 && <span><i className="access-swatch" />{language === "th" ? "หลักฐานการเข้าถึงเชิงแบบจำลอง" : "Modelled access evidence"}</span>}
        {contextFeatures.features.length > 0 && <span><i className="context-swatch" />{language === "th" ? "บริบทภูมิศาสตร์" : "Geographic context"}</span>}
      </div>
      {visibleAttributions.length > 0 && (
        <p className="map-attribution" aria-label={language === "th" ? "แหล่งที่มาของข้อมูลแผนที่" : "Map data attribution"}>
          <strong>{language === "th" ? "แหล่งข้อมูล:" : "Data attribution:"}</strong>{" "}
          {visibleAttributions.map((attribution, index) => (
            <span key={attribution}>
              {index > 0 && " · "}
              {attributionLink(attribution)
                ? <a href={attributionLink(attribution)} target="_blank" rel="license noopener noreferrer">{displayAttribution(attribution)}</a>
                : displayAttribution(attribution)}
            </span>
          ))}
        </p>
      )}
      <span className={`map-provenance-badge ${datasetMode}`}>{mapGeometryDisclosure(language, datasetMode)}</span>
      <details className="map-text-alternative">
        <summary>{language === "th" ? "ข้อความทดแทนแผนที่" : "Map text alternative"}</summary>
        <p>{mapProvenanceLabel(language, datasetMode)}</p>
        <p>{language === "th"
          ? `${areaFeatures.features.length} พื้นที่ · ${roadFeatures.features.length.toLocaleString()} ช่วงถนน · ${facilityFeatures.features.length} สถานที่สำคัญ · ${accessFeatures.features.length} จุดหลักฐานการเข้าถึง`
          : `${areaFeatures.features.length} areas · ${roadFeatures.features.length.toLocaleString()} road segments · ${facilityFeatures.features.length} important facilities · ${accessFeatures.features.length} access-evidence points`}</p>
        {datasetMode === "candidate" && <p className="map-candidate-warning">{language === "th" ? "ยืนยันสถานที่ การเปิดใช้งาน และสภาพถนนล่าสุดกับหน่วยงานท้องถิ่นก่อนดำเนินการ" : "Confirm facilities, operating status, and current road conditions with local authorities before acting."}</p>}
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

function areaStyle(
  areaId: string,
  actionClass: string,
  selectedId: string,
  scenarioId: ScenarioId,
  areas: AreaRecord[],
  actionClassColors: Record<string, string> = ACTION_CLASS_COLORS,
  usePaletteColors = false,
  hasBasemap = false,
): import("leaflet").PathOptions {
  const area = areas.find((item) => item.area_id === areaId);
  const presentation = scenarioMapPresentation(actionClass, scenarioId, area?.scenario_results[scenarioId]);
  const publicClassColor = actionClassColors[actionClass] ?? actionClassColors.E;
  const fillColor = usePaletteColors && scenarioId === "baseline" ? publicClassColor : presentation.fillColor;
  return {
    color: areaId === selectedId
      ? usePaletteColors ? "#0C2740" : "#052e3b"
      : usePaletteColors && scenarioId === "baseline" ? publicClassColor : presentation.outlineColor,
    weight: areaId === selectedId ? 4 : scenarioId === "baseline" ? 2 : 3,
    fillColor,
    fillOpacity: hasBasemap
      ? areaId === selectedId ? 0.38 : scenarioId === "baseline" ? 0.18 : 0.28
      : areaId === selectedId ? 0.82 : scenarioId === "baseline" ? 0.5 : 0.64,
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

export type FacilityCategory = "healthcare" | "school" | "emergency" | "shelter" | "community";

const FACILITY_LABELS: Record<FacilityCategory, Record<Language, string>> = {
  healthcare: { en: "Health", th: "สุขภาพ" },
  school: { en: "School", th: "โรงเรียน" },
  emergency: { en: "Emergency service", th: "บริการฉุกเฉิน" },
  shelter: { en: "Shelter location", th: "จุดพักพิง" },
  community: { en: "Community", th: "ชุมชน" },
};

export function facilityDisplayCategory(value: string): FacilityCategory {
  if (value === "healthcare") return "healthcare";
  if (value === "school") return "school";
  if (value === "emergency_service") return "emergency";
  if (value === "shelter_candidate") return "shelter";
  return "community";
}

function facilityTypeLabel(type: FacilityCategory, language: Language): string {
  return FACILITY_LABELS[type][language];
}

export function facilityIconMarkup(type: FacilityCategory): string {
  const paths: Record<FacilityCategory, string> = {
    healthcare: '<path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z"/>',
    school: '<path d="m3 9 9-5 9 5-9 5zM6 12v6h12v-6M9 18v-4h6v4"/>',
    emergency: '<path d="M12 3l7 3v5c0 5-2.8 8.3-7 10-4.2-1.7-7-5-7-10V6zM12 7v8M8 11h8"/>',
    shelter: '<path d="m4 11 8-7 8 7v9h-6v-6h-4v6H4z"/>',
    community: '<path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3 20v-3c0-2.2 2.2-4 5-4s5 1.8 5 4v3M13 14c.8-.6 1.8-1 3-1 2.8 0 5 1.8 5 4v3h-5"/>',
  };
  return `<span aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false">${paths[type]}</svg></span>`;
}

function attributionLink(attribution: string): string | undefined {
  if (attribution === "© OpenStreetMap contributors") return "https://www.openstreetmap.org/copyright";
  if (attribution === "Esri World Imagery") return "https://www.arcgis.com/home/item.html?id=b4d457217e6641d682cab85f26db7bd0";
  if (attribution === "© OpenTopoMap (CC-BY-SA)") return "https://wiki.opentopomap.org/about";
  return undefined;
}

export function displayAttribution(attribution: string): string {
  return attribution
    .replace(/\bcandidate\b/gi, "planning")
    .replace(/\bfixture\b/gi, "reference")
    .replace(/\bsynthetic\b/gi, "modelled");
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
  if (datasetMode === "fixture_demo") return language === "th" ? "ขอบเขตพื้นที่วางแผน" : "Planning-area boundary";
  if (datasetMode === "candidate") return language === "th" ? "ขอบเขตพื้นที่แม่สาย · ตรวจสอบกับท้องถิ่น" : "Mae Sai planning boundary · verify locally";
  return language === "th" ? "เรขาคณิตจากข้อมูลนำเข้าทางการ" : "Official-input geometry";
}

function mapProvenanceLabel(language: Language, datasetMode: DatasetMode): string {
  if (datasetMode === "fixture_demo") return language === "th" ? "แผนที่พื้นที่วางแผนจากข้อมูลที่จัดเก็บในอุปกรณ์" : "Planning-area map from device-stored GeoJSON";
  if (datasetMode === "candidate") return language === "th" ? "แผนที่แม่สายจากข้อมูลเปิดที่ติดตามแหล่งที่มา โปรดยืนยันสถานที่และสภาพถนนกับหน่วยงานท้องถิ่น" : "Mae Sai planning map from provenance-tracked open data; verify facilities and road conditions locally";
  return language === "th" ? "แผนที่จากข้อมูลนำเข้าทางการ" : "Map from official-input GeoJSON";
}
