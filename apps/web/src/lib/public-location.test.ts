import { describe, expect, it, vi } from "vitest";

import type { FeatureCollection } from "@/lib/types";

import {
  findAreaIdForPoint,
  searchPublicAddresses,
} from "./public-location";

describe("searchPublicAddresses", () => {
  it("waits for a meaningful query before making a network request", async () => {
    const fetchMock = vi.fn();

    await expect(searchPublicAddresses("12", "en", undefined, fetchMock)).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requests bounded Thailand address suggestions and prioritizes street numbers", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(String(input));
      expect(url.origin).toBe("https://geocode.arcgis.com");
      expect(url.pathname).toBe(
        "/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
      );
      expect(url.searchParams.get("SingleLine")).toBe("123 Phahonyothin Road");
      expect(url.searchParams.get("langCode")).toBe("en");
      expect(url.searchParams.get("countryCode")).toBe("THA");
      expect(url.searchParams.get("searchExtent")).toBe("99.72,20.12,100.18,20.62");
      expect(url.searchParams.get("maxLocations")).toBe("6");
      expect(url.searchParams.get("forStorage")).toBe("false");
      expect(url.searchParams.get("locationType")).toBe("rooftop");
      return new Response(JSON.stringify({
        candidates: [
          {
            address: "Phahonyothin Road, Mae Sai, Chiang Rai, Thailand",
            location: { x: 99.887, y: 20.431 },
            score: 100,
            attributes: { Addr_type: "StreetName" },
          },
          {
            address: "123 Phahonyothin Road, Mae Sai, Chiang Rai 57130, Thailand",
            location: { x: 99.886, y: 20.43 },
            score: 97,
            attributes: { Addr_type: "PointAddress" },
          },
        ],
      }), { status: 200 });
    });

    const results = await searchPublicAddresses(
      "  123   Phahonyothin Road  ",
      "en",
      undefined,
      fetchMock,
    );

    expect(results).toHaveLength(2);
    expect(results[0]).toMatchObject({
      id: "address-20.4300000-99.8860000-1",
      label: "123 Phahonyothin Road, Mae Sai, Chiang Rai 57130, Thailand",
      hasStreetNumber: true,
      latitude: 20.43,
      longitude: 99.886,
    });
  });

  it("rejects invalid, out-of-bounds, and missing-location provider results", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      candidates: [
        {
          address: "Outside Mae Sai",
          location: { x: 101.2, y: 21.2 },
          score: 100,
          attributes: { Addr_type: "PointAddress" },
        },
        {
          address: "Not a point",
          location: null,
          score: 100,
        },
        null,
      ],
    }), { status: 200 }));

    await expect(
      searchPublicAddresses("Mae Sai address", "en", undefined, fetchMock),
    ).resolves.toEqual([]);
  });

  it("requests Thai result labels for Thai searches", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      expect(new URL(String(input)).searchParams.get("langCode")).toBe("th");
      return new Response(JSON.stringify({ candidates: [] }), { status: 200 });
    });

    await searchPublicAddresses("ถนนพหลโยธิน", "th", undefined, fetchMock);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("surfaces provider errors without returning untrusted candidates", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      error: { message: "Invalid request" },
    }), { status: 200 }));

    await expect(
      searchPublicAddresses("117 หมู่ 10 แม่สาย", "th", undefined, fetchMock),
    ).rejects.toThrow("Invalid request");
  });
});

describe("findAreaIdForPoint", () => {
  const areas: FeatureCollection = {
    type: "FeatureCollection",
    name: "areas",
    features: [
      {
        type: "Feature",
        properties: { area_id: "AREA-POLYGON" },
        geometry: {
          type: "Polygon",
          coordinates: [
            [[99, 20], [100, 20], [100, 21], [99, 21], [99, 20]],
            [[99.4, 20.4], [99.6, 20.4], [99.6, 20.6], [99.4, 20.6], [99.4, 20.4]],
          ],
        },
      },
      {
        type: "Feature",
        properties: { area_id: "AREA-MULTI" },
        geometry: {
          type: "MultiPolygon",
          coordinates: [
            [[[101, 20], [102, 20], [102, 21], [101, 21], [101, 20]]],
          ],
        },
      },
    ],
  };

  it("finds polygon and multipolygon areas while respecting holes", () => {
    expect(findAreaIdForPoint(areas, 99.2, 20.2)).toBe("AREA-POLYGON");
    expect(findAreaIdForPoint(areas, 101.5, 20.5)).toBe("AREA-MULTI");
    expect(findAreaIdForPoint(areas, 99.5, 20.5)).toBeUndefined();
    expect(findAreaIdForPoint(areas, 120, 40)).toBeUndefined();
  });
});
