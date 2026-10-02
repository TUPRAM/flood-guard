/**
 * Parity of the browser's access and Evacuation Equity Gap logic with Python.
 *
 * The expected values come from `apps/web/scripts/equity-access-parity-fixture.py`, which runs the Python builder
 * (`lost_at`, `home_wet`), `floodguard.replay_equity.replay_equity_gap` (the replay's equity rule: each group's lost
 * residents over its residents within reach before the flood, with its null reasons) and
 * `floodguard.shelter_set_comparison.shelter_set_summary` on the served manifest's access node file.
 * A changed threshold, rounding rule, level step, group-size limit, cut-off share or denominator on either side fails here.
 * Everything is a T1 scenario on a modelled flood; hours come from illustrative stage keyframes, not observed;
 * "vulnerable" is the terrain/remoteness proxy.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { hourlyStages, roundLikePython, TIMELINE_MANIFEST_URL, type TimelineManifest } from "./flood-timeline";
import {
  accessEquityGap,
  accessLevelIndex,
  accessLevelStep,
  accessSnapshot,
  CUTOFF_COVERAGE_SHARE,
  EQUITY_DENOMINATOR,
  EQUITY_MIN_GROUP,
  equityWording,
  evacuationEquityGap,
  floodedHomeMask,
  homeWetAt,
  nodeLostAccess,
  parseAccessNodes,
  scopeTotals,
  shelterSetComparison,
  summarizeAccessSets,
  withinReachBeforeFlood,
  type EquityGap,
  type EquityNullReason,
} from "./flood-timeline-evacuation";

type Band = "higher" | "lower" | "similar" | null;
type Reason = EquityNullReason | null;
/** vulnerable lost, vulnerable within reach before the flood, other lost, other within reach, then the Python results. */
type EquityRow = [number, number, number, number, number | null, number | null, number | null, Band, string, Reason];
/** level index, people lost, vulnerable lost, other lost, then the Python results. */
type LevelRow = [number, number, number, number, number | null, number | null, number | null, Band, string, Reason];
/** One shelter set counted for one scope by Python's `shelter_set_summary`. */
interface ComparisonGroup {
  set: string;
  scope: "all" | "flooded";
  residents: number;
  baseline: number;
  vulnerable_baseline: number;
  at_peak: { keeping: number; lost: number; lost_share: number | null; vulnerable_lost: number };
  cutoff_status: "reached" | "not_reached" | "no_baseline";
  cutoff_hour: number | null;
  /** hour, keeping, lost, lost share */
  hours: [number, number, number, number | null][];
}
interface AccessGroup {
  set: string;
  scope: "all" | "flooded";
  totals: { population: number; vulnerable: number; non_vulnerable: number };
  /** Residents with a shelter of the set within reach before the flood: the denominators of the loss rates. */
  within_reach: { population: number; vulnerable: number; non_vulnerable: number };
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
  equity_denominator: string;
  equity_minimum_group: number;
  equity_null_reasons: string[];
  equity_columns: string[];
  equity_edge_cases: { case: string; row: EquityRow }[];
  equity_random_cases: EquityRow[];
  access_level_columns: string[];
  access: AccessGroup[];
  cutoff_coverage_share: number;
  set_comparison_hour_columns: string[];
  set_comparison: ComparisonGroup[];
}

const publicRoot = resolve(import.meta.dirname, "../../public");
const publicFile = (href: string) => resolve(publicRoot, href.replace(/^\//, ""));
const fixture = JSON.parse(readFileSync(resolve(import.meta.dirname, "__fixtures__/mae-sai-equity-access-parity.json"), "utf8")) as ParityFixture;
const manifest = JSON.parse(readFileSync(publicFile(TIMELINE_MANIFEST_URL), "utf8")) as TimelineManifest;
const access = manifest.access!;
const shelters = manifest.shelters!;
const nodeBytes = new Uint8Array(readFileSync(publicFile(access.nodes.href)));
const nodes = parseAccessNodes(nodeBytes, access);

/** What Python reports for a gap: both rates, the ratio, the band, the wording and the reason a ratio is withheld. */
const pythonView = (gap: EquityGap) => [gap.vulnerableRate, gap.nonVulnerableRate, gap.ratio, gap.band, gap.interpretation, gap.reason];
const gapOf = ([vulnerableLost, vulnerableWithinReach, nonVulnerableLost, nonVulnerableWithinReach]: readonly [number, number, number, number, ...unknown[]]) =>
  evacuationEquityGap({ vulnerableLost, vulnerableWithinReach, nonVulnerableLost, nonVulnerableWithinReach });
const TOO_SMALL = "Equity gap not computed: a group has fewer than 50 residents with a shelter within reach before the flood.";
const NO_LOSS = "Equity gap not computed: neither group has lost access.";
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
    expect(fixture.generated_by).toContain("floodguard.replay_equity.replay_equity_gap");
    expect(fixture.generated_by).toContain("floodguard.shelter_set_comparison.shelter_set_summary");
    expect(fixture.equity_minimum_group).toBe(EQUITY_MIN_GROUP);
    expect(fixture.equity_denominator).toBe(EQUITY_DENOMINATOR);
    expect(fixture.equity_denominator).toBe("within_reach_before_flood");
    expect(fixture.cutoff_coverage_share).toBe(CUTOFF_COVERAGE_SHARE);
  });

  it("labels its figures as a T1 scenario with a proxy for vulnerability, a confidence, a timestamp and assumptions", () => {
    expect(fixture.scenario_tier).toBe(access.scenario_tier);
    expect(fixture.scenario_tier).toContain("T1 scenario (model)");
    expect(fixture.vulnerable_definition).toContain("vulnerable = terrain/remoteness proxy");
    expect(fixture.confidence).toBe("low");
    expect(fixture.source_timestamp).toBe(access.source_timestamp);
    expect(fixture.assumptions.length).toBeGreaterThanOrEqual(3);
    expect(fixture.assumptions.join(" ")).toContain("Hours come from illustrative stage keyframes, not observed");
    expect(fixture.assumptions.join(" ")).toContain("the shelter sets are not ranked");
    expect(fixture.assumptions.join(" ")).toContain("of its residents who had a shelter of the set within reach before the flood, the share who lost it");
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

describe("Evacuation Equity Gap parity with floodguard.replay_equity", () => {
  it("gives Python's rates, ratio, band, wording and reason on the hand-picked rule cases", () => {
    expect(fixture.equity_columns.slice(0, 4)).toEqual(["vulnerable_lost", "vulnerable_within_reach", "non_vulnerable_lost", "non_vulnerable_within_reach"]);
    expect(fixture.equity_columns.slice(4)).toEqual(["vulnerable_rate", "non_vulnerable_rate", "ratio", "band", "interpretation", "reason"]);
    expect(fixture.equity_edge_cases.length).toBeGreaterThanOrEqual(40);
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

  it("withholds the ratio with reason no_loss when neither group has lost access, as Python does", () => {
    for (const name of ["no loss in either group", "no loss, both groups large", "no loss, groups of exactly 50"]) {
      const row = edgeCase(name);
      expect([row[0], row[2]], name).toEqual([0, 0]);
      expect(row.slice(4), name).toEqual([0, 0, null, null, NO_LOSS, "no_loss"]);
      expect(gapOf(row), name).toMatchObject({ status: "no_loss", reason: "no_loss", ratio: null, band: null });
    }
  });

  it("reads loss from the residents who lost access, not from a rate that rounds to zero, as Python does", () => {
    // Three residents lost in a group of 74,647: both rates are 0.0000, and it is still a loss.
    const otherOnly = edgeCase("small loss in a large group, no vulnerable loss");
    expect(otherOnly.slice(0, 4)).toEqual([0, 7152, 3, 74647]);
    expect(otherOnly.slice(4)).toEqual([0, 0, 0, "lower", "Vulnerable residents are 0 times as likely to lose access.", null]);
    expect(gapOf(otherOnly)).toMatchObject({ status: "ratio", reason: null, vulnerableLost: 0, nonVulnerableLost: 3 });
    // Both groups lost a little: the ratio comes from the unrounded rates.
    expect(edgeCase("small loss in both large groups").slice(4, 8)).toEqual([0.0001, 0, 3.479, "higher"]);
    expect(edgeCase("both rates round to zero").slice(4, 8)).toEqual([0, 0, 1, "similar"]);
    expect(edgeCase("only the non-vulnerable rate rounds to zero").slice(6, 8)).toEqual([1250, "higher"]);
    // No loss at all in the other group stays undefined, however small the vulnerable loss.
    expect(edgeCase("small vulnerable loss only, large groups").slice(6)).toEqual([null, null,
      "Equity gap ratio undefined because vulnerable loss exists while non-vulnerable loss is zero.", "undefined_ratio"]);
    // The page never says "no one" or "no proxy-vulnerable resident" while residents have lost access.
    for (const name of ["small loss in a large group, no vulnerable loss", "small loss in both large groups", "both rates round to zero",
      "only the non-vulnerable rate rounds to zero", "small vulnerable loss beside a large other loss"]) {
      const row = edgeCase(name);
      for (const language of ["en", "th"] as const) {
        const wording = equityWording(gapOf(row), language);
        const said = `${wording.value} ${wording.sentence}`;
        expect(said, name).not.toMatch(/No one in either group|ไม่มีผู้ใดในทั้งสองกลุ่ม|Infinity|NaN/);
        if (row[0] > 0) expect(said, name).not.toMatch(/no proxy-vulnerable resident has lost access|ไม่มีผู้ใดในกลุ่มเปราะบางตามตัวแทนสูญเสียการเข้าถึง/);
        if (row[2] > 0 && row[5] === 0) expect(said, name).toContain("< 0.01%");
      }
    }
    expect(equityWording(gapOf(otherOnly), "en")).toEqual({
      value: "no proxy-vulnerable resident has lost access", sentence: "At this replay hour, < 0.01% of everyone else have.",
    });
    expect(equityWording(gapOf(edgeCase("small loss in both large groups")), "en")).toEqual({
      value: "3.48", sentence: "Proxy-vulnerable residents are about 3.5× more likely to lose access (0.01% vs < 0.01%).",
    });
  });

  it("withholds the ratio with reason insufficient_group_denominator below 50 residents within reach per group, as Python does", () => {
    expect(fixture.equity_null_reasons).toEqual(["insufficient_group_denominator", "no_loss", "undefined_ratio"]);
    const tooSmall = [
      "vulnerable group of 49.99", "vulnerable group of 49 ", "other group of 49", "both groups too small", "one resident in the vulnerable group",
      "too small and no loss", "too small and only vulnerable loss", "no vulnerable residents", "no vulnerable residents and no other loss",
      "no other residents", "no residents at all", "nobody in the vulnerable group within reach", "27 vulnerable residents within reach",
    ];
    for (const name of tooSmall) {
      const row = edgeCase(name);
      expect(Math.min(row[1], row[3]), name).toBeLessThan(EQUITY_MIN_GROUP);
      expect(row.slice(6), name).toEqual([null, null, TOO_SMALL, "insufficient_group_denominator"]);
      expect(gapOf(row), name).toMatchObject({ status: "insufficient_group_denominator", reason: "insufficient_group_denominator", ratio: null, band: null });
    }
    // Exactly 50 residents is enough: a ratio is given.
    expect(edgeCase("vulnerable group of exactly 50").slice(6)).toEqual([2, "higher", "Vulnerable residents are 2 times more likely to lose access.", null]);
    expect(edgeCase("other group of exactly 50").slice(6)).toEqual([0.5, "lower", "Vulnerable residents are 0.5 times as likely to lose access.", null]);
    // Every reason in the fixture is one the page knows, and it is null exactly when there is a ratio.
    const rows = [...fixture.equity_edge_cases.map((item) => item.row), ...fixture.equity_random_cases, ...fixture.access.flatMap((group) => group.levels)];
    for (const row of rows) {
      expect(row[9] === null).toBe(row[6] !== null);
      if (row[9] !== null) expect(fixture.equity_null_reasons).toContain(row[9]);
    }
    const reasons = new Set(fixture.equity_edge_cases.map((item) => item.row[9]));
    expect([...reasons]).toEqual(expect.arrayContaining([null, "insufficient_group_denominator", "no_loss", "undefined_ratio"]));
  });

  it("pins the denominator: the same lost residents give the opposite direction over all residents counted", () => {
    // Plan of 8 sites at the 3.5 m peak (rounded): 320 of 373 and 13,109 of 24,537 within reach before the flood.
    const within = edgeCase("plan of 8 at the peak, within-reach denominators");
    expect(within.slice(0, 4)).toEqual([320, 373, 13109, 24537]);
    expect(within.slice(4)).toEqual([0.8579, 0.5343, 1.606, "higher", "Vulnerable residents are 1.61 times more likely to lose access.", null]);
    // The earlier denominator, all residents counted (7,152 and 74,647), is a different input with a different answer.
    const counted = edgeCase("plan of 8 at the peak, if all residents counted");
    expect(counted.slice(0, 4)).toEqual([320, 7152, 13109, 74647]);
    expect(counted.slice(6, 8)).toEqual([0.255, "lower"]);
    expect(gapOf(within).band).not.toBe(gapOf(counted).band);
    expect(edgeCase("reported set at the peak, within-reach denominators").slice(4, 8)).toEqual([0, 0.2209, 0, "lower"]);
    // Nobody of a group within reach: no rate for that group and no ratio.
    expect(edgeCase("nobody in the vulnerable group within reach").slice(4)).toEqual([null, 0.9477, null, null, TOO_SMALL, "insufficient_group_denominator"]);
    expect(edgeCase("everyone within reach lost in both groups").slice(4, 8)).toEqual([1, 1, 1, "similar"]);
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

  it("counts the same residents within reach before the flood as Python: the denominators of the loss rates", () => {
    for (const group of fixture.access) {
      const mask = masks[group.scope];
      const summary = summarizeAccessSets(nodes, access, mask)[access.sets.indexOf(group.set)];
      const reach = withinReachBeforeFlood(scopeTotals(nodes, mask), accessSnapshot(summary, 0, access.levels).never);
      const label = `${group.set}/${group.scope}`;
      expect(reach.population, label).toBeCloseTo(group.within_reach.population, 6);
      expect(reach.vulnerable, label).toBeCloseTo(group.within_reach.vulnerable, 6);
      expect(reach.nonVulnerable, label).toBeCloseTo(group.within_reach.non_vulnerable, 6);
      expect(group.within_reach.population + group.no_baseline_access, label).toBeCloseTo(group.totals.population, 6);
      // No denominator sits on the 50-resident limit, where the browser's order of additions could change the answer.
      for (const value of [group.within_reach.vulnerable, group.within_reach.non_vulnerable]) expect(Math.abs(value - EQUITY_MIN_GROUP), label).toBeGreaterThan(1e-3);
    }
    // The denominators are not the residents counted: for the default plan only 373 of 7,152 proxy-vulnerable residents
    // had a site within reach before the flood, and none of the 103 whose homes flood had a reported site within reach.
    const group = (set: string, scope: string) => fixture.access.find((item) => item.set === set && item.scope === scope)!;
    const planAll = group(`plan_${shelters.knee_k}`, "all");
    expect([Math.round(planAll.within_reach.vulnerable), Math.round(planAll.totals.vulnerable)]).toEqual([373, 7152]);
    expect([Math.round(planAll.within_reach.non_vulnerable), Math.round(planAll.totals.non_vulnerable)]).toEqual([24537, 74647]);
    const reportedAll = group("reported_2024", "all");
    expect([Math.round(reportedAll.within_reach.vulnerable), Math.round(reportedAll.within_reach.non_vulnerable)]).toEqual([2440, 32085]);
    const reportedWet = group("reported_2024", "flooded");
    expect([reportedWet.within_reach.vulnerable, Math.round(reportedWet.totals.vulnerable)]).toEqual([0, 103]);
  });

  it("states the same Evacuation Equity Gap as Python from its own sums, at every level, set and scope", () => {
    let compared = 0;
    for (const group of fixture.access) {
      const mask = masks[group.scope];
      const summary = summarizeAccessSets(nodes, access, mask)[access.sets.indexOf(group.set)];
      const totals = scopeTotals(nodes, mask);
      for (const row of group.levels) {
        // The page's own path: lost residents over the residents within reach before the flood.
        const gap = accessEquityGap(accessSnapshot(summary, access.levels[row[0]], access.levels), totals);
        expect(pythonView(gap), `${group.set}/${group.scope} level ${row[0]}`).toEqual(row.slice(4));
        // And on Python's own sums, so the function is compared on identical inputs too.
        expect(pythonView(gapOf([row[2], group.within_reach.vulnerable, row[3], group.within_reach.non_vulnerable])), `${group.set}/${group.scope} level ${row[0]} (Python sums)`).toEqual(row.slice(4));
        compared += 1;
      }
    }
    expect(compared).toBe(fixture.access.length * access.levels.length);
    // Before the water rises nobody has lost access: the reason is no_loss, not a ratio of 1. Where a group has fewer
    // than 50 residents within reach the reason is the group size at every level, because that rule comes first.
    for (const group of fixture.access) {
      const small = Math.min(group.within_reach.vulnerable, group.within_reach.non_vulnerable) < EQUITY_MIN_GROUP;
      const reasons = new Set(group.levels.map((row) => row[9]));
      if (small) expect([...reasons], `${group.set}/${group.scope}`).toEqual(["insufficient_group_denominator"]);
      else expect(group.levels[0].slice(6), `${group.set}/${group.scope}`).toEqual([null, null, NO_LOSS, "no_loss"]);
    }
  });

  it("gives on the served data what the owners' decision records: about 1.6 for the plan of 8, no ratio in the default view", () => {
    const peakLevel = accessLevelIndex(fixture.peak_stage_m, access.levels);
    const peakRow = (set: string, scope: string) => fixture.access.find((item) => item.set === set && item.scope === scope)!.levels[peakLevel];
    // Plan of 8, all residents: 320 of 373 against 13,109 of 24,537.
    const plan = peakRow(`plan_${shelters.knee_k}`, "all");
    expect([Math.round(plan[2]), Math.round(plan[3])]).toEqual([320, 13109]);
    expect(plan.slice(4)).toEqual([0.8577, 0.5342, 1.606, "higher", "Vulnerable residents are 1.61 times more likely to lose access.", null]);
    // Reported set, all residents: none of the 2,440 proxy-vulnerable residents within reach lost access.
    const reported = peakRow("reported_2024", "all");
    expect([reported[2], Math.round(reported[3])]).toEqual([0, 7086]);
    expect(reported.slice(4, 8)).toEqual([0, 0.2208, 0, "lower"]);
    // The default view (reported set, residents whose homes flood): no proxy-vulnerable resident within reach, no ratio.
    expect(peakRow("reported_2024", "flooded").slice(4)).toEqual([null, 0.9476, null, null, TOO_SMALL, "insufficient_group_denominator"]);
    // Every result the rule can give on real data is in the fixture: both directions, no loss and too small a group.
    const seen = new Set(fixture.access.flatMap((item) => item.levels.map((row) => row[9] ?? row[7])));
    expect([...seen].sort()).toEqual(["higher", "insufficient_group_denominator", "lower", "no_loss"]);
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

describe("Shelter set comparison parity with floodguard.shelter_set_comparison (T1 scenario)", () => {
  const stages = hourlyStages(manifest.stage_anchors);
  const scoped = {
    all: { summaries: summarizeAccessSets(nodes, access, null), totals: scopeTotals(nodes, null) },
    flooded: (() => {
      const mask = floodedHomeMask(nodes, shelters.method.peak_stage_m, manifest.hand.step_m, manifest.hand.channel_code, manifest.hand.never_code);
      return { summaries: summarizeAccessSets(nodes, access, mask), totals: scopeTotals(nodes, mask) };
    })(),
  };
  const compare = (group: ComparisonGroup, stage: number) =>
    shelterSetComparison(scoped[group.scope].summaries[access.sets.indexOf(group.set)], scoped[group.scope].totals, stage, stages, access.levels);

  it("covers every shelter set of the manifest, counted for all residents and for flooded homes", () => {
    expect(fixture.set_comparison.map((group) => `${group.set}/${group.scope}`)).toEqual(access.sets.flatMap((set) => [`${set}/all`, `${set}/flooded`]));
    expect(fixture.set_comparison_hour_columns).toEqual(["hour", "keeping", "lost", "lost_share"]);
    const hours = fixture.set_comparison[0].hours.map(([hour]) => hour);
    // Before the flood, the rise, the peak and the recession are all sampled.
    expect(hours).toEqual(expect.arrayContaining([0, 46, 47, 58, 84, 263]));
  });

  it("gives Python's baseline, residents keeping access, newly lost and share at the modelled peak", () => {
    for (const group of fixture.set_comparison) {
      const label = `${group.set}/${group.scope}`;
      const row = compare(group, fixture.peak_stage_m);
      expect(row.residents, label).toBeCloseTo(group.residents, 6);
      expect(row.baseline, label).toBeCloseTo(group.baseline, 6);
      expect(row.keeping, label).toBeCloseTo(group.at_peak.keeping, 6);
      expect(row.lost, label).toBeCloseTo(group.at_peak.lost, 6);
      expect(row.lostShare, label).toBe(group.at_peak.lost_share);
      expect(row.vulnerableBaseline, label).toBeCloseTo(group.vulnerable_baseline, 6);
      expect(row.vulnerableLost, label).toBeCloseTo(group.at_peak.vulnerable_lost, 6);
    }
  });

  it("gives Python's modelled access cut-off hour for every set and scope", () => {
    const statuses = new Set<string>();
    for (const group of fixture.set_comparison) {
      const { cutoff } = compare(group, fixture.peak_stage_m);
      expect([cutoff.status, cutoff.hour], `${group.set}/${group.scope}`).toEqual([group.cutoff_status, group.cutoff_hour]);
      statuses.add(group.cutoff_status);
    }
    // Both outcomes occur on the served data.
    expect([...statuses]).toEqual(expect.arrayContaining(["reached", "not_reached"]));
  });

  it("gives Python's figures at the sampled replay hours, from before the flood to the recession", () => {
    let compared = 0;
    for (const group of fixture.set_comparison) {
      for (const [hour, keeping, lost, share] of group.hours) {
        const row = compare(group, stages[hour]);
        const label = `${group.set}/${group.scope} hour ${hour}`;
        expect(row.keeping, label).toBeCloseTo(keeping, 6);
        expect(row.lost, label).toBeCloseTo(lost, 6);
        expect(row.lostShare, label).toBe(share);
        compared += 1;
      }
    }
    expect(compared).toBe(fixture.set_comparison.length * fixture.set_comparison[0].hours.length);
  });

  it("agrees with the access rows of the same fixture, so the two Python paths say the same", () => {
    for (const group of fixture.access) {
      const twin = fixture.set_comparison.find((item) => item.set === group.set && item.scope === group.scope)!;
      const peakLevel = accessLevelIndex(fixture.peak_stage_m, access.levels);
      expect(twin.at_peak.lost, `${group.set}/${group.scope}`).toBeCloseTo(group.levels[peakLevel][1], 6);
      expect(twin.baseline + group.no_baseline_access, `${group.set}/${group.scope}`).toBeCloseTo(group.totals.population, 6);
    }
  });
});
