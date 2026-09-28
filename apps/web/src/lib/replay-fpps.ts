/**
 * Scenario FPPS for the Mae Sai replay: turns the replay's per-subdistrict figures at the current moment (reconstructed
 * water, WorldPop residents in water, walking access to the chosen shelter set, impassable roads, proxy vulnerability)
 * into the five 0–100 FPPS components, then scores them with the locked `floodguard.scoring` rules (`./fpps`).
 *
 * The components use fixed, versioned scale anchors (`REPLAY_FPPS_ANCHORS`), never min–max across subdistricts, so a
 * score means the same thing at every moment and does not jump when another subdistrict changes. The result stays in
 * the replay: the manifest's `can_feed_decision_layer` is false, so nothing here is written to the Planning areas.
 */

import type { ActionClass, ConfidenceClass } from "@floodguard/contracts";

import { accessLevelIndex, nodeWithoutAccess, type AccessNodes } from "./flood-timeline-evacuation";
import { roadState, type RoadProps } from "./flood-timeline";
import {
  assignActionClass,
  componentPoints,
  DEFAULT_FPPS_WEIGHTS,
  FPPS_COMPONENTS,
  scoreSubdistrict,
  type ActionReasonCode,
  type FppsComponent,
  type FppsComponents,
  type FppsWeights,
} from "./fpps";

/** Scale anchors: the raw value that maps to a full 100. Change them only with a new `version`. */
export const REPLAY_FPPS_ANCHORS = {
  version: "replay_fpps_anchor_v1",
  /** Share of a subdistrict's modelled area under reconstructed water that counts as certain flooding. */
  floodSaturationShare: 0.25,
  /** Exposure is half "how much of the place" and half "how many people". */
  exposureShareSaturation: 0.25,
  exposurePeopleSaturation: 5000,
  /** Class-weighted share of modelled road length that is impassable (≥ 0.3 m) for a full road score. */
  roadSaturationShare: 0.5,
  /** Share of residents in the terrain/remoteness vulnerability proxy for a full context score. */
  vulnerableSaturationShare: 0.25,
} as const;

/** Road class weight for road criticality: main through-routes count three times a residential street. */
export const ROAD_CLASS_WEIGHT: Readonly<Record<string, number>> = {
  trunk: 3,
  primary: 3,
  secondary: 2,
  tertiary: 2,
};
const roadWeight = (roadClass: string) => ROAD_CLASS_WEIGHT[roadClass] ?? 1;

const clamp100 = (value: number) => Math.min(100, Math.max(0, value));
const share = (part: number, whole: number) => (whole > 0 ? part / whole : 0);

/** Raw per-subdistrict figures a score is built from, kept so the page can show the working. */
export interface ReplayFppsRaw {
  floodedKm2: number;
  modelledKm2: number;
  residents: number;
  peopleInWater: number;
  /** Residents at road nodes (the access scenario's own denominator). */
  nodeResidents: number;
  /** Node residents whose home is in reconstructed water now: the people who need to evacuate. */
  evacuees: number;
  /** Of those, residents with no open dry shelter of the chosen set within the 2 km walk. */
  evacueesWithoutAccess: number;
  vulnerableResidents: number;
  roadWeightedKm: number;
  roadWeightedImpassableKm: number;
}

export interface ReplayFppsRow {
  id: string;
  raw: ReplayFppsRaw;
  components: FppsComponents;
  /** Weighted points of each component; they add up to the unrounded score. */
  points: FppsComponents;
  fpps_0_100: number;
  action_class: ActionClass;
  action_reason_code: ActionReasonCode;
  top_reason: string;
  /** Class the same score would get if the inputs were verified to medium confidence (never shown as the class). */
  score_implied_class: ActionClass;
  rank: number;
}

/** Static per-subdistrict road length (km), class-weighted, over modelled pieces only. */
export function tambonRoadWeights(roads: readonly Pick<RoadProps, "c" | "len" | "m" | "t">[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const road of roads) {
    if (!road.m) continue;
    out[road.t] = (out[road.t] ?? 0) + (roadWeight(road.c) * road.len) / 1000;
  }
  return out;
}

/** Class-weighted impassable road km per subdistrict at `stage` (same rule as the replay's road states). */
export function tambonImpassableRoads(
  roads: readonly Pick<RoadProps, "c" | "len" | "m" | "t" | "h" | "k">[],
  stage: number,
  impassableDepthM: number,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const road of roads) {
    if (!road.m || roadState(road.h, stage, impassableDepthM, road.k ?? 1) !== "impassable") continue;
    out[road.t] = (out[road.t] ?? 0) + (roadWeight(road.c) * road.len) / 1000;
  }
  return out;
}

const CHANNEL_CODE = 0;
const NEVER_CODE = 255;

/** A node's home is wet at `stage`: the Python `home_wet` rule (channel homes are wet as soon as the stage rises). */
export function nodeHomeWet(homeCode: number, stage: number, step: number): boolean {
  return homeCode !== NEVER_CODE && stage > 0 && (homeCode === CHANNEL_CODE || homeCode * step < stage);
}

export interface EvacuationNeed {
  /** Per subdistrict (`access.tambons` order): node residents whose home is wet now. */
  evacuees: Float64Array;
  /** Of those, residents without a dry shelter of the set within reach (lost during the flood or never had one). */
  withoutAccess: Float64Array;
}

/** Who needs to evacuate now and cannot walk to a dry shelter of shelter set `setIndex`, per subdistrict. */
export function evacuationNeed(
  nodes: Pick<AccessNodes, "count" | "population" | "tambonIndex" | "homeCode" | "cutCodes">,
  setIndex: number,
  stage: number,
  levels: readonly number[],
  step: number,
  tambonCount: number,
): EvacuationNeed {
  const evacuees = new Float64Array(tambonCount);
  const withoutAccess = new Float64Array(tambonCount);
  const levelIndex = accessLevelIndex(stage, levels);
  const row = setIndex * nodes.count;
  for (let node = 0; node < nodes.count; node += 1) {
    const place = nodes.tambonIndex[node] - 1;
    if (place < 0 || place >= tambonCount || !nodeHomeWet(nodes.homeCode[node], stage, step)) continue;
    const people = nodes.population[node];
    evacuees[place] += people;
    if (nodeWithoutAccess(nodes.cutCodes[row + node], levelIndex)) withoutAccess[place] += people;
  }
  return { evacuees, withoutAccess };
}

/** Proxy-vulnerable residents per subdistrict, in `access.tambons` order. */
export function tambonVulnerable(nodes: Pick<AccessNodes, "count" | "vulnerable" | "tambonIndex">, tambonCount: number): Float64Array {
  const out = new Float64Array(tambonCount);
  for (let node = 0; node < nodes.count; node += 1) {
    const place = nodes.tambonIndex[node] - 1;
    if (place >= 0 && place < tambonCount) out[place] += nodes.vulnerable[node];
  }
  return out;
}

/** The five 0–100 components from one subdistrict's raw figures. */
export function replayComponents(raw: ReplayFppsRaw, anchors = REPLAY_FPPS_ANCHORS): FppsComponents {
  const floodShare = share(raw.floodedKm2, raw.modelledKm2);
  const peopleShare = share(raw.peopleInWater, raw.residents);
  return {
    flood_likelihood_0_100: clamp100((100 * floodShare) / anchors.floodSaturationShare),
    exposure_0_100: clamp100(
      50 * Math.min(1, peopleShare / anchors.exposureShareSaturation) + 50 * Math.min(1, raw.peopleInWater / anchors.exposurePeopleSaturation),
    ),
    access_gap_0_100: clamp100(100 * share(raw.evacueesWithoutAccess, raw.evacuees)),
    road_criticality_0_100: clamp100((100 * share(raw.roadWeightedImpassableKm, raw.roadWeightedKm)) / anchors.roadSaturationShare),
    vulnerability_context_0_100: clamp100((100 * share(raw.vulnerableResidents, raw.nodeResidents)) / anchors.vulnerableSaturationShare),
  };
}

/** Normalise the manifest confidence to the scoring vocabulary; anything unknown is treated as low. */
export function replayConfidence(value: string): ConfidenceClass {
  const lower = value.toLowerCase();
  return lower === "high" || lower === "medium" ? lower : "low";
}

export interface ReplayFppsInputs {
  tambonIds: readonly string[];
  /** `access.tambons` order, which indexes the snapshot and node arrays. */
  accessTambons: readonly string[];
  modelledKm2: Record<string, number>;
  floodedKm2: Record<string, number>;
  residents: Record<string, number>;
  peopleInWater: Record<string, number>;
  need: EvacuationNeed | null;
  nodeResidents: ArrayLike<number> | null;
  vulnerable: ArrayLike<number> | null;
  roadWeightedKm: Record<string, number>;
  roadWeightedImpassableKm: Record<string, number>;
  confidence: string;
  weights?: FppsWeights;
}

/** Score every subdistrict and rank them (highest FPPS first; ties by id). */
export function replayFpps(inputs: ReplayFppsInputs): ReplayFppsRow[] {
  const weights = inputs.weights ?? DEFAULT_FPPS_WEIGHTS;
  const confidence = replayConfidence(inputs.confidence);
  const rows = inputs.tambonIds.map((id) => {
    const place = inputs.accessTambons.indexOf(id);
    const at = (values: ArrayLike<number> | null | undefined) => (values && place >= 0 ? values[place] ?? 0 : 0);
    const raw: ReplayFppsRaw = {
      floodedKm2: inputs.floodedKm2[id] ?? 0,
      modelledKm2: inputs.modelledKm2[id] ?? 0,
      residents: inputs.residents[id] ?? 0,
      peopleInWater: inputs.peopleInWater[id] ?? 0,
      nodeResidents: at(inputs.nodeResidents),
      evacuees: at(inputs.need?.evacuees),
      evacueesWithoutAccess: at(inputs.need?.withoutAccess),
      vulnerableResidents: at(inputs.vulnerable),
      roadWeightedKm: inputs.roadWeightedKm[id] ?? 0,
      roadWeightedImpassableKm: inputs.roadWeightedImpassableKm[id] ?? 0,
    };
    const components = replayComponents(raw);
    const scored = scoreSubdistrict({ ...components, confidence_class: confidence }, weights);
    return {
      id,
      raw,
      components,
      points: componentPoints(components, weights),
      ...scored,
      score_implied_class: assignActionClass({ ...components, confidence_class: "medium" }, scored.fpps_0_100),
      rank: 0,
    };
  });
  rows.sort((a, b) => b.fpps_0_100 - a.fpps_0_100 || a.id.localeCompare(b.id));
  rows.forEach((row, index) => { row.rank = index + 1; });
  return rows;
}

/** Each component's share (0–1) of a row's score, for "what drives this score" percentages. */
export function pointShares(points: FppsComponents): FppsComponents {
  const total = FPPS_COMPONENTS.reduce((sum, key) => sum + points[key], 0);
  return Object.fromEntries(FPPS_COMPONENTS.map((key) => [key, total > 0 ? points[key] / total : 0])) as Record<FppsComponent, number>;
}
