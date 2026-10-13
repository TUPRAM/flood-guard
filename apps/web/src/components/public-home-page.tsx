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
  findAreaIdForPoint,
  PUBLIC_GEOCODER_ATTRIBUTION_URL,
  searchPublicAddresses,
  type PublicAddressSuggestion,
  type PublicMapLocation,
} from "@/lib/public-location";
import { PRACTICE_MENU_COPY, type PracticeState, type PracticeTone } from "@/lib/public-practice-scenarios";
import type { FeatureCollection, Language, PublicFloodGuardData } from "@/lib/types";
import { usePublicPractice } from "@/lib/use-public-practice";
import { useSheetKeyboard } from "@/lib/use-sheet-keyboard";

interface PublicHomePageProps {
  language: Language;
  data: PublicFloodGuardData;
  selectedAreaId: string;
  onSelectArea: (areaId: string) => void;
  location?: PublicMapLocation;
  onLocationChange: (location: PublicMapLocation | undefined) => void;
  researchHref?: string;
  /** The practice scenario chosen in the header; null or absent on a day without practice. */
  practiceScenarioId?: PracticeState | null;
  /** Called when the reader looks for their own place: that ends the practice. */
  onPracticeEnd?: () => void;
  onNavigatePrepare?: () => void;
  onNavigateSos?: () => void;
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
/** A tap on the map chooses no planning area while a practice scenario is shown. */
const ignoreAreaSelection = () => {};
/** The practice replay draws road pieces from OpenStreetMap on every background, so its credit joins the map's. */
const PRACTICE_CREDITS = ["© OpenStreetMap contributors"];
const NO_EXTRA_CREDITS: string[] = [];

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

/**
 * What Home says on a day without practice. The app has no feed of current water and receives no reports from other
 * people, so the banner is grey, never the green of an all-clear, and the panel behind it says why.
 */
const TODAY_COPY = {
  banner: { en: "No flood reports near you", th: "ไม่มีรายงานน้ำท่วมใกล้คุณ" },
  note: { en: "Preparedness information · not an official warning", th: "ข้อมูลเพื่อการเตรียมพร้อม · ไม่ใช่คำเตือนทางการ" },
  explain: {
    en: "This app does not measure current water levels and receives no reports from other people. For current conditions, check DDPM and your local authorities.",
    th: "แอปนี้ไม่ได้วัดระดับน้ำปัจจุบัน และไม่ได้รับรายงานจากผู้อื่น โปรดตรวจสอบสถานการณ์ปัจจุบันกับ ปภ. และหน่วยงานท้องถิ่นของคุณ",
  },
  boundary: {
    en: "The preparedness information for this area is candidate research. It is non-operational: not an accepted priority score, not a reading of current hazard and not an official warning.",
    th: "ข้อมูลเพื่อการเตรียมพร้อมของพื้นที่นี้เป็นผลวิจัยแบบผู้สมัคร ไม่ใช้ปฏิบัติการ ไม่ใช่คะแนนลำดับความสำคัญที่ยอมรับแล้ว ไม่ใช่การวัดอันตรายปัจจุบัน และไม่ใช่คำเตือนทางการ",
  },
} as const;

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
  researchHref,
  practiceScenarioId = null,
  onPracticeEnd,
  onNavigatePrepare,
  onNavigateSos,
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
  // The banner is the one control that opens the panel, so the focus goes back to it when the panel closes.
  const bannerRef = useRef<HTMLButtonElement>(null);
  const hazardCloseRef = useRef<HTMLButtonElement>(null);
  const hazardPanelRef = useRef<HTMLElement>(null);
  // No area is framed for the reader: until they choose one the map shows the whole district.
  const chosenArea = data.publicAreas.find((area) => area.area_id === selectedAreaId);
  const practice = usePublicPractice(practiceScenarioId, language);
  const practising = practice.status !== "off";
  const practiceView = practice.status === "ready" ? practice.view : undefined;

  const focusAddressInput = useCallback(() => {
    window.requestAnimationFrame(() => searchInputRef.current?.focus());
  }, []);

  const applyLocation = useCallback((nextLocation: PublicMapLocation) => {
    onPracticeEnd?.();
    const areaId = findAreaIdForPoint(
      data.areaFeatures,
      nextLocation.longitude,
      nextLocation.latitude,
    );
    onLocationChange(nextLocation);
    if (areaId) onSelectArea(areaId);
    return areaId;
  }, [data.areaFeatures, onLocationChange, onPracticeEnd, onSelectArea]);

  const selectPlanningArea = useCallback((areaId: string) => {
    onPracticeEnd?.();
    locationAttemptRef.current += 1;
    searchAbortRef.current?.abort();
    setGpsState("idle");
    setSearchEditing(false);
    setSearchDraft("");
    setSearchState("idle");
    setSearchMessage("");
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
    onLocationChange(undefined);
    onSelectArea(areaId);
  }, [onLocationChange, onPracticeEnd, onSelectArea]);

  const requestPreciseLocation = useCallback(() => {
    const geolocation = navigator.geolocation;
    if (!geolocation) {
      setGpsState("unavailable");
      setSearchMessage(th
        ? "อุปกรณ์นี้ไม่รองรับตำแหน่ง GPS เลือกพื้นที่จากรายการแผนที่ หรือค้นหาที่อยู่เมื่อออนไลน์"
        : "This device does not provide GPS location. Choose an area from the map list, or search for an address when online.");
      focusAddressInput();
      return;
    }

    const attempt = locationAttemptRef.current + 1;
    locationAttemptRef.current = attempt;
    searchAbortRef.current?.abort();
    setSearchEditing(false);
    setSearchState("idle");
    setSuggestions([]);
    setActiveSuggestionIndex(-1);
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
            ? "ตำแหน่งที่ได้รับไม่ถูกต้อง เลือกพื้นที่จากรายการแผนที่"
            : "The returned position was invalid. Choose an area from the map list.");
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
            ? "ไม่ได้รับอนุญาตให้ใช้ตำแหน่ง เลือกพื้นที่จากรายการแผนที่ หรือค้นหาที่อยู่เมื่อออนไลน์"
            : "Location permission was not granted. Choose an area from the map list, or search for an address when online.");
        } else if (error.code === 3) {
          setGpsState("timeout");
          setSearchMessage(th
            ? "การค้นหา GPS ใช้เวลานานเกินไป เลือกพื้นที่จากรายการแผนที่ หรือลอง GPS อีกครั้ง"
            : "GPS took too long. Choose an area from the map list, or try GPS again.");
        } else {
          setGpsState("unavailable");
          setSearchMessage(th
            ? "ไม่สามารถรับตำแหน่ง GPS ได้ เลือกพื้นที่จากรายการแผนที่ หรือค้นหาที่อยู่เมื่อออนไลน์"
            : "GPS position is unavailable. Choose an area from the map list, or search for an address when online.");
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
        ? "พิมพ์อย่างน้อย 4 ตัวอักษร หรือเลือกพื้นที่จากรายการแผนที่"
        : "Enter at least four characters, or choose an area from the map list.");
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
        : (th ? "ไม่พบที่อยู่ในพื้นที่แม่สาย เพิ่มถนนหรือตำบล หรือเลือกพื้นที่จากรายการแผนที่" : "No address matched in the Mae Sai coverage. Add a road or district, or choose an area from the map list."));
    } catch {
      if (controller.signal.aborted) {
        return;
      }
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      setSearchState("unavailable");
      setSearchMessage(th
        ? "การค้นหาที่อยู่ออนไลน์ไม่พร้อมใช้งาน เลือกพื้นที่จากรายการแผนที่ได้โดยไม่ใช้อินเทอร์เน็ต หรือลองค้นหาอีกครั้ง"
        : "Online address search is unavailable. Choose an area from the map list without a network connection, or retry the search.");
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

  useEffect(() => () => {
    searchAbortRef.current?.abort();
    locationAttemptRef.current += 1;
  }, []);

  const closeHazard = useCallback(() => {
    setHazardOpen(false);
    bannerRef.current?.focus();
  }, []);
  useSheetKeyboard(hazardOpen, hazardPanelRef, hazardCloseRef, closeHazard);

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
      selectPlanningArea(areaMatch.area_id);
      setSearchMessage(th
        ? `เลือกพื้นที่วางแผน ${areaMatch.area_name_th} จากข้อมูลบนอุปกรณ์แล้ว`
        : `${areaMatch.area_name_en} planning area selected from on-device data.`);
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

  // One banner, always there: the scenario's sentence while practising, and a grey line on a day without practice.
  const banner: { tone: PracticeTone; text: string } = practiceView
    ? { tone: practiceView.tone, text: practiceView.banner }
    : practice.status === "loading"
      ? { tone: "neutral", text: PRACTICE_MENU_COPY.loading[language] }
      : practice.status === "unavailable"
        ? { tone: "neutral", text: PRACTICE_MENU_COPY.unavailable[language] }
        : { tone: "neutral", text: TODAY_COPY.banner[language] };
  const locationProblem = gpsState === "denied"
    || gpsState === "unavailable"
    || gpsState === "timeout"
    || searchState === "empty"
    || searchState === "unavailable";
  const showLocationCard = suggestions.length === 0
    && Boolean(location || locationProblem);

  return (
    <section className="public-home-page" aria-label={th ? "หน้าแรกเพื่อการเตรียมพร้อม" : "Preparedness home"}>
      {/* The block that stood above the map (heading, two buttons, the research link) was removed on the owner's
          request of 7 Oct 2026, so the search field stands directly under the header. The heading stays for a screen
          reader; "Make my plan" and "Help and contacts" are the Prepare and SOS tabs; the research link is in the
          panel behind the banner; the words "not an official warning" are in the note at the foot of the map and in
          that panel. */}
      <h1 className="sr-only">{practiceView
        ? practiceView.copy.heading
        : chosenArea
          ? (th ? chosenArea.area_name_th : chosenArea.area_name_en)
          : (th ? "เลือกพื้นที่วางแผนของคุณ" : "Choose your planning area")}</h1>
      <div className="public-home-map">
        <GeoMap
          areas={data.publicAreas}
          selectedId={selectedAreaId}
          onSelect={practising ? ignoreAreaSelection : selectPlanningArea}
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
          attributions={practising ? PRACTICE_CREDITS : NO_EXTRA_CREDITS}
          collapseAttribution
          visualPalette="public-outline"
          enableBasemaps
          basemapControlVariant="menu"
          compactBasemapNotice
          showLegend={false}
          showProvenanceBadge={false}
          showTextAlternative
          showDataAttribution={false}
          audience="public"
          // While a scenario is shown, its example home is the only pin on the map.
          location={practising ? undefined : location}
          initialFocus={selectedAreaId ? "selection" : "region"}
          selectionPinTitle={chosenArea && !practising
            ? (th ? chosenArea.area_name_th : chosenArea.area_name_en)
            : undefined}
          overlay={practice.overlay}
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
              locationAttemptRef.current += 1;
              searchAbortRef.current?.abort();
              setGpsState("idle");
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
          The banner stands directly under the search field and is always there (owner request of 13 Oct 2026). Its
          colour and its icon follow what it says; the tick is kept for the practice scenario without water, so a
          day without practice never reads as an all-clear. It opens the panel with the detail: the separate Hazard
          Info button, which opened the same panel, was removed as redundant on the owner's request of the same day.
        */}
        <button
          ref={bannerRef}
          type="button"
          className="public-signal-banner"
          data-tone={banner.tone}
          aria-controls="public-hazard-panel"
          aria-expanded={hazardOpen}
          onClick={() => setHazardOpen(true)}
        >
          <PublicAppIcon name={banner.tone === "calm" ? "check" : "hazard"} />
          <span>{banner.text}</span>
          <PublicAppIcon name="chevron" />
        </button>

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
                {locationProblem
                  ? searchMessage
                  : location?.source === "gps" && location.accuracyMeters
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

        </div>

        <div className="public-map-dock">
          {/*
            The priority card stood here until 13 Oct 2026 (owner: the public does not need the score). What stays on
            the first screen is the line that says what the page is not, and, while practising, which hour is shown.
          */}
          <p className="public-map-note" data-practice={practising ? "true" : undefined} data-public-not-a-warning>
            {practiceView ? (
              <>
                <strong>{practiceView.copy.noteTitle} · {practiceView.moment}</strong>
                <span>{practiceView.copy.noteBoundary}</span>
              </>
            ) : (
              <span>{TODAY_COPY.note[language]}</span>
            )}
          </p>
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
              if (event.currentTarget === event.target) closeHazard();
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
                  <p>{practising
                    ? (th ? "ฝึกซ้อมด้วยภาพจำลอง" : "PRACTICE REPLAY")
                    : (th ? "ข้อมูลเพื่อการเตรียมพร้อม" : "PREPAREDNESS INFORMATION")}</p>
                  <h2 id="public-hazard-title">
                    {practiceView
                      ? practiceView.copy.heading
                      : practising
                        ? banner.text
                        : chosenArea
                          ? (th ? chosenArea.area_name_th : chosenArea.area_name_en)
                          : (th ? "ยังไม่ได้เลือกพื้นที่วางแผน" : "No planning area chosen")}
                  </h2>
                </div>
                <button
                  ref={hazardCloseRef}
                  type="button"
                  className="public-icon-button"
                  aria-label={th ? "ปิดข้อมูลอันตราย" : "Close hazard information"}
                  onClick={closeHazard}
                >
                  <PublicAppIcon name="close" />
                </button>
              </div>

              {practiceView ? (
                <>
                  <p className="public-home-context" data-public-not-a-warning>{practiceView.copy.noteBoundary}</p>
                  <p className="public-practice-state" data-tone={practiceView.tone}>
                    <strong>{practiceView.banner}</strong>
                    <span>{practiceView.moment}</span>
                  </p>
                  <ul className="public-practice-lines">
                    {practiceView.lines.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                  <div className="public-hazard-guidance">
                    <PublicAppIcon name="prepare" />
                    <p>{practiceView.prompt}</p>
                  </div>
                  {(onNavigatePrepare || onNavigateSos) && (
                    <div className="public-practice-actions">
                      {onNavigatePrepare && (
                        <button type="button" onClick={onNavigatePrepare}>{th ? "ทบทวนแผนของฉัน" : "Review my plan"}</button>
                      )}
                      {onNavigateSos && (
                        <button type="button" onClick={onNavigateSos}>{th ? "หมายเลขฉุกเฉิน" : "Emergency numbers"}</button>
                      )}
                    </div>
                  )}
                  <h3 className="public-practice-key-heading">{practiceView.copy.keyHeading}</h3>
                  <ul className="public-practice-key">
                    {practiceView.key.map((item) => (
                      <li key={item.swatch}><i data-swatch={item.swatch} aria-hidden="true" />{item.text}</li>
                    ))}
                  </ul>
                  <p className="public-hazard-boundary">{practiceView.copy.homeNote} {practiceView.copy.boundary}</p>
                  <p className="public-practice-sources">{practiceView.copy.sources}</p>
                </>
              ) : practising ? (
                <p className="public-hazard-empty" role="status">
                  {practice.status === "unavailable"
                    ? PRACTICE_MENU_COPY.unavailableDetail[language]
                    : PRACTICE_MENU_COPY.loading[language]}
                </p>
              ) : (
                <>
                  {/* The line that stood above the map until 7 Oct 2026: it is said here, whatever area is chosen. */}
                  <p className="public-home-context" data-public-not-a-warning>{th ? "ข้อมูลเพื่อการเตรียมพร้อม · ไม่ใช่คำเตือนทางการ" : "Preparedness research · not an official warning"}</p>
                  <p className="public-hazard-explain">{TODAY_COPY.explain[language]}</p>

                  {chosenArea ? (
                    <>
                      <dl className="public-hazard-facts">
                        <div>
                          <dt>{th ? "ความเพียงพอของหลักฐาน" : "Evidence sufficiency"}</dt>
                          <dd>{formatConfidence(chosenArea.evidence_sufficiency, language)}</dd>
                        </div>
                        <div>
                          <dt>{th ? "เวลาของแหล่งข้อมูล" : "Source time"}</dt>
                          <dd>{formatSourceTime(chosenArea.source_timestamp, language)} ICT</dd>
                        </div>
                      </dl>

                      <div className="public-hazard-guidance">
                        <PublicAppIcon name="hazard" />
                        <p>{recommendationLabel(chosenArea, language)}</p>
                      </div>
                      <p className="public-hazard-boundary">{TODAY_COPY.boundary[language]}</p>
                    </>
                  ) : (
                    <p className="public-hazard-empty">
                      {th
                        ? "เลือกพื้นที่บนแผนที่ ใช้ GPS หรือค้นหาที่อยู่ เพื่อดูข้อมูลการเตรียมพร้อมของพื้นที่นั้น"
                        : "Choose an area on the map, use GPS or search for an address to see the preparedness information for that area."}
                    </p>
                  )}
                </>
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
              {researchHref ? <a className="public-home-research-link" href={researchHref}>{th ? "สำรวจกรณีศึกษาวิจัย →" : "Explore research cases →"}</a> : null}
            </aside>
          </div>
        )}
      </div>
    </section>
  );
}
