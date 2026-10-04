/**
 * The exercise items of the Command exercise replay and how they are drawn: the served file under its own rules
 * (every id starts "EX-", no phone number, no soi or house, urgency by the stated-fact rule, the shared wording lint),
 * every marker state, arrival and waiting on the replay clock, the clusters of the district zoom, the reports saved on
 * this device per subdistrict, the "no reports received" mark and the modelled depth at a point.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type AreaGeometry, type GeoCollection, type TambonProps, type TimelineManifest } from "./flood-timeline";
import { pointInArea } from "./flood-timeline-command";
import {
  arrivedExerciseItems,
  CLUSTER_RADIUS_PX,
  clusterMarkers,
  deviceReportsByTambon,
  EXERCISE_COLOURS,
  EXERCISE_FILE_URL,
  EXERCISE_STATUSES,
  EXERCISE_URGENCIES,
  exerciseArrivals,
  exerciseCounts,
  ExerciseFileError,
  exerciseMarkerSpec,
  exerciseUrgency,
  hasAddressOrName,
  hasPhonePattern,
  isOpenStatus,
  lifeAtRiskHours,
  modelDepthAt,
  mostUrgentItem,
  parseExerciseFile,
  tambonsWithoutReports,
  waitingHours,
  type ExerciseHandling,
  type ExerciseKind,
} from "./flood-timeline-command-incidents";
import { describeWordingFindings, findWordingViolations } from "./replay-wording-lint";

const publicRoot = resolve(import.meta.dirname, "../../public");
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(resolve(publicRoot, href.replace(/^\//, "")), "utf8")) as T;
const raw = readJson<Record<string, unknown>>(EXERCISE_FILE_URL);
const file = parseExerciseFile(raw);
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const tambons = readJson<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href).features;

/** Every string value of a JSON document. */
function strings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(strings);
  if (value && typeof value === "object") return Object.values(value).flatMap(strings);
  return [];
}
const metres = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) =>
  Math.hypot((a.lat - b.lat) * 111_320, (a.lon - b.lon) * 111_320 * Math.cos((a.lat * Math.PI) / 180));
const clone = () => structuredClone(raw) as { simulated: unknown; urgency_rule: Record<string, unknown>; items: Record<string, unknown>[] };
const refused = (edit: (document: ReturnType<typeof clone>) => void) => {
  const document = clone();
  edit(document);
  return () => parseExerciseFile(document);
};

describe("The served exercise file", () => {
  it("holds about 14 invented items: 2 at life at risk, 4 urgent and 8 of information, each with an EX- id", () => {
    expect(file.simulated).toBe(true);
    expect(file.items).toHaveLength(14);
    const count = (urgency: string) => file.items.filter((item) => item.urgency === urgency).length;
    expect([count("life_at_risk"), count("urgent"), count("information")]).toEqual([2, 4, 8]);
    for (const item of file.items) expect(item.id).toMatch(/^EX-\d{2}$/);
    expect(new Set(file.items.map((item) => item.id)).size).toBe(14);
    // In the order of their arrival, inside the replay.
    expect(file.items.map((item) => item.hour)).toEqual([...file.items.map((item) => item.hour)].sort((a, b) => a - b));
    expect(file.items.every((item) => item.hour >= 0 && item.hour <= 264)).toBe(true);
    // A call is an octagon and a report a rounded square: both kinds are in the file.
    expect(new Set(file.items.map((item) => item.kind))).toEqual(new Set<ExerciseKind>(["call", "report"]));
    expect(file.notice.en).toContain("invented by the FloodGuard team");
    expect(file.notice.en).toContain("never counted with real reports");
  });

  it("sets every urgency by the stated-fact rule, and states the rule in both languages", () => {
    for (const item of file.items) expect(item.urgency, item.id).toBe(exerciseUrgency(item.facts));
    expect(exerciseUrgency(["on_roof"])).toBe("life_at_risk");
    expect(exerciseUrgency(["chest_or_above_with_people"])).toBe("life_at_risk");
    expect(exerciseUrgency(["infant_or_bedridden"])).toBe("urgent");
    expect(exerciseUrgency(["no_food_for_a_day"])).toBe("urgent");
    expect(exerciseUrgency(["no_food_for_a_day", "on_roof"])).toBe("life_at_risk");
    expect(exerciseUrgency([])).toBe("information");
    expect(file.rule.en).toContain("never by the model");
    expect(file.rule.th).toContain("แบบจำลองไม่ได้เป็นผู้กำหนด");
  });

  it("places every item near a community that a place record names, inside its stated tolerance and its stated subdistrict", () => {
    const points = (manifest.reported_depths?.reports ?? []).flatMap((report) => (report.point ? [report.point] : []));
    expect(points.length).toBe(12);
    for (const item of file.items) {
      const nearest = Math.min(...points.map((point) => metres(item.point, point)));
      expect(nearest, item.id).toBeLessThanOrEqual(item.toleranceM);
      const tambon = tambons.find((feature) => pointInArea(item.point.lon, item.point.lat, feature.geometry));
      expect(tambon?.properties.id, item.id).toBe(item.tambonId);
    }
    // No two items share a point, so no marker hides another at the town zoom.
    expect(new Set(file.items.map((item) => `${item.point.lat},${item.point.lon}`)).size).toBe(14);
  });

  it("holds no phone number, no soi, no house and no person", () => {
    for (const text of strings({ ...raw, authored: "" })) {
      expect(hasPhonePattern(text), text).toBe(false);
      expect(hasAddressOrName(text), text).toBe(false);
    }
    expect(hasPhonePattern("call 081-234-5678")).toBe(true);
    expect(hasPhonePattern("โทร 0812345678")).toBe(true);
    expect(hasPhonePattern("+66 81 234 5678")).toBe(true);
    expect(hasPhonePattern("(053) 731 111")).toBe(true);
    expect(hasPhonePattern("ประชาชน 8 คน ไม่มีอาหารมาแล้ว 1 วัน ในปี 2567 (2024)")).toBe(false);
    expect(hasAddressOrName("Ko Sai, Soi 14")).toBe(true);
    expect(hasAddressOrName("เกาะทราย ซอย 4/1")).toBe(true);
    expect(hasAddressOrName("บ้านเลขที่ 12")).toBe(true);
    expect(hasAddressOrName("Mrs Somsri is on the roof")).toBe(true);
    expect(hasAddressOrName("นางสมศรีอยู่บนหลังคา")).toBe(true);
    expect(hasAddressOrName("Ko Sai community")).toBe(false);
  });

  it("copies no plea of 2024: no item shares a run of five words with a place record", () => {
    const words = (text: string) => text.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter(Boolean);
    const runs = (text: string) => {
      const list = words(text);
      return new Set(list.slice(0, Math.max(0, list.length - 4)).map((_, index) => list.slice(index, index + 5).join(" ")));
    };
    const recorded = new Set((manifest.reported_depths?.reports ?? []).flatMap((report) => [...runs(report.depth.statement.en)]));
    for (const item of file.items) for (const run of runs(item.text.en)) expect(recorded.has(run), `${item.id}: ${run}`).toBe(false);
    for (const report of manifest.reported_depths?.reports ?? []) {
      for (const item of file.items) expect(item.text.th, item.id).not.toBe(report.depth.statement.th);
    }
  });

  it("passes the shared wording lint on every string", () => {
    const findings = strings(raw).flatMap((text) => findWordingViolations(text, EXERCISE_FILE_URL));
    expect(describeWordingFindings(findings)).toBe("");
    // The lint really reads the file: a banned claim planted in an item is found.
    const seeded = clone();
    (seeded.items[0].text as { en: string }).en += " Live flood forecast.";
    expect(strings(seeded).flatMap((text) => findWordingViolations(text)).map((finding) => finding.rule).sort()).toEqual(["forecast", "live"]);
  });

  it("is refused when it breaks a rule of the exercise", () => {
    expect(refused((document) => { document.simulated = false; })).toThrow(ExerciseFileError);
    expect(refused((document) => { document.items[0].id = "R-01"; })).toThrow(/EX-nn/);
    expect(refused((document) => { document.items[1].id = document.items[0].id; })).toThrow(/share an id/);
    expect(refused((document) => { document.items[0].urgency = "life_at_risk"; })).toThrow(/does not follow from its stated facts/);
    expect(refused((document) => { document.items[0].facts = ["on_roof"]; document.items[0].urgency = "life_at_risk"; document.items[0].people_band = "1-2"; })).toThrow(/a report of depth or of a road states no fact about people/);
    expect(refused((document) => { (document.items[0].text as { en: string }).en = "Call 081-234-5678 for the boat."; })).toThrow(/phone number/);
    expect(refused((document) => { (document.items[0].place as { th: string }).th = "เกาะทราย ซอย 14"; })).toThrow(/soi, a house or a person/);
    expect(refused((document) => { document.items[0].tolerance_m = 50; })).toThrow(/100 to 400 m/);
    expect(refused((document) => { document.items[0].hour = 300; })).toThrow(/whole hour from 0 to 264/);
    expect(refused((document) => { document.items[0].kind = "call"; })).toThrow(/a call is a call for help/);
    expect(refused((document) => { document.urgency_rule.urgent = ["on_roof"]; })).toThrow(/differs from the page's rule/);
    expect(() => parseExerciseFile({ schema: "something.else" })).toThrow(ExerciseFileError);
  });
});

describe("Exercise items on the replay clock", () => {
  it("shows an item from its replay hour on, never before", () => {
    for (let hour = 0; hour <= 264; hour += 1) {
      const arrived = arrivedExerciseItems(file.items, hour);
      expect(arrived.every((item) => item.hour <= hour)).toBe(true);
      expect(arrived.length).toBe(file.items.filter((item) => item.hour <= hour).length);
    }
    expect(arrivedExerciseItems(file.items, 0)).toEqual([]);
    expect(arrivedExerciseItems(file.items, 60).map((item) => item.id)).toEqual(["EX-01", "EX-02", "EX-03", "EX-04", "EX-05", "EX-06", "EX-07", "EX-08"]);
    expect(arrivedExerciseItems(file.items, 84)).toHaveLength(11);
    expect(arrivedExerciseItems(file.items, 110)).toHaveLength(14);
  });

  it("counts open items and those at life at risk, apart from every count of real reports", () => {
    expect(exerciseCounts(file.items, 30)).toEqual({ arrived: 0, open: 0, lifeAtRisk: 0 });
    expect(exerciseCounts(file.items, 60)).toEqual({ arrived: 8, open: 8, lifeAtRisk: 1 });
    expect(exerciseCounts(file.items, 84)).toEqual({ arrived: 11, open: 11, lifeAtRisk: 2 });
    const handling = new Map<string, ExerciseHandling>([["EX-05", { status: "done", callsign: "BOAT-2" }], ["EX-01", { status: "dropped", callsign: null }], ["EX-02", { status: "assigned", callsign: "MED-1" }]]);
    expect(exerciseCounts(file.items, 84, handling)).toEqual({ arrived: 11, open: 9, lifeAtRisk: 1 });
    // The replay data counts 21 place records; the exercise file changes none of its counts.
    expect(manifest.reported_depths?.counted.place_records).toBe(21);
    expect(manifest.reported_depths?.reports.some((report) => report.id.startsWith("EX-"))).toBe(false);
  });

  it("names what a step forward brings, the hours playback pauses at, and how long an item has waited", () => {
    expect(exerciseArrivals(file.items, 45, 46).map((item) => item.id)).toEqual(["EX-05"]);
    expect(exerciseArrivals(file.items, 46, 51)).toEqual([]);
    expect(exerciseArrivals(file.items, 30, 41).map((item) => item.id)).toEqual(["EX-01", "EX-02", "EX-03", "EX-04"]);
    expect([...lifeAtRiskHours(file.items)].sort((a, b) => a - b)).toEqual([46, 62]);
    const item = file.items.find((entry) => entry.id === "EX-05")!;
    expect(waitingHours(item, 46)).toBe(0);
    expect(waitingHours(item, 52)).toBe(6);
    expect(waitingHours(item, 10)).toBe(0);
    expect(mostUrgentItem(arrivedExerciseItems(file.items, 60))?.id).toBe("EX-05");
    expect(mostUrgentItem(exerciseArrivals(file.items, 30, 41))?.id).toBe("EX-02");
    expect(mostUrgentItem([])).toBeNull();
  });
});

describe("Exercise markers: every state", () => {
  it("shows urgency by symbol, size and colour together", () => {
    expect(exerciseMarkerSpec({ kind: "call", urgency: "life_at_risk" })).toMatchObject({ shape: "octagon", size: 36, symbol: "!!", fill: "#D55E00", symbolColour: "#ffffff", halo: true });
    expect(exerciseMarkerSpec({ kind: "call", urgency: "urgent" })).toMatchObject({ shape: "octagon", size: 30, symbol: "!", fill: "#E69F00", symbolColour: "#12262d", halo: false });
    expect(exerciseMarkerSpec({ kind: "call", urgency: "information" })).toMatchObject({ shape: "octagon", size: 26, symbol: "i", fill: "#0072B2", symbolColour: "#ffffff", halo: false });
    expect(exerciseMarkerSpec({ kind: "report", urgency: "information" })).toMatchObject({ shape: "square", size: 26, symbol: "i", fill: "#0072B2" });
    // The colours are not those of medical triage.
    expect(Object.values(EXERCISE_COLOURS)).not.toContain("#ff0000");
  });

  it("shows the handling state by outline: dashed new, solid acknowledged or assigned, grey with a tick when closed", () => {
    for (const kind of ["call", "report"] as const) {
      for (const urgency of EXERCISE_URGENCIES) {
        for (const status of EXERCISE_STATUSES) {
          const spec = exerciseMarkerSpec({ kind, urgency }, status);
          const open = isOpenStatus(status);
          expect(spec.closed, `${kind} ${urgency} ${status}`).toBe(!open);
          expect(spec.outline).toBe(!open ? "none" : status === "new" ? "dashed" : "solid");
          expect(spec.fill).toBe(open ? EXERCISE_COLOURS[urgency] : EXERCISE_COLOURS.closed);
          expect(spec.showsCallsign).toBe(status === "assigned");
          expect(spec.showsWaiting).toBe(open);
          expect(spec.halo).toBe(open && urgency === "life_at_risk");
          expect(spec.shape).toBe(kind === "call" ? "octagon" : "square");
        }
      }
    }
    expect(EXERCISE_STATUSES).toEqual(["new", "acknowledged", "assigned", "done", "dropped"]);
    expect(EXERCISE_STATUSES.filter(isOpenStatus)).toEqual(["new", "acknowledged", "assigned"]);
  });
});

describe("Clusters of the district zoom", () => {
  it("merges markers within 40 px of a group's first marker, and counts the life-at-risk items it holds", () => {
    const clusters = clusterMarkers([
      { x: 100, y: 100, count: 3, lifeAtRisk: false },
      { x: 120, y: 110, count: 1, lifeAtRisk: true },
      { x: 139, y: 100, count: 1, lifeAtRisk: false },
      { x: 141, y: 100, count: 1, lifeAtRisk: false },
      { x: 400, y: 300, count: 2, lifeAtRisk: true },
    ]);
    expect(CLUSTER_RADIUS_PX).toBe(40);
    expect(clusters.map((cluster) => cluster.members)).toEqual([[0, 1, 2], [3], [4]]);
    expect(clusters[0]).toMatchObject({ total: 5, lifeAtRisk: 1 });
    expect(clusters[0].x).toBeCloseTo((100 + 120 + 139) / 3);
    expect(clusters[2]).toMatchObject({ total: 2, lifeAtRisk: 1, x: 400, y: 300 });
    expect(clusterMarkers([])).toEqual([]);
  });
});

describe("Reports saved on this device", () => {
  it("are counted per subdistrict by their planning area, newest first, and left out for another area", () => {
    const reports = [
      { planning_area_id: "TH570904", created_at: "2026-10-05T03:00:00.000Z", water_depth: "knee" },
      { planning_area_id: "TH570901", created_at: "2026-10-05T04:00:00.000Z", water_depth: "waist" },
      { planning_area_id: "TH570904", created_at: "2026-10-05T05:00:00.000Z", water_depth: "ankle" },
      { planning_area_id: "TH100101", created_at: "2026-10-05T06:00:00.000Z", water_depth: "ankle" },
    ];
    const byTambon = deviceReportsByTambon(reports, tambons.map((feature) => feature.properties.id));
    expect([...byTambon.keys()].sort()).toEqual(["TH570901", "TH570904"]);
    expect(byTambon.get("TH570904")?.map((report) => report.water_depth)).toEqual(["ankle", "knee"]);
    expect(deviceReportsByTambon([], ["TH570901"]).size).toBe(0);
  });
});

describe("The \"no reports received\" mark", () => {
  it("is on a subdistrict with residents in modelled water and neither a place record nor an exercise item", () => {
    const rows = [{ id: "A", inWater: 120 }, { id: "B", inWater: 0.2 }, { id: "C", inWater: 900 }, { id: "D", inWater: 50 }];
    expect(tambonsWithoutReports(rows, new Set(["C"]), new Set(["D"]))).toEqual(["A"]);
    expect(tambonsWithoutReports(rows, new Set(), new Set())).toEqual(["A", "C", "D"]);
  });
});

describe("The modelled depth at a point", () => {
  it("reads the terrain cell under the point: 0 where the model is dry, null outside the grid", () => {
    const bounds = [[20, 99], [21, 100]] as const;
    // A 2 x 2 grid: the channel, a cell 1 m above it, a cell 3 m above it, and a cell the model never wets.
    const codes = new Uint8Array([0, 20, 60, 255]);
    const input = { codes, factorKeys: null, width: 2, height: 2, bounds, step: 0.05 };
    expect(modelDepthAt(input, 20.9, 99.1, 2)).toBeCloseTo(2);
    expect(modelDepthAt(input, 20.9, 99.9, 2)).toBeCloseTo(1);
    expect(modelDepthAt(input, 20.1, 99.1, 2)).toBe(0);
    expect(modelDepthAt(input, 20.1, 99.9, 9)).toBe(0);
    expect(modelDepthAt(input, 22, 99.5, 2)).toBeNull();
    // With a depth-factor channel the depth is scaled cell by cell.
    const factorKeys = new Uint16Array([0 | (255 << 8), 20 | (128 << 8), 60 | (255 << 8), 255 | (255 << 8)]);
    expect(modelDepthAt({ ...input, factorKeys }, 20.9, 99.9, 2)).toBeCloseTo(128 / 255);
  });
});
