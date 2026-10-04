/**
 * The subdistrict table (region B2), the inspector (region D) and the find-place box of the Command exercise replay,
 * as they render. The table and the inspector are rendered with the served r4 files, where no planning class has been
 * issued: every plan cell is a dash and the cards say "Not issued yet". The plan group with classes is rendered only
 * with the E11 fixture, whose units are invented, on invented rows: no invented class is ever attached to a real
 * subdistrict. Every rendered panel passes the shared wording lint.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import fixture from "@/lib/__fixtures__/planning-assessment-overlay.fixture.json";
import {
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type Language,
  type LineGeometry,
  type PointGeometry,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import { buildCommandModel, tambonOrderByHour, tambonRowsAt, type CommandShelterSet, type CommandTambonRow } from "@/lib/flood-timeline-command";
import {
  buildCommandFindIndex,
  commandTableRows,
  lostAccessScale,
  parsePeakSummary,
  placeRecordsOfTambons,
  planningCellOfRow,
  planningCells,
  planningFacts,
  tambonDetailAt,
  tambonRowsBefore,
  type CommandOrderBy,
  type CommandPlanningCase,
  type CommandPlanningCell,
  type CommandTableRow,
} from "@/lib/flood-timeline-command-table";
import { parseAccessNodes } from "@/lib/flood-timeline-evacuation";
import { parsePlanningAssessmentOverlay } from "@/lib/planning-assessment-overlay";
import { describeWordingFindings, findWordingViolations, visibleText } from "@/lib/replay-wording-lint";

import { ACTION_TEXT } from "./command-workspace";
import { MaeSaiCommandExercise } from "./mae-sai-command-exercise";
import { MaeSaiCommandFind } from "./mae-sai-command-find";
import {
  CommandCardChip,
  CommandCaseCard,
  CommandDetailEmpty,
  CommandKnownPlaceholder,
  CommandTambonDetailBody,
  MaeSaiCommandInspector,
} from "./mae-sai-command-inspector";
import { CommandPlanChip, CommandQueueControls, CommandQueueTable, MaeSaiCommandQueue, type CommandQueueProps } from "./mae-sai-command-queue";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const json = <T,>(href: string): T => JSON.parse(read(href).toString("utf8")) as T;
const manifest = json<TimelineManifest>(TIMELINE_MANIFEST_URL);
const roads = json<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href);
const tambons = json<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href);
const facilities = json<GeoCollection<PointGeometry, FacilityProps>>(manifest.vectors.facilities.href);
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes: parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!) });
const scale = lostAccessScale(model);
const peaks = parsePeakSummary(json<unknown>(manifest.exports!.files.find((file) => file.id === "tambon_replay_summary")!.href));
const places = placeRecordsOfTambons(manifest.reported_depths!.reports, tambons.features);
const facilityProps = facilities.features.map((feature) => feature.properties);
const findIndex = buildCommandFindIndex({ manifest, tambons: tambons.features, facilities: facilities.features, roads: roads.features });

const LANGUAGES: readonly Language[] = ["en", "th"];
const noop = () => undefined;
const html = (node: ReactElement) => renderToStaticMarkup(node);
const text = (markup: string) => visibleText(markup).replace(/\s+/g, " ").trim();
const lintOf = (markup: string, source: string) => describeWordingFindings(findWordingViolations(visibleText(markup), source));
/** The text of one column group of the table: the head cells and every row's cells of that group. */
const groupText = (markup: string, group: "hour" | "plan") => {
  const parts = markup.split(/(?=<span[^>]*data-group="(?:hour|plan)")/).filter((part) => part.includes(`data-group="${group}"`));
  // The last plan part runs on into the footer: it ends where the rows end.
  return text(parts.map((part) => part.split("data-command-table-foot")[0]).join(" "));
};

const noCells = { O1: new Map<string, CommandPlanningCell>(), SE1: new Map<string, CommandPlanningCell>() };
const rowsAt = (hour: number, set: CommandShelterSet = "reported", order?: readonly string[]): CommandTableRow[] => commandTableRows({
  rows: tambonRowsAt(model, hour, set), before: tambonRowsBefore(model, hour, set), order: order ?? tambonOrderByHour(model, set)[hour], scale, orderBy: "hour", positionFrom: "SE1", cells: noCells,
});
const table = (language: Language, more: { hour?: number; selected?: string | null; pending?: boolean; set?: CommandShelterSet } = {}) =>
  html(<CommandQueueTable language={language} rows={rowsAt(more.hour ?? 84, more.set)} selected={more.selected ?? null} onSelect={noop} set={more.set ?? "reported"} positionFrom="SE1" pending={more.pending ?? false} />);
const queueProps = (language: Language, more: Partial<CommandQueueProps> = {}): CommandQueueProps => ({
  language, rows: rowsAt(84), selected: null, onSelect: noop, set: "reported", onSet: noop, setSites: { reported: 12, plan: 8 }, orderBy: "hour", onOrderBy: noop, canOrderByPlanning: false,
  positionFrom: "SE1", onPositionFrom: noop, pending: false, optionsOpen: true, onOptions: noop, ...more,
});

/** The E11 fixture: invented units, read in tests only. Invented rows stand on the left of its invented classes. */
const overlay = parsePlanningAssessmentOverlay(fixture);
const fixtureCells = { O1: planningCells(overlay, "O1"), SE1: planningCells(overlay, "SE1") };
const fixtureFacts = planningFacts(overlay);
const inventedRows: CommandTambonRow[] = ["FX-U03", "FX-U13", "FX-U14", "FX-U15", "FX-U01"].map((id, index) => ({
  id, th: `หน่วยทดสอบ ${id.slice(-2)}`, en: `Fixture unit ${id.slice(-2)}`, lostAccess: 500 - index * 100, inWater: 900 - index * 50,
  residents: 2000, noReachBefore: 100, noReachShare: 0.05, mostHadNoReach: false, placeRecords: 0,
}));
const inventedTable = (orderBy: CommandOrderBy = "hour", positionFrom: CommandPlanningCase = "SE1") => commandTableRows({
  rows: inventedRows, before: null, order: inventedRows.map((row) => row.id), scale: 1000, orderBy, positionFrom, cells: fixtureCells,
});
const fixtureTable = (language: Language, orderBy: CommandOrderBy = "hour", positionFrom: CommandPlanningCase = "SE1") =>
  html(<CommandQueueTable language={language} rows={inventedTable(orderBy, positionFrom)} selected={null} onSelect={noop} set="reported" positionFrom={positionFrom} pending={false} />);
const NEVER_SAFE = { en: "Class E never means safe", th: "ระดับ E ไม่ได้หมายความว่าปลอดภัย" } as const;
const count = (haystack: string, needle: string) => haystack.split(needle).length - 1;

const detailOf = (id: string, language: Language, more: { hour?: number; set?: CommandShelterSet; peak?: "ready" | "loading" | "missing" } = {}) => {
  const set = more.set ?? "reported";
  const status = more.peak ?? "ready";
  return html(<CommandTambonDetailBody language={language} hour={more.hour ?? 84} detail={tambonDetailAt(model, facilityProps, more.hour ?? 84, set, id)!} set={set}
    peak={status === "ready" ? peaks.get(id) ?? null : null} peakStatus={status} places={places.get(id) ?? []} depths={manifest.reported_depths ?? null}
    unlocated={model.placeRecords.unlocated} cells={{ O1: null, SE1: null }} facts={{ O1: null, SE1: null }} />);
};

describe("Subdistrict table (region B2): the rows", () => {
  it("is one table with two column groups: this hour's model count, and the plan fixed in time", () => {
    const markup = table("en");
    expect(markup).toMatch(/role="table" aria-label="Subdistrict table"/);
    expect([...markup.matchAll(/role="columnheader" aria-colspan="(\d)" data-group="(hour|plan)"/g)].map((match) => `${match[2]}:${match[1]}`)).toEqual(["hour:4", "plan:3"]);
    expect(groupText(markup, "hour")).toContain("This hour · model low confidence");
    expect(groupText(markup, "plan")).toContain("Plan · fixed");
    expect(groupText(markup, "plan")).toContain("Fixed in time: it does not follow the replay hour");
    expect([...markup.matchAll(/data-tambon="(TH\d+)"/g)].map((match) => match[1])).toHaveLength(8);
    // Column captions of the two groups.
    expect(groupText(markup, "hour")).toContain("subdistrict lost access in water");
    expect(groupText(markup, "plan")).toMatch(/O1 SE1 #/);
  });

  it("prints replay hour 84 as the plan's wireframe does, Thai name first", () => {
    const markup = table("en");
    const names = [...markup.matchAll(/<span class="[^"]*" lang="th">([^<]+)<\/span><span class="[^"]*" lang="en">([^<]+)<\/span>/g)].map((match) => `${match[1]} ${match[2]}`);
    expect(names).toEqual(["แม่สาย Mae Sai", "โป่งผา Pong Pha", "เกาะช้าง Ko Chang", "ศรีเมืองชุม Si Mueang Chum", "บ้านด้าย Ban Dai", "โป่งงาม Pong Ngam", "ห้วยไคร้ Huai Khrai", "เวียงพางคำ Wiang Phang Kham"]);
    const hour = groupText(markup, "hour");
    for (const figure of ["~5,700", "~5,900", "~560", "~1,900", "~460", "~1,700", "~410", "~3,500", "<10", "~2,300", "~430", "~200", "~100"]) expect(hour, figure).toContain(figure);
    // The change since the hour before stands beside the count, with its arrow.
    expect(markup).toMatch(/data-direction="up" title="\+~100 since the hour before"/);
    // The bar of the top row on the fixed scale of 10,000 residents.
    expect(markup).toContain('style="width:56.6%"');
    // The Thai page keeps the same order and figures.
    expect(groupText(table("th"), "hour")).toContain("ชั่วโมงนี้ · แบบจำลอง ความเชื่อมั่นต่ำ");
    expect(groupText(table("th"), "hour")).toContain("~5,700");
  });

  it("marks the rows where most residents had no shelter in reach before the flood, with a one-line footer", () => {
    const markup = table("en");
    const marked = [...markup.matchAll(/data-tambon="(TH\d+)"(?:(?!data-tambon=).)*?data-command-no-reach/gs)].map((match) => match[1]);
    expect(marked).toEqual(tambonRowsAt(model, 84).filter((row) => row.mostHadNoReach).map((row) => row.id).sort((a, b) => rowsAt(84).findIndex((row) => row.row.id === a) - rowsAt(84).findIndex((row) => row.row.id === b)));
    // Ban Dai, Pong Ngam and Huai Khrai are among them, as in the plan.
    for (const id of ["TH570908", "TH570909", "TH570902"]) expect(marked).toContain(id);
    expect(marked).not.toContain("TH570901");
    expect(text(markup)).toContain("+ most residents had no reported shelter within 2 km before the flood");
    expect(text(table("en", { set: "plan" }))).toContain("+ most residents had no site of the plan within 2 km before the flood");
    expect(text(table("th"))).toContain("+ ผู้อยู่อาศัยส่วนใหญ่ไม่มีที่พักพิงตามรายงานในระยะเดิน 2 กม. ตั้งแต่ก่อนน้ำท่วม");
  });

  it("shows the count of located place records on the rows that have any", () => {
    const markup = table("en");
    expect([...markup.matchAll(/data-command-records="(\d+)"/g)].map((match) => Number(match[1]))).toEqual(model.placeRecords.byTambon.filter((records) => records > 0).sort((a, b) => b - a));
    expect(text(markup)).toContain("9 located place records (news, not surveyed)");
    // Wiang Phang Kham reads 0 lost access and holds place records: a low model figure is not "fine".
    expect(markup).toMatch(/data-tambon="TH570906"(?:(?!data-tambon=).)*data-command-records="3"/s);
  });

  it("never prints a score, a priority or a class in the left group, in either language", () => {
    for (const hour of [0, 44, 84, 130, 264]) {
      const english = groupText(html(<CommandQueueTable language="en" rows={rowsAt(hour)} selected={null} onSelect={noop} set="reported" positionFrom="SE1" pending={false} />), "hour");
      expect(english, String(hour)).not.toMatch(/score|priorit|class|FPPS|rank/i);
      const thai = groupText(html(<CommandQueueTable language="th" rows={rowsAt(hour)} selected={null} onSelect={noop} set="reported" positionFrom="SE1" pending={false} />), "hour");
      expect(thai, String(hour)).not.toMatch(/คะแนน|ลำดับความสำคัญ|ระดับ|FPPS/);
    }
    // The left group of the fixture table holds none either, although its right group holds classes.
    expect(groupText(fixtureTable("en"), "hour")).not.toMatch(/score|priorit|class|FPPS/i);
  });

  it("highlights the selected row and names the row's button by the subdistrict", () => {
    const markup = table("en", { selected: "TH570904" });
    expect(markup).toMatch(/data-tambon="TH570904" data-selected="true"/);
    expect(count(markup, 'data-selected="true"')).toBe(1);
    expect(markup).toMatch(/aria-pressed="true" data-command-row="TH570904"/);
    expect(count(markup, 'aria-pressed="false"')).toBe(7);
  });

  it("says that the order is held while it differs from the order of the hour", () => {
    expect(table("en")).toContain('data-order-held="false"');
    expect(table("en")).not.toContain("data-command-order-held");
    const held = table("en", { pending: true });
    expect(held).toContain('data-order-held="true"');
    expect(text(held)).toContain("Order held");
    expect(text(held)).toContain("The numbers still follow the replay hour.");
    expect(text(table("th", { pending: true }))).toContain("คงลำดับไว้");
    // A held order keeps its rows where they were, with the figures of the new hour.
    const reversed = [...tambonOrderByHour(model)[84]].reverse();
    const rows = rowsAt(84, "reported", reversed);
    expect(rows.map((item) => item.row.id)).toEqual(reversed);
    expect(rows.at(-1)!.lost.text).toBe("~5,700");
  });
});

describe("Subdistrict table: the honest empty state of the plan group", () => {
  it("shows a dash in every chip and position, and says that nothing is issued yet", () => {
    for (const language of LANGUAGES) {
      const markup = table(language);
      expect(count(markup, 'data-state="empty"')).toBe(16);
      expect(markup).not.toMatch(/data-state="(filled|outline|unstable)"/);
      expect(markup).not.toContain("data-letter=");
      expect(markup).toContain("data-command-not-issued");
    }
    const markup = table("en");
    const plan = groupText(markup, "plan");
    // Every chip says it twice: once for a screen reader, once on hover.
    expect(count(plan, "O1: Not issued yet")).toBe(2 * 8);
    expect(count(plan, "Planning position from SE1: Not issued yet")).toBe(8);
    // The SE1 chip says it twice too; the eight positions above end in the same words.
    expect(count(plan, "SE1: Not issued yet")).toBe(2 * 8 + 8);
    expect(text(markup)).toContain("Not issued yet. Planning class from the signed protocol. Fixed in time. Not computed from this replay hour.");
    expect(text(table("th"))).toContain("ยังไม่ออกผล. ระดับการวางแผนมาจากหลักเกณฑ์ที่ลงนามแล้ว");
    // No class is shown, so nothing is said about class E.
    expect(text(markup)).not.toContain(NEVER_SAFE.en);
    // The fixture never appears on the page: no invented unit is in a table of the real subdistricts.
    expect(markup).not.toContain("FX-");
    expect(text(markup)).not.toMatch(/fixture/i);
  });
});

describe("Subdistrict table: the plan group with classes (fixture units on both sides)", () => {
  it("prints Class E never means safe wherever an E appears", () => {
    for (const language of LANGUAGES) {
      const markup = fixtureTable(language);
      const letters = [...markup.matchAll(/data-letter="([A-E])"/g)].map((match) => match[1]);
      expect(letters).toEqual(["C", "E", "E", "E"]);
      // Once under the table, and once in the label of every chip that shows an E.
      expect(markup).toContain("data-command-e-never-safe");
      const chips = [...markup.matchAll(/data-letter="E" title="([^"]+)"/g)].map((match) => match[1]);
      expect(chips).toHaveLength(3);
      for (const label of chips) expect(label).toContain(NEVER_SAFE[language]);
      // The sentence stands under the table, and with each of the three chips (for a screen reader and on hover).
      expect(count(text(markup), NEVER_SAFE[language])).toBe(1 + 2 * 3);
      // The chip of class C carries no such sentence.
      expect(markup.match(/data-letter="C" title="([^"]+)"/)![1]).not.toContain(NEVER_SAFE[language]);
    }
  });

  it("shows O1 on the own-candidate chip and SE1 on the scenario chip, filled only when headline-eligible", () => {
    const markup = fixtureTable("en");
    const chips = [...markup.matchAll(/data-case="(O1|SE1)" data-state="([a-z]+)" data-size="small"(?: data-letter="([A-E])")?/g)].map((match) => `${match[1]}:${match[2]}:${match[3] ?? "-"}`);
    expect(chips).toEqual([
      "O1:empty:-", "SE1:filled:C", // FX-U03: scenario class C, headline-eligible
      "O1:empty:-", "SE1:outline:E", // FX-U13: scenario class E, stability not evaluated
      "O1:outline:E", "SE1:empty:-", // FX-U14: own candidate, E by the protocol's display rule
      "O1:outline:E", "SE1:empty:-",
      "O1:empty:-", "SE1:empty:-", // FX-U01: no row in either case
    ]);
    const plain = text(markup);
    expect(plain).toContain("O1: Class E · Monitor and verify · Class E never means safe · Own model candidate: verify before action · stability not evaluated");
    expect(plain).toContain("SE1: Class C · Protect essential services · Scenario: what-if (2024 season envelope) · headline-eligible: the class holds when one component at a time is left out");
    expect(plain).toContain("O1 · Own model candidate: verify before action. SE1 · Scenario: what-if (2024 season envelope).");
    // A class has been issued, so the footer no longer says "Not issued yet".
    expect(markup).not.toContain("data-command-not-issued");
    // The would-be class of a low-confidence row is never shown.
    expect(plain).not.toMatch(/would[- ]be/i);
  });

  it("puts one planning position beside the two chips, from the chosen case", () => {
    const position = (markup: string) => [...markup.matchAll(/data-tambon="(FX-U\d+)".*?<span aria-hidden="true">([–\d]+)<\/span><span[^>]*>Planning position from (O1|SE1)/gs)].map((match) => `${match[1]}:${match[2]}:${match[3]}`);
    expect(position(fixtureTable("en", "hour", "SE1"))).toEqual(["FX-U03:2:SE1", "FX-U13:1:SE1", "FX-U14:–:SE1", "FX-U15:–:SE1", "FX-U01:–:SE1"]);
    expect(position(fixtureTable("en", "hour", "O1"))).toEqual(["FX-U03:–:O1", "FX-U13:–:O1", "FX-U14:2:O1", "FX-U15:1:O1", "FX-U01:–:O1"]);
    // Ordered by planning, the rows follow that position; this hour's place of each row stays in the left group.
    const byPlanning = fixtureTable("en", "planning", "SE1");
    expect([...byPlanning.matchAll(/data-tambon="(FX-U\d+)"/g)].map((match) => match[1])).toEqual(["FX-U13", "FX-U03", "FX-U14", "FX-U15", "FX-U01"]);
  });

  it("reads unstable: verify, and gives no class to a unit under 100 residents", () => {
    const row = (id: string) => overlay.rows.find((item) => item.row_id === `FX-CASE-01:${id}`)!;
    const unstable = html(<CommandPlanChip planningCase="O1" cell={planningCellOfRow(row("obs-t3-class-b"), "O1")} language="en" />);
    expect(unstable).toContain('data-state="unstable"');
    expect(unstable).toContain(">B?<");
    expect(text(unstable)).toContain("unstable: verify");
    const small = html(<CommandPlanChip planningCase="O1" cell={planningCellOfRow(row("obs-t3-c6-gr1-no-class"), "O1")} language="en" />);
    expect(small).toContain('data-state="empty"');
    expect(text(small)).toContain("No class: fewer than 100 residents");
    expect(text(html(<CommandPlanChip planningCase="SE1" cell={null} language="th" />))).toContain("SE1: ยังไม่ออกผล");
  });
});

describe("Subdistrict table: the controls and the card", () => {
  const controls = (language: Language, more: Partial<Parameters<typeof CommandQueueControls>[0]> = {}) => html(
    <CommandQueueControls language={language} orderBy="hour" onOrderBy={noop} canOrderByPlanning={false} positionFrom="SE1" onPositionFrom={noop} set="reported" onSet={noop} setSites={{ reported: 12, plan: 8 }} {...more} />);

  it("has the three controls above the table: the order, the case of the planning position and the shelter set", () => {
    const markup = controls("en");
    expect(text(markup)).toContain("Order rows by This hour Planning");
    expect(text(markup)).toContain("Planning position from O1");
    expect(text(markup)).toContain("Shelter set 2024 · 12");
    expect(text(markup)).toContain("Plan · 8");
    expect(markup).toMatch(/aria-pressed="true"[^>]*data-option="hour"/);
    expect(markup).toMatch(/aria-pressed="true"[^>]*data-option="SE1"/);
    expect(markup).toMatch(/aria-pressed="true"[^>]*data-option="reported"/);
    // The note of the shelter-set switch: the scope, and no set is graded.
    expect(text(markup)).toContain("All residents at road nodes · figures change with the set · no set is graded");
    expect(text(markup)).toContain("The first 8 sites of the ranked plan: candidates to verify, not a list of sites to open");
    expect(text(markup)).toContain("The 12 located sites among the shelters reported in use in 2024");
    expect(text(controls("th"))).toContain("เรียงแถวตาม ชั่วโมงนี้ การวางแผน");
    expect(text(controls("th"))).toContain("นับผู้อยู่อาศัยทั้งหมดที่จุดถนน · ตัวเลขเปลี่ยนตามชุดที่เลือก · ไม่ได้ตัดสินชุดใด");
  });

  it("cannot order by planning while no planning position is issued, and can once one is", () => {
    const empty = controls("en");
    expect(empty).toMatch(/aria-pressed="false" disabled="" title="No planning position has been issued, so the rows cannot be ordered by it yet"[^>]*data-option="planning"/);
    const issued = controls("en", { canOrderByPlanning: true, orderBy: "planning", positionFrom: "O1", set: "plan" });
    expect(issued).toMatch(/aria-pressed="true"[^>]*data-option="planning"/);
    expect(issued).not.toMatch(/disabled=""[^>]*data-option="planning"/);
    expect(issued).toMatch(/aria-pressed="true"[^>]*data-option="O1"/);
    expect(issued).toMatch(/aria-pressed="true"[^>]*data-option="plan"/);
  });

  it("is the card of region B2: the controls behind their button, the table, and a waiting state", () => {
    const open = html(<MaeSaiCommandQueue {...queueProps("en")} />);
    expect(open).toMatch(/data-region="B2" data-clear-panel="true" data-state="ready" data-layout="desktop" aria-label="Subdistrict table"/);
    expect(open).toContain("data-command-controls");
    expect(open).toMatch(/aria-expanded="true"[^>]*aria-label="Table options"/);
    const closed = html(<MaeSaiCommandQueue {...queueProps("en", { optionsOpen: false })} />);
    expect(closed).not.toContain("data-command-controls");
    expect(closed).toMatch(/aria-expanded="false"[^>]*aria-label="Table options"/);
    expect(closed).toContain("data-command-table");
    const waiting = html(<MaeSaiCommandQueue {...queueProps("en", { rows: null })} />);
    expect(waiting).toContain('data-state="waiting"');
    expect(text(waiting)).toContain("The table appears when the replay data has loaded");
    expect(text(html(<MaeSaiCommandQueue {...queueProps("th", { rows: null, failed: true })} />))).toContain("โหลดข้อมูลการย้อนดูไม่สำเร็จ");
  });

  it("is one line with the top row in focus mode", () => {
    const markup = html(<MaeSaiCommandQueue {...queueProps("en", { collapsed: true })} />);
    expect(markup).toContain('data-state="collapsed"');
    expect(text(markup)).toContain("1 แม่สาย Mae Sai ~5,700 lost access · ~5,900 in water");
    expect(text(markup)).toContain("Model · low confidence");
    expect(markup).not.toContain("data-command-table");
  });

  it("carries the tabs of the left column on a tablet, where the right card does not exist", () => {
    const tablet = (tab: "queue" | "detail" | "known") => html(<MaeSaiCommandQueue {...queueProps("en", { layout: "tablet", tab, optionsOpen: false, detail: <p>detail panel</p>, known: <p>known panel</p> })} />);
    const queue = tablet("queue");
    expect([...queue.matchAll(/role="tab" aria-selected="(true|false)"[^>]*data-command-tab="([a-z]+)"/g)].map((match) => `${match[2]}:${match[1]}`)).toEqual(["queue:true", "detail:false", "known:false"]);
    expect(text(queue)).toContain("Subdistricts Detail Known");
    expect(queue).toContain("data-command-table");
    expect(text(tablet("detail"))).toContain("detail panel");
    expect(tablet("detail")).not.toContain("data-command-table");
    expect(text(tablet("known"))).toContain("known panel");
    // A desktop has no tabs on this card.
    expect(html(<MaeSaiCommandQueue {...queueProps("en")} />)).not.toContain('role="tablist"');
  });
});

describe("Inspector of a subdistrict (region D, Detail)", () => {
  it("shows this hour's figures of Mae Sai, with the impassable road length and the facilities in water", () => {
    const plain = text(detailOf("TH570901", "en"));
    expect(plain).toContain("Subdistrict แม่สาย Mae Sai");
    expect(plain).toContain("At this replay hour Model · low confidence 12 Sep 2024 · 12:00 ICT · hour 84 of 264");
    expect(plain).toContain("~5,700 lost shelter access of ~13,500 in reach");
    expect(plain).toContain("~5,900 residents in modelled water");
    expect(plain).toContain("~57 km roads impassable of 87 km modelled here");
    expect(plain).toMatch(/\d+ of \d+ key facilities in modelled water/);
    expect(plain).toContain("~4,400 of ~17,900 residents (25%) had no shelter of this set within 2 km before the flood, so they can never count as having lost access.");
    expect(plain).toContain("Named roads with impassable pieces: Mueang Daeng Rd");
    // Before the flood: nothing is lost, nothing is impassable.
    const dry = text(detailOf("TH570901", "en", { hour: 0 }));
    expect(dry).toContain("0 lost shelter access");
    expect(dry).toContain("0 km roads impassable");
    expect(dry).not.toContain("Named roads with impassable pieces");
  });

  it("gives the summary at the modelled peak from the export pack, or says that it is not there", () => {
    const plain = text(detailOf("TH570901", "en"));
    expect(plain).toContain("At the modelled peak 12 Sep 2024 · 12:00 ICT");
    expect(plain).toContain("Modelled water over ~9.7 km² (45% of the subdistrict)");
    expect(plain).toContain("~5,900 residents in modelled water");
    expect(plain).toContain("~57 km of roads impassable");
    expect(plain).toContain("~5,700 lost shelter access, of ~13,500 who had one in reach (42%)");
    expect(plain).toContain("From the export table tambon_replay_summary.json. Model, low confidence.");
    expect(text(detailOf("TH570901", "en", { set: "plan" }))).toContain("~8,400 lost shelter access, of ~13,800 who had one in reach (61%)");
    expect(text(detailOf("TH570901", "en", { peak: "loading" }))).toContain("Loading the peak summary");
    expect(text(detailOf("TH570901", "en", { peak: "missing" }))).toContain("The peak summary of the export pack could not be loaded.");
    expect(text(detailOf("TH570901", "th"))).toContain("น้ำตามแบบจำลองครอบคลุม ~9.7 ตร.กม. (45% ของตำบล)");
  });

  it("lists the located place records as ordinary place records, reported and not surveyed", () => {
    const markup = detailOf("TH570901", "en");
    const plain = text(markup);
    expect(plain).toContain("Place records here Reported in news · not surveyed 9 located place records (news, not surveyed)");
    expect(plain).toContain("ชุมชนเกาะทราย (บ้านเกาะทราย หมู่ 7) Ko Sai community");
    expect(plain).toContain("Model dry");
    expect(plain).toContain("9 more place records have no point and stay at district level.");
    expect(count(markup, 'target="_blank" rel="noopener noreferrer"')).toBe(9);
    // No record is tagged as a plea or a call: decision 7 was not approved.
    for (const id of model.tambons.map((tambon) => tambon.id)) expect(text(detailOf(id, "en"))).not.toMatch(/plea|call for help|SOS/i);
    for (const id of model.tambons.map((tambon) => tambon.id)) expect(text(detailOf(id, "th"))).not.toMatch(/ขอความช่วยเหลือ|SOS/);
    // A subdistrict without a record says that this is no sign of little water.
    expect(text(detailOf("TH570908", "en"))).toContain("No located place record in this subdistrict. That is not a sign of little water.");
  });

  it("shows one card per protocol case, which today reads Not issued yet (task E8)", () => {
    for (const id of model.tambons.map((tambon) => tambon.id)) {
      const markup = detailOf(id, "en");
      expect([...markup.matchAll(/data-case="(O1|SE1)" data-issued="(true|false)"/g)].map((match) => `${match[1]}:${match[2]}`)).toEqual(["O1:false", "SE1:false"]);
      expect(count(text(markup), "Not issued yet (task E8)")).toBe(2);
      expect(text(markup)).not.toContain(NEVER_SAFE.en);
    }
    const plain = text(detailOf("TH570901", "en"));
    expect(plain).toContain("Planning class · fixed in time Planning class from the signed protocol. Fixed in time. Not computed from this replay hour.");
    expect(plain).toContain("O1 · own radar candidates, 16 Sep 2024 Own model candidate: verify before action");
    expect(plain).toContain("SE1 · season envelope, Aug–Oct 2024 Scenario: what-if (2024 season envelope)");
    expect(plain).toContain("No planning class has been issued for this subdistrict in this case.");
    expect(count(text(detailOf("TH570901", "th")), "ยังไม่ออกผล (งาน E8)")).toBe(2);
  });

  it("prints the class name, the action text and Class E never means safe with every E (fixture units)", () => {
    const card = (planningCase: CommandPlanningCase, unit: string, language: Language) =>
      html(<CommandCaseCard planningCase={planningCase} cell={fixtureCells[planningCase].get(unit)!} facts={fixtureFacts} language={language} />);
    for (const language of LANGUAGES) {
      for (const [planningCase, unit] of [["O1", "FX-U14"], ["O1", "FX-U15"], ["SE1", "FX-U13"]] as const) {
        const markup = card(planningCase, unit, language);
        expect(markup).toContain('data-issued="true"');
        expect(markup).toContain("data-command-e-never-safe");
        expect(text(markup)).toContain(`${NEVER_SAFE[language]}.`);
        expect(text(markup)).toContain(ACTION_TEXT.E[language]);
      }
      const classC = card("SE1", "FX-U03", language);
      expect(text(classC)).toContain(ACTION_TEXT.C[language]);
      expect(text(classC)).not.toContain(NEVER_SAFE[language]);
    }
    const own = text(card("O1", "FX-U14", "en"));
    expect(own).toContain("O1 · own radar candidates, 16 Sep 2024 Own model candidate: verify before action");
    expect(own).toContain("Class E · Monitor and verify stability not evaluated");
    expect(own).toContain("Planning action Monitor and obtain better evidence before action.");
    // The tier, the protocol versions and the anchors stand with the class.
    expect(own).toContain("Tier T2 · lane OBS · confidence low");
    expect(own).toContain("Planning score (FPPS) 40.5 of 100");
    expect(own).toContain("Reason code low_confidence");
    expect(own).toContain(`Protocol v1a ${overlay.protocol_sha256.v1a.slice(0, 8)} · v1b ${overlay.protocol_sha256.v1b.slice(0, 8)} · class_rule_v1`);
    expect(own).toContain("Anchors: flooded share 0.20 · dependent share P10 0.351 to P90 0.478");
    // The would-be class (D) of this low-confidence row is not on the card.
    expect(own).not.toMatch(/would[- ]be|Build resilience/i);
    const scenario = text(card("SE1", "FX-U03", "en"));
    expect(scenario).toContain("Class C · Protect essential services headline-eligible: the class holds when one component at a time is left out");
    expect(scenario).toContain("Tier T1 · lane SCN-ENV · confidence medium");
  });

  it("is a card with two tabs, and a chip when it is closed", () => {
    const card = html(<MaeSaiCommandInspector language="en" tab="detail" onTab={noop} onClose={noop} detail={<p>the detail</p>} known={<CommandKnownPlaceholder language="en" />} />);
    expect(card).toMatch(/<aside class="[^"]*" data-region="D" data-clear-panel="true" aria-label="Detail and what is known"/);
    expect([...card.matchAll(/role="tab" aria-selected="(true|false)"[^>]*data-command-card-tab="([a-z]+)"/g)].map((match) => `${match[2]}:${match[1]}`)).toEqual(["detail:true", "known:false"]);
    expect(text(card)).toContain("the detail");
    expect(card).toMatch(/aria-label="Clear the selection"[^>]*data-command-card-close/);
    const empty = html(<MaeSaiCommandInspector language="en" tab="detail" onTab={noop} onClose={noop} detail={null} known={<CommandKnownPlaceholder language="en" />} />);
    expect(text(empty)).toContain("Select a subdistrict in the table to see its detail.");
    expect(empty).toMatch(/aria-label="Close the card"/);
    const known = html(<MaeSaiCommandInspector language="th" tab="known" onTab={noop} onClose={noop} detail={null} known={<CommandKnownPlaceholder language="th" />} />);
    expect(text(known)).toContain("รายการสิ่งที่มีรายงานหรือสังเกตได้จะแสดงเมื่อโหลดข้อมูลการย้อนดูเสร็จ");
    // The tab of "Known by now" carries the number of rows once the list is there.
    const counted = html(<MaeSaiCommandInspector language="en" tab="known" onTab={noop} onClose={noop} detail={null} known={<p>rows</p>} knownCount={35} />);
    expect(text(counted)).toContain("Known by now (35)");
    const chip = html(<CommandCardChip language="en" label="Detail: แม่สาย" onOpen={noop} />);
    expect(chip).toMatch(/aria-expanded="false" data-region="D" data-command-card="chip"/);
    expect(text(chip)).toBe("Detail: แม่สาย");
    expect(text(html(<CommandDetailEmpty language="th" />))).toBe("เลือกตำบลในตารางเพื่อดูรายละเอียด");
  });
});

describe("Find-place box", () => {
  const find = (language: Language, query = "") => html(<MaeSaiCommandFind language={language} index={findIndex} onPick={noop} onClose={noop} initialQuery={query} />);

  it("says what it searches, and that the data holds no list of villages or sois", () => {
    const markup = find("en");
    expect(markup).toMatch(/data-command-popover="find" data-clear-panel="true"/);
    expect(text(markup)).toContain("Find a place");
    expect(text(markup)).toContain("Searches the names in the replay data: subdistricts, reported shelters, place records, named facilities and named roads. The data holds no list of villages or sois.");
    expect(markup).toMatch(/type="search"[^>]*placeholder="Subdistrict, shelter, place, road"/);
    expect(markup).not.toContain('role="listbox"');
    expect(text(find("th"))).toContain("ข้อมูลไม่มีรายชื่อหมู่บ้านหรือซอย");
  });

  it("lists the names it finds, Thai name first, with what kind of name each is", () => {
    const markup = find("en", "mae sai");
    const kinds = [...markup.matchAll(/role="option" aria-selected="(true|false)"(?: aria-disabled="true")? data-kind="([a-z_]+)"/g)].map((match) => `${match[2]}:${match[1]}`);
    expect(kinds.length).toBeGreaterThan(1);
    expect(kinds.length).toBeLessThanOrEqual(6);
    expect(kinds[0]).toBe("tambon:true");
    expect(text(markup)).toContain("แม่สาย Mae Sai Subdistrict");
    expect(text(markup)).toMatch(/\d names/);
    expect(text(find("en", "ko sai"))).toContain("Place record (news, not surveyed)");
    expect(text(find("th", "วัด"))).toContain("ที่พักพิงตามรายงานปี 2567 (2024)");
    // A name without a point in the data is listed, and cannot be shown on the map.
    const unlocated = find("en", "Pa Sang Ngam");
    expect(unlocated).toMatch(/aria-disabled="true" data-kind="shelter"/);
    expect(text(unlocated)).toContain("Shelter reported in 2024 · no point in the data");
    expect(text(find("en", "Bangkok"))).toContain("No name in the replay data matches.");
  });
});

describe("Command page with the table and the inspector", () => {
  it("keeps the legend and the right card apart: one panel over the map at a time", () => {
    const markup = html(<MaeSaiCommandExercise initial={{ hour: 84 }} />);
    // At rest the right card is its chip and the legend is its chip; neither is open.
    expect(markup).toContain('data-command-card="chip"');
    expect(markup).toContain('data-command-legend="chip"');
    expect(markup).not.toContain('data-command-legend="open"');
    expect(markup).not.toMatch(/<aside[^>]*data-region="D"/);
    expect(markup).not.toContain("data-selected=");
  });

  it("passes the shared wording lint in both languages, at several replay hours and with both shelter sets", () => {
    for (const language of LANGUAGES) {
      const panels: [string, string][] = [
        ...[0, 44, 84, 130, 264].map((hour): [string, string] => [`table ${hour}`, table(language, { hour })]),
        ["table, plan set", table(language, { set: "plan" })],
        ["table, order held", table(language, { pending: true })],
        ["table, fixture units", fixtureTable(language)],
        ["card", html(<MaeSaiCommandQueue {...queueProps(language)} />)],
        ["card, waiting", html(<MaeSaiCommandQueue {...queueProps(language, { rows: null })} />)],
        ["card, focus mode", html(<MaeSaiCommandQueue {...queueProps(language, { collapsed: true })} />)],
        ["card, tablet", html(<MaeSaiCommandQueue {...queueProps(language, { layout: "tablet", optionsOpen: true })} />)],
        ...model.tambons.map((tambon): [string, string] => [`detail ${tambon.en}`, detailOf(tambon.id, language)]),
        ["detail, plan set", detailOf("TH570901", language, { set: "plan" })],
        ["detail, peak missing", detailOf("TH570904", language, { peak: "missing", hour: 130 })],
        ...(["O1", "SE1"] as const).flatMap((planningCase) => [...fixtureCells[planningCase].values()].map((cell): [string, string] => [
          `case card ${cell.rowId}`, html(<CommandCaseCard planningCase={planningCase} cell={cell} facts={fixtureFacts} language={language} />),
        ])),
        ["inspector", html(<MaeSaiCommandInspector language={language} tab="known" onTab={noop} onClose={noop} detail={null} known={<CommandKnownPlaceholder language={language} />} />)],
        ["find", html(<MaeSaiCommandFind language={language} index={findIndex} onPick={noop} onClose={noop} />)],
        ...["mae", "วัด", "road", "school", "zzz"].map((query): [string, string] => [`find ${query}`, html(<MaeSaiCommandFind language={language} index={findIndex} onPick={noop} onClose={noop} initialQuery={query} />)]),
      ];
      for (const [name, markup] of panels) expect(lintOf(markup, `${name} ${language}`), `${name} ${language}`).toBe("");
    }
  });
});
