/**
 * The demo's deep links into the Mae Sai replay (`docs/demo_walkthrough.md`, section "Mae Sai Replay Beat", roadmap
 * P4-1) against the page's own link parser: every link must be the page's canonical form of a valid state, so it opens
 * exactly the moment and view the walkthrough describes, and the page writes the same link back once loaded. The links
 * must also open on production, which serves master until this branch is merged: no layer letter that master's replay
 * cannot read. The figures the page shows at each link's hour (`districtStats`) must equal the ones
 * `docs/demo/replay_numbers.md` lists for the speaker (the Python side computes them independently).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  districtStats,
  stageAt,
  TIMELINE_END_T,
  TIMELINE_MANIFEST_URL,
  type FacilityProps,
  type GeoCollection,
  type RoadProps,
  type TimelineManifest,
} from "./flood-timeline";
import {
  imageryChoices,
  LINK_PARAMS,
  parseReplayLink,
  serializeReplayLink,
  type ReplayLinkState,
} from "./flood-timeline-link";

const repoRoot = resolve(import.meta.dirname, "../../../..");
const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")), "utf8");
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL)) as TimelineManifest;
const walkthrough = readFileSync(resolve(repoRoot, "docs/demo_walkthrough.md"), "utf8");
const numbers = readFileSync(resolve(repoRoot, "docs/demo/replay_numbers.md"), "utf8");
const section = walkthrough.slice(walkthrough.indexOf("## Mae Sai Replay Beat"), walkthrough.indexOf("## Replay Beat: Words To Avoid"));
const ROUTE = "/studio/cases/mae-sai-2024/";
const links = [...section.matchAll(/`(\/studio\/cases\/mae-sai-2024\/\?[^`]+)`/g)].map((match) => match[1]);

/** Layer letters master's replay reads (it has no reported-depth layer); a link with another letter would be ignored there. */
const MASTER_LAYER_LETTERS = new Set("trfscixvge");

const choices = imageryChoices(manifest.layers);
const options = {
  maxHour: TIMELINE_END_T * 24,
  imageryIds: choices,
  compareIds: choices.filter((id) => id !== "none"),
  maxPlanK: manifest.shelters?.plan.length ?? 0,
};
// Defaults far from every link, so a parameter the parser refused would show up as a changed value.
const defaults: ReplayLinkState = {
  hour: 0, imagery: "none", waterMode: "duration", waterOpacity: 10, roadMode: "hours", compare: null, language: "th",
  layers: { tambons: false, roads: false, facilities: true, reported: false, candidates: false, ineligible: true, cutoff: true, viirs: true, gauges: true, envelope: false, reportedDepths: true },
  shelterSet: "plan", planK: 1, accessScope: "all",
};

describe("demo deep links", () => {
  it("lists the five replay links of the beat, four in English and one in Thai", () => {
    expect(links).toHaveLength(5);
    expect(links.map((link) => new URLSearchParams(link.split("?")[1]).get("lang"))).toEqual(["en", "en", "en", "en", "th"]);
    expect(links.every((link) => link.startsWith(`${ROUTE}?`))).toBe(true);
  });

  it("are the page's canonical links of valid states, so each opens as written and is written back unchanged", () => {
    for (const link of links) {
      const query = link.split("?")[1];
      const names = [...new URLSearchParams(query).keys()];
      expect(names.every((name) => (LINK_PARAMS as readonly string[]).includes(name)), link).toBe(true);
      const state = parseReplayLink(query, defaults, options);
      expect(serializeReplayLink(state), link).toBe(query);
    }
  });

  it("open the moments and views the walkthrough names", () => {
    const states = links.map((link) => parseReplayLink(link.split("?")[1], defaults, options));
    expect(states.map((state) => state.hour)).toEqual([46, 84, 158, 84, 84]);
    expect(states[0].waterMode).toBe("arrival");
    expect(states[2].compare).toEqual(["s2-20240905", "s2-20240915"]);
    expect(states.map((state) => state.layers.envelope)).toEqual([false, false, false, true, false]);
    expect(states.every((state) => state.shelterSet === "reported" && state.planK === manifest.shelters?.knee_k && state.accessScope === "flooded")).toBe(true);
  });

  it("use only layer letters that master's replay reads, so they open the same way on production", () => {
    for (const link of links) {
      const letters = new URLSearchParams(link.split("?")[1]).get("layers") ?? "";
      expect([...letters].every((letter) => MASTER_LAYER_LETTERS.has(letter)), link).toBe(true);
    }
  });

  it("show at each hour the figures replay_numbers.md lists for the speaker", () => {
    const roads = JSON.parse(read(manifest.vectors.roads.href)) as GeoCollection<unknown, RoadProps>;
    const facilities = JSON.parse(read(manifest.vectors.facilities.href)) as GeoCollection<unknown, FacilityProps>;
    const rows = [...numbers.matchAll(/^\| (\d+) \| [^|]+ \| [^|]+ \| ([\d.]+) m \| ([\d.]+) km² \| ([\d,]+) \|$/gm)];
    expect(rows.map((row) => Number(row[1]))).toEqual([42, 46, 84, 158]);
    for (const [, hour, stage, flooded, people] of rows) {
      const at = stageAt(Number(hour) / 24, manifest.stage_anchors);
      const stats = districtStats(manifest, at, roads.features.map((feature) => feature.properties), facilities.features.map((feature) => feature.properties));
      expect(at.toFixed(2), `hour ${hour}`).toBe(stage);
      expect(stats.flooded_km2.toFixed(1), `hour ${hour}`).toBe(flooded);
      expect(Math.round(stats.people_in_water ?? -1).toLocaleString("en-US"), `hour ${hour}`).toBe(people);
    }
  });
});
