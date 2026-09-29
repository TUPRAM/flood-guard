import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";

import {
  accessDayStats,
  accessLevelIndex,
  accessLevelStep,
  accessLostSeries,
  accessSnapshot,
  buildCutoffRamp,
  candidateReasons,
  capacityFlag,
  capacityShortfall,
  clampPlanK,
  cutoffWeight,
  equityWhy,
  equityWording,
  evacuationEquityGap,
  floodedHomeMask,
  formatRate,
  formatSignificant3,
  homeWetAt,
  planCoverageSentence,
  scopeTotals,
  NEVER_LOST_CODE,
  NO_BASELINE_CODE,
  nodeLostAccess,
  nodeWithoutAccess,
  osmReference,
  otherCandidates,
  parseAccessNodes,
  planSetId,
  planSites,
  REPORTED_SET_ID,
  countedInReportedSet,
  reportedSetExclusions,
  reportedSiteCounts,
  reportedShelterCheck,
  reportedSiteRole,
  shareOfAchievable,
  siteModelled,
  summarizeAccessSets,
  tambonResidents,
} from "./flood-timeline-evacuation";
import {
  buildDepthLut,
  buildPeopleLut,
  buildResidentsLut,
  CHANNEL_RGBA,
  coverageComplete,
  decodeGrayPng,
  densityCandidates,
  densityClassIndex,
  densityColours,
  densityLegend,
  densityPerHa,
  DENSITY_CLASSES,
  hourlyStages,
  peopleKeys,
  TIMELINE_MANIFEST_URL,
  type TimelineManifest,
} from "./flood-timeline";

const publicRoot = resolve(import.meta.dirname, "../../public");
const publicFile = (href: string) => resolve(publicRoot, href.replace(/^\//, ""));
const manifest = JSON.parse(readFileSync(publicFile(TIMELINE_MANIFEST_URL), "utf8")) as TimelineManifest;
const access = manifest.access!;
const shelters = manifest.shelters!;
const nodes = parseAccessNodes(new Uint8Array(readFileSync(publicFile(access.nodes.href))), access);
const summaries = summarizeAccessSets(nodes, access);
const summaryFor = (id: string) => summaries.find((summary) => summary.id === id)!;

describe("Mae Sai evacuation access (T1 scenario)", () => {
  it("decodes the little-endian node file per the manifest layout", () => {
    expect(nodes.count).toBe(access.nodes.count);
    expect(nodes.setCount).toBe(access.sets.length);
    expect(nodes.cutCodes).toHaveLength(access.sets.length * access.nodes.count);
    const sum = (values: Float32Array) => values.reduce((total, value) => total + value, 0);
    expect(Math.round(sum(nodes.population))).toBe(access.totals.population);
    expect(sum(nodes.vulnerable)).toBeCloseTo(access.totals.vulnerable, 0);
    expect(sum(nodes.population) - sum(nodes.vulnerable)).toBeCloseTo(access.totals.non_vulnerable, 0);
    const [[south, west], [north, east]] = manifest.bounds;
    const invalidNodes: number[] = [];
    for (let node = 0; node < nodes.count; node += 1) {
      const inside = nodes.lon[node] >= west && nodes.lon[node] <= east && nodes.lat[node] >= south && nodes.lat[node] <= north;
      if (nodes.tambonIndex[node] > access.tambons.length || !inside || nodes.vulnerable[node] > nodes.population[node] + 1e-4) invalidNodes.push(node);
    }
    expect(invalidNodes).toEqual([]);
    const invalidCodes = nodes.cutCodes.filter((code) => !(code === NEVER_LOST_CODE || code === NO_BASELINE_CODE || (code >= 1 && code < access.levels.length)));
    expect(invalidCodes).toHaveLength(0);
  });

  it("fails closed on a file or layout that does not match the manifest", () => {
    const bytes = new Uint8Array(readFileSync(publicFile(access.nodes.href)));
    expect(() => parseAccessNodes(bytes.subarray(1), access)).toThrow(/size/);
    const retyped = { ...access, nodes: { ...access.nodes, layout: access.nodes.layout.map((field) => (field.name === "lon" ? { ...field, dtype: "float64" } : field)) } };
    expect(() => parseAccessNodes(bytes, retyped)).toThrow(/lon/);
    const reshaped = { ...access, sets: access.sets.slice(1) };
    expect(() => parseAccessNodes(bytes, reshaped)).toThrow(/shape/);
    const missing = { ...access, nodes: { ...access.nodes, layout: access.nodes.layout.filter((field) => field.name !== "home_k") } };
    expect(() => parseAccessNodes(bytes, missing)).toThrow(/home_k/);
  });

  it("indexes stage levels like the Python lost_at, including float noise at level edges", () => {
    expect(access.levels).toHaveLength(81);
    expect(accessLevelStep(access.levels)).toBe(0.05);
    expect(accessLevelIndex(0, access.levels)).toBe(0);
    expect(accessLevelIndex(0.049, access.levels)).toBe(0);
    expect(accessLevelIndex(0.15, access.levels)).toBe(3); // 0.15 / 0.05 = 2.9999999999999996
    expect(accessLevelIndex(3.5, access.levels)).toBe(70);
    expect(nodeLostAccess(3, 3)).toBe(true);
    expect(nodeLostAccess(4, 3)).toBe(false);
    expect(nodeLostAccess(NEVER_LOST_CODE, 999)).toBe(false);
    expect(nodeLostAccess(NO_BASELINE_CODE, 999)).toBe(false);
    expect(nodeWithoutAccess(NO_BASELINE_CODE, 0)).toBe(true);
    expect(nodeWithoutAccess(5, 4)).toBe(false);
    expect(nodeWithoutAccess(5, 5)).toBe(true);
  });

  it("reproduces the baked access figures at every keyframe for every baked set", () => {
    let compared = 0;
    for (const day of manifest.days) {
      for (const [set, baked] of Object.entries(day.stats.access ?? {})) {
        expect(access.sets).toContain(set);
        expect(accessDayStats(summaryFor(set), day.stage_m, access.levels), `${day.date} ${set}`).toEqual(baked);
        compared += 1;
      }
    }
    expect(compared).toBe(manifest.days.length * 2);
    expect(Object.keys(manifest.days[0].stats.access!)).toEqual([REPORTED_SET_ID, planSetId(shelters.knee_k)]);
  });

  it("answers any stage from cumulative histograms, identical to a node-by-node count", () => {
    for (const set of [REPORTED_SET_ID, planSetId(1), planSetId(shelters.plan.length)]) {
      const summary = summaryFor(set);
      const row = access.sets.indexOf(set) * nodes.count;
      for (const stage of [0, 0.12, 0.9, 1.8, 2.5, 3.5, 5]) {
        const level = accessLevelIndex(stage, access.levels);
        let lost = 0;
        let never = 0;
        const byTambon = new Array(access.tambons.length).fill(0);
        for (let node = 0; node < nodes.count; node += 1) {
          const code = nodes.cutCodes[row + node];
          if (nodeLostAccess(code, level)) {
            lost += nodes.population[node];
            byTambon[nodes.tambonIndex[node] - 1] += nodes.population[node];
          }
          if (code === NO_BASELINE_CODE) never += nodes.population[node];
        }
        const snapshot = accessSnapshot(summary, stage, access.levels);
        expect(snapshot.lost.population).toBeCloseTo(lost, 6);
        expect(snapshot.never.population).toBeCloseTo(never, 6);
        snapshot.lostByTambon.forEach((value, place) => expect(value).toBeCloseTo(byTambon[place], 6));
        expect(snapshot.lost.population + snapshot.never.population).toBeLessThanOrEqual(access.totals.population + 1);
      }
      const series = accessLostSeries(summary, hourlyStages(manifest.stage_anchors), access.levels);
      expect(series).toHaveLength(264);
      expect(series[0]).toBe(0);
      expect(Math.max(...series)).toBeCloseTo(accessSnapshot(summary, 3.5, access.levels).lost.population, 6);
    }
    // Negative stages lose nothing; residents per subdistrict add up to the district.
    expect(accessSnapshot(summaryFor(REPORTED_SET_ID), -1, access.levels).lost.population).toBe(0);
    const residents = tambonResidents(nodes, access.tambons.length);
    expect(Math.round(residents.reduce((total, value) => total + value, 0))).toBe(access.totals.population);
  });

  it("weights cut-off blobs by residents and maps accumulated alpha through a transparent-to-purple ramp", () => {
    expect(cutoffWeight(0)).toBe(0);
    expect(cutoffWeight(-3)).toBe(0);
    expect(cutoffWeight(25)).toBeCloseTo(0.5, 12);
    expect(cutoffWeight(100)).toBe(1);
    expect(cutoffWeight(500)).toBe(1);
    const ramp = buildCutoffRamp();
    expect(ramp).toHaveLength(256);
    expect(ramp[0]).toBe(0);
    const alpha = (value: number) => value >>> 24;
    for (let value = 2; value < 256; value += 1) expect(alpha(ramp[value])).toBeGreaterThanOrEqual(alpha(ramp[value - 1]));
    expect(alpha(ramp[255])).toBe(200); // never fully opaque, so water and residents stay readable underneath
    expect(ramp[255] & 255).toBe(70); // red channel of the darkest stop, little-endian ABGR
    expect(buildCutoffRamp(false)[255] >>> 24).toBe(70);
  });

  it("gives every plan size its own set, and bigger plans never leave more people without access at baseline", () => {
    for (let k = 1; k <= shelters.plan.length; k += 1) expect(access.sets).toContain(planSetId(k));
    let previous = Infinity;
    for (let k = 1; k <= shelters.plan.length; k += 1) {
      const never = accessSnapshot(summaryFor(planSetId(k)), 0, access.levels).never.population;
      expect(never).toBeLessThanOrEqual(previous + 1e-6);
      previous = never;
    }
  });
});

describe("Evacuation Equity Gap (same rules as floodguard.equity)", () => {
  it("computes the ratio of loss rates with Python rounding and wording", () => {
    const normal = evacuationEquityGap({ vulnerableLost: 20, vulnerableTotal: 100, nonVulnerableLost: 10, nonVulnerableTotal: 100 });
    expect(normal).toMatchObject({ status: "ratio", vulnerableRate: 0.2, nonVulnerableRate: 0.1, ratio: 2, band: "higher" });
    expect(normal.interpretation).toBe("Vulnerable residents are 2 times more likely to lose access.");
    const lower = evacuationEquityGap({ vulnerableLost: 34.3, vulnerableTotal: 7151.6, nonVulnerableLost: 5671, nonVulnerableTotal: 74646.9 });
    expect(lower.vulnerableRate).toBe(0.0048);
    expect(lower.nonVulnerableRate).toBe(0.076);
    expect(lower.ratio).toBe(0.063);
    expect(lower.band).toBe("lower");
    expect(lower.interpretation).toBe("Vulnerable residents are 0.063 times as likely to lose access.");
    const similar = evacuationEquityGap({ vulnerableLost: 11, vulnerableTotal: 100, nonVulnerableLost: 10, nonVulnerableTotal: 100 });
    expect(similar).toMatchObject({ ratio: 1.1, band: "similar", interpretation: "Access-loss rates are broadly similar between groups." });
    expect(evacuationEquityGap({ vulnerableLost: 12, vulnerableTotal: 100, nonVulnerableLost: 10, nonVulnerableTotal: 100 }).band).toBe("similar"); // exactly 1.2
    expect(evacuationEquityGap({ vulnerableLost: 8, vulnerableTotal: 100, nonVulnerableLost: 10, nonVulnerableTotal: 100 }).band).toBe("similar"); // exactly 0.8
  });

  it("is undefined for zero denominators and when only vulnerable residents lose access", () => {
    expect(evacuationEquityGap({ vulnerableLost: 0, vulnerableTotal: 0, nonVulnerableLost: 5, nonVulnerableTotal: 50 }))
      .toMatchObject({ status: "no_vulnerable_denominator", ratio: null, vulnerableRate: null, nonVulnerableRate: 0.1 });
    expect(evacuationEquityGap({ vulnerableLost: 5, vulnerableTotal: 50, nonVulnerableLost: 0, nonVulnerableTotal: 0 }))
      .toMatchObject({ status: "no_non_vulnerable_denominator", ratio: null, vulnerableRate: 0.1, nonVulnerableRate: null });
    const onlyVulnerable = evacuationEquityGap({ vulnerableLost: 5, vulnerableTotal: 50, nonVulnerableLost: 0, nonVulnerableTotal: 100 });
    expect(onlyVulnerable).toMatchObject({ status: "undefined_ratio", ratio: null, band: null });
    expect(onlyVulnerable.interpretation).toContain("undefined");
    const none = evacuationEquityGap({ vulnerableLost: 0, vulnerableTotal: 50, nonVulnerableLost: 0, nonVulnerableTotal: 100 });
    expect(none).toMatchObject({ status: "no_loss", ratio: 1 });
    expect(none.interpretation).toContain("No measured access-loss gap");
  });

  it("formats like Python's .3g", () => {
    expect(formatSignificant3(2)).toBe("2");
    expect(formatSignificant3(0.063)).toBe("0.063");
    expect(formatSignificant3(1.25)).toBe("1.25");
    expect(formatSignificant3(12.345)).toBe("12.3");
    expect(formatSignificant3(9.996)).toBe("10");
    expect(formatSignificant3(1234)).toBe("1.23e+03");
    expect(formatSignificant3(0.00001)).toBe("1e-05");
    expect(formatSignificant3(0)).toBe("0");
  });
});

describe("Mae Sai shelter plan and reported shelters", () => {
  it("ranks a nested plan of eligible candidates with a knee at 90% of the achievable coverage", () => {
    const byId = new Map(shelters.candidates.map((candidate) => [candidate.id, candidate]));
    expect(shelters.plan.length).toBeGreaterThan(0);
    expect(shelters.plan.length).toBeLessThanOrEqual(shelters.method.max_plan_sites);
    expect(shelters.candidates.filter((candidate) => candidate.eligible)).toHaveLength(shelters.eligible_count);
    shelters.plan.forEach((entry, index) => {
      expect(byId.get(entry.candidate_id)?.eligible).toBe(true);
      expect(entry.loads).toHaveLength(index + 1);
      if (index > 0) {
        expect(entry.cumulative_share).toBeGreaterThanOrEqual(shelters.plan[index - 1].cumulative_share);
        expect(entry.late_cumulative_share).toBeGreaterThanOrEqual(shelters.plan[index - 1].late_cumulative_share);
      }
    });
    expect(new Set(shelters.plan.map((entry) => entry.candidate_id)).size).toBe(shelters.plan.length);
    const knee = shelters.knee_k;
    expect(shareOfAchievable(shelters.plan, knee)).toBeGreaterThanOrEqual(0.9);
    if (knee > 1) expect(shareOfAchievable(shelters.plan, knee - 1)).toBeLessThan(0.9);
    expect(shareOfAchievable(shelters.plan, shelters.plan.length)).toBe(1);
    expect(shelters.uncoverable_people).toBeLessThan(shelters.demand_people);
  });

  it("assigns loads for the chosen plan size and flags capacity shortfalls", () => {
    const k = shelters.knee_k;
    const sites = planSites(shelters, k);
    expect(sites.map((site) => site.rank)).toEqual(Array.from({ length: k }, (_, index) => index + 1));
    expect(sites.map((site) => site.load)).toEqual(shelters.plan[k - 1].loads);
    expect(sites.map((site) => site.candidate.id)).toEqual(shelters.plan.slice(0, k).map((entry) => entry.candidate_id));
    for (const site of sites) expect(site.shortfall).toBe(site.capacity !== null && site.load > site.capacity);
    expect(planSites(shelters, 1)[0].load).toBe(shelters.plan[0].loads[0]);
    expect(planSites(shelters, 0)).toEqual([]);
    expect(planSites(shelters, 999)).toHaveLength(shelters.plan.length);
    expect(capacityShortfall(200, 130)).toBe(true);
    expect(capacityShortfall(130, 130)).toBe(false);
    expect(capacityShortfall(5000, null)).toBe(false);
    expect(clampPlanK(0, shelters)).toBe(1);
    expect(clampPlanK(99, shelters)).toBe(shelters.plan.length);
    expect(clampPlanK(Number.NaN, shelters)).toBe(shelters.knee_k);
  });

  it("reads each reported shelter's model check, including unlocated ones", () => {
    const byId = new Map(shelters.reported.map((shelter) => [shelter.id, shelter]));
    const statuses = shelters.reported.map((shelter) => reportedShelterCheck(shelter).status);
    expect(statuses).toContain("not_located");
    expect(statuses).toContain("high_ground");
    expect(statuses).toContain("dry");
    // "floods" appears exactly when the manifest flags a located, modelled site as flooding at the modelled peak.
    const flagged = shelters.reported.some((shelter) => shelter.lat !== null && shelter.lon !== null && shelter.model_check?.m && shelter.model_check.floods_at_modelled_peak);
    expect(statuses.includes("floods")).toBe(flagged);
    expect(reportedShelterCheck({ lat: 1, lon: 1, model_check: { h: 1, k: 1, freeboard_m: -0.6, snap_m: 1, high_ground: false, floods_at_modelled_peak: true, m: true } }))
      .toEqual({ status: "floods", freeboard: -0.6 });
    for (const shelter of shelters.reported) {
      const check = reportedShelterCheck(shelter);
      if (shelter.lat === null || shelter.lon === null) expect(check.status).toBe("not_located");
      if (check.status === "floods") expect(shelter.model_check?.floods_at_modelled_peak).toBe(true);
      if (check.status === "dry") expect(check.freeboard).toBeGreaterThanOrEqual(0);
      expect(shelter.sources.length).toBeGreaterThan(0);
      expect(shelter.name_en.length).toBeGreaterThan(0);
      expect(shelter.name_th.length).toBeGreaterThan(0);
    }
    expect(reportedShelterCheck({ lat: 1, lon: 1, model_check: null }).status).toBe("not_located");
    expect(reportedShelterCheck({ lat: 1, lon: 1, model_check: { h: 3, k: 1, freeboard_m: null, snap_m: 1, high_ground: false, floods_at_modelled_peak: false, m: true } }).status).toBe("unchecked");
    expect(reportedShelterCheck({ lat: 1, lon: 1, model_check: { h: null, k: 1, freeboard_m: null, snap_m: 1, high_ground: false, floods_at_modelled_peak: false, m: false } }).status).toBe("not_modelled");
    expect(byId.size).toBe(shelters.reported.length);
    expect(osmReference("OSM way/106085171")).toEqual({ type: "way", id: "106085171", url: "https://www.openstreetmap.org/way/106085171" });
    expect(osmReference("OSM relation/6666702")?.type).toBe("relation");
    expect(osmReference("facility F1")).toBeNull();
  });

  it("takes each reported site's role and access-set membership from the manifest", () => {
    const byId = new Map(shelters.reported.map((shelter) => [shelter.id, shelter]));
    const office = byId.get("R05")!;
    expect(office.role).toBe("relief_command_centre");
    expect(reportedSiteRole(office)).toEqual({ role: "relief_command" });
    expect(office.in_access_set).toBe(false);
    const temple = byId.get("R04")!;
    expect(temple.role).toBe("shelter");
    expect(temple.first_use).toBe("2024-09-21");
    expect(temple.in_access_set).toBe(false);
    expect(reportedSiteRole(byId.get("R01")!)).toEqual({ role: "shelter" });
    // Mapped sites the manifest leaves out of the precomputed reported set; the page names them.
    expect(reportedSetExclusions(shelters).map((shelter) => shelter.id).sort()).toEqual(["R04", "R05", "R19"]);
    const counts = reportedSiteCounts(shelters);
    expect(counts).toEqual({ total: 19, shelters: 18, commandCentres: 1, counted: 12 });
    expect(shelters.reported.filter(countedInReportedSet).every((shelter) => shelter.lat !== null && shelter.in_access_set)).toBe(true);
    for (const shelter of shelters.reported) expect(shelter.access_set_note.length).toBeGreaterThan(0);
    expect(access.sets).toContain(REPORTED_SET_ID);
  });

  it("carries confidence and source timestamps for the scenario figures in the manifest", () => {
    for (const block of [access, shelters]) {
      expect(block.confidence).toBe("low");
      expect(block.confidence_reason.length).toBeGreaterThan(20);
      expect(block.source_timestamp).toMatch(/2026-07-09/);
    }
    expect(access.source_timestamp).toMatch(/WorldPop 2020/);
    expect(shelters.reported_status).toMatch(/not an official register/);
    expect(shelters.reported_compiled).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(shelters.reported_access_set_rule).toMatch(/command centre/);
  });

  it("marks shelter sites outside the terrain model from the manifest's m flag", () => {
    const outside = shelters.candidates.filter((candidate) => !siteModelled(candidate)).map((candidate) => candidate.id).sort();
    // The model flag and the screening reason agree, and (with both DEM tiles in r3) the only unmodelled sites are
    // those outside the replay grid itself.
    expect(outside.length).toBeGreaterThan(0);
    expect(outside).toEqual(shelters.candidates.filter((candidate) => candidate.ineligible_reasons.includes("outside_model")).map((candidate) => candidate.id).sort());
    const [[south, west], [north, east]] = manifest.bounds;
    const inGrid = (candidate: { lat: number; lon: number }) => candidate.lat >= south && candidate.lat <= north && candidate.lon >= west && candidate.lon <= east;
    if (coverageComplete(manifest.model_coverage)) {
      expect(shelters.candidates.filter((candidate) => !inGrid(candidate)).map((candidate) => candidate.id).sort()).toEqual(outside);
    }
    for (const candidate of shelters.candidates.filter((item) => outside.includes(item.id))) {
      expect(candidate.h).toBeNull();
      expect(candidate.high_ground).toBe(false);
      expect(candidate.eligible).toBe(false);
      const reasons = candidateReasons(candidate);
      expect(reasons).toContain("outside_model");
      expect(reasons).not.toContain("floods_or_under_freeboard_at_peak");
    }
    const modelled = shelters.candidates.find((candidate) => siteModelled(candidate) && candidate.ineligible_reasons.length > 0)!;
    expect(candidateReasons(modelled)).toEqual(modelled.ineligible_reasons);
    expect(candidateReasons({ eligible: true, ineligible_reasons: [] })).toEqual([]);
    for (const shelter of shelters.reported) {
      if (shelter.model_check) expect(shelter.model_check.m).toBe(true);
    }
  });

  it("lists every candidate outside the first k plan sites, split by eligibility", () => {
    for (const k of [1, shelters.knee_k, shelters.plan.length]) {
      const { eligible, ineligible } = otherCandidates(shelters, k);
      expect(eligible.length + ineligible.length + k).toBe(shelters.candidates.length);
      expect(eligible.every((candidate) => candidate.eligible)).toBe(true);
      expect(ineligible.every((candidate) => !candidate.eligible)).toBe(true);
      expect(eligible.length).toBe(shelters.eligible_count - k);
    }
  });
});

describe("Mae Sai residents on the water grid", () => {
  it("decodes density codes back to people per hectare on the log scale", () => {
    const max = manifest.population!.max_per_ha;
    expect(densityPerHa(0, max)).toBe(0);
    expect(densityPerHa(254, max)).toBeCloseTo(max, 9);
    for (const perHa of [0.5, 2, 7, 15, 30]) {
      const code = Math.round((254 * Math.log1p(perHa)) / Math.log1p(max));
      expect(Math.abs(densityPerHa(code, max) - perHa) / perHa).toBeLessThan(0.02);
    }
    expect(densityClassIndex(0)).toBe(-1);
    expect(densityClassIndex(1)).toBe(0);
    expect(densityClassIndex(2)).toBe(1);
    expect(densityClassIndex(25)).toBe(DENSITY_CLASSES.length - 1);
    const legend = densityLegend(max);
    expect(legend.at(-1)!.max).toBe(max);
    expect(densityLegend(4)).toHaveLength(2);
  });

  it("paints wet cells by residents' density and leaves dry cells transparent", async () => {
    const bytes = new Uint8Array(readFileSync(publicFile(manifest.population!.href)));
    const raster = await decodeGrayPng(bytes, (data) => new Uint8Array(inflateSync(data)));
    expect([raster.width, raster.height]).toEqual([manifest.hand.width, manifest.hand.height]);
    let inhabited = 0;
    let maxCode = 0;
    for (const code of raster.data) {
      if (code > maxCode) maxCode = code;
      if (code > 0) inhabited += 1;
    }
    expect(maxCode).toBeLessThanOrEqual(254);
    expect(inhabited).toBeGreaterThan(0);
    expect(densityCandidates(raster.data)).toHaveLength(inhabited);

    const colours = densityColours(manifest.population!.max_per_ha);
    expect(colours[0]).toBe(0);
    const step = manifest.hand.step_m;
    const lut = buildPeopleLut(1, step, colours);
    const depth = buildDepthLut(1, step);
    const key = (hand: number, density: number) => hand | (density << 8);
    for (const hand of [1, 10, 19, 20, 40, 254, 255]) {
      const wet = depth[hand] !== 0;
      expect(lut[key(hand, 200)] !== 0, `code ${hand}`).toBe(wet);
      if (wet) {
        expect(lut[key(hand, 200)]).toBe(colours[200]);
        expect(lut[key(hand, 0)]).not.toBe(0); // wet without residents stays faintly visible
        expect(lut[key(hand, 0)]).not.toBe(colours[200]);
      }
    }
    expect(lut[key(0, 77)] & 255).toBe(CHANNEL_RGBA[0]);
    const reused = new Uint32Array(65_536).fill(3);
    expect(buildPeopleLut(0, step, colours, true, reused)).toBe(reused);
    expect(reused[key(1, 200)]).toBe(0);
    const residents = buildResidentsLut(colours);
    expect(residents[0]).toBe(0);
    expect(residents[200]).toBe(colours[200]);
    expect(Array.from(peopleKeys(Uint8Array.from([3, 0]), Uint8Array.from([2, 9])))).toEqual([3 | (2 << 8), 9 << 8]);
    expect(() => peopleKeys(Uint8Array.from([1]), Uint8Array.from([1, 2]))).toThrow();
  }, 30_000);
});

describe("Access population scope: like-with-like comparison with the ranked plan", () => {
  const peakStage = shelters.method.peak_stage_m;
  const { step_m: step, channel_code: channel, never_code: never } = manifest.hand;
  const mask = floodedHomeMask(nodes, peakStage, step, channel, never);
  const flooded = summarizeAccessSets(nodes, access, mask);

  it("reads a home as wet with the builder's rule: channel homes as soon as the stage rises, never-code homes never", () => {
    expect(homeWetAt(0, 0, step)).toBe(false);
    expect(homeWetAt(0, 0.01, step)).toBe(true);
    expect(homeWetAt(20, 1.0, step)).toBe(false); // 20 * 0.05 = 1.0 is not below the stage
    expect(homeWetAt(20, 1.01, step)).toBe(true);
    expect(homeWetAt(255, 99, step)).toBe(false);
    expect(homeWetAt(7, 1, 0.05, 7, 255)).toBe(true); // a custom channel code
  });

  it("counts the residents whose homes flood at the modelled peak, which is the plan's demand", () => {
    const scoped = scopeTotals(nodes, mask);
    expect(scoped.population).toBeCloseTo(shelters.demand_people, -1);
    expect(Math.abs(scoped.population - shelters.demand_people)).toBeLessThan(1);
    expect(scoped.vulnerable + scoped.nonVulnerable).toBeCloseTo(scoped.population, 6);
    const all = scopeTotals(nodes);
    expect(Math.round(all.population)).toBe(access.totals.population);
    expect(scoped.population).toBeLessThan(all.population);
    expect(() => summarizeAccessSets(nodes, access, new Uint8Array(3))).toThrow(/every access node/);
  });

  it("before the flood, residents out of reach of plan k plus the plan's coverage add up to the demand", () => {
    // The plan covers flooded-home residents who can walk to a site on normal roads; the scoped card counts the same people.
    for (let k = 1; k <= shelters.plan.length; k += 1) {
      const summary = flooded[access.sets.indexOf(planSetId(k))];
      const dry = accessSnapshot(summary, 0, access.levels);
      expect(dry.lost.population).toBe(0);
      expect(dry.never.population + shelters.plan[k - 1].cumulative_demand).toBeCloseTo(shelters.demand_people, -1);
    }
  });

  it("answers the scoped figures from histograms exactly as a node-by-node count of the masked nodes", () => {
    const setIndex = access.sets.indexOf(REPORTED_SET_ID);
    for (const stage of [0.5, 2.0, peakStage]) {
      const level = accessLevelIndex(stage, access.levels);
      let lost = 0;
      let without = 0;
      for (let node = 0; node < nodes.count; node += 1) {
        if (!mask[node]) continue;
        const code = nodes.cutCodes[setIndex * nodes.count + node];
        if (nodeLostAccess(code, level)) lost += nodes.population[node];
        if (nodeWithoutAccess(code, level)) without += nodes.population[node];
      }
      const snapshot = accessSnapshot(flooded[setIndex], stage, access.levels);
      expect(snapshot.lost.population).toBeCloseTo(lost, 3);
      expect(snapshot.lost.population + snapshot.never.population).toBeCloseTo(without, 3);
    }
    const residents = tambonResidents(nodes, access.tambons.length, mask);
    expect(residents.reduce((sum, value) => sum + value, 0)).toBeCloseTo(scopeTotals(nodes, mask).population, 3);
  });
});

describe("Evacuation Equity Gap wording on the page", () => {
  const gap = (vulnerableLost: number, vulnerableTotal: number, nonVulnerableLost: number, nonVulnerableTotal: number) =>
    evacuationEquityGap({ vulnerableLost, vulnerableTotal, nonVulnerableLost, nonVulnerableTotal });

  it("says '— (no one has lost access at this replay hour)' when both loss rates are zero, never a parity ratio", () => {
    const none = equityWording(gap(0, 100, 0, 1000), "en");
    expect(none).toEqual({ value: "— (no one has lost access at this replay hour)", sentence: "" });
    expect(equityWording(gap(0, 100, 0, 1000), "th").value).toBe("— (ไม่มีผู้สูญเสียการเข้าถึง ณ ชั่วโมงนี้)");
  });

  it("states the ratio to two decimals and compares the two rates in plain words", () => {
    const lower = equityWording(gap(1, 100, 50, 1000), "en");
    expect(lower.value).toBe("0.20");
    expect(lower.sentence).toBe("Proxy-vulnerable residents are about 5.0× less likely to lose access (1.00% vs 5.00%).");
    const higher = equityWording(gap(10, 100, 20, 1000), "en");
    expect(higher.value).toBe("5.00");
    expect(higher.sentence).toBe("Proxy-vulnerable residents are about 5.0× more likely to lose access (10.00% vs 2.00%).");
    const far = equityWording(gap(18, 10_000, 960, 10_000), "en");
    expect(far.value).toBe("0.02");
    expect(far.sentence).toBe("Proxy-vulnerable residents are about 53× less likely to lose access (0.18% vs 9.60%).");
    const similar = equityWording(gap(10, 100, 100, 1000), "en");
    expect(similar.value).toBe("1.00");
    expect(similar.sentence).toContain("about as likely as everyone else");
    for (const value of [lower.value, higher.value, far.value, similar.value]) expect(value).toMatch(/^\d+\.\d{2}$/);
    expect(formatRate(0.0018)).toBe("0.18%");
    expect(equityWording(gap(1, 100, 50, 1000), "th").sentence).toContain("น้อยกว่าประมาณ 5.0 เท่า (1.00% เทียบกับ 5.00%)");
  });

  it("handles no vulnerable loss, only vulnerable loss and empty groups without a misleading number", () => {
    const zero = equityWording(gap(0, 100, 50, 1000), "en");
    expect(zero.value).toBe("0.00");
    expect(zero.sentence).toBe("No proxy-vulnerable resident has lost access, against 5.00% of everyone else.");
    const only = equityWording(gap(5, 100, 0, 1000), "en");
    expect(only.value).toBe("undefined");
    expect(only.sentence).toContain("so the ratio cannot be computed");
    expect(equityWording(gap(0, 0, 5, 1000), "en").value).toBe("—");
    expect(equityWording(gap(1, 100, 0, 0), "en").value).toBe("—");
  });

  it("explains why the proxy points this way only when proxy-vulnerable residents are less affected", () => {
    expect(equityWhy(gap(1, 100, 50, 1000), "en")).toContain("not who is more vulnerable");
    expect(equityWhy(gap(1, 100, 50, 1000), "th")).toMatch(/[฀-๿]/);
    expect(equityWhy(gap(10, 100, 20, 1000), "en")).toBeNull();
    expect(equityWhy(gap(0, 100, 0, 1000), "en")).toBeNull();
  });
});

describe("Plan-size sentence and capacity flags", () => {
  it("states what a plan of k sites covers, pre-emptive and late, from the ranked plan", () => {
    const people = (value: number) => Math.round(value).toLocaleString("en-US");
    for (const k of [1, 3, shelters.knee_k, shelters.plan.length]) {
      const entry = shelters.plan[k - 1];
      expect(planCoverageSentence(shelters, k, "en")).toBe(
        `k = ${k}: ${k} site${k === 1 ? "" : "s"} cover${k === 1 ? "s" : ""} ${people(entry.cumulative_demand)} of ${people(shelters.demand_people)} residents whose homes flood (${Math.round(entry.cumulative_share * 100)}%) · late evacuation ${Math.round(entry.late_cumulative_share * 100)}%`,
      );
    }
    expect(planCoverageSentence(shelters, 99, "en")).toBe(planCoverageSentence(shelters, shelters.plan.length, "en"));
    expect(planCoverageSentence(shelters, 3, "th")).toContain(`k = 3: ที่พักพิง 3 แห่งครอบคลุม`);
    expect(planCoverageSentence({ plan: [], demand_people: 0 }, 1, "en")).toBe("");
  });

  it("flags sites whose capacity is unknown or far below the residents assigned", () => {
    expect(capacityFlag({ load: 500, capacity: null })).toBe("unknown");
    expect(capacityFlag({ load: 1782, capacity: 41 })).toBe("far_below");
    expect(capacityFlag({ load: 80, capacity: 40 })).toBe("far_below");
    expect(capacityFlag({ load: 79, capacity: 40 })).toBeNull();
    expect(capacityFlag({ load: 10, capacity: 400 })).toBeNull();
    const flagged = planSites(shelters, shelters.plan.length).filter((site) => capacityFlag(site) !== null);
    for (const site of flagged) expect(site.capacity === null || site.load >= 2 * site.capacity).toBe(true);
  });
});
