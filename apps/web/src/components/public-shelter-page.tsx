"use client";

import { useEffect, useId, useMemo, useState } from "react";

import type { DatasetMode, PublicPreparednessArea } from "@floodguard/contracts";

import { GeoMap } from "@/components/geo-map";
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
import type { FeatureCollection, Language } from "@/lib/types";

interface PublicShelterPageProps {
  language: Language;
  selectedAreaName: string;
  selectedAreaId: string;
  areas: PublicPreparednessArea[];
  areaFeatures: FeatureCollection;
  datasetMode: DatasetMode;
  plan: HouseholdPlan;
  onNavigatePrepare: () => void;
}

const EMPTY_FEATURES: FeatureCollection = {
  type: "FeatureCollection",
  name: "public_shelter_withheld",
  features: [],
};

/**
 * Worked example the page opens on: a destination a household could have
 * confirmed, with the first two checklist steps already ticked.
 *
 * Ban Pa Daeng School sits in a village inside the Ko Chang planning area and
 * geocodes to the same point from either language, which keeps the example
 * walk local. Schools are the usual evacuation point in Thai districts, but
 * FloodGuard has verified nothing here — the confirmation checkbox and the
 * safety notice still carry that qualification.
 */
const EXAMPLE_DESTINATION: Record<Language, string> = {
  en: "Ban Pa Daeng School, Mae Sai",
  th: "โรงเรียนบ้านป่าแดง แม่สาย",
};

const EXAMPLE_COMPLETED_STEPS: RouteStepId[] = [
  "confirm_destination",
  "confirm_route",
];

type RouteStepId =
  | "confirm_destination"
  | "confirm_route"
  | "prepare_household"
  | "share_plan";
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
}: PublicShelterPageProps) {
  const th = language === "th";
  const destinationInputId = useId();
  const destinationConfirmationId = useId();
  const routeChecklistId = useId();
  const exampleDestination = EXAMPLE_DESTINATION[language];
  const [destinationDraft, setDestinationDraft] = useState(exampleDestination);
  const [selectedDestination, setSelectedDestination] = useState(exampleDestination);
  const [authorityConfirmed, setAuthorityConfirmed] = useState(true);
  const [completedSteps, setCompletedSteps] = useState<Set<RouteStepId>>(
    () => new Set(EXAMPLE_COMPLETED_STEPS),
  );
  const [resolvedPin, setResolvedPin] = useState<{
    destination: string;
    location: PublicMapLocation;
  } | null>(null);

  // Tagged with the destination it belongs to, so a pin for a previous
  // destination is filtered out by derivation rather than cleared in an effect.
  const destinationPin = resolvedPin?.destination === selectedDestination
    ? resolvedPin.location
    : undefined;

  // The pin comes from geocoding whatever destination is confirmed, so the map
  // never shows a coordinate the app invented. Offline it stays absent and the
  // map still shows the real planning-area boundary.
  useEffect(() => {
    if (!selectedDestination) return;
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
  }, [language, selectedDestination]);

  // Straight-line leg from the planning area to the geocoded destination. Both
  // ends come from real geometry, so the distance and bearing below are
  // measured rather than invented.
  const routeLeg = useMemo(() => buildRouteLeg(
    areaCentre(areaFeatures, selectedAreaId),
    destinationPin
      ? { latitude: destinationPin.latitude, longitude: destinationPin.longitude }
      : undefined,
  ), [areaFeatures, destinationPin, selectedAreaId]);

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

    // Routing unavailable: fall back to the measured straight-line leg, and say so.
    if (!routeLeg) return [];
    const heading = COMPASS_LABELS[routeLeg.bearing][language];
    const distance = formatRouteDistance(routeLeg.metres, language);
    const origin = selectedAreaName || (th ? "พื้นที่ที่เลือก" : "the selected area");
    return [
      {
        id: "depart",
        icon: "arrow" as const,
        title: th ? `มุ่งหน้าไป${heading}` : `Head ${heading}`,
        detail: th
          ? `ออกจาก${origin} มุ่งหน้าไปยัง ${selectedDestination}`
          : `Set out from ${origin} towards ${selectedDestination}.`,
      },
      {
        id: "distance",
        icon: "route" as const,
        title: th
          ? `ระยะตรง ${distance} ประมาณ ${routeLeg.minutes} นาที`
          : `${distance} direct, about ${routeLeg.minutes} min`,
        detail: th
          ? "ยังไม่ได้เส้นทางตามถนน นี่คือระยะเส้นตรง เส้นทางเดินจริงจะยาวกว่านี้"
          : "The road-by-road route is unavailable, so this is the straight-line distance. The walking route will be longer.",
      },
      {
        id: "arrive",
        icon: "destination" as const,
        title: th ? `ถึง ${selectedDestination}` : `Arrive at ${selectedDestination}`,
        detail: th
          ? "ยืนยันทางเข้าและว่าจุดหมายเปิดให้บริการก่อนออกเดินทาง"
          : "Confirm the entrance and that the destination is open before you travel.",
      },
    ];
  }, [language, routeLeg, selectedAreaName, selectedDestination, th, walkingRoute]);

  const selectedNeeds = useMemo(
    () => HOUSEHOLD_NEEDS.filter(({ id }) => plan.needs[id]),
    [plan.needs],
  );
  const completedStepCount = completedSteps.size;

  const saveDestination = () => {
    const normalizedDestination = destinationDraft.trim();
    if (!normalizedDestination || !authorityConfirmed) return;
    setSelectedDestination(normalizedDestination);
    setCompletedSteps(new Set());
  };

  const toggleStep = (stepId: RouteStepId) => {
    setCompletedSteps((current) => {
      const next = new Set(current);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  return (
    <section className="public-shelter-page" aria-labelledby="public-shelter-title">
      <header className="public-shelter-page__heading">
        <h1 id="public-shelter-title">{th ? "วางแผนเส้นทางไปยังจุดหมายที่ยืนยันแล้ว" : "Plan a route to a confirmed destination"}</h1>
      </header>

      <section className="public-shelter-profile" aria-labelledby="public-shelter-profile-title">
        <div className="public-shelter-profile__copy">
          <div className="public-shelter-section-heading">
            <ShelterIcon name="house" />
            <h2 id="public-shelter-profile-title">
              {th ? "ข้อมูลครัวเรือน" : "Household profile"}
            </h2>
          </div>
          <p className="public-shelter-profile__summary">
            {selectedNeeds.length > 0
              ? (th ? "ความต้องการที่ควรคำนึงถึงระหว่างเดินทาง" : "Needs to account for while travelling")
              : (th ? "ยังไม่ได้บันทึกความต้องการช่วยเหลือ" : "No support needs recorded")}
          </p>
          {selectedNeeds.length > 0 && (
            <ul className="public-shelter-profile__needs" aria-label={th ? "ความต้องการของครัวเรือน" : "Household needs"}>
              {selectedNeeds.map(({ id }) => (
                <li key={id}>
                  {/* Each need carries its own icon, so the card describes the
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

      <section className="public-shelter-destination" aria-labelledby="public-shelter-destination-title">
        <div className="public-shelter-section-heading">
          <ShelterIcon name="destination" />
          <div>
            <h2 id="public-shelter-destination-title">{th ? "เลือกจุดหมาย" : "Choose a destination"}</h2>
          </div>
        </div>

        <form
          className="public-shelter-destination__form"
          onSubmit={(event) => {
            event.preventDefault();
            saveDestination();
          }}
        >
          <label htmlFor={destinationInputId}>{th ? "ชื่อหรือที่อยู่ของจุดหมาย" : "Destination name or address"}</label>
          <input
            id={destinationInputId}
            autoComplete="off"
            value={destinationDraft}
            onChange={(event) => {
              setDestinationDraft(event.target.value);
              setAuthorityConfirmed(false);
            }}
            placeholder={th ? "กรอกจุดหมายที่ยืนยันแล้ว" : "Enter the confirmed destination"}
            type="text"
          />
          <label className="public-shelter-destination__confirmation" htmlFor={destinationConfirmationId}>
            <input
              id={destinationConfirmationId}
              checked={authorityConfirmed}
              onChange={(event) => setAuthorityConfirmed(event.target.checked)}
              type="checkbox"
            />
            <span>
              {th
                ? "ฉันได้ยืนยันจุดหมายและเส้นทางกับ ปภ. หรือหน่วยงานท้องถิ่นแล้ว"
                : "I confirmed this destination and route with DDPM or a local authority."}
            </span>
          </label>
          <div className="public-shelter-destination__actions">
            <button
              className="public-shelter-primary-action"
              disabled={!destinationDraft.trim() || !authorityConfirmed}
              type="button"
              onClick={saveDestination}
            >
              {th ? "ใช้จุดหมายนี้" : "Use this destination"}
            </button>
            <a className="public-shelter-call-action" href="tel:1784">
              <ShelterIcon name="phone" />
              <span>{th ? "โทร 1784 เพื่อยืนยัน" : "Call 1784 to confirm"}</span>
            </a>
          </div>
        </form>
      </section>

      <section className="public-shelter-route-overview" aria-labelledby="public-shelter-route-title">
        {/*
          A real basemap with the planning-area boundary and a geocoded pin for
          the confirmed destination. It deliberately draws no route line: the
          walking route is computed by Google Maps from "Start Guidance", and
          sketching one here would imply routing FloodGuard has not done.
        */}
        <div className="public-shelter-route-overview__graphic">
          <GeoMap
            areas={areas}
            selectedId={selectedAreaId}
            onSelect={() => {}}
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
            attributions={[]}
            visualPalette="public-risk"
            enableBasemaps
            basemapControlVariant="menu"
            showLegend={false}
            showProvenanceBadge={false}
            showTextAlternative={false}
            showDataAttribution={false}
            audience="public"
            location={destinationPin}
            initialFocus="selection"
            routePath={routePath}
          />
          <p className="sr-only">
            {th
              ? `แผนที่แสดงขอบเขตพื้นที่ ${selectedAreaName || "ที่เลือก"} และหมุดจุดหมาย ${selectedDestination || "ที่ยังไม่ได้เลือก"} ไม่ได้แสดงเส้นทางเดิน`
              : `Map showing the ${selectedAreaName || "selected"} area boundary and a pin for ${selectedDestination || "the destination yet to be selected"}. It does not show a walking route.`}
          </p>
        </div>

        <div className="public-shelter-route-overview__summary">
          <p className="eyebrow">{th ? "จุดหมายที่เลือก" : "Selected destination"}</p>
          <h2 id="public-shelter-route-title">
            {selectedDestination || (th ? "กรอกและยืนยันจุดหมายด้านบน" : "Enter and confirm a destination above")}
          </h2>
          <dl>
            <div>
              <dt>{th ? "พื้นที่วางแผน" : "Planning area"}</dt>
              <dd>{selectedAreaName || (th ? "ไม่ได้เลือกพื้นที่" : "No area selected")}</dd>
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
                    ? `${formatRouteDistance(routeLeg.metres, language)} · ${routeLeg.minutes} ${th ? "นาที" : "min"}`
                    : (th ? "ยังคำนวณไม่ได้" : "Not available yet")}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="public-shelter-directions" aria-labelledby="public-shelter-directions-title">
        <h2 id="public-shelter-directions-title">
          {th ? "เส้นทางทีละขั้น" : "Step-by-step directions"}
        </h2>
        {directions.length > 0 ? (
          <ol className="public-shelter-directions__list">
            {directions.map((step) => (
              <li key={step.id}>
                <span className="public-shelter-directions__icon" aria-hidden="true">
                  <ShelterIcon name={step.icon} />
                </span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="public-shelter-directions__empty">
            {th
              ? "ยืนยันจุดหมายด้านบนเพื่อดูทิศทางและระยะทาง"
              : "Confirm a destination above to see the heading and distance."}
          </p>
        )}
      </section>

      <section className="public-shelter-checklist" aria-labelledby={routeChecklistId}>
        <div className="public-shelter-checklist__heading">
          <div>
            <h2 id={routeChecklistId}>{th ? "รายการตรวจสอบทีละขั้น" : "Step-by-step checklist"}</h2>
          </div>
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

      <aside className="public-shelter-safety" aria-labelledby="public-shelter-safety-title">
        <ShelterIcon name="warning" />
        <div>
          <h2 id="public-shelter-safety-title">{th ? "ข้อควรระวังด้านความปลอดภัย" : "Safety disclaimer"}</h2>
          <p>
            {th
              ? "เส้นทางนี้คำนวณจากแผนที่ถนนของ OpenStreetMap และไม่ทราบว่าจุดใดถูกน้ำท่วมในขณะนี้ โปรดยืนยันว่าจุดหมายเปิดให้บริการ ตรวจสอบสภาพเส้นทางในเวลาที่เดินทาง และปฏิบัติตามคำแนะนำของ ปภ. และหน่วยงานท้องถิ่น ห้ามเดินหรือขับรถลงในน้ำท่วมที่ไหลเชี่ยวหรือลึก"
              : "This route is calculated from the OpenStreetMap road network and does not know which roads are flooded right now. Confirm that the destination is open, check route conditions at the time of travel, and follow DDPM and local-authority instructions. Do not walk or drive into moving or deep floodwater."}
          </p>
        </div>
      </aside>

    </section>
  );
}
