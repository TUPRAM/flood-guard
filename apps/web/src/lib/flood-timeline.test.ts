import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";

import {
  buildDepthLut,
  CHANNEL_RGBA,
  coverageShare,
  decodeGrayPng,
  districtStats,
  facilitiesInWater,
  formatAge,
  formatLocalStamp,
  formatMoment,
  hourIndex,
  inflateZlib,
  latestObservation,
  lutEquals,
  observationGap,
  paintDepth,
  phaseAt,
  roadState,
  roundLikePython,
  stageAt,
  tFromDate,
  waterCandidates,
  type FacilityProps,
  type GeoCollection,
  type RoadProps,
  type TimelineManifest,
} from "./flood-timeline";

const dir = resolve(import.meta.dirname, "../../public/studies/mae-sai-2024-timeline/r1");
const readJson = <T,>(name: string): T => JSON.parse(readFileSync(resolve(dir, name), "utf8")) as T;
const manifest = readJson<TimelineManifest>("timeline.json");
const roads = readJson<GeoCollection<unknown, RoadProps>>("roads.geojson").features.map((feature) => feature.properties);
const facilities = readJson<GeoCollection<unknown, FacilityProps>>("facilities.geojson").features.map((feature) => feature.properties);

describe("Mae Sai flood timeline logic", () => {
  it("interpolates the assumed stage over the manifest anchors and clamps outside", () => {
    const anchors = manifest.stage_anchors;
    expect(anchors.length).toBeGreaterThanOrEqual(manifest.days.length);
    anchors.slice(1).forEach((anchor, index) => expect(anchor.t).toBeGreaterThan(anchors[index].t));
    manifest.days.forEach((day, index) => expect(stageAt(index + 0.5, anchors)).toBe(day.stage_m));
    anchors.forEach((anchor) => expect(stageAt(anchor.t, anchors)).toBe(anchor.stage_m));
    expect(stageAt(-3, anchors)).toBe(anchors[0].stage_m);
    expect(stageAt(99, anchors)).toBe(anchors.at(-1)!.stage_m);
    expect(stageAt(3, anchors)).toBeCloseTo(3.35, 12);
    expect(tFromDate("2024-09-09T00:00:00+07:00")).toBe(0);
    expect(tFromDate("2024-09-12T12:00:00+07:00")).toBe(3.5);
  });

  it("keeps the river in bank for every hour of 9 September and rises through the night of 10 September", () => {
    const anchors = manifest.stage_anchors;
    for (let hour = 0; hour <= 24; hour += 1) expect(stageAt(hour / 24, anchors), `9 Sep ${hour}:00`).toBe(0);
    const tenth = Array.from({ length: 25 }, (_, hour) => stageAt(1 + hour / 24, anchors));
    tenth.slice(1).forEach((value, index) => expect(value).toBeGreaterThanOrEqual(tenth[index]));
    expect(stageAt(1 + 22 / 24, anchors)).toBeCloseTo(1.5, 5);
    expect(stageAt(2.5, anchors)).toBe(3.2);
  });

  it("quantises the replay clock to whole hours without drifting on float noise", () => {
    expect(hourIndex(0)).toBe(0);
    expect(hourIndex(3.5)).toBe(84);
    expect(hourIndex(84 / 24)).toBe(84);
    expect(hourIndex((84 + 0.99) / 24)).toBe(84);
    expect(hourIndex(7 / 24 - 1e-12)).toBe(7);
    expect(Math.floor((7 / 24 - 1e-12) * 24)).toBe(6); // what a bare floor would show
    expect(formatMoment(83.6 / 24, "en")).toBe(formatMoment(83 / 24, "en"));
  });

  it("reproduces the baked keyframe statistics exactly from histograms, roads and facilities", () => {
    expect(roads).toHaveLength(manifest.vectors.roads.features);
    expect(facilities).toHaveLength(manifest.vectors.facilities.features);
    for (const day of manifest.days) {
      const stats = districtStats(manifest, day.stage_m, roads, facilities);
      expect(stats, day.date).toEqual(day.stats);
      expect(Object.keys(stats.tambon_flooded_km2).sort()).toEqual(Object.keys(day.stats.tambon_flooded_km2).sort());
    }
  });

  it("excludes roads and facilities outside the model grid from every statistic", () => {
    expect(roads.every((road) => typeof road.m === "boolean")).toBe(true);
    expect(facilities.every((facility) => typeof facility.m === "boolean")).toBe(true);
    const outside = roads.filter((road) => !road.m);
    expect(roundLikePython(outside.reduce((sum, road) => sum + road.len, 0) / 1000, 2)).toBe(manifest.roads_not_modelled_km);
    expect(facilities.filter((facility) => facility.m)).toHaveLength(manifest.facilities_count.modelled);
    expect(facilities).toHaveLength(manifest.facilities_count.total);
    // Forcing every unmodelled feature to the lowest HAND must not change any figure.
    const peak = Math.max(...manifest.days.map((day) => day.stage_m));
    const forcedRoads = roads.map((road) => (road.m ? road : { ...road, h: 0 }));
    const forcedFacilities: FacilityProps[] = [...facilities, { id: "outside", type: "school", n: "", t: "TH570905", h: 0, m: false }];
    expect(districtStats(manifest, peak, forcedRoads, forcedFacilities)).toEqual(districtStats(manifest, peak, roads, facilities));
    expect(facilitiesInWater(forcedFacilities, peak).some((entry) => entry.facility.id === "outside")).toBe(false);
  });

  it("lists modelled facilities in water deepest first", () => {
    const peak = Math.max(...manifest.days.map((day) => day.stage_m));
    const wet = facilitiesInWater(facilities, peak);
    const peakDay = manifest.days.find((day) => day.stage_m === peak)!;
    expect(wet).toHaveLength(peakDay.stats.facilities_wet);
    wet.slice(1).forEach((entry, index) => expect(entry.depth).toBeLessThanOrEqual(wet[index].depth));
    expect(wet.every((entry) => entry.depth > 0)).toBe(true);
    expect(facilitiesInWater(facilities, 0)).toEqual([]);
  });

  it("reports subdistrict and district model coverage consistently", () => {
    const tambonIds = Object.keys(manifest.tambon_histograms).sort();
    expect(Object.keys(manifest.tambon_coverage).sort()).toEqual(tambonIds);
    const modelled = Object.values(manifest.tambon_coverage).reduce((sum, item) => sum + item.modelled_km2, 0);
    const total = Object.values(manifest.tambon_coverage).reduce((sum, item) => sum + item.total_km2, 0);
    expect(Math.abs(manifest.model_coverage.modelled_km2 - modelled)).toBeLessThanOrEqual(0.06); // per-tambon values are rounded to 0.01
    expect(Math.abs(manifest.model_coverage.district_km2 - total)).toBeLessThanOrEqual(0.06);
    expect(manifest.model_coverage.reason.length).toBeGreaterThan(10);
    for (const item of Object.values(manifest.tambon_coverage)) {
      expect(coverageShare(item)).toBeGreaterThan(0);
      expect(coverageShare(item)).toBeLessThanOrEqual(1);
    }
    expect(coverageShare(undefined)).toBe(1);
    expect(coverageShare({ modelled_km2: 5, total_km2: 0 })).toBe(1);
  });

  it("classifies road passability at the 0.3 m threshold", () => {
    expect(roadState(null, 3.5)).toBe("dry");
    expect(roadState(1, 1)).toBe("dry");
    expect(roadState(1, 0.5)).toBe("dry");
    expect(roadState(1, 1.1)).toBe("wet");
    expect(roadState(1, 1.3)).toBe("impassable");
    expect(roadState(0, 0.3)).toBe("impassable");
    expect(roadState(0, 0.29)).toBe("wet");
    expect(3.5 - 3.2).toBeLessThan(0.3); // binary noise the rounding must absorb
    expect(roadState(3.2, 3.5)).toBe("impassable");
    expect(roadState(3.2, 3.5, manifest.impassable_depth_m)).toBe("impassable");
  });

  it("keeps dry and never-flooding codes transparent and paints wet codes opaque", () => {
    const lut = buildDepthLut(1, 0.05);
    expect(lut[255]).toBe(0);
    expect(lut[20]).toBe(0); // HAND 1.0 m is not below a 1.0 m stage
    expect(lut[40]).toBe(0);
    expect(lut[0] >>> 24).toBe(CHANNEL_RGBA[3]);
    expect(lut[0] & 255).toBe(CHANNEL_RGBA[0]);
    expect(lut[10] >>> 24).toBeGreaterThan(200);
    expect(lut[19] >>> 24).toBeGreaterThan(200);
    expect(lut[10]).not.toBe(lut[19]); // 0.5 m and 0.05 m fall in different depth classes
    const dry = buildDepthLut(0, 0.05);
    expect(Array.from(dry.subarray(1)).every((value) => value === 0)).toBe(true);
    expect(dry[0]).not.toBe(0);
    expect(lutEquals(buildDepthLut(1.01, 0.05), buildDepthLut(1.04, 0.05))).toBe(true);
    expect(lutEquals(buildDepthLut(1.01, 0.05), buildDepthLut(1.06, 0.05))).toBe(false);
    const reused = new Uint32Array(256).fill(7);
    expect(buildDepthLut(1, 0.05, true, reused)).toBe(reused);
    expect(lutEquals(reused, buildDepthLut(1, 0.05))).toBe(true);
    expect(() => buildDepthLut(1, 0.05, true, new Uint32Array(8))).toThrow();
  });

  it("paints only candidate pixels", () => {
    const codes = Uint8Array.from([0, 5, 200, 255, 30]);
    const candidates = waterCandidates(codes, 3.5, 0.05);
    expect(Array.from(candidates)).toEqual([0, 1, 4]);
    const pixels = new Uint32Array(codes.length);
    paintDepth(codes, candidates, buildDepthLut(1, 0.05), pixels);
    expect(pixels[0]).not.toBe(0);
    expect(pixels[1]).not.toBe(0);
    expect(pixels[2]).toBe(0);
    expect(pixels[3]).toBe(0);
    expect(pixels[4]).toBe(0);
  });

  it("chooses the latest image at or before the moment, never a future one", () => {
    const at = (iso: string, kind: "optical" | "radar") => latestObservation(tFromDate(iso), manifest.observations, kind)?.observation.id;
    expect(at("2024-09-12T12:00:00+07:00", "optical")).toBe("s2-20240905");
    expect(at("2024-09-15T10:57:00+07:00", "optical")).toBe("s2-20240905");
    expect(at("2024-09-15T10:59:00+07:00", "optical")).toBe("s2-20240915");
    expect(at("2024-09-16T06:15:00+07:00", "radar")).toBe("s1-20240906");
    expect(at("2024-09-16T06:17:00+07:00", "radar")).toBe("s1-20240915");
    expect(latestObservation(tFromDate("2024-09-01T00:00:00+07:00"), manifest.observations)).toBeNull();
    const age = latestObservation(3.5, manifest.observations, "optical")!.ageDays;
    expect(age).toBeGreaterThan(6.9);
    expect(formatAge(age, "en")).toBe("7 days before this moment");
  });

  it("finds the imagery gap from the observations and only inside it", () => {
    const sorted = [...manifest.observations].sort((a, b) => tFromDate(a.local) - tFromDate(b.local));
    const gapAt = (t: number) => observationGap(t, manifest.observations);
    const gap = gapAt(3.5)!;
    expect(gap).not.toBeNull();
    const beforeT = tFromDate(gap.before.local);
    const afterT = tFromDate(gap.after.local);
    expect(afterT - beforeT).toBeGreaterThan(1);
    expect(sorted.filter((item) => tFromDate(item.local) > beforeT && tFromDate(item.local) < afterT)).toEqual([]);
    expect(gapAt(0)).toEqual(gap);
    expect(gapAt(afterT - 1 / 24)).toEqual(gap);
    expect(gapAt(afterT)).toBeNull();
    expect(gapAt(afterT + 1 / 24)).toBeNull();
    expect(`${formatLocalStamp(gap.before.local, "en")} → ${formatLocalStamp(gap.after.local, "en")}`).toBe("6 Sep 18:31 ICT → 15 Sep 10:58 ICT");
  });

  it("maps phases and local labels onto the replay clock", () => {
    expect(phaseAt(0.2, manifest.phases).id).toBe("dry");
    expect(phaseAt(1.5, manifest.phases).id).toBe("onset");
    expect(phaseAt(3.99, manifest.phases).id).toBe("peak");
    expect(phaseAt(6.5, manifest.phases).id).toBe("receding");
    expect(phaseAt(10.99, manifest.phases).id).toBe("gone");
    expect(phaseAt(11, manifest.phases).id).toBe("gone");
    expect(phaseAt(8, manifest.phases).label.en).toBe("Mostly receded");
    expect(manifest.days.every((day, index) => phaseAt(index + 0.5, manifest.phases).id === day.phase)).toBe(true);
    expect(formatMoment(3.5, "en")).toBe("Thu 12 Sep 2024 · 12:00 ICT");
    expect(formatMoment(3.5, "th")).toBe("พฤ. 12 ก.ย. 2024 · 12:00 น.");
  });

  it("decodes the HAND code raster losslessly on the manifest grid", async () => {
    const bytes = new Uint8Array(readFileSync(resolve(dir, "hand-codes.png")));
    const raster = await decodeGrayPng(bytes, (data) => new Uint8Array(inflateSync(data)));
    expect([raster.width, raster.height]).toEqual([manifest.hand.width, manifest.hand.height]);
    const counts = new Uint32Array(256);
    for (let index = 0; index < raster.data.length; index += 1) counts[raster.data[index]] += 1;
    expect(counts[0]).toBeGreaterThan(0);
    expect(counts[255]).toBeGreaterThan(0);
    const viaStream = await decodeGrayPng(bytes, inflateZlib);
    expect(Buffer.compare(Buffer.from(viaStream.data), Buffer.from(raster.data))).toBe(0);
  }, 30_000);

  it("rounds like Python, including exact decimal ties", () => {
    expect(roundLikePython(0.0625, 3)).toBe(0.062);
    expect(roundLikePython(0.1875, 3)).toBe(0.188);
    expect(roundLikePython(2.675, 2)).toBe(2.67); // binary value is just below the tie
    expect(roundLikePython(0.0005, 3)).toBe(0.001);
    expect(roundLikePython(12.3456, 2)).toBe(12.35);
  });
});
