import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { districtStats, TIMELINE_MANIFEST_URL, type GeoCollection, type LineGeometry, type RoadProps, type TimelineManifest } from "./flood-timeline";
import { parseAccessNodes, planSetId, REPORTED_SET_ID, tambonResidents } from "./flood-timeline-evacuation";
import { FPPS_COMPONENTS } from "./fpps";
import {
  evacuationNeed,
  nodeHomeWet,
  pointShares,
  replayComponents,
  replayConfidence,
  replayFpps,
  tambonImpassableRoads,
  tambonRoadWeights,
  tambonVulnerable,
  type ReplayFppsRaw,
} from "./replay-fpps";

const publicFile = (href: string) => resolve(process.cwd(), "public", href.replace(/^\//, ""));
const manifest = JSON.parse(readFileSync(publicFile(TIMELINE_MANIFEST_URL), "utf8")) as TimelineManifest;
const roads = (JSON.parse(readFileSync(publicFile(manifest.vectors.roads.href), "utf8")) as GeoCollection<LineGeometry, RoadProps>)
  .features.map((feature) => feature.properties);
const access = manifest.access!;
const nodes = parseAccessNodes(new Uint8Array(readFileSync(publicFile(access.nodes.href))), access);
const nodeResidents = tambonResidents(nodes, access.tambons.length);
const vulnerable = tambonVulnerable(nodes, access.tambons.length);
const roadWeights = tambonRoadWeights(roads);

function scoreAt(stage: number, setId = REPORTED_SET_ID, confidence = manifest.confidence) {
  const stats = districtStats(manifest, stage, roads, []);
  return replayFpps({
    tambonIds: Object.keys(manifest.tambon_coverage),
    accessTambons: access.tambons,
    modelledKm2: Object.fromEntries(Object.entries(manifest.tambon_coverage).map(([id, value]) => [id, value.modelled_km2])),
    floodedKm2: stats.tambon_flooded_km2,
    residents: manifest.population!.tambon_totals,
    peopleInWater: stats.tambon_people_in_water ?? {},
    need: evacuationNeed(nodes, access.sets.indexOf(setId), stage, access.levels, manifest.hand.step_m, access.tambons.length),
    nodeResidents,
    vulnerable,
    roadWeightedKm: roadWeights,
    roadWeightedImpassableKm: tambonImpassableRoads(roads, stage, manifest.impassable_depth_m),
    confidence,
  });
}

const raw = (overrides: Partial<ReplayFppsRaw>): ReplayFppsRaw => ({
  floodedKm2: 0, modelledKm2: 10, residents: 1000, peopleInWater: 0, nodeResidents: 1000, evacuees: 0, evacueesWithoutAccess: 0,
  vulnerableResidents: 0, roadWeightedKm: 10, roadWeightedImpassableKm: 0, ...overrides,
});

describe("replay FPPS components", () => {
  it("maps raw figures to 0-100 with fixed anchors", () => {
    const components = replayComponents(raw({
      floodedKm2: 1.25, peopleInWater: 125, evacuees: 200, evacueesWithoutAccess: 60, vulnerableResidents: 50, roadWeightedImpassableKm: 2.5,
    }));
    expect(components.flood_likelihood_0_100).toBeCloseTo(50); // 12.5% of 25%
    expect(components.exposure_0_100).toBeCloseTo(25 + 1.25); // half of 12.5/25%, plus 125/5000 of 50
    expect(components.access_gap_0_100).toBeCloseTo(30); // 60 of the 200 people whose homes are wet
    expect(components.road_criticality_0_100).toBeCloseTo(50); // 25% of 50%
    expect(components.vulnerability_context_0_100).toBeCloseTo(20); // 5% of 25%
  });

  it("saturates at 100 and stays at 0 for empty denominators", () => {
    const high = replayComponents(raw({ floodedKm2: 10, peopleInWater: 5000, evacuees: 400, evacueesWithoutAccess: 400, vulnerableResidents: 1000, roadWeightedImpassableKm: 10 }));
    for (const key of FPPS_COMPONENTS) expect(high[key]).toBe(100);
    const empty = replayComponents(raw({ modelledKm2: 0, residents: 0, nodeResidents: 0, evacuees: 0, roadWeightedKm: 0 }));
    for (const key of FPPS_COMPONENTS) expect(empty[key]).toBe(0);
  });

  it("mirrors the Python home_wet rule", () => {
    expect(nodeHomeWet(10, 0.6, 0.05)).toBe(true); // 0.50 m < 0.6 m
    expect(nodeHomeWet(12, 0.6, 0.05)).toBe(false); // 0.60 m is not below 0.6 m
    expect(nodeHomeWet(0, 0.01, 0.05)).toBe(true); // channel home: wet as soon as the stage rises
    expect(nodeHomeWet(0, 0, 0.05)).toBe(false);
    expect(nodeHomeWet(255, 4, 0.05)).toBe(false); // never floods
  });

  it("treats unknown confidence as low", () => {
    expect(replayConfidence("LOW")).toBe("low");
    expect(replayConfidence("Medium")).toBe("medium");
    expect(replayConfidence("unknown")).toBe("low");
  });

  it("gives point shares that sum to one", () => {
    const row = scoreAt(3.5)[0];
    const shares = pointShares(row.points);
    expect(FPPS_COMPONENTS.reduce((sum, key) => sum + shares[key], 0)).toBeCloseTo(1);
  });
});

describe("replay FPPS on the Mae Sai manifest", () => {
  it("keeps every class at E while the manifest confidence is low", () => {
    expect(manifest.confidence.toLowerCase()).toBe("low");
    for (const row of scoreAt(3.5)) {
      expect(row.action_class).toBe("E");
      expect(row.action_reason_code).toBe("low_confidence");
    }
  });

  it("ranks all eight subdistricts with unique ranks", () => {
    const rows = scoreAt(3.5);
    expect(rows).toHaveLength(8);
    expect(rows.map((row) => row.rank)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    for (let index = 1; index < rows.length; index += 1) expect(rows[index - 1].fpps_0_100).toBeGreaterThanOrEqual(rows[index].fpps_0_100);
  });

  it("puts a riverside subdistrict first at the peak and a hill subdistrict last", () => {
    const rows = scoreAt(3.5);
    expect(["TH570901", "TH570905"]).toContain(rows[0].id); // Mae Sai, Si Mueang Chum
    expect(rows.at(-1)!.id).toBe("TH570906"); // Wiang Phang Kham: about 1% flooded at the peak
  });

  it("rises from the dry baseline to the peak", () => {
    const dry = Object.fromEntries(scoreAt(0).map((row) => [row.id, row]));
    for (const row of scoreAt(3.5)) {
      expect(dry[row.id].components.flood_likelihood_0_100).toBe(0);
      expect(row.fpps_0_100).toBeGreaterThanOrEqual(dry[row.id].fpps_0_100);
    }
  });

  it("counts fewer stranded evacuees as the ranked plan grows", () => {
    const stranded = (setId: string) => scoreAt(3.5, setId).reduce((total, row) => total + row.raw.evacueesWithoutAccess, 0);
    const planSizes = access.sets.filter((id) => id.startsWith("plan_")).length;
    let previous = Infinity;
    for (let k = 1; k <= planSizes; k += 1) {
      const value = stranded(planSetId(k));
      expect(value).toBeLessThanOrEqual(previous + 1e-6);
      previous = value;
    }
  });

  it("has no access gap where nobody's home is wet", () => {
    for (const row of scoreAt(0)) {
      expect(row.raw.evacuees).toBe(0);
      expect(row.components.access_gap_0_100).toBe(0);
    }
  });

  it("gives the score-implied class separately from the confidence-gated class", () => {
    const top = scoreAt(3.5)[0];
    expect(top.action_class).toBe("E");
    expect(["A", "B", "C", "D"]).toContain(top.score_implied_class);
  });
});
