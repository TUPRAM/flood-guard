"use client";

import type { Map as LeafletMap } from "leaflet";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import type { DatasetMode, PublicPreparednessArea } from "@floodguard/contracts";

import { GeoMap } from "@/components/geo-map";
import { PublicAppIcon } from "@/components/public-app-icon";
import {
  HOUSEHOLD_NEEDS,
  householdNeedCountLabel,
  type HouseholdNeedId,
  type HouseholdPlan,
} from "@/lib/household-plan";
import {
  searchPublicAddresses,
  type PublicMapLocation,
} from "@/lib/public-location";
import {
  COMPASS_LABELS,
  MANEUVER_ICONS,
  MANEUVER_LABELS,
  areaCentre,
  buildRouteLeg,
  fetchWalkingRoute,
  formatRouteDistance,
  type WalkingRoute,
} from "@/lib/public-route";
import {
  loadShelterHistory,
  SHELTER_HISTORY_COPY,
  shelterSiteLines,
  shelterSiteSummary,
  type ShelterHistorySite,
} from "@/lib/public-shelter-history";
import {
  EMPTY_SHELTER_TRIP,
  SHELTER_PAGE_COPY,
  shelterBanner,
  shelterTone,
  type ShelterStepId,
  type ShelterTrip,
} from "@/lib/public-shelter-view";
import type { FeatureCollection, Language } from "@/lib/types";
import type { PublicPractice } from "@/lib/use-public-practice";
import { useSheetKeyboard } from "@/lib/use-sheet-keyboard";

type LeafletModule = typeof import("leaflet");
type MountShelterHistory = typeof import("@/components/public-shelter-layer").mountShelterHistory;

interface PublicShelterPageProps {
  language: Language;
  selectedAreaName: string;
  selectedAreaId: string;
  areas: PublicPreparednessArea[];
  areaFeatures: FeatureCollection;
  datasetMode: DatasetMode;
  plan: HouseholdPlan;
  onNavigatePrepare: () => void;
  /** What the reader has entered here. The Public shell keeps it, so it survives a visit to another page. */
  trip: ShelterTrip;
  onTripChange: (update: (trip: ShelterTrip) => ShelterTrip) => void;
  /**
   * The practice scenario chosen in the header, if any. While one is shown this map shows the same hour of the
   * replay around the example home, and distances are measured from that home.
   */
  practice?: PublicPractice;
  onPracticeEnd?: () => void;
  /**
   * Whether the places reported in use as shelters in September 2024 are shown. Their list is part of the Mae Sai
   * replay, which ships in the competition build alone.
   */
  showShelterHistory?: boolean;
}

const EMPTY_FEATURES: FeatureCollection = {
  type: "FeatureCollection",
  name: "public_shelter_withheld",
  features: [],
};
const NO_EXTRA_CREDITS: string[] = [];
/** The practice replay draws road pieces from OpenStreetMap on every background, so its credit joins the map's. */
const PRACTICE_CREDITS = ["© OpenStreetMap contributors"];
const PRACTICE_OFF: PublicPractice = { status: "off" };
/** The areas are drawn for orientation on this map; a tap on one chooses nothing. */
const ignoreAreaSelection = () => {};
/** What the route keeps clear of when the map frames it: the field and the banner above, the tools and the note below. */
const ROUTE_VIEW_PADDING = { topLeft: [24, 176], bottomRight: [72, 120] } as const;

type RouteStepId = ShelterStepId;
type ShelterIconName =
  | "accessibility"
  | "arrow"
  | "child"
  | "elder"
  | "house"
  | "medicine"
  | "pet"
  | "transport"
  | "check"
  | "destination"
  | "phone"
  | "route"
  | "turn-left"
  | "turn-right"
  | "slight-left"
  | "slight-right"
  | "sharp-left"
  | "sharp-right"
  | "uturn"
  | "roundabout"
  | "walk"
  | "warning";

const ROUTE_STEPS: Array<{
  id: RouteStepId;
  en: string;
  th: string;
}> = [
  {
    id: "confirm_destination",
    en: "Confirm that the selected destination is open and can receive your household.",
    th: "ยืนยันว่าจุดหมายที่เลือกเปิดให้บริการและสามารถรองรับครัวเรือนของคุณได้",
  },
  {
    id: "confirm_route",
    en: "Confirm the route and travel conditions with DDPM or a local authority.",
    th: "ยืนยันเส้นทางและสภาพการเดินทางกับ ปภ. หรือหน่วยงานท้องถิ่น",
  },
  {
    id: "prepare_household",
    en: "Bring medicine, documents, drinking water, and the support items your household needs.",
    th: "นำยา เอกสาร น้ำดื่ม และอุปกรณ์ช่วยเหลือที่ครัวเรือนของคุณต้องใช้",
  },
  {
    id: "share_plan",
    en: "Tell a trusted contact which destination and route option you selected.",
    th: "แจ้งผู้ติดต่อที่ไว้ใจว่าคุณเลือกจุดหมายและเส้นทางใด",
  },
];

const NEED_ICONS: Record<HouseholdNeedId, ShelterIconName> = {
  children: "child",
  older_adults: "elder",
  mobility_support: "accessibility",
  regular_medicine: "medicine",
  pets: "pet",
  limited_transport: "transport",
};

const NEED_SHORT_LABELS: Record<HouseholdNeedId, { en: string; th: string }> = {
  children: { en: "Children", th: "เด็ก" },
  older_adults: { en: "Older adults", th: "ผู้สูงอายุ" },
  mobility_support: { en: "Mobility support", th: "การช่วยเหลือด้านการเคลื่อนไหว" },
  regular_medicine: { en: "Regular medicine", th: "ยาประจำ" },
  pets: { en: "Pets", th: "สัตว์เลี้ยง" },
  limited_transport: { en: "Transport support", th: "การช่วยเหลือด้านการเดินทาง" },
};

function ShelterIcon({ name }: { name: ShelterIconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.9,
  };

  return (
    <svg aria-hidden="true" className="public-shelter-icon" viewBox="0 0 24 24">
      {name === "accessibility" && (
        <>
          <circle {...common} cx="12" cy="4.5" r="1.6" />
          <path {...common} d="M10.5 8.2h3.7l2.2 3.4M11.1 8.2l-1 5.1 3.4 2.2 1.7 4M8.9 11.2a5.1 5.1 0 1 0 4.4 8" />
        </>
      )}
      {name === "child" && (
        <>
          <circle {...common} cx="12" cy="5" r="2.3" />
          <path {...common} d="M12 9v6M8.5 11.5 12 10l3.5 1.5M9.5 21l2.5-6 2.5 6" />
        </>
      )}
      {name === "elder" && (
        <>
          <circle {...common} cx="11" cy="4.6" r="2.1" />
          <path {...common} d="M11 8.6v6.2M8.4 11l2.6-1.4 2.6 1.4M9 21l2-6.2 2.4 6.2M17 9.5V21" />
        </>
      )}
      {name === "house" && (
        <>
          <path {...common} d="M3.5 10.6 12 4l8.5 6.6" />
          <path {...common} d="M5.6 9.5V20h12.8V9.5" />
          <path {...common} d="M9.8 20v-5.2h4.4V20" />
        </>
      )}
      {name === "medicine" && (
        <>
          <rect {...common} x="4" y="7.5" width="16" height="12" rx="2.5" />
          <path {...common} d="M12 11v5M9.5 13.5h5M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5" />
        </>
      )}
      {name === "pet" && (
        <>
          <circle {...common} cx="6.4" cy="10.4" r="1.8" />
          <circle {...common} cx="10.6" cy="6.6" r="1.8" />
          <circle {...common} cx="15.4" cy="6.6" r="1.8" />
          <circle {...common} cx="19" cy="10.9" r="1.8" />
          <path {...common} d="M12.8 12.2c2.6 0 4.6 2 4.6 4.3 0 2-1.4 3.2-3.3 3.2-1 0-1.4-.5-2.6-.5s-1.6.5-2.6.5c-1.9 0-3.3-1.2-3.3-3.2 0-2.3 2-4.3 4.6-4.3Z" />
        </>
      )}
      {name === "transport" && (
        <>
          <path {...common} d="M4 16.5V9a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v7.5" />
          <path {...common} d="M17 11h2.2l1.8 3v2.5H4" />
          <circle {...common} cx="8" cy="17.5" r="1.9" />
          <circle {...common} cx="17" cy="17.5" r="1.9" />
        </>
      )}
      {name === "arrow" && (
        <>
          <path {...common} d="M5 12h14" />
          <path {...common} d="m14 7 5 5-5 5" />
        </>
      )}
      {name === "check" && <path {...common} d="m5 12 4.2 4.2L19 6.5" />}
      {/* Turn arrows: the stem shows the approach, the head the new heading. */}
      {name === "turn-left" && (
        <>
          <path {...common} d="M18 20v-7a4 4 0 0 0-4-4H7" />
          <path {...common} d="m11 5-5 4 5 4" />
        </>
      )}
      {name === "turn-right" && (
        <>
          <path {...common} d="M6 20v-7a4 4 0 0 1 4-4h7" />
          <path {...common} d="m13 5 5 4-5 4" />
        </>
      )}
      {name === "slight-left" && (
        <>
          <path {...common} d="M17 20v-6.5a5 5 0 0 0-1.5-3.6L9 4" />
          <path {...common} d="M8 9V4h5" />
        </>
      )}
      {name === "slight-right" && (
        <>
          <path {...common} d="M7 20v-6.5a5 5 0 0 1 1.5-3.6L15 4" />
          <path {...common} d="M16 9V4h-5" />
        </>
      )}
      {name === "sharp-left" && (
        <>
          <path {...common} d="M17 20v-5a5 5 0 0 0-5-5H8" />
          <path {...common} d="m12 6-5 4 5 4" />
        </>
      )}
      {name === "sharp-right" && (
        <>
          <path {...common} d="M7 20v-5a5 5 0 0 1 5-5h4" />
          <path {...common} d="m12 6 5 4-5 4" />
        </>
      )}
      {name === "uturn" && (
        <>
          <path {...common} d="M8 20V9a4 4 0 0 1 8 0v11" />
          <path {...common} d="m5 12 3-3 3 3" />
        </>
      )}
      {name === "roundabout" && (
        <>
          <circle {...common} cx="11" cy="13" r="4" />
          <path {...common} d="M11 20v-3M15 13h5" />
          <path {...common} d="m17 10 3 3-3 3" />
        </>
      )}
      {name === "destination" && (
        <>
          <path {...common} d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
          <circle {...common} cx="12" cy="10" r="2.5" />
        </>
      )}
      {name === "phone" && (
        <path {...common} d="M7.1 3.5 10 7.9 8.3 10a15.2 15.2 0 0 0 5.7 5.7l2.1-1.7 4.4 2.9-.8 3a2 2 0 0 1-2 1.5C10.1 20.5 3.5 13.9 2.6 6.3a2 2 0 0 1 1.5-2l3-.8Z" />
      )}
      {name === "route" && (
        <>
          <circle {...common} cx="6" cy="18" r="2" />
          <circle {...common} cx="18" cy="6" r="2" />
          <path {...common} d="M7.8 17.2c2.1-.9 2.5-2.2 1.2-3.8-1.7-2.1-.2-4.3 2.6-4.3h1.1c1.5 0 2.8-.6 3.6-1.7" />
        </>
      )}
      {name === "walk" && (
        <>
          <circle {...common} cx="13" cy="4.2" r="1.7" />
          <path {...common} d="m11.1 8.1 3.1 1.8 2.4 3.3M12 9.2l-1.5 4.2-3.2 2.3M10.5 13.4l3.1 2.3 1.1 4.1M9.7 15.2 8.1 20" />
        </>
      )}
      {name === "warning" && (
        <>
          <path {...common} d="M12 3 2.8 20h18.4L12 3Z" />
          <path {...common} d="M12 9v5M12 17.2h.01" />
        </>
      )}
    </svg>
  );
}

export function PublicShelterPage({
  language,
  selectedAreaName,
  selectedAreaId,
  areas,
  areaFeatures,
  datasetMode,
  plan,
  onNavigatePrepare,
  trip,
  onTripChange,
  practice = PRACTICE_OFF,
  onPracticeEnd,
  showShelterHistory = false,
}: PublicShelterPageProps) {
  const th = language === "th";
  const destinationInputId = useId();
  const destinationConfirmationId = useId();
  const routeChecklistId = useId();
  // A site is a place taken from the list of 2024. Its position is the list's own, so no address is looked up for it.
  const {
    draft: destinationDraft,
    draftSite,
    destination: selectedDestination,
    destinationSite: selectedSite,
    authorityConfirmed,
  } = trip;
  const completedSteps = useMemo(() => new Set(trip.completedSteps), [trip.completedSteps]);
  const practiceView = practice.status === "ready" ? practice.view : undefined;
  const drawPractice = practice.status === "ready" ? practice.overlay : undefined;
  const [resolvedPin, setResolvedPin] = useState<{
    destination: string;
    location: PublicMapLocation;
  } | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [history, setHistory] = useState<{
    sites: ShelterHistorySite[];
    mount: MountShelterHistory;
  } | null>(null);
  // The banner is the control that opens the sheet, so the focus goes back to it when the sheet closes.
  const bannerRef = useRef<HTMLButtonElement>(null);
  const sheetCloseRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  // The map moves to the places of 2024 once, when they arrive; after that the view is the reader's.
  const historyFramedRef = useRef(false);

  const closeSheet = useCallback(() => {
    setSheetOpen(false);
    bannerRef.current?.focus();
  }, []);
  useSheetKeyboard(sheetOpen, sheetRef, sheetCloseRef, closeSheet);

  // The places reported as shelters in 2024 and the code that draws them. They are an addition: without them (the
  // public build, or no connection on a first visit) the page works as it did.
  useEffect(() => {
    if (!showShelterHistory) return;
    const controller = new AbortController();
    Promise.all([
      loadShelterHistory(controller.signal),
      import("@/components/public-shelter-layer"),
    ])
      .then(([sites, layer]) => {
        if (controller.signal.aborted || sites.length === 0) return;
        setHistory({ sites, mount: layer.mountShelterHistory });
      })
      .catch(() => {
        /* The list of 2024 is an addition; the map and the destination field stay. */
      });
    return () => controller.abort();
  }, [showShelterHistory]);

  // A new destination in the field: whatever was confirmed or ticked before belongs to the old one.
  const startDestination = useCallback((value: string, site: ShelterHistorySite | null) => {
    onTripChange(() => ({ ...EMPTY_SHELTER_TRIP, draft: value, draftSite: site }));
  }, [onTripChange]);

  // Taking a place of 2024 only fills the field. The sheet opens on the step that asks whether an authority
  // confirmed it: the list is history and says nothing about today.
  const chooseSite = useCallback((site: ShelterHistorySite) => {
    startDestination(site.name[language], site);
    setSheetOpen(true);
    sheetRef.current?.scrollTo({ top: 0 });
  }, [language, startDestination]);

  const hasMarkers = Boolean(history?.sites.some((site) => site.point));
  const overlay = useMemo(() => {
    const places = history && hasMarkers ? history : null;
    if (!drawPractice && !places) return undefined;
    return (map: LeafletMap, leaflet: LeafletModule) => {
      // The scenario first: it draws the hour of the replay and moves the map to the example home. The markers of
      // 2024 lie over it.
      const removePractice = drawPractice?.(map, leaflet);
      let removePlaces: (() => void) | undefined;
      if (places) {
        // With a scenario or an area chosen the map already shows where the reader is looking.
        const frame = !drawPractice && !historyFramedRef.current && !selectedAreaId;
        if (!drawPractice) historyFramedRef.current = true;
        removePlaces = places.mount(leaflet, map, places.sites, language, chooseSite, frame);
      }
      return () => {
        removePlaces?.();
        removePractice?.();
      };
    };
  }, [chooseSite, drawPractice, hasMarkers, history, language, selectedAreaId]);

  // The pin is the position of the place taken from the list, or comes from geocoding whatever destination is
  // confirmed, so the map never shows a coordinate the app invented. Tagged with the destination it belongs to, so a
  // pin for a previous destination is filtered out by derivation rather than cleared in an effect. Offline it stays
  // absent and the map still shows the real planning-area boundary.
  const destinationPin = useMemo<PublicMapLocation | undefined>(() => {
    if (!selectedDestination) return undefined;
    if (selectedSite?.point) {
      return { ...selectedSite.point, label: selectedDestination, source: "address" };
    }
    return resolvedPin?.destination === selectedDestination ? resolvedPin.location : undefined;
  }, [resolvedPin, selectedDestination, selectedSite]);

  useEffect(() => {
    if (!selectedDestination || selectedSite?.point) return;
    const controller = new AbortController();
    searchPublicAddresses(selectedDestination, language, controller.signal)
      .then((matches) => {
        const match = matches[0];
        if (controller.signal.aborted || !match) return;
        setResolvedPin({
          destination: selectedDestination,
          location: {
            latitude: match.latitude,
            longitude: match.longitude,
            label: match.label,
            source: "address",
          },
        });
      })
      .catch(() => {
        /* Address lookup is an enhancement; the boundary map still renders. */
      });
    return () => controller.abort();
  }, [language, selectedDestination, selectedSite]);

  // Where distances start: the centre of the chosen planning area, never a position of the reader. In a practice
  // scenario it is the example home, which is a point of the model and nobody's address.
  const practiceHome = practiceView?.home;
  const origin = useMemo(() => (
    practiceHome
      ? { latitude: practiceHome.latitude, longitude: practiceHome.longitude }
      : areaCentre(areaFeatures, selectedAreaId)
  ), [areaFeatures, practiceHome, selectedAreaId]);

  // Straight-line leg from there to the destination. Both ends come from real geometry, so the distance and bearing
  // below are measured rather than invented.
  const routeLeg = useMemo(() => buildRouteLeg(
    origin,
    destinationPin
      ? { latitude: destinationPin.latitude, longitude: destinationPin.longitude }
      : undefined,
  ), [destinationPin, origin]);

  const [resolvedRoute, setResolvedRoute] = useState<{
    key: string;
    route: WalkingRoute;
  } | null>(null);

  // Keyed by the leg it was computed for, so a route for a previous
  // destination is discarded by derivation rather than cleared in an effect.
  const routeKey = routeLeg
    ? `${routeLeg.from.latitude},${routeLeg.from.longitude};${routeLeg.to.latitude},${routeLeg.to.longitude}`
    : "";
  const walkingRoute = resolvedRoute?.key === routeKey ? resolvedRoute.route : undefined;

  // Asks OSRM for the road-following route. On failure the page keeps the
  // straight-line leg rather than showing nothing.
  useEffect(() => {
    if (!routeLeg || !routeKey) return;
    const controller = new AbortController();
    fetchWalkingRoute(routeLeg.from, routeLeg.to, controller.signal)
      .then((route) => {
        if (controller.signal.aborted || !route) return;
        setResolvedRoute({ key: routeKey, route });
      })
      .catch(() => {
        /* Routing is an enhancement; the straight-line leg stays. */
      });
    return () => controller.abort();
  }, [routeKey, routeLeg]);

  const routePath = useMemo(() => {
    if (walkingRoute) return walkingRoute.path;
    if (!routeLeg) return undefined;
    return [
      [routeLeg.from.latitude, routeLeg.from.longitude] as const,
      [routeLeg.to.latitude, routeLeg.to.longitude] as const,
    ];
  }, [routeLeg, walkingRoute]);

  const directions = useMemo(() => {
    // Real turns from the router when it answered. OSRM names the road each
    // step travels along, so the road you are leaving is the previous step's
    // name — that is what makes "after X" accurate rather than guessed.
    if (walkingRoute && walkingRoute.steps.length > 0) {
      const steps = walkingRoute.steps;
      return steps.map((step, index) => {
        const previousName = index > 0 ? steps[index - 1].name : "";
        const onto = step.name
          ? (th ? `เข้าสู่ ${step.name}` : `onto ${step.name}`)
          : "";
        const after = previousName && previousName !== step.name
          ? (th ? `หลังจาก ${previousName}` : `after ${previousName}`)
          : "";
        const distance = step.metres > 0
          ? formatRouteDistance(step.metres, language)
          : "";

        if (step.maneuver === "arrive") {
          return {
            id: `step-${index}`,
            icon: MANEUVER_ICONS.arrive,
            title: th ? `ถึง ${selectedDestination}` : `Arrive at ${selectedDestination}`,
            detail: th
              ? "ยืนยันทางเข้าและว่าจุดหมายเปิดให้บริการก่อนออกเดินทาง"
              : "Confirm the entrance and that the destination is open before you travel.",
          };
        }

        const title = [MANEUVER_LABELS[step.maneuver][language], onto, after]
          .filter(Boolean)
          .join(" ");
        const remaining = index < steps.length - 1
          ? steps.slice(index + 1).reduce((total, rest) => total + rest.metres, 0)
          : 0;
        const detail = [
          distance
            ? (th ? `เดินต่อประมาณ ${distance}` : `Continue for about ${distance}.`)
            : "",
          remaining > 0
            ? (th
              ? `เหลืออีก ${formatRouteDistance(remaining, language)} ถึงจุดหมาย`
              : `${formatRouteDistance(remaining, language)} still to go.`)
            : "",
        ].filter(Boolean).join(" ");

        return {
          id: `step-${index}`,
          icon: MANEUVER_ICONS[step.maneuver],
          title,
          detail,
        };
      });
    }

    // Routing unavailable: show orientation only, never turn-by-turn advice.
    if (!routeLeg) return [];
    const heading = COMPASS_LABELS[routeLeg.bearing][language];
    const distance = formatRouteDistance(routeLeg.metres, language);
    return [
      {
        id: "orientation",
        icon: "route" as const,
        title: th
          ? `จุดหมายอยู่ทาง${heading} · ระยะเส้นตรง ${distance}`
          : `Destination lies ${heading} · ${distance} straight-line distance`,
        detail: th
          ? "ยังไม่มีเส้นทางเดินตามถนน ข้อมูลนี้ใช้ดูทิศทางเท่านั้น อย่าใช้เพื่อนำทาง"
          : "No road-following walking route is available. This is orientation only, not directions.",
      },
    ];
  }, [language, routeLeg, selectedDestination, th, walkingRoute]);

  const selectedNeeds = useMemo(
    () => HOUSEHOLD_NEEDS.filter(({ id }) => plan.needs[id]),
    [plan.needs],
  );
  const completedStepCount = completedSteps.size;
  const draftName = destinationDraft.trim();

  const saveDestination = () => {
    if (!draftName || !authorityConfirmed) return;
    onTripChange((current) => ({ ...current, destination: draftName, destinationSite: current.draftSite, completedSteps: [] }));
    // The sheet makes way for the map, which now shows the pin and the line to it.
    closeSheet();
  };

  const toggleStep = (stepId: RouteStepId) => {
    onTripChange((current) => ({
      ...current,
      completedSteps: current.completedSteps.includes(stepId)
        ? current.completedSteps.filter((id) => id !== stepId)
        : [...current.completedSteps, stepId],
    }));
  };

  const banner = shelterBanner({
    draft: destinationDraft,
    destination: selectedDestination,
    practice: practiceView ? { tone: practiceView.tone, text: practiceView.pages.shelter.banner } : undefined,
    walk: walkingRoute ? { metres: walkingRoute.metres, minutes: walkingRoute.minutes } : undefined,
    directMetres: routeLeg?.metres,
  }, language);

  const historySection = history ? (
    <section className="public-shelter-sheet-section public-shelter-history" aria-labelledby="public-shelter-history-title">
      <h3 id="public-shelter-history-title">{SHELTER_HISTORY_COPY.listHeading[language]}</h3>
      <p>{SHELTER_HISTORY_COPY.listNote[language]}</p>
      <ul>
        {history.sites.map((site) => (
          <li key={site.id}>
            <span>
              <strong>{site.name[language]}</strong>
              <small>{shelterSiteSummary(site, language)}</small>
            </span>
            {/* A place without a known position cannot be drawn, so it is listed and not offered. */}
            {site.point ? (
              <button type="button" onClick={() => chooseSite(site)}>
                {SHELTER_HISTORY_COPY.use[language]}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  ) : null;

  return (
    <section className="public-home-page public-shelter-page" aria-labelledby="public-shelter-title">
      {/*
        Until 13 Oct 2026 this page was a column of cards with a small map among them. On the owner's request it has
        the frame of Home, whose class names it wears for that: the map takes the page, the destination field and
        the banner stand over it, and everything else is in the sheet the banner opens.
      */}
      <h1 id="public-shelter-title" className="sr-only">{SHELTER_PAGE_COPY.title[language]}</h1>
      <div className="public-home-map public-shelter-map">
        {/* Road-following routes and direct orientation lines are labelled separately, in the note at the foot. */}
        <GeoMap
          areas={areas}
          selectedId={selectedAreaId}
          onSelect={ignoreAreaSelection}
          language={language}
          showRoads={false}
          showFacilities={false}
          showAccess={false}
          height="100%"
          areaFeatures={areaFeatures}
          roadFeatures={EMPTY_FEATURES}
          facilityFeatures={EMPTY_FEATURES}
          accessFeatures={EMPTY_FEATURES}
          contextFeatures={EMPTY_FEATURES}
          datasetMode={datasetMode}
          showSelectionSheet={false}
          attributions={drawPractice ? PRACTICE_CREDITS : NO_EXTRA_CREDITS}
          // As on Home: the credit of the map data folds away once shown and is repeated in the layers menu.
          collapseAttribution
          visualPalette="public-outline"
          enableBasemaps
          basemapControlVariant="menu"
          compactBasemapNotice
          showLegend={false}
          showProvenanceBadge={false}
          showTextAlternative={false}
          showDataAttribution={false}
          audience="public"
          location={destinationPin}
          initialFocus={selectedAreaId ? "selection" : "region"}
          routePath={routePath}
          routeViewPadding={ROUTE_VIEW_PADDING}
          overlay={overlay}
        />
        <p className="sr-only">
          {th
            ? `แผนที่แสดงขอบเขตพื้นที่ ${selectedAreaName || "ที่เลือก"} และหมุดจุดหมาย ${selectedDestination || "ที่ยังไม่ได้เลือก"} ${walkingRoute ? "มีเส้นทางเดินตามแผนที่ถนนที่ต้องตรวจสอบสภาพจริง" : "อาจมีเส้นตรงเพื่อดูทิศทางซึ่งไม่ใช่เส้นทางเดิน"}${hasMarkers ? " หมุดรูปบ้านคือสถานที่ที่มีรายงานว่าใช้เป็นที่พักพิงในเดือนกันยายน 2567 (2024) ซึ่งมีรายการอยู่ในรายละเอียดด้านหลังแถบข้อความ" : ""}`
            : `Map showing the ${selectedAreaName || "selected"} area boundary and a pin for ${selectedDestination || "the destination yet to be selected"}. ${walkingRoute ? "A road-map walking route requires on-site verification." : "Any direct line is orientation only, not a walking route."}${hasMarkers ? " The house markers are the places reported as shelters in September 2024; they are listed in the details behind the banner." : ""}`}
        </p>

        <div className="public-map-rail">
          <div className="public-map-search-field">
            <form
              className="public-map-search"
              onSubmit={(event) => {
                event.preventDefault();
                if (draftName) setSheetOpen(true);
              }}
            >
              <PublicAppIcon name="pin" />
              <label className="sr-only" htmlFor={destinationInputId}>{SHELTER_PAGE_COPY.fieldLabel[language]}</label>
              <input
                id={destinationInputId}
                autoComplete="off"
                value={destinationDraft}
                onChange={(event) => startDestination(event.target.value, null)}
                placeholder={SHELTER_PAGE_COPY.fieldLabel[language]}
                type="text"
              />
              <button type="submit" disabled={!draftName}>{SHELTER_PAGE_COPY.fieldNext[language]}</button>
            </form>
          </div>

          {/*
            The banner is always there and opens the sheet, as on Home. It is never green: the page knows no shelter
            that is open today.
          */}
          <button
            ref={bannerRef}
            type="button"
            className="public-signal-banner"
            data-tone={banner.tone}
            aria-controls="public-shelter-panel"
            aria-expanded={sheetOpen}
            onClick={() => setSheetOpen(true)}
          >
            <PublicAppIcon name={banner.icon} />
            <span>{banner.text}</span>
            <PublicAppIcon name="chevron" />
          </button>
        </div>

        <div className="public-map-dock">
          {/*
            In a practice scenario the note says, as on Home, which hour of the replay the map shows and what the
            replay is not. What the page does not know about today is then the first line of the sheet.
          */}
          <p className="public-map-note" data-practice={practiceView ? "true" : undefined} data-public-not-a-warning={practiceView ? true : undefined}>
            {practiceView ? (
              <>
                <strong>{practiceView.copy.noteTitle} · {practiceView.moment}</strong>
                <span>{practiceView.copy.noteBoundary}</span>
              </>
            ) : null}
            {routePath ? (
              <strong>{(walkingRoute ? SHELTER_PAGE_COPY.routeWalk : SHELTER_PAGE_COPY.routeDirect)[language]}</strong>
            ) : null}
            {practiceView ? null : <span>{SHELTER_PAGE_COPY.noteUnknown[language]}</span>}
            {hasMarkers ? <span>{SHELTER_HISTORY_COPY.mapNote[language]}</span> : null}
          </p>
        </div>

        {sheetOpen && (
          <div
            className="public-hazard-overlay"
            role="presentation"
            onMouseDown={(event) => {
              if (event.currentTarget === event.target) closeSheet();
            }}
          >
            <aside
              ref={sheetRef}
              id="public-shelter-panel"
              className="public-hazard-panel public-shelter-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby="public-shelter-panel-title"
            >
              <div className="public-hazard-panel-heading">
                <div>
                  <p>{SHELTER_PAGE_COPY.panelEyebrow[language]}</p>
                  <h2 id="public-shelter-panel-title">
                    {selectedDestination || draftName || SHELTER_PAGE_COPY.panelHeading[language]}
                  </h2>
                </div>
                <button
                  ref={sheetCloseRef}
                  type="button"
                  className="public-icon-button"
                  aria-label={SHELTER_PAGE_COPY.panelClose[language]}
                  onClick={closeSheet}
                >
                  <PublicAppIcon name="close" />
                </button>
              </div>
              <p className="public-hazard-explain">{SHELTER_PAGE_COPY.unknown[language]}</p>

              {practiceView ? (
                <section className="public-shelter-practice" aria-label={practiceView.copy.noteTitle}>
                  <p className="public-practice-state" data-tone={shelterTone(practiceView.tone)}>
                    <strong>{practiceView.pages.shelter.banner}</strong>
                    <span>{practiceView.copy.noteTitle} · {practiceView.moment} · {practiceView.copy.homeLabel}</span>
                  </p>
                  <ul className="public-practice-lines">
                    {practiceView.pages.shelter.lines.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                  <div className="public-hazard-guidance">
                    <PublicAppIcon name="prepare" />
                    <p>{practiceView.pages.shelter.prompt}</p>
                  </div>
                  {onPracticeEnd ? (
                    <div className="public-practice-actions">
                      <button
                        type="button"
                        onClick={() => {
                          closeSheet();
                          onPracticeEnd();
                        }}
                      >
                        {practiceView.copy.end}
                      </button>
                    </div>
                  ) : null}
                  <p className="public-hazard-boundary" data-public-not-a-warning>{practiceView.copy.homeNote} {practiceView.copy.boundary}</p>
                </section>
              ) : null}

              {selectedDestination ? (
                <>
                  <dl className="public-hazard-facts">
                    <div>
                      <dt>{practiceView ? SHELTER_PAGE_COPY.from[language] : (th ? "พื้นที่วางแผน" : "Planning area")}</dt>
                      <dd>{practiceView ? practiceView.copy.heading : selectedAreaName || (th ? "ไม่ได้เลือกพื้นที่" : "No area selected")}</dd>
                    </div>
                    <div>
                      <dt>{th ? "รูปแบบการเดินทาง" : "Travel mode"}</dt>
                      <dd>{th ? "เดินเท้า" : "Walking"}</dd>
                    </div>
                    <div>
                      <dt>{walkingRoute
                        ? (th ? "ระยะเดิน" : "Walking distance")
                        : (th ? "ระยะเส้นตรง" : "Direct distance")}</dt>
                      <dd>
                        {walkingRoute
                          ? `${formatRouteDistance(walkingRoute.metres, language)} · ${walkingRoute.minutes} ${th ? "นาที" : "min"}`
                          : routeLeg
                            ? formatRouteDistance(routeLeg.metres, language)
                            : (th ? "ยังคำนวณไม่ได้" : "Not available yet")}
                      </dd>
                    </div>
                  </dl>

                  <section className="public-shelter-sheet-section" aria-labelledby="public-shelter-directions-title">
                    <h3 id="public-shelter-directions-title">
                      {walkingRoute ? (th ? "ข้อมูลเส้นทางเดิน" : "Walking route information") : (th ? "ข้อมูลทิศทาง" : "Orientation information")}
                    </h3>
                    {directions.length > 0 ? (
                      <ol className="public-shelter-directions__list">
                        {directions.map((step) => (
                          <li key={step.id}>
                            <span className="public-shelter-directions__icon" aria-hidden="true">
                              <ShelterIcon name={step.icon} />
                            </span>
                            <div>
                              <h4>{step.title}</h4>
                              <p>{step.detail}</p>
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p>
                        {th
                          ? "ยังคำนวณระยะทางไม่ได้ ต้องมีพื้นที่วางแผน (เลือกได้ในหน้าแรกหรือหน้าเตรียมพร้อม) และชื่อสถานที่ที่ระบบค้นหาที่อยู่พบ"
                          : "The distance is not available yet. It needs a planning area (choose one on Home or in Prepare) and a place the address search can find."}
                      </p>
                    )}
                  </section>
                </>
              ) : draftName ? (
                <div className="public-shelter-confirm">
                  {draftSite ? (
                    <ul className="public-practice-lines">
                      {shelterSiteLines(draftSite, language).map((line) => <li key={line}>{line}</li>)}
                    </ul>
                  ) : null}
                  <label className="public-shelter-destination__confirmation" htmlFor={destinationConfirmationId}>
                    <input
                      id={destinationConfirmationId}
                      checked={authorityConfirmed}
                      onChange={(event) => {
                        const authorityConfirmed = event.target.checked;
                        onTripChange((current) => ({ ...current, authorityConfirmed }));
                      }}
                      type="checkbox"
                    />
                    <span>{SHELTER_PAGE_COPY.confirmation[language]}</span>
                  </label>
                  <button
                    className="public-shelter-primary-action"
                    disabled={!authorityConfirmed}
                    type="button"
                    onClick={saveDestination}
                  >
                    {SHELTER_PAGE_COPY.use[language]}
                  </button>
                </div>
              ) : (
                <p className="public-hazard-empty">
                  {(history ? SHELTER_PAGE_COPY.emptyWithHistory : SHELTER_PAGE_COPY.empty)[language]}
                </p>
              )}

              {/*
                With no destination the list of 2024 comes first: it is what the reader can start from. Once a
                destination is in the field the checklist for it comes first, and the list moves below.
              */}
              {!draftName && !selectedDestination ? historySection : null}
              {draftName || selectedDestination ? (
                <section className="public-shelter-sheet-section public-shelter-checklist" aria-labelledby={routeChecklistId}>
                  <div className="public-shelter-checklist__heading">
                    <h3 id={routeChecklistId}>{th ? "รายการตรวจสอบทีละขั้น" : "Step-by-step checklist"}</h3>
                    <span aria-label={th ? `ทำแล้ว ${completedStepCount} จาก ${ROUTE_STEPS.length} ขั้น` : `${completedStepCount} of ${ROUTE_STEPS.length} steps complete`}>
                      {completedStepCount}/{ROUTE_STEPS.length}
                    </span>
                  </div>
                  <progress max={ROUTE_STEPS.length} value={completedStepCount}>
                    {completedStepCount}/{ROUTE_STEPS.length}
                  </progress>
                  <ol>
                    {ROUTE_STEPS.map((step, index) => (
                      <li className={completedSteps.has(step.id) ? "completed" : ""} key={step.id}>
                        <label>
                          <input
                            checked={completedSteps.has(step.id)}
                            onChange={() => toggleStep(step.id)}
                            type="checkbox"
                          />
                          <span className="public-shelter-checklist__number" aria-hidden="true">
                            {completedSteps.has(step.id) ? <ShelterIcon name="check" /> : index + 1}
                          </span>
                          <span>{step[language]}</span>
                        </label>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              <section className="public-shelter-sheet-section public-shelter-profile" aria-labelledby="public-shelter-profile-title">
                <div>
                  <h3 id="public-shelter-profile-title">{th ? "ข้อมูลครัวเรือน" : "Household profile"}</h3>
                  <p className="public-shelter-profile__summary">
                    {selectedNeeds.length > 0
                      ? (th ? "ความต้องการที่ควรคำนึงถึงระหว่างเดินทาง" : "Needs to account for while travelling")
                      : (th ? "ยังไม่ได้บันทึกความต้องการช่วยเหลือ" : "No support needs recorded")}
                  </p>
                  {selectedNeeds.length > 0 && (
                    <ul className="public-shelter-profile__needs" aria-label={th ? "ความต้องการของครัวเรือน" : "Household needs"}>
                      {selectedNeeds.map(({ id }) => (
                        <li key={id}>
                          {/* Each need carries its own icon, so the list describes the
                              household rather than showing one stand-in symbol. */}
                          <ShelterIcon name={NEED_ICONS[id]} />
                          <span>
                            {householdNeedCountLabel(id, plan.need_counts[id] ?? 1, language)
                              ?? NEED_SHORT_LABELS[id][language]}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <button className="public-shelter-profile__edit" type="button" onClick={onNavigatePrepare}>
                  {th ? "แก้ไข" : "Edit"}
                </button>
              </section>

              {draftName || selectedDestination ? historySection : null}

              <aside className="public-shelter-safety" aria-labelledby="public-shelter-safety-title">
                <ShelterIcon name="warning" />
                <div>
                  <h3 id="public-shelter-safety-title">{SHELTER_PAGE_COPY.safetyHeading[language]}</h3>
                  <p>{SHELTER_PAGE_COPY.safety[language]}</p>
                </div>
              </aside>

              <a className="public-hazard-official-link" href="tel:1784">
                {SHELTER_PAGE_COPY.call[language]}
                <ShelterIcon name="phone" />
              </a>
            </aside>
          </div>
        )}
      </div>
    </section>
  );
}
