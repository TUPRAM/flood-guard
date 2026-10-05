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
  exerciseMarkerBox,
  exerciseMarkerSpec,
  exerciseUrgency,
  hasAddressOrName,
  hasPhonePattern,
  isOpenStatus,
  ITEM_MARKER_OFFSETS,
  shownExerciseItem,
  lifeAtRiskHours,
  modelDepthAt,
  mostUrgentItem,
  parseExerciseFile,
  placeItemMarkers,
  recordBubbleBox,
  tambonsWithoutReports,
  waitingHours,
  type ExerciseHandling,
  type ExerciseKind,
  type ExerciseUrgency,
  type MarkerBox,
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
    // "Life at risk" is about people in the water, not about deep water under people who are dry upstairs: an item
    // with water above head height outside and people on an upper floor follows the rule at "urgent" (EX-07).
    expect(file.rule.en).toContain("people standing in water at chest height or above");
    expect(file.rule.th).toContain("มีคนยืนอยู่ในน้ำที่ลึกระดับอกขึ้นไป");
    const dryUpstairs = file.items.find((item) => item.id === "EX-07")!;
    expect(dryUpstairs).toMatchObject({ urgency: "urgent", depthBand: "over_head", facts: ["no_food_for_a_day"] });
    expect(dryUpstairs.text.en).toContain("on an upper floor");
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
    // The line is at seven digits: six in a run are a count or a code, seven are refused.
    expect(hasPhonePattern("ref 123456")).toBe(false);
    expect(hasPhonePattern("ref 1234567")).toBe(true);
    expect(hasPhonePattern("ref 123 456")).toBe(false);
    expect(hasPhonePattern("ref 123 4567")).toBe(true);
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
          // The waiting clock is on the map for an open item that is urgent or at life at risk; an item of
          // information keeps its clock in the popup and the inspector.
          expect(spec.showsWaiting).toBe(open && urgency !== "information");
          expect(spec.halo).toBe(open && urgency === "life_at_risk");
          expect(spec.shape).toBe(kind === "call" ? "octagon" : "square");
        }
      }
    }
    expect(EXERCISE_STATUSES).toEqual(["new", "acknowledged", "assigned", "done", "dropped"]);
    expect(EXERCISE_STATUSES.filter(isOpenStatus)).toEqual(["new", "acknowledged", "assigned"]);
  });
});

describe("The selected item in the inspector", () => {
  it("is shown from its replay hour on, and never before it", () => {
    const item = file.items.find((entry) => entry.id === "EX-05")!;
    expect(item.hour).toBe(46);
    expect(shownExerciseItem(file.items, "EX-05", 45)).toBeNull();
    expect(shownExerciseItem(file.items, "EX-05", 46)).toBe(item);
    expect(shownExerciseItem(file.items, "EX-05", 264)).toBe(item);
    expect(shownExerciseItem(file.items, "EX-99", 264)).toBeNull();
    expect(shownExerciseItem(file.items, null, 264)).toBeNull();
    for (const entry of file.items) {
      for (const hour of [0, entry.hour - 1, entry.hour, entry.hour + 1]) expect(shownExerciseItem(file.items, entry.id, hour) !== null, `${entry.id} at ${hour}`).toBe(hour >= entry.hour);
    }
  });
});

describe("Clusters of the district zoom", () => {
  it("merges markers within 40 px of a group's first marker, and counts place records and invented items apart", () => {
    const clusters = clusterMarkers([
      { x: 100, y: 100, records: 3, items: 0, lifeAtRisk: false },
      { x: 120, y: 110, records: 0, items: 1, lifeAtRisk: true },
      { x: 139, y: 100, records: 0, items: 1, lifeAtRisk: false },
      { x: 190, y: 100, records: 1, items: 0, lifeAtRisk: false },
      { x: 400, y: 300, records: 0, items: 1, lifeAtRisk: true },
    ]);
    expect(CLUSTER_RADIUS_PX).toBe(40);
    expect(clusters.map((cluster) => cluster.members)).toEqual([[0, 1, 2], [3], [4]]);
    // The two kinds are never added (owner decision 5): a cluster has no total.
    expect(clusters[0]).toMatchObject({ records: 3, items: 2, lifeAtRisk: 1 });
    expect(clusters[0]).not.toHaveProperty("total");
    expect(clusters[0].x).toBeCloseTo((100 + 120 + 139) / 3);
    expect(clusters[1]).toMatchObject({ records: 1, items: 0, lifeAtRisk: 0 });
    expect(clusters[2]).toMatchObject({ records: 0, items: 1, lifeAtRisk: 1, x: 400, y: 300 });
    expect(clusterMarkers([])).toEqual([]);
  });

  it("merges two groups whose middles are within 40 px, so two count marks never stand on each other", () => {
    // The fourth marker is 41 px from the first, so it starts a group; that group's middle is 21 px from the first group's.
    const clusters = clusterMarkers([
      { x: 100, y: 100, records: 3, items: 0, lifeAtRisk: false },
      { x: 120, y: 110, records: 0, items: 1, lifeAtRisk: true },
      { x: 139, y: 100, records: 0, items: 1, lifeAtRisk: false },
      { x: 141, y: 100, records: 0, items: 1, lifeAtRisk: true },
    ]);
    expect(clusters.map((cluster) => cluster.members)).toEqual([[0, 1, 2, 3]]);
    expect(clusters[0]).toMatchObject({ records: 3, items: 3, lifeAtRisk: 2 });
  });
});

describe("Exercise markers of the town zoom: none covers a place record or another item", () => {
  const overlap = (a: MarkerBox, b: MarkerBox): boolean => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

  it("leaves a marker on its point when nothing is in the way", () => {
    expect(placeItemMarkers([], [{ x: 100, y: 100, size: 30, lineWidth: 60 }])).toEqual([{ dx: 0, dy: 0 }]);
    expect(placeItemMarkers([recordBubbleBox(400, 400)], [{ x: 100, y: 100, size: 36, lineWidth: 60 }])).toEqual([{ dx: 0, dy: 0 }]);
    expect(ITEM_MARKER_OFFSETS[0]).toEqual([0, 0]);
  });

  it("moves a marker off a place-record bubble, and the second of two markers off the first", () => {
    const bubble = recordBubbleBox(100, 100);
    const items = [{ x: 104, y: 92, size: 30, lineWidth: 60 }, { x: 110, y: 96, size: 26, lineWidth: 26 }];
    const placed = placeItemMarkers([bubble], items);
    const boxes = items.map((item, index) => exerciseMarkerBox(item.x + placed[index].dx, item.y + placed[index].dy, item.size, item.lineWidth));
    expect(placed[0]).not.toEqual({ dx: 0, dy: 0 });
    for (const box of boxes) expect(overlap(box, bubble)).toBe(false);
    expect(overlap(boxes[0], boxes[1])).toBe(false);
    // The first in the list is placed first: the caller lists the most urgent first, so those keep the nearer place.
    expect(Math.hypot(placed[0].dx, placed[0].dy)).toBeLessThanOrEqual(Math.hypot(placed[1].dx, placed[1].dy));
    for (const shift of placed) expect(ITEM_MARKER_OFFSETS.some(([dx, dy]) => dx === shift.dx && dy === shift.dy)).toBe(true);
  });

  it("depends on distances only, so a pan of the map moves no marker", () => {
    const at = (shift: number) => placeItemMarkers([recordBubbleBox(100 + shift, 100 + shift)], [{ x: 104 + shift, y: 92 + shift, size: 30, lineWidth: 60 }, { x: 150 + shift, y: 96 + shift, size: 26, lineWidth: 26 }]);
    expect(at(0)).toEqual(at(731));
  });

  it("takes the place where it covers least when every place is taken", () => {
    // A wall of obstacles around the point: every offset collides, and the marker still gets a place of the list.
    const wall: MarkerBox[] = [{ left: -400, top: -400, right: 600, bottom: 600 }];
    const [shift] = placeItemMarkers(wall, [{ x: 100, y: 100, size: 30, lineWidth: 60 }]);
    expect(ITEM_MARKER_OFFSETS.some(([dx, dy]) => dx === shift.dx && dy === shift.dy)).toBe(true);
  });

  it("keeps the real place records above the invented items of information in the drawing order", () => {
    // The layer draws an item at 3000 + 100 per urgency step (information 3100, urgent 3200, life at risk 3300) and a
    // place record at 3150: a real 2024 record is never under an invented item of information.
    const rank = (urgency: ExerciseUrgency) => 3000 + (3 - EXERCISE_URGENCIES.indexOf(urgency)) * 100;
    expect(rank("information")).toBeLessThan(3150);
    expect(rank("urgent")).toBeGreaterThan(3150);
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
