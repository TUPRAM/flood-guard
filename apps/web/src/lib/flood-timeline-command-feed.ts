/**
 * "Known by now" of the Command exercise replay (Mae Sai, September 2024): what had been reported or observed by a
 * replay hour, what is only model, and what is missing. One pure function, `knownBy`, over the replay data.
 *
 * Every item has the time the replay data gives it, and is listed from the first whole replay hour at or after that
 * time, so the list never holds an item of a later hour:
 *   - a place record from news, at the time its article was published (an article with a date and no time counts from
 *     the end of that day);
 *   - rain at a gauge, when an hour reaches the display rule of 10 mm (a rule for this list, not a hazard level);
 *   - a satellite pass at its acquisition time. It would have reached responders later, and the list says so. The two
 *     scenes taken before the replay starts are held at the start;
 *   - the VIIRS daily map at its nominal 13:30 pass, as one line with the share of the district under cloud;
 *   - the RADARSAT-2 figure of GISTDA at its acquisition time, with the calibration tag: it was used to set the model;
 *   - shelters reported in use, on the day of their first dated 2024 source (day precision: the hour is not known);
 *   - events of the model at the hour they occur in it, tagged model.
 * UNOSAT product 3991 and the 2024 season envelope cover a span of days and have no time in the data: they are listed
 * in hindsight only. No DOM access in this module.
 */

import {
  tFromDate,
  tFromLocalDate,
  type RainStation,
  type ReportedDepthReport,
  type ReportedShelter,
  type TimelineManifest,
  type TimelineObservation,
} from "./flood-timeline";
import { clampCommandHour, COMMAND_LAST_HOUR, type CommandModel, type CommandShelterSet, type CommandTambon } from "./flood-timeline-command";
import { accessSnapshot, reportedSiteRole } from "./flood-timeline-evacuation";

/** What the exercise shows of the future: nothing (trainee, the default), or everything (hindsight). */
export type CommandMode = "trainee" | "hindsight";
export const COMMAND_MODES: readonly CommandMode[] = ["trainee", "hindsight"];
export const DEFAULT_COMMAND_MODE: CommandMode = "trainee";

/** The evidence lane of a row, as its tag names it. */
export type CommandFeedLane = "model" | "observed" | "reported" | "calibration" | "scenario";

/** A place a row names. A place with a point can be shown on the map. */
export interface CommandFeedPlace {
  th: string;
  en: string;
  lat: number | null;
  lon: number | null;
  /** The stated tolerance of a place record (m). */
  toleranceM: number | null;
  /** The reported site behind the place, when it is one. */
  siteId: string | null;
}

export type CommandFeedDetail =
  | { kind: "place_record"; reports: ReportedDepthReport[] }
  | { kind: "rain"; station: RainStation; mm: number }
  | { kind: "satellite"; observation: TimelineObservation; preEvent: boolean; calibration: boolean }
  | { kind: "viirs"; date: string; cloudShare: number }
  | { kind: "radarsat"; km2: number; reportedText: string }
  | { kind: "unosat_3991"; km2: number; reportedText: string }
  | { kind: "season_envelope"; credit: string; sentence: string }
  | { kind: "shelters"; date: string; shelters: number; commandCentres: number }
  | { kind: "model_phase"; phaseId: string; label: { en: string; th: string } }
  | { kind: "model_peak"; stage: number }
  | { kind: "model_first_loss"; tambon: CommandTambon; lostAccess: number };

export type CommandFeedKind = CommandFeedDetail["kind"];

/** How exactly the time of an item is known. */
export type CommandFeedPrecision =
  /** A time to the minute, or to the hour. */
  | "time"
  /** A date only, counted from the start of that day (shelters: "reported by that day"). */
  | "day"
  /** A date only, counted from the end of that day (a news article without a time). */
  | "day_end"
  /** Taken before the replay starts: held at the start. */
  | "held"
  /** No time in the data: hindsight only. */
  | "none";

export interface CommandFeedItem {
  id: string;
  lane: CommandFeedLane;
  /** Hours since 9 Sep 00:00 ICT, fractions included (13:30 on 10 Sep is 37.5); null when the data holds no time. */
  time: number | null;
  /** The first whole replay hour at which the item is known. Never before `time`. */
  fromHour: number;
  precision: CommandFeedPrecision;
  /** Shown in hindsight mode only. */
  hindsightOnly: boolean;
  places: CommandFeedPlace[];
  /** Where a reader can check the item. */
  source: { href: string; publisher: string } | null;
  detail: CommandFeedDetail;
}

/**
 * When GISTDA's RADARSAT-2 scene of the Mae Sai flood was acquired. The replay data gives the time only inside the
 * text of the external check ("… 10 Sep 2024 18:15 (time zone not stated; assumed ICT)"); a test keeps this constant
 * equal to that text.
 */
export const RADARSAT2_ACQUIRED_LOCAL = "2024-09-10T18:15:00+07:00";
export const RADARSAT2_CHECK_ID = "gistda-radarsat2-20240910";
export const UNOSAT_3991_CHECK_ID = "unosat-3991";

/** The display rule of the rain rows: an hour with this much rain or more is listed when the hour before had less. */
export const RAIN_DISPLAY_RULE_MM = 10;

/** A subdistrict's first loss of shelter access is listed from this many residents on (the table then prints "~10"). */
export const FIRST_LOSS_RESIDENTS = 10;

const hoursOf = (instant: string): number => tFromDate(instant) * 24;
/** The first whole hour at or after a time; a hair of floating-point noise does not push it to the next hour. */
const wholeHourFrom = (time: number): number => Math.max(0, Math.ceil(time - 1e-9));

/** The replay hour from which a place record is known in trainee mode: its publication, or the end of a day without a time. */
export function placeRecordHour(report: Pick<ReportedDepthReport, "source">): { time: number; fromHour: number; precision: CommandFeedPrecision } {
  const { published } = report.source;
  if (/^\d{4}-\d{2}-\d{2}$/.test(published)) {
    const end = (tFromLocalDate(published) + 1) * 24;
    return { time: end, fromHour: wholeHourFrom(end), precision: "day_end" };
  }
  const time = hoursOf(published);
  return { time, fromHour: wholeHourFrom(time), precision: "time" };
}

/**
 * The day from which a reported site counts as reported: its first use when the data gives an exact date, otherwise
 * its first source dated in 2024. A source that was only looked up later ("accessed 2026-…") is not a 2024 report.
 * Null when the data holds neither.
 */
export function reportedSiteDate(site: Pick<ReportedShelter, "first_use" | "sources">): string | null {
  if (/^\d{4}-\d{2}-\d{2}$/.test(site.first_use)) return site.first_use;
  const dates = site.sources.map((source) => source.date).filter((date) => /^2024-\d{2}-\d{2}$/.test(date)).sort();
  return dates[0] ?? null;
}

/** The replay hour from which a reported site is known in trainee mode (the start of its day), or null without a date. */
export function reportedSiteHour(site: Pick<ReportedShelter, "first_use" | "sources">): number | null {
  const date = reportedSiteDate(site);
  return date === null ? null : Math.round(tFromLocalDate(date) * 24);
}

/** The hours at which a gauge reaches the display rule after an hour under it; index 0 is 9 Sep 00:00–01:00. */
export function rainRuleHours(series: readonly (number | null)[], rule: number = RAIN_DISPLAY_RULE_MM): number[] {
  const hours: number[] = [];
  series.forEach((value, index) => {
    const before = index > 0 ? series[index - 1] ?? 0 : 0;
    if ((value ?? 0) >= rule && before < rule) hours.push(index);
  });
  return hours;
}

/**
 * Every row of the list for the whole replay, in the order of their times. `knownBy` then cuts it at a replay hour.
 * The model rows follow the shelter set the table counts.
 */
export function buildCommandFeed(manifest: TimelineManifest, model: Pick<CommandModel, "stages" | "tambons" | "sets" | "levels">, set: CommandShelterSet = "reported"): CommandFeedItem[] {
  const items: CommandFeedItem[] = [];

  // --- Place records from news: one row per statement, at the time its article was published.
  const statements = new Map<string, ReportedDepthReport[]>();
  for (const report of manifest.reported_depths?.reports ?? []) statements.set(report.statement_id, [...(statements.get(report.statement_id) ?? []), report]);
  for (const [statementId, reports] of statements) {
    const when = placeRecordHour(reports[0]);
    items.push({
      id: `record:${statementId}`,
      lane: "reported",
      ...when,
      hindsightOnly: false,
      places: reports.map((report) => ({
        th: report.place.th, en: report.place.en, lat: report.point?.lat ?? null, lon: report.point?.lon ?? null, toleranceM: report.location_tolerance_m, siteId: null,
      })),
      source: { href: reports[0].source.url, publisher: reports[0].source.publisher },
      detail: { kind: "place_record", reports },
    });
  }

  // --- Rain: an hour that reaches the display rule. The value of hour i (i:00 to i+1:00) is known at hour i + 1.
  for (const station of manifest.rainfall?.stations ?? []) {
    const series = manifest.rainfall?.hourly_mm[station.code] ?? [];
    for (const index of rainRuleHours(series)) {
      items.push({
        id: `rain:${station.code}:${index}`,
        lane: "observed",
        time: index + 1,
        fromHour: index + 1,
        precision: "time",
        hindsightOnly: false,
        places: [{ th: station.name_th, en: station.name_en, lat: station.lat, lon: station.lon, toleranceM: null, siteId: null }],
        source: manifest.rainfall ? { href: manifest.rainfall.source_url, publisher: "HII ThaiWater" } : null,
        detail: { kind: "rain", station, mm: series[index] ?? 0 },
      });
    }
  }

  // --- Satellite passes, at acquisition. The pass the model was tuned to carries the calibration tag.
  const tuned = Boolean(manifest.s1_anchor?.role?.startsWith("calibration"));
  const lastRadar = [...manifest.observations].reverse().find((observation) => observation.kind === "radar");
  for (const observation of manifest.observations) {
    const time = hoursOf(observation.local);
    const preEvent = time < 0;
    // The radar pass the recession keyframes were tuned to is the last radar scene of the replay.
    const calibration = tuned && !preEvent && observation === lastRadar;
    items.push({
      id: `satellite:${observation.id}`,
      lane: calibration ? "calibration" : "observed",
      time,
      fromHour: preEvent ? 0 : wholeHourFrom(time),
      precision: preEvent ? "held" : "time",
      hindsightOnly: false,
      places: [],
      source: null,
      detail: { kind: "satellite", observation, preEvent, calibration },
    });
  }

  // --- VIIRS daily maps: one line each with the cloud share. No VIIRS map is drawn on this page.
  for (const day of manifest.viirs_daily?.days ?? []) {
    const time = hoursOf(day.nominal_local_time);
    items.push({
      id: `viirs:${day.date}`,
      lane: "observed",
      time,
      fromHour: wholeHourFrom(time),
      precision: "time",
      hindsightOnly: false,
      places: [],
      source: manifest.viirs_daily ? { href: manifest.viirs_daily.source_url, publisher: "NOAA/GMU VIIRS" } : null,
      detail: { kind: "viirs", date: day.date, cloudShare: day.cloud_share },
    });
  }

  // --- Agency figures. RADARSAT-2: at acquisition, used to set the model. UNOSAT 3991: a cumulative product, hindsight only.
  for (const check of manifest.external_checks ?? []) {
    if (!("reported_km2" in check)) continue;
    if (check.id === RADARSAT2_CHECK_ID) {
      const time = hoursOf(RADARSAT2_ACQUIRED_LOCAL);
      items.push({
        id: `agency:${check.id}`, lane: "calibration", time, fromHour: wholeHourFrom(time), precision: "time", hindsightOnly: false, places: [],
        source: check.urls[0] ? { href: check.urls[0], publisher: "GISTDA" } : null,
        detail: { kind: "radarsat", km2: check.reported_km2, reportedText: check.reported_text },
      });
    } else if (check.id === UNOSAT_3991_CHECK_ID) {
      items.push({
        id: `agency:${check.id}`, lane: "calibration", time: null, fromHour: COMMAND_LAST_HOUR, precision: "none", hindsightOnly: true, places: [],
        source: check.urls[0] ? { href: check.urls[0], publisher: "UNOSAT" } : null,
        detail: { kind: "unosat_3991", km2: check.reported_km2, reportedText: check.reported_text },
      });
    }
  }

  // --- The 2024 season envelope: a scenario layer with no date per patch, hindsight only.
  const envelope = manifest.season_envelope;
  if (envelope?.shown) {
    items.push({
      id: "envelope:unosat-4009", lane: "scenario", time: null, fromHour: COMMAND_LAST_HOUR, precision: "none", hindsightOnly: true, places: [],
      source: envelope.urls?.[0] ? { href: envelope.urls[0], publisher: "UNOSAT" } : null,
      detail: { kind: "season_envelope", credit: envelope.credit, sentence: envelope.standard_sentence },
    });
  }

  // --- Shelters reported in use: one row per day, with the sites first reported that day.
  const byDate = new Map<string, ReportedShelter[]>();
  for (const site of manifest.shelters?.reported ?? []) {
    const date = reportedSiteDate(site);
    if (date) byDate.set(date, [...(byDate.get(date) ?? []), site]);
  }
  for (const [date, sites] of byDate) {
    const time = Math.round(tFromLocalDate(date) * 24);
    const commandCentres = sites.filter((site) => reportedSiteRole(site).role === "relief_command").length;
    items.push({
      id: `shelters:${date}`,
      lane: "reported",
      time,
      fromHour: Math.max(0, time),
      precision: "day",
      // A site first used after the replay ends is part of the record, and of no replay hour.
      hindsightOnly: time > COMMAND_LAST_HOUR,
      places: sites.map((site) => ({ th: site.name_th, en: site.name_en, lat: site.lat, lon: site.lon, toleranceM: null, siteId: site.id })),
      source: sites[0].sources[0] ? { href: sites[0].sources[0].url, publisher: sites[0].sources[0].publisher } : null,
      detail: { kind: "shelters", date, shelters: sites.length - commandCentres, commandCentres },
    });
  }

  // --- Events of the model: the first hour of each later phase, the highest assumed stage, and the first hour a
  // subdistrict shows residents who lost shelter access.
  for (const phase of manifest.phases) {
    const hour = clampCommandHour(tFromLocalDate(phase.start) * 24);
    if (hour <= 0 || hour >= COMMAND_LAST_HOUR) continue;
    items.push({ id: `model:phase:${phase.id}`, lane: "model", time: hour, fromHour: hour, precision: "time", hindsightOnly: false, places: [], source: null, detail: { kind: "model_phase", phaseId: phase.id, label: phase.label } });
  }
  let peak = 0;
  for (let hour = 1; hour < model.stages.length; hour += 1) if (model.stages[hour] > model.stages[peak]) peak = hour;
  if (model.stages.length > 0 && model.stages[peak] > 0) {
    items.push({ id: "model:peak", lane: "model", time: peak, fromHour: peak, precision: "time", hindsightOnly: false, places: [], source: null, detail: { kind: "model_peak", stage: model.stages[peak] } });
  }
  const pending = new Set(model.tambons.map((_, index) => index));
  for (let hour = 0; hour < model.stages.length && pending.size > 0; hour += 1) {
    const lost = accessSnapshot(model.sets[set].summary, model.stages[hour], model.levels).lostByTambon;
    for (const index of [...pending]) {
      if (!((lost[index] ?? 0) >= FIRST_LOSS_RESIDENTS)) continue;
      pending.delete(index);
      const tambon = model.tambons[index];
      items.push({ id: `model:first-loss:${tambon.id}`, lane: "model", time: hour, fromHour: hour, precision: "time", hindsightOnly: false, places: [], source: null, detail: { kind: "model_first_loss", tambon, lostAccess: lost[index] } });
    }
  }

  return items.sort(byTime);
}

/** Earlier first; an item without a time after all others; ties keep the order they were built in. */
function byTime(a: CommandFeedItem, b: CommandFeedItem): number {
  return (a.time ?? Infinity) - (b.time ?? Infinity) || a.fromHour - b.fromHour;
}

/**
 * What is known by replay hour `t`, newest first: every row whose time has come, and none of a later hour. Rows that
 * have no time in the data (hindsight only) are never in it.
 */
export function knownBy(feed: readonly CommandFeedItem[], t: number): CommandFeedItem[] {
  const at = clampCommandHour(t);
  return feed.filter((item) => !item.hindsightOnly && item.fromHour <= at).reverse();
}

/** Everything, newest first, for hindsight mode: the rows of every replay hour, and the rows the data gives no time. */
export function hindsightFeed(feed: readonly CommandFeedItem[]): CommandFeedItem[] {
  return [...feed].reverse();
}

/** The rows a mode shows at a replay hour. */
export function feedAt(feed: readonly CommandFeedItem[], hour: number, mode: CommandMode): CommandFeedItem[] {
  return mode === "hindsight" ? hindsightFeed(feed) : knownBy(feed, hour);
}

/** A group of rows under one heading: a local day of the replay, the start of the replay, or the whole event. */
export interface CommandFeedGroup {
  /** "2024-09-12", "start" (held at the start) or "event" (no time in the data). */
  key: string;
  items: CommandFeedItem[];
}

/** The local day (ICT) a time falls in; 24:00 of the last day stays on that day. */
export function feedDate(time: number): string {
  const day = Math.floor(Math.min(time, COMMAND_LAST_HOUR - 1e-6) / 24);
  return new Date(Date.UTC(2024, 8, 9 + day)).toISOString().slice(0, 10);
}

/** Rows grouped by day, in the order given (newest first for the list). */
export function groupFeedByDay(items: readonly CommandFeedItem[]): CommandFeedGroup[] {
  const groups: CommandFeedGroup[] = [];
  for (const item of items) {
    const key = item.time === null ? "event" : item.precision === "held" ? "start" : item.time > COMMAND_LAST_HOUR ? "after" : feedDate(item.time);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(item);
    else groups.push({ key, items: [item] });
  }
  return groups;
}

// --- Event marks on the time track -----------------------------------------------------------------------

/** One mark of the time track: filled for an observed or reported item, hollow for an event of the model. */
export interface CommandEventMark {
  /** Where the mark stands, in replay hours (the mean of what it merges). */
  hour: number;
  /** The first hour of what it merges: the hour the event buttons stop at. */
  firstHour: number;
  filled: boolean;
  /** How many rows it stands for. */
  count: number;
}

/** The rows that have a mark: those with a time inside the replay. A scene held at the start has none. */
export function feedMarkItems(feed: readonly CommandFeedItem[]): CommandFeedItem[] {
  return feed.filter((item) => !item.hindsightOnly && item.precision !== "held" && item.precision !== "none" && item.fromHour >= 0 && item.fromHour <= COMMAND_LAST_HOUR);
}

/** A merged mark is a wider pill with its count: a mark closer than this to its first hour joins it, so the pill covers no neighbour. */
export const MERGED_MARK_REACH_PX = 11;

/**
 * The marks of the track. Marks that would stand closer than `minGapPx` to the first mark of a group merge into one
 * with a count (a mark that already holds several reaches `MERGED_MARK_REACH_PX`); a merged mark is filled when it
 * holds an observed or reported row. In trainee mode the marks after the replay hour are left out: the future is hidden.
 */
export function feedEventMarks(feed: readonly CommandFeedItem[], pxPerHour: number, options: { upTo?: number; minGapPx?: number } = {}): CommandEventMark[] {
  const minGap = options.minGapPx ?? 6;
  const upTo = options.upTo ?? COMMAND_LAST_HOUR;
  const marks: (CommandEventMark & { sum: number })[] = [];
  for (const item of feedMarkItems(feed).sort((a, b) => a.fromHour - b.fromHour)) {
    if (item.fromHour > upTo) break;
    const filled = item.lane !== "model";
    const last = marks[marks.length - 1];
    if (last && (item.fromHour - last.firstHour) * pxPerHour < (last.count > 1 && minGap > 0 ? Math.max(minGap, MERGED_MARK_REACH_PX) : minGap)) {
      last.count += 1;
      last.sum += item.fromHour;
      last.hour = last.sum / last.count;
      last.filled = last.filled || filled;
    } else {
      marks.push({ hour: item.fromHour, firstHour: item.fromHour, filled, count: 1, sum: item.fromHour });
    }
  }
  return marks.map(({ hour, firstHour, filled, count }) => ({ hour, firstHour, filled, count }));
}

/** The replay hours the "previous event" and "next event" buttons stop at: every hour with a mark, the start and the end. */
export function feedEventHours(feed: readonly CommandFeedItem[]): number[] {
  return [...new Set([0, ...feedMarkItems(feed).map((item) => item.fromHour), COMMAND_LAST_HOUR])].sort((a, b) => a - b);
}

// --- Place records known by now --------------------------------------------------------------------------

/** The place records a mode shows at a replay hour: all of them in hindsight, those published by the hour in trainee mode. */
export function placeRecordsAt<T extends Pick<ReportedDepthReport, "source">>(reports: readonly T[], hour: number, mode: CommandMode): T[] {
  if (mode === "hindsight") return [...reports];
  const at = clampCommandHour(hour);
  return reports.filter((report) => placeRecordHour(report).fromHour <= at);
}

/** How the model reads at the points of the located place records: the counts of the situation line. */
export interface PlaceRecordTally { located: number; consistent: number; wet: number; dry: number; other: number }

/**
 * The located place records among `reports`, counted by what the model shows at their point over the time they
 * describe: consistent with the report, wet (depth not compared), or dry. Nobody should trust the smooth water layer
 * over a person's report, and this count says how often the two differ.
 */
export function placeRecordTally(reports: readonly Pick<ReportedDepthReport, "point" | "consistency">[]): PlaceRecordTally {
  const located = reports.filter((report) => report.point !== null);
  const count = (status: ReportedDepthReport["consistency"]) => located.filter((report) => report.consistency === status).length;
  const consistent = count("consistent");
  const wet = count("model_wet");
  const dry = count("model_dry");
  return { located: located.length, consistent, wet, dry, other: located.length - consistent - wet - dry };
}
