/**
 * The subdistrict table and the inspector of the Command exercise replay, as pure functions: the rows as the table
 * prints them from the served r4 files, the two orders kept apart, the hold of the order, the plan cells read from a
 * planning assessment overlay (the E11 fixture with its invented units, in tests only), the figures of one
 * subdistrict, and the find-place index.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import fixture from "./__fixtures__/planning-assessment-overlay.fixture.json";
import {
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type LineGeometry,
  type PointGeometry,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import {
  buildCommandModel,
  holdTambonOrder,
  ORDER_LEAD_RESIDENTS,
  plainTambonOrder,
  stepTambonOrder,
  tambonOrderByHour,
  tambonRowsAt,
  type CommandTambonRow,
} from "./flood-timeline-command";
import {
  buildCommandFindIndex,
  COMMAND_OVERLAY_HREFS,
  COMMAND_PLANNING_CASES,
  commandHoldReducer,
  commandOverlayRefusal,
  commandTableRows,
  DEFAULT_POSITION_CASE,
  hasPlanningPositions,
  lostAccessScale,
  niceCeiling,
  NO_COMMAND_HOLD,
  normaliseFindText,
  parsePeakSummary,
  placeRecordsOfTambons,
  planningCellOfRow,
  planningCells,
  planningFacts,
  planningPositions,
  readCommandOverlay,
  searchCommandPlaces,
  tambonDetailAt,
  tambonRowsBefore,
  type CommandPlanningCell,
} from "./flood-timeline-command-table";
import { parseAccessNodes } from "./flood-timeline-evacuation";
import { parsePlanningAssessmentOverlay, type PlanningAssessmentOverlay } from "./planning-assessment-overlay";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const json = <T,>(href: string): T => JSON.parse(read(href).toString("utf8")) as T;
const manifest = json<TimelineManifest>(TIMELINE_MANIFEST_URL);
const roads = json<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href);
const tambons = json<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href);
const facilities = json<GeoCollection<PointGeometry, FacilityProps>>(manifest.vectors.facilities.href);
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes: parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!) });
const summaryFile = manifest.exports!.files.find((file) => file.id === "tambon_replay_summary")!;
const peaks = parsePeakSummary(json<unknown>(summaryFile.href));
const orders = tambonOrderByHour(model);
const scale = lostAccessScale(model);

/** The E11 fixture: invented units, never a place. It is read in tests only. */
const overlay: PlanningAssessmentOverlay = parsePlanningAssessmentOverlay(fixture);
const fixtureCells = { O1: planningCells(overlay, "O1"), SE1: planningCells(overlay, "SE1") };
const noCells = { O1: new Map<string, CommandPlanningCell>(), SE1: new Map<string, CommandPlanningCell>() };
const fixtureRow = (rowId: string) => overlay.rows.find((row) => row.row_id === `FX-CASE-01:${rowId}`)!;

const tableAt = (hour: number, more: Partial<Parameters<typeof commandTableRows>[0]> = {}) => commandTableRows({
  rows: tambonRowsAt(model, hour), before: tambonRowsBefore(model, hour, "reported"), order: orders[hour], scale, orderBy: "hour", positionFrom: DEFAULT_POSITION_CASE, cells: noCells, ...more,
});

/** Invented rows on the left for the invented units on the right, so no invented class is ever attached to a real subdistrict. */
const inventedRows: CommandTambonRow[] = ["FX-U03", "FX-U13", "FX-U14", "FX-U15", "FX-U01"].map((id, index) => ({
  id, th: `หน่วยทดสอบ ${id.slice(-2)}`, en: `Fixture unit ${id.slice(-2)}`, lostAccess: 500 - index * 100, inWater: 900 - index * 50,
  residents: 2000, noReachBefore: 100, noReachShare: 0.05, mostHadNoReach: false, placeRecords: 0,
}));
const inventedTable = (more: Partial<Parameters<typeof commandTableRows>[0]> = {}) => commandTableRows({
  rows: inventedRows, before: null, order: inventedRows.map((row) => row.id), scale: 1000, orderBy: "hour", positionFrom: "SE1", cells: fixtureCells, ...more,
});

describe("Rows of the table as it prints them", () => {
  it("prints replay hour 84 in the order of the plan's wireframe, with rounded figures and no plan cell", () => {
    const rows = tableAt(84);
    expect(rows.map((item) => item.row.en)).toEqual(["Mae Sai", "Pong Pha", "Ko Chang", "Si Mueang Chum", "Ban Dai", "Pong Ngam", "Huai Khrai", "Wiang Phang Kham"]);
    expect(rows.map((item) => item.position)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(rows.map((item) => item.lost.text)).toEqual(["~5,700", "~560", "~460", "~410", "<10", "0", "0", "0"]);
    expect(rows.map((item) => item.water.text)).toEqual(["~5,900", "~1,900", "~1,700", "~3,500", "~2,300", "~430", "~200", "~100"]);
    // No overlay exists for Mae Sai: every plan cell is empty and no row has a planning position.
    for (const item of rows) {
      expect(item.cells).toEqual({ O1: null, SE1: null });
      expect(item.planningPosition).toBeNull();
    }
    expect(hasPlanningPositions(noCells.SE1)).toBe(false);
    // The left half holds a count and nothing that rates a subdistrict (decision D7).
    for (const item of rows) expect(Object.keys(item).sort()).toEqual(["bar", "cells", "change", "lost", "planningPosition", "position", "row", "water"]);
  });

  it("draws the bar on one fixed scale for the whole replay and for both shelter sets", () => {
    expect(scale).toBe(10_000);
    const peak = tableAt(84);
    expect(peak[0].bar).toBeCloseTo(peak[0].row.lostAccess / 10_000, 9);
    expect(peak[0].bar).toBeCloseTo(0.566, 3);
    for (const hour of [0, 43, 60, 84, 117, 152, 264]) {
      for (const item of tableAt(hour)) {
        expect(item.bar).toBeGreaterThanOrEqual(0);
        expect(item.bar).toBeLessThanOrEqual(1);
      }
    }
    // The plan set reaches higher counts; the same scale holds them.
    const plan = commandTableRows({ rows: tambonRowsAt(model, 84, "plan"), before: null, order: tambonOrderByHour(model, "plan")[84], scale, orderBy: "hour", positionFrom: "SE1", cells: noCells });
    expect(Math.max(...plan.map((item) => item.bar))).toBeLessThanOrEqual(1);
    expect(Math.max(...plan.map((item) => item.row.lostAccess))).toBeGreaterThan(8000);
    expect([niceCeiling(5660), niceCeiling(8399), niceCeiling(1), niceCeiling(0), niceCeiling(10_000), niceCeiling(140)]).toEqual([6000, 10_000, 1, 1, 10_000, 150]);
  });

  it("gives every row its change since the hour before, rounded like the figure", () => {
    const rising = tableAt(84);
    expect(rising[0].change).toEqual({ text: "+~100", direction: 1 });
    const first = tableAt(0);
    for (const item of first) expect(item.change).toEqual({ text: "0", direction: 0 });
    // As the river falls the count falls, and the arrow points down.
    const falling = [...Array(60).keys()].map((step) => tableAt(100 + step)).find((rows) => rows.some((item) => item.change.direction < 0));
    expect(falling).toBeDefined();
    expect(falling!.find((item) => item.change.direction < 0)!.change.text).toMatch(/^−(~[\d,]+|<10)$/);
    expect(tambonRowsBefore(model, 0, "reported")).toBeNull();
  });
});

describe("Order of the rows: order, ties, the 25-resident rule and the hold", () => {
  const row = (id: string, lostAccess: number, inWater = 0) => ({ id, lostAccess, inWater });

  it("orders by residents who lost shelter access, breaks ties by residents in water, then by code", () => {
    expect(plainTambonOrder([row("C", 5, 9), row("A", 5, 9), row("B", 80), row("D", 5, 20)])).toEqual(["B", "D", "A", "C"]);
    // All rows at zero: residents in water decide, then the code.
    expect(plainTambonOrder([row("C", 0, 1), row("B", 0, 3), row("A", 0, 1)])).toEqual(["B", "A", "C"]);
  });

  it("lets a row overtake only when it leads by at least 25 residents", () => {
    expect(ORDER_LEAD_RESIDENTS).toBe(25);
    const before = ["A", "B"];
    expect(stepTambonOrder(before, [row("A", 300), row("B", 324)])).toEqual(["A", "B"]);
    expect(stepTambonOrder(before, [row("A", 300), row("B", 325)])).toEqual(["B", "A"]);
  });

  it("holds the order while the pointer, the keyboard or the time thumb holds it, and still updates the numbers", () => {
    // Find an hour at which the ruled order changes.
    const changeHour = orders.findIndex((order, hour) => hour > 0 && order.join() !== orders[hour - 1].join());
    expect(changeHour).toBeGreaterThan(0);
    const shown = orders[changeHour - 1];
    let hold = commandHoldReducer(NO_COMMAND_HOLD, { source: "pointer", held: true, order: shown });
    expect(hold.frozen).toEqual(shown);
    // A second hold keeps the first order; it does not freeze a newer one.
    hold = commandHoldReducer(hold, { source: "drag", held: true, order: orders[changeHour] });
    expect(hold.frozen).toEqual(shown);
    const held = holdTambonOrder({ order: hold.frozen! }, orders[changeHour], true);
    expect(held).toMatchObject({ order: shown, held: true, pending: true });
    // The rows keep the held order and carry the figures of the new hour.
    const rows = tableAt(changeHour, { order: held.order });
    expect(rows.map((item) => item.row.id)).toEqual(shown);
    const fresh = new Map(tambonRowsAt(model, changeHour).map((item) => [item.id, item]));
    for (const item of rows) expect(item.row.lostAccess).toBe(fresh.get(item.row.id)!.lostAccess);
    // One hold ends: the order stays. The last one ends: the ruled order shows.
    hold = commandHoldReducer(hold, { source: "pointer", held: false, order: null });
    expect(hold.frozen).toEqual(shown);
    hold = commandHoldReducer(hold, { source: "drag", held: false, order: null });
    expect(hold).toEqual(NO_COMMAND_HOLD);
    expect(holdTambonOrder(null, orders[changeHour], false)).toMatchObject({ order: orders[changeHour], pending: false });
    // The same hold twice changes nothing.
    const once = commandHoldReducer(NO_COMMAND_HOLD, { source: "focus", held: true, order: shown });
    expect(commandHoldReducer(once, { source: "focus", held: true, order: orders[changeHour] })).toBe(once);
  });
});

describe("Plan cells from a planning assessment overlay (fixture units, in tests only)", () => {
  it("looks for one optional file per case, and takes the planning position from SE1 unless asked", () => {
    expect(COMMAND_PLANNING_CASES).toEqual(["O1", "SE1"]);
    expect(COMMAND_OVERLAY_HREFS).toEqual({ O1: "/planning-overlays/mae-sai-2024/o1.json", SE1: "/planning-overlays/mae-sai-2024/se1.json" });
    expect(DEFAULT_POSITION_CASE).toBe("SE1");
  });

  it("never puts the fixture, another case, a local overlay or a refused file on the page", () => {
    expect(readCommandOverlay(fixture, "O1")).toEqual({ overlay: null, refusal: "fixture" });
    expect(readCommandOverlay(fixture, "SE1")).toEqual({ overlay: null, refusal: "fixture" });
    expect(readCommandOverlay({ rows: [] }, "O1")).toEqual({ overlay: null, refusal: "refused_by_parser" });
    expect(readCommandOverlay("not an overlay", "SE1").refusal).toBe("refused_by_parser");
    // A fixture relabelled as a real case is refused by the parser: its case is not one the protocol describes.
    expect(readCommandOverlay({ ...fixture, dataset_mode: "candidate", case: { ...fixture.case, kind: "portfolio_case", case_id: "O1" } }, "O1").refusal).toBe("refused_by_parser");
    // What the page checks after the parser: the kind of case, the case asked for and the publication level.
    const real = { case: { ...overlay.case, kind: "portfolio_case" as const, case_id: "SE1" }, dataset_mode: "candidate" as const, publication_eligibility: "public" as const };
    expect(commandOverlayRefusal(real, "SE1")).toBeNull();
    expect(commandOverlayRefusal(real, "O1")).toBe("other_case");
    expect(commandOverlayRefusal({ ...real, publication_eligibility: "pitch" }, "SE1")).toBe("not_public");
    expect(commandOverlayRefusal({ ...real, publication_eligibility: "local" }, "SE1")).toBe("not_public");
    expect(commandOverlayRefusal({ ...real, dataset_mode: "fixture_demo" }, "SE1")).toBe("fixture");
    expect(commandOverlayRefusal(overlay, "O1")).toBe("fixture");
  });

  it("reads the rows of each case by the lane and tier the protocol gives it, and never the would-be class", () => {
    expect(planningCells(null, "O1").size).toBe(0);
    // O1: own candidates, observed lane, tier T2. Both invented units are low confidence, so the binding class is E.
    expect([...fixtureCells.O1.keys()]).toEqual(["FX-U14", "FX-U15"]);
    for (const cell of fixtureCells.O1.values()) {
      expect(cell).toMatchObject({ planningCase: "O1", letter: "E", reasonCode: "low_confidence", tier: "T2", lane: "OBS", confidenceClass: "low", headline: "not_evaluated", filled: false, otherRows: 0 });
    }
    // The overlay holds a would-be class for both; the page never shows it.
    expect([fixtureRow("obs-t2-c1-and-c4-own-candidate").would_be_class, fixtureRow("obs-t2-c1-own-candidate").would_be_class]).toEqual(["D", "C"]);
    for (const cell of fixtureCells.O1.values()) {
      expect(Object.values(cell)).not.toContain("D");
      expect(Object.values(cell)).not.toContain("C");
    }
    // SE1: the season-envelope scenario lane. One class is headline-eligible (a filled chip), one is not evaluated.
    expect([...fixtureCells.SE1.keys()]).toEqual(["FX-U03", "FX-U13"]);
    expect(fixtureCells.SE1.get("FX-U03")).toMatchObject({ letter: "C", lane: "SCN-ENV", tier: "T1", headline: "headline_eligible", filled: true, scenarioId: "FX-ENV" });
    expect(fixtureCells.SE1.get("FX-U13")).toMatchObject({ letter: "E", headline: "not_evaluated", filled: false });
    // Rows of other lanes (agency maps, engine rows, the locked tier) are in neither column.
    const used = new Set([...fixtureCells.O1.values(), ...fixtureCells.SE1.values()].map((cell) => cell.rowId));
    expect(used.size).toBe(4);
    expect(overlay.rows.length).toBe(26);
  });

  it("reads an unstable class and a unit under 100 residents as the overlay states them", () => {
    const unstable = planningCellOfRow(fixtureRow("obs-t3-class-b"), "O1");
    expect(unstable).toMatchObject({ letter: "B", headline: "unstable_verify", filled: false });
    const small = planningCellOfRow(fixtureRow("obs-t3-c6-gr1-no-class"), "O1");
    expect(small).toMatchObject({ letter: null, reasonCode: "insufficient_denominator" });
  });

  it("derives the planning position inside one case, by the planning score, and never across cases", () => {
    expect(Object.fromEntries(planningPositions(fixtureCells.SE1.values()))).toEqual({ "FX-U13": 1, "FX-U03": 2 });
    expect(Object.fromEntries(planningPositions(fixtureCells.O1.values()))).toEqual({ "FX-U15": 1, "FX-U14": 2 });
    // Units with one score share a position; a unit without a score has none.
    const cell = (unitId: string, fpps: number | null): CommandPlanningCell => ({ ...fixtureCells.O1.get("FX-U14")!, unitId, fpps });
    expect(Object.fromEntries(planningPositions([cell("a", 60), cell("b", 60), cell("c", 20), cell("d", null)]))).toEqual({ a: 1, b: 1, c: 3 });
    expect(hasPlanningPositions(fixtureCells.SE1)).toBe(true);
    // The position column follows the chosen case only.
    const fromSe1 = inventedTable({ positionFrom: "SE1" });
    const fromO1 = inventedTable({ positionFrom: "O1" });
    expect(fromSe1.map((item) => [item.row.id, item.planningPosition])).toEqual([["FX-U03", 2], ["FX-U13", 1], ["FX-U14", null], ["FX-U15", null], ["FX-U01", null]]);
    expect(fromO1.map((item) => [item.row.id, item.planningPosition])).toEqual([["FX-U03", null], ["FX-U13", null], ["FX-U14", 2], ["FX-U15", 1], ["FX-U01", null]]);
    // Both chips always show, whichever case the position comes from.
    expect(fromO1.map((item) => [item.cells.O1?.letter ?? null, item.cells.SE1?.letter ?? null])).toEqual([[null, "C"], [null, "E"], ["E", null], ["E", null], [null, null]]);
  });

  it("orders the rows by the planning position when asked, and keeps this hour's place of each row beside it", () => {
    const byPlanning = inventedTable({ orderBy: "planning", positionFrom: "SE1" });
    expect(byPlanning.map((item) => item.row.id)).toEqual(["FX-U13", "FX-U03", "FX-U14", "FX-U15", "FX-U01"]);
    // The left position is still the place in this hour's count: the two orders stand side by side.
    expect(byPlanning.map((item) => item.position)).toEqual([2, 1, 3, 4, 5]);
    expect(inventedTable({ orderBy: "hour" }).map((item) => item.row.id)).toEqual(["FX-U03", "FX-U13", "FX-U14", "FX-U15", "FX-U01"]);
    // Nothing in a row compares the two orders or blends them.
    for (const item of byPlanning) expect(Object.keys(item)).not.toContain("differs");
  });

  it("carries the tier, the protocol versions and the anchors a class is shown with", () => {
    const facts = planningFacts(overlay);
    expect(facts.protocol).toEqual(overlay.protocol_sha256);
    expect(facts.classRule).toBe("class_rule_v1");
    expect(facts.floodAnchor).toBe(0.2);
    expect(facts.vulnerabilityAnchors).toEqual({ lower: "P10", lowerValue: 0.351416, upper: "P90", upperValue: 0.477677 });
  });
});

describe("One subdistrict in the inspector", () => {
  const facilityProps = facilities.features.map((feature) => feature.properties);

  it("gives the figures of the hour, the impassable road length and the facilities in water", () => {
    const detail = tambonDetailAt(model, facilityProps, 84, "reported", "TH570901")!;
    expect(detail.row.en).toBe("Mae Sai");
    expect(Math.round(detail.row.lostAccess)).toBe(5660);
    expect(Math.round(detail.withinReachBefore)).toBe(13_460);
    expect(detail.roadKmImpassable).toBe(57.33);
    expect(detail.roadKmModelled).toBeGreaterThan(detail.roadKmImpassable);
    expect(detail.roadsImpassable.map((road) => road.name)).toContain("ถนนเหมืองแดง");
    expect(detail.facilities.total).toBe(facilityProps.filter((facility) => facility.t === "TH570901").length);
    expect(detail.facilities.inWater.length).toBeLessThanOrEqual(detail.facilities.modelled);
    expect(tambonDetailAt(model, facilityProps, 84, "reported", "TH000000")).toBeNull();
    // Before the flood nothing is impassable and nothing is in water.
    const dry = tambonDetailAt(model, facilityProps, 0, "reported", "TH570901")!;
    expect([dry.roadKmImpassable, dry.roadsImpassable.length, dry.facilities.inWater.length]).toEqual([0, 0, 0]);
  });

  it("equals the export pack's summary at the modelled peak, subdistrict by subdistrict", () => {
    expect(peaks.size).toBe(8);
    for (const tambon of model.tambons) {
      const peak = peaks.get(tambon.id)!;
      const detail = tambonDetailAt(model, facilityProps, 84, "reported", tambon.id)!;
      expect(peak.peakLocalTime).toBe("2024-09-12T12:00:00+07:00");
      expect(detail.roadKmImpassable, tambon.en).toBe(peak.roadKmImpassable);
      expect(detail.row.inWater, tambon.en).toBe(peak.residentsInWater);
      expect(Math.abs(detail.row.lostAccess - peak.access.reported!.lostAccess), tambon.en).toBeLessThan(0.06);
      expect(Math.abs(detail.withinReachBefore - peak.access.reported!.withinReachBefore), tambon.en).toBeLessThan(0.06);
      const plan = tambonDetailAt(model, facilityProps, 84, "plan", tambon.id)!;
      expect(Math.abs(plan.row.lostAccess - peak.access.plan!.lostAccess), tambon.en).toBeLessThan(0.06);
    }
    expect(peaks.get("TH570901")).toMatchObject({ peakStage: 3.5, floodedKm2: 9.669, floodedShare: 0.4485, residentsInWater: 5920.5 });
  });

  it("reads only well-formed records of the summary", () => {
    expect(parsePeakSummary(null).size).toBe(0);
    expect(parsePeakSummary({ records: "none" }).size).toBe(0);
    expect(parsePeakSummary({ records: [{ tambon_id: "X" }, 7, { tambon_id: "Y", modelled_peak_local_time: "2024-09-12T12:00:00+07:00", modelled_peak_stage_m: 3.5, modelled_flooded_km2_at_peak: 1, modelled_residents_in_water_at_peak: 2, modelled_road_km_impassable_at_peak: 3 }] }))
      .toEqual(new Map([["Y", { tambonId: "Y", peakStage: 3.5, peakLocalTime: "2024-09-12T12:00:00+07:00", floodedKm2: 1, floodedShare: null, residentsInWater: 2, roadKmImpassable: 3, access: { reported: null, plan: null } }]]));
  });

  it("lists the located place records of each subdistrict by their point, as ordinary place records", () => {
    const reports = manifest.reported_depths!.reports;
    const places = placeRecordsOfTambons(reports, tambons.features);
    const count = (id: string) => places.get(id)!.reduce((sum, place) => sum + place.reports.length, 0);
    expect(model.tambons.map((tambon) => count(tambon.id))).toEqual(model.placeRecords.byTambon);
    expect([...places.values()].flat().reduce((sum, place) => sum + place.reports.length, 0)).toBe(12);
    expect([...places.values()].flat()).toHaveLength(9);
    // Records at one point are one place; a record without a point is in no list.
    expect(places.get("TH570901")!.some((place) => place.reports.length > 1)).toBe(true);
    const listed = new Set([...places.values()].flat().flatMap((place) => place.reports.map((report) => report.id)));
    for (const report of reports) expect(listed.has(report.id)).toBe(report.point !== null);
    // A record is the record of the data and nothing more: no tag is added to it.
    for (const place of [...places.values()].flat()) for (const report of place.reports) expect(reports).toContain(report);
  });
});

describe("Find a place: only the names the replay data holds", () => {
  const index = buildCommandFindIndex({ manifest, tambons: tambons.features, facilities: facilities.features, roads: roads.features });
  const kinds = (kind: string) => index.filter((entry) => entry.kind === kind);

  it("indexes the subdistricts, the reported sites, the places of the place records, the named facilities and the named roads", () => {
    expect(kinds("tambon")).toHaveLength(8);
    expect(kinds("shelter")).toHaveLength(18);
    expect(kinds("command_centre")).toHaveLength(1);
    expect(kinds("road").map((entry) => entry.th ?? entry.en).sort()).toEqual(["The 2nd Friendship Bridge", "ถนนพหลโยธิน", "ถนนฤทธิประศาสน์", "ถนนห้วยไคร้ - ห้วยน้ำริน", "ถนนเลี่ยงเมืองแม่สาย", "ถนนเหมืองแดง"]);
    expect(kinds("facility")).toHaveLength(facilities.features.filter((feature) => feature.properties.n.trim()).length);
    // Every place record is behind one entry; the entries with a point sit on the nine reported places.
    expect(kinds("place_record").reduce((sum, entry) => sum + entry.records, 0)).toBe(manifest.reported_depths!.reports.length);
    expect(new Set(kinds("place_record").filter((entry) => entry.target).map((entry) => (entry.target!.type === "point" ? `${entry.target!.lat},${entry.target!.lon}` : ""))).size).toBe(9);
    expect(new Set(index.map((entry) => entry.id)).size).toBe(index.length);
    // Four reported shelters have no coordinates: they are listed, and cannot be shown.
    expect(kinds("shelter").filter((entry) => entry.target === null)).toHaveLength(4);
    expect(kinds("place_record").filter((entry) => entry.target === null).length).toBeGreaterThan(0);
  });

  it("finds a name in either language, names that start with the query first, subdistricts before the rest", () => {
    expect(searchCommandPlaces(index, "mae sai")[0]).toMatchObject({ kind: "tambon", th: "แม่สาย", target: { type: "tambon", id: "TH570901" } });
    expect(searchCommandPlaces(index, "แม่สาย")[0]).toMatchObject({ kind: "tambon", en: "Mae Sai" });
    expect(searchCommandPlaces(index, "  PONG  ").slice(0, 2).map((entry) => entry.en)).toEqual(["Pong Pha", "Pong Ngam"]);
    const road = searchCommandPlaces(index, "phahon")[0];
    expect(road).toMatchObject({ kind: "road", th: "ถนนพหลโยธิน", en: "Phahonyothin Rd (Hwy 1)" });
    expect(road.target).toMatchObject({ type: "road", name: "ถนนพหลโยธิน" });
    expect(searchCommandPlaces(index, "ko sai").map((entry) => entry.kind)).toContain("place_record");
    const place = searchCommandPlaces(index, "Ko Sai community")[0];
    expect(place.target).toEqual({ type: "point", lat: 20.4434, lon: 99.8831, toleranceM: 150, siteId: null });
    const office = searchCommandPlaces(index, "district office")[0];
    expect(office).toMatchObject({ kind: "command_centre", target: { type: "point", siteId: "R05" } });
    expect(searchCommandPlaces(index, "โรงเรียน").every((entry) => entry.kind === "facility" || entry.kind === "place_record")).toBe(true);
  });

  it("finds nothing for an empty query or a name the data does not hold, and keeps to its limit", () => {
    expect(searchCommandPlaces(index, "")).toEqual([]);
    expect(searchCommandPlaces(index, "   ")).toEqual([]);
    expect(searchCommandPlaces(index, "Bangkok")).toEqual([]);
    expect(searchCommandPlaces(index, "a", 5)).toHaveLength(5);
    expect(normaliseFindText(" Mae-Sai (moo 7) ")).toBe("maesaimoo7");
    // Spaces and hyphens are dropped in Thai too, and both sides of a comparison are normalised the same way.
    expect(normaliseFindText("ถนน ห้วยไคร้ - ห้วยน้ำริน")).toBe(normaliseFindText("ถนนห้วยไคร้ห้วยน้ำริน"));
    expect(normaliseFindText("ถนน ห้วยไคร้ - ห้วยน้ำริน")).not.toMatch(/[\s-]/);
  });
});
