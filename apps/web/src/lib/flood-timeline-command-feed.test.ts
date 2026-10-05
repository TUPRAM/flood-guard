/**
 * "Known by now" of the Command exercise replay, on the served r4 replay data: `knownBy(t)` never returns an item of a
 * later hour, each kind of row has the time the data gives it, the rows the data gives no time are hindsight only, and
 * the marks of the time track merge and follow the mode.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { formatLocalStamp, TIMELINE_EPOCH_MS, TIMELINE_MANIFEST_URL, type AreaGeometry, type GeoCollection, type RoadProps, type TambonProps, type TimelineManifest } from "./flood-timeline";
import { buildCommandModel } from "./flood-timeline-command";
import {
  buildCommandFeed,
  feedAt,
  feedDate,
  feedEventHours,
  feedEventMarks,
  feedMarkItems,
  groupFeedByDay,
  hindsightFeed,
  knownBy,
  markHalfWidthPx,
  MERGED_MARK_REACH_PX,
  modelPeakHour,
  placeRecordHorizon,
  placeRecordHour,
  placeRecordPlacesAt,
  placeRecordsAt,
  placeRecordTally,
  RADARSAT2_ACQUIRED_LOCAL,
  RADARSAT2_CHECK_ID,
  RAIN_DISPLAY_RULE_MM,
  rainRuleHours,
  reportedSiteDate,
  reportedSiteHour,
  reportedSitePendingAt,
  reportedSiteSourcesAt,
  type CommandFeedItem,
  type CommandFeedKind,
} from "./flood-timeline-command-feed";
import { parseAccessNodes } from "./flood-timeline-evacuation";
import { reportedDepthPlaces, reportedDepthPopup, shippableReportedDepths } from "./flood-timeline-reported-depths";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<unknown, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes: parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!) });
const feed = buildCommandFeed(manifest, model);
const ofKind = <K extends CommandFeedKind>(kind: K) => feed.filter((item): item is CommandFeedItem & { detail: Extract<CommandFeedItem["detail"], { kind: K }> } => item.detail.kind === kind);
const hourOf = (local: string) => (Date.parse(local) - TIMELINE_EPOCH_MS) / 3_600_000;

describe("knownBy(t)", () => {
  it("never returns an item of a later hour, at any replay hour", () => {
    for (let hour = 0; hour <= 264; hour += 1) {
      const known = knownBy(feed, hour);
      for (const item of known) {
        expect(item.fromHour, `${item.id} at hour ${hour}`).toBeLessThanOrEqual(hour);
        expect(item.hindsightOnly).toBe(false);
        // The time the data gives the item has come (a scene held at the start was taken before the replay).
        if (item.time !== null) expect(item.time, item.id).toBeLessThanOrEqual(hour);
        // A place record is listed only once its article has been published.
        if (item.detail.kind === "place_record") {
          for (const report of item.detail.reports) {
            const published = report.source.published;
            const instant = published.length === 10 ? Date.parse(`${published}T24:00:00+07:00`) : Date.parse(published);
            expect(instant, report.id).toBeLessThanOrEqual(TIMELINE_EPOCH_MS + hour * 3_600_000);
          }
        }
      }
      // Nothing that is known is left out either.
      expect(known.length).toBe(feed.filter((item) => !item.hindsightOnly && item.fromHour <= hour).length);
    }
  });

  it("lists newest first, grows with the replay hour and never holds an exercise item", () => {
    let before = -1;
    for (const hour of [0, 30, 36, 60, 84, 110, 200, 264]) {
      const known = knownBy(feed, hour);
      expect(known.length).toBeGreaterThanOrEqual(before);
      before = known.length;
      const times = known.map((item) => item.time ?? Infinity);
      expect(times).toEqual([...times].sort((a, b) => b - a));
      expect(known.some((item) => item.id.includes("EX-"))).toBe(false);
    }
    // At the start only the two scenes taken before the replay are held.
    expect(knownBy(feed, 0).map((item) => item.id).sort()).toEqual(["satellite:s1-20240906", "satellite:s2-20240905"]);
    expect(knownBy(feed, 264).length).toBe(feed.filter((item) => !item.hindsightOnly).length);
  });
});

describe("The rows of the list", () => {
  it("lists a place record at the publication of its article, one row per statement", () => {
    const records = ofKind("place_record");
    expect(records).toHaveLength(manifest.reported_depths!.counted.statements);
    expect(records.reduce((sum, item) => sum + item.detail.reports.length, 0)).toBe(manifest.reported_depths!.counted.place_records);
    for (const item of records) {
      expect(item.lane).toBe("reported");
      for (const report of item.detail.reports) expect(placeRecordHour(report).fromHour).toBe(item.fromHour);
    }
    // 10 Sep 05:32 is known from 06:00; an article with a date and no time counts from the end of that day.
    expect(records.find((item) => item.id === "record:ms-c2-01")).toMatchObject({ fromHour: 30, precision: "time" });
    expect(records.find((item) => item.id === "record:ms-c2-01")!.time).toBeCloseTo(29 + 32 / 60, 5);
    expect(records.find((item) => item.id === "record:ms-c2-20")).toMatchObject({ time: 72, fromHour: 72, precision: "day_end" });
    expect(records.filter((item) => item.precision === "day_end")).toHaveLength(2);
    // The statement PPTV made for three communities is one row with three places.
    expect(records.find((item) => item.id === "record:ms-c2-07")!.places.map((place) => place.en)).toEqual(["Ko Sai community", "Mai Lung Khon community", "Mueang Daeng community"]);
  });

  it("lists rain when an hour reaches the display rule after an hour under it", () => {
    expect(RAIN_DISPLAY_RULE_MM).toBe(10);
    expect(rainRuleHours([0, 12, 14, 3, 10, null, 11])).toEqual([1, 4, 6]);
    const rain = ofKind("rain");
    const hours = (code: string) => rain.filter((item) => item.detail.station.code === code).map((item) => item.fromHour);
    // MOU189 has 14 hours at 10 mm or more in 8 runs; DIWO has one. The value of hour i is known at hour i + 1.
    expect(hours("MOU189")).toEqual([22, 33, 35, 39, 57, 69, 103, 208]);
    expect(hours("DIWO")).toEqual([42]);
    expect(rain.every((item) => item.lane === "observed" && item.detail.mm >= RAIN_DISPLAY_RULE_MM)).toBe(true);
    expect(manifest.rainfall!.hourly_mm.MOU189.filter((value) => (value ?? 0) >= 10)).toHaveLength(14);
  });

  it("lists a satellite pass at its acquisition, holds the two earlier scenes at the start, and tags the pass the model was tuned to", () => {
    const passes = ofKind("satellite");
    expect(passes.map((item) => [item.id, item.fromHour, item.precision, item.lane])).toEqual([
      ["satellite:s2-20240905", 0, "held", "observed"],
      ["satellite:s1-20240906", 0, "held", "observed"],
      ["satellite:s2-20240915", 155, "time", "observed"],
      ["satellite:s1-20240915", 175, "time", "calibration"],
    ]);
    expect(passes[2].time).toBeCloseTo(hourOf("2024-09-15T10:58:15+07:00"), 6);
    expect(manifest.s1_anchor.role).toBe("calibration_informed_magnitude_check");
  });

  it("lists the VIIRS daily map as one line per day, from the hour after its 13:30 pass", () => {
    const days = ofKind("viirs");
    expect(days).toHaveLength(manifest.viirs_daily!.days.length);
    expect(days[0]).toMatchObject({ time: 37.5, fromHour: 38, lane: "observed" });
    expect(days.map((item) => Math.round(item.detail.cloudShare * 100))).toEqual([100, 100, 82, 69, 98, 4, 23, 34, 63]);
    expect(knownBy(feed, 37).some((item) => item.id === "viirs:2024-09-10")).toBe(false);
    expect(knownBy(feed, 38).some((item) => item.id === "viirs:2024-09-10")).toBe(true);
  });

  it("lists the RADARSAT-2 figure at its acquisition on 10 Sep 18:15, with the calibration tag", () => {
    const check = manifest.external_checks!.find((item) => item.id === RADARSAT2_CHECK_ID)!;
    // The data gives the time inside a sentence only: the constant is kept equal to it here.
    expect("observed" in check && check.observed).toContain("10 Sep 2024 18:15");
    expect(RADARSAT2_ACQUIRED_LOCAL).toBe("2024-09-10T18:15:00+07:00");
    const [row] = ofKind("radarsat");
    expect(row).toMatchObject({ lane: "calibration", time: 42.25, fromHour: 43, hindsightOnly: false });
    expect(row.detail.km2).toBe(9.9);
    expect("role" in check && check.role).toBe("calibration_anchor");
  });

  it("keeps UNOSAT 3991 and the season envelope for hindsight: the data gives them no time", () => {
    const hindsightOnly = feed.filter((item) => item.hindsightOnly).map((item) => item.id).sort();
    expect(hindsightOnly).toEqual(["agency:unosat-3991", "envelope:unosat-4009", "shelters:2024-09-21"]);
    for (const id of ["agency:unosat-3991", "envelope:unosat-4009"]) {
      const item = feed.find((entry) => entry.id === id)!;
      expect(item).toMatchObject({ time: null, precision: "none" });
      expect(knownBy(feed, 264).includes(item)).toBe(false);
      expect(hindsightFeed(feed).includes(item)).toBe(true);
    }
    expect(feedAt(feed, 30, "hindsight")).toHaveLength(feed.length);
    expect(feedAt(feed, 30, "trainee")).toEqual(knownBy(feed, 30));
    const envelope = ofKind("season_envelope")[0];
    expect(envelope.lane).toBe("scenario");
    expect(envelope.detail.credit).toBe("UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009");
    expect(envelope.detail.sentence).toContain("FloodGuard did not validate it.");
  });

  it("lists the shelters reported in use on the day of their first dated 2024 source", () => {
    const sites = manifest.shelters!.reported;
    const site = (id: string) => sites.find((item) => item.id === id)!;
    // An exact first-use date is used as it is; a bound ("… or earlier") gives way to the first source dated in 2024.
    expect(reportedSiteDate(site("R05"))).toBe("2024-09-11");
    expect(reportedSiteDate(site("R01"))).toBe("2024-09-11");
    expect(reportedSiteDate(site("R06"))).toBe("2024-09-16");
    expect(reportedSiteDate(site("R19"))).toBe("2024-09-14");
    expect(reportedSiteDate(site("R04"))).toBe("2024-09-21");
    expect(reportedSiteDate({ first_use: "2024-09-15 or earlier", sources: [{ title: "", publisher: "", date: "accessed 2026-09-27", url: "", quote_or_paraphrase: "" }] })).toBeNull();
    expect(reportedSiteHour(site("R05"))).toBe(48);
    expect(reportedSiteHour(site("R04"))).toBe(288);
    const rows = ofKind("shelters");
    expect(rows.map((item) => [item.detail.date, item.detail.shelters, item.detail.commandCentres, item.fromHour])).toEqual([
      ["2024-09-11", 2, 1, 48],
      ["2024-09-14", 1, 0, 120],
      ["2024-09-16", 14, 0, 168],
      ["2024-09-21", 1, 0, 288],
    ]);
    expect(rows.reduce((sum, item) => sum + item.places.length, 0)).toBe(sites.length);
    expect(rows.every((item) => item.lane === "reported" && item.precision === "day")).toBe(true);
  });

  it("lists the events of the model at the hour they occur in it, tagged model", () => {
    expect(ofKind("model_phase").map((item) => [item.detail.phaseId, item.fromHour])).toEqual([["onset", 24], ["peak", 48], ["receding", 96], ["gone", 168]]);
    expect(ofKind("model_peak")[0]).toMatchObject({ fromHour: 84, lane: "model" });
    const losses = ofKind("model_first_loss");
    // Every row is zero up to and including hour 43; four subdistricts reach ten residents or more.
    expect(losses.every((item) => item.fromHour > 43 && item.detail.lostAccess >= 10 && item.lane === "model")).toBe(true);
    expect(losses.map((item) => item.detail.tambon.en).sort()).toEqual(["Ko Chang", "Mae Sai", "Pong Pha", "Si Mueang Chum"]);
    expect(feed.filter((item) => item.lane === "model").every((item) => item.id.startsWith("model:"))).toBe(true);
  });

  it("groups rows by the local day, with the start of the replay and the whole event as groups of their own", () => {
    expect(feedDate(0)).toBe("2024-09-09");
    expect(feedDate(37.5)).toBe("2024-09-10");
    expect(feedDate(264)).toBe("2024-09-19");
    const groups = groupFeedByDay(hindsightFeed(feed));
    expect(groups[0].key).toBe("event");
    expect(groups[1].key).toBe("after");
    expect(groups[groups.length - 1].key).toBe("start");
    expect(groups.reduce((sum, group) => sum + group.items.length, 0)).toBe(feed.length);
    const known = groupFeedByDay(knownBy(feed, 84));
    expect(known[0].key).toBe("2024-09-12");
    expect(known.map((group) => group.key)).toEqual(["2024-09-12", "2024-09-11", "2024-09-10", "2024-09-09", "start"]);
  });
});

describe("Event marks of the time track", () => {
  it("marks every row with a time inside the replay: filled for observed or reported, hollow for the model", () => {
    const marked = feedMarkItems(feed);
    expect(marked.some((item) => item.precision === "held" || item.hindsightOnly)).toBe(false);
    const marks = feedEventMarks(feed, 1000, { minGapPx: 0 });
    expect(marks.reduce((sum, mark) => sum + mark.count, 0)).toBe(marked.length);
    const peak = marks.find((mark) => mark.firstHour === 84)!;
    expect(peak).toMatchObject({ filled: false, count: 1 });
    expect(marks.find((mark) => mark.firstHour === 43)).toMatchObject({ filled: true });
  });

  it("merges marks closer than 6 px into one with a count, and hides the marks after the replay hour in trainee mode", () => {
    const wide = feedEventMarks(feed, 4);
    const narrow = feedEventMarks(feed, 2.4);
    expect(narrow.length).toBeLessThan(wide.length);
    for (const marks of [wide, narrow]) {
      expect(marks.reduce((sum, mark) => sum + mark.count, 0)).toBe(feedMarkItems(feed).length);
      expect(marks.some((mark) => mark.count > 1)).toBe(true);
    }
    for (let index = 1; index < wide.length; index += 1) expect((wide[index].firstHour - wide[index - 1].firstHour) * 4).toBeGreaterThanOrEqual(6);
    const upTo = feedEventMarks(feed, 4, { upTo: 60 });
    expect(upTo.every((mark) => mark.firstHour <= 60)).toBe(true);
    expect(upTo.reduce((sum, mark) => sum + mark.count, 0)).toBe(feedMarkItems(feed).filter((item) => item.fromHour <= 60).length);
    // A merged mark is filled as soon as it holds an observed or reported row.
    expect(feedEventMarks([feed.find((item) => item.id === "model:peak")!, { ...feed.find((item) => item.id === "viirs:2024-09-12")!, fromHour: 85 }], 4)).toEqual([{ hour: 84.5, firstHour: 84, filled: true, count: 2 }]);
  });

  it("gives the event buttons the start, every marked hour and the end", () => {
    const hours = feedEventHours(feed);
    expect(hours[0]).toBe(0);
    expect(hours[hours.length - 1]).toBe(264);
    expect(hours).toEqual([...new Set(hours)].sort((a, b) => a - b));
    for (const hour of [24, 30, 43, 48, 84, 155, 175]) expect(hours).toContain(hour);
  });
});

describe("Place records known by now", () => {
  const reports = manifest.reported_depths!.reports;
  it("are those published by the replay hour in trainee mode, and all of them in hindsight", () => {
    expect(placeRecordsAt(reports, 29, "trainee")).toEqual([]);
    expect(placeRecordsAt(reports, 30, "trainee").map((report) => report.id)).toEqual(["ms-c2-01"]);
    expect(placeRecordsAt(reports, 60, "trainee").length).toBeLessThan(reports.length);
    expect(placeRecordsAt(reports, 264, "trainee")).toHaveLength(21);
    expect(placeRecordsAt(reports, 0, "hindsight")).toHaveLength(21);
  });

  it("count how the model reads at their points: 12 with a point, consistent with 1, wet at 2 and dry at 9", () => {
    const counts = manifest.reported_depths!.counts.all;
    expect(placeRecordTally(reports)).toEqual({ located: 12, consistent: counts.consistent, wet: counts.model_wet, dry: counts.model_dry, other: 0 });
    expect(placeRecordTally(reports)).toMatchObject({ consistent: 1, wet: 2, dry: 9 });
    expect(placeRecordTally(placeRecordsAt(reports, 36, "trainee"))).toEqual({ located: 5, consistent: 0, wet: 0, dry: 5, other: 0 });
    expect(placeRecordTally([])).toEqual({ located: 0, consistent: 0, wet: 0, dry: 0, other: 0 });
  });
});

describe("Marks of the time track: none touches another", () => {
  it("measures between the places the marks are drawn at, and gives a count pill its width", () => {
    expect([markHalfWidthPx(1), markHalfWidthPx(2), markHalfWidthPx(9), markHalfWidthPx(10)]).toEqual([3.5, 7.5, 7.5, 9.5]);
    expect(MERGED_MARK_REACH_PX).toBe(17);
    for (const pxPerHour of [1.6, 2.4, 3.56, 4, 6]) {
      for (const upTo of [30, 60, 84, 130, 264]) {
        const marks = feedEventMarks(feed, pxPerHour, { upTo });
        expect(marks.reduce((sum, mark) => sum + mark.count, 0)).toBe(feedMarkItems(feed).filter((item) => item.fromHour <= upTo).length);
        for (let index = 1; index < marks.length; index += 1) {
          const gap = (marks[index].hour - marks[index - 1].hour) * pxPerHour;
          // Two pills with a count keep 2 px clear; a dot beside a pill too; two dots may touch at 6 px.
          const pill = marks[index].count > 1 || marks[index - 1].count > 1;
          expect(gap, `${pxPerHour} px/h up to ${upTo}, mark ${index}`).toBeGreaterThanOrEqual(pill ? markHalfWidthPx(marks[index].count) + markHalfWidthPx(marks[index - 1].count) + 2 : 6);
        }
      }
    }
  });

  it("only reworks the last marks as the replay hour moves on, so the marks behind it stay where they are", () => {
    const pxPerHour = 3.56;
    for (let hour = 31; hour <= 200; hour += 1) {
      const before = feedEventMarks(feed, pxPerHour, { upTo: hour - 1 });
      const now = feedEventMarks(feed, pxPerHour, { upTo: hour });
      // Every mark but the last three of the hour before is drawn again exactly as it was.
      const steady = before.slice(0, Math.max(0, before.length - 3));
      expect(now.slice(0, steady.length), `hour ${hour}`).toEqual(steady);
    }
  });
});

describe("What the map shows of the reports at a replay hour", () => {
  const block = shippableReportedDepths(manifest)!;
  const reports = block.reports;
  const places = reportedDepthPlaces(block);
  const sites = manifest.shelters!.reported;
  const peakHour = modelPeakHour(model.stages);
  const shownIds = (hour: number, mode: "trainee" | "hindsight") => placeRecordPlacesAt(places, hour, mode).flatMap((place) => place.reports.map((report) => report.id)).sort();

  it("puts a bubble on the map only for the place records published by the replay hour in trainee mode", () => {
    expect(placeRecordPlacesAt(places, 20, "trainee")).toEqual([]);
    for (const hour of [20, 31, 36, 60, 84, 107, 108, 130, 264]) {
      const located = placeRecordsAt(reports, hour, "trainee").filter((report) => report.point !== null).map((report) => report.id).sort();
      expect(shownIds(hour, "trainee"), `hour ${hour}`).toEqual(located);
      for (const place of placeRecordPlacesAt(places, hour, "trainee")) expect(place.reports.length).toBeGreaterThan(0);
    }
    // The record of the article of 13 Sep 11:32 (Piyaphon village) is on the map from replay hour 108, not before.
    expect(shownIds(107, "trainee")).not.toContain("ms-c2-22");
    expect(shownIds(108, "trainee")).toContain("ms-c2-22");
    // Hindsight shows every located record at every hour.
    expect(shownIds(0, "hindsight")).toEqual(reports.filter((report) => report.point !== null).map((report) => report.id).sort());
  });

  it("holds the modelled peak and a later first-wet time back in the popup of a place record", () => {
    expect(peakHour).toBe(84);
    expect(modelPeakHour([])).toBeNull();
    expect(modelPeakHour([0, 0])).toBeNull();
    expect(modelPeakHour([0, 1, 3, 3, 2])).toBe(2);
    expect(placeRecordHorizon(36, "hindsight", peakHour)).toBeNull();
    expect(placeRecordHorizon(36, "trainee", peakHour)).toEqual({ atMs: TIMELINE_EPOCH_MS + 36 * 3_600_000, peakReached: false });
    expect(placeRecordHorizon(83, "trainee", peakHour)?.peakReached).toBe(false);
    expect(placeRecordHorizon(84, "trainee", peakHour)?.peakReached).toBe(true);
    expect(placeRecordHorizon(84, "trainee", null)?.peakReached).toBe(false);
    // Ko Sai: first wet in the model on 10 Sep 19:00 (replay hour 43), 3.34 m at the modelled peak.
    const koSai = reports.find((report) => report.id === "ms-c2-07")!;
    expect(hourOf(koSai.model!.first_wet!)).toBe(43);
    for (const language of ["en", "th"] as const) {
      const lines = (hour: number | null) => reportedDepthPopup(koSai, block, language, hour === null ? undefined : placeRecordHorizon(hour, "trainee", peakHour) ?? undefined).lines.map((line) => line.text).join("\n");
      const peakWords = language === "th" ? "ที่ระดับสูงสุดของแบบจำลอง" : "At the modelled peak";
      const firstWet = formatLocalStamp(koSai.model!.first_wet!, language);
      // At 10 Sep 12:00 (hour 36) the popup names neither the depth at the peak nor the hour the point floods.
      expect(lines(36)).not.toContain(peakWords);
      expect(lines(36)).not.toContain("3.34");
      expect(lines(36)).not.toContain(firstWet);
      expect(lines(36)).toContain(language === "th" ? "จุดนี้สูงจากร่องน้ำ" : "The point is");
      // At hour 60 the point has been wet since hour 43: that time has passed and is told; the peak is still to come.
      expect(lines(60)).toContain(firstWet);
      expect(lines(60)).not.toContain(peakWords);
      expect(lines(60)).not.toContain("3.34");
      // From the peak hour on, and in hindsight, the popup is the replay's own.
      expect(lines(84)).toContain(peakWords);
      expect(lines(84)).toContain("3.34");
      expect(lines(84)).toBe(lines(null));
    }
    // For every located record and every hour from its publication to the hour before the peak: no later fact.
    for (const report of reports) {
      if (!report.model) continue;
      for (let hour = placeRecordHour(report).fromHour; hour < peakHour!; hour += 1) {
        const text = reportedDepthPopup(report, block, "en", placeRecordHorizon(hour, "trainee", peakHour)!).lines.map((line) => line.text).join("\n");
        expect(text, `${report.id} at hour ${hour}`).not.toContain("At the modelled peak");
        expect(text).not.toContain("never wet in the model");
        if (report.model.first_wet && hourOf(report.model.first_wet) > hour) expect(text, `${report.id} at hour ${hour}`).not.toContain(formatLocalStamp(report.model.first_wet, "en"));
        // The window the report describes ended before its article was published, so its line never names a later time.
        expect(hourOf(report.model.window_max_at)).toBeLessThanOrEqual(hour);
      }
    }
  });

  it("draws a reported site as not yet reported before its day, in trainee mode only", () => {
    const centre = sites.find((site) => site.id === "R05")!;
    expect(reportedSiteHour(centre)).toBe(48);
    expect(reportedSitePendingAt(centre, 47, "trainee")).toBe(true);
    expect(reportedSitePendingAt(centre, 48, "trainee")).toBe(false);
    expect(reportedSitePendingAt(centre, 0, "hindsight")).toBe(false);
    for (const hour of [20, 60, 84, 130]) {
      for (const site of sites) {
        const from = reportedSiteHour(site);
        expect(reportedSitePendingAt(site, hour, "trainee"), `${site.id} at ${hour}`).toBe(from !== null && hour < from);
        expect(reportedSitePendingAt(site, hour, "hindsight")).toBe(false);
      }
    }
    // At 9 Sep 20:00 every dated site is still to come; at 14 Sep 10:00 the two shelters of 11 Sep and the command centre are known.
    expect(sites.filter((site) => !reportedSitePendingAt(site, 20, "trainee") && reportedSiteHour(site) !== null)).toEqual([]);
    expect(sites.filter((site) => !reportedSitePendingAt(site, 130, "trainee")).length).toBeLessThan(sites.length);
  });

  it("lists in the popup of a site only the sources dated by the replay day, in trainee mode only", () => {
    for (const hour of [20, 60, 84, 130, 264]) {
      const today = feedDate(hour);
      for (const site of sites) {
        const listed = reportedSiteSourcesAt(site.sources, hour, "trainee");
        for (const source of listed) expect(source.date <= today, `${site.id} ${source.date} at ${hour}`).toBe(true);
        expect(listed).toEqual(site.sources.filter((source) => /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(source.date) && source.date <= today));
        expect(reportedSiteSourcesAt(site.sources, hour, "hindsight")).toEqual(site.sources);
      }
    }
    // A source without a plain date ("accessed 2026-...") is a later fact in trainee mode.
    expect(reportedSiteSourcesAt([{ date: "accessed 2026-10-01" }, { date: "2024-09-11" }, { date: "2024-09-16" }], 84, "trainee")).toEqual([{ date: "2024-09-11" }]);
  });
});
