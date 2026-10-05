/**
 * The act flow of the Command exercise replay, as it renders: the fixed action bar of an invented item with its trays,
 * the inspector in incident mode (how to get near, and where people go: facts only), the brief sheet, the facilitator's
 * setup sheet, the exercise log, the notice with its undo, the exercise menu and the help steps.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type AreaGeometry, type FacilityProps, type GeoCollection, type Language, type LineGeometry, type RoadProps, type TambonProps, type TimelineManifest } from "@/lib/flood-timeline";
import { buildCommandModel, changeSinceHourBefore, districtFiguresAt, tambonOrderByHour, tambonRowsAt } from "@/lib/flood-timeline-command";
import { commandActionNotice } from "@/lib/flood-timeline-command-act-copy";
import { BRIEF_TAG, itemBriefLines, itemBriefSms, itemFacts, resolveStaging, situationBriefLines, smsHref } from "@/lib/flood-timeline-command-brief";
import type { CommandMode } from "@/lib/flood-timeline-command-feed";
import { EXERCISE_FILE_URL, parseExerciseFile, type ExerciseHandling, type ExerciseItem } from "@/lib/flood-timeline-command-incidents";
import { applyItemAction, COMMAND_LOG_ACTIONS, DEFAULT_COMMAND_SETUP, EMPTY_EXERCISE_STATE, type CommandLogEntry, type CommandSetup } from "@/lib/flood-timeline-command-log";
import { tambonDetailAt } from "@/lib/flood-timeline-command-table";
import { parseAccessNodes, REPORTED_SET_ID } from "@/lib/flood-timeline-evacuation";
import { visibleText } from "@/lib/replay-wording-lint";

import { CommandBriefSheet, type CommandBriefContent } from "./mae-sai-command-brief";
import { CommandHelpSheet, CommandNav, CommandNotice } from "./mae-sai-command-chrome";
import { MaeSaiCommandExercise } from "./mae-sai-command-exercise";
import { CommandDeviceDetailBody, CommandItemActionBar, CommandItemDetailBody } from "./mae-sai-command-incident";
import { MaeSaiCommandInspector } from "./mae-sai-command-inspector";
import { MaeSaiCommandQueue } from "./mae-sai-command-queue";
import { COMMAND_LOG_ROWS_SHOWN, CommandLogSheet, CommandSetupSheet } from "./mae-sai-command-setup";
import { MaeSaiCommandSituation } from "./mae-sai-command-situation";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<LineGeometry, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const facilities = (JSON.parse(read(manifest.vectors.facilities.href).toString("utf8")) as GeoCollection<unknown, FacilityProps>).features.map((feature) => feature.properties);
const nodes = parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!);
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes });
const exercise = parseExerciseFile(JSON.parse(read(EXERCISE_FILE_URL).toString("utf8")));
const sites = manifest.shelters!.reported;
const item = (id: string): ExerciseItem => exercise.items.find((entry) => entry.id === id)!;
const tambonOf = (entry: ExerciseItem) => model.tambons.find((tambon) => tambon.id === entry.tambonId) ?? null;

const LANGUAGES: readonly Language[] = ["en", "th"];
const noop = () => undefined;
const html = (node: ReactElement) => renderToStaticMarkup(node);
const text = (markup: string) => visibleText(markup).replace(/\s+/g, " ").trim();
const NEW: ExerciseHandling = { status: "new", callsign: null };
const factsOf = (entry: ExerciseItem, hour: number, mode: CommandMode, depth: number | null | undefined) => itemFacts({
  point: entry.point, hour, mode, stage: model.stages[hour], depth, impassableDepthM: manifest.impassable_depth_m, roads: roads.features, sites, nodes,
  setIndex: manifest.access!.sets.indexOf(REPORTED_SET_ID), levels: model.levels, staging: resolveStaging({ type: "site", id: "R05" }, sites),
});
const incident = (entry: ExerciseItem, hour: number, mode: CommandMode, depth: number | null | undefined, language: Language = "en", handling: ExerciseHandling = NEW, authorUrgency = entry.urgency) => html(
  <CommandItemDetailBody language={language} hour={hour} item={entry} handling={handling} tambon={tambonOf(entry)} depth={depth} rule={exercise.rule} authorUrgency={authorUrgency}
    facts={factsOf(entry, hour, mode, depth)} roadsImpassable={tambonDetailAt(model, facilities, hour, "reported", entry.tambonId)?.roadsImpassable ?? []} countedSites={12} onUrgency={noop} />,
);
const bar = (handling: ExerciseHandling, tray: "assign" | "more" | null, language: Language = "en", roster = DEFAULT_COMMAND_SETUP.roster) => html(
  <CommandItemActionBar language={language} item={item("EX-05")} handling={handling} roster={roster} tray={tray} onTray={noop} onAction={noop} onBrief={noop} onSetup={noop} />,
);
const briefOf = (entry: ExerciseItem, callsign: string | null = "BOAT-2"): CommandBriefContent => {
  const input = { item: entry, tambon: tambonOf(entry), callsign, hour: 84, facts: factsOf(entry, 84, "trainee", 1.4) };
  return { itemId: entry.id, lines: { th: itemBriefLines(input, "th"), en: itemBriefLines(input, "en") }, sms: { th: itemBriefSms(input, "th"), en: itemBriefSms(input, "en") } };
};
const stagingSites = [{ id: "R05", name: { th: "ที่ว่าการอำเภอแม่สาย", en: "Mae Sai District Office" } }, { id: "R01", name: { th: "ศูนย์พักพิงเทศบาลตำบลแม่สาย", en: "Mae Sai Subdistrict Municipality Office shelter and relief centre" } }];
const setupSheet = (language: Language, more: Partial<CommandSetup> = {}) => html(
  <CommandSetupSheet open={false} onClose={noop} language={language} setup={{ ...DEFAULT_COMMAND_SETUP, ...more }} hour={84} stagingSites={stagingSites} itemCount={14}
    onRoster={noop} onStaging={noop} onPickStaging={noop} onStartHour={noop} onStart={noop} onMode={noop} onItems={noop} onPause={noop} onSpeed={noop} onReset={noop} />,
);
const logRows = (count: number): CommandLogEntry[] => Array.from({ length: count }, (_, index) => ({
  seq: index + 1, replayHour: 46 + (index % 100), deviceTime: new Date(Date.parse("2026-10-05T03:00:00.000Z") + index * 1000).toISOString(), role: "coordinator" as const,
  callsign: "BOAT-2", action: COMMAND_LOG_ACTIONS[index % 5], itemId: "EX-05", detail: null,
}));
const logSheet = (log: CommandLogEntry[], language: Language = "en") => html(<CommandLogSheet open={false} onClose={noop} language={language} log={log} onExport={noop} onReset={noop} timeZone="Asia/Bangkok" />);

describe("The action bar of an invented item", () => {
  it("is Assign, Brief and Done, in that order, with one more button for what is used less often", () => {
    const markup = bar(NEW, null);
    expect([...markup.matchAll(/data-command-act="([a-z-]+)"/g)].map((match) => match[1])).toEqual(["assign", "brief", "done", "more"]);
    expect(text(markup).startsWith("Assign Brief Done")).toBe(true);
    expect(markup).toMatch(/role="group" aria-label="Actions on this exercise item" data-command-actions="EX-05" data-status="new"/);
    expect(markup).toMatch(/aria-label="More actions"/);
    // Nothing asks "are you sure": the bar holds no dialog.
    expect(markup).not.toMatch(/<dialog|confirm/i);
    expect(text(bar(NEW, null, "th")).startsWith("มอบหมาย ข้อความสรุป เสร็จสิ้น")).toBe(true);
  });

  it("opens the roster typed on this device, each callsign with the kind of its team, and gives no advice", () => {
    const markup = bar(NEW, "assign");
    expect([...markup.matchAll(/data-command-callsign="([^"]+)" data-team-type="([a-z]+)"/g)].map((match) => `${match[1]}:${match[2]}`))
      .toEqual(["BOAT-1:boat", "BOAT-2:boat", "WADE-1:wading", "TRUCK-1:vehicle", "MED-1:medical"]);
    expect(markup).toMatch(/aria-label="Assign to BOAT-2 \(Boat\)"/);
    expect(markup).toMatch(/data-command-act="assign">Assign<\/button>/);
    expect(markup).toMatch(/aria-expanded="true" data-command-act="assign"/);
    const shown = text(markup);
    expect(shown).toContain("Assign to a callsign");
    expect(shown).toContain("The page gives no advice on the kind of team to send.");
    expect(shown).toContain("Edit the roster");
    // The callsign an item is assigned to is marked in the roster.
    expect(bar({ status: "assigned", callsign: "MED-1" }, "assign")).toMatch(/aria-pressed="true" aria-label="Assign to MED-1 \(Medical\)"/);
    expect(text(bar(NEW, "assign", "en", []))).toContain("The roster is empty. Add callsigns in the exercise setup.");
  });

  it("holds acknowledge and the two ways to drop an item behind the fourth button", () => {
    const markup = bar(NEW, "more");
    expect([...markup.matchAll(/data-command-act="([a-z-]+)"/g)].map((match) => match[1])).toEqual(["acknowledge", "drop-duplicate", "drop-unreachable", "assign", "brief", "done", "more"]);
    expect(markup).toMatch(/aria-label="Drop as: duplicate"/);
    expect(markup).toMatch(/aria-label="Drop as: could not reach"/);
    // An item that is no longer new cannot be acknowledged again.
    expect(markup).not.toMatch(/disabled="" data-command-act="acknowledge"/);
    expect(bar({ status: "assigned", callsign: "BOAT-2" }, "more")).toMatch(/disabled="" data-command-act="acknowledge"/);
  });

  it("offers Reopen in the place of Done on a closed item, and no assignment", () => {
    for (const status of ["done", "dropped"] as const) {
      const markup = bar({ status, callsign: "BOAT-2" }, "more");
      expect([...markup.matchAll(/data-command-act="([a-z-]+)"/g)].map((match) => match[1])).toEqual(["assign", "brief", "reopen", "more"]);
      expect(markup).toMatch(/disabled="" aria-expanded="false" data-command-act="assign"/);
      expect(text(markup)).toContain("The item is closed. Reopen it to assign it again.");
    }
    // A closed item never shows the roster, even when the tray was open.
    expect(bar({ status: "done", callsign: "BOAT-2" }, "assign")).not.toContain("data-command-tray");
  });

  it("stays fixed under the detail of the right card, and under the detail tab of a tablet", () => {
    const footer = <CommandItemActionBar language="en" item={item("EX-05")} handling={NEW} roster={DEFAULT_COMMAND_SETUP.roster} tray={null} onTray={noop} onAction={noop} onBrief={noop} onSetup={noop} />;
    const card = html(<MaeSaiCommandInspector language="en" tab="detail" onTab={noop} onClose={noop} detail={<p>detail</p>} footer={footer} known={null} />);
    // The bar comes after the scrolling body, as a sibling of it.
    expect(card).toMatch(/<p>detail<\/p><\/div><div class="[^"]*" role="group" aria-label="Actions on this exercise item"/);
    expect(html(<MaeSaiCommandInspector language="en" tab="known" onTab={noop} onClose={noop} detail={<p>detail</p>} footer={footer} known={<p>known</p>} />)).not.toContain("data-command-actions");
    expect(html(<MaeSaiCommandInspector language="en" tab="detail" onTab={noop} onClose={noop} detail={null} footer={footer} known={null} />)).not.toContain("data-command-actions");
    const tablet = (tab: "queue" | "detail") => html(
      <MaeSaiCommandQueue language="en" rows={null} selected={null} onSelect={noop} set="reported" onSet={noop} setSites={{ reported: 12, plan: 8 }} orderBy="hour" onOrderBy={noop} canOrderByPlanning={false}
        positionFrom="SE1" onPositionFrom={noop} pending={false} optionsOpen={false} onOptions={noop} layout="tablet" tab={tab} detail={<p>detail</p>} detailFooter={footer} known={null} />,
    );
    expect(tablet("detail")).toMatch(/<p>detail<\/p><\/div><div class="[^"]*" role="group" aria-label="Actions on this exercise item"/);
    expect(tablet("queue")).not.toContain("data-command-actions");
  });
});

describe("The inspector in incident mode", () => {
  it("states how to get near as facts: the depth with no current, the 0.3 m level, the nearest road, the named roads and the straight line", () => {
    const markup = incident(item("EX-09"), 84, "hindsight", 1.42);
    const shown = text(markup);
    expect(shown).toContain("How to get near facts only Model · low confidence");
    expect(shown).toContain("Model here: ~1.4 m of water at this replay hour · current not modelled");
    expect(shown).toContain("At or over the 0.3 m level at which roads count as impassable.");
    expect(shown).toMatch(/Nearest road piece under 0\.3 m in the model: .+, (~[\d.]+|<10) (m|km) away \((dry|wet, under 0\.3 m)\)/);
    expect(shown).toContain("Not checked for a connected way out; bridge decks not modelled.");
    expect(shown).toMatch(/Named roads impassable in Wiang Phang Kham subdistrict this hour: /);
    expect(shown).toMatch(/From the staging point \(Mae Sai District Office\): ~[\d.]+ km · north(-west)? straight line, not a route/);
    expect(shown).toContain("The page gives no advice on the kind of team to send: the model has depth and no current.");
    expect(markup).toMatch(/data-command-depth-fact="at_or_over"/);
    // Under 0.3 m, dry, outside the grid and not loaded each read as what they are.
    expect(text(incident(item("EX-09"), 84, "hindsight", 0.2))).toContain("Under the 0.3 m level at which roads count as impassable.");
    expect(incident(item("EX-09"), 84, "hindsight", 0)).not.toContain("data-command-depth-fact");
    expect(text(incident(item("EX-09"), 84, "hindsight", null))).toContain("Model here: outside the modelled area");
    expect(text(incident(item("EX-09"), 84, "hindsight", undefined))).toContain("Model here: the water layer has not loaded");
  });

  it("gives no advice on the kind of team anywhere on the card", () => {
    for (const language of LANGUAGES) {
      for (const entry of exercise.items) {
        // What the invented message itself says is not the page's advice: it is left out of the check.
        const shown = text(incident(entry, Math.max(entry.hour, 84), "hindsight", 0.8, language)).replace(entry.text[language], "");
        expect(shown, `${entry.id} ${language}`).not.toMatch(/\bboat|wading|by vehicle|send a |should send|เรือ|เดินลุย|ควรส่ง(?!ชุดปฏิบัติการประเภทใด)/i);
      }
    }
  });

  it("lists the three nearest counted shelters with distance, bearing, their state in the model and what was reported", () => {
    const markup = incident(item("EX-05"), 84, "hindsight", 0.6);
    const shown = text(markup);
    expect(shown).toContain("Shelters near this point 3 nearest of the 12 counted sites · straight line");
    expect([...markup.matchAll(/data-command-site="(R\d\d)"/g)]).toHaveLength(3);
    expect(shown).toMatch(/~[\d.]+ km · (north|south|east|west)(-(east|west))? dry in the model at this stage/);
    expect(shown).toContain("reported in use by 15 Sep 2024; opening time not known");
    expect(shown).toContain("Occupancy as reported: 34 (2024-09-11 01:00), 53 (about 2024-09-15)");
    expect(shown).toContain("Straight-line distances. Nothing here says that a site could be reached, was in use at this hour or had room.");
    expect(markup).toMatch(/data-command-node-line="true" data-access="(kept|lost|none_before|none)"/);
    expect(shown).toMatch(/Access model(, resident node (~[\d.]+|<10) m away)?: /);
  });

  it("shows no later date in trainee mode, and marks a site that is not yet reported", () => {
    const at60 = incident(item("EX-05"), 60, "trainee", 0.6);
    expect(text(at60)).toContain("first reported in use on 11 Sep 2024; opening time not known");
    expect(text(at60)).toContain("Occupancy counts carry later dates, so they are shown in hindsight mode.");
    expect(text(at60)).not.toMatch(/2024-09-1[5-9]|15 Sep 2024|2025/);
    expect(at60).toMatch(/data-command-occupancy="held"/);
    const at40 = incident(item("EX-02"), 40, "trainee", 0);
    expect([...at40.matchAll(/data-pending="true"/g)]).toHaveLength(3);
    expect(text(at40)).toContain("Not yet reported at this replay hour");
    expect(text(at40)).not.toMatch(/reported in use|Occupancy/);
    expect(text(incident(item("EX-05"), 60, "trainee", 0.6, "th"))).toContain("มีรายงานการใช้ครั้งแรกเมื่อวันที่ 11 ก.ย. 2567 (2024) · ไม่ทราบเวลาที่เริ่มเปิดใช้");
  });

  it("moves the urgency one step with one tap, and says when the operator changed it", () => {
    const urgent = incident(item("EX-07"), 60, "trainee", 1);
    expect([...urgent.matchAll(/data-command-urgency-step="(raise|lower)"/g)].map((match) => match[1])).toEqual(["raise", "lower"]);
    expect(urgent).not.toMatch(/disabled="" aria-label="(Raise|Lower)/);
    expect(urgent).not.toContain("data-command-urgency-changed");
    // At the top level there is no step up; at the bottom level no step down.
    expect(incident(item("EX-05"), 60, "trainee", 1)).toMatch(/disabled="" aria-label="Raise the urgency one step"/);
    expect(incident(item("EX-01"), 60, "trainee", 1)).toMatch(/disabled="" aria-label="Lower the urgency one step"/);
    const raised = incident({ ...item("EX-07"), urgency: "life_at_risk" }, 60, "trainee", 1, "en", { status: "acknowledged", callsign: null }, "urgent");
    expect(text(raised)).toContain("Life at risk · acknowledged");
    expect(text(raised)).toContain("Changed on this device: Urgent → Life at risk");
    // A closed item keeps its callsign and has no steps.
    const closed = incident(item("EX-07"), 60, "trainee", 1, "en", { status: "done", callsign: "BOAT-2" });
    expect(closed).not.toContain("data-command-urgency-step");
    expect(closed).toMatch(/<b data-command-item-callsign="true">BOAT-2<\/b>/);
    expect(text(closed)).toContain("Urgent · done BOAT-2");
  });

  it("assigns no team to a report saved on this device, and builds no brief from it", () => {
    const markup = html(<CommandDeviceDetailBody language="en" tambon={{ id: "TH570904", th: "โป่งผา", en: "Pong Pha" }} reports={[]} />);
    expect(text(markup)).toContain("No team is assigned to a report saved on this device, and no brief is built from it: it is dated today, outside the 2024 replay, and it names a subdistrict and no point.");
    expect(markup).not.toContain("data-command-actions");
  });
});

describe("The brief sheet", () => {
  it("opens in Thai, whatever the language of the page, with the exercise tag as its first and its last line", () => {
    for (const language of LANGUAGES) {
      const markup = html(<CommandBriefSheet open={false} onClose={noop} language={language} content={briefOf(item("EX-05"))} />);
      expect(markup).toMatch(/data-command-brief="EX-05" data-brief-language="th"/);
      const brief = /<pre class="[^"]*" lang="th" tabindex="0" aria-label="[^"]*" data-command-brief-text="true">(.*?)<\/pre>/s.exec(markup)![1];
      const lines = visibleText(brief).split("\n").map((line) => line.replace(/\s+/g, " ").trim());
      expect(lines).toHaveLength(9);
      expect(lines[0]).toBe("[ฝึกซ้อม – ไม่ใช่เหตุจริง] EX-05 · ชุด BOAT-2");
      expect(lines[8]).toBe("[ฝึกซ้อม – ไม่ใช่เหตุจริง]");
      // The tag is set apart as a tag at both ends.
      expect([...brief.matchAll(/<span class="[^"]*">\[ฝึกซ้อม – ไม่ใช่เหตุจริง\]<\/span>/g)]).toHaveLength(2);
      expect(markup).toMatch(/aria-pressed="true" data-command-brief-language="th"/);
      expect(markup).toMatch(/aria-pressed="false" data-command-brief-language="en"/);
    }
    expect(text(html(<CommandBriefSheet open={false} onClose={noop} language="en" content={briefOf(item("EX-05"))} />))).toContain("Brief · EX-05");
  });

  it("offers Copy, and the text-message version with its count and a link that names no recipient", () => {
    const content = briefOf(item("EX-05"));
    const markup = html(<CommandBriefSheet open={false} onClose={noop} language="en" content={content} />);
    expect(markup).toContain("data-command-brief-copy");
    // Share is offered only where the browser has a share sheet: a page rendered without a browser has none.
    expect(markup).not.toContain("data-command-brief-share");
    const href = /<a class="[^"]*" href="([^"]*)" data-command-sms="true">/.exec(markup)![1].replaceAll("&amp;", "&");
    expect(href).toBe(smsHref(content.sms!.th));
    expect(href.startsWith("sms:?&body=")).toBe(true);
    expect(href).not.toMatch(/^sms:[^?]/);
    const shown = text(markup);
    expect(shown).toContain(`${content.sms!.th.length} of 134 characters · 2 parts`);
    expect(shown).toContain("No recipient is filled in: you type the number.");
    expect(shown).toContain("A brief holds no rain value, no note of a report and no statement of a place record.");
    expect(shown).toContain("FloodGuard sends nothing. A brief leaves this device only through the app you pick.");
  });

  it("shows the situation brief without a text-message version", () => {
    const rows = tambonRowsAt(model, 84);
    const lines = (language: Language) => situationBriefLines({ hour: 84, figures: districtFiguresAt(model, 84), rows: tambonOrderByHour(model)[84].flatMap((id) => rows.filter((row) => row.id === id)), change: changeSinceHourBefore(model, 84) }, language);
    const markup = html(<CommandBriefSheet open={false} onClose={noop} language="en" content={{ itemId: null, lines: { th: lines("th"), en: lines("en") }, sms: null }} />);
    expect(markup).toMatch(/data-command-brief="situation"/);
    expect(markup).not.toContain("data-command-sms");
    expect(text(markup)).toContain("Situation brief");
    expect(text(markup)).toContain(`${BRIEF_TAG.th} สรุปสถานการณ์`);
    // With nothing to show the sheet has no body.
    expect(html(<CommandBriefSheet open={false} onClose={noop} language="en" content={null} />)).not.toContain("data-command-brief=");
  });

  it("is one tap away on the clock card", () => {
    const card = html(<MaeSaiCommandSituation language="en" hour={84} manifest={manifest} model={model} onBrief={noop} />);
    expect(card).toMatch(/aria-haspopup="dialog" aria-label="Open the situation brief" title="Open the situation brief" data-command-situation-brief="true"/);
    expect(html(<MaeSaiCommandSituation language="en" hour={84} manifest={manifest} model={model} />)).not.toContain("data-command-situation-brief");
    // Focus mode keeps the card to its two lines.
    expect(html(<MaeSaiCommandSituation language="en" hour={84} manifest={manifest} model={model} onBrief={noop} collapsed />)).not.toContain("data-command-situation-brief");
  });
});

describe("The facilitator's setup sheet", () => {
  it("holds the roster with the kind of each team, and states the callsign rule", () => {
    const markup = setupSheet("en");
    expect([...markup.matchAll(/data-command-team="([^"]+)"/g)].map((match) => match[1])).toEqual(["BOAT-1", "BOAT-2", "WADE-1", "TRUCK-1", "MED-1"]);
    const shown = text(markup);
    expect(shown).toContain("Callsigns only: no names and no phone numbers. At most 12 characters; an entry with seven or more digits is refused.");
    expect(shown).toContain("A device starts with five example callsigns. They name no real unit.");
    expect(markup).toMatch(/<option value="boat" selected="">Boat<\/option><option value="wading">Wading<\/option><option value="vehicle">Vehicle<\/option><option value="medical">Medical<\/option>/);
    expect(markup).toMatch(/aria-label="Remove BOAT-1"/);
    // The add button waits for a callsign.
    expect(markup).toMatch(/disabled="" data-command-roster-add="true"/);
  });

  it("offers the district office, the municipality office or a tap on the map as the staging point", () => {
    const markup = setupSheet("en");
    expect([...markup.matchAll(/data-command-staging="([A-Za-z0-9]+)"/g)].map((match) => match[1])).toEqual(["R05", "R01", "point"]);
    expect(markup).toMatch(/data-command-staging="R05" name="[^"]*" checked=""/);
    expect(markup).not.toMatch(/data-command-staging="(R01|point)" name="[^"]*" checked=""/);
    expect(text(markup)).toContain("ที่ว่าการอำเภอแม่สาย Mae Sai District Office · reported in use in 2024");
    expect(text(markup)).toContain("A point on the map not set yet Pick on the map");
    expect(text(markup)).toContain("a straight line, not a route");
    const picked = setupSheet("en", { staging: { type: "point", lat: 20.4401, lon: 99.8912 } });
    expect(picked).toMatch(/data-command-staging="point" name="[^"]*" checked=""/);
    expect(text(picked)).toContain("20.4401, 99.8912");
  });

  it("sets the start hour, the mode, the invented items, the pause and the speed", () => {
    const markup = setupSheet("en");
    const shown = text(markup);
    expect(markup).toMatch(/data-command-start-hour="36"/);
    expect(shown).toContain("10 Sep 2024 · 12:00 ICT hour 36 of 264");
    expect(markup).toMatch(/type="range" class="[^"]*" min="0" max="264" step="1"/);
    expect(shown).toContain("Start the exercise from this hour");
    expect(markup).toMatch(/aria-pressed="true" data-command-setup-mode="trainee"/);
    expect(markup).toMatch(/type="checkbox" data-command-setup-items="true" checked=""/);
    expect(markup).toMatch(/type="checkbox" data-command-setup-pause="true" checked=""/);
    expect(shown).toContain("Exercise items (14)");
    expect(markup).toMatch(/aria-pressed="true" title="1 replay hour per second" data-command-setup-speed="hour_per_second"/);
    const changed = setupSheet("en", { mode: "hindsight", itemsOn: false, speed: "drill", startHour: 84 });
    expect(changed).toMatch(/aria-pressed="true" data-command-setup-mode="hindsight"/);
    expect(changed).toMatch(/aria-pressed="true" title="Drill speed: 1 replay hour per minute" data-command-setup-speed="drill"/);
    // The pause has nothing to pause for while the items are off.
    expect(changed).toMatch(/type="checkbox" disabled="" data-command-setup-pause="true"/);
    // "Use the hour on screen" has nothing to do when the start hour is that hour.
    expect(changed).toMatch(/disabled="" data-command-start-now="true"/);
  });

  it("says that it is saved on this device only, and what a reset clears", () => {
    for (const language of LANGUAGES) {
      const markup = setupSheet(language);
      expect(markup).toContain("data-command-device-chip");
      expect(markup).toContain("data-command-reset");
    }
    expect(text(setupSheet("en"))).toContain("Saved on this device only");
    expect(text(setupSheet("en"))).toContain("Clears the roster, the setup, how each item was handled and the log from this device. The replay data stays as it is.");
    expect(text(setupSheet("th"))).toContain("บันทึกไว้ในอุปกรณ์เครื่องนี้เท่านั้น");
  });
});

describe("The exercise log", () => {
  it("lists replay time, device time, role, callsign and action, newest first", () => {
    const state = applyItemAction(EMPTY_EXERCISE_STATE, { id: "EX-05", urgency: "life_at_risk" }, { type: "assign", callsign: "BOAT-2" },
      { replayHour: 60, nowMs: Date.parse("2026-10-05T03:00:00.000Z"), roster: DEFAULT_COMMAND_SETUP.roster });
    if ("refused" in state) throw new Error("refused");
    const done = applyItemAction(state.state, { id: "EX-05", urgency: "life_at_risk" }, { type: "drop", reason: "unreachable" }, { replayHour: 62, nowMs: Date.parse("2026-10-05T03:02:05.000Z"), roster: DEFAULT_COMMAND_SETUP.roster });
    if ("refused" in done) throw new Error("refused");
    const markup = logSheet([...done.state.log]);
    expect([...markup.matchAll(/<th scope="col">([^<]+)<\/th>/g)].map((match) => match[1])).toEqual(["Replay time", "Device time", "Role", "Callsign", "Action"]);
    expect([...markup.matchAll(/data-command-log-row="(\d+)"/g)].map((match) => match[1])).toEqual(["2", "1"]);
    const shown = text(markup);
    expect(shown).toContain("11 Sep 14:00 ICT 5 Oct, 10:02:05 Coordinator BOAT-2 EX-05 dropped: could not reach");
    expect(shown).toContain("11 Sep 12:00 ICT 5 Oct, 10:00:00 Coordinator BOAT-2 EX-05 assigned");
    expect(shown).toContain("Saved on this device only");
    expect(shown).toContain("Every row is an exercise action: none is a real dispatch.");
    expect(shown).toContain('The file has a column "simulated" that is true on every row. It holds no rain value and no note of a report.');
    expect(markup).not.toMatch(/disabled="" data-command-log-export/);
  });

  it("shows a short history of a long log, and says that the export holds every row", () => {
    const markup = logSheet(logRows(132));
    expect([...markup.matchAll(/data-command-log-row="\d+"/g)]).toHaveLength(COMMAND_LOG_ROWS_SHOWN);
    expect(markup).toMatch(/data-command-log-row="132"[^>]*>.*data-command-log-row="83"/s);
    expect(text(markup)).toContain("Showing the newest 50 of 132 rows; the export holds them all.");
  });

  it("has nothing to export before anything was done", () => {
    const markup = logSheet([]);
    expect(text(markup)).toContain("Nothing has been done in this exercise yet.");
    expect(markup).toMatch(/disabled="" data-command-log-export="true"/);
    expect(markup).toContain("data-command-reset");
  });
});

describe("The notice with its undo, the exercise menu and the help steps", () => {
  it("names what an action did beside a button that undoes it", () => {
    const result = applyItemAction(EMPTY_EXERCISE_STATE, { id: "EX-05", urgency: "life_at_risk" }, { type: "assign", callsign: "BOAT-2" }, { replayHour: 60, nowMs: 0, roster: DEFAULT_COMMAND_SETUP.roster });
    if ("refused" in result) throw new Error("refused");
    expect(commandActionNotice(result.undo, "life_at_risk", "en")).toBe("EX-05 assigned to BOAT-2");
    expect(commandActionNotice(result.undo, "life_at_risk", "th")).toBe("มอบหมาย EX-05 ให้ BOAT-2 แล้ว");
    const markup = html(<CommandNotice language="en" message="EX-05 assigned to BOAT-2" action={{ id: "a", label: "Undo", onPress: noop, timed: true }} />);
    expect(markup).toMatch(/<p class="[^"]*" data-command-notice="with-action">EX-05 assigned to BOAT-2<button type="button" class="[^"]*" data-command-notice-action="true">Undo<i aria-hidden="true"><\/i><\/button><\/p>/);
    // "Cancel" while the page waits for a tap on the map has no line that runs out.
    expect(html(<CommandNotice language="en" message="Tap the map where the team starts" action={{ id: "pick", label: "Cancel", onPress: noop }} />)).not.toContain("<i ");
  });

  it("opens the setup, the log and the situation brief from the exercise menu, on a desktop and on a tablet", () => {
    const nav = (open: boolean, menuOpen = false) => html(
      <CommandNav language="en" hour={84} menuOpen={menuOpen} onMenu={noop} onLanguage={noop} onHelp={noop} basemap="street" onBasemap={noop} exercise={{ open, onToggle: noop, onSetup: noop, onLog: noop, onSituation: noop }} />,
    );
    expect(nav(false)).toMatch(/aria-expanded="false" title="Exercise: setup, log and situation brief" data-command-exercise-menu="true"/);
    expect(nav(false)).not.toContain("data-command-exercise-panel");
    const open = nav(true);
    expect(open).toContain("data-command-exercise-panel");
    expect([...open.matchAll(/data-command-exercise-item="([a-z]+)"/g)].map((match) => match[1])).toEqual(["setup", "log", "situation"]);
    // A tablet has the same three entries in its menu.
    const tablet = nav(false, true);
    expect([...tablet.matchAll(/data-command-exercise-item="([a-z]+)"/g)].map((match) => match[1])).toEqual(["setup", "log", "situation"]);
    expect(text(tablet)).toContain("Exercise setup Exercise log Situation brief");
    // Without the exercise the navigation is as before.
    expect(html(<CommandNav language="en" hour={84} menuOpen onMenu={noop} onLanguage={noop} onHelp={noop} basemap="street" onBasemap={noop} />)).not.toContain("data-command-exercise");
  });

  it("explains the path from seeing to acting in the help sheet", () => {
    const markup = html(<CommandHelpSheet open={false} onClose={noop} onAbout={noop} language="en" />);
    expect([...markup.matchAll(/<li>/g)]).toHaveLength(5);
    const shown = text(markup);
    expect(shown).toContain("From seeing to acting");
    expect(shown).toContain("facts only, no advice");
    expect(shown).toContain("Every action can be undone for 10 seconds and has a row in the exercise log. The log stays on this device.");
    expect(text(html(<CommandHelpSheet open={false} onClose={noop} onAbout={noop} language="th" />))).toContain("ทุกการดำเนินการเลิกทำได้ภายใน 10 วินาที");
  });

  it("carries the exercise menu and the sheets of the exercise on the page from its first render", () => {
    const markup = html(<MaeSaiCommandExercise />);
    expect(markup).toContain("data-command-exercise-menu");
    for (const dialog of ["info", "help", "setup", "log", "brief"]) expect(markup, dialog).toContain(`data-command-dialog="${dialog}"`);
    // Before the replay data has loaded the page holds no brief and no action bar.
    expect(markup).not.toContain("data-command-brief=");
    expect(markup).not.toContain("data-command-actions");
  });
});
