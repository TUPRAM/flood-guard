import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";

import {
  namedRoadLengths,
  rankRouteGroups,
  roadImportance,
  ARRIVAL_PENDING_ALPHA,
  ARRIVAL_RAMP,
  arrivalClasses,
  arrivalT,
  assumptionCaveat,
  checkDifference,
  coverageComplete,
  externalChecksByRole,
  isSeasonEnvelopeCheck,
  SEASON_ENVELOPE_ROLE,
  sizeChecks,
  rainAt,
  rainSummary,
  referencesNotIngested,
  smallestFloodedExtent,
  VIIRS_CLASSES,
  viirsDayAt,
  viirsReading,
  manifestRevision,
  tFromLocalDate,
  buildArrivalLut,
  buildDepthLut,
  buildDurationLut,
  CHANNEL_RGBA,
  codeTimings,
  coverageShare,
  decodeGrayPng,
  decodePng,
  districtStats,
  DURATION_CLASSES,
  durationClassIndex,
  EVENT_HOURS,
  facilitiesInWater,
  formatAge,
  formatHourSpan,
  formatHourStamp,
  formatLocalStamp,
  formatMoment,
  handGridFromRaster,
  hatchStripes,
  hourClassIndex,
  hourIndex,
  hourlyStages,
  hoursUnder,
  inflateZlib,
  latestObservation,
  LOW_CONFIDENCE_HATCH,
  lowConfidenceCells,
  lowConfidenceRgba,
  lutEquals,
  manifestAssets,
  manifestDirectory,
  observationGap,
  paintDepth,
  paintLowConfidence,
  phaseAt,
  projectToFrame,
  ROAD_CUT_CLASSES,
  roadCut,
  roadCutClassIndex,
  roadCutGroups,
  roadState,
  roundLikePython,
  peopleInWater,
  peopleInWaterStats,
  cellDepth,
  stageAt,
  tFromDate,
  TIMELINE_END_T,
  TIMELINE_MANIFEST_URL,
  thaiYear,
  waterCandidates,
  type FacilityProps,
  type GeoCollection,
  type LineGeometry,
  type RoadProps,
  type TimelineManifest,
} from "./flood-timeline";
import { findWordingViolations } from "./replay-wording-lint";

// Every fixture path comes from the page's one manifest constant and the hrefs inside that manifest.
const publicRoot = resolve(import.meta.dirname, "../../public");
const publicFile = (href: string) => resolve(publicRoot, href.replace(/^\//, ""));
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(publicFile(href), "utf8")) as T;
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const roadCollection = readJson<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href);
const roads = roadCollection.features.map((feature) => feature.properties);
const facilities = readJson<GeoCollection<unknown, FacilityProps>>(manifest.vectors.facilities.href).features.map((feature) => feature.properties);

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
    expect(stageAt(2.5, anchors)).toBe(3.2);
  });

  it("interpolates over the sub-daily anchors: 10 Sep 18:15 (GISTDA onset) and 11 Sep 02:00", () => {
    const anchors = manifest.stage_anchors;
    const gistda = anchors.find((anchor) => Math.abs(anchor.t - (1 + 18.25 / 24)) < 1e-5)!;
    const surge = anchors.find((anchor) => Math.abs(anchor.t - (2 + 2 / 24)) < 1e-5)!;
    const onsetCheck = sizeChecks(manifest.external_checks).find((check) => check.id.startsWith("gistda"))!;
    // The 18:15 knot is the stage the manifest's GISTDA check reports; the 02:00 knot is the illustrative surge.
    expect(gistda.stage_m).toBe(onsetCheck.model_stage_m);
    expect(surge.stage_m).toBe(2.5);
    expect(tFromDate("2024-09-10T18:15:00+07:00")).toBeCloseTo(gistda.t, 5);
    expect(stageAt(gistda.t, anchors)).toBe(gistda.stage_m);
    expect(stageAt(surge.t, anchors)).toBe(2.5);
    // Between the two knots the stage is the straight line joining them, not the noon keyframes.
    const t = 1 + 22 / 24;
    const expected = gistda.stage_m + ((surge.stage_m - gistda.stage_m) * (t - gistda.t)) / (surge.t - gistda.t);
    expect(stageAt(t, anchors)).toBeCloseTo(expected, 12);
    expect(stageAt(t, anchors)).toBeGreaterThan(gistda.stage_m);
    expect(stageAt(t, anchors)).toBeLessThan(surge.stage_m);
    expect(onsetCheck.model_stage_m).toBe(roundLikePython(stageAt(gistda.t, anchors), 3));
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

  it("reproduces the baked keyframe statistics exactly from histograms, roads (with depth factors) and facilities", () => {
    expect(roads).toHaveLength(manifest.vectors.roads.features);
    expect(facilities).toHaveLength(manifest.vectors.facilities.features);
    expect(roads.every((road) => typeof road.k === "number" && road.k > 0 && road.k <= 1)).toBe(true);
    expect(roads.some((road) => road.k! < 1)).toBe(true);
    for (const day of manifest.days) {
      const stats = districtStats(manifest, day.stage_m, roads, facilities);
      const { access, ...baked } = day.stats;
      expect(access, day.date).toBeDefined();
      expect(stats, day.date).toEqual(baked);
      expect(stats.flooded_km2).toBe(day.stats.flooded_km2);
      expect(stats.tambon_flooded_km2).toEqual(day.stats.tambon_flooded_km2);
      expect([stats.road_km_impassable, stats.road_km_wet, stats.facilities_wet])
        .toEqual([day.stats.road_km_impassable, day.stats.road_km_wet, day.stats.facilities_wet]);
      expect(Object.keys(stats.tambon_flooded_km2).sort()).toEqual(Object.keys(day.stats.tambon_flooded_km2).sort());
    }
  });

  it("counts modelled residents in water from the people-by-code histograms, channel excluded", () => {
    const population = manifest.population!;
    expect(Object.keys(population.tambon_histograms).sort()).toEqual(Object.keys(manifest.tambon_histograms).sort());
    for (const day of manifest.days) {
      const people = peopleInWaterStats(population, day.stage_m, manifest.hand.step_m);
      expect(people.tambon_people_in_water, day.date).toEqual(day.stats.tambon_people_in_water);
      expect(people.people_in_water, day.date).toBe(day.stats.people_in_water);
    }
    const toy = new Array(256).fill(0);
    toy[0] = 1000; // channel: never counted
    toy[1] = 5;
    toy[2] = 7;
    toy[255] = 900; // never floods
    expect(peopleInWater(toy, 0.1, 0.05)).toBe(5); // code 2 sits at exactly 0.1 m: not below the stage
    expect(peopleInWater(toy, 0.11, 0.05)).toBe(12);
    expect(peopleInWater(toy, 99, 0.05)).toBe(12);
    expect(() => peopleInWater([1, 2], 1, 0.05)).toThrow();
    const unosat = sizeChecks(manifest.external_checks).find((check) => check.id.startsWith("unosat"));
    const peak = Math.max(...manifest.days.map((day) => day.stage_m));
    expect(unosat?.model_peak_people_in_water).toBe(peopleInWaterStats(population, peak, manifest.hand.step_m).people_in_water);
    expect(unosat?.model_peak_km2).toBe(districtStats(manifest, peak, roads, facilities).flooded_km2);
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

  it("scales road depth by the piece's depth factor k: impassable on rounded k * (s - h), wet when that depth is above 0", () => {
    expect(roadState(1, 1.9, 0.3, 0.35)).toBe("impassable"); // 0.315 m
    expect(roadState(1, 1.8, 0.3, 0.35)).toBe("wet"); // 0.28 m
    expect(roadState(1, 1.8, 0.3, 1)).toBe("impassable");
    expect(roadState(1, 1.6, 0.3, 0.5)).toBe("impassable"); // 0.5 * 0.6 = 0.3 after rounding
    // Python road_state: round(k * (s - h), 6) > 0. Float noise above HAND that rounds to 0 m is dry, as in Python.
    expect(roadState(1, 1 + 1e-9, 0.3, 0.35)).toBe("dry");
    expect(roadState(2.5, 2.500000559999552, 0.3, 0.35)).toBe("dry"); // 11 Sep 02:00 on the hourly grid
    expect(roadState(2.5, 2.500000559999552, 0.3, 1)).toBe("wet"); // 5.6e-7 m rounds to 1e-6 m
    expect(roadState(1, 1 + 2e-6, 0.3, 0.35)).toBe("wet");
    expect(roadState(1, 1, 0.3, 0.35)).toBe("dry");
    expect(roadState(1, 0.9, 0.3, 0.35)).toBe("dry");
    expect(roadState(null, 9, 0.3, 0.35)).toBe("dry");
  });

  it("matches the Python road rule at every hour of the replay grid (Python-generated fixture)", () => {
    const fixture = JSON.parse(readFileSync(resolve(import.meta.dirname, "__fixtures__/mae-sai-road-state-hourly.json"), "utf8")) as {
      manifest: string; roads_sha256: string; columns: string[]; hours: [number, number, number, number][];
    };
    expect(fixture.manifest).toBe(TIMELINE_MANIFEST_URL);
    expect(fixture.roads_sha256).toBe(manifest.vectors.roads.sha256);
    expect(fixture.columns).toEqual(["hour", "stage_m", "road_km_wet", "road_km_impassable"]);
    const stages = hourlyStages(manifest.stage_anchors);
    expect(fixture.hours).toHaveLength(stages.length);
    for (const [hour, stage, wetKm, impassableKm] of fixture.hours) {
      // The browser samples the same stage as numpy.interp over the manifest knots...
      expect(stages[hour], `hour ${hour}`).toBe(stage);
      // ...and classifies every modelled piece exactly as floodguard.flood_timeline.road_state does.
      const stats = districtStats(manifest, stage, roads, []);
      expect([stats.road_km_wet, stats.road_km_impassable], `hour ${hour}, stage ${stage}`).toEqual([wetKm, impassableKm]);
    }
    // The fixture covers the hours where the earlier browser rule (wet whenever stage > HAND) counted float noise
    // above a piece's HAND as a wet road.
    const looseWetKm = (stage: number) => roundLikePython(roads.filter((road) => road.m && road.h !== null && stage > road.h
      && roadState(road.h, stage, manifest.impassable_depth_m, road.k ?? 1) !== "impassable").reduce((sum, road) => sum + road.len, 0) / 1000, 2);
    const noisy = fixture.hours.filter(([, stage, wetKm]) => looseWetKm(stage) !== wetKm).map(([hour]) => hour);
    expect(noisy).toEqual([50, 55, 68, 116, 128]);
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
    // Thai dates carry the Buddhist Era year with the CE year in brackets.
    expect(formatMoment(3.5, "th")).toBe("พฤ. 12 ก.ย. 2567 (2024) · 12:00 น.");
    expect(thaiYear(2024)).toBe("2567 (2024)");
    // The replay's last position (20 Sep 00:00) is labelled as the end of 19 Sep, the last day it covers.
    expect(formatMoment(TIMELINE_END_T, "en")).toBe("Thu 19 Sep 2024 · end of day (24:00 ICT)");
    expect(formatMoment(TIMELINE_END_T, "th")).toBe("พฤ. 19 ก.ย. 2567 (2024) · สิ้นวัน (24:00 น.)");
    expect(formatMoment(TIMELINE_END_T - 1 / 24, "en")).toBe("Thu 19 Sep 2024 · 23:00 ICT");
  });

  it("decodes the HAND code raster losslessly on the manifest grid", async () => {
    const bytes = new Uint8Array(readFileSync(publicFile(manifest.hand.href)));
    const raster = await decodePng(bytes, (data) => new Uint8Array(inflateSync(data)));
    expect([raster.width, raster.height]).toEqual([manifest.hand.width, manifest.hand.height]);
    const grid = handGridFromRaster(raster, manifest.hand.depth_factor_channel);
    const counts = new Uint32Array(256);
    for (let index = 0; index < grid.codes.length; index += 1) counts[grid.codes[index]] += 1;
    expect(counts[0]).toBeGreaterThan(0);
    expect(counts[255]).toBeGreaterThan(0);
    // From r2 on: RGB with R = effective HAND code and G = round(k * 255), k clipped to [floor, 1].
    expect(raster.channels).toBe(3);
    expect(manifest.hand.depth_factor_channel).toBe("G");
    expect(grid.factors).not.toBeNull();
    const floorByte = Math.round(manifest.hand.depth_factor!.floor * 255);
    let reduced = 0;
    let belowFloor = 0;
    for (let index = 0; index < grid.factors!.length; index += 1) {
      if (grid.codes[index] === manifest.hand.never_code) continue;
      const factor = grid.factors![index];
      if (factor < floorByte - 1) belowFloor += 1;
      if (factor < 255) reduced += 1;
    }
    expect(belowFloor).toBe(0);
    expect(reduced).toBeGreaterThan(0);
    // Wetness depends on the code only; depth scales with k (channel depth = k * stage).
    expect(cellDepth(0, 2, 0.05, 128)).toBeCloseTo((128 / 255) * 2, 12);
    expect(cellDepth(20, 2, 0.05, 128)).toBeCloseTo((128 / 255) * (2 - 1), 12);
    expect(cellDepth(40, 2, 0.05, 128)).toBeNull();
    expect(cellDepth(255, 9, 0.05, 255)).toBeNull();
    const viaStream = await decodePng(bytes, inflateZlib);
    expect(Buffer.compare(Buffer.from(viaStream.data), Buffer.from(raster.data))).toBe(0);
    if (raster.channels === 1) {
      const gray = await decodeGrayPng(bytes, inflateZlib);
      expect(Buffer.compare(Buffer.from(gray.data), Buffer.from(grid.codes))).toBe(0);
    }
  }, 30_000);

  it("decodes the low-confidence flag (B) only when the manifest declares it, and it matches the manifest's share", async () => {
    const bytes = new Uint8Array(readFileSync(publicFile(manifest.hand.href)));
    const raster = await decodePng(bytes, (data) => new Uint8Array(inflateSync(data)));
    expect(manifest.hand.low_confidence_channel).toBe("B");
    expect(manifest.hand.low_confidence?.meaning).toMatch(/reads as wet at almost any stage/);
    const share = manifest.hand.low_confidence_share!;
    expect(share.low_confidence_km2).toBeLessThan(share.peak_flooded_km2);
    // Undeclared: the B values are ignored.
    expect(handGridFromRaster(raster, manifest.hand.depth_factor_channel).lowConfidence).toBeNull();
    const grid = handGridFromRaster(raster, manifest.hand.depth_factor_channel, manifest.hand.low_confidence_channel);
    const flags = grid.lowConfidence!;
    expect(flags).toHaveLength(grid.codes.length);
    // The builder writes 255 or 0 only.
    const blue = new Set<number>();
    for (let index = 0; index < flags.length; index += 1) blue.add(raster.data[index * raster.channels + 2]);
    expect([...blue].sort((a, b) => a - b)).toEqual([0, 255]);
    // Share of the wet out-of-channel cells at the modelled peak that are flagged, close to the manifest's share.
    const peak = manifest.shelters!.method.peak_stage_m;
    const candidates = waterCandidates(grid.codes, Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m)), manifest.hand.step_m);
    const low = lowConfidenceCells(grid.codes, flags, candidates, manifest.hand.channel_code);
    const wetAtPeak = (code: number) => code !== manifest.hand.channel_code && code !== manifest.hand.never_code && code * manifest.hand.step_m < peak;
    let wet = 0;
    let wetLow = 0;
    for (const cell of candidates) if (wetAtPeak(grid.codes[cell])) wet += 1;
    for (const cell of low) {
      expect(grid.codes[cell]).not.toBe(manifest.hand.channel_code);
      if (wetAtPeak(grid.codes[cell])) wetLow += 1;
    }
    expect(low.length).toBeGreaterThan(0);
    expect(Math.abs(wetLow / wet - share.low_confidence_km2 / share.peak_flooded_km2)).toBeLessThan(0.03);
  }, 30_000);

  it("fails closed on an unknown or missing low-confidence channel and hatches flagged wet cells only", () => {
    // 3 x 2 RGB raster: R codes, G factors, B flags.
    const data = new Uint8Array([0, 255, 255, 1, 255, 255, 2, 255, 0, 3, 128, 255, 255, 255, 255, 4, 255, 127]);
    const raster = { width: 3, height: 2, channels: 3, data };
    const grid = handGridFromRaster(raster, "G", "B");
    expect([...grid.lowConfidence!]).toEqual([1, 1, 0, 1, 1, 0]);
    expect(handGridFromRaster(raster, "G", null).lowConfidence).toBeNull();
    expect(() => handGridFromRaster(raster, "G", "A")).toThrow(/Unsupported HAND low_confidence_channel/);
    expect(() => handGridFromRaster({ width: 1, height: 1, channels: 1, data: new Uint8Array([3]) }, null, "B")).toThrow(/no low confidence channel/);
    // Channel cells and cells that never flood are not low-confidence water.
    const candidates = new Uint32Array([0, 1, 2, 3, 5]);
    expect([...lowConfidenceCells(grid.codes, grid.lowConfidence!, candidates, 0)]).toEqual([1, 3]);
    expect(() => lowConfidenceCells(grid.codes, new Uint8Array(2), candidates)).toThrow();
    // Diagonal stripes on the raster grid.
    const stripes = hatchStripes(new Uint32Array([0, 1, 2, 3, 6, 7]), 3, 3, 1);
    expect([...stripes]).toEqual([1, 0, 0, 0, 0, 1]);
    expect(LOW_CONFIDENCE_HATCH.stripe).toBeLessThan(LOW_CONFIDENCE_HATCH.period);
  });

  it("draws low-confidence water paler and hatched, and leaves dry cells transparent", () => {
    const blue: [number, number, number, number] = [8, 81, 156, 230];
    const between = lowConfidenceRgba(blue, false);
    const stripe = lowConfidenceRgba(blue, true);
    expect(lowConfidenceRgba([0, 0, 0, 0], true)).toEqual([0, 0, 0, 0]);
    // Lighter than the original, and the stripe keeps more of the water colour than the gaps between stripes.
    const lightness = (rgba: readonly number[]) => rgba[0] + rgba[1] + rgba[2];
    expect(lightness(between)).toBeGreaterThan(lightness(stripe));
    expect(lightness(stripe)).toBeGreaterThan(lightness(blue));
    expect(between[3]).toBeLessThan(blue[3]);
    expect(stripe[3]).toBe(blue[3]);
    // Desaturated: the channel spread shrinks.
    const spread = (rgba: readonly number[]) => Math.max(rgba[0], rgba[1], rgba[2]) - Math.min(rgba[0], rgba[1], rgba[2]);
    expect(spread(between)).toBeLessThan(spread(blue));
    const pack = (rgba: readonly number[]) => ((rgba[3] << 24) | (rgba[2] << 16) | (rgba[1] << 8) | rgba[0]) >>> 0;
    const pixels = new Uint32Array([pack(blue), 0, pack(blue), pack(blue)]);
    paintLowConfidence(new Uint32Array([0, 1, 2]), new Uint8Array([1, 1, 0]), pixels, true);
    expect(pixels[0]).toBe(pack(stripe));
    expect(pixels[1]).toBe(0);
    expect(pixels[2]).toBe(pack(between));
    expect(pixels[3]).toBe(pack(blue));
    expect(() => paintLowConfidence(new Uint32Array([0]), new Uint8Array(0), pixels)).toThrow();
  });

  it("rounds like Python, including exact decimal ties", () => {
    expect(roundLikePython(0.0625, 3)).toBe(0.062);
    expect(roundLikePython(0.1875, 3)).toBe(0.188);
    expect(roundLikePython(2.675, 2)).toBe(2.67); // binary value is just below the tie
    expect(roundLikePython(0.0005, 3)).toBe(0.001);
    expect(roundLikePython(12.3456, 2)).toBe(12.35);
  });
});

describe("Mae Sai replay manifest wiring", () => {
  it("keeps every asset under the manifest's revision directory with a content hash", () => {
    const directory = manifestDirectory(TIMELINE_MANIFEST_URL);
    expect(TIMELINE_MANIFEST_URL.startsWith(directory)).toBe(true);
    const assets = manifestAssets(manifest);
    for (const href of [manifest.hand.href, ...manifest.layers.map((layer) => layer.href), ...Object.values(manifest.vectors).map((vector) => vector.href)]) {
      expect(assets.map((asset) => asset.href)).toContain(href);
    }
    for (const asset of assets) {
      expect(asset.href.startsWith(directory), asset.href).toBe(true);
      expect(asset.sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(asset.bytes).toBeGreaterThan(0);
    }
    expect(new Set(assets.map((asset) => asset.href)).size).toBe(assets.length);
    // Records nested anywhere are found; malformed ones are ignored.
    const nested = { a: [{ href: "/x", sha256: "a".repeat(64), bytes: 1 }], b: { c: { href: "/y", sha256: "short", bytes: 1 } } };
    expect(manifestAssets(nested)).toEqual([{ href: "/x", sha256: "a".repeat(64), bytes: 1 }]);
  });

  it("names the revision the manifest itself declares", () => {
    expect(manifest.revision).toBe(manifestRevision());
  });
});

describe("Mae Sai external checks and assumption caveats", () => {
  const checks = sizeChecks(manifest.external_checks);

  it("groups checks by the manifest's role: calibration anchor, calibration-informed and independent checks, and the season-envelope comparison", () => {
    const { calibration, informed, independent, envelope } = externalChecksByRole(manifest.external_checks!);
    expect(calibration.map((check) => check.id)).toEqual(["gistda-radarsat2-20240910"]);
    // UNOSAT 3991 was known while the stage keyframes were tuned (owner decision, 30 Sep 2026).
    expect(informed.map((check) => check.id)).toEqual(["unosat-3991"]);
    expect(independent).toEqual([]);
    // The comparison with the season envelope has a group of its own: a scenario, plausibility and not validation.
    expect(envelope.map((check) => check.id)).toEqual(["unosat-4009-season-envelope"]);
    expect(envelope[0].role).toBe(SEASON_ENVELOPE_ROLE);
    expect(isSeasonEnvelopeCheck(envelope[0])).toBe(true);
    expect(checks.some(isSeasonEnvelopeCheck)).toBe(false);
    // Whatever else an entry says, that role is never listed as an independent check, a calibration anchor or a size check.
    const dressed = externalChecksByRole([{ ...checks[1], id: "dressed-up", role: SEASON_ENVELOPE_ROLE } as never]);
    expect([...dressed.calibration, ...dressed.informed, ...dressed.independent]).toEqual([]);
    expect(dressed.envelope.map((check) => check.id)).toEqual(["dressed-up"]);
    // A role the page does not know is never shown as independent.
    const unknown = externalChecksByRole([{ ...checks[0], role: "something_else" as never }]);
    expect([...unknown.calibration, ...unknown.informed, ...unknown.independent, ...unknown.envelope]).toEqual([]);
    expect(calibration[0].observed).toMatch(/time zone not stated; assumed ICT/);
  });

  it("compares UNOSAT's cumulative 13-19 Sep extent with the model over the same window, with the peak for reference", () => {
    const unosat = checks.find((check) => check.id === "unosat-3991")!;
    expect(unosat.model_window).toMatch(/13-19 Sep/);
    // The window's largest modelled extent is at its highest assumed stage, the start of 13 Sep.
    const windowStage = stageAt(tFromLocalDate("2024-09-13"), manifest.stage_anchors);
    expect(unosat.model_stage_m).toBeCloseTo(windowStage, 3);
    const stats = districtStats(manifest, windowStage, [], []);
    expect(unosat.model_km2).toBeCloseTo(stats.flooded_km2, 1);
    expect(unosat.model_people_in_water).toBe(stats.people_in_water);
    const peak = Math.max(...manifest.days.map((day) => day.stats.flooded_km2));
    expect(unosat.model_peak_km2).toBe(peak);
    expect(unosat.model_peak_people_in_water).toBe(Math.max(...manifest.days.map((day) => day.stats.people_in_water ?? 0)));
    expect(unosat.model_km2).toBeLessThan(unosat.model_peak_km2!);
  });

  it("adds a page note only where an assumption leaves out something a reader needs", () => {
    const noted = manifest.assumptions.map((item) => [item, assumptionCaveat(item)] as const).filter(([, caveat]) => caveat !== null);
    expect(noted).toHaveLength(1);
    expect(noted[0][0]).toMatch(/GISTDA/);
    expect(noted[0][1]!.en).toMatch(/does not state a time zone.*11 Sep 01:15 ICT/);
    expect(noted[0][1]!.th).toMatch(/[฀-๿]/);
    // The single-stage wording is gone from this revision's assumptions.
    expect(manifest.assumptions.some((item) => item.startsWith("One stage is applied"))).toBe(false);
  });
});

describe("Mae Sai arrival and time under water (hourly stage samples)", () => {
  const step = manifest.hand.step_m;
  const stages = hourlyStages(manifest.stage_anchors);
  const timings = codeTimings(stages, step, manifest.hand.never_code);

  it("samples the assumed stage at the start of every local hour of the replay", () => {
    expect(stages).toHaveLength(EVENT_HOURS);
    expect(EVENT_HOURS).toBe(264);
    stages.forEach((value, hour) => expect(value).toBe(stageAt(hour / 24, manifest.stage_anchors)));
  });

  it("derives arrival and duration per code as pure functions of the stage curve", () => {
    const toy = Float64Array.from([0, 0.2, 0.6, 1.2, 0.8, 0.3, 0]);
    // Code c floods while stage > c * step (strictly), so HAND 0.6 m is not flooded at a 0.6 m stage.
    expect(arrivalT(0, toy, 0.1)).toBe(1 / 24);
    expect(arrivalT(6, toy, 0.1)).toBe(3 / 24);
    expect(arrivalT(12, toy, 0.1)).toBeNull();
    expect(arrivalT(255, toy, 0.1)).toBeNull();
    expect(hoursUnder(6, toy, 0.1)).toBe(2);
    expect(hoursUnder(2, toy, 0.1)).toBe(4);
    expect(hoursUnder(12, toy, 0.1)).toBe(0);
    expect(hoursUnder(255, toy, 0.1)).toBe(0);
    const table = codeTimings(toy, 0.1);
    expect(table.arrivalHour).toHaveLength(256);
    expect(table.hoursUnder).toHaveLength(256);
    expect(table.arrivalHour[6]).toBe(3);
    expect(table.arrivalHour[12]).toBe(-1);
    expect(table.arrivalHour[255]).toBe(-1);
    expect(table.hoursUnder[2]).toBe(4);
  });

  it("floods lower ground earlier and for longer, and never floods the never code", () => {
    expect(timings.arrivalHour[manifest.hand.never_code]).toBe(-1);
    expect(timings.hoursUnder[manifest.hand.never_code]).toBe(0);
    let previousArrival = -1;
    let previousHours = Infinity;
    for (let code = 1; code < 255; code += 1) {
      const arrival = timings.arrivalHour[code];
      expect(timings.hoursUnder[code]).toBeLessThanOrEqual(previousHours);
      previousHours = timings.hoursUnder[code];
      if (arrival < 0) {
        expect(timings.hoursUnder[code]).toBe(0);
        continue;
      }
      expect(arrival).toBeGreaterThanOrEqual(previousArrival);
      previousArrival = arrival;
      expect(stages[arrival]).toBeGreaterThan(code * step);
      if (arrival > 0) expect(stages[arrival - 1]).toBeLessThanOrEqual(code * step);
      expect(timings.hoursUnder[code]).toBe(Array.from(stages).filter((value) => value > code * step).length);
    }
    // Nothing floods during the dry first day of the replay.
    for (let code = 1; code < 255; code += 1) expect(timings.arrivalHour[code] === -1 || timings.arrivalHour[code] >= 24).toBe(true);
  });

  it("classes arrival hours into the ramp and dims cells that have not flooded yet at the playhead", () => {
    const classes = arrivalClasses(timings.arrivalHour, ARRIVAL_RAMP, manifest.hand.channel_code);
    expect(classes.length).toBeGreaterThan(0);
    expect(classes.length).toBeLessThanOrEqual(ARRIVAL_RAMP.length);
    classes.slice(1).forEach((item, index) => expect(item.from).toBe(classes[index].to + 1));
    const flooded = Array.from(timings.arrivalHour.subarray(1, 255)).filter((hour) => hour >= 0);
    expect(classes[0].from).toBe(Math.min(...flooded));
    expect(classes.at(-1)!.to).toBe(Math.max(...flooded));
    for (const hour of flooded) expect(hourClassIndex(hour, classes)).toBeGreaterThanOrEqual(0);
    expect(arrivalClasses(new Int16Array(256).fill(-1))).toEqual([]);

    const code = timings.arrivalHour.findIndex((hour, index) => index > 0 && index < 255 && hour > 30);
    const arrival = timings.arrivalHour[code];
    const before = buildArrivalLut(timings.arrivalHour, classes, arrival - 1);
    const after = buildArrivalLut(timings.arrivalHour, classes, arrival);
    expect(before[code] >>> 24).toBe(ARRIVAL_PENDING_ALPHA);
    expect(after[code] >>> 24).toBeGreaterThan(200);
    expect(before[code] & 0xffffff).toBe(after[code] & 0xffffff);
    expect(after[255]).toBe(0);
    expect(after[0] & 255).toBe(CHANNEL_RGBA[0]);
    const never = timings.arrivalHour.findIndex((hour, index) => index > 0 && hour < 0);
    if (never > 0) expect(after[never]).toBe(0);
    // Reused buffers are cleared and returned.
    const reused = new Uint32Array(256).fill(9);
    expect(buildArrivalLut(timings.arrivalHour, classes, arrival, true, reused)).toBe(reused);
    expect(lutEquals(reused, after)).toBe(true);
  });

  it("colours hours under water by duration class and leaves dry codes transparent", () => {
    expect(durationClassIndex(0)).toBe(-1);
    expect(durationClassIndex(1)).toBe(0);
    expect(durationClassIndex(5)).toBe(0);
    expect(durationClassIndex(6)).toBe(1);
    expect(durationClassIndex(24)).toBe(2);
    expect(durationClassIndex(500)).toBe(DURATION_CLASSES.length - 1);
    const lut = buildDurationLut(timings.hoursUnder);
    for (let code = 1; code < 256; code += 1) {
      if (timings.hoursUnder[code] === 0) expect(lut[code], `code ${code}`).toBe(0);
      else expect(lut[code] >>> 24, `code ${code}`).toBeGreaterThan(200);
    }
    expect(lut[0] & 255).toBe(CHANNEL_RGBA[0]);
    // No browns or oranges (red well above green, green above blue), so the ramp never reads as the 15 Sep flood mud.
    for (const { rgba: [r, g, b] } of DURATION_CLASSES) expect(r - g > 40 && g >= b, `${r},${g},${b}`).toBe(false);
    expect(formatHourSpan(34, 40, "en")).toBe("10 Sep 10:00–17:00");
    expect(formatHourSpan(46, 50, "en")).toBe("10 Sep 22:00 – 11 Sep 03:00");
    expect(formatHourStamp(46, "th")).toBe("10 ก.ย. 22:00 น.");
  });
});

describe("Mae Sai road cut duration (Keep Routes Open)", () => {
  const stages = hourlyStages(manifest.stage_anchors);

  it("counts impassable hours with the same float-safe threshold as the road state", () => {
    // HAND 3.2 m under a 3.5 m stage is exactly 0.3 m deep, which must count as impassable.
    const toy = Float64Array.from([0, 3.5, 3.5, 3.4, 3.2, 3.6, 0, 0]);
    expect(roadCut(3.2, toy, 0.3)).toEqual({ hours: 3, firstHour: 1, reopenHour: 6 });
    expect(roadCut(null, toy, 0.3)).toEqual({ hours: 0, firstHour: null, reopenHour: null });
    expect(roadCut(0, Float64Array.from([0, 1, 1]), 0.3)).toEqual({ hours: 2, firstHour: 1, reopenHour: null });
    // A depth factor k scales the depth before the threshold.
    expect(roadCut(3.2, toy, 0.3, 0.5).hours).toBe(0);
    for (const road of roads.slice(0, 400)) {
      const cut = roadCut(road.h, stages, manifest.impassable_depth_m, road.k ?? 1);
      const expected = Array.from(stages).filter((stage) => roadState(road.h, stage, manifest.impassable_depth_m, road.k ?? 1) === "impassable").length;
      expect(cut.hours).toBe(expected);
    }
  });

  it("maps hours cut to the five classes", () => {
    expect(ROAD_CUT_CLASSES.map((item) => item.label.en)).toEqual(["Not cut", "< 6 h", "6–24 h", "24–48 h", "≥ 48 h"]);
    expect([0, 1, 5, 6, 23, 24, 47, 48, 200].map(roadCutClassIndex)).toEqual([0, 1, 1, 2, 2, 3, 3, 4, 4]);
  });

  it("lists the longest-cut named routes, modelled pieces only", () => {
    const features = roadCollection.features;
    const cuts = features.map((feature) => roadCut(feature.properties.m ? feature.properties.h : null, stages, manifest.impassable_depth_m, feature.properties.k ?? 1));
    const groups = roadCutGroups(features, cuts, 10);
    expect(groups.length).toBeGreaterThan(0);
    expect(groups.length).toBeLessThanOrEqual(10);
    // Named routes first (all of them when there are ten or fewer), then unnamed class-and-subdistrict groups.
    const named = groups.filter((group) => group.name !== null);
    expect(groups.slice(0, named.length)).toEqual(named);
    const allNamed = roadCutGroups(features, cuts, Infinity).filter((group) => group.name !== null);
    expect(named.length).toBe(Math.min(10, allNamed.length));
    for (const part of [named, groups.slice(named.length)]) {
      part.slice(1).forEach((group, index) => {
        const previous = part[index];
        expect(group.maxHours < previous.maxHours || (group.maxHours === previous.maxHours && group.kmCut <= previous.kmCut)).toBe(true);
      });
    }
    for (const group of groups) {
      expect(group.pieces.length).toBeGreaterThan(0);
      for (const index of group.pieces) {
        const props = features[index].properties;
        expect(props.m).toBe(true);
        expect(cuts[index].hours).toBeGreaterThan(0);
        if (group.name) expect(props.n?.trim()).toBe(group.name);
        else {
          expect(props.n?.trim() || "").toBe("");
          expect(group.key).toBe(`class:${props.c}|${props.t}`);
        }
      }
      expect(group.maxHours).toBe(Math.max(...group.pieces.map((index) => cuts[index].hours)));
      expect(group.firstHour).toBe(Math.min(...group.pieces.map((index) => cuts[index].firstHour!)));
      if (group.reopenHour !== null) expect(group.reopenHour).toBeGreaterThan(group.firstHour);
      expect(group.bounds[0][0]).toBeLessThanOrEqual(group.bounds[1][0]);
      expect(group.bounds[0][1]).toBeLessThanOrEqual(group.bounds[1][1]);
      expect(group.tambons.length).toBeGreaterThan(0);
    }
    // Pieces outside the model never form or join a group, even when forced to the lowest ground.
    const allOutside = features.map((feature) => ({ ...feature, properties: { ...feature.properties, m: false, h: 0 } }));
    const forcedCuts = allOutside.map((feature) => roadCut(feature.properties.h, stages, manifest.impassable_depth_m));
    expect(forcedCuts.some((cut) => cut.hours > 0)).toBe(true);
    expect(roadCutGroups(allOutside, forcedCuts, 10)).toEqual([]);
    expect(() => roadCutGroups(features, cuts.slice(1))).toThrow();
  });

  it("groups unnamed pieces by class and subdistrict and reports still-cut routes", () => {
    const line = (lon: number, lat: number): LineGeometry => ({ type: "LineString", coordinates: [[lon, lat], [lon + 0.01, lat + 0.01]] });
    const features: { geometry: LineGeometry; properties: RoadProps }[] = [
      { geometry: line(99.9, 20.4), properties: { c: "primary", h: 0, m: true, len: 1000, t: "A", n: "Phahonyothin Road" } },
      { geometry: line(99.8, 20.3), properties: { c: "primary", h: 0, m: true, len: 500, t: "B", n: "Phahonyothin Road" } },
      { geometry: line(99.7, 20.2), properties: { c: "residential", h: 0, m: true, len: 250, t: "A" } },
      { geometry: line(99.6, 20.1), properties: { c: "residential", h: 0, m: true, len: 250, t: "B", n: " " } },
      { geometry: line(99.5, 20.0), properties: { c: "trunk", h: 0, m: false, len: 9000, t: "A", n: "Outside" } },
    ];
    const cuts = [
      { hours: 10, firstHour: 30, reopenHour: 40 },
      { hours: 20, firstHour: 28, reopenHour: null },
      { hours: 5, firstHour: 31, reopenHour: 36 },
      { hours: 5, firstHour: 32, reopenHour: 37 },
      { hours: 99, firstHour: 1, reopenHour: null },
    ];
    const groups = roadCutGroups(features, cuts);
    expect(groups.map((group) => group.key)).toEqual(["name:Phahonyothin Road", "class:residential|A", "class:residential|B"]);
    const [named] = groups;
    expect(named).toMatchObject({ name: "Phahonyothin Road", kmCut: 1.5, maxHours: 20, firstHour: 28, reopenHour: null, tambons: ["A", "B"], pieces: [0, 1] });
    expect(named.bounds[0]).toEqual([20.3, 99.8]);
    expect(named.bounds[1][0]).toBeCloseTo(20.41, 9);
    expect(named.bounds[1][1]).toBeCloseTo(99.91, 9);
    expect(groups[1]).toMatchObject({ name: null, classes: ["residential"], kmCut: 0.25, reopenHour: 36 });
  });

  it("ranks named roads and unnamed street groups separately by road importance x longest cut", () => {
    const group = (key: string, name: string | null, classes: string[], maxHours: number, kmCut = 1) => ({
      key, name, classes, maxHours, kmCut, tambons: ["A"], firstHour: 30, reopenHour: 40, pieces: [0], bounds: [[20, 99], [20.1, 99.1]] as [[number, number], [number, number]],
    });
    const groups = [
      group("name:Lane", "Soi 1", ["residential"], 110),
      group("name:Hwy 1", "ถนนพหลโยธิน", ["trunk"], 40),
      group("name:Bypass", "ถนนเลี่ยงเมืองแม่สาย", ["primary"], 30),
      group("class:residential|A", null, ["residential"], 110, 45),
      group("class:tertiary|B", null, ["tertiary"], 90, 2),
      group("class:residential|C", null, ["residential"], 20, 1),
    ];
    expect(roadImportance(["trunk"])).toBeGreaterThan(roadImportance(["primary"]));
    expect(roadImportance(["primary"])).toBeGreaterThan(roadImportance(["residential"]));
    expect(roadImportance(["unknown"])).toBe(1);
    const ranked = rankRouteGroups(groups, { unnamedLimit: 2 });
    // Trunk 4 x 40 h = 160 > lane 1 x 110 h = 110 > primary 3 x 30 h = 90.
    expect(ranked.named.map((item) => item.key)).toEqual(["name:Hwy 1", "name:Lane", "name:Bypass"]);
    // Tertiary 1.5 x 90 h = 135 > residential 1 x 110 h = 110; the third unnamed group is cut off by the limit.
    expect(ranked.unnamed.map((item) => item.key)).toEqual(["class:tertiary|B", "class:residential|A"]);
    expect(rankRouteGroups(groups).unnamed).toHaveLength(3);
    // On the real data every named cut road comes before any street group, and each part is in score order.
    const cuts = roadCollection.features.map((feature) => roadCut(feature.properties.m ? feature.properties.h : null, hourlyStages(manifest.stage_anchors), manifest.impassable_depth_m, feature.properties.k ?? 1));
    const real = rankRouteGroups(roadCutGroups(roadCollection.features, cuts, Infinity), { unnamedLimit: 6 });
    expect(real.named.length).toBeGreaterThan(0);
    expect(real.named.every((item) => item.name !== null)).toBe(true);
    expect(real.unnamed.every((item) => item.name === null)).toBe(true);
    expect(real.unnamed.length).toBeLessThanOrEqual(6);
    for (const part of [real.named, real.unnamed]) {
      const scores = part.map((item) => roadImportance(item.classes) * item.maxHours);
      expect(scores).toEqual([...scores].sort((a, b) => b - a));
    }
    // Total modelled length of each named road gives "km cut" its context.
    const lengths = namedRoadLengths(roadCollection.features);
    for (const item of real.named) expect(lengths.get(item.name!.trim())!).toBeGreaterThanOrEqual(item.kmCut - 1e-9);
  });

  it("projects lon/lat linearly in Web Mercator over the manifest bounds", () => {
    const [[south, west], [north, east]] = manifest.bounds;
    expect(projectToFrame(west, north, manifest.bounds, 800, 600)).toEqual([0, 0]);
    const [x, y] = projectToFrame(east, south, manifest.bounds, 800, 600);
    expect(x).toBeCloseTo(800, 9);
    expect(y).toBeCloseTo(600, 9);
    const [, middle] = projectToFrame(west, (south + north) / 2, manifest.bounds, 800, 600);
    expect(middle).toBeGreaterThan(299);
    expect(middle).toBeLessThan(301);
  });
});

describe("Mae Sai observed evidence: VIIRS daily flood maps and rain gauges", () => {
  const viirs = manifest.viirs_daily!;
  const rainfall = manifest.rainfall!;

  it("lists one hashed VIIRS image per day, timed at its nominal pass on the replay clock", () => {
    expect(viirs.days.length).toBeGreaterThan(0);
    const hrefs = manifestAssets(manifest).map((asset) => asset.href);
    expect(viirs.days.map((day) => day.date)).toEqual([...viirs.days.map((day) => day.date)].sort());
    for (const day of viirs.days) {
      expect(hrefs, day.date).toContain(day.href);
      expect(day.date).toBe(day.nominal_local_time.slice(0, 10));
      expect(day.t, day.date).toBeCloseTo(tFromDate(day.nominal_local_time), 6);
      expect(day.cloud_share).toBeGreaterThanOrEqual(0);
      expect(day.cloud_share).toBeLessThanOrEqual(1);
      expect(day.clear_km2).toBeLessThanOrEqual(manifest.model_coverage.district_km2 + 0.1);
      // The model side of the comparison uses the same stage curve the page interpolates (baked to 0.001 m).
      expect(Math.abs(day.model_stage_m - stageAt(day.t, manifest.stage_anchors)), day.date).toBeLessThanOrEqual(0.0005 + 1e-9);
      expect(day.model_flood_km2_clear).toBeLessThanOrEqual(day.model_flood_km2_district + 1e-9);
    }
  });

  it("decodes every VIIRS image as RGBA on its declared grid, painted only in the legend's colours", async () => {
    const allowed = new Set(VIIRS_CLASSES.map((item) => item.rgba.join(",")));
    const unknown = new Set<string>();
    const seen = new Set<string>();
    for (const day of viirs.days) {
      const raster = await decodePng(new Uint8Array(readFileSync(publicFile(day.href))), (data) => new Uint8Array(inflateSync(data)));
      expect([raster.width, raster.height, raster.channels], day.date).toEqual([day.width, day.height, 4]);
      for (let sample = 0; sample < raster.data.length; sample += 4) {
        if (raster.data[sample + 3] === 0) continue;
        const colour = Array.from(raster.data.subarray(sample, sample + 4)).join(",");
        (allowed.has(colour) ? seen : unknown).add(colour);
      }
    }
    expect([...unknown]).toEqual([]);
    expect(seen.size).toBeGreaterThan(1);
    // Every coloured class is named in the manifest legend.
    for (const item of VIIRS_CLASSES) expect(viirs.legend[item.code], item.code).toBeTruthy();
    expect(viirs.legend.transparent).toBeTruthy();
  });

  it("shows the map of the day at or before the playhead, and none outside the mapped dates", () => {
    const first = viirs.days[0];
    const last = viirs.days.at(-1)!;
    expect(viirsDayAt(first.t - 1 / 24, viirs.days)).toBeNull();
    expect(viirsDayAt(first.t, viirs.days)?.date).toBe(first.date);
    viirs.days.forEach((day, index) => {
      expect(viirsDayAt(day.t + 0.25, viirs.days)?.date).toBe(day.date);
      const next = viirs.days[index + 1];
      if (next) expect(viirsDayAt(next.t - 1 / 24, viirs.days)?.date).toBe(day.date);
    });
    // The last map stays up to the end of its local day, not into the next one.
    expect(viirsDayAt(tFromLocalDate(last.date) + 1 - 1 / 24, viirs.days)?.date).toBe(last.date);
    expect(viirsDayAt(tFromLocalDate(last.date) + 1, viirs.days)).toBeNull();
    // A map is never carried more than a day across a gap.
    const gappy = [{ t: 1.5625, date: "2024-09-10" }, { t: 4.5625, date: "2024-09-13" }];
    expect(viirsDayAt(2.5, gappy)?.date).toBe("2024-09-10");
    expect(viirsDayAt(2.6, gappy)).toBeNull();
    expect(viirsDayAt(4.6, gappy)?.date).toBe("2024-09-13");
    expect(viirsDayAt(1, [])).toBeNull();
  });

  it("reads each day's clear-sky comparison plainly, disagreement included, and never as a validation", () => {
    for (const day of viirs.days) {
      const reading = viirsReading(day);
      expect(reading.en, day.date).not.toMatch(/confirm/i);
      // Validation and accuracy wording is the shared replay wording lint's job, in both languages.
      expect(findWordingViolations(`${reading.en} ${reading.th}`, day.date)).toEqual([]);
      expect(reading.th).toMatch(/[฀-๿]/);
      if (!(day.clear_km2 > 0)) expect(reading.kind).toBe("no_observation");
    }
    // Days on which VIIRS saw no flood water in clear pixels where the model has some are stated as such.
    for (const day of viirs.days.filter((item) => viirsReading(item).kind === "model_only")) {
      expect(viirsReading(day).en).toContain(`VIIRS detected no flood water in the ${day.clear_km2.toFixed(1)} km² of clear sky, where the model places ${day.model_flood_km2_clear.toFixed(1)} km².`);
    }
    for (const day of viirs.days.filter((item) => ["viirs_larger", "viirs_smaller", "similar_size"].includes(viirsReading(item).kind))) {
      expect(viirsReading(day).en).toContain(`VIIRS ${day.viirs_flood_km2_clear.toFixed(1)} km² vs model ${day.model_flood_km2_clear.toFixed(1)} km²`);
    }
    const base = { cloud_share: 0.1, clear_km2: 250 };
    expect(viirsReading({ cloud_share: 1, clear_km2: 0, viirs_flood_km2_clear: 0, model_flood_km2_clear: 0 }).kind).toBe("no_observation");
    expect(viirsReading({ ...base, viirs_flood_km2_clear: 0, model_flood_km2_clear: 0.01 }).kind).toBe("neither");
    expect(viirsReading({ ...base, viirs_flood_km2_clear: 4, model_flood_km2_clear: 0 }).kind).toBe("viirs_only");
    expect(viirsReading({ ...base, viirs_flood_km2_clear: 46, model_flood_km2_clear: 19.5 }).en).toContain("VIIRS shows about 2.4× more");
    expect(viirsReading({ ...base, viirs_flood_km2_clear: 3, model_flood_km2_clear: 8 }).kind).toBe("viirs_smaller");
    expect(viirsReading({ ...base, viirs_flood_km2_clear: 10, model_flood_km2_clear: 9 }).en).toContain("does not show that the locations match");
    expect(viirsReading({ cloud_share: 0.8, clear_km2: 50, viirs_flood_km2_clear: 0, model_flood_km2_clear: 7 }).en)
      .toBe("Mostly cloudy (80% cloud). VIIRS detected no flood water in the 50.0 km² of clear sky, where the model places 7.0 km².");
  });

  it("keeps one hourly rain value per replay hour and gauge, with the baked totals", () => {
    const [[south, west], [north, east]] = manifest.bounds;
    expect(rainfall.stations.length).toBeGreaterThan(0);
    for (const station of rainfall.stations) {
      const series = rainfall.hourly_mm[station.code];
      expect(series, station.code).toHaveLength(EVENT_HOURS);
      const summary = rainSummary(series);
      expect(summary.total_mm, station.code).toBeCloseTo(station.total_mm, 1);
      expect(summary.max_hour_mm).toBe(station.max_hour_mm);
      expect(summary.missing_hours).toBe(station.missing_hours);
      expect(station.lat).toBeGreaterThan(south);
      expect(station.lat).toBeLessThan(north);
      expect(station.lon).toBeGreaterThan(west);
      expect(station.lon).toBeLessThan(east);
    }
    expect(rainfall.note).toMatch(/not flooding/);
    const code = rainfall.stations[0].code;
    expect(rainAt(rainfall, code, 0)).toBe(rainfall.hourly_mm[code][0]);
    for (const hour of [-1, EVENT_HOURS, 1.5]) expect(rainAt(rainfall, code, hour)).toBeNull();
    expect(rainAt(rainfall, "none", 0)).toBeNull();
    expect(rainAt({ hourly_mm: { X: [1, null] } }, "X", 1)).toBeNull();
    expect(rainSummary([1.25, null, 2.5, 0])).toEqual({ total_mm: 3.8, max_hour_mm: 2.5, missing_hours: 1 });
  });

  it("drops a reference once its source is ingested and states full model coverage generically", () => {
    const references = manifest.external_references ?? [];
    const trim = (url: string) => url.replace(/\/+$/, "");
    const ingested = references.filter((reference) => [viirs.source_url, rainfall.source_url].some((url) => trim(url) === trim(reference.url)));
    // An ingested source is dropped whether or not the revision still lists it as a reference.
    const pending = referencesNotIngested(manifest);
    expect(pending).toHaveLength(references.length - ingested.length);
    for (const reference of ingested) expect(pending).not.toContain(reference);
    expect(referencesNotIngested({ external_references: [{ name: "a", url: "https://x.org/" }, { name: "b", url: "https://y.org" }], rainfall: { ...rainfall, source_url: "https://x.org" } }))
      .toEqual([{ name: "b", url: "https://y.org" }]);
    expect(coverageComplete(manifest.model_coverage)).toBe(manifest.model_coverage.modelled_km2 / manifest.model_coverage.district_km2 >= 0.999);
    expect(coverageComplete({ modelled_km2: 305.6, district_km2: 305.6 })).toBe(true);
    expect(coverageComplete({ modelled_km2: 294.4, district_km2: 305.6 })).toBe(false);
  });

  it("finds the smallest non-zero modelled extent, which bounds how close the GISTDA anchor can get", () => {
    const smallest = smallestFloodedExtent(manifest)!;
    expect(smallest.stage_m).toBeGreaterThan(0);
    const justAbove = districtStats(manifest, smallest.stage_m + 1e-6, [], []).flooded_km2;
    expect(smallest.km2).toBeCloseTo(justAbove, 2);
    expect(districtStats(manifest, smallest.stage_m, [], []).flooded_km2).toBe(0);
    const gistda = sizeChecks(manifest.external_checks).find((check) => check.id.startsWith("gistda"))!;
    expect(checkDifference(gistda)).toBeCloseTo((gistda.model_km2 - gistda.reported_km2) / gistda.reported_km2, 12);
    // No stage gives a non-zero extent below the smallest one, so an anchor under it cannot be matched from below.
    if (smallest.km2 > gistda.reported_km2) expect(gistda.model_km2).toBeGreaterThanOrEqual(roundLikePython(smallest.km2, 1));
    expect(checkDifference({ model_km2: 3, reported_km2: 0 })).toBeNull();
    expect(smallestFloodedExtent({ tambon_histograms: { a: new Array(256).fill(0) }, hand: manifest.hand, pixel_area_m2: 100 })).toBeNull();
  });
});
