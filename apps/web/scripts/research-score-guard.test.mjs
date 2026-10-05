import assert from "node:assert/strict";
import { test } from "node:test";

import {
  decimalNumbers,
  firstWorkspaceScoreAt,
  forbiddenValues,
  readWorkspaceMarkup,
  researchScoreMarkup,
  researchScoreTraces,
  visibleText,
  workspaceRankingProblems,
} from "./research-score-guard.mjs";

// The eight retained rows of the planning bundle and the GeoAI report's values, as they are published.
const retained = [
  ["TH570901", "Mae Sai", "แม่สาย", 18.01], ["TH570902", "Huai Khrai", "ห้วยไคร้", 5.9], ["TH570903", "Ko Chang", "เกาะช้าง", 53.65],
  ["TH570904", "Pong Pha", "โป่งผา", 15.42], ["TH570905", "Si Mueang Chum", "ศรีเมืองชุม", 50.37], ["TH570906", "Wiang Phang Kham", "เวียงพางคำ", 9.03],
  ["TH570908", "Ban Dai", "บ้านด้าย", 16.99], ["TH570909", "Pong Ngam", "โป่งงาม", 11.28],
].map(([id, name_en, name_th, value]) => ({ id, name_en, name_th, score: value.toFixed(1), stored: String(value), action_class: "E" }));
const values = forbiddenValues(retained, [44, 34, 23.6, 36.7, 15.2, 12.6, 17.1, 12.9]);

// What the planning overview says once a case has loaded, in both languages (the sentences that name FPPS, a class
// or a number), and the sentences of the forward page.
const CLEAN = [
  "Mae Sai core — Mae Sai · September 2024 2024-09-01–2024-09-30 Accepted FPPS / action class: unavailable Candidate flood extent and imposed road closures are assumptions, not observed road conditions.",
  "Modelled residents in the study area 44,160 2020 population context Within 30 minutes · baseline 15,580 Lose 30-minute access · imposed closures 11,199",
  "Candidate destinations: 9 Within 30 minutes 15,670 1,824 road segments enter an imposed closure scenario from candidate-flood intersection.",
  "Children means ages 0–14; observed local counts are unavailable. A partial subdistrict result describes its AOI intersection, not the full subdistrict.",
  "Accepted FPPS and action class remain unavailable. Missing inputs are not zero and weights are not redistributed. Sources, timing and limitations 2026-10-02T03:14:15.123Z",
  "Earlier research scores and classes are not accepted event-response priorities. The score table of the earlier Mae Sai GeoAI report, with a research score and class for each subdistrict, is not shown on Planning; it is kept, as historical research, only in Studio's archive.",
  "© OpenStreetMap contributors · ODbL 1.0 · openstreetmap.org/copyright EN ไทย",
  "แม่สาย พื้นที่หลัก — แม่สาย · กันยายน 2567 2024-09-01–2024-09-30 คะแนนและระดับที่รับรอง: ยังไม่มี ขอบเขตน้ำท่วมเป็นข้อมูลผู้สมัคร การปิดถนนเป็นสมมติฐาน ไม่ใช่สภาพถนนที่สังเกต",
  "ขอบเขตพื้นที่ศึกษาและชั้นข้อมูลที่อนุญาตให้เผยแพร่ ยังไม่ยืนยันสภาพถนนหรือจุดเข้าของสถานที่ 03 · บริการ",
  "FPPS และชั้นการดำเนินการที่ยอมรับยังไม่มี ค่าที่ขาดไม่ใช่ศูนย์และไม่มีการกระจายน้ำหนักใหม่ แหล่งข้อมูล เวลา และข้อจำกัด 2026-10-02T03:14:15.123Z",
  "คะแนนและชั้นการดำเนินการในงานวิจัยเดิมไม่ใช่ลำดับความสำคัญในการรับมือเหตุการณ์ที่ได้รับการยอมรับ ตารางคะแนนของรายงาน GeoAI แม่สายฉบับก่อน ซึ่งมีคะแนนและชั้นงานวิจัยของแต่ละตำบล ไม่แสดงในหน้าการวางแผน",
  "This page has moved. The Planning map workspace is now at /command/. หน้านี้ย้ายแล้ว พื้นที่ทำงานแผนที่สำหรับการวางแผนอยู่ที่ /command/",
];

test("the sentences of the planning overview and of the forward page carry no written form of a research score or class", () => {
  for (const text of CLEAN) assert.deepEqual(researchScoreTraces(text, values), [], text);
});

test("each written form of a research score or class is found, in English and in Thai", () => {
  for (const text of [
    "FPPS 53.6",
    "FPPS: 53.6",
    "FPPS score 53.6 (E)",
    "Retained FPPS: 53.6 (E) for Ko Chang; 50.4 (E) for Si Mueang Chum.",
    "Subdistrict FPPS Class Ko Chang 61.2 B",
    "Ko Chang 53.6 | E",
    "Class E",
    "Action class: E",
    "Research classes A to E",
    "ชั้น E",
    "คะแนน FPPS: 53.6 ชั้นการดำเนินการ E",
    "ชั้นการดำเนินการ E",
    "ระดับ D",
    "The report gave Wiang Phang Kham 23.6.",
    "Ko Chang 44.0 D",
    "Ko Chang (53.65)",
  ]) assert.notDeepEqual(researchScoreTraces(text, values), [], text);
  assert.deepEqual(researchScoreMarkup('<li><span class="rank-score class-e"><b>61.2</b></span></li>'), ["rank-score", "class-e"]);
  assert.deepEqual(researchScoreMarkup('<div class="fpps-block"><b>61.2</b></div><span class="decision-class class-a">A</span><b class="x class-d">D</b>'), ["fpps-block", "decision-class", "class-a", "class-d"]);
  assert.deepEqual(researchScoreMarkup('<main class="planning-candidate-overview-module__a1__page"><script>var a = \'class="rank-score"\';</script></main>'), []);
});

test("the list is one of written forms: a score written in another way passes, and the records say so", () => {
  // A whole number, a new value away from the word FPPS, and a class given as a bare letter are not found.
  for (const text of ["Ko Chang 44 D", "Priority of Ko Chang: 61.2", "Ko Chang — E"]) assert.deepEqual(researchScoreTraces(text, values), [], text);
});

test("a number stands on its own only when it is not part of a longer number, a version or a word", () => {
  assert.deepEqual(decimalNumbers("44,160 1.09 v1.0 2024-09-01 127.0.0.1 53.6% (9.0) 15.4.").map((number) => number.value), ["1.09", "53.6", "9.0", "15.4"]);
});

const row = (item, shown = item.score, badge = "e", letter = item.action_class) =>
  `<li><button type="button" class=""><span class="rank-number">01</span><span class="rank-name"><b>${item.name_en}</b><small>${item.id}</small></span><span class="rank-score class-${badge}"><b>${shown}</b><small>Class<!-- --> <!-- -->${letter}</small></span></button></li>`;
const listRow = (item, shown = item.score, letter = item.action_class) => `<li><button type="button">${item.name_en}<!-- -->: <!-- -->class ${letter}, FPPS ${shown}, low</button></li>`;
const LABEL = "Subdistrict scores and classes below are retained research comparisons, not accepted event-response priorities.";
const workspace = ({ rows = retained.map((item) => row(item)).join(""), list = retained.map((item) => listRow(item)).join(""), before = "", after = "" } = {}) =>
  `<main class="command-page"><p>Source time 16 Sept 2024, 06:16 ICT</p>${before}<p>${LABEL}</p><ol>${rows}</ol><ul class="map-area-results">${list}</ul><dd>1.09</dd><dd>5,794</dd>${after}<script>var x = "99.9";</script></main>`;

test("the workspace may show its eight retained rows, each with its own value and class, and no other one-decimal number", () => {
  assert.deepEqual(workspaceRankingProblems(readWorkspaceMarkup(workspace()), retained), []);
  const [first, ...rest] = retained;
  const changed = (html) => workspaceRankingProblems(readWorkspaceMarkup(html), retained);
  // A badge or a class that is not the bundle's, in the rail or in the map's text list.
  assert.match(changed(workspace({ rows: row(first, first.score, "a", "A") + rest.map((item) => row(item)).join("") })).join("; "), /TH570901 is shown as 18\.0, class A \(badge a\).*a class that no retained subdistrict has: A/);
  assert.match(changed(workspace({ rows: row(first, first.score, "a", "E") + rest.map((item) => row(item)).join("") })).join("; "), /TH570901 is shown as 18\.0, class E \(badge a\)/);
  assert.match(changed(workspace({ list: listRow(first, first.score, "B") + rest.map((item) => listRow(item)).join("") })).join("; "), /text list shows Mae Sai as 18\.0, class B/);
  // A value that is not the row's own, a ninth row, a missing row.
  assert.match(changed(workspace({ rows: row(first, "50.4") + rest.map((item) => row(item)).join("") })).join("; "), /TH570901 is shown as 50\.4/);
  assert.match(changed(workspace({ rows: retained.map((item) => row(item)).join("") + row({ id: "TH570999", name_en: "Ninth area", score: "44.0", action_class: "D" }, "44.0", "d", "D") })).join("; "), /9 rows for 8.*not in the bundle: TH570999.*not one of the retained values: 44\.0.*no retained subdistrict has: D/);
  assert.match(changed(workspace({ rows: rest.map((item) => row(item)).join("") })).join("; "), /7 rows for 8/);
  // A ninth value outside the rail: as text, or in a list of its own.
  assert.match(changed(workspace({ after: "<p>Ninth area 44.0 D</p>" })).join("; "), /not one of the retained values: 44\.0/);
  assert.match(changed(workspace({ after: "<ol><li><b>36.7</b></li></ol>" })).join("; "), /not one of the retained values: 36\.7/);
});

test("the first retained score or class of the workspace is found whatever its written form, so that the label can be required before it", () => {
  const at = (html) => { const text = visibleText(html); return { label: text.indexOf(LABEL), first: firstWorkspaceScoreAt(text) }; };
  const plain = at(workspace());
  assert.ok(plain.label > -1 && plain.label < plain.first);
  for (const before of ["<p>53.6 / E</p>", "<p>FPPS 53.6</p>", "<p>Class E</p>", "<p>ชั้น E</p>", "<p>FPPS: 53</p>"]) {
    const moved = at(workspace({ before }));
    assert.ok(moved.first > -1 && moved.first < moved.label, before);
  }
});
