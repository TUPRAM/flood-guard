"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import type { PublicPreparednessArea } from "@floodguard/contracts";

import { GeoMap } from "@/components/geo-map";
import { PublicAppIcon } from "@/components/public-app-icon";
import { formatConfidence, formatSourceTime } from "@/lib/format";
import {
  derivePublicHazardSignals,
  hazardSignalLabel,
  hazardSignalSummary,
} from "@/lib/public-hazard-signals";
import {
  findAreaIdForPoint,
  PUBLIC_GEOCODER_ATTRIBUTION_URL,
  searchPublicAddresses,
  type PublicAddressSuggestion,
  type PublicMapLocation,
} from "@/lib/public-location";
import type { FeatureCollection, Language, PublicFloodGuardData } from "@/lib/types";

interface PublicHomePageProps {
  language: Language;
  data: PublicFloodGuardData;
  selectedAreaId: string;
  onSelectArea: (areaId: string) => void;
  location?: PublicMapLocation;
  onLocationChange: (location: PublicMapLocation) => void;
}

const EMPTY_ROADS: FeatureCollection = {
  type: "FeatureCollection",
  name: "public_home_roads_withheld",
  features: [],
};
const EMPTY_FACILITIES: FeatureCollection = {
  type: "FeatureCollection",
  name: "public_home_facilities_withheld",
  features: [],
};
const EMPTY_ACCESS: FeatureCollection = {
  type: "FeatureCollection",
  name: "public_home_access_withheld",
  features: [],
};
const EMPTY_CONTEXT: FeatureCollection = {
  type: "FeatureCollection",
  name: "public_home_context_withheld",
  features: [],
};

type SearchState = "idle" | "loading" | "ready" | "empty" | "unavailable";
type GpsState = "idle" | "requesting" | "ready" | "denied" | "unavailable" | "timeout";

function recommendationLabel(
  area: PublicPreparednessArea,
  language: Language,
): string {
  const labels = {
    low_confidence: {
      en: "Check current conditions with DDPM and local authorities before acting.",
      th: "ตรวจสอบสภาพปัจจุบันกับ ปภ. และหน่วยงานท้องถิ่นก่อนดำเนินการ",
    },
    low_priority_score: {
      en: "Keep official updates and your household plan under review.",
      th: "ติดตามประกาศทางการและทบทวนแผนครัวเรือน",
    },
    life_safety_exposure: {
      en: "Prioritize local checks for life-safety needs.",
      th: "ให้ความสำคัญกับการตรวจสอบความต้องการด้านความปลอดภัยของชีวิต",
    },
    critical_route_access: {
      en: "Confirm important routes and alternatives with local authorities.",
      th: "ยืนยันเส้นทางสำคัญและทางเลือกกับหน่วยงานท้องถิ่น",
    },
    essential_service_access: {
      en: "Confirm access to essential services and local backup plans.",
      th: "ยืนยันการเข้าถึงบริการจำเป็นและแผนสำรองในพื้นที่",
    },
    resilience: {
      en: "Review longer-term preparedness and resilience actions.",
      th: "ทบทวนการเตรียมพร้อมและการเสริมความยืดหยุ่นระยะยาว",
    },
  } as const;
  return labels[area.recommendation_code][language];
}

type PriorityBand = "very_high" | "high" | "moderate" | "lower";

function priorityBandCode(value: number): PriorityBand {
  if (value >= 75) return "very_high";
  if (value >= 50) return "high";
  if (value >= 25) return "moderate";
  return "lower";
}

function priorityBand(value: number, language: Language): string {
  const labels: Record<PriorityBand, Record<Language, string>> = {
    very_high: { en: "Very high", th: "สูงมาก" },
    high: { en: "High", th: "สูง" },
    moderate: { en: "Moderate", th: "ปานกลาง" },
    lower: { en: "Lower", th: "ต่ำกว่า" },
  };
  return labels[priorityBandCode(value)][language];
}

/** Highest-priority area, used to frame Home before the reader picks one. */
function highestPriorityAreaId(areas: PublicPreparednessArea[]): string {
  let best: PublicPreparednessArea | undefined;
  for (const area of areas) {
    if (!best || area.planning_priority_0_100 > best.planning_priority_0_100) {
      best = area;
    }
  }
  return best?.area_id ?? "";
}

function localAreaMatch(
  areas: PublicPreparednessArea[],
  query: string,
): PublicPreparednessArea | undefined {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return undefined;
  return areas.find((area) => (
    area.area_id.toLocaleLowerCase() === normalized
    || area.area_name_en.toLocaleLowerCase() === normalized
    || area.area_name_th.toLocaleLowerCase() === normalized
  ));
}

export function PublicHomePage({
  language,
  data,
  selectedAreaId,
  onSelectArea,
  location,
  onLocationChange,
}: PublicHomePageProps) {
  const th = language === "th";
  const [searchDraft, setSearchDraft] = useState(
    location?.source === "address" ? location.label : "",
  );
  const [searchEditing, setSearchEditing] = useState(false);
  const [searchMessage, setSearchMessage] = useState("");
  const [searchState, setSearchState] = useState<SearchState>("idle");
  const [suggestions, setSuggestions] = useState<PublicAddressSuggestion[]>([]);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [gpsState, setGpsState] = useState<GpsState>(
    location?.source === "gps" ? "ready" : "idle",
  );
  const [hazardOpen, setHazardOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchAbortRef = useRef<AbortController | null>(null);
  const locationAttemptRef = useRef(0);
  const hazardButtonRef = useRef<HTMLButtonElement>(null);
  const hazardCloseRef = useRef<HTMLButtonElement>(null);
  const hazardPanelRef = useRef<HTMLElement>(null);
  // Home frames the highest-priority area until the reader picks one. Keeping it
  // local means opening the app never writes a planning area into the saved
  // household plan — that stays an explicit choice.
  const focusAreaId = selectedAreaId || highestPriorityAreaId(data.publicAreas);
  const selectedArea = data.publicAreas.find((area) => area.area_id === focusAreaId);

  const focusAddressInput = useCallback(() => {
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);

  const applyLocation = useCallback((nextLocation: PublicMapLocation) => {
    const areaId = findAreaIdForPoint(
      data.areaFeatures,
      nextLocation.longitude,
      nextLocation.latitude,
    );
    onLocationChange(nextLocation);
    if (areaId) onSelectArea(areaId);
    return areaId;
  }, [data.areaFeatures, onLocationChange, onSelectArea]);

  const requestPreciseLocation = useCallback(() => {
    const geolocation = navigator.geolocation;
    if (!geolocation) {
      setGpsState("unavailable");
      setSearchMessage(th
        ? "อุปกรณ์นี้ไม่รองรับตำแหน่ง GPS โปรดค้นหาที่อยู่แทน"
        : "This device does not provide GPS location. Search for an address instead.");
      focusAddressInput();
      return;
    }

    const attempt = locationAttemptRef.current + 1;
    locationAttemptRef.current = attempt;
    setGpsState("requesting");
    setSearchMessage(th
      ? "กำลังขอตำแหน่งที่แม่นยำจากอุปกรณ์…"
      : "Requesting a high-accuracy position from this device…");

    geolocation.getCurrentPosition(
      (position) => {
        if (attempt !== locationAttemptRef.current) return;
        const latitude = Number(position.coords.latitude);
        const longitude = Number(position.coords.longitude);
        const accuracy = Number(position.coords.accuracy);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
          setGpsState("unavailable");
              setSearchMessage(th
            ? "ตำแหน่งที่ได้รับไม่ถูกต้อง โปรดค้นหาที่อยู่แทน"
            : "The returned position was invalid. Search for an address instead.");
          focusAddressInput();
          return;
        }

        const roundedAccuracy = Number.isFinite(accuracy) && accuracy > 0
          ? Math.round(accuracy)
          : undefined;
        const label = th ? "ตำแหน่งที่แม่นยำของคุณ" : "Your precise location";
        const areaId = applyLocation({
          latitude,
          longitude,
          accuracyMeters: roundedAccuracy,
          label,
          source: "gps",
        });
        setGpsState("ready");
        setSearchDraft("");
        setSearchEditing(false);
        setSuggestions([]);
        setActiveSuggestionIndex(-1);
          setSearchMessage([
          th ? "วางหมุดที่ตำแหน่งอุปกรณ์แล้ว" : "Pin placed at the device position.",
          roundedAccuracy
            ? (th ? `ความแม่นยำประมาณ ±${roundedAccuracy} ม.` : `Reported accuracy ±${roundedAccuracy} m.`)
            : "",
          areaId
            ? ""
            : (th ? "ตำแหน่งอยู่นอกขอบเขตข้อมูลการวางแผน" : "The point is outside the planning-data coverage."),
        ].filter(Boolean).join(" "));
      },
      (error) => {
        if (attempt !== locationAttemptRef.current) return;
          if (error.code === 1) {
          setGpsState("denied");
          setSearchMessage(th
            ? "ไม่ได้รับอนุญาตให้ใช้ตำแหน่ง โปรดพิมพ์ที่อยู่แทน"
            : "Location permission was not granted. Enter an address instead.");
        } else if (error.code === 3) {
          setGpsState("timeout");
          setSearchMessage(th
            ? "การค้นหา GPS ใช้เวลานานเกินไป โปรดพิมพ์ที่อยู่หรือลองใหม่"
            : "GPS took too long. Enter an address or try precise location again.");
        } else {
          setGpsState("unavailable");
          setSearchMessage(th
            ? "ไม่สามารถรับตำแหน่ง GPS ได้ โปรดพิมพ์ที่อยู่แทน"
            : "GPS position is unavailable. Enter an address instead.");
        }
        focusAddressInput();
      },
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 15_000,
      },
    );
  }, [applyLocation, focusAddressInput, th]);

  const runAddressSearch = useCallback(async (query: string) => {
    const normalized = query.trim();
    if (normalized.length < 4) {
      setSearchState("idle");
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      setSearchMessage(th
        ? "พิมพ์บ้านเลขที่และชื่อถนนอย่างน้อย 4 ตัวอักษร"
        : "Enter at least four characters, including a street number when available.");
      return;
    }

    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;
    setSearchState("loading");
    setSearchMessage(th ? "กำลังค้นหาที่อยู่…" : "Looking for address matches…");
    try {
      const nextSuggestions = await searchPublicAddresses(
        normalized,
        language,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setSuggestions(nextSuggestions);
      setActiveSuggestionIndex(nextSuggestions.length > 0 ? 0 : -1);
      setSearchState(nextSuggestions.length > 0 ? "ready" : "empty");
      setSearchMessage(nextSuggestions.length > 0
        ? (th ? "เลือกที่อยู่ที่ตรงกันเพื่อวางหมุด" : "Choose the matching address to place the pin.")
        : (th ? "ไม่พบที่อยู่ โปรดเพิ่มบ้านเลขที่ ถนน ตำบล หรือรหัสไปรษณีย์" : "No address matched. Add a street number, road, district, or postcode."));
    } catch (error) {
      if (controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) {
        return;
      }
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      setSearchState("unavailable");
      setSearchMessage(th
        ? "การค้นหาที่อยู่ออนไลน์ไม่พร้อมใช้งาน คุณยังสามารถลอง GPS หรือค้นหาอีกครั้งเมื่อออนไลน์"
        : "Online address search is unavailable. You can still try GPS or search again when online.");
    }
  }, [language, th]);

  useEffect(() => {
    if (
      !searchEditing
      || searchDraft.trim().length < 4
      || localAreaMatch(data.publicAreas, searchDraft)
    ) {
      return;
    }
    const timer = window.setTimeout(() => {
      void runAddressSearch(searchDraft);
    }, 700);
    return () => window.clearTimeout(timer);
  }, [data.publicAreas, runAddressSearch, searchDraft, searchEditing]);

  useEffect(() => () => searchAbortRef.current?.abort(), []);

  useEffect(() => {
    if (!hazardOpen) return;
    hazardCloseRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHazardOpen(false);
        hazardButtonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !hazardPanelRef.current) return;
      const focusable = [...hazardPanelRef.current.querySelectorAll<HTMLElement>(
        "button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
      )].filter((element) => !element.hasAttribute("disabled"));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [hazardOpen]);

  const chooseSuggestion = (suggestion: PublicAddressSuggestion) => {
    locationAttemptRef.current += 1;
    searchAbortRef.current?.abort();
    const areaId = applyLocation({
      latitude: suggestion.latitude,
      longitude: suggestion.longitude,
      label: suggestion.label,
      source: "address",
    });
    setGpsState("idle");
    setSearchDraft(suggestion.label);
    setSearchEditing(false);
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
    setSearchState("idle");
    setSearchMessage([
      th ? "วางหมุดที่ตำแหน่งที่เลือกแล้ว" : "Pin placed at the selected address.",
      suggestion.hasStreetNumber
        ? ""
        : (th ? "ผลลัพธ์นี้เป็นระดับถนนหรือพื้นที่ โปรดเพิ่มบ้านเลขที่เพื่อความละเอียดมากขึ้น" : "This is a street or area match; add a street number for a more precise result."),
      areaId
        ? ""
        : (th ? "ตำแหน่งอยู่นอกขอบเขตข้อมูลการวางแผน" : "The point is outside the planning-data coverage."),
    ].filter(Boolean).join(" "));
  };

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchDraft.trim();
    const areaMatch = localAreaMatch(data.publicAreas, query);
    if (areaMatch) {
      onSelectArea(areaMatch.area_id);
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      setSearchState("idle");
      setSearchMessage(th
        ? `เลือก ${areaMatch.area_name_th} แล้ว โปรดเพิ่มบ้านเลขที่และถนนเพื่อวางหมุดให้แม่นยำ`
        : `${areaMatch.area_name_en} selected. Add a street number and road for an exact pin.`);
      return;
    }
    if (activeSuggestionIndex >= 0 && suggestions[activeSuggestionIndex]) {
      chooseSuggestion(suggestions[activeSuggestionIndex]);
      return;
    }
    void runAddressSearch(query);
  };

  const onSearchKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (suggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((index) => (
        index <= 0 ? suggestions.length - 1 : index - 1
      ));
    } else if (event.key === "Escape") {
      event.preventDefault();
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      setSearchState("idle");
    } else if (
      event.key === "Enter"
      && activeSuggestionIndex >= 0
      && suggestions[activeSuggestionIndex]
    ) {
      event.preventDefault();
      chooseSuggestion(suggestions[activeSuggestionIndex]);
    }
  };

  const priorityValue = selectedArea?.planning_priority_0_100 ?? 0;
  const hazardSignals = derivePublicHazardSignals(selectedArea);
  const locationProblem = gpsState === "denied"
    || gpsState === "unavailable"
    || gpsState === "timeout"
    || searchState === "empty"
    || searchState === "unavailable";
  const showLocationCard = suggestions.length === 0
    && Boolean(location || locationProblem);

  return (
    <section className="public-home-page" aria-label={th ? "แผนที่หน้าแรก" : "Home map"}>
      <div className="public-home-map">
        <GeoMap
          areas={data.publicAreas}
          selectedId={focusAreaId}
          onSelect={onSelectArea}
          language={language}
          showRoads={false}
          showFacilities={false}
          showAccess={false}
          height="100%"
          areaFeatures={data.areaFeatures}
          roadFeatures={EMPTY_ROADS}
          facilityFeatures={EMPTY_FACILITIES}
          accessFeatures={EMPTY_ACCESS}
          contextFeatures={EMPTY_CONTEXT}
          datasetMode={data.status.dataset_mode}
          showSelectionSheet={false}
          attributions={[]}
          visualPalette="public-risk"
          enableBasemaps
          basemapControlVariant="menu"
          showLegend={false}
          showProvenanceBadge={false}
          showTextAlternative={false}
          showDataAttribution={false}
          audience="public"
          location={location}
          initialFocus="selection"
          selectionPinTitle={selectedArea
            ? (th ? selectedArea.area_name_th : selectedArea.area_name_en)
            : undefined}
        />

        <div className="public-map-rail">
        <div className="public-map-search-field">
        <form className="public-map-search" role="search" onSubmit={submitSearch}>
          <PublicAppIcon name="search" />
          <label className="sr-only" htmlFor="public-area-search">
            {th ? "ค้นหาที่อยู่แบบละเอียด" : "Search for an exact address"}
          </label>
          <input
            ref={searchInputRef}
            id="public-area-search"
            value={searchDraft}
            placeholder={th ? "บ้านเลขที่ ถนน ตำบล แม่สาย" : "Street number, road, Mae Sai"}
            autoComplete="street-address"
            role="combobox"
            aria-autocomplete="list"
            aria-controls="public-address-suggestions"
            aria-expanded={suggestions.length > 0}
            aria-activedescendant={
              activeSuggestionIndex >= 0
                ? `public-address-option-${activeSuggestionIndex}`
                : undefined
            }
            aria-describedby="public-location-search-status"
            onChange={(event) => {
              const value = event.target.value;
              searchAbortRef.current?.abort();
              setSearchDraft(value);
              setSearchEditing(true);
              setSuggestions([]);
              setActiveSuggestionIndex(-1);
              setSearchState("idle");
              setSearchMessage("");
            }}
            onKeyDown={onSearchKeyDown}
          />
          <button type="submit" disabled={searchState === "loading"}>
            {searchState === "loading"
              ? (th ? "กำลังค้นหา" : "Finding")
              : (th ? "ค้นหา" : "Search")}
          </button>
        </form>

        {suggestions.length > 0 && (
          <div
            id="public-address-suggestions"
            className="public-address-suggestions"
            role="listbox"
            aria-label={th ? "ที่อยู่ที่แนะนำ" : "Suggested addresses"}
          >
            {suggestions.map((suggestion, index) => (
              <button
                key={suggestion.id}
                id={`public-address-option-${index}`}
                type="button"
                role="option"
                aria-selected={activeSuggestionIndex === index}
                onMouseEnter={() => setActiveSuggestionIndex(index)}
                onClick={() => chooseSuggestion(suggestion)}
              >
                <strong>{suggestion.label}</strong>
                <small>
                  {suggestion.hasStreetNumber
                    ? (th ? "ตรงกับบ้านเลขที่" : "Street-number match")
                    : (th ? "ตรงกับถนนหรือพื้นที่" : "Street or area match")}
                </small>
              </button>
            ))}
            <a
              href={PUBLIC_GEOCODER_ATTRIBUTION_URL}
              target="_blank"
              rel="license noopener noreferrer"
            >
              {th ? "คำแนะนำที่อยู่โดย Esri" : "Address suggestions by Esri"}
            </a>
          </div>
        )}
        </div>

        {/*
          The card appears for a resolved location or a real problem only. A
          plain "type an address" instruction repeats the input placeholder, so
          it stays in the live region below instead of taking a slab of map.
        */}
        {!showLocationCard && (
          <p
            id="public-location-search-status"
            className="sr-only"
            role="status"
            aria-live="polite"
          >
            {searchMessage}
          </p>
        )}

        {showLocationCard && (
          <div
            id="public-location-search-status"
            className={`public-location-status state-${searchState}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong>
                {location
                  ? location.label
                  : (th ? "ค้นหาตำแหน่ง" : "Location search")}
              </strong>
              <small>
                {location?.source === "gps" && location.accuracyMeters
                  ? (th ? `GPS ±${location.accuracyMeters} ม. · ไม่บันทึก` : `GPS ±${location.accuracyMeters} m · not saved`)
                  : location?.source === "address"
                    ? (th ? "ตำแหน่งที่เลือก · ไม่บันทึก" : "Selected address · not saved")
                    : searchMessage}
              </small>
            </span>
            {gpsState !== "requesting" && location?.source !== "gps" && (
              <button type="button" onClick={requestPreciseLocation}>
                {th ? "ใช้ GPS" : "Use GPS"}
              </button>
            )}
          </div>
        )}

        {hazardSignals.length > 0 && (
          <button
            type="button"
            className="public-signal-banner"
            aria-controls="public-hazard-panel"
            aria-expanded={hazardOpen}
            onClick={() => setHazardOpen(true)}
          >
            <PublicAppIcon name="hazard" />
            <span>{hazardSignalSummary(hazardSignals.length, language)}</span>
            <PublicAppIcon name="chevron" />
          </button>
        )}
        </div>

        <div className="public-map-dock">
          <aside
            className="public-risk-indicator"
            aria-label={th ? "ตัวชี้วัดการวางแผนน้ำท่วม" : "Flood planning indicator"}
          >
            <div className="public-risk-headline">
              <strong>
                {selectedArea
                  ? (th ? selectedArea.area_name_th : selectedArea.area_name_en)
                  : (th ? "ยังไม่พบพื้นที่วางแผน" : "No planning area matched")}
              </strong>
              {selectedArea && (
                <span
                  className="public-risk-chip"
                  data-band={priorityBandCode(priorityValue)}
                >
                  {priorityBand(priorityValue, language)}
                </span>
              )}
            </div>
            <div className="public-risk-scale">
              {selectedArea && (
                <i
                  style={{ left: `${Math.max(0, Math.min(100, priorityValue))}%` }}
                  aria-hidden="true"
                />
              )}
            </div>
            <div className="public-risk-scale-labels">
              <span>{th ? "ความเสี่ยงต่ำ" : "Low risk"}</span>
              <span>{th ? "ความเสี่ยงสูง" : "High risk"}</span>
            </div>
          </aside>

          <button
            ref={hazardButtonRef}
            type="button"
            className="public-hazard-button"
            aria-expanded={hazardOpen}
            aria-controls="public-hazard-panel"
            onClick={() => setHazardOpen(true)}
          >
            <PublicAppIcon name="hazard" />
            <span>{th ? "ข้อมูลอันตราย" : "Hazard Info"}</span>
          </button>
        </div>

        {/*
          Sits with zoom and layers in the map-tool column. GPS is only ever
          requested from here, so opening the app never reaches for the device
          position on its own.
        */}
        <button
          type="button"
          className="public-locate-button"
          aria-label={gpsState === "requesting"
            ? (th ? "กำลังขอตำแหน่ง" : "Requesting location")
            : (th ? "ใช้ตำแหน่งของฉัน" : "Use my location")}
          aria-busy={gpsState === "requesting"}
          disabled={gpsState === "requesting"}
          onClick={requestPreciseLocation}
        >
          <PublicAppIcon name="locate" />
        </button>

        {hazardOpen && (
          <div
            className="public-hazard-overlay"
            role="presentation"
            onMouseDown={(event) => {
              if (event.currentTarget !== event.target) return;
              setHazardOpen(false);
              hazardButtonRef.current?.focus();
            }}
          >
            <aside
              ref={hazardPanelRef}
              id="public-hazard-panel"
              className="public-hazard-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby="public-hazard-title"
            >
              <div className="public-hazard-panel-heading">
                <div>
                  <p>{th ? "ข้อมูลเพื่อการวางแผน" : "PLANNING INFORMATION"}</p>
                  <h2 id="public-hazard-title">
                    {selectedArea
                      ? (th ? selectedArea.area_name_th : selectedArea.area_name_en)
                      : (th ? "ยังไม่พบพื้นที่วางแผน" : "No planning area matched")}
                  </h2>
                </div>
                <button
                  ref={hazardCloseRef}
                  type="button"
                  className="public-icon-button"
                  aria-label={th ? "ปิดข้อมูลอันตราย" : "Close hazard information"}
                  onClick={() => {
                    setHazardOpen(false);
                    hazardButtonRef.current?.focus();
                  }}
                >
                  <PublicAppIcon name="close" />
                </button>
              </div>

              {selectedArea ? (
                <>
                  <dl className="public-hazard-facts">
                    <div>
                      <dt>{th ? "ตัวชี้วัดการวางแผน" : "Planning indicator"}</dt>
                      <dd>{priorityBand(priorityValue, language)} · {priorityValue.toFixed(1)}/100</dd>
                    </div>
                    <div>
                      <dt>{th ? "ความเพียงพอของหลักฐาน" : "Evidence sufficiency"}</dt>
                      <dd>{formatConfidence(selectedArea.evidence_sufficiency, language)}</dd>
                    </div>
                    <div>
                      <dt>{th ? "เวลาของแหล่งข้อมูล" : "Source time"}</dt>
                      <dd>{formatSourceTime(selectedArea.source_timestamp, language)} ICT</dd>
                    </div>
                  </dl>
                  {hazardSignals.length > 0 && (
                    <ul className="public-hazard-signals">
                      {hazardSignals.map((signal) => (
                        <li key={signal.code}>
                          <PublicAppIcon name="hazard" />
                          <span>{hazardSignalLabel(signal, language)}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  <div className="public-hazard-guidance">
                    <PublicAppIcon name="hazard" />
                    <p>{recommendationLabel(selectedArea, language)}</p>
                  </div>
                  <p className="public-hazard-boundary">
                    {th
                      ? "ตัวชี้วัดนี้ใช้ข้อมูลอุทกภัยในอดีตเพื่อการเตรียมพร้อม ไม่ได้ยืนยันระดับน้ำหรืออันตรายในปัจจุบัน"
                      : "This indicator uses historical flood evidence for preparedness. It does not confirm current water levels or hazards."}
                  </p>
                </>
              ) : (
                <p className="public-hazard-empty">
                  {th
                    ? "ใช้ GPS หรือเลือกที่อยู่เพื่อเชื่อมหมุดกับข้อมูลพื้นที่วางแผนที่มีอยู่"
                    : "Use GPS or choose an address to match the pin with available planning-area information."}
                </p>
              )}

              <a
                className="public-hazard-official-link"
                href="https://www.disaster.go.th/home"
                target="_blank"
                rel="noreferrer"
              >
                {th ? "ตรวจสอบประกาศปัจจุบันจาก ปภ." : "Check current DDPM updates"}
                <span aria-hidden="true">↗</span>
              </a>
            </aside>
          </div>
        )}
      </div>
    </section>
  );
}
