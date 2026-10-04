/**
 * The reports on the map and "Known by now" of the Command exercise replay, as they render: the drawing of every
 * marker state, the legend that explains them, the count of open exercise items and the place-record chip on the
 * situation card, the marks and the mode switch of the time dock, the list with its fixed first lines, the inspector
 * of an invented item and of the reports saved on this device, the exercise options, the notice of a new item and the
 * pause of playback. Every rendered panel passes the shared wording lint in both languages.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TIMELINE_MANIFEST_URL, type AreaGeometry, type GeoCollection, type Language, type RoadProps, type TambonProps, type TimelineManifest } from "@/lib/flood-timeline";
import { buildCommandModel } from "@/lib/flood-timeline-command";
import { buildCommandFeed, feedAt, feedEventHours, knownBy, placeRecordsAt, placeRecordTally } from "@/lib/flood-timeline-command-feed";
import {
  EXERCISE_FILE_URL,
  EXERCISE_STATUSES,
  EXERCISE_URGENCIES,
  exerciseCounts,
  exerciseMarkerSpec,
  lifeAtRiskHours,
  parseExerciseFile,
  type ExerciseHandling,
} from "@/lib/flood-timeline-command-incidents";
import {
  COMMAND_STATUS,
  commandDeviceMeta,
  commandFeedHeadline,
  commandItemMarkerTitle,
  commandItemPlaceLine,
  commandItemStateLine,
  commandItemTitle,
  commandItemWhatLine,
  commandItemWhenLine,
  commandModelHereLine,
  commandNewItemsNotice,
  commandRecordTallyChip,
  commandRecordTallyLine,
} from "@/lib/flood-timeline-command-reports-copy";
import { commandDayChips, commandMarkStops, commandPhaseSpans, commandReplayReducer, initialCommandReplay, nextEventStop, previousEventStop } from "@/lib/flood-timeline-command-replay";
import { parseAccessNodes } from "@/lib/flood-timeline-evacuation";
import type { PublicReport } from "@/lib/public-report";
import { describeWordingFindings, findWordingViolations, visibleText } from "@/lib/replay-wording-lint";

import { CommandLegend, CommandNotice, CommandViewPopover } from "./mae-sai-command-chrome";
import { CommandModeSegments, CommandModeSwitch, MaeSaiCommandFeed } from "./mae-sai-command-feed";
import { CommandDeviceDetailBody, CommandItemDetailBody } from "./mae-sai-command-incident";
import { clusterMarkerNodes, exerciseMarkerNodes, EXERCISE_MARKER_VIEWBOX, MarkerGlyph, placeRecordMarkerNodes, type SvgNode } from "./mae-sai-command-markers";
import { keyboardPopups } from "./mae-sai-map-kit";
import { MaeSaiCommandSituation } from "./mae-sai-command-situation";
import { MaeSaiCommandTimebar, type CommandPhaseBandItem } from "./mae-sai-command-timebar";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<unknown, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes: parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!) });
const exercise = parseExerciseFile(JSON.parse(read(EXERCISE_FILE_URL).toString("utf8")));
const feed = buildCommandFeed(manifest, model);
const days = commandDayChips(manifest.days);
const phases: CommandPhaseBandItem[] = commandPhaseSpans(manifest.phases).map((span, index) => ({ ...span, label: manifest.phases[index].label }));
const item = (id: string) => exercise.items.find((entry) => entry.id === id)!;

const LANGUAGES: readonly Language[] = ["en", "th"];
const noop = () => undefined;
const html = (node: ReactElement) => renderToStaticMarkup(node);
const text = (markup: string) => visibleText(markup).replace(/\s+/g, " ").trim();
const lintOf = (value: string, source: string) => describeWordingFindings(findWordingViolations(value, source));
const attr = (nodes: readonly SvgNode[], name: string) => nodes.map((node) => node.attrs[name]).filter((value) => value !== undefined);
const NEW: ExerciseHandling = { status: "new", callsign: null };
const deviceReport = (id: string, area: string, depth: PublicReport["water_depth"], notes = ""): PublicReport => ({
  schema_version: "1.0", report_id: `public-report:${id}`, planning_area_id: area, planning_area_name_th: "โป่งผา", planning_area_name_en: "Pong Pha",
  water_depth: depth, water_depth_cm: 48, notes, photo_attached: notes !== "", created_at: "2026-10-05T03:40:00.000Z", storage_scope: "device_local",
});
const timebar = (hour: number, language: Language, mode: "trainee" | "hindsight" = "trainee") => html(
  <MaeSaiCommandTimebar language={language} hour={hour} playing={false} speed="hour_per_second" days={days} phases={phases} stops={commandMarkStops(feedEventHours(feed))}
    rainfall={manifest.rainfall ?? null} feed={feed} mode={mode} onMode={noop} onTogglePlay={noop} onStep={noop} onSeek={noop} onEvent={noop} onSpeed={noop} />,
);

describe("Marker drawings: every state", () => {
  it("draws an exercise item by urgency (size, symbol, colour) and by handling state (outline)", () => {
    for (const kind of ["call", "report"] as const) {
      for (const urgency of EXERCISE_URGENCIES) {
        for (const status of EXERCISE_STATUSES) {
          const spec = exerciseMarkerSpec({ kind, urgency }, status);
          const nodes = exerciseMarkerNodes(spec);
          const name = `${kind} ${urgency} ${status}`;
          // An octagon is a path, a rounded square a rect.
          expect(nodes[0].tag, name).toBe(kind === "call" ? "path" : "rect");
          if (spec.closed) {
            // Grey with a tick, and no urgency symbol.
            expect(nodes).toHaveLength(2);
            expect(nodes[0].attrs.fill).toBe("#b4bcbd");
            expect(nodes.some((node) => node.tag === "text")).toBe(false);
            continue;
          }
          expect(nodes).toHaveLength(3);
          expect(nodes[0].attrs.fill, name).toBe(spec.fill);
          expect(nodes[0].attrs.stroke).toBe("#ffffff");
          // The white halo of a life-at-risk item is wider than the casing of the others.
          expect(nodes[0].attrs["stroke-width"]).toBe(urgency === "life_at_risk" ? 3.4 : 2);
          // Dashed while new; solid once acknowledged or assigned.
          expect(nodes[1].attrs["stroke-dasharray"], name).toBe(status === "new" ? "3 2.5" : undefined);
          expect(nodes[2]).toMatchObject({ tag: "text", text: spec.symbol });
          expect(nodes[2].attrs.fill).toBe(spec.symbolColour);
        }
      }
    }
    // The three sizes: 36, 30 and 26 px across.
    const width = (urgency: "life_at_risk" | "urgent" | "information") => {
      const d = String(exerciseMarkerNodes(exerciseMarkerSpec({ kind: "call", urgency }))[0].attrs.d);
      const xs = [...d.matchAll(/(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)/g)].map((match) => Number(match[1]));
      return Math.max(...xs) - Math.min(...xs);
    };
    expect([width("life_at_risk"), width("urgent"), width("information")]).toEqual([36, 30, 26]);
  });

  it("draws a place record as a white bubble with its count, and a dashed badge where the model is dry at the point", () => {
    const plain = placeRecordMarkerNodes(3, false);
    expect(plain).toHaveLength(2);
    expect(plain[0].attrs.fill).toBe("#ffffff");
    expect(plain[1]).toMatchObject({ tag: "text", text: "3" });
    const dry = placeRecordMarkerNodes(2, true);
    expect(dry).toHaveLength(5);
    expect(dry[2].attrs["stroke-dasharray"]).toBe("2 1.6");
    // Urgency colours are for exercise markers only.
    for (const colour of ["#D55E00", "#E69F00", "#0072B2"]) expect(attr(dry, "fill")).not.toContain(colour);
  });

  it("draws a count mark with the total, and \"!!\" with its count when it holds a life-at-risk item", () => {
    expect(clusterMarkerNodes(7, 0).map((node) => node.text).filter(Boolean)).toEqual(["7"]);
    const withLife = clusterMarkerNodes(22, 2);
    expect(withLife.map((node) => node.text).filter(Boolean)).toEqual(["22", "!!2"]);
    expect(attr(withLife, "fill")).toContain("#D55E00");
  });

  it("renders the same drawing in the legend", () => {
    const glyph = html(<MarkerGlyph nodes={exerciseMarkerNodes(exerciseMarkerSpec({ kind: "call", urgency: "life_at_risk" }))} viewBox={EXERCISE_MARKER_VIEWBOX} size={24} />);
    expect(glyph).toMatch(/^<svg viewBox="-22 -22 44 44" width="24" height="24"[^>]*aria-hidden="true"/);
    expect(glyph).toContain('stroke-dasharray="3 2.5"');
    expect(glyph).toContain(">!!</text>");
  });
});

describe("Popup lines of an exercise item", () => {
  it("has six lines: the tag and kind, the place, what, when, the model, and the state", () => {
    const life = item("EX-05");
    expect(commandItemTitle(life, "en")).toBe("Exercise · invented · Call for help · EX-05");
    expect(commandItemTitle(item("EX-03"), "th")).toBe("ฝึกซ้อม · สมมุติขึ้น · รายงานสภาพถนน · EX-03");
    expect(commandItemPlaceLine(life, { th: "แม่สาย", en: "Mae Sai" }, "en")).toBe("หมู่บ้านปิยะพร (Piyaphon village) · Mae Sai subdistrict · placed to within ±400 m");
    expect(commandItemPlaceLine(life, { th: "แม่สาย", en: "Mae Sai" }, "th")).toBe("หมู่บ้านปิยะพร · ต.แม่สาย · ตำแหน่งคลาดเคลื่อนได้ ±400 ม.");
    expect(commandItemWhatLine(life, "en")).toBe("water above head height · 1–2 people · needs: evacuation");
    expect(commandItemWhatLine(item("EX-01"), "en")).toBe("waist-deep water · no people stated · no need stated");
    expect(commandItemWhenLine(life, 6, "en")).toBe("Received 10 Sep 22:00 ICT (replay time) · waiting 6 h in replay time");
    expect(commandItemWhenLine(life, 0, "th")).toBe("ได้รับเมื่อ 10 ก.ย. 22:00 น. (เวลาในการย้อนดู) · เพิ่งได้รับในชั่วโมงนี้ของการย้อนดู");
    expect(commandItemWhenLine(life, null, "en")).toBe("Received 10 Sep 22:00 ICT (replay time)");
    // The model line always says that the current is not modelled.
    expect(commandModelHereLine(0.42, "en")).toBe("Model here: ~0.4 m of water at this replay hour · current not modelled");
    expect(commandModelHereLine(0, "en")).toBe("Model here: dry at this replay hour · current not modelled");
    expect(commandModelHereLine(0.02, "th")).toBe("แบบจำลอง ณ จุดนี้: น้ำลึก <0.1 ม. ณ ชั่วโมงนี้ของการย้อนดู · ไม่ได้จำลองกระแสน้ำ");
    expect(commandModelHereLine(null, "en")).toBe("Model here: outside the modelled area");
    expect(commandModelHereLine(undefined, "en")).toBe("Model here: the water layer has not loaded");
    expect(commandItemStateLine(life, NEW, "en")).toBe("Life at risk · new");
    expect(commandItemStateLine(item("EX-02"), { status: "assigned", callsign: "BOAT-2" }, "en")).toBe("Urgent · assigned · BOAT-2");
    expect(commandItemMarkerTitle(life, NEW, "en")).toBe("Exercise · invented · Call for help · EX-05: Life at risk · new · Piyaphon village");
    // The states are new, acknowledged, assigned, done and dropped; nothing is called checked or proven.
    expect(Object.values(COMMAND_STATUS).map((entry) => entry.en)).toEqual(["new", "acknowledged", "assigned", "done", "dropped"]);
  });

  it("says on a device sign that it is outside the replay", () => {
    expect(commandDeviceMeta("2026-10-05T03:40:00.000Z", "en")).toBe("This device · 5 Oct 2026 · not part of the 2024 replay · tambon (subdistrict) only");
    expect(commandDeviceMeta("2026-10-05T03:40:00.000Z", "th")).toBe("อุปกรณ์เครื่องนี้ · 5 ต.ค. 2569 (2026) · ไม่ใช่ส่วนหนึ่งของการย้อนดูเหตุการณ์ปี 2567 (2024) · ระบุเพียงระดับตำบล");
  });
});

describe("Situation card: open exercise items and the place-record chip", () => {
  it("counts the open exercise items in plain digits under the exercise tag, apart from the model figures", () => {
    const counts = exerciseCounts(exercise.items, 84);
    const markup = html(<MaeSaiCommandSituation language="en" hour={84} manifest={manifest} model={model} exercise={counts} tally={placeRecordTally(placeRecordsAt(manifest.reported_depths!.reports, 84, "trainee"))} />);
    expect(markup).toMatch(/data-figure="exerciseItems" data-open="11" data-life="2"/);
    expect(text(markup)).toContain("Open exercise items: 11 (invented). 2 at life at risk.");
    // A counted thing carries no tilde.
    expect(markup).not.toContain("~11");
    expect(text(markup)).toContain("11 place records · model dry at 9");
    expect(markup).toContain('aria-label="Place records with a point: 11. At the point, the model is consistent with 1, wet at 1 and dry at 9."');
    // Before any item arrives the count is a plain 0, with no life-at-risk line.
    const early = html(<MaeSaiCommandSituation language="en" hour={20} manifest={manifest} model={model} exercise={exerciseCounts(exercise.items, 20)} tally={placeRecordTally([])} />);
    expect(early).toMatch(/data-figure="exerciseItems" data-open="0" data-life="0"/);
    expect(early).not.toContain("data-command-record-chip");
  });

  it("computes the situation line from the data: 12 with a point, consistent with 1, wet at 2 and dry at 9", () => {
    const all = placeRecordTally(manifest.reported_depths!.reports);
    expect(commandRecordTallyLine(all, "en")).toBe("Place records with a point: 12. At the point, the model is consistent with 1, wet at 2 and dry at 9.");
    expect(commandRecordTallyLine(all, "th")).toBe("รายการตามสถานที่ที่มีจุดบนแผนที่: 12 รายการ ที่จุดเหล่านั้นแบบจำลองสอดคล้อง 1 มีน้ำ 2 และแห้ง 9");
    expect(commandRecordTallyChip(all, "en")).toBe("12 place records · model dry at 9");
    expect(commandRecordTallyLine(placeRecordTally([]), "en")).toBe("No place record with a point by this replay hour.");
  });
});

describe("Time dock: event marks and the mode switch", () => {
  it("draws filled marks for reported or observed rows and hollow marks for the model, up to the replay hour in trainee mode", () => {
    const trainee = timebar(84, "en");
    const marks = [...trainee.matchAll(/<i style="left:[^"]*" data-filled="(true|false)" data-count="(\d+)" data-hour="(\d+)">/g)].map((match) => ({ filled: match[1] === "true", count: Number(match[2]), hour: Number(match[3]) }));
    expect(marks.length).toBeGreaterThan(5);
    expect(marks.every((mark) => mark.hour <= 84)).toBe(true);
    expect(marks.some((mark) => !mark.filled)).toBe(true);
    expect(marks.some((mark) => mark.filled && mark.count > 1)).toBe(true);
    expect(marks.reduce((sum, mark) => sum + mark.count, 0)).toBe(knownBy(feed, 84).filter((row) => row.precision !== "held").length);
    expect(trainee).toContain("data-command-future");
    expect(text(trainee)).toContain("Trainee mode · the future is hidden");
    expect(trainee).toMatch(/aria-pressed="true" aria-label="Trainee mode: hide the future"/);
    // Hindsight: every mark of the replay, and no hatch over the later hours.
    const hindsight = timebar(84, "en", "hindsight");
    expect([...hindsight.matchAll(/data-filled="/g)].length).toBeGreaterThan(marks.length);
    expect(hindsight).not.toContain("data-command-future");
    expect(text(hindsight)).toContain("Hindsight mode · everything is shown");
    expect(text(timebar(84, "th"))).toContain("โหมดผู้ฝึก · ซ่อนสิ่งที่ยังไม่เกิด");
  });

  it("stops the event buttons at the hours of the marks, and pauses playback when a life-at-risk item arrives", () => {
    const stops = commandMarkStops(feedEventHours(feed));
    expect(stops[0]).toEqual({ hour: 0, kind: "start" });
    expect(stops[stops.length - 1]).toEqual({ hour: 264, kind: "end" });
    // After 10 Sep 12:00 the next mark is the article published at 13:00.
    expect(nextEventStop(stops, 36)?.hour).toBe(37);
    expect(previousEventStop(stops, 84)?.hour).toBeLessThan(84);
    expect(commandMarkStops([5, 5, 300, -4]).map((stop) => stop.hour)).toEqual([0, 5, 264]);
    // Playback stops at hour 46, where EX-05 arrives; pressing play again goes on.
    const pauseAt = lifeAtRiskHours(exercise.items);
    let state = { ...initialCommandReplay(44), playing: true };
    state = commandReplayReducer(state, { type: "tick", pauseAt });
    expect(state).toMatchObject({ hour: 45, playing: true });
    state = commandReplayReducer(state, { type: "tick", pauseAt });
    expect(state).toMatchObject({ hour: 46, playing: false });
    state = commandReplayReducer(commandReplayReducer(state, { type: "toggle_play" }), { type: "tick", pauseAt });
    expect(state).toMatchObject({ hour: 47, playing: true });
    // Switched off, playback runs through.
    expect(commandReplayReducer({ ...initialCommandReplay(45), playing: true }, { type: "tick", pauseAt: new Set() })).toMatchObject({ hour: 46, playing: true });
    expect(commandReplayReducer({ ...initialCommandReplay(45), playing: true }, { type: "tick" })).toMatchObject({ hour: 46, playing: true });
  });

  it("offers the two modes as two buttons and as one switch", () => {
    const segments = html(<CommandModeSegments language="en" mode="trainee" onMode={noop} />);
    expect([...segments.matchAll(/aria-pressed="(true|false)"[^>]*data-mode="([a-z]+)"/g)].map((match) => `${match[2]}:${match[1]}`)).toEqual(["trainee:true", "hindsight:false"]);
    expect(html(<CommandModeSwitch language="th" mode="hindsight" onMode={noop} />)).toMatch(/aria-pressed="false"[^>]*data-command-mode-switch="hindsight"/);
  });
});

describe("\"Known by now\"", () => {
  const list = (hour: number, language: Language, mode: "trainee" | "hindsight" = "trainee") => html(
    <MaeSaiCommandFeed language={language} hour={hour} mode={mode} onMode={noop} items={feedAt(feed, hour, mode)} depths={manifest.reported_depths ?? null} onPlace={noop}
      tally={placeRecordTally(placeRecordsAt(manifest.reported_depths!.reports, hour, mode))} />,
  );

  it("opens with the fixed lines: what is missing, and how the model reads at the place records known by now", () => {
    const markup = list(84, "en");
    expect(text(markup)).toContain("Missing No public hourly river-level record for the Sai was found.");
    expect(text(markup)).toContain("Place records with a point: 11. At the point, the model is consistent with 1, wet at 1 and dry at 9.");
    expect(text(list(84, "th"))).toContain("ไม่พบข้อมูลระดับน้ำแม่น้ำสายรายชั่วโมงที่เปิดเผยต่อสาธารณะ");
    // The fixed lines stand before the first row.
    expect(markup.indexOf('data-feed-fixed="missing"')).toBeLessThan(markup.indexOf("data-feed-item"));
  });

  it("lists the rows newest first, grouped by day, each with its lane tag, time and source", () => {
    const markup = list(84, "en");
    const ids = [...markup.matchAll(/data-feed-item="([^"]+)"/g)].map((match) => match[1]);
    expect(ids).toEqual(knownBy(feed, 84).map((row) => row.id));
    expect([...markup.matchAll(/data-feed-group="([^"]+)"/g)].map((match) => match[1])).toEqual(["2024-09-12", "2024-09-11", "2024-09-10", "2024-09-09", "start"]);
    expect(text(markup)).toContain("12 Sep 2024");
    expect(text(markup)).toContain("Held at the start of the replay");
    // A satellite pass is worded as acquired; the RADARSAT-2 figure carries the calibration tag.
    expect(text(markup)).toContain("Sentinel-2 image of 5 Sep 10:58 ICT: held at the start");
    expect(text(markup)).toContain("Calibration GISTDA RADARSAT-2 flood analysis: 9.9 km² of water in Mae Sai district Calibration: used to set the model. Acquired at this time and published later.");
    expect(text(markup)).toContain("VIIRS daily flood map: 100% of the district under cloud");
    // The pass of 12 Sep 13:30 is known from 14:00, not at 12:00.
    expect(text(markup)).not.toContain("82% of the district under cloud");
    expect(text(list(86, "en"))).toContain("VIIRS daily flood map: 82% of the district under cloud");
    expect(text(markup)).toContain("Model Highest assumed river stage in the model: 3.5 m");
    expect(text(markup)).toContain("2 shelters and the district command centre reported in use");
    // A place with a point is a link that moves the map; a source opens in a new tab.
    expect(markup).toContain("data-feed-place");
    expect(markup).toMatch(/<a class="[^"]*" href="https:\/\/[^"]+" target="_blank" rel="noopener noreferrer">/);
    // Nothing of a later hour: the 15 Sep pass and UNOSAT 3991 are not in the list.
    expect(text(markup)).not.toContain("acquired 15 Sep");
    expect(text(markup)).not.toContain("UNOSAT product 3991");
    expect(text(list(160, "en"))).toContain("Sentinel-2 image acquired 15 Sep 10:58 ICT; would have reached responders later");
  });

  it("shows everything in hindsight, with the season envelope and its credit sentence from the manifest", () => {
    const markup = list(60, "en", "hindsight");
    expect([...markup.matchAll(/data-feed-item=/g)]).toHaveLength(feed.length);
    expect(text(markup)).toContain("Hindsight mode · everything is shown");
    expect(text(markup)).toContain("Whole event · hindsight only");
    expect(text(markup)).toContain("UNOSAT product 3991: about 70 km² of water mapped over 13–19 Sep 2024 (cumulative) Preliminary, not field-validated.");
    expect(text(markup)).toContain("2024 season envelope: water mapped at some time from August to October 2024 (scenario)");
    expect(text(markup)).toContain(manifest.season_envelope!.standard_sentence);
    expect(text(markup)).toContain("Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009");
    // Rows of a later hour say so.
    expect(markup).toContain('data-later="true"');
    expect(text(markup)).toContain("later than this replay hour");
  });

  it("says so when nothing is known yet, and while the data loads", () => {
    const empty = html(<MaeSaiCommandFeed language="en" hour={0} mode="trainee" onMode={noop} items={[]} tally={placeRecordTally([])} depths={null} onPlace={noop} />);
    expect(text(empty)).toContain("Nothing had been reported or observed by this replay hour.");
    expect(text(empty)).toContain("No place record with a point by this replay hour.");
    const loading = html(<MaeSaiCommandFeed language="en" hour={0} mode="trainee" onMode={noop} items={null} tally={null} depths={null} onPlace={noop} />);
    expect(text(loading)).toContain("appears when the replay data has loaded");
  });

  it("words every row in both languages without a banned claim", () => {
    for (const language of LANGUAGES) {
      for (const row of feed) expect(lintOf(commandFeedHeadline(row, manifest.reported_depths ?? null, language), row.id), `${row.id} ${language}`).toBe("");
    }
  });
});

describe("Inspector of a report", () => {
  it("shows an invented item with its tag first, its urgency, what it says, the model at its point and the rule", () => {
    const life = item("EX-09");
    const markup = html(<CommandItemDetailBody language="en" hour={84} item={life} handling={NEW} tambon={{ th: "เวียงพางคำ", en: "Wiang Phang Kham" }} depth={3.2} rule={exercise.rule} />);
    expect(markup).toMatch(/data-command-item="EX-09" data-urgency="life_at_risk"/);
    const shown = text(markup);
    expect(shown.startsWith("Exercise · invented Call for help EX-09")).toBe(true);
    expect(shown).toContain("Life at risk · new");
    expect(shown).toContain("waiting 22 h in replay time");
    expect(shown).toContain("Four adults are standing in chest-deep water on a ground floor.");
    expect(shown).toContain("~3.2 m of water at this replay hour · current not modelled");
    expect(shown).toContain("Model · low confidence");
    expect(shown).toContain("Urgency is set by the author of an item from the facts it states, never by the model.");
    expect(shown).toContain("Never counted with real reports.");
    // No team-type advice anywhere on the card.
    expect(shown).not.toMatch(/boat|wading/i);
    const thai = text(html(<CommandItemDetailBody language="th" hour={84} item={life} handling={NEW} tambon={{ th: "เวียงพางคำ", en: "Wiang Phang Kham" }} depth={0} rule={exercise.rule} />));
    expect(thai).toContain("ฝึกซ้อม · สมมุติขึ้น");
    expect(thai).toContain("เสี่ยงต่อชีวิต · ใหม่");
    expect(thai).toContain("แห้ง ณ ชั่วโมงนี้ของการย้อนดู · ไม่ได้จำลองกระแสน้ำ");
  });

  it("shows the reports saved on this device with their date, and keeps a note behind a tap", () => {
    const reports = [deviceReport("a00001", "TH570904", "knee", "Water at the gate."), deviceReport("a00002", "TH570904", "waist")];
    const markup = html(<CommandDeviceDetailBody language="en" tambon={{ id: "TH570904", th: "โป่งผา", en: "Pong Pha" }} reports={reports} />);
    const shown = text(markup);
    expect(shown).toContain("This device · 5 Oct 2026 · not part of the 2024 replay · tambon (subdistrict) only");
    expect(shown).toContain("2 reports saved");
    expect(shown).toContain("Depth: Knee · 48 cm");
    expect(shown).toContain("Nothing was sent to anyone.");
    expect(markup).toMatch(/<details><summary>Show the note<\/summary><p>Water at the gate\.<\/p><\/details>/);
    expect([...markup.matchAll(/<details>/g)]).toHaveLength(1);
  });
});

describe("Exercise options, legend and notice", () => {
  it("offers the invented items and the pause for a life-at-risk item, both on", () => {
    const markup = html(<CommandViewPopover language="en" facilities={false} facilityCount={42} onFacilities={noop} onClose={noop}
      exercise={{ count: 14, items: true, onItems: noop, pause: true, onPause: noop }} />);
    expect(text(markup)).toContain("Exercise items (14)");
    expect(text(markup)).toContain("Pause when a life-at-risk item arrives");
    expect(markup).toMatch(/<input type="checkbox" data-command-items="true" checked=""\/>/);
    expect(markup).toMatch(/<input type="checkbox" data-command-pause="true" checked=""\/>/);
  });

  it("explains the marker grammar in the legend", () => {
    const shown = text(html(<CommandLegend language="en" open onToggle={noop} facilities={false} unmodelledRoads={false} wetSites={false} />));
    for (const entry of [
      "2024 place records at a point, with their count", "model dry at the point", "call: life at risk", "call: urgent", "call: information", "depth or road report",
      "dashed: new", "solid: acknowledged or assigned", "grey, tick: done or dropped", "callsign and hours waited (replay)", "reports saved on this device",
      "no reports received", "several items", "stated tolerance of the selected place", "shelter not yet reported at this hour",
      "never by the model. The colours are not those of medical triage.",
    ]) expect(shown, entry).toContain(entry);
    // What the map draws of water and roads is modelled: the legend wears the model tag in its head, as text.
    const legend = html(<CommandLegend language="en" open onToggle={noop} facilities={false} unmodelledRoads={false} wetSites={false} />);
    expect(legend).toMatch(/data-command-lane="model">Model · low confidence<\/span>/);
    // Wet and impassable roads are drawn over modelled water, a dry road on the ground.
    expect(legend.match(/data-over="water"/g)).toHaveLength(2);
    // Its title can take the keyboard focus when the legend opens.
    expect(legend).toMatch(/<h2 id="[^"]*" tabindex="-1" data-command-panel-title="true">Legend<\/h2>/);
    // The season envelope is in the legend in hindsight mode only.
    expect(shown).not.toContain("2024 season envelope (scenario)");
    expect(text(html(<CommandLegend language="en" open onToggle={noop} facilities={false} unmodelledRoads={false} wetSites={false} mode="hindsight" />))).toContain("2024 season envelope (scenario)");
  });

  it("names what a step forward brought, and is a button that shows it", () => {
    expect(commandNewItemsNotice(1, 0, false, "en")).toBe("New exercise call (1)");
    expect(commandNewItemsNotice(0, 2, false, "en")).toBe("New exercise report (2)");
    expect(commandNewItemsNotice(2, 1, false, "en")).toBe("New exercise items (3)");
    expect(commandNewItemsNotice(1, 0, true, "en")).toBe("New exercise call (1) · replay paused");
    expect(commandNewItemsNotice(1, 0, true, "th")).toBe("ฝึกซ้อม: มีการขอความช่วยเหลือใหม่ (1) · หยุดการเล่นชั่วคราว");
    const button = html(<CommandNotice language="en" message="New exercise call (1)" onSelect={noop} />);
    expect(button).toMatch(/<button type="button" class="[^"]*" data-command-notice="action">New exercise call \(1\)/);
    expect(html(<CommandNotice language="en" message="A line" />)).toMatch(/<p class="[^"]*" data-command-notice="true">A line<\/p>/);
  });
});

describe("Keys of the map popups (the shared map kit)", () => {
  afterEach(() => vi.unstubAllGlobals());

  /** A map as the key handling sees it: a container that takes one key listener, and a popup that can be closed. */
  const fakeMap = () => {
    let listener: ((event: unknown) => void) | null = null;
    const state = { closed: 0, open: true };
    const map = {
      getContainer: () => ({ addEventListener: (_type: string, handler: (event: unknown) => void) => { listener = handler; }, removeEventListener: () => { listener = null; } }),
      closePopup: () => { state.closed += 1; state.open = false; },
    };
    const press = (key: string) => {
      const event = { key, target: null, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
      listener?.(event);
      return event;
    };
    return { map: map as unknown as Parameters<typeof keyboardPopups>[0], state, press, wired: () => listener !== null };
  };

  it("uses Escape up when it closes a popup, so the page clears nothing else on that key press", () => {
    vi.stubGlobal("HTMLElement", class {});
    const { map, state, press, wired } = fakeMap();
    const keys = keyboardPopups(map, () => state.open, { consumeEscape: true });
    // A popup is open: Escape closes it and is marked as handled. The page's own key handler leaves a handled key alone.
    const first = press("Escape");
    expect([state.closed, first.defaultPrevented]).toEqual([1, true]);
    // No popup is open: the key is left for the page (it clears the selection, then leaves focus mode).
    const second = press("Escape");
    expect([state.closed, second.defaultPrevented]).toEqual([1, false]);
    // Other keys are never used up.
    state.open = true;
    expect(press("Enter").defaultPrevented).toBe(false);
    keys.remove();
    expect(wired()).toBe(false);
  });

  it("leaves the key unmarked without the option, as on the Studio replay", () => {
    vi.stubGlobal("HTMLElement", class {});
    const { map, state, press } = fakeMap();
    keyboardPopups(map, () => state.open);
    const event = press("Escape");
    expect([state.closed, event.defaultPrevented]).toEqual([1, false]);
  });
});

describe("Reports and \"Known by now\": wording", () => {
  it("passes the shared wording lint in both languages", () => {
    for (const language of LANGUAGES) {
      const panels: [string, ReactElement][] = [
        ["situation", <MaeSaiCommandSituation key="a" language={language} hour={84} manifest={manifest} model={model} exercise={exerciseCounts(exercise.items, 84)} tally={placeRecordTally(manifest.reported_depths!.reports)} />],
        ["time dock, trainee", <MaeSaiCommandTimebar key="b" language={language} hour={84} playing={false} speed="drill" days={days} phases={phases} stops={[]} rainfall={manifest.rainfall ?? null} feed={feed} mode="trainee" onMode={noop} onTogglePlay={noop} onStep={noop} onSeek={noop} onEvent={noop} onSpeed={noop} />],
        ["feed, trainee", <MaeSaiCommandFeed key="c" language={language} hour={110} mode="trainee" onMode={noop} items={feedAt(feed, 110, "trainee")} tally={placeRecordTally(manifest.reported_depths!.reports)} depths={manifest.reported_depths ?? null} onPlace={noop} />],
        ["feed, hindsight", <MaeSaiCommandFeed key="d" language={language} hour={60} mode="hindsight" onMode={noop} items={feedAt(feed, 60, "hindsight")} tally={placeRecordTally(manifest.reported_depths!.reports)} depths={manifest.reported_depths ?? null} onPlace={noop} />],
        ...exercise.items.map((entry): [string, ReactElement] => [`item ${entry.id}`, <CommandItemDetailBody key={entry.id} language={language} hour={120} item={entry} handling={NEW} tambon={{ th: "แม่สาย", en: "Mae Sai" }} depth={0.6} rule={exercise.rule} />]),
        ["device", <CommandDeviceDetailBody key="e" language={language} tambon={{ id: "TH570904", th: "โป่งผา", en: "Pong Pha" }} reports={[deviceReport("a00001", "TH570904", "knee", "A note.")]} />],
        ["legend, hindsight", <CommandLegend key="f" language={language} open onToggle={noop} facilities unmodelledRoads wetSites mode="hindsight" />],
        ["view", <CommandViewPopover key="g" language={language} facilities facilityCount={42} onFacilities={noop} onClose={noop} exercise={{ count: 14, items: true, onItems: noop, pause: true, onPause: noop }} />],
      ];
      for (const [name, node] of panels) expect(lintOf(visibleText(html(node)), `${name} ${language}`), `${name} ${language}`).toBe("");
      // The lines of a popup, as the map builds them from text nodes.
      for (const entry of exercise.items) {
        const lines = [commandItemTitle(entry, language), commandItemPlaceLine(entry, { th: "แม่สาย", en: "Mae Sai" }, language), commandItemWhatLine(entry, language), commandItemWhenLine(entry, 5, language),
          commandModelHereLine(0.4, language), commandItemStateLine(entry, NEW, language), commandItemMarkerTitle(entry, NEW, language)].join("\n");
        expect(lintOf(lines, `popup ${entry.id} ${language}`), `popup ${entry.id} ${language}`).toBe("");
      }
    }
  });
});
