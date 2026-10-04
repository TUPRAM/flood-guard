/**
 * From seeing to acting: the facts about an invented item (nearest counted shelters, the access model at the nearest
 * resident node, the nearest road under 0.3 m, the staging point), and the brief built from them. The brief starts
 * and ends with the exercise tag, holds no rain value, no free text and no statement of a place record, and its
 * text-message link names no recipient.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type AreaGeometry, type GeoCollection, type Language, type LineGeometry, type RoadProps, type TambonProps, type TimelineManifest } from "./flood-timeline";
import { buildCommandModel, changeSinceHourBefore, districtFiguresAt, tambonOrderByHour, tambonRowsAt } from "./flood-timeline-command";
import {
  ACCESS_NODE_REACH_M,
  bearingDeg,
  BRIEF_DEFAULT_LANGUAGE,
  BRIEF_MAX_LINES,
  BRIEF_TAG,
  BRIEF_TAG_SHORT,
  commandDistanceBearing,
  commandDistanceText,
  commandRoadName,
  compassPoint,
  depthFact,
  distanceM,
  itemBriefLines,
  itemBriefSms,
  itemFacts,
  nearestAccessNode,
  nearestCountedSites,
  nearestRoadUnderDepth,
  nodeAccessAt,
  resolveStaging,
  shortSiteName,
  situationBriefLines,
  SMS_MAX_CHARS,
  smsHref,
  smsParts,
  type ItemFacts,
  type LatLon,
} from "./flood-timeline-command-brief";
import { EXERCISE_FILE_URL, parseExerciseFile, type ExerciseItem } from "./flood-timeline-command-incidents";
import { accessSnapshot, countedInReportedSet, parseAccessNodes, REPORTED_SET_ID } from "./flood-timeline-evacuation";
import { roadState } from "./flood-timeline";
import { describeWordingFindings, findWordingViolations } from "./replay-wording-lint";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<LineGeometry, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const nodes = parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!);
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes });
const exercise = parseExerciseFile(JSON.parse(read(EXERCISE_FILE_URL).toString("utf8")));
const sites = manifest.shelters!.reported;
const setIndex = manifest.access!.sets.indexOf(REPORTED_SET_ID);
const LANGUAGES: readonly Language[] = ["en", "th"];
const PEAK = 84;
const item = (id: string): ExerciseItem => exercise.items.find((entry) => entry.id === id)!;
const tambonOf = (entry: ExerciseItem) => model.tambons.find((tambon) => tambon.id === entry.tambonId) ?? null;
/** The facts of an item at one hour; the depth is 0.6 m unless a test names another (undefined is a depth too: not loaded). */
const factsOf = (entry: ExerciseItem, hour: number, options: { depth?: number | null; mode?: "trainee" | "hindsight" } = {}): ItemFacts => itemFacts({
  point: entry.point, hour, mode: options.mode ?? "hindsight", stage: model.stages[hour], depth: "depth" in options ? options.depth : 0.6, impassableDepthM: manifest.impassable_depth_m, roads: roads.features, sites, nodes, setIndex,
  levels: manifest.access!.levels, staging: resolveStaging({ type: "site", id: "R05" }, sites),
});
const lintOf = (text: string, source: string) => describeWordingFindings(findWordingViolations(text, source));

describe("Straight lines on the ground", () => {
  const office: LatLon = { lat: 20.4281122, lon: 99.8832196 };

  it("measures a distance along the great circle, and a bearing clockwise from north", () => {
    // One thousandth of a degree of latitude is about 111 m everywhere.
    expect(distanceM(office, { lat: office.lat + 0.001, lon: office.lon })).toBeCloseTo(111.2, 0);
    // At 20.4° north a thousandth of a degree of longitude is about 104 m.
    expect(distanceM(office, { lat: office.lat, lon: office.lon + 0.001 })).toBeCloseTo(104.2, 0);
    expect(distanceM(office, office)).toBe(0);
    expect(bearingDeg(office, { lat: office.lat + 0.01, lon: office.lon })).toBeCloseTo(0, 5);
    expect(bearingDeg(office, { lat: office.lat, lon: office.lon + 0.01 })).toBeCloseTo(90, 1);
    expect(bearingDeg(office, { lat: office.lat - 0.01, lon: office.lon })).toBeCloseTo(180, 5);
    expect(bearingDeg(office, { lat: office.lat, lon: office.lon - 0.01 })).toBeCloseTo(270, 1);
  });

  it("names the nearest of the eight compass points", () => {
    expect([0, 22, 23, 45, 90, 135, 180, 225, 270, 315, 338, 359.9, 360, -45].map(compassPoint)).toEqual(["N", "N", "NE", "NE", "E", "SE", "S", "SW", "W", "NW", "N", "N", "N", "NW"]);
  });

  it("prints a distance rounded, with a tilde: the points are placed to within a tolerance", () => {
    expect([0, 4, 7, 124, 994, 995, 1249, 12_340].map((metres) => commandDistanceText(metres, "en"))).toEqual(["<10 m", "<10 m", "~10 m", "~120 m", "~990 m", "~1.0 km", "~1.2 km", "~12.3 km"]);
    expect(commandDistanceText(1249, "th")).toBe("~1.2 กม.");
    expect(commandDistanceBearing(1249, "NE", "en")).toBe("~1.2 km · north-east");
    expect(commandDistanceBearing(480, "SW", "th")).toBe("~480 ม. · ทิศตะวันตกเฉียงใต้");
  });
});

describe("Where people go: the nearest counted shelters", () => {
  it("lists the three nearest of the twelve located sites counted in the 2024 set, by straight line", () => {
    expect(sites.filter(countedInReportedSet)).toHaveLength(12);
    const near = nearestCountedSites(sites, item("EX-05").point, model.stages[PEAK], { hour: PEAK, mode: "hindsight" });
    expect(near).toHaveLength(3);
    expect(near.map((site) => site.distanceM)).toEqual([...near.map((site) => site.distanceM)].sort((a, b) => a - b));
    // The command centre, a site first used after the replay and a site without a point are never listed.
    const all = nearestCountedSites(sites, item("EX-05").point, model.stages[PEAK], { hour: PEAK, mode: "hindsight" }, 99);
    expect(all).toHaveLength(12);
    for (const id of ["R05", "R04", "R19", "R09", "R13", "R14", "R17"]) expect(all.map((site) => site.id)).not.toContain(id);
    // Each carries its distance, its bearing, its state in the model and what the data says of its use.
    for (const site of near) {
      expect(site.distanceM).toBeGreaterThan(0);
      expect(["dry", "wet", "not_modelled"]).toContain(site.state);
      expect(site.firstUse).toBe("2024-09-15 or earlier");
      expect(site.occupancy).not.toMatch(/^Occupancy:/);
      expect(site.pending).toBe(false);
    }
  });

  it("marks a site as not yet reported in trainee mode before the day of its first source", () => {
    const point = item("EX-02").point;
    const early = nearestCountedSites(sites, point, model.stages[40], { hour: 40, mode: "trainee" }, 99);
    expect(early.every((site) => site.pending)).toBe(true);
    // 11 Sep 00:00 (hour 48): the two shelters named in the first reports.
    const day11 = nearestCountedSites(sites, point, model.stages[48], { hour: 48, mode: "trainee" }, 99);
    expect(day11.filter((site) => !site.pending).map((site) => site.id).sort()).toEqual(["R01", "R02"]);
    // 16 Sep 00:00 (hour 168): the list published that day names the rest.
    expect(nearestCountedSites(sites, point, model.stages[168], { hour: 168, mode: "trainee" }, 99).every((site) => !site.pending)).toBe(true);
    expect(nearestCountedSites(sites, point, model.stages[40], { hour: 40, mode: "hindsight" }, 99).every((site) => !site.pending)).toBe(true);
  });

  it("shortens a site's name by the note in brackets at its end", () => {
    expect(shortSiteName("ที่ว่าการอำเภอแม่สาย (ศูนย์บัญชาการเหตุการณ์ฯ / โรงครัว)")).toBe("ที่ว่าการอำเภอแม่สาย");
    expect(shortSiteName("Wat Chetiyaram (Wat San That) shelter")).toBe("Wat Chetiyaram (Wat San That) shelter");
    expect(shortSiteName("(only a note)")).toBe("(only a note)");
  });
});

describe("The access model at the nearest resident node", () => {
  it("finds the nearest node within 300 m, and none far from any home", () => {
    expect(ACCESS_NODE_REACH_M).toBe(300);
    const near = nearestAccessNode(nodes, item("EX-02").point)!;
    expect(near.distanceM).toBeLessThanOrEqual(300);
    // No other node is nearer.
    for (let index = 0; index < nodes.count; index += 1) {
      expect(distanceM(item("EX-02").point, { lat: nodes.lat[index], lon: nodes.lon[index] })).toBeGreaterThanOrEqual(near.distanceM - 1e-6);
    }
    expect(nearestAccessNode(nodes, { lat: 21.5, lon: 99.2 })).toBeNull();
    expect(nearestAccessNode(nodes, item("EX-02").point, 0)).toBeNull();
  });

  it("reads kept, lost or none even before the flood, as the district figures count them", () => {
    const levels = manifest.access!.levels;
    for (const hour of [0, 60, PEAK, 130]) {
      const stage = model.stages[hour];
      let lost = 0;
      let none = 0;
      for (let index = 0; index < nodes.count; index += 1) {
        const access = nodeAccessAt(nodes, setIndex, index, stage, levels);
        if (access === "lost") lost += nodes.population[index];
        if (access === "none_before") none += nodes.population[index];
      }
      const snapshot = accessSnapshot(model.sets.reported.summary, stage, levels);
      expect(lost).toBeCloseTo(snapshot.lost.population, 3);
      expect(none).toBeCloseTo(model.sets.reported.summary.never.population, 3);
    }
    // Before the flood nobody has lost access: a node either keeps it or never had it.
    const before = new Set(Array.from({ length: nodes.count }, (_, index) => nodeAccessAt(nodes, setIndex, index, 0, levels)));
    expect([...before].sort()).toEqual(["kept", "none_before"]);
  });
});

describe("How to get near: facts only", () => {
  it("reads the model at the point against the 0.3 m level at which roads count as impassable", () => {
    expect(depthFact(undefined, 0.3)).toBe("not_loaded");
    expect(depthFact(null, 0.3)).toBe("outside");
    expect(depthFact(0, 0.3)).toBe("dry");
    expect(depthFact(0.29, 0.3)).toBe("under");
    expect(depthFact(0.3, 0.3)).toBe("at_or_over");
    // 3.5 − 3.2 counts as 0.3 m, as it does for a road.
    expect(depthFact(3.5 - 3.2, 0.3)).toBe("at_or_over");
    expect(depthFact(1.4, 0.3)).toBe("at_or_over");
  });

  it("finds the nearest road piece under 0.3 m in the model, and never an impassable one", () => {
    const point = item("EX-09").point;
    const dry = nearestRoadUnderDepth(roads.features, point, 0, manifest.impassable_depth_m)!;
    const peak = nearestRoadUnderDepth(roads.features, point, model.stages[PEAK], manifest.impassable_depth_m)!;
    expect(dry.state).toBe("dry");
    expect(dry.distanceM).toBeGreaterThanOrEqual(0);
    // At the peak the nearest such piece is no nearer than before the flood.
    expect(peak.distanceM).toBeGreaterThanOrEqual(dry.distanceM);
    expect(["dry", "wet"]).toContain(peak.state);
    // With every piece impassable there is none.
    expect(nearestRoadUnderDepth(roads.features.filter((road) => road.properties.m && road.properties.h !== null), point, 99, manifest.impassable_depth_m)).toBeNull();
    // A piece outside the model is never offered.
    expect(nearestRoadUnderDepth(roads.features.map((road) => ({ ...road, properties: { ...road.properties, m: false } })), point, 0, manifest.impassable_depth_m)).toBeNull();
  });

  it("measures to the nearest point of a piece, not to its ends", () => {
    const piece = { properties: { c: "residential", h: null, m: true, len: 200, t: "TH570901", n: "ถนนทดสอบ" } as RoadProps, geometry: { type: "LineString" as const, coordinates: [[99.88, 20.43], [99.882, 20.43]] as [number, number][] } };
    const beside = nearestRoadUnderDepth([piece], { lat: 20.431, lon: 99.881 }, 2, 0.3)!;
    expect(beside.distanceM).toBeCloseTo(111.1, 0);
    expect(beside.name).toBe("ถนนทดสอบ");
    const beyond = nearestRoadUnderDepth([piece], { lat: 20.43, lon: 99.883 }, 2, 0.3)!;
    expect(beyond.distanceM).toBeCloseTo(104.3, 0);
    expect(roadState(null, 2, 0.3)).toBe("dry");
    expect(commandRoadName(null, "en")).toBe("an unnamed road");
    expect(commandRoadName("ถนนทดสอบ", "th")).toBe("ถนนทดสอบ");
  });

  it("places the staging point at the district office, at the municipality office or at a tapped point", () => {
    expect(resolveStaging({ type: "site", id: "R05" }, sites)).toMatchObject({ siteId: "R05", name: { th: "ที่ว่าการอำเภอแม่สาย", en: "Mae Sai District Office" } });
    expect(resolveStaging({ type: "site", id: "R01" }, sites)).toMatchObject({ siteId: "R01", lat: 20.4265331 });
    expect(resolveStaging({ type: "point", lat: 20.44, lon: 99.89 }, sites)).toEqual({ lat: 20.44, lon: 99.89, name: null, siteId: null });
    // A site without a point, or one the data does not hold, gives no staging point.
    expect(resolveStaging({ type: "site", id: "R09" }, sites)).toBeNull();
    expect(resolveStaging({ type: "site", id: "R99" }, sites)).toBeNull();
  });

  it("gathers the facts of an item: three sites, the node, the road and the straight line from the staging point", () => {
    const facts = factsOf(item("EX-05"), PEAK, { depth: 1.4 });
    expect(facts.sites).toHaveLength(3);
    expect(facts.depthFact).toBe("at_or_over");
    expect(facts.staging!.distanceM).toBeCloseTo(distanceM(resolveStaging({ type: "site", id: "R05" }, sites)!, item("EX-05").point), 6);
    expect(facts.staging!.compass).toBe("NE");
    expect(facts.road).not.toBeNull();
    // Without a staging point there is no line; without the 2024 set there is no line from the access model.
    const bare = itemFacts({ point: item("EX-05").point, hour: PEAK, mode: "hindsight", stage: model.stages[PEAK], depth: undefined, impassableDepthM: 0.3, roads: roads.features, sites, nodes, setIndex: -1, levels: manifest.access!.levels, staging: null });
    expect(bare).toMatchObject({ staging: null, node: null, depthFact: "not_loaded" });
  });
});

describe("The brief of an invented item", () => {
  const briefs = LANGUAGES.flatMap((language) => exercise.items.map((entry) => ({
    language, entry, lines: itemBriefLines({ item: entry, tambon: tambonOf(entry), callsign: "BOAT-2", hour: Math.max(entry.hour, PEAK), facts: factsOf(entry, Math.max(entry.hour, PEAK)) }, language),
  })));

  it("is written in Thai unless English is asked for", () => {
    expect(BRIEF_DEFAULT_LANGUAGE).toBe("th");
    const entry = item("EX-05");
    const lines = itemBriefLines({ item: entry, tambon: tambonOf(entry), callsign: null, hour: PEAK, facts: factsOf(entry, PEAK) });
    expect(lines[0]).toBe("[ฝึกซ้อม – ไม่ใช่เหตุจริง] EX-05");
  });

  it("starts and ends with the exercise tag, in at most nine lines", () => {
    expect(briefs).toHaveLength(2 * exercise.items.length);
    for (const { language, entry, lines } of briefs) {
      const tag = BRIEF_TAG[language];
      expect(lines.length, entry.id).toBeLessThanOrEqual(BRIEF_MAX_LINES);
      expect(lines[0].startsWith(`${tag} ${entry.id}`), entry.id).toBe(true);
      expect(lines[lines.length - 1], entry.id).toBe(tag);
      for (const line of lines) expect(line).not.toContain("\n");
    }
    expect(BRIEF_TAG).toEqual({ en: "[EXERCISE – not a real incident]", th: "[ฝึกซ้อม – ไม่ใช่เหตุจริง]" });
  });

  it("reads as the template of the plan", () => {
    const entry = item("EX-05");
    const facts = factsOf(entry, PEAK, { depth: 1.42 });
    const th = itemBriefLines({ item: entry, tambon: tambonOf(entry), callsign: "BOAT-2", hour: PEAK, facts }, "th");
    expect(th[0]).toBe("[ฝึกซ้อม – ไม่ใช่เหตุจริง] EX-05 · ชุด BOAT-2");
    expect(th[1]).toBe("เหตุ: ขอความช่วยเหลือ (เสี่ยงต่อชีวิต) · น้ำสูงเกินศีรษะ");
    expect(th[2]).toBe("ที่: หมู่บ้านปิยะพร ต.แม่สาย (±400 ม.) 20.4345,99.8955");
    expect(th[3]).toBe("คน: 1–2 คน · ต้องการ: การอพยพ");
    expect(th[4]).toMatch(/^เข้าถึง: แบบจำลองน้ำลึก ~1\.4 ม\. · ถนนที่น้ำต่ำกว่า 0\.3 ม\. ใกล้สุด (~[\d.]+|<10) (ม|กม)\. · ไม่ทราบความแรงกระแสน้ำ$/);
    expect(th[5]).toMatch(/^ที่พักพิงใกล้สุด \(เส้นตรง\): .+ ~[\d.]+ (ม|กม)\.$/);
    expect(th[6]).toBe("เวลาในการย้อนดู: 12 ก.ย. 2567 (2024) · 12:00 น.");
    expect(th[7]).toBe("ที่มา: รายการฝึกซ้อม (สมมุติขึ้น) · แบบจำลองความเชื่อมั่นต่ำ");
    const en = itemBriefLines({ item: entry, tambon: tambonOf(entry), callsign: "BOAT-2", hour: PEAK, facts }, "en");
    expect(en[0]).toBe("[EXERCISE – not a real incident] EX-05 · team BOAT-2");
    expect(en[1]).toBe("What: Call for help (Life at risk) · water above head height");
    expect(en[2]).toBe("Where: หมู่บ้านปิยะพร (Piyaphon village), Mae Sai subdistrict (±400 m) 20.4345,99.8955");
    expect(en[6]).toBe("Replay time: 12 Sep 2024 · 12:00 ICT");
    expect(en[7]).toBe("Source: exercise item (invented) · model, low confidence");
  });

  it("says what the model has at the point in every case, and always that the current is not known", () => {
    const entry = item("EX-01");
    const line = (depth: number | null | undefined, language: Language) => itemBriefLines({ item: entry, tambon: tambonOf(entry), callsign: null, hour: PEAK, facts: factsOf(entry, PEAK, { depth }) }, language)[4];
    expect(line(undefined, "en")).toMatch(/^Access: model depth not loaded · /);
    expect(line(null, "en")).toMatch(/^Access: the point is outside the modelled area · /);
    expect(line(0, "en")).toMatch(/^Access: model dry at the point · /);
    expect(line(0.02, "en")).toMatch(/^Access: model depth <0\.1 m · /);
    for (const depth of [undefined, null, 0, 0.6]) {
      expect(line(depth, "en").endsWith("strength of the current not known")).toBe(true);
      expect(line(depth, "th").endsWith("ไม่ทราบความแรงกระแสน้ำ")).toBe(true);
    }
  });

  it("names the nearest shelter that has been reported by the replay hour, or says that none has", () => {
    const entry = item("EX-02");
    const shelter = (hour: number, mode: "trainee" | "hindsight") => itemBriefLines({ item: entry, tambon: tambonOf(entry), callsign: null, hour, facts: factsOf(entry, hour, { mode }) }, "en")[5];
    expect(shelter(40, "trainee")).toBe("Nearest shelter (straight line): none reported yet at this replay hour");
    expect(shelter(40, "hindsight")).toMatch(/^Nearest shelter \(straight line\): .+ ~[\d.]+ (m|km)$/);
    expect(shelter(60, "trainee")).toMatch(/^Nearest shelter \(straight line\): (Mae Sai Subdistrict Municipality Office shelter and relief centre|Wat Phrom Wihan temporary shelter) ~/);
  });

  it("never holds a rain value, the free text of an item or the statement of a place record", () => {
    const statements = manifest.reported_depths!.reports.flatMap((report) => [report.depth.statement.en, report.depth.statement.th]);
    for (const { language, entry, lines } of briefs) {
      const text = lines.join("\n");
      // No rain: no millimetres, no gauge and no word for rain.
      expect(text, entry.id).not.toMatch(/\d\s?(?:mm|มม\.)|rain|ฝน|gauge|MOU189|DIWO/i);
      // The sentences an item says are free text: the brief is built from the stated fields only.
      expect(text.includes(entry.text[language]), entry.id).toBe(false);
      for (const sentence of entry.text[language].split(/(?<=[.!?])\s+/).filter((part) => part.length > 20)) expect(text.includes(sentence), entry.id).toBe(false);
      for (const statement of statements) expect(text.includes(statement), entry.id).toBe(false);
      expect(lintOf(text, `brief ${entry.id} ${language}`)).toBe("");
    }
  });
});

describe("The text-message version", () => {
  it("is two lines of at most 134 characters, with the short exercise tag at both ends", () => {
    expect(SMS_MAX_CHARS).toBe(134);
    for (const language of LANGUAGES) {
      for (const entry of exercise.items) {
        for (const callsign of [null, "BOAT-2", "ABCDEFGHIJKL"]) {
          const text = itemBriefSms({ item: entry, tambon: tambonOf(entry), callsign }, language);
          const tag = BRIEF_TAG_SHORT[language];
          expect(text.length, `${entry.id} ${language}`).toBeLessThanOrEqual(SMS_MAX_CHARS);
          expect(text.split("\n")).toHaveLength(2);
          expect(text.startsWith(`${tag} ${entry.id}`)).toBe(true);
          expect(text.endsWith(tag)).toBe(true);
          expect(text).toContain(`${entry.point.lat.toFixed(4)},${entry.point.lon.toFixed(4)}`);
          expect(text).not.toMatch(/\d\s?(?:mm|มม\.)|rain|ฝน/i);
          expect(lintOf(text, `sms ${entry.id} ${language}`)).toBe("");
        }
      }
    }
    expect(itemBriefSms({ item: item("EX-05"), tambon: tambonOf(item("EX-05")), callsign: "BOAT-2" }, "th"))
      .toBe("[ฝึกซ้อม] EX-05 ชุด BOAT-2: ขอความช่วยเหลือ น้ำสูงเกินศีรษะ 1–2 คน\nหมู่บ้านปิยะพร ต.แม่สาย 20.4345,99.8955 [ฝึกซ้อม]");
    expect(itemBriefSms({ item: item("EX-05"), tambon: tambonOf(item("EX-05")), callsign: "BOAT-2" }, "en"))
      .toBe("[EXERCISE] EX-05 BOAT-2: Call for help, water above head height, 1-2 people\nPiyaphon village, Mae Sai 20.4345,99.8955 [EXERCISE]");
  });

  it("drops the people band, the depth band and the subdistrict, and then cuts the place name, to stay within the limit", () => {
    const long = { ...item("EX-10"), place: { th: "ชุมชนที่มีชื่อยาวมากเป็นพิเศษเพื่อทดสอบการตัดข้อความให้อยู่ในความยาวที่กำหนดไว้สำหรับข้อความสั้น", en: "A community with a very long name that is here only to test how the text is cut to the limit of a short message" } };
    for (const language of LANGUAGES) {
      const text = itemBriefSms({ item: long, tambon: { th: "เวียงพางคำ", en: "Wiang Phang Kham" }, callsign: "ABCDEFGHIJKL" }, language);
      expect(text.length).toBeLessThanOrEqual(SMS_MAX_CHARS);
      expect(text).toContain("…");
      expect(text.startsWith(BRIEF_TAG_SHORT[language])).toBe(true);
      expect(text.endsWith(BRIEF_TAG_SHORT[language])).toBe(true);
      expect(text).toContain("20.4312,99.8998");
    }
  });

  it("counts the parts of a message as the standard does", () => {
    expect(smsParts("a".repeat(160))).toEqual({ characters: 160, parts: 1, alphabet: "basic" });
    expect(smsParts("a".repeat(161))).toEqual({ characters: 161, parts: 2, alphabet: "basic" });
    // A bracket takes two places of the basic alphabet.
    expect(smsParts(`[${"a".repeat(158)}]`).parts).toBe(2);
    expect(smsParts("ก".repeat(70))).toEqual({ characters: 70, parts: 1, alphabet: "unicode" });
    expect(smsParts("ก".repeat(71)).parts).toBe(2);
    expect(smsParts("ก".repeat(134)).parts).toBe(2);
    expect(smsParts("ก".repeat(135)).parts).toBe(3);
    // The Thai version is two parts at most; the English one is one part.
    for (const entry of exercise.items) {
      expect(smsParts(itemBriefSms({ item: entry, tambon: tambonOf(entry), callsign: "BOAT-2" }, "th")).parts).toBeLessThanOrEqual(2);
      expect(smsParts(itemBriefSms({ item: entry, tambon: tambonOf(entry), callsign: "BOAT-2" }, "en"))).toMatchObject({ parts: 1, alphabet: "basic" });
    }
  });

  it("hands the text to the message app with no recipient", () => {
    const text = itemBriefSms({ item: item("EX-05"), tambon: tambonOf(item("EX-05")), callsign: "BOAT-2" }, "th");
    const href = smsHref(text);
    expect(href.startsWith("sms:?&body=")).toBe(true);
    // Nothing stands between "sms:" and "?": no number, and no hotline.
    expect(href).not.toMatch(/^sms:[^?]/);
    expect(href).not.toMatch(/1784|1669|191/);
    expect(decodeURIComponent(href.slice("sms:?&body=".length))).toBe(text);
    expect(smsHref("a b&c")).toBe("sms:?&body=a%20b%26c");
  });
});

describe("The situation brief", () => {
  const brief = (hour: number, language: Language) => {
    const rows = tambonRowsAt(model, hour, "reported");
    const order = tambonOrderByHour(model, "reported")[hour];
    return situationBriefLines({ hour, figures: districtFiguresAt(model, hour), rows: order.map((id) => rows.find((row) => row.id === id)!), change: changeSinceHourBefore(model, hour) }, language);
  };

  it("gives the three model figures, the first three subdistricts and the roads newly impassable, between two exercise tags", () => {
    const en = brief(PEAK, "en");
    expect(en).toHaveLength(BRIEF_MAX_LINES);
    expect(en[0]).toBe("[EXERCISE – not a real incident] Situation brief");
    expect(en[1]).toBe("Replay time: 12 Sep 2024 · 12:00 ICT (hour 84 of 264)");
    expect(en[2]).toBe("Lost shelter access: ~7,100 residents (of ~34,500 in reach)");
    expect(en[3]).toBe("Residents in modelled water: ~16,100");
    expect(en[4]).toBe("Roads impassable: ~164 km of 307 km");
    expect(en[5]).toBe("Most residents who lost shelter access: Mae Sai ~5,700 · Pong Pha ~560 · Ko Chang ~460");
    expect(en[6]).toBe("No named road became impassable this hour");
    // An hour of the onset names the roads, as the clock card does.
    expect(brief(44, "en")[6]).toMatch(/^Newly impassable since 19:00: .+/);
    expect(brief(44, "th")[6]).toMatch(/^ถนนที่เริ่มสัญจรไม่ได้ตั้งแต่ 19:00 น\.: .+/);
    expect(en[7]).toBe("Source: model, low confidence · current not modelled");
    expect(en[8]).toBe("[EXERCISE – not a real incident]");
    const th = brief(PEAK, "th");
    expect(th[0]).toBe("[ฝึกซ้อม – ไม่ใช่เหตุจริง] สรุปสถานการณ์");
    expect(th[5]).toBe("ตำบลที่มีผู้สูญเสียการเข้าถึงที่พักพิงมากที่สุด: แม่สาย ~5,700 · โป่งผา ~560 · เกาะช้าง ~460");
    expect(th[8]).toBe("[ฝึกซ้อม – ไม่ใช่เหตุจริง]");
  });

  it("says so when no subdistrict has lost access and no named road has changed", () => {
    const start = brief(0, "en");
    expect(start[5]).toBe("No subdistrict has residents who lost shelter access at this hour");
    expect(start[6]).toBe("No named road became impassable this hour");
    expect(brief(0, "th")[5]).toBe("ยังไม่มีตำบลใดมีผู้สูญเสียการเข้าถึงที่พักพิง ณ ชั่วโมงนี้");
  });

  it("holds no score, no class and no rain value, at every hour", () => {
    for (const language of LANGUAGES) {
      for (const hour of [0, 36, 44, 60, PEAK, 100, 130, 200, 264]) {
        const lines = brief(hour, language);
        const text = lines.join("\n");
        expect(lines).toHaveLength(BRIEF_MAX_LINES);
        expect(lines[0].startsWith(BRIEF_TAG[language])).toBe(true);
        expect(lines[8]).toBe(BRIEF_TAG[language]);
        expect(text).not.toMatch(/score|priority|class|FPPS|คะแนน|ลำดับความสำคัญ|\d\s?(?:mm|มม\.)|rain|ฝน/i);
        expect(lintOf(text, `situation brief ${hour} ${language}`)).toBe("");
      }
    }
  });
});
