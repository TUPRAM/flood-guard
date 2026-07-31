import type { FeatureCollection } from "./types";

export interface RoutePoint {
  latitude: number;
  longitude: number;
}

export type CompassDirection =
  | "north"
  | "north-east"
  | "east"
  | "south-east"
  | "south"
  | "south-west"
  | "west"
  | "north-west";

export interface PublicRouteLeg {
  from: RoutePoint;
  to: RoutePoint;
  /** Straight-line distance in metres. Not a road distance. */
  metres: number;
  bearing: CompassDirection;
  /** Estimated walking minutes for the straight-line distance. */
  minutes: number;
}

/**
 * Average walking pace used for the time estimate, in metres per second.
 * 1.3 m/s is the pace commonly used for pedestrian planning; the estimate is
 * always presented as approximate because the straight-line distance is a
 * lower bound on the real walking distance.
 */
export const WALKING_METRES_PER_SECOND = 1.3;

const COMPASS_ORDER: CompassDirection[] = [
  "north",
  "north-east",
  "east",
  "south-east",
  "south",
  "south-west",
  "west",
  "north-west",
];

export const COMPASS_LABELS: Record<CompassDirection, { en: string; th: string }> = {
  "north": { en: "north", th: "ทิศเหนือ" },
  "north-east": { en: "north-east", th: "ทิศตะวันออกเฉียงเหนือ" },
  "east": { en: "east", th: "ทิศตะวันออก" },
  "south-east": { en: "south-east", th: "ทิศตะวันออกเฉียงใต้" },
  "south": { en: "south", th: "ทิศใต้" },
  "south-west": { en: "south-west", th: "ทิศตะวันตกเฉียงใต้" },
  "west": { en: "west", th: "ทิศตะวันตก" },
  "north-west": { en: "north-west", th: "ทิศตะวันตกเฉียงเหนือ" },
};

/**
 * Centre of a planning area's own geometry, used as the route origin. It is the
 * centre of the area's extent, not a household position — FloodGuard never
 * holds one.
 */
export function areaCentre(
  collection: FeatureCollection,
  areaId: string,
): RoutePoint | undefined {
  if (!areaId) return undefined;
  const feature = collection.features.find(
    (candidate) => String(candidate.properties.area_id ?? "") === areaId,
  );
  if (!feature) return undefined;

  let minLatitude = Number.POSITIVE_INFINITY;
  let maxLatitude = Number.NEGATIVE_INFINITY;
  let minLongitude = Number.POSITIVE_INFINITY;
  let maxLongitude = Number.NEGATIVE_INFINITY;
  let seen = false;

  const visit = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (
      value.length >= 2
      && typeof value[0] === "number"
      && typeof value[1] === "number"
    ) {
      const [longitude, latitude] = value as [number, number];
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return;
      seen = true;
      if (latitude < minLatitude) minLatitude = latitude;
      if (latitude > maxLatitude) maxLatitude = latitude;
      if (longitude < minLongitude) minLongitude = longitude;
      if (longitude > maxLongitude) maxLongitude = longitude;
      return;
    }
    for (const entry of value) visit(entry);
  };
  visit((feature.geometry as { coordinates?: unknown }).coordinates);

  if (!seen) return undefined;
  return {
    latitude: (minLatitude + maxLatitude) / 2,
    longitude: (minLongitude + maxLongitude) / 2,
  };
}

/** Great-circle distance in metres. */
export function haversineMetres(from: RoutePoint, to: RoutePoint): number {
  const earthRadius = 6_371_000;
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const deltaLatitude = toRadians(to.latitude - from.latitude);
  const deltaLongitude = toRadians(to.longitude - from.longitude);
  const a = Math.sin(deltaLatitude / 2) ** 2
    + Math.cos(toRadians(from.latitude))
      * Math.cos(toRadians(to.latitude))
      * Math.sin(deltaLongitude / 2) ** 2;
  return Math.round(2 * earthRadius * Math.asin(Math.min(1, Math.sqrt(a))));
}

/** Initial compass bearing from one point to another, to eight points. */
export function compassBearing(from: RoutePoint, to: RoutePoint): CompassDirection {
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const fromLatitude = toRadians(from.latitude);
  const toLatitude = toRadians(to.latitude);
  const deltaLongitude = toRadians(to.longitude - from.longitude);
  const y = Math.sin(deltaLongitude) * Math.cos(toLatitude);
  const x = Math.cos(fromLatitude) * Math.sin(toLatitude)
    - Math.sin(fromLatitude) * Math.cos(toLatitude) * Math.cos(deltaLongitude);
  const degrees = (Math.atan2(y, x) * 180) / Math.PI;
  const normalized = (degrees + 360) % 360;
  const index = Math.round(normalized / 45) % 8;
  return COMPASS_ORDER[index];
}

export function walkingMinutes(metres: number): number {
  if (metres <= 0) return 0;
  return Math.max(1, Math.round(metres / WALKING_METRES_PER_SECOND / 60));
}

export function formatRouteDistance(metres: number, language: "th" | "en"): string {
  if (metres >= 1_000) {
    // Round to a tenth before formatting: toFixed alone reports 1450 m as
    // "1.4 km", because 1.45 sits just below 1.45 in binary floating point.
    const kilometres = (Math.round(metres / 100) / 10).toFixed(1);
    return language === "th" ? `${kilometres} กม.` : `${kilometres} km`;
  }
  const rounded = Math.round(metres / 10) * 10;
  return language === "th" ? `${rounded} ม.` : `${rounded} m`;
}

/**
 * Builds the straight-line leg between a planning area and a destination.
 * Returns undefined when either end is unknown, so the page can say so rather
 * than draw a line it cannot support.
 */
export function buildRouteLeg(
  from: RoutePoint | undefined,
  to: RoutePoint | undefined,
): PublicRouteLeg | undefined {
  if (!from || !to) return undefined;
  const metres = haversineMetres(from, to);
  return {
    from,
    to,
    metres,
    bearing: compassBearing(from, to),
    minutes: walkingMinutes(metres),
  };
}

/* -------------------------------------------------------------------------
   Walking route from OSRM.
   OpenStreetMap hosts a public OSRM instance with a foot profile. It returns
   the road-following geometry and the turn list, so the directions on screen
   are the router's, not text this app invented. It is a shared community
   service with no availability guarantee: every caller must handle failure by
   falling back to the straight-line leg.
   ------------------------------------------------------------------------- */

const OSRM_FOOT_ENDPOINT = "https://routing.openstreetmap.de/routed-foot/route/v1/foot";

export const ROUTING_ATTRIBUTION = "Walking route by OSRM · OpenStreetMap";

export type RouteManeuver =
  | "depart"
  | "arrive"
  | "continue"
  | "left"
  | "slight-left"
  | "sharp-left"
  | "right"
  | "slight-right"
  | "sharp-right"
  | "uturn"
  | "roundabout";

export const MANEUVER_LABELS: Record<RouteManeuver, { en: string; th: string }> = {
  "depart": { en: "Set off", th: "เริ่มออกเดินทาง" },
  "arrive": { en: "Arrive", th: "ถึงจุดหมาย" },
  "continue": { en: "Continue", th: "เดินต่อไป" },
  "left": { en: "Turn left", th: "เลี้ยวซ้าย" },
  "slight-left": { en: "Bear left", th: "ชิดซ้าย" },
  "sharp-left": { en: "Turn sharp left", th: "เลี้ยวซ้ายหักศอก" },
  "right": { en: "Turn right", th: "เลี้ยวขวา" },
  "slight-right": { en: "Bear right", th: "ชิดขวา" },
  "sharp-right": { en: "Turn sharp right", th: "เลี้ยวขวาหักศอก" },
  "uturn": { en: "Make a U-turn", th: "กลับรถ" },
  "roundabout": { en: "Take the roundabout", th: "เข้าวงเวียน" },
};

/** Icon the page draws for each maneuver, so a left turn shows a left arrow. */
export const MANEUVER_ICONS = {
  "depart": "arrow",
  "arrive": "destination",
  "continue": "arrow",
  "left": "turn-left",
  "slight-left": "slight-left",
  "sharp-left": "sharp-left",
  "right": "turn-right",
  "slight-right": "slight-right",
  "sharp-right": "sharp-right",
  "uturn": "uturn",
  "roundabout": "roundabout",
} as const satisfies Record<RouteManeuver, string>;

export interface WalkingRouteStep {
  maneuver: RouteManeuver;
  /** Street or path name from OpenStreetMap; empty when the way is unnamed. */
  name: string;
  metres: number;
}

export interface WalkingRoute {
  /** Road-following geometry as [latitude, longitude] pairs. */
  path: Array<[number, number]>;
  metres: number;
  minutes: number;
  steps: WalkingRouteStep[];
}

function toManeuver(type: unknown, modifier: unknown): RouteManeuver {
  if (type === "depart") return "depart";
  if (type === "arrive") return "arrive";
  if (type === "roundabout" || type === "rotary") return "roundabout";
  switch (modifier) {
    case "left": return "left";
    case "slight left": return "slight-left";
    case "sharp left": return "sharp-left";
    case "right": return "right";
    case "slight right": return "slight-right";
    case "sharp right": return "sharp-right";
    case "uturn": return "uturn";
    default: return "continue";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Requests a walking route. Returns undefined whenever the service is
 * unreachable or answers with anything this app cannot verify, so the caller
 * shows the straight-line fallback instead of a half-parsed route.
 */
export async function fetchWalkingRoute(
  from: RoutePoint,
  to: RoutePoint,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<WalkingRoute | undefined> {
  const coordinates = `${from.longitude},${from.latitude};${to.longitude},${to.latitude}`;
  const url = `${OSRM_FOOT_ENDPOINT}/${coordinates}?overview=full&geometries=geojson&steps=true`;

  let payload: unknown;
  try {
    const response = await fetchImpl(url, { signal });
    if (!response.ok) return undefined;
    payload = await response.json();
  } catch {
    return undefined;
  }

  if (!isRecord(payload) || payload.code !== "Ok") return undefined;
  const route = Array.isArray(payload.routes) ? payload.routes[0] : undefined;
  if (!isRecord(route)) return undefined;

  const geometry = isRecord(route.geometry) ? route.geometry : undefined;
  const rawPath = geometry && Array.isArray(geometry.coordinates)
    ? geometry.coordinates
    : [];
  const path: Array<[number, number]> = [];
  for (const entry of rawPath) {
    if (!Array.isArray(entry) || entry.length < 2) continue;
    const [longitude, latitude] = entry as [number, number];
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
    path.push([latitude, longitude]);
  }
  if (path.length < 2) return undefined;

  const metres = typeof route.distance === "number" && Number.isFinite(route.distance)
    ? Math.round(route.distance)
    : 0;
  const seconds = typeof route.duration === "number" && Number.isFinite(route.duration)
    ? route.duration
    : 0;

  const legs = Array.isArray(route.legs) ? route.legs : [];
  const steps: WalkingRouteStep[] = [];
  for (const leg of legs) {
    if (!isRecord(leg) || !Array.isArray(leg.steps)) continue;
    for (const step of leg.steps) {
      if (!isRecord(step)) continue;
      const maneuver = isRecord(step.maneuver) ? step.maneuver : undefined;
      steps.push({
        maneuver: toManeuver(maneuver?.type, maneuver?.modifier),
        name: typeof step.name === "string" ? step.name : "",
        metres: typeof step.distance === "number" && Number.isFinite(step.distance)
          ? Math.round(step.distance)
          : 0,
      });
    }
  }

  return {
    path,
    metres,
    minutes: seconds > 0 ? Math.max(1, Math.round(seconds / 60)) : walkingMinutes(metres),
    steps,
  };
}
