/**
 * The Command exercise replay as it renders: the banner in both languages, the clock and the rounded model figures at
 * replay hour 84 from the served r4 files, the model-limit chip, focus mode, the time dock, the keys that step the
 * replay, the hour carried to the Studio replay, the information drawer and the legend. Every rendered panel passes
 * the shared wording lint.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type AreaGeometry, type GeoCollection, type Language, type RoadProps, type TambonProps, type TimelineManifest } from "@/lib/flood-timeline";
import { buildCommandModel, districtFiguresAt } from "@/lib/flood-timeline-command";
import { COMMAND_BANNER, commandBannerLine } from "@/lib/flood-timeline-command-copy";
import {
  commandDayChips,
  commandEventStops,
  commandKeyAction,
  commandPhaseSpans,
  commandReplayReducer,
  initialCommandReplay,
} from "@/lib/flood-timeline-command-replay";
import { localizedText } from "@/lib/flood-timeline-copy";
import { parseAccessNodes } from "@/lib/flood-timeline-evacuation";
import { describeWordingFindings, findWordingViolations, visibleText } from "@/lib/replay-wording-lint";
import {
  COMMAND_EXERCISE_ROUTE,
  CommandBanner,
  CommandCredits,
  CommandHelpSheet,
  CommandInfoBody,
  CommandLegend,
  CommandNav,
  CommandNotice,
  CommandToolRail,
  CommandViewPopover,
  CommandWatermark,
} from "./mae-sai-command-chrome";
import { MaeSaiCommandExercise } from "./mae-sai-command-exercise";
import { MaeSaiCommandSituation } from "./mae-sai-command-situation";
import { MaeSaiCommandTimebar, type CommandPhaseBandItem } from "./mae-sai-command-timebar";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<unknown, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes: parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!) });
const stops = commandEventStops(manifest, model.stages);
const days = commandDayChips(manifest.days);
const phases: CommandPhaseBandItem[] = commandPhaseSpans(manifest.phases).map((span, index) => ({ ...span, label: manifest.phases[index].label }));

const LANGUAGES: readonly Language[] = ["en", "th"];
const noop = () => undefined;
const html = (node: ReactElement) => renderToStaticMarkup(node);
/** The reader-visible text of rendered markup, with entities decoded and white space collapsed. */
const text = (markup: string) => visibleText(markup).replace(/\s+/g, " ").trim();
const lintOf = (markup: string, source: string) => describeWordingFindings(findWordingViolations(visibleText(markup), source));
const situation = (hour: number, language: Language, collapsed = false) =>
  html(<MaeSaiCommandSituation language={language} hour={hour} manifest={manifest} model={model} collapsed={collapsed} />);
const timebar = (hour: number, language: Language, more: { collapsed?: boolean; playing?: boolean; disabled?: boolean } = {}) =>
  html(<MaeSaiCommandTimebar language={language} hour={hour} playing={more.playing ?? false} speed="hour_per_second" collapsed={more.collapsed} disabled={more.disabled}
    days={days} phases={phases} stops={stops} rainfall={manifest.rainfall ?? null} onTogglePlay={noop} onStep={noop} onSeek={noop} onEvent={noop} onSpeed={noop} />);

describe("Command exercise page shell", () => {
  it("is the full-screen exercise root, with the banner and every region, before any data loads", () => {
    const markup = html(<MaeSaiCommandExercise />);
    expect(markup).toMatch(/^<main id="main-content" class="command-page [^"]*" data-command-exercise="true" data-focus="off" data-hour="36"/);
    expect(markup).toContain('data-command-ready="false"');
    for (const region of ["A", "B1", "B2", "C", "D", "E", "F", "G", "H", "I"]) expect(markup, region).toContain(`data-region="${region}"`);
    // Region D (the right card) is its chip until something is selected or the chip is pressed.
    expect(markup).toContain('data-command-card="chip"');
    expect(text(markup)).toContain("Known by now");
    // The table waits for the replay data and says so.
    expect(markup).toMatch(/data-region="B2"[^>]*data-state="waiting"/);
    expect(text(markup)).toContain("The table appears when the replay data has loaded");
    expect(text(markup)).toContain("Exercise replay");
    expect(text(markup)).toContain("Loading the replay data");
    // The clock needs no data: the page opens on 10 Sep 12:00.
    expect(text(markup)).toContain("10 Sep 2024 · 12:00 ICT");
    // The time controls wait for the data; the tools that need the map wait for the map.
    expect(markup).toMatch(/<button type="button" class="[^"]*" disabled="" aria-label="Play"/);
    expect(markup).toMatch(/disabled="" aria-label="Zoom in"/);
    expect(lintOf(markup, "Command shell")).toBe("");
  });

  it("lives at the temporary route and starts where it is told to", () => {
    expect(COMMAND_EXERCISE_ROUTE).toBe("/command/exercise/");
    const markup = html(<MaeSaiCommandExercise initial={{ hour: 84 }} />);
    expect(markup).toContain('data-hour="84"');
    expect(text(markup)).toContain("12 Sep 2024 · 12:00 ICT");
    expect(markup).toContain('href="/command/exercise/" aria-current="page"');
  });

  it("collapses the clock card, the table card and the time dock in focus mode", () => {
    const rest = html(<MaeSaiCommandExercise initial={{ hour: 84 }} />);
    const focus = html(<MaeSaiCommandExercise initial={{ hour: 84, focus: true }} />);
    expect(rest).toContain('data-focus="off"');
    expect(rest).toContain('data-collapsed="false"');
    expect(focus).toContain('data-focus="on"');
    expect(focus).toContain('data-collapsed="true"');
    // The clock card is one line: the short time and the replay hour.
    expect(text(focus)).toContain("12 Sep 12:00 ICT · h 84");
    expect(text(focus)).not.toContain("12 Sep 2024 · 12:00 ICT");
    // The focus tool is pressed and offers the way back; the banner stays.
    expect(focus).toMatch(/aria-pressed="true" aria-label="Leave focus mode"/);
    expect(rest).toMatch(/aria-pressed="false" aria-label="Focus mode: more map, smaller panels"/);
    expect(text(focus)).toContain("not an official warning");
  });
});

describe("Command banner (region A)", () => {
  it("prints the approved exercise line in English and in Thai, with the button of the information drawer", () => {
    const english = html(<CommandBanner language="en" onInfo={noop} infoOpen={false} />);
    expect(text(english)).toContain("Exercise replay Mae Sai, September 2024 reconstructed, not real-time not an official warning");
    for (const part of ["Exercise replay", "Mae Sai, September 2024", "reconstructed, not real-time", "not an official warning"]) expect(english).toContain(`>${part}<`);
    expect(commandBannerLine("en").split(" · ")).toHaveLength(4);
    expect(english).toContain('aria-label="About this exercise: permitted use, assumptions, limits, sources and licences"');
    expect(english).toContain('aria-haspopup="dialog"');
    const thai = html(<CommandBanner language="th" onInfo={noop} infoOpen={false} />);
    for (const part of ["ฝึกซ้อมย้อนดูเหตุการณ์", "แม่สาย กันยายน 2567 (2024)", "จำลองย้อนหลัง ไม่ใช่ข้อมูลเรียลไทม์", "ไม่ใช่คำเตือนทางการ"]) expect(thai).toContain(`>${part}<`);
    expect(thai).toContain('lang="th"');
    // The banner has no control that closes or hides it.
    for (const markup of [english, thai]) {
      expect(markup.match(/<button/g)).toHaveLength(1);
      expect(lintOf(markup, "banner")).toBe("");
    }
  });

  it("tiles the exercise label across the map in both languages at once", () => {
    const markup = html(<CommandWatermark tiles={12} />);
    expect(markup.match(/EXERCISE · ฝึกซ้อม/g)).toHaveLength(12);
    expect(markup).toContain('aria-hidden="true"');
    expect(COMMAND_BANNER.watermark.en).toBe("EXERCISE · ฝึกซ้อม");
  });
});

describe("Command clock and figures (region B1)", () => {
  it("shows the replay time, the hour, the phase and the assumed stage at replay hour 84", () => {
    const english = situation(84, "en");
    expect(text(english)).toContain("Replay time");
    expect(text(english)).toContain("12 Sep 2024 · 12:00 ICT");
    expect(text(english)).toContain("hour 84 of 264");
    expect(text(english)).toContain("Phase: Peak · assumed river stage 3.5 m (illustrative curve)");
    expect(english).toContain('data-command-phase="peak"');
    const thai = situation(84, "th");
    expect(text(thai)).toContain("เวลาในการย้อนดู");
    expect(text(thai)).toContain("12 ก.ย. 2567 (2024) · 12:00 น.");
    expect(text(thai)).toContain("ชั่วโมงที่ 84 จาก 264");
    expect(text(thai)).toContain("ระยะ: ระดับสูงสุด · ระดับแม่น้ำสมมุติ 3.5 ม. (ค่าเพื่อการอธิบาย)");
  });

  it("shows the three model figures rounded, under the model tag, never to the last digit", () => {
    const figures = districtFiguresAt(model, 84);
    // The figures of the replay data at the peak, as the plan and the export table give them (163.8 km to one decimal).
    expect([figures.lostAccess, figures.inWater, figures.roadKmImpassable]).toEqual([7086, 16060, 163.77]);
    const english = situation(84, "en");
    expect(english).toMatch(/data-figure="lostAccess"><strong>~7,100<\/strong><span>lost shelter access<\/span><small>of ~34,500 in reach<\/small>/);
    expect(english).toMatch(/data-figure="inWater"><strong>~16,100<\/strong><span>residents in modelled water<\/span>/);
    expect(english).toMatch(/data-figure="roads"><strong>~164 km<\/strong><span>roads impassable<\/span><small>of 307 km<\/small>/);
    expect(text(english)).toContain("Model · low confidence");
    for (const exact of ["7,086", "7086", "16,060", "16060", "163.8", "163.77"]) expect(english, exact).not.toContain(exact);
    // The fourth figure, open exercise items, keeps its slot; without the exercise file it says the items are off.
    expect(english).toContain('data-figure="exerciseItems"');
    expect(text(english)).toContain("Exercise items are switched off");
    const thai = situation(84, "th");
    expect(thai).toMatch(/<strong>~7,100<\/strong><span>สูญเสียการเข้าถึงที่พักพิง<\/span><small>จาก ~34,500 คนในระยะเดิน<\/small>/);
    expect(thai).toMatch(/<strong>~164 กม.<\/strong><span>ถนนสัญจรไม่ได้<\/span>/);
    expect(text(thai)).toContain("แบบจำลอง · ความเชื่อมั่นต่ำ");
    // Before the flood the figures are plain zeros.
    expect(situation(30, "en")).toMatch(/data-figure="lostAccess"><strong>0<\/strong>/);
  });

  it("says what changed since the hour before", () => {
    expect(text(situation(84, "en"))).toContain("Since 12 Sep 11:00: +~100 lost access · 0 in water · +~1 km impassable");
    expect(text(situation(44, "en"))).toContain("newly impassable: Mae Sai bypass, Phahonyothin Rd (Hwy 1) and 1 more");
    expect(text(situation(0, "en"))).toContain("Start of the replay: no hour before to compare with");
    expect(text(situation(84, "th"))).toContain("ตั้งแต่ 12 ก.ย. 11:00 น.: +~100 สูญเสียการเข้าถึง");
  });

  it("shows the model-limit chip in the Receding and Mostly receded phases only", () => {
    for (const hour of [0, 30, 84, 95]) {
      expect(situation(hour, "en"), String(hour)).not.toContain("data-command-limit");
      expect(situation(hour, "en")).toContain('data-limit="off"');
    }
    for (const hour of [96, 130, 200, 264]) {
      const markup = situation(hour, "en");
      expect(markup, String(hour)).toContain("data-command-limit");
      expect(markup).toContain('data-limit="on"');
      expect(text(markup)).toContain("Model limit: standing water and mud are not reconstructed");
      // The full sentence of the replay data is the chip's title.
      expect(markup).toContain('title="The model dries as the river falls; standing water and mud are not reconstructed."');
    }
    expect(text(situation(130, "th"))).toContain("ข้อจำกัดของแบบจำลอง: ไม่ได้จำลองน้ำท่วมขังและโคลน");
  });

  it("is one line in focus mode: the short time, the hour and two of the figures", () => {
    const markup = situation(84, "en", true);
    expect(text(markup)).toBe("12 Sep 12:00 ICT · h 84 ~7,100 lost access · ~16,100 in water │ Situation at the replay hour │ Model · low confidence");
    expect(markup).not.toContain("data-figure");
    expect(text(situation(84, "th", true))).toContain("12 ก.ย. 12:00 น. · ชม. 84");
  });

  it("says that the data is loading, or that it failed, with a way to try again", () => {
    const loading = html(<MaeSaiCommandSituation language="en" hour={36} manifest={null} model={null} />);
    expect(text(loading)).toContain("10 Sep 2024 · 12:00 ICT");
    expect(text(loading)).toContain("Loading the replay data");
    expect(loading).not.toContain("data-figure");
    const failed = html(<MaeSaiCommandSituation language="th" hour={36} manifest={null} model={null} failed onRetry={noop} />);
    expect(text(failed)).toContain("โหลดข้อมูลการย้อนดูไม่สำเร็จ");
    expect(failed).toContain(">ลองอีกครั้ง</button>");
  });

  it("passes the wording lint at every phase, in both languages", () => {
    for (const language of LANGUAGES) {
      for (const hour of [0, 30, 44, 84, 130, 200, 264]) {
        expect(lintOf(situation(hour, language), `situation ${hour} ${language}`)).toBe("");
        expect(lintOf(situation(hour, language, true), `situation line ${hour} ${language}`)).toBe("");
      }
    }
  });
});

describe("Command time dock (region F)", () => {
  it("has the event buttons, play, the hour steppers and the three speeds", () => {
    const markup = timebar(84, "en");
    for (const label of ["Previous event", "Play", "Next event", "Back one hour", "Forward one hour"]) expect(markup, label).toContain(`aria-label="${label}"`);
    expect(markup).toContain('role="group" aria-label="Playback speed"');
    expect(markup).toMatch(/aria-pressed="true"[^>]*data-command-speed="hour_per_second"/);
    expect(markup).toMatch(/aria-pressed="false"[^>]*data-command-speed="four_per_second"/);
    expect(markup).toMatch(/aria-pressed="false"[^>]*data-command-speed="drill"/);
    for (const label of ["1 replay hour per second", "4 replay hours per second", "Drill speed: 1 replay hour per minute"]) expect(markup).toContain(`aria-label="${label}"`);
    expect(text(markup)).toContain("−1 h");
    expect(text(markup)).toContain("+1 h");
    expect(timebar(84, "en", { playing: true })).toContain('aria-label="Pause"');
  });

  it("has eleven day chips with the day of the replay hour marked", () => {
    const markup = timebar(84, "en");
    expect(markup.match(/data-command-day="/g)).toHaveLength(11);
    expect(markup).toMatch(/aria-label="Go to 12 Sep" aria-current="true" data-command-day="12"/);
    expect(markup.match(/aria-current="true"/g)).toHaveLength(1);
    expect(timebar(130, "th")).toMatch(/aria-label="ไปยังวันที่ 14 ก.ย." aria-current="true" data-command-day="14"/);
  });

  it("prints the phase names in the band and hatches the track after the playhead", () => {
    const markup = timebar(84, "en");
    for (const phase of manifest.phases) expect(markup, phase.id).toContain(`data-phase="${phase.id}"`);
    for (const name of ["Dry / normal", "Onset", "Peak", "Receding", "Mostly receded"]) expect(markup).toContain(`>${name}<`);
    expect(markup).toMatch(/data-command-future="true"><span>not yet known at this hour<\/span>/);
    // The hatched part starts at the playhead: hour 84 of 264.
    expect(markup).toContain(`left:${((84 / 264) * 100).toFixed(3)}%`);
    expect(timebar(84, "th")).toContain(">ยังไม่ทราบ ณ ชั่วโมงนี้<");
    // The rain of the two gauges is observed, and labelled as such.
    expect(markup).toContain('aria-label="Rain per hour at two gauges (observed)"');
    expect(text(markup)).toContain("Rain mm/h · observed");
  });

  it("names the replay hour on the slider", () => {
    const markup = timebar(84, "en");
    expect(markup).toMatch(/<input type="range" class="[^"]*" min="0" max="264" step="1" aria-label="Replay hour" aria-valuetext="12 Sep 2024 · 12:00 ICT, hour 84 of 264" data-command-slider="true" value="84"\/>/);
  });

  it("stops at the ends: nothing is hatched at the last hour, and play starts again from the first", () => {
    const end = timebar(264, "en");
    expect(end).not.toContain("data-command-future");
    expect(end).toContain('aria-label="Play again from the first hour"');
    expect(end).toMatch(/disabled="" aria-label="Next event"/);
    expect(end).toMatch(/disabled="" aria-label="Forward one hour"/);
    const start = timebar(0, "en");
    expect(start).toMatch(/disabled="" aria-label="Previous event"/);
    expect(start).toMatch(/disabled="" aria-label="Back one hour"/);
  });

  it("is one line in focus mode and waits for the data", () => {
    expect(timebar(84, "en", { collapsed: true })).toContain('data-collapsed="true"');
    expect(text(timebar(84, "en", { collapsed: true }))).toContain("12 Sep 12:00 ICT");
    expect(timebar(84, "en", { disabled: true })).toMatch(/disabled="" aria-label="Play"/);
    for (const language of LANGUAGES) expect(lintOf(timebar(84, language), `timebar ${language}`)).toBe("");
  });
});

describe("Command keys", () => {
  it("steps the clock by one hour on an arrow key and by one day with Shift", () => {
    let state = initialCommandReplay(84);
    const press = (key: string, shiftKey = false) => {
      const action = commandKeyAction({ key, shiftKey });
      if (action?.type === "step") state = commandReplayReducer(state, action);
      if (action?.type === "event") state = commandReplayReducer(state, { ...action, stops });
      if (action?.type === "toggle_focus") state = commandReplayReducer(state, { type: "focus" });
    };
    press("ArrowRight");
    expect(text(situation(state.hour, "en"))).toContain("12 Sep 2024 · 13:00 ICT");
    press("ArrowLeft", true);
    expect(text(situation(state.hour, "en"))).toContain("11 Sep 2024 · 13:00 ICT");
    expect(text(situation(state.hour, "en"))).toContain("hour 61 of 264");
    press("]");
    expect(state.hour).toBe(84);
    press("[");
    expect(text(situation(state.hour, "en"))).toContain("11 Sep 2024 · 00:00 ICT");
    press("f");
    expect(text(situation(state.hour, "en", state.focus))).toContain("11 Sep 00:00 ICT · h 48");
  });
});

describe("Command navigation, tools and legend (regions C, E, G)", () => {
  const nav = (language: Language, hour = 84) =>
    html(<CommandNav language={language} hour={hour} menuOpen={false} onMenu={noop} onLanguage={noop} onHelp={noop} basemap="street" onBasemap={noop} />);

  it("links Public, this page and the Studio replay at the same replay hour", () => {
    const markup = nav("en");
    expect(markup).toContain('href="/public/"');
    expect(markup).toContain(`href="${COMMAND_EXERCISE_ROUTE}" aria-current="page"`);
    // The hour travels with the same t parameter; the Studio page is asked to count all residents, as this page does.
    expect(markup).toContain('href="/studio/cases/mae-sai-2024/?t=84&amp;pop=all&amp;lang=en"');
    expect(nav("th", 130)).toContain('href="/studio/cases/mae-sai-2024/?t=130&amp;pop=all&amp;lang=th"');
    for (const label of ["Public", "Command (exercise)", "Studio"]) expect(text(markup)).toContain(label);
    // The language button is named in the language it switches to.
    expect(markup).toMatch(/aria-label="Switch to Thai" data-command-language="th"><span lang="th">ไทย<\/span>/);
    expect(nav("th")).toMatch(/aria-label="เปลี่ยนเป็นภาษาอังกฤษ" data-command-language="en"><span lang="en">EN<\/span>/);
    expect(markup).toContain('aria-label="Help and keys"');
  });

  it("has seven round tools, the find-place box among them", () => {
    const rail = html(<CommandToolRail language="en" focus={false} basemap="street" nextFit="town" viewOpen={false} disabled={false} onView={noop} onBasemap={noop} onZoom={noop} onFit={noop} onFocus={noop} />);
    expect([...rail.matchAll(/data-command-tool="([a-z-]+)"/g)].map((match) => match[1])).toEqual(["view", "basemap", "zoom-in", "zoom-out", "fit", "find", "focus"]);
    expect(rail).toMatch(/aria-expanded="false" aria-label="Find a place"/);
    expect(rail).not.toMatch(/disabled=""[^>]*aria-label="Find a place"/);
    expect(rail).toContain('aria-label="Basemap: Grey street map"');
    expect(rail).toContain('aria-label="Show the town"');
    const next = html(<CommandToolRail language="en" focus basemap="terrain" nextFit="district" viewOpen disabled={false} onView={noop} onBasemap={noop} onZoom={noop} onFit={noop} onFocus={noop} />);
    expect(next).toContain('aria-label="Basemap: Terrain shading"');
    expect(next).toContain('aria-label="Show the whole district"');
    expect(next).toMatch(/aria-expanded="true" aria-label="Map view"/);
  });

  it("keeps the key facilities off until asked for, in the view popover", () => {
    const off = html(<CommandViewPopover language="en" facilities={false} facilityCount={42} onFacilities={noop} onClose={noop} />);
    expect(text(off)).toContain("Key facilities (42)");
    expect(off).toMatch(/<input type="checkbox" data-command-facilities="true"\/>/);
    expect(html(<CommandViewPopover language="en" facilities facilityCount={42} onFacilities={noop} onClose={noop} />)).toMatch(/<input type="checkbox" data-command-facilities="true" checked=""\/>/);
    // The Evidence view is named, and said to be not built yet.
    expect(text(off)).toContain("Not built yet: candidate sites and satellite images. The 2024 season envelope is drawn in hindsight mode.");
  });

  it("is a chip until opened, then a grid of what the map draws", () => {
    const chip = html(<CommandLegend language="en" open={false} onToggle={noop} facilities={false} unmodelledRoads={false} wetSites={false} />);
    expect(chip).toMatch(/^<button[^>]*aria-expanded="false"[^>]*data-command-legend="chip"/);
    expect(text(chip)).toBe("Legend");
    const open = html(<CommandLegend language="en" open onToggle={noop} facilities={false} unmodelledRoads={false} wetSites={false} />);
    expect(open).toContain('data-command-legend="open"');
    for (const entry of ["under 0.3 m", "0.3 m or more", "lowest confidence", "outside the district", "dry", "wet, under 0.3 m", "impassable", "shelter reported in 2024", "command centre (reported)", "subdistrict boundary"]) {
      expect(text(open), entry).toContain(entry);
    }
    expect(text(open)).toContain("Model, low confidence. Bridge decks and the current are not modelled.");
    // What the map does not draw is not in the legend: the r4 data has no road outside the model and no wet reported site.
    for (const absent of ["not modelled ", "shelter, wet in the model", "key facility"]) expect(text(open), absent).not.toContain(absent);
    const full = html(<CommandLegend language="en" open onToggle={noop} facilities unmodelledRoads wetSites />);
    for (const entry of ["shelter, wet in the model", "key facility", "facility in modelled water"]) expect(text(full)).toContain(entry);
    expect(text(html(<CommandLegend language="th" open onToggle={noop} facilities unmodelledRoads wetSites />))).toContain("ลึก 0.3 เมตรขึ้นไป");
  });
});

describe("Command information drawer", () => {
  it("lists the permitted use, the limits, the assumptions, the sources with their licences and the build date", () => {
    const markup = html(<CommandInfoBody language="en" manifest={manifest} />);
    const shown = text(markup);
    expect(shown).toContain("Permitted use");
    expect(shown).toContain("Not for emergency response, evacuation orders or any operational decision; not an official warning.");
    expect(shown).toContain("Limits (4)");
    expect(shown).toContain("Assumptions (26)");
    expect(shown).toContain("Sources and licences (10)");
    expect(markup.match(/<li>/g)!.length).toBeGreaterThanOrEqual(4 + 4 + 26 + 8);
    for (const source of manifest.sources) {
      expect(markup, source.id).toContain(`>${source.name.replace(/&/g, "&amp;")}<`);
      expect(shown, source.id).toContain(`Licence: ${source.licence}`);
    }
    expect(shown).toContain("Data r4 · built 3 Oct 2026 · sources 3–19 Sep 2024");
    // What the page is not, in the drawer's own words, with the official hotlines.
    for (const sentence of ["Not real-time.", "Not an official warning, and not a dispatch system.", "Not for operational decisions.", "Not a scored case."]) expect(shown).toContain(sentence);
    expect(shown).toContain("1784");
    expect(shown).toContain("Every modelled figure is low confidence.");
  });

  it("says that the Thai text was not reviewed by a native speaker, in both languages", () => {
    expect(text(html(<CommandInfoBody language="en" manifest={manifest} />))).toContain("The Thai text on this page was written by an AI assistant. It has not been reviewed by a native speaker.");
    const thai = text(html(<CommandInfoBody language="th" manifest={manifest} />));
    expect(thai).toContain("ข้อความภาษาไทยในหน้านี้เขียนโดยผู้ช่วย AI และยังไม่มีเจ้าของภาษาตรวจทาน");
    expect(thai).toContain("ข้อมูลชุด r4 · จัดทำเมื่อ 3 ต.ค. 2569 (2026) · แหล่งข้อมูลช่วง 3–19 ก.ย. 2567 (2024)");
    // A sentence of the replay data without a Thai rendering is shown in English, marked as the original: one mark each.
    const untranslated = [manifest.permitted_use!, ...manifest.limitations, ...manifest.assumptions].filter((sentence) => localizedText(sentence, "th").lang !== "th");
    expect(thai.split("ต้นฉบับภาษาอังกฤษ").length - 1).toBe(untranslated.length);
    // The limits and the permitted use of the replay data read in Thai.
    expect(localizedText(manifest.permitted_use!, "th").lang).toBe("th");
    expect(thai).toContain(localizedText(manifest.limitations[3], "th").text);
  });

  it("still states what the page is before the data has loaded", () => {
    const shown = text(html(<CommandInfoBody language="en" manifest={null} />));
    expect(shown).toContain("What this page is");
    expect(shown).toContain("It has not been reviewed by a native speaker.");
    expect(shown).not.toContain("Assumptions (");
  });
});

describe("Command panels: wording", () => {
  it("passes the shared wording lint in both languages", () => {
    for (const language of LANGUAGES) {
      const panels: [string, ReactElement][] = [
        ["drawer", <CommandInfoBody key="a" language={language} manifest={manifest} />],
        ["help", <CommandHelpSheet key="b" open={false} onClose={noop} onAbout={noop} language={language} />],
        ["nav", <CommandNav key="c" language={language} hour={84} menuOpen onMenu={noop} onLanguage={noop} onHelp={noop} basemap="street" onBasemap={noop} />],
        ["rail", <CommandToolRail key="d" language={language} focus={false} basemap="street" nextFit="town" viewOpen={false} disabled={false} onView={noop} onBasemap={noop} onZoom={noop} onFit={noop} onFocus={noop} />],
        ["view", <CommandViewPopover key="e" language={language} facilities facilityCount={42} onFacilities={noop} onClose={noop} />],
        ["legend", <CommandLegend key="f" language={language} open onToggle={noop} facilities unmodelledRoads wetSites />],
        ["credits", <CommandCredits key="g" language={language} view={{ metresPerPixel: 35.8, zoom: 12 }} revision="r4" />],
        ["notice", <CommandNotice key="h" language={language} message={language === "th" ? "โหลดแผนที่ถนนไม่ได้ จึงแสดงภูมิประเทศแบบแสงเงาแทน" : "Street map unavailable: showing terrain shading"} />],
      ];
      for (const [name, node] of panels) expect(lintOf(html(node), `${name} ${language}`), `${name} ${language}`).toBe("");
    }
  });

  it("prints the scale and the credits of the map", () => {
    const markup = html(<CommandCredits language="en" view={{ metresPerPixel: 35.8, zoom: 12 }} revision="r4" />);
    expect(text(markup)).toContain("2 km");
    expect(text(markup)).toContain("© OpenStreetMap contributors · Copernicus DEM © DLR, Airbus DS · data r4");
    expect(markup).toContain(`width:${Math.round(2000 / 35.8)}px`);
    expect(text(html(<CommandCredits language="th" view={{ metresPerPixel: 35.8, zoom: 12 }} revision="r4" />))).toContain("2 กม.");
  });
});
