import type { FeatureCollection, GeoFeature, Language } from "@/lib/types";

export type PublicLocationSource = "gps" | "address";

export interface PublicMapLocation {
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
  label: string;
  source: PublicLocationSource;
}

export interface PublicAddressSuggestion {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  hasStreetNumber: boolean;
}

interface ArcGisCandidate {
  address?: unknown;
  location?: {
    x?: unknown;
    y?: unknown;
  };
  score?: unknown;
  attributes?: Record<string, unknown>;
}

interface ArcGisResponse {
  candidates?: unknown;
  error?: {
    message?: unknown;
  };
}

interface ParsedAddressSuggestion {
  suggestion: PublicAddressSuggestion;
  score: number;
}

type FetchLike = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

export const PUBLIC_GEOCODER_ATTRIBUTION_URL =
  "https://developers.arcgis.com/rest/geocode/";

const DEFAULT_GEOCODER_URL =
  "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates";
const MAE_SAI_SEARCH_BOUNDS = {
  minLongitude: 99.72,
  minLatitude: 20.12,
  maxLongitude: 100.18,
  maxLatitude: 20.62,
} as const;

export async function searchPublicAddresses(
  query: string,
  language: Language,
  signal?: AbortSignal,
  fetchImpl: FetchLike = fetch,
): Promise<PublicAddressSuggestion[]> {
  const normalized = query.trim().replace(/\s+/gu, " ");
  if (normalized.length < 4) return [];

  const endpoint = configuredGeocoderUrl();
  endpoint.searchParams.set("SingleLine", normalized);
  endpoint.searchParams.set("f", "json");
  endpoint.searchParams.set("countryCode", "THA");
  endpoint.searchParams.set("searchExtent", [
    MAE_SAI_SEARCH_BOUNDS.minLongitude,
    MAE_SAI_SEARCH_BOUNDS.minLatitude,
    MAE_SAI_SEARCH_BOUNDS.maxLongitude,
    MAE_SAI_SEARCH_BOUNDS.maxLatitude,
  ].join(","));
  endpoint.searchParams.set("maxLocations", "6");
  endpoint.searchParams.set("outFields", "Match_addr,Addr_type");
  endpoint.searchParams.set("forStorage", "false");
  endpoint.searchParams.set("outSR", "4326");
  endpoint.searchParams.set("locationType", "rooftop");
  endpoint.searchParams.set("langCode", language === "th" ? "th" : "en");
  const token = process.env.NEXT_PUBLIC_ARCGIS_GEOCODING_TOKEN?.trim();
  if (token) endpoint.searchParams.set("token", token);

  const response = await fetchImpl(endpoint, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Address search failed with status ${response.status}.`);
  }

  const payload = await response.json() as ArcGisResponse;
  if (payload.error) {
    const message = cleanProperty(payload.error.message);
    throw new Error(message || "The address search service rejected the request.");
  }
  if (!Array.isArray(payload.candidates)) return [];

  const suggestions = payload.candidates
    .flatMap((candidate, index) => parseArcGisCandidate(candidate, index))
    .filter(({ suggestion }) => isInsideMaeSaiSearchBounds(
      suggestion.longitude,
      suggestion.latitude,
    ))
    .sort((left, right) => (
      Number(right.suggestion.hasStreetNumber) - Number(left.suggestion.hasStreetNumber)
      || right.score - left.score
    ))
    .map(({ suggestion }) => suggestion);

  const seen = new Set<string>();
  return suggestions.filter((suggestion) => {
    const key = [
      suggestion.label.toLocaleLowerCase(),
      suggestion.latitude.toFixed(6),
      suggestion.longitude.toFixed(6),
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 6);
}

export function findAreaIdForPoint(
  collection: FeatureCollection,
  longitude: number,
  latitude: number,
): string | undefined {
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return undefined;
  const point: Position = [longitude, latitude];
  for (const feature of collection.features) {
    if (!featureContainsPoint(feature, point)) continue;
    const areaId = String(feature.properties.area_id ?? "").trim();
    if (areaId) return areaId;
  }
  return undefined;
}

function configuredGeocoderUrl(): URL {
  const configured = process.env.NEXT_PUBLIC_FLOODGUARD_GEOCODER_URL?.trim();
  try {
    const endpoint = new URL(configured || DEFAULT_GEOCODER_URL);
    if (endpoint.protocol !== "https:" && endpoint.hostname !== "127.0.0.1" && endpoint.hostname !== "localhost") {
      return new URL(DEFAULT_GEOCODER_URL);
    }
    return endpoint;
  } catch {
    return new URL(DEFAULT_GEOCODER_URL);
  }
}

function parseArcGisCandidate(
  candidate: unknown,
  index: number,
): ParsedAddressSuggestion[] {
  if (!candidate || typeof candidate !== "object") return [];
  const result = candidate as ArcGisCandidate;
  const longitude = Number(result.location?.x);
  const latitude = Number(result.location?.y);
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return [];

  const label = cleanProperty(result.address).slice(0, 260);
  if (!label) return [];

  const addressType = cleanProperty(result.attributes?.Addr_type).toLocaleLowerCase();
  const exactAddressTypes = new Set([
    "pointaddress",
    "subaddress",
    "streetaddress",
    "streetaddressext",
  ]);
  const hasLeadingStreetNumber = /^\p{N}+(?:[\s/-]|$)/u.test(label);
  const score = Number(result.score);

  return [{
    suggestion: {
      id: `address-${latitude.toFixed(7)}-${longitude.toFixed(7)}-${index}`,
      label,
      latitude,
      longitude,
      hasStreetNumber: exactAddressTypes.has(addressType) && hasLeadingStreetNumber,
    },
    score: Number.isFinite(score) ? score : 0,
  }];
}

function cleanProperty(value: unknown): string {
  return typeof value === "string" || typeof value === "number"
    ? String(value).trim().replace(/\s+/gu, " ")
    : "";
}

function isInsideMaeSaiSearchBounds(
  longitude: number,
  latitude: number,
): boolean {
  return longitude >= MAE_SAI_SEARCH_BOUNDS.minLongitude
    && longitude <= MAE_SAI_SEARCH_BOUNDS.maxLongitude
    && latitude >= MAE_SAI_SEARCH_BOUNDS.minLatitude
    && latitude <= MAE_SAI_SEARCH_BOUNDS.maxLatitude;
}

type Position = [number, number];
type LinearRing = Position[];
type PolygonCoordinates = LinearRing[];
type MultiPolygonCoordinates = PolygonCoordinates[];

function featureContainsPoint(feature: GeoFeature, point: Position): boolean {
  if (feature.geometry.type === "Polygon") {
    return polygonContainsPoint(feature.geometry.coordinates, point);
  }
  if (feature.geometry.type === "MultiPolygon") {
    if (!Array.isArray(feature.geometry.coordinates)) return false;
    return (feature.geometry.coordinates as MultiPolygonCoordinates)
      .some((polygon) => polygonContainsPoint(polygon, point));
  }
  return false;
}

function polygonContainsPoint(coordinates: unknown, point: Position): boolean {
  if (!Array.isArray(coordinates) || coordinates.length === 0) return false;
  const rings = coordinates as PolygonCoordinates;
  const [outer, ...holes] = rings;
  return isPositionRing(outer)
    && pointInRing(point, outer)
    && !holes.some((hole) => isPositionRing(hole) && pointInRing(point, hole));
}

function isPositionRing(value: unknown): value is LinearRing {
  return Array.isArray(value)
    && value.length >= 3
    && value.every((position) => (
      Array.isArray(position)
      && position.length >= 2
      && Number.isFinite(Number(position[0]))
      && Number.isFinite(Number(position[1]))
    ));
}

function pointInRing([pointX, pointY]: Position, ring: LinearRing): boolean {
  let inside = false;
  for (let current = 0, previous = ring.length - 1; current < ring.length; previous = current++) {
    const [currentX, currentY] = ring[current].map(Number) as Position;
    const [previousX, previousY] = ring[previous].map(Number) as Position;
    if (pointOnSegment(pointX, pointY, previousX, previousY, currentX, currentY)) {
      return true;
    }
    const crosses = (currentY > pointY) !== (previousY > pointY)
      && pointX < ((previousX - currentX) * (pointY - currentY))
        / (previousY - currentY) + currentX;
    if (crosses) inside = !inside;
  }
  return inside;
}

function pointOnSegment(
  pointX: number,
  pointY: number,
  startX: number,
  startY: number,
  endX: number,
  endY: number,
): boolean {
  const cross = (pointY - startY) * (endX - startX)
    - (pointX - startX) * (endY - startY);
  if (Math.abs(cross) > 1e-10) return false;
  return pointX >= Math.min(startX, endX) - 1e-10
    && pointX <= Math.max(startX, endX) + 1e-10
    && pointY >= Math.min(startY, endY) - 1e-10
    && pointY <= Math.max(startY, endY) + 1e-10;
}
