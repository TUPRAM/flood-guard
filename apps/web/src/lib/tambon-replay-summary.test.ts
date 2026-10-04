/**
 * The export pack's per-subdistrict summary (`exports/tambon_replay_summary.json`, roadmap P3-2) against the page: every
 * record must equal what the page derives from the manifest for that subdistrict at the modelled peak (flooded area,
 * residents in water, impassable road length and walking access for the reported 2024 set and the knee plan, counted
 * both ways), and carry its own lane, tier, confidence, timestamps and assumptions. No record holds a priority score or
 * an action class, and the season-envelope comparison is named, never copied (it is under another licence).
 * The JSON schema itself is checked in pytest (`tests/test_replay_exports.py`), which has a validator.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  manifestDirectory,
  stageAt,
  TIMELINE_MANIFEST_URL,
  type FacilityProps,
  type GeoCollection,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import { parseAccessNodes } from "./flood-timeline-evacuation";
import { findWordingViolations } from "./replay-wording-lint";
import { peakDay, tambonPeakFigures } from "./tambon-replay-summary";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const folder = manifestDirectory(TIMELINE_MANIFEST_URL);
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<unknown, RoadProps>;
const facilities = JSON.parse(read(manifest.vectors.facilities.href).toString("utf8")) as GeoCollection<unknown, FacilityProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<unknown, TambonProps>;
const nodes = parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!);
const record = manifest.exports!.files.find((file) => file.id === "tambon_replay_summary")!;

interface SummaryRecord {
  tambon_id: string;
  tambon_name_th: string;
  tambon_name_en: string;
  lane: string;
  evidence_tier: string;
  confidence_class: string;
  source_timestamp: string;
  generated_at: string;
  operational_status: string;
  assumptions: { en: string; th: string }[];
  modelled_peak_local_time: string;
  season_envelope_comparison?: { lane: string; stage: string; file: string; entry: string };
  [key: string]: unknown;
}
interface SummaryDocument {
  name: string;
  schema_id: string;
  metadata: Record<string, string> & { fields: { key: string; th: string; en: string }[] };
  records: SummaryRecord[];
}
const summary = JSON.parse(read(record.href).toString("utf8")) as SummaryDocument;
const derived = tambonPeakFigures(manifest, roads.features.map((feature) => feature.properties), facilities.features.map((feature) => feature.properties), nodes);

/** Dotted paths of every leaf of a record, in order (a list is one leaf), as the Python writer lists them. */
const leafPaths = (value: unknown, path = ""): string[] => (value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length > 0
  ? Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => leafPaths(item, path ? `${path}.${key}` : key))
  : [path]);
const THAI = /[฀-๿]/;

describe("Per-subdistrict replay summary (export pack)", () => {
  it("is a download of the export pack, listed with its hash, one record per subdistrict in the page's order", () => {
    expect(record).toBeDefined();
    expect(record.name).toBe("tambon_replay_summary.json");
    expect(record.href).toBe(`${folder}exports/tambon_replay_summary.json`);
    expect(record.media_type).toBe("application/json");
    expect(record.lanes).toEqual(["SCN"]);
    expect(record.licence).toBe("ODbL 1.0");
    expect(record.rows).toBe(8);
    expect(summary.name).toBe("tambon_replay_summary");
    expect(summary.schema_id).toBe("https://floodguard.th/contracts/tambon-replay-summary.schema.json");
    expect(summary.records.map((item) => item.tambon_id)).toEqual(manifest.access!.tambons);
    expect(summary.records).toHaveLength(8);
  });

  it("equals, record by record, what the page derives from the manifest at the modelled peak", () => {
    const peak = peakDay(manifest);
    expect([peak.date, peak.stage_m]).toEqual(["2024-09-12", 3.5]);
    expect(stageAt(peak.index + 0.5, manifest.stage_anchors)).toBe(peak.stage_m);
    expect(manifest.shelters!.method.peak_stage_m).toBe(peak.stage_m);
    expect(derived).toHaveLength(summary.records.length);
    for (const [index, item] of summary.records.entries()) {
      const page = derived[index];
      const { modelled_access_at_peak: access, ...figures } = page;
      for (const [key, value] of Object.entries(figures)) expect(item[key], `${item.tambon_id} ${key}`).toEqual(value);
      expect(item.modelled_access_at_peak, item.tambon_id).toEqual(access);
      // The district figures the page shows are the sum of the subdistricts (to rounding).
      expect(item.modelled_peak_local_time).toBe("2024-09-12T12:00:00+07:00");
    }
    const sum = (pick: (item: SummaryRecord) => number) => summary.records.reduce((total, item) => total + pick(item), 0);
    expect(sum((item) => item.modelled_flooded_km2_at_peak as number)).toBeCloseTo(peak.stats.flooded_km2, 2);
    expect(sum((item) => item.modelled_residents_in_water_at_peak as number)).toBeCloseTo(peak.stats.people_in_water!, -1);
    expect(Math.abs(sum((item) => item.modelled_road_km_impassable_at_peak as number) - peak.stats.road_km_impassable)).toBeLessThan(0.05);
    // Access at the peak: the subdistricts add up to the district figures the access card shows (34,525 and 7,086 lost for
    // the reported set, 24,910 and 13,429 for the plan of 8, all residents at road nodes).
    const access = (set: "reported_2024" | "knee_plan", measure: string) => sum((item) => {
      const sets = item.modelled_access_at_peak as Record<string, Record<string, Record<string, number>>>;
      return sets[set].all_residents_at_road_nodes[measure];
    });
    expect(Math.round(access("reported_2024", "within_reach_before_flood"))).toBe(34_525);
    expect(Math.round(access("reported_2024", "lost_access"))).toBe(peak.stats.access!.reported_2024.people_lost_access);
    expect(Math.round(access("knee_plan", "within_reach_before_flood"))).toBe(24_910);
    expect(Math.round(access("knee_plan", "lost_access"))).toBe(peak.stats.access![`plan_${manifest.shelters!.knee_k}`].people_lost_access);
  });

  it("names each subdistrict as the page does, in Thai and English", () => {
    const names = Object.fromEntries(tambons.features.map((feature) => [feature.properties.id, feature.properties]));
    for (const item of summary.records) {
      expect(item.tambon_name_th).toBe(names[item.tambon_id].th);
      expect(item.tambon_name_en).toBe(names[item.tambon_id].en);
      expect(item.tambon_name_th).toMatch(THAI);
    }
  });

  it("gives every record its lane, tier, confidence, timestamps and assumptions, in both languages", () => {
    const meta = summary.metadata;
    const assumptions = Object.keys(meta).filter((key) => /^assumption_\d+$/.test(key)).map((key) => ({ en: meta[key], th: meta[`${key}_th`] }));
    expect(assumptions.length).toBeGreaterThanOrEqual(6);
    for (const item of summary.records) {
      expect([item.lane, item.evidence_tier, item.confidence_class, item.operational_status]).toEqual(["SCN", "T1 scenario (model)", "low", "non_operational"]);
      expect(item.generated_at).toBe(manifest.generated_at);
      expect(item.source_timestamp).toBe(meta.source_timestamp);
      expect(item.source_timestamp).toContain("peak keyframe 2024-09-12T12:00:00+07:00");
      expect(item.assumptions).toEqual(assumptions);
      for (const assumption of item.assumptions) expect(assumption.th).toMatch(THAI);
      // No Buddhist-era year without its CE year.
      expect(JSON.stringify(item.assumptions)).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    }
    expect(meta.confidence_class).toBe("low");
    expect(meta.operational_status).toBe("non_operational");
    expect(meta.accepted).toContain("accepted_fpps=null; accepted_action_class=null");
    expect(meta.generated_at).toBe(manifest.generated_at);
    expect(meta.knee_k).toBe(String(manifest.shelters!.knee_k));
    // The declared fields are exactly each record's fields, each with a Thai label.
    for (const item of summary.records) expect(leafPaths(item)).toEqual(meta.fields.map((field) => field.key));
    for (const field of meta.fields) expect(field.th, field.key).toMatch(THAI);
  });

  it("holds no priority score or action class, and names the season-envelope comparison without copying it", () => {
    const keys = summary.records.flatMap((item) => leafPaths(item));
    expect(keys.filter((key) => /fpps|action[_-]?class|priority[_-]?score/i.test(key))).toEqual([]);
    expect(Object.keys(summary.metadata).filter((key) => /fpps|action[_-]?class|priority[_-]?score/i.test(key))).toEqual([]);
    const envelope = manifest.season_envelope!;
    const statistics = JSON.parse(read(envelope.files.statistics.href).toString("utf8")) as {
      comparison: { by_tambon_stage: string; by_tambon: { tambon_id: string }[] };
    };
    for (const item of summary.records) {
      const pointer = item.season_envelope_comparison!;
      expect(pointer.lane).toBe("SCN-ENV");
      expect(pointer.file).toBe("season_envelope.files.statistics");
      expect(pointer.stage).toBe(statistics.comparison.by_tambon_stage);
      expect(pointer.entry).toBe(`comparison.by_tambon[tambon_id=${item.tambon_id}]`);
      expect(statistics.comparison.by_tambon.some((row) => row.tambon_id === item.tambon_id)).toBe(true);
      // Only words: no figure of the envelope travels in this ODbL file.
      expect(Object.values(pointer).every((value) => typeof value === "string")).toBe(true);
    }
    const text = read(record.href).toString("utf8");
    expect(text.replace(summary.metadata.not_included, "").replace(summary.metadata.not_included_th, "")).not.toContain("4009");
  });

  it("passes the shared wording lint in both languages", () => {
    const meta = { ...summary.metadata, fields: undefined };
    expect(findWordingViolations(JSON.stringify(meta), "summary metadata")).toEqual([]);
    expect(findWordingViolations(JSON.stringify(summary.metadata.fields), "summary fields")).toEqual([]);
    for (const item of summary.records) expect(findWordingViolations(JSON.stringify(item), item.tambon_id)).toEqual([]);
    expect(findWordingViolations(`${record.title.en}\n${record.title.th}`, "summary title")).toEqual([]);
  });
});
