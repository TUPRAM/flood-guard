/**
 * Evacuation access, Evacuation Equity Gap and shelter-plan logic for the Mae Sai replay.
 *
 * Everything here is a T1 planning scenario on the modelled flood: which residents could still walk to an open,
 * dry shelter as the assumed stage rises. It is not an observation of who was cut off, and not a warning.
 * Mirrors `scripts/mae_sai_timeline_evacuation.py` (`lost_at`) and `floodguard.equity` (`_compute_row_equity`).
 * No DOM access in this module.
 */

import {
  roundLikePython,
  type AccessDayStats,
  type AccessInfo,
  type Language,
  type ReportedShelter,
  type ShelterCandidate,
  type ShelterInfo,
  type ShelterPlanEntry,
} from "./flood-timeline";

/** Cut code for nodes that keep access at every evaluated level. */
export const NEVER_LOST_CODE = 254;
/** Cut code for nodes without a shelter of the set within reach even before the flood (level 0). */
export const NO_BASELINE_CODE = 255;
/** Shelter set of the sites reported in use in September 2024. */
export const REPORTED_SET_ID = "reported_2024";
/** Shelter set of the first `k` sites of the ranked plan. */
export const planSetId = (k: number): string => `plan_${k}`;

// --- Access node file ----------------------------------------------------------------------------

/** Decoded `access-nodes.bin`: one entry per resident node, cut codes set-major. */
export interface AccessNodes {
  count: number;
  lon: Float32Array;
  lat: Float32Array;
  population: Float32Array;
  vulnerable: Float32Array;
  /** 1-based index into `access.tambons`; 0 = none. */
  tambonIndex: Uint8Array;
  homeCode: Uint8Array;
  homeK: Uint8Array;
  /** Row `s` (shelter set `access.sets[s]`) covers bytes `[s * count, (s + 1) * count)`. */
  cutCodes: Uint8Array;
  setCount: number;
}

const FIELD_DTYPES = {
  lon: "float32",
  lat: "float32",
  population: "float32",
  vulnerable_population: "float32",
  tambon_index: "uint8",
  home_code: "uint8",
  home_k: "uint8",
  cut_codes: "uint8",
} as const;

/**
 * Decode the access node file per the manifest layout (little-endian float32 and uint8 columns; `cut_codes`
 * shaped [sets][count]). Fails closed when the size, a field, its type or its extent does not match the manifest.
 */
export function parseAccessNodes(input: ArrayBuffer | Uint8Array, access: Pick<AccessInfo, "nodes" | "sets">): AccessNodes {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const { count, layout } = access.nodes;
  if (!Number.isSafeInteger(count) || count <= 0) throw new Error("Access node count is invalid");
  if (bytes.byteLength !== access.nodes.bytes) throw new Error("Access node file size differs from the manifest");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const setCount = access.sets.length;
  const field = (name: keyof typeof FIELD_DTYPES, rows: number, width: number) => {
    const entry = layout.find((item) => item.name === name);
    if (!entry) throw new Error(`Access node field missing: ${name}`);
    if (entry.dtype !== FIELD_DTYPES[name]) throw new Error(`Access node field ${name} has type ${entry.dtype}`);
    const end = entry.offset + rows * count * width;
    if (!Number.isSafeInteger(entry.offset) || entry.offset < 0 || end > bytes.byteLength) throw new Error(`Access node field ${name} lies outside the file`);
    if (entry.shape && (entry.shape.length !== 2 || entry.shape[0] !== rows || entry.shape[1] !== count)) {
      throw new Error(`Access node field ${name} has shape ${JSON.stringify(entry.shape)}`);
    }
    return entry.offset;
  };
  const float32 = (name: keyof typeof FIELD_DTYPES) => {
    const offset = field(name, 1, 4);
    const out = new Float32Array(count);
    for (let index = 0; index < count; index += 1) out[index] = view.getFloat32(offset + index * 4, true);
    return out;
  };
  const uint8 = (name: keyof typeof FIELD_DTYPES, rows = 1) => {
    const offset = field(name, rows, 1);
    return bytes.slice(offset, offset + rows * count);
  };
  if (setCount === 0) throw new Error("The access scenario lists no shelter sets");
  return {
    count,
    lon: float32("lon"),
    lat: float32("lat"),
    population: float32("population"),
    vulnerable: float32("vulnerable_population"),
    tambonIndex: uint8("tambon_index"),
    homeCode: uint8("home_code"),
    homeK: uint8("home_k"),
    cutCodes: uint8("cut_codes", setCount),
    setCount,
  };
}

// --- Access at a stage -----------------------------------------------------------------------------

/** Spacing of the evaluated stage levels (0.05 m), rounded to 1e-6 m. */
export function accessLevelStep(levels: readonly number[]): number {
  return levels.length > 1 ? roundLikePython(levels[1] - levels[0], 6) : 0.05;
}

/** Index of the evaluated level in force at `stage`: floor(stage / step + 1e-6), as in the Python `lost_at`. */
export function accessLevelIndex(stage: number, levels: readonly number[]): number {
  return Math.floor(stage / accessLevelStep(levels) + 1e-6);
}

/** A node has lost access at a level when it had baseline access and its cut code is at or below that level. */
export function nodeLostAccess(code: number, levelIndex: number): boolean {
  return code !== NEVER_LOST_CODE && code !== NO_BASELINE_CODE && code <= levelIndex;
}

/** Without access: lost during the flood, or never within reach of the set (code 255). */
export function nodeWithoutAccess(code: number, levelIndex: number): boolean {
  return code === NO_BASELINE_CODE || nodeLostAccess(code, levelIndex);
}

export interface AccessGroupSums { population: number; vulnerable: number; nonVulnerable: number }

/**
 * Per shelter set: running sums of residents by cut code so any stage is answered in O(1) (plus one pass over
 * subdistricts). `cumulative.*[c]` = everyone whose cut code is 0..c, i.e. lost once the level index reaches c.
 */
export interface AccessSetSummary {
  id: string;
  tambonCount: number;
  cumulative: { population: Float64Array; vulnerable: Float64Array; nonVulnerable: Float64Array; tambon: Float64Array };
  never: AccessGroupSums & { tambon: Float64Array };
}

const CUT_CODES = NEVER_LOST_CODE; // cut codes 0..253 are level indices

// --- Population scope: whose access is counted ------------------------------------------------------

/**
 * Which residents the access figures count: those whose home node floods at the modelled peak (the people the
 * ranked plan is built for) or every resident snapped to a road node.
 */
export type AccessScope = "flooded" | "all";
export const ACCESS_SCOPES: readonly AccessScope[] = ["flooded", "all"];

/**
 * Whether a resident node's home is wet at `stage`: the same rule as the builder's `home_wet` (a channel home is wet
 * as soon as the stage rises; the never code never floods; otherwise code * step < stage).
 */
export function homeWetAt(homeCode: number, stage: number, step: number, channelCode = 0, neverCode = 255): boolean {
  if (homeCode === neverCode || !(stage > 0)) return false;
  return homeCode === channelCode || homeCode * step < stage;
}

/** 1 for each node whose home is wet at `stage` (e.g. the modelled peak), else 0. */
export function floodedHomeMask(nodes: Pick<AccessNodes, "count" | "homeCode">, stage: number, step: number, channelCode = 0, neverCode = 255): Uint8Array {
  const mask = new Uint8Array(nodes.count);
  for (let node = 0; node < nodes.count; node += 1) mask[node] = homeWetAt(nodes.homeCode[node], stage, step, channelCode, neverCode) ? 1 : 0;
  return mask;
}

/** Residents (all, proxy-vulnerable and everyone else) of the nodes in `mask` (every node without one). */
export function scopeTotals(nodes: Pick<AccessNodes, "count" | "population" | "vulnerable">, mask?: Uint8Array | null): AccessGroupSums {
  let population = 0;
  let vulnerable = 0;
  for (let node = 0; node < nodes.count; node += 1) {
    if (mask && !mask[node]) continue;
    population += nodes.population[node];
    vulnerable += nodes.vulnerable[node];
  }
  return { population, vulnerable, nonVulnerable: population - vulnerable };
}

/**
 * Build the per-set cumulative histograms once after the node file loads. With `mask`, only the nodes it marks
 * (e.g. homes that flood at the peak) are counted.
 */
export function summarizeAccessSets(nodes: AccessNodes, access: Pick<AccessInfo, "sets" | "tambons">, mask?: Uint8Array | null): AccessSetSummary[] {
  const tambonCount = access.tambons.length;
  if (mask && mask.length !== nodes.count) throw new Error("The scope mask must cover every access node");
  return access.sets.map((id, setIndex) => {
    const population = new Float64Array(CUT_CODES);
    const vulnerable = new Float64Array(CUT_CODES);
    const nonVulnerable = new Float64Array(CUT_CODES);
    const tambon = new Float64Array(CUT_CODES * tambonCount);
    const never = { population: 0, vulnerable: 0, nonVulnerable: 0, tambon: new Float64Array(tambonCount) };
    const row = setIndex * nodes.count;
    for (let node = 0; node < nodes.count; node += 1) {
      if (mask && !mask[node]) continue;
      const code = nodes.cutCodes[row + node];
      if (code === NEVER_LOST_CODE) continue;
      const people = nodes.population[node];
      const vulnerablePeople = nodes.vulnerable[node];
      const place = nodes.tambonIndex[node] - 1;
      if (code === NO_BASELINE_CODE) {
        never.population += people;
        never.vulnerable += vulnerablePeople;
        never.nonVulnerable += people - vulnerablePeople;
        if (place >= 0 && place < tambonCount) never.tambon[place] += people;
        continue;
      }
      population[code] += people;
      vulnerable[code] += vulnerablePeople;
      nonVulnerable[code] += people - vulnerablePeople;
      if (place >= 0 && place < tambonCount) tambon[code * tambonCount + place] += people;
    }
    for (let code = 1; code < CUT_CODES; code += 1) {
      population[code] += population[code - 1];
      vulnerable[code] += vulnerable[code - 1];
      nonVulnerable[code] += nonVulnerable[code - 1];
      for (let place = 0; place < tambonCount; place += 1) tambon[code * tambonCount + place] += tambon[(code - 1) * tambonCount + place];
    }
    return { id, tambonCount, cumulative: { population, vulnerable, nonVulnerable, tambon }, never };
  });
}

export interface AccessSnapshot {
  levelIndex: number;
  /** Residents who had a shelter of the set within reach before the flood and lost it by this stage. */
  lost: AccessGroupSums;
  /** Residents with no shelter of the set within reach even before the flood. */
  never: AccessGroupSums;
  /** Per subdistrict, in `access.tambons` order. */
  lostByTambon: number[];
  neverByTambon: number[];
}

const clampCode = (levelIndex: number) => Math.min(CUT_CODES - 1, levelIndex);

/** Residents lost (people only) for one set at `stage`: O(1). */
export function peopleLostAt(summary: AccessSetSummary, stage: number, levels: readonly number[]): number {
  const index = accessLevelIndex(stage, levels);
  return index < 0 ? 0 : summary.cumulative.population[clampCode(index)];
}

/** Access for one shelter set at `stage` (unrounded). */
export function accessSnapshot(summary: AccessSetSummary, stage: number, levels: readonly number[]): AccessSnapshot {
  const levelIndex = accessLevelIndex(stage, levels);
  const code = clampCode(levelIndex);
  const any = levelIndex >= 0;
  const { cumulative, never, tambonCount } = summary;
  return {
    levelIndex,
    lost: {
      population: any ? cumulative.population[code] : 0,
      vulnerable: any ? cumulative.vulnerable[code] : 0,
      nonVulnerable: any ? cumulative.nonVulnerable[code] : 0,
    },
    never: { population: never.population, vulnerable: never.vulnerable, nonVulnerable: never.nonVulnerable },
    lostByTambon: Array.from({ length: tambonCount }, (_, place) => (any ? cumulative.tambon[code * tambonCount + place] : 0)),
    neverByTambon: Array.from(never.tambon),
  };
}

/** Access figures for one set at `stage`, rounded exactly like the baked `days[].stats.access[set]`. */
export function accessDayStats(summary: AccessSetSummary, stage: number, levels: readonly number[]): AccessDayStats {
  const { lost } = accessSnapshot(summary, stage, levels);
  return {
    people_lost_access: roundLikePython(lost.population, 0),
    vulnerable_lost: roundLikePython(lost.vulnerable, 1),
    non_vulnerable_lost: roundLikePython(lost.nonVulnerable, 1),
  };
}

/** People who have lost access at each sampled stage (e.g. the replay's hourly stages), for the replay chart. */
export function accessLostSeries(summary: AccessSetSummary, stages: ArrayLike<number>, levels: readonly number[]): Float64Array {
  const out = new Float64Array(stages.length);
  for (let index = 0; index < stages.length; index += 1) out[index] = peopleLostAt(summary, stages[index], levels);
  return out;
}

/** Resident nodes' population per subdistrict (in `access.tambons` order), for bar scales; `mask` limits the nodes. */
export function tambonResidents(nodes: AccessNodes, tambonCount: number, mask?: Uint8Array | null): Float64Array {
  const out = new Float64Array(tambonCount);
  for (let node = 0; node < nodes.count; node += 1) {
    if (mask && !mask[node]) continue;
    const place = nodes.tambonIndex[node] - 1;
    if (place >= 0 && place < tambonCount) out[place] += nodes.population[node];
  }
  return out;
}

// --- "People cut off" heat -------------------------------------------------------------------------------

/** Opacity weight of one lost node's blob: grows with the square root of its residents, full at 100 people. */
export function cutoffWeight(people: number): number {
  return people > 0 ? Math.min(1, Math.sqrt(people) / 10) : 0;
}

/** Heat ramp stops (accumulated blob alpha 0-255 → colour): pale lilac to deep purple, distinct from the water blues. */
export const CUTOFF_RAMP: readonly (readonly [number, readonly [number, number, number, number]])[] = [
  [1, [214, 188, 250, 40]],
  [96, [170, 110, 225, 120]],
  [192, [120, 40, 170, 170]],
  [255, [70, 0, 120, 200]],
];

/**
 * 256-entry packed colour ramp for the heat's accumulated alpha (index 0 transparent), little-endian ABGR
 * by default like the water LUTs.
 */
export function buildCutoffRamp(littleEndian = true): Uint32Array {
  const out = new Uint32Array(256);
  for (let value = 1; value < 256; value += 1) {
    const upper = Math.max(0, CUTOFF_RAMP.findIndex(([at]) => at >= value));
    const [toAt, to] = CUTOFF_RAMP[upper];
    const [fromAt, from] = CUTOFF_RAMP[Math.max(0, upper - 1)];
    const share = toAt === fromAt ? 1 : (value - fromAt) / (toAt - fromAt);
    const [r, g, b, a] = from.map((channel, index) => Math.round(channel + (to[index] - channel) * share));
    out[value] = (littleEndian ? ((a << 24) | (b << 16) | (g << 8) | r) : ((r << 24) | (g << 16) | (b << 8) | a)) >>> 0;
  }
  return out;
}

// --- Evacuation Equity Gap -----------------------------------------------------------------------------

export type EquityStatus = "no_vulnerable_denominator" | "no_non_vulnerable_denominator" | "no_loss" | "undefined_ratio" | "ratio";

export interface EquityGap {
  status: EquityStatus;
  vulnerableRate: number | null;
  nonVulnerableRate: number | null;
  /** (vulnerable lost / vulnerable total) / (non-vulnerable lost / non-vulnerable total), rounded to 3 decimals. */
  ratio: number | null;
  /** "higher" when ratio > 1.2, "lower" when ratio < 0.8, else "similar"; null without a ratio. */
  band: "higher" | "lower" | "similar" | null;
  /** English interpretation, word for word as `floodguard.equity`. */
  interpretation: string;
}

export interface EquityInput { vulnerableLost: number; vulnerableTotal: number; nonVulnerableLost: number; nonVulnerableTotal: number }

/** Python `format(value, ".3g")` for a finite number. */
export function formatSignificant3(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return "0";
  const [mantissa, exponentText] = Math.abs(value).toExponential(2).split("e");
  const exponent = Number(exponentText);
  const sign = value < 0 ? "-" : "";
  if (exponent < -4 || exponent >= 3) {
    const digits = mantissa.replace(/\.?0+$/, "");
    return `${sign}${digits}e${exponent < 0 ? "-" : "+"}${String(Math.abs(exponent)).padStart(2, "0")}`;
  }
  const fixed = Math.abs(value).toFixed(Math.max(0, 2 - exponent));
  return `${sign}${fixed.includes(".") ? fixed.replace(/\.?0+$/, "") : fixed}`;
}

const rate = (numerator: number, denominator: number) => roundLikePython(numerator / denominator, 4);

/**
 * Evacuation Equity Gap with the same rules as `floodguard.equity._compute_row_equity`: rates rounded to 4
 * decimals, ratio to 3; undefined when a denominator is zero or when only vulnerable residents lose access;
 * 1.0 when neither group loses access.
 */
export function evacuationEquityGap(input: EquityInput): EquityGap {
  const { vulnerableLost, vulnerableTotal, nonVulnerableLost, nonVulnerableTotal } = input;
  if (vulnerableTotal === 0) {
    return {
      status: "no_vulnerable_denominator",
      vulnerableRate: null,
      nonVulnerableRate: nonVulnerableTotal === 0 ? null : rate(nonVulnerableLost, nonVulnerableTotal),
      ratio: null,
      band: null,
      interpretation: "Equity gap unavailable: no vulnerable population denominator.",
    };
  }
  if (nonVulnerableTotal === 0) {
    return {
      status: "no_non_vulnerable_denominator",
      vulnerableRate: rate(vulnerableLost, vulnerableTotal),
      nonVulnerableRate: null,
      ratio: null,
      band: null,
      interpretation: "Equity gap unavailable: no non-vulnerable population denominator.",
    };
  }
  const vulnerableRate = rate(vulnerableLost, vulnerableTotal);
  const nonVulnerableRate = rate(nonVulnerableLost, nonVulnerableTotal);
  if (vulnerableRate === 0 && nonVulnerableRate === 0) {
    return {
      status: "no_loss", vulnerableRate, nonVulnerableRate, ratio: 1, band: "similar",
      interpretation: "No measured access-loss gap; both groups have zero loss.",
    };
  }
  if (nonVulnerableRate === 0 && vulnerableRate > 0) {
    return {
      status: "undefined_ratio", vulnerableRate, nonVulnerableRate, ratio: null, band: null,
      interpretation: "Equity gap ratio undefined because vulnerable loss exists while non-vulnerable loss is zero.",
    };
  }
  const ratio = roundLikePython(vulnerableRate / nonVulnerableRate, 3);
  const band = ratio > 1.2 ? "higher" : ratio < 0.8 ? "lower" : "similar";
  const interpretation = band === "higher"
    ? `Vulnerable residents are ${formatSignificant3(ratio)} times more likely to lose access.`
    : band === "lower"
      ? `Vulnerable residents are ${formatSignificant3(ratio)} times as likely to lose access.`
      : "Access-loss rates are broadly similar between groups.";
  return { status: "ratio", vulnerableRate, nonVulnerableRate, ratio, band, interpretation };
}

/** How the page states the gap: the headline value and a plain sentence (empty when the value says it all). */
export interface EquityWording { value: string; sentence: string }

/** A loss rate as a percentage with two decimals ("0.18%"). */
export const formatRate = (rate: number): string => `${(rate * 100).toFixed(2)}%`;
/** "about N×" amount: whole numbers from 10, one decimal below. */
const timesText = (value: number) => (value >= 10 ? String(Math.round(value)) : value.toFixed(1));

/**
 * Page wording of the Evacuation Equity Gap: a fixed two-decimal ratio and a plain comparison of the two loss rates
 * ("about 50× less likely (0.18% vs 9.60%)"). "—" when nobody has lost access, "undefined" when only proxy-vulnerable
 * residents have. The ratio and its rules stay those of `evacuationEquityGap`.
 */
export function equityWording(gap: EquityGap, language: Language): EquityWording {
  const th = language === "th";
  const v = gap.vulnerableRate ?? 0;
  const o = gap.nonVulnerableRate ?? 0;
  const pair = th ? `(${formatRate(v)} เทียบกับ ${formatRate(o)})` : `(${formatRate(v)} vs ${formatRate(o)})`;
  switch (gap.status) {
    case "no_vulnerable_denominator":
      return { value: "—", sentence: th ? "คำนวณไม่ได้: ไม่มีผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนในขอบเขตนี้" : "Not available: no proxy-vulnerable residents are counted in this scope." };
    case "no_non_vulnerable_denominator":
      return { value: "—", sentence: th ? "คำนวณไม่ได้: ไม่มีผู้อยู่อาศัยกลุ่มอื่นในขอบเขตนี้" : "Not available: no other residents are counted in this scope." };
    case "no_loss":
      return { value: th ? "— (ยังไม่มีผู้ใดสูญเสียการเข้าถึง)" : "— (no one has lost access yet)", sentence: "" };
    case "undefined_ratio":
      return {
        value: th ? "หาค่าไม่ได้" : "undefined",
        sentence: th
          ? `มีเพียงกลุ่มเปราะบางตามตัวแทนที่สูญเสียการเข้าถึง ${pair} จึงคำนวณอัตราส่วนไม่ได้`
          : `Only proxy-vulnerable residents have lost access ${pair}, so the ratio cannot be computed.`,
      };
    default: {
      const value = (gap.ratio ?? 0).toFixed(2);
      if (gap.band === "higher") {
        return { value, sentence: th
          ? `ผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนมีโอกาสสูญเสียการเข้าถึงมากกว่าประมาณ ${timesText(v / o)} เท่า ${pair}`
          : `Proxy-vulnerable residents are about ${timesText(v / o)}× more likely to lose access ${pair}.` };
      }
      if (gap.band === "lower") {
        if (v === 0) {
          return { value, sentence: th
            ? `ยังไม่มีผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนสูญเสียการเข้าถึง ขณะที่กลุ่มอื่นสูญเสีย ${formatRate(o)}`
            : `No proxy-vulnerable resident has lost access, against ${formatRate(o)} of everyone else.` };
        }
        return { value, sentence: th
          ? `ผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนมีโอกาสสูญเสียการเข้าถึงน้อยกว่าประมาณ ${timesText(o / v)} เท่า ${pair}`
          : `Proxy-vulnerable residents are about ${timesText(o / v)}× less likely to lose access ${pair}.` };
      }
      return { value, sentence: th
        ? `ผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนมีโอกาสสูญเสียการเข้าถึงใกล้เคียงกับกลุ่มอื่น ${pair}`
        : `Proxy-vulnerable residents are about as likely as everyone else to lose access ${pair}.` };
    }
  }
}

/**
 * One plain line on why the proxy points the way it does, when proxy-vulnerable residents are the less affected
 * group (null otherwise): the proxy marks hillside and remote homes, which stay dry in this valley-floor flood.
 */
export function equityWhy(gap: EquityGap, language: Language): string | null {
  if (gap.status !== "ratio" || gap.band !== "lower") return null;
  return language === "th"
    ? "เหตุที่เป็นเช่นนี้: ตัวแทนนี้ระบุบ้านบนที่ลาดชันหรือห่างถนน ซึ่งส่วนใหญ่อยู่บนเนินและพื้นที่ห่างไกลที่น้ำไม่ท่วม ขณะที่น้ำท่วมพื้นที่ราบริมน้ำที่คนส่วนใหญ่อาศัยอยู่"
    : "Why it points this way here: the proxy marks homes on slopes or far from a drivable road, mostly hillside and remote homes that stay dry, while this flood covers the valley floor, where most homes are.";
}

// --- Shelter plan ---------------------------------------------------------------------------------------

/** A plan size within 1 … plan length (the knee when `k` is not a whole number). */
export function clampPlanK(k: number, shelters: Pick<ShelterInfo, "plan" | "knee_k">): number {
  const size = shelters.plan.length;
  if (size === 0) return 0;
  const value = Number.isFinite(k) ? Math.round(k) : shelters.knee_k;
  return Math.min(size, Math.max(1, value));
}

/** True when the residents assigned to a site exceed its capacity estimate (unknown capacity never counts). */
export function capacityShortfall(load: number, capacity: number | null): boolean {
  return capacity !== null && load > capacity;
}

export interface PlannedShelter {
  /** 1-based rank in the greedy plan. */
  rank: number;
  candidate: ShelterCandidate;
  entry: ShelterPlanEntry;
  /** Residents assigned to this site when the plan has `k` sites (`plan[k - 1].loads[rank - 1]`). */
  load: number;
  capacity: number | null;
  shortfall: boolean;
}

/**
 * The first `k` sites of the ranked plan with their loads for a plan of size `k`. Greedy plans are nested:
 * the first k entries are the plan for k shelters.
 */
export function planSites(shelters: Pick<ShelterInfo, "candidates" | "plan">, k: number): PlannedShelter[] {
  const byId = new Map(shelters.candidates.map((candidate) => [candidate.id, candidate]));
  const size = Math.min(Math.max(0, Math.floor(k)), shelters.plan.length);
  if (size === 0) return [];
  const loads = shelters.plan[size - 1].loads;
  return shelters.plan.slice(0, size).map((entry, index) => {
    const candidate = byId.get(entry.candidate_id);
    if (!candidate) throw new Error(`Plan names an unknown candidate: ${entry.candidate_id}`);
    const load = loads[index] ?? 0;
    return { rank: index + 1, candidate, entry, load, capacity: candidate.capacity_est, shortfall: capacityShortfall(load, candidate.capacity_est) };
  });
}

/** A plan site's load is "far above" its capacity estimate from this multiple on. */
export const FAR_OVER_CAPACITY = 2;

/**
 * Capacity warning for a plan site: "unknown" without a capacity estimate, "far_below" when the capacity estimate is
 * less than half the residents assigned to it, else null.
 */
export function capacityFlag(site: Pick<PlannedShelter, "load" | "capacity">): "unknown" | "far_below" | null {
  if (site.capacity === null) return "unknown";
  return site.load > site.capacity && site.load >= FAR_OVER_CAPACITY * site.capacity ? "far_below" : null;
}

const wholePeople = (value: number) => Math.round(value).toLocaleString("en-US");

/**
 * Live sentence next to the plan-size slider: "k = 3: 3 sites cover 5,725 of 14,169 residents whose homes flood
 * (40%) · late evacuation 23%", from the plan's cumulative coverage at size `k`.
 */
export function planCoverageSentence(shelters: Pick<ShelterInfo, "plan" | "demand_people">, k: number, language: Language): string {
  const size = Math.min(Math.max(1, Math.round(k)), shelters.plan.length);
  const entry = shelters.plan[size - 1];
  if (!entry) return "";
  const share = `${Math.round(entry.cumulative_share * 100)}%`;
  const late = `${Math.round(entry.late_cumulative_share * 100)}%`;
  return language === "th"
    ? `k = ${size}: ที่พักพิง ${size} แห่งครอบคลุม ${wholePeople(entry.cumulative_demand)} จาก ${wholePeople(shelters.demand_people)} คนที่บ้านถูกน้ำท่วม (${share}) · อพยพล่าช้า ${late}`
    : `k = ${size}: ${size} site${size === 1 ? "" : "s"} cover${size === 1 ? "s" : ""} ${wholePeople(entry.cumulative_demand)} of ${wholePeople(shelters.demand_people)} residents whose homes flood (${share}) · late evacuation ${late}`;
}

/** Share (0-1) of the achievable coverage (the full ranking's cumulative demand) that the first `k` sites reach. */
export function shareOfAchievable(plan: readonly ShelterPlanEntry[], k: number): number {
  const best = plan.at(-1)?.cumulative_demand ?? 0;
  if (!(best > 0) || k < 1) return 0;
  return plan[Math.min(k, plan.length) - 1].cumulative_demand / best;
}

export type ReportedCheck =
  | { status: "not_located" }
  | { status: "not_modelled" }
  | { status: "floods"; freeboard: number | null }
  | { status: "high_ground" }
  | { status: "dry"; freeboard: number }
  | { status: "unchecked" };

/**
 * What the reconstruction says about a reported shelter's mapped location at the modelled peak; a location outside
 * the terrain model (`model_check.m` false) has no result.
 */
export function reportedShelterCheck(shelter: Pick<ReportedShelter, "lat" | "lon" | "model_check">): ReportedCheck {
  const check = shelter.model_check;
  if (shelter.lat === null || shelter.lon === null || !check) return { status: "not_located" };
  if (!check.m) return { status: "not_modelled" };
  if (check.floods_at_modelled_peak) return { status: "floods", freeboard: check.freeboard_m };
  if (check.high_ground) return { status: "high_ground" };
  if (check.freeboard_m !== null) return { status: "dry", freeboard: check.freeboard_m };
  return { status: "unchecked" };
}

/** Plan candidates outside the first `k` ranked sites, split into eligible and ineligible ones (manifest order). */
export function otherCandidates(shelters: Pick<ShelterInfo, "candidates" | "plan">, k: number): { eligible: ShelterCandidate[]; ineligible: ShelterCandidate[] } {
  const inPlan = new Set(shelters.plan.slice(0, Math.max(0, Math.floor(k))).map((entry) => entry.candidate_id));
  const rest = shelters.candidates.filter((candidate) => !inPlan.has(candidate.id));
  return { eligible: rest.filter((candidate) => candidate.eligible), ineligible: rest.filter((candidate) => !candidate.eligible) };
}

// --- Reported sites and the "reported_2024" access set ---------------------------------------------------

/** True when the site has map coordinates (unlocated sites are listed but never mapped, checked or counted). */
export function reportedLocated(shelter: Pick<ReportedShelter, "lat" | "lon">): boolean {
  return shelter.lat !== null && shelter.lon !== null;
}

/**
 * Whether the precomputed "reported_2024" access set counts the site: the manifest's `in_access_set`, which the build
 * applies to located sites only (see `shelters.reported_access_set_rule`).
 */
export function countedInReportedSet(shelter: Pick<ReportedShelter, "lat" | "lon" | "in_access_set">): boolean {
  return shelter.in_access_set && reportedLocated(shelter);
}

/** Whether a plan candidate lies inside the terrain model (manifest `m`); outside it there is no flood result. */
export function siteModelled(candidate: Pick<ShelterCandidate, "m">): boolean {
  return candidate.m !== false;
}

/** A candidate's ineligibility reasons exactly as the manifest records them (empty when eligible). */
export function candidateReasons(candidate: Pick<ShelterCandidate, "eligible" | "ineligible_reasons">): string[] {
  return candidate.eligible ? [] : [...candidate.ineligible_reasons];
}

/** Map symbol group for a reported site, from its manifest role. */
export function reportedSiteRole(shelter: Pick<ReportedShelter, "role">): { role: "shelter" | "relief_command" } {
  return { role: shelter.role === "relief_command_centre" ? "relief_command" : "shelter" };
}

/** Reported sites by manifest role, plus how many of them the "reported_2024" access set counts. */
export function reportedSiteCounts(shelters: Pick<ShelterInfo, "reported">): { total: number; shelters: number; commandCentres: number; counted: number } {
  const reported = shelters.reported;
  return {
    total: reported.length,
    shelters: reported.filter((shelter) => shelter.role === "shelter").length,
    commandCentres: reported.filter((shelter) => shelter.role === "relief_command_centre").length,
    counted: reported.filter(countedInReportedSet).length,
  };
}

/** Mapped reported sites that the "reported_2024" access set leaves out (manifest `in_access_set` false). */
export function reportedSetExclusions(shelters: Pick<ShelterInfo, "reported">): ReportedShelter[] {
  return shelters.reported.filter((shelter) => reportedLocated(shelter) && !shelter.in_access_set);
}

/** "OSM way/106085171" → { type: "way", id: "106085171", url } (null for anything else). */
export function osmReference(source: string): { type: string; id: string; url: string } | null {
  const match = /^OSM (node|way|relation)\/(\d+)$/.exec(source.trim());
  return match ? { type: match[1], id: match[2], url: `https://www.openstreetmap.org/${match[1]}/${match[2]}` } : null;
}
