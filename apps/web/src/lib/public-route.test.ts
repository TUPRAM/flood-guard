import { describe, expect, it } from "vitest";

import {
  areaCentre,
  buildRouteLeg,
  compassBearing,
  fetchWalkingRoute,
  formatRouteDistance,
  haversineMetres,
  walkingMinutes,
} from "./public-route";
import type { FeatureCollection } from "./types";

const collection = {
  type: "FeatureCollection",
  name: "areas",
  features: [
    {
      type: "Feature",
      properties: { area_id: "TH570903" },
      geometry: {
        type: "Polygon",
        coordinates: [[
          [99.8, 20.4],
          [99.9, 20.4],
          [99.9, 20.5],
          [99.8, 20.5],
          [99.8, 20.4],
        ]],
      },
    },
  ],
} as unknown as FeatureCollection;

describe("public route geometry", () => {
  it("takes the centre of a planning area's own extent", () => {
    expect(areaCentre(collection, "TH570903")).toEqual({
      latitude: 20.45,
      longitude: 99.85,
    });
  });

  it("returns nothing for an unknown or unset area", () => {
    expect(areaCentre(collection, "TH999999")).toBeUndefined();
    expect(areaCentre(collection, "")).toBeUndefined();
  });

  it("measures distance against a known separation", () => {
    // One degree of latitude is about 111 km anywhere on the globe.
    const metres = haversineMetres(
      { latitude: 20, longitude: 99 },
      { latitude: 21, longitude: 99 },
    );
    expect(metres).toBeGreaterThan(110_500);
    expect(metres).toBeLessThan(111_500);
    expect(haversineMetres(
      { latitude: 20, longitude: 99 },
      { latitude: 20, longitude: 99 },
    )).toBe(0);
  });

  it("names the compass heading between two points", () => {
    const origin = { latitude: 20, longitude: 99 };
    expect(compassBearing(origin, { latitude: 21, longitude: 99 })).toBe("north");
    expect(compassBearing(origin, { latitude: 19, longitude: 99 })).toBe("south");
    expect(compassBearing(origin, { latitude: 20, longitude: 100 })).toBe("east");
    expect(compassBearing(origin, { latitude: 20, longitude: 98 })).toBe("west");
    expect(compassBearing(origin, { latitude: 20.9, longitude: 99.9 })).toBe("north-east");
  });

  it("estimates walking time at the documented pace", () => {
    // 1.3 m/s => 780 m in ten minutes.
    expect(walkingMinutes(780)).toBe(10);
    expect(walkingMinutes(0)).toBe(0);
    // Any real distance rounds up to at least a minute.
    expect(walkingMinutes(5)).toBe(1);
  });

  it("formats distance in metres below a kilometre and kilometres above", () => {
    expect(formatRouteDistance(840, "en")).toBe("840 m");
    expect(formatRouteDistance(1_450, "en")).toBe("1.5 km");
    expect(formatRouteDistance(840, "th")).toBe("840 ม.");
    expect(formatRouteDistance(1_450, "th")).toBe("1.5 กม.");
  });

  it("only builds a leg when both ends are known", () => {
    const from = { latitude: 20.45, longitude: 99.85 };
    const to = { latitude: 20.43, longitude: 99.88 };
    const leg = buildRouteLeg(from, to);

    expect(leg?.metres).toBeGreaterThan(0);
    expect(leg?.bearing).toBe("south-east");
    expect(leg?.minutes).toBeGreaterThan(0);
    expect(buildRouteLeg(undefined, to)).toBeUndefined();
    expect(buildRouteLeg(from, undefined)).toBeUndefined();
  });

  it("parses a walking route into geometry and turns", async () => {
    const payload = {
      code: "Ok",
      routes: [{
        distance: 812.4,
        duration: 640,
        geometry: {
          type: "LineString",
          coordinates: [[99.88, 20.43], [99.882, 20.431], [99.884, 20.433]],
        },
        legs: [{
          steps: [
            { maneuver: { type: "depart" }, name: "Phahonyothin Road", distance: 210 },
            { maneuver: { type: "turn", modifier: "left" }, name: "Soi 4", distance: 400.2 },
            { maneuver: { type: "arrive" }, name: "", distance: 0 },
          ],
        }],
      }],
    };
    const route = await fetchWalkingRoute(
      { latitude: 20.43, longitude: 99.88 },
      { latitude: 20.433, longitude: 99.884 },
      undefined,
      (async () => new Response(JSON.stringify(payload), { status: 200 })) as typeof fetch,
    );

    // Coordinates arrive as [longitude, latitude] and must come back flipped.
    expect(route?.path[0]).toEqual([20.43, 99.88]);
    expect(route?.path).toHaveLength(3);
    expect(route?.metres).toBe(812);
    expect(route?.minutes).toBe(11);
    expect(route?.steps.map((step) => step.maneuver)).toEqual([
      "depart",
      "left",
      "arrive",
    ]);
    expect(route?.steps[1].name).toBe("Soi 4");
    expect(route?.steps[1].metres).toBe(400);
  });

  it("gives up rather than half-parsing an unusable routing answer", async () => {
    const from = { latitude: 20.43, longitude: 99.88 };
    const to = { latitude: 20.433, longitude: 99.884 };
    const respond = (body: unknown, status = 200) => (
      (async () => new Response(JSON.stringify(body), { status })) as typeof fetch
    );

    expect(await fetchWalkingRoute(from, to, undefined, respond({ code: "NoRoute" }))).toBeUndefined();
    expect(await fetchWalkingRoute(from, to, undefined, respond({ code: "Ok" }, 500))).toBeUndefined();
    // A single point is not a line.
    expect(await fetchWalkingRoute(from, to, undefined, respond({
      code: "Ok",
      routes: [{ geometry: { coordinates: [[99.88, 20.43]] }, legs: [] }],
    }))).toBeUndefined();
    // Network failure falls through to the straight-line caller.
    expect(await fetchWalkingRoute(from, to, undefined, (() => {
      throw new Error("offline");
    }) as unknown as typeof fetch)).toBeUndefined();
  });
});
