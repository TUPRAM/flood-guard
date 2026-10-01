/**
 * Parity of the browser's access and Evacuation Equity Gap logic with Python.
 *
 * The expected values come from `apps/web/scripts/equity-access-parity-fixture.py`, which runs the Python builder
 * (`lost_at`, `home_wet`) and `floodguard.equity.compute_equity_gap` on the served manifest's access node file.
 * A changed threshold, rounding rule or level step on either side fails here. Everything is a T1 scenario on a
 * modelled flood; "vulnerable" is the terrain/remoteness proxy.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { hourlyStages, roundLikePython, TIMELINE_MANIFEST_URL, type TimelineManifest } from "./flood-timeline";
import {
  accessLevelIndex,
  accessLevelStep,
  accessSnapshot,
  evacuationEquityGap,
  floodedHomeMask,
  homeWetAt,
  nodeLostAccess,
  parseAccessNodes,
  scopeTotals,
  summarizeAccessSets,
  type EquityGap,
} from "./flood-timeline-evacuation";

type Band = "higher" | "lower" | "similar" | null;
/** vulnerable lost, vulnerable total, other lost, other total, then the Python results. */
type EquityRow = [number, number, number, number, number | null, number | null, number | null, Band, string];
/** level index, people lost, vulnerable lost, other lost, then the Python results. */
type LevelRow = [number, number, number, number, number | null, number | null, number | null, Band, string];
interface AccessGroup {
  set: string;
  scope: "all" | "flooded";
  totals: { population: number; vulnerable: number; non_vulnerable: number };
  no_baseline_access: number;
  levels: LevelRow[];
}
interface ParityFixture {
  generated_by: string;
  manifest: string;
  access_nodes_sha256: string;
  scenario_tier: string;
  vulnerable_definition: string;
  confidence: string;
  source_timestamp: string;
  assumptions: string[];
  official_warning: boolean;
  peak_stage_m: number;
  level_step_m: number;
  hours: [number, number, number][];
  level_cases: [number, number][];
  lost_codes: number[];
  lost_cases: [number, boolean[]][];
  home_codes: number[];
  home_wet_cases: [number, boolean[]][];
  equity_columns: string[];
  equity_edge_cases: { case: string; row: EquityRow }[];
  equity_random_cases: EquityRow[];
  access_level_columns: string[];
  access: AccessGroup[];
}

const publicRoot = resolve(import.meta.dirname, "../../public");
const publicFile = (href: string) => resolve(publicRoot, href.replace(/^\//, ""));
const fixture = JSON.parse(readFileSync(resolve(import.meta.dirname, "__fixtures__/mae-sai-equity-access-parity.json"), "utf8")) as ParityFixture;
const manifest = JSON.parse(readFileSync(publicFile(TIMELINE_MANIFEST_URL), "utf8")) as TimelineManifest;
const access = manifest.access!;
const shelters = manifest.shelters!;
const nodeBytes = new Uint8Array(readFileSync(publicFile(access.nodes.href)));
const nodes = parseAccessNodes(nodeBytes, access);

/** What Python reports for a gap: both rates, the ratio, the band its wording states and the wording itself. */
const pythonView = (gap: EquityGap) => [gap.vulnerableRate, gap.nonVulnerableRate, gap.ratio, gap.band, gap.interpretation];
const gapOf = ([vulnerableLost, vulnerableTotal, nonVulnerableLost, nonVulnerableTotal]: readonly [number, number, number, number, ...unknown[]]) =>
  evacuationEquityGap({ vulnerableLost, vulnerableTotal, nonVulnerableLost, nonVulnerableTotal });
const edgeCase = (name: string) => {
  const found = fixture.equity_edge_cases.find((item) => item.case.startsWith(name));
  if (!found) throw new Error(`The parity fixture lost its case: ${name}`);
  return found.row;
};

describe("Equity and access parity fixture", () => {
  it("was generated from the manifest and node file the page serves", () => {
    expect(fixture.manifest).toBe(TIMELINE_MANIFEST_URL);
    expect(fixture.access_nodes_sha256).toBe(access.nodes.sha256);
    expect(createHash("sha256").update(nodeBytes).digest("hex")).toBe(fixture.access_nodes_sha256);
    expect(fixture.peak_stage_m).toBe(shelters.method.peak_stage_m);
    expect(fixture.level_step_m).toBe(accessLevelStep(access.levels));
    expect(fixture.generated_by).toContain("floodguard.equity.compute_equity_gap");
  });

  it("labels its figures as a T1 scenario with a proxy for vulnerability, a confidence, a timestamp and assumptions", () => {
    expect(fixture.scenario_tier).toBe(access.scenario_tier);
    expect(fixture.scenario_tier).toContain("T1 scenario (model)");
    expect(fixture.vulnerable_definition).toContain("vulnerable = terrain/remoteness proxy");
    expect(fixture.confidence).toBe("low");
    expect(fixture.source_timestamp).toBe(access.source_timestamp);
    expect(fixture.assumptions.length).toBeGreaterThanOrEqual(3);
    expect(fixture.official_warning).toBe(false);
    // The fixture holds access figures only: no priority score and no action class.
    expect(JSON.stringify(Object.keys(fixture))).not.toMatch(/fpps|action_class/i);
  });
});

describe("Access level and lost-access parity with the Python builder", () => {
  it("maps every replay hour's stage to the level index Python's lost_at uses", () => {
    const stages = hourlyStages(manifest.stage_anchors);
    expect(fixture.hours).toHaveLength(stages.length);
    for (const [hour, stage, level] of fixture.hours) {
      expect(stages[hour], `hour ${hour}`).toBe(stage);
      expect(accessLevelIndex(stage, access.levels), `hour ${hour}, stage ${stage}`).toBe(level);
    }
    // The hourly grid reaches the modelled peak level.
    expect(Math.max(...fixture.hours.map(([, , level]) => level))).toBe(accessLevelIndex(fixture.peak_stage_m, access.levels));
  });

  it("maps awkward stages (binary rounding at level edges, beyond the last level) to the same index", () => {
    expect(fixture.level_cases.length).toBeGreaterThan(80);
    for (const [stage, level] of fixture.level_cases) expect(accessLevelIndex(stage, access.levels), `stage ${stage}`).toBe(level);
    const byStage = new Map(fixture.level_cases);
    expect([byStage.get(0.049), byStage.get(0.05), byStage.get(0.15), byStage.get(0.35), byStage.get(3.5), byStage.get(4.05)]).toEqual([0, 1, 3, 7, 70, 81]);
  });

  it("counts a node as lost exactly when Python does, never for codes 254 and 255", () => {
    expect(fixture.lost_codes).toEqual(expect.arrayContaining([0, 254, 255]));
    for (const [stage, flags] of fixture.lost_cases) {
      const level = accessLevelIndex(stage, access.levels);
      expect(fixture.lost_codes.map((code) => nodeLostAccess(code, level)), `stage ${stage}`).toEqual(flags);
    }
    for (const [, flags] of fixture.lost_cases) {
      expect(flags[fixture.lost_codes.indexOf(254)]).toBe(false);
      expect(flags[fixture.lost_codes.indexOf(255)]).toBe(false);
    }
  });

  it("reads a home as wet exactly when Python's home_wet does", () => {
    const { step_m: step, channel_code: channel, never_code: never } = manifest.hand;
    for (const [stage, flags] of fixture.home_wet_cases) {
      expect(fixture.home_codes.map((code) => homeWetAt(code, stage, step, channel, never)), `stage ${stage}`).toEqual(flags);
    }
  });
});

describe("Evacuation Equity Gap parity with floodguard.equity", () => {
  it("gives Python's rates, ratio, band and wording on the hand-picked rule cases", () => {
    expect(fixture.equity_columns.slice(4)).toEqual(["vulnerable_rate", "non_vulnerable_rate", "ratio", "band", "interpretation"]);
    expect(fixture.equity_edge_cases.length).toBeGreaterThanOrEqual(30);
    for (const { case: name, row } of fixture.equity_edge_cases) expect(pythonView(gapOf(row)), name).toEqual(row.slice(4));
  });

  it("keeps the band limits where Python has them: above 1.2 is higher, below 0.8 is lower", () => {
    // These rows pin the two limits from both sides; a drifted TypeScript threshold fails on at least one of them.
    expect(edgeCase("ratio exactly 1.2").slice(6, 8)).toEqual([1.2, "similar"]);
    expect(edgeCase("ratio 1.201").slice(6, 8)).toEqual([1.201, "higher"]);
    expect(edgeCase("ratio 1.199").slice(6, 8)).toEqual([1.199, "similar"]);
    expect(edgeCase("ratio 1.25").slice(6, 8)).toEqual([1.25, "higher"]);
    expect(edgeCase("ratio exactly 0.8").slice(6, 8)).toEqual([0.8, "similar"]);
    expect(edgeCase("ratio 0.799").slice(6, 8)).toEqual([0.799, "lower"]);
    expect(edgeCase("ratio 0.801").slice(6, 8)).toEqual([0.801, "similar"]);
    expect(edgeCase("ratio 0.75").slice(6, 8)).toEqual([0.75, "lower"]);
    for (const name of ["ratio exactly 1.2", "ratio 1.201", "ratio 1.199", "ratio 1.25", "ratio exactly 0.8", "ratio 0.799", "ratio 0.801", "ratio 0.75"]) {
      const row = edgeCase(name);
      expect(gapOf(row).band, name).toBe(row[7]);
    }
    // Rounding rules: rates to 4 decimals and the ratio to 3, half-way cases as Python rounds them.
    expect(edgeCase("rate half-way case 0.00005")[4]).toBe(0.0001);
    expect(edgeCase("rate half-way case 0.00015")[4]).toBe(0.0001);
    expect(edgeCase("three-decimal ratio rounding")[6]).toBe(2.332);
    // Undefined results stay undefined: no ratio and no band.
    expect(edgeCase("only vulnerable loss").slice(6, 8)).toEqual([null, null]);
    expect(edgeCase("no vulnerable residents").slice(4, 8)).toEqual([null, 0.1, null, null]);
    expect(edgeCase("no other residents").slice(4, 8)).toEqual([0.1, null, null, null]);
  });

  it("gives Python's result on 150 reproducible inputs with fractional residents", () => {
    expect(fixture.equity_random_cases).toHaveLength(150);
    const bands = new Set<Band>();
    fixture.equity_random_cases.forEach((row, index) => {
      expect(pythonView(gapOf(row)), `random case ${index}`).toEqual(row.slice(4));
      bands.add(row[7]);
    });
    expect([...bands]).toEqual(expect.arrayContaining(["higher", "lower", "similar"]));
  });
});

describe("Access loss and equity parity on the served node file (T1 scenario)", () => {
  const masks = {
    all: null,
    flooded: floodedHomeMask(nodes, shelters.method.peak_stage_m, manifest.hand.step_m, manifest.hand.channel_code, manifest.hand.never_code),
  };

  it("covers the reported set, the smallest, default and largest plan, for all residents and for flooded homes", () => {
    const groups = fixture.access.map((group) => `${group.set}/${group.scope}`);
    const sets = ["reported_2024", "plan_1", `plan_${shelters.knee_k}`, access.sets.at(-1)!];
    expect(groups).toEqual(sets.flatMap((set) => [`${set}/all`, `${set}/flooded`]));
    for (const group of fixture.access) expect(group.levels.map(([level]) => level)).toEqual(access.levels.map((_, index) => index));
    expect(fixture.access_level_columns.slice(0, 4)).toEqual(["level_index", "people_lost", "vulnerable_lost", "non_vulnerable_lost"]);
  });

  it("sums the same lost residents as Python at every level, set and scope", () => {
    for (const group of fixture.access) {
      const mask = masks[group.scope];
      const summary = summarizeAccessSets(nodes, access, mask)[access.sets.indexOf(group.set)];
      const totals = scopeTotals(nodes, mask);
      const label = `${group.set}/${group.scope}`;
      expect(totals.population, label).toBeCloseTo(group.totals.population, 6);
      expect(totals.vulnerable, label).toBeCloseTo(group.totals.vulnerable, 6);
      expect(totals.nonVulnerable, label).toBeCloseTo(group.totals.non_vulnerable, 6);
      for (const [level, people, vulnerable, other] of group.levels) {
        const snapshot = accessSnapshot(summary, access.levels[level], access.levels);
        expect(snapshot.levelIndex, `${label} level ${level}`).toBe(level);
        expect(snapshot.lost.population, `${label} level ${level}`).toBeCloseTo(people, 6);
        expect(snapshot.lost.vulnerable, `${label} level ${level}`).toBeCloseTo(vulnerable, 6);
        expect(snapshot.lost.nonVulnerable, `${label} level ${level}`).toBeCloseTo(other, 6);
        expect(snapshot.never.population, label).toBeCloseTo(group.no_baseline_access, 6);
      }
    }
  });

  it("states the same Evacuation Equity Gap as Python from its own sums, at every level, set and scope", () => {
    let compared = 0;
    for (const group of fixture.access) {
      const mask = masks[group.scope];
      const summary = summarizeAccessSets(nodes, access, mask)[access.sets.indexOf(group.set)];
      const totals = scopeTotals(nodes, mask);
      for (const row of group.levels) {
        const { lost } = accessSnapshot(summary, access.levels[row[0]], access.levels);
        const gap = evacuationEquityGap({
          vulnerableLost: lost.vulnerable, vulnerableTotal: totals.vulnerable,
          nonVulnerableLost: lost.nonVulnerable, nonVulnerableTotal: totals.nonVulnerable,
        });
        expect(pythonView(gap), `${group.set}/${group.scope} level ${row[0]}`).toEqual(row.slice(4));
        // And on Python's own sums, so the function is compared on identical inputs too.
        expect(pythonView(gapOf([row[2], group.totals.vulnerable, row[3], group.totals.non_vulnerable])), `${group.set}/${group.scope} level ${row[0]} (Python sums)`).toEqual(row.slice(4));
        compared += 1;
      }
    }
    expect(compared).toBe(fixture.access.length * access.levels.length);
  });

  it("reproduces the baked keyframe figures, so the fixture and the manifest agree", () => {
    for (const day of manifest.days) {
      for (const [set, baked] of Object.entries(day.stats.access ?? {})) {
        const group = fixture.access.find((item) => item.set === set && item.scope === "all")!;
        const row = group.levels[accessLevelIndex(day.stage_m, access.levels)];
        expect(roundLikePython(row[1], 0), `${day.date} ${set}`).toBe(baked.people_lost_access);
      }
    }
  });
});
