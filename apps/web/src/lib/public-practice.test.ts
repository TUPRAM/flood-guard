import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { parseTimelineManifest, TIMELINE_MANIFEST_URL, type GeoCollection, type LineGeometry, type RoadProps } from "./flood-timeline";
import { parseExerciseFile, EXERCISE_FILE_URL } from "./flood-timeline-command-incidents";
import { NEVER_LOST_CODE, NO_BASELINE_CODE, parseAccessNodes } from "./flood-timeline-evacuation";
import {
  groundDistanceM,
  householdStatus,
  nearestAccessNode,
  PRACTICE_BANNER,
  PRACTICE_COPY,
  PRACTICE_PROMPT,
  PRACTICE_RADIUS_M,
  practiceReportLabel,
  practiceReportLines,
  practiceReports,
  practiceStatus,
  practiceView,
  REACH_RISK_MARGIN_M,
  roadsNear,
  tallyRoads,
  type HouseholdInput,
  type PracticeReplay,
} from "./public-practice";
import {
  PRACTICE_HOMES,
  PRACTICE_MENU_COPY,
  PRACTICE_SCENARIO_LABELS,
  PRACTICE_SCENARIOS,
  PRACTICE_STATE_TONE,
  practiceScenario,
  type PracticeState,
} from "./public-practice-scenarios";
import { findWordingViolations } from "./replay-wording-lint";

// The fixtures are the published replay files themselves (revision r5) and the file of invented exercise items.
const publicRoot = resolve(import.meta.dirname, "../../public");
const readPublic = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = parseTimelineManifest(JSON.parse(readPublic(TIMELINE_MANIFEST_URL).toString("utf8")));
const roads = JSON.parse(readPublic(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<LineGeometry, RoadProps>;
const nodes = parseAccessNodes(new Uint8Array(readPublic(manifest.access!.nodes.href)), manifest.access!);
const replay: PracticeReplay = { manifest, roads, nodes };
const exercise = parseExerciseFile(JSON.parse(readPublic(EXERCISE_FILE_URL).toString("utf8")));

const levels = Array.from({ length: 81 }, (_, index) => Math.round(index * 5) / 100);
const noRoads = { totalM: 5000, wetM: 0, impassableM: 0 };
const input = (over: Partial<HouseholdInput>): HouseholdInput => ({
  stage: 1,
  stageBefore: 1,
  stageAfter: 1,
  // Terrain 5 m above the channel at a step of 0.05 m: dry at every stage of the replay.
  homeCode: 100,
  homeFactor: 255,
  cutCode: NEVER_LOST_CODE,
  levels,
  step: 0.05,
  roads: noRoads,
  ...over,
});

describe("householdStatus", () => {
  it("is normal while no road within reach has water on it", () => {
    const status = householdStatus(input({ stage: 0, stageBefore: 0, stageAfter: 0 }));
    expect(status.state).toBe("normal");
    expect(status.homeDepthM).toBeNull();
    expect(status.reach).toBe("within_reach");
  });

  it("reads shallow water on roads as a heads-up and impassable roads as roads cut", () => {
    expect(householdStatus(input({ roads: { totalM: 5000, wetM: 400, impassableM: 0 } })).state).toBe("heads_up");
    expect(householdStatus(input({ roads: { totalM: 5000, wetM: 400, impassableM: 900 } })).state).toBe("roads_cut");
  });

  it("reads the same roads as going down once the river falls", () => {
    const falling = { stage: 0.9, stageBefore: 1.0, stageAfter: 0.8 };
    expect(householdStatus(input({ ...falling, roads: { totalM: 5000, wetM: 400, impassableM: 0 } })).state).toBe("going_down");
    expect(householdStatus(input({ ...falling, roads: { totalM: 5000, wetM: 0, impassableM: 900 } })).state).toBe("going_down");
    // Nothing wet nearby is normal, whichever way the river moves.
    expect(householdStatus(input({ ...falling })).state).toBe("normal");
  });

  it("calls the walk to a shelter close to being cut only while the river rises within the margin", () => {
    // Cut code 46 is a stage of 2.30 m.
    const near = householdStatus(input({ stage: 1.9, stageBefore: 1.6, stageAfter: 2.2, cutCode: 46, roads: { totalM: 5000, wetM: 0, impassableM: 900 } }));
    expect(near.state).toBe("reach_at_risk");
    expect(near.reach).toBe("at_risk");
    expect(near.reachMarginM).toBeCloseTo(0.4, 6);
    expect(near.reachMarginM!).toBeLessThanOrEqual(REACH_RISK_MARGIN_M);
    const far = householdStatus(input({ stage: 1.2, stageBefore: 0.9, stageAfter: 1.5, cutCode: 46, roads: { totalM: 5000, wetM: 0, impassableM: 900 } }));
    expect(far.state).toBe("roads_cut");
    expect(far.reach).toBe("within_reach");
    // The same height on a falling river is not a walk about to be cut.
    const receding = householdStatus(input({ stage: 1.9, stageBefore: 2.2, stageAfter: 1.6, cutCode: 46, roads: { totalM: 5000, wetM: 0, impassableM: 900 } }));
    expect(receding.state).toBe("going_down");
    expect(receding.reach).toBe("within_reach");
  });

  it("is cut off once the stage reaches the cut level, and never for a point that keeps its walk", () => {
    const lost = householdStatus(input({ stage: 2.3, stageBefore: 2.0, stageAfter: 2.6, cutCode: 46 }));
    expect(lost.state).toBe("cut_off");
    expect(lost.reach).toBe("lost");
    expect(lost.reachMarginM).toBeNull();
    expect(householdStatus(input({ stage: 3.5, cutCode: NEVER_LOST_CODE })).reach).toBe("within_reach");
  });

  it("does not call a point cut off that had no shelter within reach before the flood", () => {
    const status = householdStatus(input({ stage: 3.5, cutCode: NO_BASELINE_CODE, roads: { totalM: 5000, wetM: 0, impassableM: 4000 } }));
    expect(status.reach).toBe("none_before_flood");
    expect(status.state).toBe("roads_cut");
  });

  it("puts water at the home before everything else", () => {
    // Terrain 2.75 m above the channel; at 3.5 m the home is 0.75 m deep.
    const status = householdStatus(input({ stage: 3.5, homeCode: 55, cutCode: 46, roads: { totalM: 5000, wetM: 0, impassableM: 4000 } }));
    expect(status.state).toBe("water_at_home");
    expect(status.homeDepthM).toBeCloseTo(0.75, 6);
    // A home on the mapped channel is not wet at stage 0.
    expect(householdStatus(input({ stage: 0, stageBefore: 0, stageAfter: 0, homeCode: 0 })).homeDepthM).toBeNull();
  });
});

describe("roads and resident points near a home", () => {
  const piece = (longitude: number, latitude: number, h: number | null, len: number, m = true) => ({
    type: "Feature" as const,
    geometry: { type: "LineString" as const, coordinates: [[longitude, latitude], [longitude + 0.0005, latitude]] as [number, number][] },
    properties: { c: "residential", h, m, len, t: "TH570901" },
  });

  it("measures ground distance in metres", () => {
    expect(groundDistanceM(20.44, 99.887, 20.44, 99.887)).toBe(0);
    expect(groundDistanceM(20.44, 99.887, 20.449, 99.887)).toBeCloseTo(995, -1);
  });

  it("keeps the road pieces inside the radius and counts their length by state", () => {
    const near = [piece(99.887, 20.44, 0.5, 100), piece(99.888, 20.441, 1.2, 60), piece(99.889, 20.442, null, 80), piece(99.887, 20.441, 0.5, 40, false)];
    const kept = roadsNear([...near, piece(99.95, 20.44, 0.1, 500)], 20.44, 99.887, PRACTICE_RADIUS_M);
    expect(kept).toHaveLength(4);
    // At 1.0 m: the first piece is 0.5 m deep (impassable), the second is dry, the third never floods, the fourth is not modelled.
    expect(tallyRoads(kept, 1.0, 0.3)).toEqual({ totalM: 240, wetM: 0, impassableM: 100 });
    // At 1.3 m the second piece has 0.1 m of water on it: wet, still passable.
    expect(tallyRoads(kept, 1.3, 0.3)).toEqual({ totalM: 240, wetM: 60, impassableM: 100 });
  });

  it("finds the nearest resident point within reach, and none further away", () => {
    const points = { count: 2, lat: new Float32Array([20.44, 20.45]), lon: new Float32Array([99.887, 99.887]) };
    expect(nearestAccessNode(points, 20.4401, 99.887)).toBe(0);
    expect(nearestAccessNode(points, 20.445, 99.887)).toBe(-1);
  });
});

describe("the practice scenarios on the published replay (r5)", () => {
  it("has a resident point of the replay at each example home, in Mae Sai town", () => {
    const tambons = manifest.access!.tambons;
    for (const home of Object.values(PRACTICE_HOMES)) {
      const node = nearestAccessNode(nodes, home.latitude, home.longitude);
      expect(node).toBeGreaterThanOrEqual(0);
      expect(groundDistanceM(home.latitude, home.longitude, nodes.lat[node], nodes.lon[node])).toBeLessThan(15);
      expect(tambons[nodes.tambonIndex[node] - 1]).toBe(home.tambonId);
    }
    expect(groundDistanceM(PRACTICE_HOMES.dry.latitude, PRACTICE_HOMES.dry.longitude, PRACTICE_HOMES.flooded.latitude, PRACTICE_HOMES.flooded.longitude)).toBeLessThan(150);
  });

  it("computes every scenario to the state it is named after", () => {
    const computed = PRACTICE_SCENARIOS.map((scenario) => practiceStatus(replay, PRACTICE_HOMES[scenario.home], scenario.hour)?.state);
    expect(computed).toEqual(PRACTICE_SCENARIOS.map((scenario) => scenario.id));
    expect(new Set(computed).size).toBe(7);
  });

  it("keeps the dry home dry and cut off at the modelled peak while its neighbour floods", () => {
    const peak = practiceScenario("cut_off")!;
    const dry = practiceStatus(replay, PRACTICE_HOMES.dry, peak.hour)!;
    const flooded = practiceStatus(replay, PRACTICE_HOMES.flooded, peak.hour)!;
    expect(dry.homeDepthM).toBeNull();
    expect(dry.reach).toBe("lost");
    expect(flooded.homeDepthM!).toBeGreaterThan(1);
    // Most of the road within reach is impassable at the peak, and none of it at noon on 9 September.
    expect(dry.roads.impassableM / dry.roads.totalM).toBeGreaterThan(0.6);
    expect(practiceStatus(replay, PRACTICE_HOMES.dry, practiceScenario("normal")!.hour)!.roads).toMatchObject({ wetM: 0, impassableM: 0 });
  });

  it("shows only the invented items that have arrived by the hour, nearest first", () => {
    const early = practiceReports(exercise.items, PRACTICE_HOMES.dry, practiceScenario("normal")!.hour);
    expect(early).toEqual([]);
    const late = practiceReports(exercise.items, PRACTICE_HOMES.dry, practiceScenario("going_down")!.hour);
    expect(late).toHaveLength(exercise.items.length);
    expect(late.every((entry, index) => index === 0 || late[index - 1].distanceM <= entry.distanceM)).toBe(true);
    expect(late.every((entry) => entry.item.id.startsWith("EX-"))).toBe(true);
  });

  it("builds a view whose banner, tone and lines belong to the computed state", () => {
    for (const scenario of PRACTICE_SCENARIOS) {
      for (const language of ["en", "th"] as const) {
        const view = practiceView(replay, exercise.items, scenario, language)!;
        expect(view.status.state).toBe(scenario.id);
        expect(view.banner).toBe(PRACTICE_BANNER[scenario.id][language]);
        expect(view.tone).toBe(PRACTICE_STATE_TONE[scenario.id]);
        expect(view.prompt).toBe(PRACTICE_PROMPT[scenario.id][language]);
        expect(view.moment).toContain("2024");
        expect(view.lines.length).toBeGreaterThanOrEqual(3);
        expect(view.showPeakExtent).toBe(scenario.id === "normal" || scenario.id === "heads_up");
      }
    }
    const peak = practiceView(replay, exercise.items, practiceScenario("cut_off")!, "en")!;
    expect(peak.lines[0]).toMatch(/^\d+\.\d km of the \d+\.\d km of road within 1 km are under 30 cm of water or more\./);
    expect(peak.lines[1]).toBe("No shelter reported in use in 2024 can be reached within a 2 km walk on passable roads.");
    expect(peak.lines[2]).toBe("The model has this home dry.");
    expect(peak.lines[3]).toMatch(/practice reports within 1 km \(invented for the exercise\)\.$/);
    const flooded = practiceView(replay, exercise.items, practiceScenario("water_at_home")!, "en")!;
    expect(flooded.lines[2]).toMatch(/^The model has about \d\.\d m of water at this home\.$/);
    const calm = practiceView(replay, exercise.items, practiceScenario("normal")!, "en")!;
    expect(calm.lines[0]).toBe("No road within 1 km has water on it.");
    expect(calm.reports).toEqual([]);
    expect(calm.key.map((item) => item.swatch)).toEqual(["water", "peak", "road-impassable", "road-wet", "radius"]);
    const risk = practiceView(replay, exercise.items, practiceScenario("reach_at_risk")!, "en")!;
    expect(risk.lines[1]).toMatch(/that walk is cut once the river is about \d+ cm higher\.$/);
  });

  it("only counts an hour the replay covers and a home it knows", () => {
    expect(practiceStatus(replay, { latitude: 13.75, longitude: 100.5 }, 84)).toBeNull();
    for (const scenario of PRACTICE_SCENARIOS) {
      expect(scenario.hour).toBeGreaterThanOrEqual(0);
      expect(scenario.hour).toBeLessThan(11 * 24);
    }
  });
});

describe("practice wording", () => {
  const states = PRACTICE_SCENARIOS.map((scenario) => scenario.id) satisfies PracticeState[];

  it("names every state in both languages", () => {
    for (const state of states) {
      for (const table of [PRACTICE_BANNER, PRACTICE_PROMPT, PRACTICE_SCENARIO_LABELS]) {
        expect(table[state].en.trim()).not.toBe("");
        expect(table[state].th.trim()).not.toBe("");
      }
    }
  });

  it("passes the replay's wording rules: no present-moment claim, no promise of what comes, no instruction to move", () => {
    const texts: { source: string; text: string }[] = [];
    const add = (source: string, table: Record<string, Record<"en" | "th", string>>) => {
      for (const [key, value] of Object.entries(table)) {
        texts.push({ source: `${source}.${key} (en)`, text: value.en }, { source: `${source}.${key} (th)`, text: value.th });
      }
    };
    add("PRACTICE_BANNER", PRACTICE_BANNER);
    add("PRACTICE_PROMPT", PRACTICE_PROMPT);
    add("PRACTICE_COPY", PRACTICE_COPY);
    add("PRACTICE_SCENARIO_LABELS", PRACTICE_SCENARIO_LABELS);
    add("PRACTICE_MENU_COPY", PRACTICE_MENU_COPY);
    for (const scenario of PRACTICE_SCENARIOS) {
      for (const language of ["en", "th"] as const) {
        const view = practiceView(replay, exercise.items, scenario, language)!;
        texts.push({ source: `view ${scenario.id} (${language})`, text: [view.banner, view.moment, ...view.lines, view.prompt, ...view.key.map((item) => item.text)].join(" │ ") });
      }
    }
    for (const item of exercise.items) {
      for (const language of ["en", "th"] as const) {
        const lines = practiceReportLines(item, language);
        texts.push({ source: `report ${item.id} (${language})`, text: [practiceReportLabel(item, language), lines.title, lines.depth, lines.tag].join(" │ ") });
      }
    }
    const findings = texts.flatMap(({ source, text }) => findWordingViolations(text, source));
    expect(findings.map((finding) => `[${finding.rule}] ${finding.source}: ${finding.context}`)).toEqual([]);
  });

  it("says on the map and in the panel what the replay is not", () => {
    expect(PRACTICE_COPY.noteBoundary.en).toBe("Model · not real-time · not an official warning");
    expect(PRACTICE_COPY.noteBoundary.th).toContain("ไม่ใช่ข้อมูลเรียลไทม์");
    expect(PRACTICE_COPY.noteBoundary.th).toContain("ไม่ใช่คำเตือนทางการ");
    expect(PRACTICE_COPY.boundary.en).toContain("low confidence");
    expect(PRACTICE_COPY.boundary.en).toContain("Not real-time and not an official warning");
  });
});
