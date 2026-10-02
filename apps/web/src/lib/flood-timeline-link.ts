/**
 * Shareable deep links for the Mae Sai replay: the moment and the view settings as URL query parameters.
 * Pure parsing and serialisation only; invalid or unknown values fall back to the caller's defaults.
 */

import type { Language, TimelineLayer } from "./flood-timeline";

export type WaterMode = "depth" | "arrival" | "duration" | "people" | "residents";
export type RoadMode = "state" | "hours";
/** Evacuation-access shelter set: the sites reported in use in 2024, or the first k sites of the ranked plan. */
export type ShelterSetChoice = "reported" | "plan";
export const WATER_MODES: readonly WaterMode[] = ["depth", "arrival", "duration", "people", "residents"];
export const ROAD_MODES: readonly RoadMode[] = ["state", "hours"];
export const SHELTER_SETS: readonly ShelterSetChoice[] = ["reported", "plan"];
/** Residents the access figures count: homes that flood at the modelled peak (default) or everyone at road nodes. */
export type AccessScopeChoice = "flooded" | "all";
export const ACCESS_SCOPE_CHOICES: readonly AccessScopeChoice[] = ["flooded", "all"];

export interface LayerVisibility {
  tambons: boolean;
  roads: boolean;
  facilities: boolean;
  /** Shelters reported in use in September 2024 (stars). */
  reported: boolean;
  /** Ranked plan candidates (numbered top-k badges and eligible sites). */
  candidates: boolean;
  /** Candidates screened out (grey), with their reasons. */
  ineligible: boolean;
  /** "People cut off" heat of resident nodes that have lost access at this stage. */
  cutoff: boolean;
  /** Observed VIIRS daily flood map (375 m) for the day at or before the playhead. */
  viirs: boolean;
  /** Observed hourly rain gauges (markers with totals). */
  gauges: boolean;
  /**
   * The 2024 season envelope (a scenario layer, hatched). It is a layer of its own: the hour in `t` never turns it
   * on or off, and it is not an imagery choice.
   */
  envelope: boolean;
}

export interface ReplayLinkState {
  /** Whole hours since 9 Sep 00:00 ICT (the slider position). */
  hour: number;
  /** Imagery selection: "auto", "none" or a manifest layer id. */
  imagery: string;
  waterMode: WaterMode;
  /** Water opacity, 0-100 (percent). */
  waterOpacity: number;
  roadMode: RoadMode;
  /** Left and right imagery of the swipe comparison, or null when comparison is off. */
  compare: readonly [string, string] | null;
  language: Language;
  layers: LayerVisibility;
  shelterSet: ShelterSetChoice;
  /** Plan size k (1 … plan length) for the ranked-plan shelter set. */
  planK: number;
  /** Whose walking access the access card counts. */
  accessScope: AccessScopeChoice;
}

export interface ReplayLinkOptions {
  /** Largest valid hour index. */
  maxHour: number;
  /** Valid `img` values (including "auto" and "none"). */
  imageryIds: readonly string[];
  /** Valid comparison sides ("none" excluded). */
  compareIds: readonly string[];
  /** Largest valid plan size (the ranked plan's length); 0 ignores `k`. */
  maxPlanK?: number;
}

/** Query parameter names; kept short because the link is meant to be pasted into messages. */
export const LINK_PARAMS = ["t", "img", "wm", "wo", "rm", "cmp", "lang", "layers", "set", "k", "pop"] as const;

/**
 * One letter per map layer in `layers=`: t r f subdistricts, roads, facilities; s c i x reported shelters, plan
 * candidates, ineligible candidates, people cut off; v g the observed VIIRS daily flood map and the rain gauges;
 * e the 2024 season envelope (scenario).
 */
const LAYER_LETTERS: [keyof LayerVisibility, string][] = [
  ["tambons", "t"], ["roads", "r"], ["facilities", "f"], ["reported", "s"], ["candidates", "c"], ["ineligible", "i"], ["cutoff", "x"],
  ["viirs", "v"], ["gauges", "g"], ["envelope", "e"],
];
const LAYER_PATTERN = new RegExp(`^[${LAYER_LETTERS.map(([, letter]) => letter).join("")}]{1,${LAYER_LETTERS.length}}$`);

function parseLayers(value: string): LayerVisibility | null {
  if (value !== "none" && (!LAYER_PATTERN.test(value) || new Set(value).size !== value.length)) return null;
  const visibility = {} as LayerVisibility;
  for (const [key, letter] of LAYER_LETTERS) visibility[key] = value !== "none" && value.includes(letter);
  return visibility;
}

function serializeLayers(layers: LayerVisibility): string {
  const letters = LAYER_LETTERS.filter(([key]) => layers[key]).map(([, letter]) => letter).join("");
  return letters || "none";
}

function parseWhole(value: string, max: number): number | null {
  if (!/^\d{1,5}$/.test(value)) return null;
  const number = Number(value);
  return number <= max ? number : null;
}

/** Read a replay link; every missing or invalid parameter keeps its value from `defaults`. */
export function parseReplayLink(search: string, defaults: ReplayLinkState, options: ReplayLinkOptions): ReplayLinkState {
  const params = new URLSearchParams(search);
  const read = (name: (typeof LINK_PARAMS)[number]) => params.get(name)?.trim() ?? null;
  const state: ReplayLinkState = { ...defaults, layers: { ...defaults.layers } };

  const t = read("t");
  const hour = t === null ? null : parseWhole(t, options.maxHour);
  if (hour !== null) state.hour = hour;

  const img = read("img");
  if (img !== null && options.imageryIds.includes(img)) state.imagery = img;

  const wm = read("wm");
  if (wm !== null && (WATER_MODES as readonly string[]).includes(wm)) state.waterMode = wm as WaterMode;

  const wo = read("wo");
  const opacity = wo === null ? null : parseWhole(wo, 100);
  if (opacity !== null) state.waterOpacity = opacity;

  const rm = read("rm");
  if (rm !== null && (ROAD_MODES as readonly string[]).includes(rm)) state.roadMode = rm as RoadMode;

  const cmp = read("cmp");
  if (cmp !== null) {
    const sides = cmp.split(",");
    state.compare = sides.length === 2 && sides.every((side) => options.compareIds.includes(side))
      ? [sides[0], sides[1]]
      : defaults.compare;
  }

  const lang = read("lang");
  if (lang === "en" || lang === "th") state.language = lang;

  const layers = read("layers");
  const visibility = layers === null ? null : parseLayers(layers);
  if (visibility) state.layers = visibility;

  const set = read("set");
  if (set !== null && (SHELTER_SETS as readonly string[]).includes(set)) state.shelterSet = set as ShelterSetChoice;

  const k = read("k");
  const planK = k === null || !options.maxPlanK ? null : parseWhole(k, options.maxPlanK);
  if (planK !== null && planK >= 1) state.planK = planK;

  const pop = read("pop");
  if (pop !== null && (ACCESS_SCOPE_CHOICES as readonly string[]).includes(pop)) state.accessScope = pop as AccessScopeChoice;
  return state;
}

/** Query string (without "?") for a replay state; `cmp` is present only while comparison is on. */
export function serializeReplayLink(state: ReplayLinkState): string {
  const params = new URLSearchParams();
  params.set("t", String(Math.round(state.hour)));
  params.set("img", state.imagery);
  params.set("wm", state.waterMode);
  params.set("wo", String(Math.round(state.waterOpacity)));
  params.set("rm", state.roadMode);
  if (state.compare) params.set("cmp", `${state.compare[0]},${state.compare[1]}`);
  params.set("lang", state.language);
  params.set("layers", serializeLayers(state.layers));
  params.set("set", state.shelterSet);
  params.set("k", String(Math.round(state.planK)));
  params.set("pop", state.accessScope);
  // Commas are safe in a query string; keep "cmp=a,b" readable.
  return params.toString().replace(/%2C/gi, ",");
}

/** Replace the replay parameters in `search`, keeping any unrelated parameters. */
export function mergeReplayLink(search: string, state: ReplayLinkState): string {
  const merged = new URLSearchParams(search);
  for (const name of LINK_PARAMS) merged.delete(name);
  const own = serializeReplayLink(state);
  const rest = merged.toString();
  return rest ? `${own}&${rest}` : own;
}

const IMAGERY_KIND_ORDER: readonly TimelineLayer["kind"][] = ["sentinel-2", "sentinel-1", "sentinel-1-change", "terrain"];
const kindRank = (kind: string) => {
  const rank = (IMAGERY_KIND_ORDER as readonly string[]).indexOf(kind);
  return rank < 0 ? IMAGERY_KIND_ORDER.length : rank;
};

/** Imagery choices in display order: "auto", the manifest layers (optical, radar, radar change, terrain; oldest first), "none". */
export function imageryChoices(layers: readonly Pick<TimelineLayer, "id" | "kind" | "date">[]): string[] {
  const ordered = [...layers].sort((a, b) => kindRank(a.kind) - kindRank(b.kind)
    || (a.date ?? "").localeCompare(b.date ?? "")
    || a.id.localeCompare(b.id));
  return ["auto", ...ordered.map((layer) => layer.id), "none"];
}

/** Default swipe comparison: the earliest and latest optical layers (else the first two layers), or null. */
export function defaultCompareSides(layers: readonly Pick<TimelineLayer, "id" | "kind" | "date">[]): [string, string] | null {
  const ordered = imageryChoices(layers).slice(1, -1);
  const optical = ordered.filter((id) => layers.find((layer) => layer.id === id)?.kind === "sentinel-2");
  if (optical.length >= 2) return [optical[0], optical[optical.length - 1]];
  return ordered.length >= 2 ? [ordered[0], ordered[1]] : null;
}
