import { describe, expect, it } from "vitest";

import {
  defaultCompareSides,
  imageryChoices,
  LINK_PARAMS,
  mergeReplayLink,
  parseReplayLink,
  serializeReplayLink,
  type ReplayLinkOptions,
  type ReplayLinkState,
} from "./flood-timeline-link";
import type { TimelineLayer } from "./flood-timeline";

const layers: Pick<TimelineLayer, "id" | "kind" | "date">[] = [
  { id: "hillshade", kind: "terrain", date: null },
  { id: "s2-20240915", kind: "sentinel-2", date: "2024-09-15T03:58:15Z" },
  { id: "s1-20240906", kind: "sentinel-1", date: "2024-09-06T11:31:06Z" },
  { id: "s2-20240905", kind: "sentinel-2", date: "2024-09-05T03:58:19Z" },
  { id: "s1-change", kind: "sentinel-1-change", date: "2024-09-06T11:31:06Z/2024-09-15T23:16:01Z" },
];
const choices = imageryChoices(layers);
const options: ReplayLinkOptions = { maxHour: 264, imageryIds: choices, compareIds: choices.filter((id) => id !== "none"), maxPlanK: 12 };
const allLayers = { tambons: true, roads: true, facilities: true, reported: true, candidates: true, ineligible: true, cutoff: true, viirs: true, gauges: true, envelope: true };
const noLayers = { tambons: false, roads: false, facilities: false, reported: false, candidates: false, ineligible: false, cutoff: false, viirs: false, gauges: false, envelope: false };
const defaults: ReplayLinkState = {
  hour: 12,
  imagery: "auto",
  waterMode: "depth",
  waterOpacity: 85,
  roadMode: "state",
  compare: null,
  language: "en",
  layers: { ...noLayers, tambons: true, roads: true, facilities: true, reported: true, candidates: true },
  shelterSet: "reported",
  planK: 8,
  accessScope: "flooded",
};

describe("Mae Sai replay deep links", () => {
  it("orders imagery choices and picks the earliest and latest optical scenes for comparison", () => {
    expect(choices).toEqual(["auto", "s2-20240905", "s2-20240915", "s1-20240906", "s1-change", "hillshade", "none"]);
    expect(defaultCompareSides(layers)).toEqual(["s2-20240905", "s2-20240915"]);
    expect(defaultCompareSides(layers.filter((layer) => layer.kind !== "sentinel-2"))).toEqual(["s1-20240906", "s1-change"]);
    expect(defaultCompareSides([layers[0]])).toBeNull();
  });

  it("round-trips every view setting through the query string", () => {
    const states: ReplayLinkState[] = [
      defaults,
      {
        hour: 84, imagery: "s1-change", waterMode: "arrival", waterOpacity: 40, roadMode: "hours",
        compare: ["s2-20240905", "s2-20240915"], language: "th", layers: { ...noLayers, roads: true, cutoff: true },
        shelterSet: "plan", planK: 3, accessScope: "all",
      },
      {
        hour: 0, imagery: "none", waterMode: "duration", waterOpacity: 0, roadMode: "state",
        compare: ["auto", "hillshade"], language: "en", layers: noLayers, shelterSet: "plan", planK: 12, accessScope: "flooded",
      },
      { ...defaults, hour: 264, waterOpacity: 100, waterMode: "people", layers: allLayers, planK: 1 },
      { ...defaults, waterMode: "residents", shelterSet: "reported", layers: { ...noLayers, ineligible: true, candidates: true } },
    ];
    for (const state of states) {
      const query = serializeReplayLink(state);
      expect(parseReplayLink(query, defaults, options), query).toEqual(state);
      expect(parseReplayLink(`?${query}`, defaults, options)).toEqual(state);
      expect(serializeReplayLink(parseReplayLink(query, defaults, options))).toBe(query);
    }
  });

  it("writes short, readable parameters and omits the comparison while it is off", () => {
    const query = serializeReplayLink({ ...defaults, compare: ["s2-20240905", "s2-20240915"], layers: { ...noLayers, tambons: true, facilities: true } });
    expect(query).toBe("t=12&img=auto&wm=depth&wo=85&rm=state&cmp=s2-20240905,s2-20240915&lang=en&layers=tf&set=reported&k=8&pop=flooded");
    expect(serializeReplayLink(defaults)).not.toContain("cmp=");
    expect(serializeReplayLink(defaults)).toContain("layers=trfsc");
    expect(serializeReplayLink({ ...defaults, layers: allLayers, shelterSet: "plan", planK: 4 })).toContain("layers=trfscixvge&set=plan&k=4");
    // Whose access the card counts: homes that flood at the peak (default) or all residents at road nodes.
    expect(serializeReplayLink({ ...defaults, accessScope: "all" })).toContain("&pop=all");
    // The observed VIIRS map and the rain gauges have their own letters.
    expect(serializeReplayLink({ ...defaults, layers: { ...noLayers, viirs: true } })).toContain("layers=v&");
    expect(serializeReplayLink({ ...defaults, layers: { ...noLayers, roads: true, gauges: true } })).toContain("layers=rg&");
    // The season envelope (a scenario layer) has a letter of its own.
    expect(serializeReplayLink({ ...defaults, layers: { ...noLayers, envelope: true } })).toContain("layers=e&");
    expect(serializeReplayLink({ ...defaults, layers: noLayers })).toContain("layers=none");
  });

  it("falls back to the defaults for missing, unknown or malformed values", () => {
    expect(parseReplayLink("", defaults, options)).toEqual(defaults);
    const invalid = [
      "t=265", "t=-1", "t=3.5", "t=abc", "t=", "t=999999",
      "img=s2-20990101", "img=", "wm=flow", "wo=101", "wo=-5", "wo=0.5", "rm=closed",
      "cmp=s2-20240905", "cmp=none,s2-20240905", "cmp=a,b,c", "cmp=",
      "lang=fr", "layers=z", "layers=tt", "layers=trfz", "layers=trfscixx", "layers=vv", "layers=trfscixvgv", "layers=ee", "layers=trfscixvgee", "layers=",
      "set=all", "set=", "k=0", "k=13", "k=2.5", "k=-1", "k=",
      "pop=", "pop=everyone", "pop=FLOODED",
    ];
    for (const query of invalid) expect(parseReplayLink(query, defaults, options), query).toEqual(defaults);
    // Valid parameters survive next to invalid ones.
    expect(parseReplayLink("t=48&wm=nope&rm=hours", defaults, options)).toEqual({ ...defaults, hour: 48, roadMode: "hours" });
    expect(parseReplayLink("set=plan&k=5&layers=x", defaults, options)).toEqual({ ...defaults, shelterSet: "plan", planK: 5, layers: { ...noLayers, cutoff: true } });
    expect(parseReplayLink("layers=trfv", defaults, options).layers).toEqual({ ...noLayers, tambons: true, roads: true, facilities: true, viirs: true });
    expect(parseReplayLink("layers=gx", defaults, options).layers).toEqual({ ...noLayers, gauges: true, cutoff: true });
    expect(parseReplayLink("pop=all&set=plan", defaults, options)).toEqual({ ...defaults, accessScope: "all", shelterSet: "plan" });
    // A link written before the scope switch opens on the default scope.
    expect(parseReplayLink("set=plan&k=3", defaults, options).accessScope).toBe("flooded");
    // Without a ranked plan, k is ignored.
    expect(parseReplayLink("k=5", defaults, { ...options, maxPlanK: 0 }).planK).toBe(defaults.planK);
    // A link written before the shelter, VIIRS and rain layers existed keeps its letters and turns the new layers off.
    expect(parseReplayLink("layers=trf", defaults, options).layers).toEqual({ ...noLayers, tambons: true, roads: true, facilities: true });
    // An invalid comparison keeps the caller's default comparison, not a half-parsed one.
    const withCompare = { ...defaults, compare: ["s2-20240905", "s2-20240915"] as const };
    expect(parseReplayLink("cmp=bogus,s2-20240915", withCompare, options).compare).toEqual(["s2-20240905", "s2-20240915"]);
    // Parsing never mutates the defaults.
    const snapshot = JSON.stringify(defaults);
    parseReplayLink("layers=r&t=5", defaults, options);
    expect(JSON.stringify(defaults)).toBe(snapshot);
  });

  it("turns the season envelope on only through its own layer letter, at any hour and with any imagery", () => {
    // No replay hour selects the envelope: for every hour of the replay a link without the letter leaves it off, and a
    // link with the letter leaves it on, whatever the hour. It is not an imagery choice either.
    expect(choices.some((id) => /envelope|4009|unosat/i.test(id))).toBe(false);
    for (let hour = 0; hour <= options.maxHour; hour += 1) {
      for (const imagery of choices) {
        expect(parseReplayLink(`t=${hour}&img=${imagery}`, defaults, options).layers.envelope, `t=${hour} img=${imagery}`).toBe(false);
        expect(parseReplayLink(`t=${hour}&img=${imagery}&layers=trv`, defaults, options).layers.envelope).toBe(false);
      }
      const on = parseReplayLink(`t=${hour}&layers=re`, defaults, options);
      expect(on.layers).toEqual({ ...noLayers, roads: true, envelope: true });
      expect(on.hour).toBe(hour);
    }
    // A link written before the layer existed keeps its letters and leaves the envelope off.
    expect(parseReplayLink("layers=trfscixvg", defaults, options).layers.envelope).toBe(false);
    // The hour of a link never changes with the envelope, and the envelope never changes the hour that is written.
    const withEnvelope = serializeReplayLink({ ...defaults, hour: 84, layers: { ...defaults.layers, envelope: true } });
    const without = serializeReplayLink({ ...defaults, hour: 84 });
    expect(new URLSearchParams(withEnvelope).get("t")).toBe(new URLSearchParams(without).get("t"));
    expect(new URLSearchParams(withEnvelope).get("img")).toBe("auto");
  });

  it("replaces its own parameters and keeps unrelated ones", () => {
    const merged = mergeReplayLink("?utm_source=report&t=5&wm=arrival", { ...defaults, hour: 100 });
    const params = new URLSearchParams(merged);
    expect(params.get("t")).toBe("100");
    expect(params.get("wm")).toBe("depth");
    expect(params.get("utm_source")).toBe("report");
    expect(params.getAll("t")).toHaveLength(1);
    expect(mergeReplayLink("", defaults)).toBe(serializeReplayLink(defaults));
    expect(LINK_PARAMS).toEqual(["t", "img", "wm", "wo", "rm", "cmp", "lang", "layers", "set", "k", "pop"]);
  });
});
