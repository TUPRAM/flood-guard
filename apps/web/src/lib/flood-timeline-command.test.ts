/**
 * The figures of the Command exercise replay against the served replay data (the r4 files): the district figures and the
 * rows of the subdistrict table at the modelled peak equal the baked day and the export pack's per-subdistrict summary,
 * every row is zero outside the flood hours, the ordering rules behave as the plan states them (with the measured
 * number of order changes over the replay), and modelled figures are rounded before they are printed.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  roundLikePython,
  stageAt,
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type GeoCollection,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import { parseAccessNodes, planSetId, REPORTED_SET_ID } from "./flood-timeline-evacuation";
import {
  buildCommandModel,
  changeSinceHourBefore,
  clampCommandHour,
  COMMAND_LAST_HOUR,
  COMMAND_SHELTER_SETS,
  commandSetId,
  commandStage,
  districtFiguresAt,
  holdTambonOrder,
  NO_REACH_MARK_SHARE,
  ORDER_LEAD_RESIDENTS,
  orderChangeHours,
  placeRecordsByTambon,
  plainTambonOrder,
  pointInArea,
  reduceTambonOrder,
  roundModelChange,
  roundModelFigure,
  roundModelKm,
  stepTambonOrder,
  tambonOrderByHour,
  tambonRowsAt,
  type CommandShelterSet,
  type OrderRow,
  type TambonOrderState,
} from "./flood-timeline-command";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<unknown, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const nodes = parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!);
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes });

/** The export pack's per-subdistrict summary at the modelled peak (12 Sep 12:00 ICT, replay hour 84). */
interface SummaryAccess { residents: number; already_out_of_reach_before_flood: number; lost_access: number }
interface SummaryRecord {
  tambon_id: string;
  modelled_residents_in_water_at_peak: number;
  modelled_road_km_impassable_at_peak: number;
  modelled_access_at_peak: Record<"reported_2024" | "knee_plan", { all_residents_at_road_nodes: SummaryAccess }>;
}
const summaryFile = manifest.exports!.files.find((file) => file.id === "tambon_replay_summary")!;
const summary = JSON.parse(read(summaryFile.href).toString("utf8")) as { metadata: { peak_local_time: string }; records: SummaryRecord[] };

const PEAK_HOUR = 84;
const hours = Array.from({ length: COMMAND_LAST_HOUR + 1 }, (_, hour) => hour);
const nameOf = (id: string) => model.tambons.find((tambon) => tambon.id === id)!.en;
const whole = (value: number) => roundLikePython(value, 0);

describe("Command replay model", () => {
  it("covers the 265 hourly positions of the replay with the assumed stage of each", () => {
    expect(COMMAND_LAST_HOUR).toBe(264);
    expect(model.stages).toHaveLength(265);
    for (const hour of [0, 36, 43, 44, PEAK_HOUR, 152, 153, 264]) expect(commandStage(model, hour)).toBe(stageAt(hour / 24, manifest.stage_anchors));
    // 12 Sep 12:00 ICT is the modelled peak: 3.5 m, the highest stage of the replay.
    expect(summary.metadata.peak_local_time).toBe("2024-09-12T12:00:00+07:00");
    expect(commandStage(model, PEAK_HOUR)).toBe(3.5);
    expect(Math.max(...model.stages)).toBe(3.5);
    expect(clampCommandHour(-3)).toBe(0);
    expect(clampCommandHour(999)).toBe(264);
    expect(clampCommandHour(83.6)).toBe(84);
    expect(clampCommandHour(Number.NaN)).toBe(0);
  });

  it("holds the eight subdistricts in the order of the access node file, Thai name and romanised name", () => {
    expect(model.tambons.map((tambon) => tambon.id)).toEqual(manifest.access!.tambons);
    expect(model.tambons.map((tambon) => tambon.en)).toEqual(["Mae Sai", "Huai Khrai", "Ko Chang", "Pong Pha", "Si Mueang Chum", "Wiang Phang Kham", "Ban Dai", "Pong Ngam"]);
    expect(model.tambons[0].th).toBe("แม่สาย");
    expect(model.tambons.every((tambon) => /[฀-๿]/.test(tambon.th))).toBe(true);
  });

  it("switches between the shelters reported in 2024 and the first 8 sites of the ranked plan", () => {
    expect(COMMAND_SHELTER_SETS).toEqual(["reported", "plan"]);
    expect(manifest.shelters!.knee_k).toBe(8);
    expect(commandSetId("reported", manifest.shelters!)).toBe(REPORTED_SET_ID);
    expect(commandSetId("plan", manifest.shelters!)).toBe(planSetId(8));
    expect(model.sets.reported.setId).toBe("reported_2024");
    expect(model.sets.plan.setId).toBe("plan_8");
    // The figures change with the set (no set is graded); water and roads do not depend on it.
    const reported = districtFiguresAt(model, PEAK_HOUR, "reported");
    const plan = districtFiguresAt(model, PEAK_HOUR, "plan");
    expect(reported.lostAccess).toBe(7086);
    expect(plan.lostAccess).toBe(13429);
    expect(whole(reported.withinReachBefore)).toBe(34525);
    expect(whole(plan.withinReachBefore)).toBe(24910);
    expect(plan.inWater).toBe(reported.inWater);
    expect(plan.roadKmImpassable).toBe(reported.roadKmImpassable);
    expect(districtFiguresAt(model, PEAK_HOUR)).toEqual(reported);
  });

  it("fails closed without the access scenario, the shelters or the residents, and without a subdistrict boundary", () => {
    const base = { roads: roads.features, tambons: tambons.features, nodes };
    expect(() => buildCommandModel({ ...base, manifest: { ...manifest, access: undefined } })).toThrow(/no access scenario/);
    expect(() => buildCommandModel({ ...base, manifest: { ...manifest, population: undefined } })).toThrow(/no access scenario/);
    expect(() => buildCommandModel({ ...base, tambons: tambons.features.slice(1), manifest })).toThrow(/No boundary for subdistrict TH570901/);
  });
});

describe("District figures at a replay hour", () => {
  it("equal the plan and the export table at replay hour 84: 7,086 lost shelter access, 16,060 in water, 163.8 km", () => {
    const figures = districtFiguresAt(model, PEAK_HOUR);
    expect(figures).toMatchObject({ hour: 84, stage: 3.5, set: "reported", lostAccess: 7086, inWater: 16060, roadKmImpassable: 163.77 });
    expect(figures.roadKmImpassable.toFixed(1)).toBe("163.8");
    // The base of "lost shelter access", the scope it is counted over, and the shipped road total.
    expect(whole(figures.withinReachBefore)).toBe(34525);
    expect(whole(figures.residents)).toBe(manifest.access!.totals.population);
    expect(whole(figures.residents - figures.withinReachBefore)).toBe(47273);
    expect(((figures.residents - figures.withinReachBefore) / figures.residents).toFixed(2)).toBe("0.58");
    expect(figures.roadKmTotal.toFixed(1)).toBe("306.8");
    // The export pack's summary gives the same totals (it rounds each subdistrict to 0.1 or 0.01).
    const lost = summary.records.reduce((sum, record) => sum + record.modelled_access_at_peak.reported_2024.all_residents_at_road_nodes.lost_access, 0);
    const water = summary.records.reduce((sum, record) => sum + record.modelled_residents_in_water_at_peak, 0);
    const km = summary.records.reduce((sum, record) => sum + record.modelled_road_km_impassable_at_peak, 0);
    expect(Math.abs(lost - figures.lostAccess)).toBeLessThan(0.5);
    expect(whole(water)).toBe(figures.inWater);
    expect(km).toBeCloseTo(figures.roadKmImpassable, 1);
  });

  it("equal every baked day at its noon keyframe, for both shelter sets", () => {
    expect(manifest.days).toHaveLength(11);
    manifest.days.forEach((day, index) => {
      const hour = index * 24 + 12;
      for (const set of COMMAND_SHELTER_SETS) {
        const figures = districtFiguresAt(model, hour, set);
        expect(figures.stage, day.date).toBe(day.stage_m);
        expect(figures.lostAccess, `${day.date} ${set}`).toBe(day.stats.access![model.sets[set].setId].people_lost_access);
        expect(figures.inWater, day.date).toBe(day.stats.people_in_water);
        expect(figures.roadKmImpassable, day.date).toBe(day.stats.road_km_impassable);
      }
    });
  });

  it("are never above their base, and are zero at both ends of the replay", () => {
    for (const set of COMMAND_SHELTER_SETS) {
      for (const hour of hours) {
        const figures = districtFiguresAt(model, hour, set);
        expect(figures.lostAccess).toBeLessThanOrEqual(figures.withinReachBefore);
        expect(figures.inWater).toBeLessThanOrEqual(figures.residents);
        expect(figures.roadKmImpassable).toBeLessThanOrEqual(figures.roadKmTotal);
      }
      for (const hour of [0, 12, 264]) expect(districtFiguresAt(model, hour, set)).toMatchObject({ lostAccess: 0, inWater: 0, roadKmImpassable: 0 });
    }
  });
});

describe("Rows of the subdistrict table", () => {
  const rows = tambonRowsAt(model, PEAK_HOUR);
  const byName = Object.fromEntries(rows.map((row) => [row.en, row]));

  it("equal the export pack's per-subdistrict summary at replay hour 84, for both shelter sets", () => {
    expect(summary.records.map((record) => record.tambon_id)).toEqual(rows.map((row) => row.id));
    for (const [set, label] of [["reported", "reported_2024"], ["plan", "knee_plan"]] as [CommandShelterSet, "reported_2024" | "knee_plan"][]) {
      const counted = tambonRowsAt(model, PEAK_HOUR, set);
      summary.records.forEach((record, index) => {
        const access = record.modelled_access_at_peak[label].all_residents_at_road_nodes;
        const row = counted[index];
        expect(roundLikePython(row.lostAccess, 1), `${row.en} ${set} lost`).toBe(access.lost_access);
        expect(row.inWater, `${row.en} in water`).toBe(record.modelled_residents_in_water_at_peak);
        expect(roundLikePython(row.residents, 1), `${row.en} residents`).toBe(access.residents);
        expect(roundLikePython(row.noReachBefore, 1), `${row.en} ${set} no shelter in reach`).toBe(access.already_out_of_reach_before_flood);
      });
    }
  });

  it("give the peak values the plan lists: Mae Sai 5,660 lost shelter access, and the rest of the table", () => {
    expect(whole(byName["Mae Sai"].lostAccess)).toBe(5660);
    expect(rows.map((row) => [row.en, whole(row.lostAccess), whole(row.inWater)])).toEqual([
      ["Mae Sai", 5660, 5920], ["Huai Khrai", 0, 197], ["Ko Chang", 458, 1706], ["Pong Pha", 558, 1922],
      ["Si Mueang Chum", 407, 3466], ["Wiang Phang Kham", 0, 102], ["Ban Dai", 3, 2312], ["Pong Ngam", 0, 435],
    ]);
    // The rows add up to the district figures.
    expect(whole(rows.reduce((sum, row) => sum + row.lostAccess, 0))).toBe(districtFiguresAt(model, PEAK_HOUR).lostAccess);
    expect(whole(rows.reduce((sum, row) => sum + row.inWater, 0))).toBe(districtFiguresAt(model, PEAK_HOUR).inWater);
    expect(whole(rows.reduce((sum, row) => sum + row.residents, 0))).toBe(whole(model.residents));
  });

  it("carry the share of residents with no reported shelter in reach before the flood, and the + mark when that is most of them", () => {
    expect(NO_REACH_MARK_SHARE).toBe(0.5);
    expect(rows.map((row) => [row.en, row.noReachShare, row.mostHadNoReach])).toEqual([
      ["Mae Sai", 0.2477, false], ["Huai Khrai", 1, true], ["Ko Chang", 0.5746, true], ["Pong Pha", 0.605, true],
      ["Si Mueang Chum", 0.7786, true], ["Wiang Phang Kham", 0.3993, false], ["Ban Dai", 0.9994, true], ["Pong Ngam", 0.8327, true],
    ]);
    // The share is a fact of the shelter set, not of the hour: it is the same before the flood and at the peak.
    expect(tambonRowsAt(model, 0).map((row) => row.noReachShare)).toEqual(rows.map((row) => row.noReachShare));
    // Ban Dai at the peak: about 3 residents count as lost while 2,312 are in modelled water.
    expect(roundModelFigure(byName["Ban Dai"].lostAccess).text).toBe("<10");
    expect(whole(byName["Ban Dai"].inWater)).toBe(2312);
    // With the ranked plan's sites the shares differ: the mark follows the chosen set.
    const plan = tambonRowsAt(model, PEAK_HOUR, "plan");
    expect(plan.map((row) => row.noReachShare)).not.toEqual(rows.map((row) => row.noReachShare));
    for (const row of plan) expect(row.mostHadNoReach).toBe(row.noReachShare! > 0.5);
  });

  it("count the located place records of each subdistrict by point-in-polygon", () => {
    expect(model.placeRecords).toEqual({ byTambon: [9, 0, 0, 0, 0, 3, 0, 0], located: 12, unlocated: 9, outside: 0 });
    expect(rows.map((row) => row.placeRecords)).toEqual([9, 0, 0, 0, 0, 3, 0, 0]);
    // Wiang Phang Kham: no resident counted as lost and about 100 in modelled water, yet three place records from news.
    expect(byName["Wiang Phang Kham"]).toMatchObject({ lostAccess: 0, placeRecords: 3 });
    expect(manifest.reported_depths!.counted.place_records).toBe(model.placeRecords.located + model.placeRecords.unlocated);
    // A point outside every boundary is counted as outside, and a record without a point as unlocated.
    expect(placeRecordsByTambon([{ point: { lat: 0, lon: 0 } }, { point: null }, { point: { lat: 20.4441, lon: 99.8791 } }], tambons.features))
      .toEqual({ byTambon: [0, 0, 0, 0, 0, 1, 0, 0], located: 2, unlocated: 1, outside: 1 });
  });

  it("are all zero up to replay hour 43 and from replay hour 153", () => {
    const zeroHours = hours.filter((hour) => tambonRowsAt(model, hour).every((row) => row.lostAccess === 0));
    expect(zeroHours).toEqual([...hours.filter((hour) => hour <= 43), ...hours.filter((hour) => hour >= 153)]);
    // 156 of the 265 hourly positions (the plan wrote 155): hours 0 to 43 and 153 to 264.
    expect(zeroHours).toHaveLength(156);
    expect(districtFiguresAt(model, 43).lostAccess).toBe(0);
    expect(districtFiguresAt(model, 44).lostAccess).toBe(1445);
    expect(districtFiguresAt(model, 152).lostAccess).toBe(300);
    expect(districtFiguresAt(model, 153).lostAccess).toBe(0);
    // Water is on the map before and after anybody counts as lost: zero rows are not dry rows.
    expect(districtFiguresAt(model, 36).inWater).toBe(2667);
    expect(districtFiguresAt(model, 160).inWater).toBeGreaterThan(0);
  });

  it("never hold a score, a class or a position: the replay is not a scored case", () => {
    for (const key of [...Object.keys(rows[0]), ...Object.keys(districtFiguresAt(model, PEAK_HOUR)), ...Object.keys(changeSinceHourBefore(model, PEAK_HOUR))]) {
      expect(key).not.toMatch(/score|class|priority|fpps|rank|position/i);
    }
  });
});

describe("What changed since the hour before", () => {
  it("is nothing at hour 0, where there is no hour before", () => {
    expect(changeSinceHourBefore(model, 0)).toEqual({
      hour: 0, sinceHour: null, lostAccess: 0, inWater: 0, roadKmImpassable: 0,
      newlyImpassable: { named: [], unnamedKm: 0 }, passableAgain: { named: [], unnamedKm: 0 },
    });
  });

  it("gives the three differences and the named roads newly impassable as the water rises", () => {
    const change = changeSinceHourBefore(model, 44);
    expect(change).toMatchObject({ hour: 44, sinceHour: 43, lostAccess: 1445, inWater: 1496, roadKmImpassable: 19.93 });
    // Roads cut for the first time, the more important class first: the bypass (trunk), Phahonyothin Road (primary),
    // Mueang Daeng Road (tertiary).
    expect(change.newlyImpassable.named).toEqual([
      { name: "ถนนเลี่ยงเมืองแม่สาย", km: 0.32, tambons: ["TH570901"], classes: ["trunk"], whole: true },
      { name: "ถนนพหลโยธิน", km: 0.09, tambons: ["TH570906"], classes: ["primary"], whole: true },
      { name: "ถนนเหมืองแดง", km: 0.83, tambons: ["TH570901"], classes: ["tertiary"], whole: true },
    ]);
    expect(change.newlyImpassable.unnamedKm).toBe(18.69);
    expect(change.passableAgain).toEqual({ named: [], unnamedKm: 0 });
    // An hour later more of the same roads is impassable: they are listed again, no longer as cut for the first time.
    const next = changeSinceHourBefore(model, 45);
    expect(next.newlyImpassable.named.every((road) => !road.whole)).toBe(true);
    expect(next.newlyImpassable.named.map((road) => road.name)).toEqual(["ถนนเลี่ยงเมืองแม่สาย", "ถนนเหมืองแดง"]);
  });

  it("gives falling figures and the roads passable again as the river falls", () => {
    const change = changeSinceHourBefore(model, 85);
    expect(change).toMatchObject({ sinceHour: 84, lostAccess: -148, inWater: -177, roadKmImpassable: -3.99 });
    expect(change.newlyImpassable).toEqual({ named: [], unnamedKm: 0 });
    expect(change.passableAgain.unnamedKm).toBe(3.99);
    const last = changeSinceHourBefore(model, 153);
    expect(last.lostAccess).toBe(-300);
    expect(last.passableAgain.named.every((road) => road.whole)).toBe(true);
    expect(changeSinceHourBefore(model, 200)).toMatchObject({ lostAccess: 0, roadKmImpassable: 0, newlyImpassable: { named: [], unnamedKm: 0 } });
  });

  it("adds up: the differences rebuild the figures of every hour, and the road lists rebuild the road difference", () => {
    for (const set of COMMAND_SHELTER_SETS) {
      let lost = 0;
      let water = 0;
      let km = 0;
      for (const hour of hours) {
        const change = changeSinceHourBefore(model, hour, set);
        lost += change.lostAccess;
        water += change.inWater;
        km += change.roadKmImpassable;
        const figures = districtFiguresAt(model, hour, set);
        expect(lost, `${set} hour ${hour}`).toBe(figures.lostAccess);
        expect(water, `hour ${hour}`).toBe(figures.inWater);
        expect(km).toBeCloseTo(figures.roadKmImpassable, 6);
        const listed = (roads: typeof change.newlyImpassable) => roads.named.reduce((sum, road) => sum + road.km, roads.unnamedKm);
        expect(listed(change.newlyImpassable) - listed(change.passableAgain)).toBeCloseTo(change.roadKmImpassable, 1);
      }
    }
  });
});

describe("Rounding of modelled figures", () => {
  it("prints a tilde with the nearest 10 below 1,000 and the nearest 100 above, <10 for tiny values and a plain 0", () => {
    const cases: [number, string][] = [
      [0, "0"], [0.4, "0"], [0.5, "<10"], [2.9, "<10"], [9.4, "<10"], [9.5, "~10"], [14, "~10"], [15, "~20"], [102, "~100"], [196.6, "~200"],
      [434.9, "~430"], [558.2, "~560"], [994, "~990"], [995, "~1,000"], [1000, "~1,000"], [1049, "~1,000"], [1050, "~1,100"], [5659.8, "~5,700"],
      [7086, "~7,100"], [16060, "~16,100"], [34525.2, "~34,500"], [81798.5, "~81,800"], [1234567, "~1,234,600"],
      [-5, "0"], [Number.NaN, "0"], [Number.POSITIVE_INFINITY, "0"],
    ];
    for (const [value, text] of cases) expect(roundModelFigure(value).text, String(value)).toBe(text);
    expect(roundModelFigure(0)).toEqual({ text: "0", value: 0, kind: "zero" });
    expect(roundModelFigure(2.9)).toEqual({ text: "<10", value: 3, kind: "under_ten" });
    expect(roundModelFigure(7086)).toEqual({ text: "~7,100", value: 7100, kind: "rounded" });
  });

  it("prints road lengths as whole kilometres with a tilde, <1 below one kilometre", () => {
    const cases: [number, string][] = [[0, "0"], [0.004, "0"], [0.4, "<1"], [0.99, "<1"], [1, "~1"], [19.93, "~20"], [163.77, "~164"], [306.805, "~307"], [1234.5, "~1,235"], [-2, "0"]];
    for (const [value, text] of cases) expect(roundModelKm(value).text, String(value)).toBe(text);
  });

  it("prints a difference with its sign, and 0 when the figure did not move by a whole unit", () => {
    expect(roundModelChange(96)).toEqual({ text: "+~100", direction: 1 });
    expect(roundModelChange(-148)).toEqual({ text: "−~150", direction: -1 });
    expect(roundModelChange(3)).toEqual({ text: "+<10", direction: 1 });
    expect(roundModelChange(-0.3)).toEqual({ text: "0", direction: 0 });
    expect(roundModelChange(0)).toEqual({ text: "0", direction: 0 });
    expect(roundModelChange(Number.NaN)).toEqual({ text: "0", direction: 0 });
    expect(roundModelChange(19.93, roundModelKm)).toEqual({ text: "+~20", direction: 1 });
    expect(roundModelChange(-0.4, roundModelKm)).toEqual({ text: "−<1", direction: -1 });
    expect(roundModelChange(-3.99, roundModelKm).text).toBe("−~4");
  });

  it("gives the figures of replay hour 84 as the wireframe prints them", () => {
    const figures = districtFiguresAt(model, PEAK_HOUR);
    expect([roundModelFigure(figures.lostAccess).text, roundModelFigure(figures.withinReachBefore).text, roundModelFigure(figures.inWater).text,
      roundModelKm(figures.roadKmImpassable).text, roundModelKm(figures.roadKmTotal).text]).toEqual(["~7,100", "~34,500", "~16,100", "~164", "~307"]);
    const rows = tambonRowsAt(model, PEAK_HOUR);
    const order = tambonOrderByHour(model)[PEAK_HOUR].map((id) => rows.find((row) => row.id === id)!);
    expect(order.map((row) => [row.en, `${roundModelFigure(row.lostAccess).text}${row.mostHadNoReach ? "+" : ""}`, roundModelFigure(row.inWater).text])).toEqual([
      ["Mae Sai", "~5,700", "~5,900"], ["Pong Pha", "~560+", "~1,900"], ["Ko Chang", "~460+", "~1,700"], ["Si Mueang Chum", "~410+", "~3,500"],
      ["Ban Dai", "<10+", "~2,300"], ["Pong Ngam", "0+", "~430"], ["Huai Khrai", "0+", "~200"], ["Wiang Phang Kham", "0", "~100"],
    ]);
  });
});

describe("Ordering rules of the table", () => {
  const row = (id: string, lostAccess: number, inWater = 0): OrderRow => ({ id, lostAccess, inWater });

  it("orders by residents who lost shelter access, then by residents in water, then by subdistrict code", () => {
    expect(plainTambonOrder([row("C", 10), row("A", 300), row("B", 40)])).toEqual(["A", "B", "C"]);
    // Ties, the zero rows among them, by residents in water and then by code.
    expect(plainTambonOrder([row("D", 0, 5), row("C", 0, 90), row("B", 0, 90), row("A", 0, 0)])).toEqual(["B", "C", "D", "A"]);
    // Whole residents are compared, as the table prints them: 0.3 of a modelled resident does not lead a zero row.
    expect(plainTambonOrder([row("A", 0.3, 10), row("B", 0, 50)])).toEqual(["B", "A"]);
    expect(stepTambonOrder(null, [row("C", 10), row("A", 300), row("B", 40)])).toEqual(["A", "B", "C"]);
  });

  it("lets a row overtake when it leads by at least 25 residents, or when its printed figure is higher", () => {
    expect(ORDER_LEAD_RESIDENTS).toBe(25);
    const before = ["A", "B", "C"];
    // Two rows that print the same figure ("~1,300"): the lead of 25 decides.
    expect(stepTambonOrder(before, [row("A", 1300), row("B", 1324), row("C", 10)])).toEqual(["A", "B", "C"]);
    expect(stepTambonOrder(before, [row("A", 1300), row("B", 1325), row("C", 10)])).toEqual(["B", "A", "C"]);
    // Once ahead, a row is not overtaken back until the other leads by 25 again.
    expect(stepTambonOrder(["B", "A", "C"], [row("A", 1310), row("B", 1300), row("C", 10)])).toEqual(["B", "A", "C"]);
    expect(stepTambonOrder(["B", "A", "C"], [row("A", 1325), row("B", 1300), row("C", 10)])).toEqual(["A", "B", "C"]);
    // A row can pass several rows in one step when it leads each of them.
    expect(stepTambonOrder(before, [row("A", 100), row("B", 90), row("C", 130)])).toEqual(["C", "A", "B"]);
    // It passes nobody when the row just above keeps it back, even if it leads a row further up by 25.
    expect(stepTambonOrder(before, [row("A", 1200), row("B", 1210), row("C", 1226)])).toEqual(["A", "B", "C"]);
    // A row whose printed figure is higher always overtakes, whatever its lead: the table never shows a lower figure
    // over a higher one. "~1,700" passes "~1,600" with a lead of 23, "~320" passes "~300", and a row above zero passes
    // a row at zero, so a row that reads "0" never stands over a row that reads "<10".
    expect(stepTambonOrder(["A", "B"], [row("A", 1647.8), row("B", 1670.9)])).toEqual(["B", "A"]);
    expect(stepTambonOrder(["A", "B"], [row("A", 300), row("B", 324)])).toEqual(["B", "A"]);
    expect(stepTambonOrder(["A", "B"], [row("A", 0, 900), row("B", 2, 10)])).toEqual(["B", "A"]);
    expect(stepTambonOrder(["A", "B", "C"], [row("A", 0, 900), row("B", 0.4, 10), row("C", 1.9, 10)])).toEqual(["C", "A", "B"]);
    expect(stepTambonOrder(["A", "B"], [row("A", 1, 900), row("B", 24, 10)])).toEqual(["B", "A"]);
    // Two rows that both read "<10" print the same figure: the lead of 25 holds between them.
    expect(stepTambonOrder(["A", "B"], [row("A", 2, 900), row("B", 8, 10)])).toEqual(["A", "B"]);
    // Rows with the same count are re-ordered by residents in water, then by code, whatever the order before.
    expect(stepTambonOrder(["B", "A", "C"], [row("A", 0, 40), row("B", 0, 10), row("C", 0, 80)])).toEqual(["C", "A", "B"]);
    expect(stepTambonOrder(["B", "A"], [row("A", 7, 3), row("B", 7, 3)])).toEqual(["A", "B"]);
    // Other rows than before, a repeated id or no order at all: the plain order.
    expect(stepTambonOrder(["A", "X", "C"], [row("A", 1), row("B", 3), row("C", 2)])).toEqual(["B", "C", "A"]);
    expect(stepTambonOrder(["A", "A", "C"], [row("A", 1), row("B", 3), row("C", 2)])).toEqual(["B", "C", "A"]);
    expect(stepTambonOrder(["A"], [row("A", 1), row("B", 3)])).toEqual(["B", "A"]);
    // A lead of 0 is the plain order at every step.
    expect(stepTambonOrder(before, [row("A", 300), row("B", 301), row("C", 10)], 0)).toEqual(["B", "A", "C"]);
  });

  it("holds the shown order while the numbers update, and shows the ruled order when the hold ends", () => {
    let state: TambonOrderState | null = null;
    state = reduceTambonOrder(state, [row("A", 3000), row("B", 1000), row("C", 10)]);
    expect(state).toEqual({ order: ["A", "B", "C"], ruled: ["A", "B", "C"], held: false, pending: false });
    // Held and nothing to move: no "Order held" line.
    state = reduceTambonOrder(state, [row("A", 2900), row("B", 1200), row("C", 10)], { hold: true });
    expect(state).toEqual({ order: ["A", "B", "C"], ruled: ["A", "B", "C"], held: true, pending: false });
    // Held while B overtakes A: the shown order stays, the ruled order moves on, and the table says so.
    state = reduceTambonOrder(state, [row("A", 2000), row("B", 2600), row("C", 10)], { hold: true });
    expect(state).toEqual({ order: ["A", "B", "C"], ruled: ["B", "A", "C"], held: true, pending: true });
    // The ruled order keeps its own memory under the hold: A is 10 ahead again and prints the same "~2,600", which
    // is not enough to pass B back.
    state = reduceTambonOrder(state, [row("A", 2610), row("B", 2600), row("C", 10)], { hold: true });
    expect(state).toMatchObject({ order: ["A", "B", "C"], ruled: ["B", "A", "C"], held: true, pending: true });
    // Released: the ruled order of the latest hour.
    state = reduceTambonOrder(state, [row("A", 2610), row("B", 2600), row("C", 10)]);
    expect(state).toEqual({ order: ["B", "A", "C"], ruled: ["B", "A", "C"], held: false, pending: false });
    // A hold with nothing shown yet, or over other rows, shows the ruled order.
    expect(reduceTambonOrder(null, [row("B", 5), row("A", 9)], { hold: true })).toEqual({ order: ["A", "B"], ruled: ["A", "B"], held: false, pending: false });
    expect(holdTambonOrder({ order: ["X", "Y"] }, ["A", "B"], true)).toEqual({ order: ["A", "B"], ruled: ["A", "B"], held: false, pending: false });
    // The hold rule on its own, over the order of an hour read from the precomputed list.
    expect(holdTambonOrder({ order: ["A", "B"] }, ["B", "A"], true)).toEqual({ order: ["A", "B"], ruled: ["B", "A"], held: true, pending: true });
    expect(holdTambonOrder({ order: ["A", "B"] }, ["B", "A"], false)).toEqual({ order: ["B", "A"], ruled: ["B", "A"], held: false, pending: false });
    // A custom lead reaches the step.
    expect(reduceTambonOrder({ order: ["A", "B"], ruled: ["A", "B"], held: false, pending: false }, [row("A", 10), row("B", 15)], { lead: 5 }).order).toEqual(["B", "A"]);
  });

  describe("over the 264 hours of the replay", () => {
    const rowsByHour = hours.map((hour) => tambonRowsAt(model, hour));
    const plain = rowsByHour.map((rows) => plainTambonOrder(rows));
    const ruled = tambonOrderByHour(model);
    /** The order of the rows above zero only (whole residents), which is what the plan counted. */
    const aboveZero = (orders: string[][]) => orders.map((order, hour) => order.filter((id) => Math.round(rowsByHour[hour].find((row) => row.id === id)!.lostAccess) > 0));

    it("has Mae Sai first whenever any row is above zero, and the wireframe's order at the peak", () => {
      for (const hour of hours.filter((item) => item >= 44 && item <= 152)) {
        expect(plain[hour][0], `hour ${hour}`).toBe("TH570901");
        expect(ruled[hour][0], `hour ${hour}`).toBe("TH570901");
      }
      expect(ruled[PEAK_HOUR].map(nameOf)).toEqual(["Mae Sai", "Pong Pha", "Ko Chang", "Si Mueang Chum", "Ban Dai", "Pong Ngam", "Huai Khrai", "Wiang Phang Kham"]);
      expect(ruled[PEAK_HOUR]).toEqual(plain[PEAK_HOUR]);
      // Before any water every row ties at zero in both columns: the order is the subdistrict code.
      expect(ruled[0]).toEqual([...manifest.access!.tambons].sort());
    });

    it("changes order 14 times without the 25-resident rule and 12 times with it (9 and 7 times among the rows above zero)", () => {
      // Without the rule: the plain order of every hour (a lead of 0 gives the same list).
      expect(tambonOrderByHour(model, "reported", 0)).toEqual(plain);
      expect(orderChangeHours(plain)).toEqual([31, 43, 44, 45, 50, 99, 117, 118, 131, 142, 153, 155, 164, 198]);
      // The plan counted 9: the changes in the order of the rows above zero.
      expect(orderChangeHours(aboveZero(plain))).toEqual([44, 45, 50, 99, 117, 118, 131, 147, 153]);
      // With the rule the swap of hours 117 and 118 is gone.
      // A row above zero passes a row at zero at once, so Ban Dai ("<10") is over Pong Pha ("0") from hour 131 and
      // nothing is left to move at hour 147.
      expect(orderChangeHours(ruled)).toEqual([31, 43, 44, 45, 50, 99, 131, 142, 153, 155, 164, 198]);
      expect(orderChangeHours(aboveZero(ruled))).toEqual([44, 45, 50, 99, 131, 147, 153]);
      // The same count for the ranked plan's sites: 18 without the rule, 17 with it.
      expect(orderChangeHours(hours.map((hour) => plainTambonOrder(tambonRowsAt(model, hour, "plan"))))).toHaveLength(18);
      expect(orderChangeHours(tambonOrderByHour(model, "plan"))).toHaveLength(17);
    });

    it("never prints a lower figure above a higher one, at any hour and with either shelter set", () => {
      const printed = (value: number) => {
        const figure = roundModelFigure(value);
        return figure.kind === "under_ten" ? 1 : figure.value;
      };
      for (const set of COMMAND_SHELTER_SETS) {
        const orders = tambonOrderByHour(model, set);
        for (const hour of hours) {
          const rows = tambonRowsAt(model, hour, set);
          const figures = orders[hour].map((id) => printed(rows.find((item) => item.id === id)!.lostAccess));
          expect(figures, `${set} hour ${hour}`).toEqual([...figures].sort((a, b) => b - a));
        }
      }
      // The two hours a review named, with the ranked plan's sites: "~1,700" stood under "~1,600" at hour 91, and
      // "~380" under "~360" at hour 125.
      const plan = tambonOrderByHour(model, "plan");
      const read = (hour: number) => plan[hour].map((id) => `${nameOf(id)} ${roundModelFigure(tambonRowsAt(model, hour, "plan").find((item) => item.id === id)!.lostAccess).text}`);
      expect(read(91).slice(1, 3)).toEqual(["Wiang Phang Kham ~1,700", "Si Mueang Chum ~1,600"]);
      expect(read(125).indexOf("Pong Pha ~380")).toBeLessThan(read(125).indexOf("Si Mueang Chum ~360"));
    });

    it("never keeps a row that reads 0 above a row with somebody counted, with either shelter set", () => {
      for (const set of COMMAND_SHELTER_SETS) {
        const orders = tambonOrderByHour(model, set);
        for (const hour of hours) {
          const rows = tambonRowsAt(model, hour, set);
          const lost = orders[hour].map((id) => Math.round(rows.find((item) => item.id === id)!.lostAccess));
          const firstZero = lost.indexOf(0);
          if (firstZero >= 0) expect(lost.slice(firstZero).every((value) => value === 0), `${set} hour ${hour}: ${lost.join(" ")}`).toBe(true);
        }
      }
      // The hours the review named: Ban Dai ("<10") now stands above Pong Pha ("0") at hours 131 to 146.
      const names = (hour: number) => ruled[hour].map(nameOf);
      for (const hour of [131, 140, 146]) expect(names(hour).indexOf("Ban Dai"), `hour ${hour}`).toBeLessThan(names(hour).indexOf("Pong Pha"));
      const plan = tambonOrderByHour(model, "plan");
      const planRows = tambonRowsAt(model, 44, "plan");
      const planLost = plan[44].map((id) => Math.round(planRows.find((item) => item.id === id)!.lostAccess));
      expect(planLost).toEqual([...planLost].sort((a, b) => Number(b > 0) - Number(a > 0)));
    });

    it("keeps Ko Chang above Pong Pha through hours 117 and 118, where a few residents separate them", () => {
      const lost = (hour: number, name: string) => whole(rowsByHour[hour].find((row) => row.en === name)!.lostAccess);
      expect([lost(116, "Ko Chang"), lost(116, "Pong Pha")]).toEqual([402, 329]);
      expect([lost(117, "Ko Chang"), lost(117, "Pong Pha")]).toEqual([308, 311]);
      expect([lost(118, "Ko Chang"), lost(118, "Pong Pha")]).toEqual([308, 307]);
      const pair = (order: string[]) => order.filter((id) => id === "TH570903" || id === "TH570904").map(nameOf).join(" > ");
      // The plain order swaps the two at hour 117 and swaps them back at hour 118.
      expect([116, 117, 118, 119].map((hour) => pair(plain[hour]))).toEqual(["Ko Chang > Pong Pha", "Pong Pha > Ko Chang", "Ko Chang > Pong Pha", "Ko Chang > Pong Pha"]);
      // With the rule Pong Pha never leads by 25, so the rows stay where they were.
      expect([116, 117, 118, 119].map((hour) => pair(ruled[hour]))).toEqual(Array.from({ length: 4 }, () => "Ko Chang > Pong Pha"));
    });

    it("gives every hour one order: a jump on the time bar shows what playing up to that hour shows", () => {
      expect(ruled).toHaveLength(265);
      for (const order of ruled) expect([...order].sort()).toEqual([...manifest.access!.tambons].sort());
      // Stepping the reducer hour by hour without a hold gives the same list.
      let state: TambonOrderState | null = null;
      for (const hour of hours) {
        state = reduceTambonOrder(state, rowsByHour[hour]);
        expect(state.order, `hour ${hour}`).toEqual(ruled[hour]);
      }
    });
  });
});

describe("Point-in-polygon", () => {
  const square: AreaGeometry = { type: "Polygon", coordinates: [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]] };
  const two: AreaGeometry = { type: "MultiPolygon", coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]], [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]]] };

  it("reads polygons with holes and multi-polygons", () => {
    expect(pointInArea(2, 2, square)).toBe(true);
    expect(pointInArea(5, 5, square)).toBe(false); // in the hole
    expect(pointInArea(11, 5, square)).toBe(false);
    expect(pointInArea(0.5, 0.5, two)).toBe(true);
    expect(pointInArea(5.5, 5.5, two)).toBe(true);
    expect(pointInArea(3, 3, two)).toBe(false);
    expect(pointInArea(1, 1, { type: "Polygon", coordinates: [] })).toBe(false);
  });

  it("puts the district office in Wiang Phang Kham and a point in Myanmar in no subdistrict", () => {
    const find = (lat: number, lon: number) => tambons.features.find((feature) => pointInArea(lon, lat, feature.geometry))?.properties.en ?? null;
    const office = manifest.shelters!.reported.find((site) => site.id === "R05")!;
    expect(find(office.lat!, office.lon!)).toBe("Wiang Phang Kham");
    expect(find(20.4441, 99.8791)).toBe("Wiang Phang Kham"); // Sai Lom Joy border market
    expect(find(20.4434, 99.8831)).toBe("Mae Sai"); // Ko Sai community
    expect(find(20.47, 99.88)).toBeNull(); // across the Sai River
  });
});
