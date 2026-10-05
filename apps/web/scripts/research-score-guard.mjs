import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * What the build checks mean by "a research score or class" on the Planning pages (decision log R17 and R19). It is
 * a list of written forms, and the static check, the browser check and their records use this one list:
 *
 * - the markup of the map workspace's ranking: `rank-score`, `fpps-block`, `decision-class`, `action-class-legend`
 *   and the class badges `class-a` to `class-e`;
 * - the word FPPS followed, in the same sentence and within 40 characters, by a digit;
 * - "class", "classes", "ชั้น…" or "ระดับ…" followed by a single capital letter A to E;
 * - one of the eight retained values of the planning bundle, as the workspace writes it (one decimal) or as the
 *   bundle stores it, and one of the GeoAI report's values written with a decimal point.
 *
 * It does not read meaning. A score written in another way passes: a new number that is none of those values and
 * stands away from the word FPPS, a whole number such as the report's 44 and 34, or a class given as a bare letter.
 */

const MARKER = /^(?:rank-score|fpps-block|decision-class|action-class-legend|class-[a-e])$/;
/** The same markers, as a selector for a rendered page. */
export const RESEARCH_SCORE_SELECTOR = [".rank-score", ".fpps-block", ".decision-class", ".action-class-legend", ...["a", "b", "c", "d", "e"].map((letter) => `.class-${letter}`)].join(", ");

const SCORE_AFTER_WORD = /FPPS[^.!?]{0,40}?\d+(?:\.\d+)?/g;
const CLASS_ENGLISH = /(?<![A-Za-z])(?:[Cc]lass(?:es)?|CLASS(?:ES)?)\W{0,3}[A-E](?![A-Za-z0-9])/g;
const CLASS_THAI = /(?:ชั้น|ระดับ)[^\sA-Za-z0-9]{0,24}\s{0,2}[A-E](?![A-Za-z0-9])/g;
/** A number written with a decimal point that stands on its own: not part of a longer number, a version or a word. */
const DECIMAL_NUMBER = /(?<![\w.,])\d+\.\d+(?![\w]|[.,]\d)/g;
/** The forms the map workspace itself uses for a class ("Class E", "class E", "ชั้น E"). */
const WORKSPACE_CLASS = /(?:(?<![A-Za-z])[Cc]lass|ชั้น)\s+([A-E])(?![A-Za-z0-9])/g;

/** The retained ranking of the planning bundle, one row per subdistrict, as the map workspace writes it. */
export function readRetainedRanking(out) {
  const bundle = JSON.parse(readFileSync(resolve(out, "offline-demo/mae-sai/bundle.json"), "utf8"));
  return bundle.areas.map((area) => ({
    id: area.area_id,
    name_en: area.area_name_en,
    name_th: area.area_name_th,
    score: area.fpps_0_100.toFixed(1),
    stored: String(area.fpps_0_100),
    action_class: area.action_class,
  }));
}

/** The scores of the GeoAI research report's table, as the report stores and shows them. */
export function readReportScores(out) {
  return JSON.parse(readFileSync(resolve(out, "geoai/mae-sai-real.json"), "utf8")).subdistricts.map((row) => Number(row.fpps));
}

/** Every value a page without research scores must not show as a number of its own. */
export function forbiddenValues(retained, reportScores) {
  return new Set([
    ...retained.flatMap((row) => [row.score, row.stored]),
    // A report value is looked for only where it is written with a decimal point: 44 and 34 are whole numbers and
    // would be taken for a count of people or of road segments.
    ...reportScores.flatMap((value) => [value.toFixed(1), String(value)]).filter((text) => text.includes(".")),
  ]);
}

/** The text a reader sees in a built page, in page order: no script, no comment, no tag. */
export function visibleText(html) {
  return html.replace(/<script\b[\s\S]*?<\/script>/g, " ").replace(/<style\b[\s\S]*?<\/style>/g, " ").replace(/<!--[\s\S]*?-->/g, "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
}

/** The numbers of a text that are written with a decimal point and stand on their own. */
export function decimalNumbers(text) {
  return [...text.matchAll(DECIMAL_NUMBER)].map((match) => ({ value: match[0], index: match.index }));
}

/**
 * The written forms of a research score or class found in a text that must have none. `values` is the set from
 * `forbiddenValues`. An empty list means that none of the forms listed at the head of this file is in the text.
 */
export function researchScoreTraces(text, values) {
  return [
    ...[...text.matchAll(SCORE_AFTER_WORD), ...text.matchAll(CLASS_ENGLISH), ...text.matchAll(CLASS_THAI)].map((match) => match[0]),
    ...decimalNumbers(text).filter((number) => values.has(number.value)).map((number) => number.value),
  ];
}

/** The ranking markup found in the HTML of a page that must have none. */
export function researchScoreMarkup(html) {
  return [...html.replace(/<script\b[\s\S]*?<\/script>/g, " ").matchAll(/\bclass="([^"]*)"/g)]
    .flatMap((match) => match[1].split(/\s+/).filter((name) => MARKER.test(name)));
}

/**
 * Runs in the page (pass it to `page.evaluate`): the text of the document, hidden text included, outside the
 * containers named by `exclude`, and the elements that carry the ranking markup.
 */
export function collectRenderedPage({ selector, exclude }) {
  const skipped = ["script", "style", "noscript", "template", ...(exclude ? [exclude] : [])].join(", ");
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const parts = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.parentElement || node.parentElement.closest(skipped)) continue;
    parts.push(node.nodeValue ?? "");
  }
  return {
    text: parts.join(" ").replace(/\s+/g, " "),
    marked: [...document.querySelectorAll(selector)].map((element) => `${element.tagName.toLowerCase()}.${[...element.classList].join(".")}`),
  };
}

/**
 * The map workspace is the one page that shows the retained ranking. What it may show of it, in a built page or a
 * rendered one: the eight rows of the bundle, each with its own value and its own class, and no other number with one
 * decimal. `rows` are the rows of the ranking rail and `list` the rows of the map's text list, as `{ id | name,
 * score, badge, action_class }`; `text` is the page's text. Returns what differs from the bundle.
 */
export function workspaceRankingProblems({ rows, list, text }, retained) {
  const problems = [];
  const byId = new Map(retained.map((row) => [row.id, row]));
  const byName = new Map(retained.flatMap((row) => [[row.name_en, row], [row.name_th, row]]));
  if (rows.length !== retained.length || new Set(rows.map((row) => row.id)).size !== retained.length) {
    problems.push(`the ranking has ${rows.length} rows for ${retained.length} retained subdistricts`);
  }
  for (const row of rows) {
    const expected = byId.get(row.id);
    if (!expected) problems.push(`the ranking has a row that is not in the bundle: ${row.id}`);
    else if (row.score !== expected.score || row.action_class !== expected.action_class || row.badge.toUpperCase() !== expected.action_class) {
      problems.push(`${row.id} is shown as ${row.score}, class ${row.action_class} (badge ${row.badge}); the bundle has ${expected.score}, class ${expected.action_class}`);
    }
  }
  if (list.length !== retained.length) problems.push(`the map's text list has ${list.length} rows for ${retained.length} retained subdistricts`);
  for (const row of list) {
    const expected = byName.get(row.name);
    if (!expected) problems.push(`the map's text list has a row that is not in the bundle: ${row.name}`);
    else if (row.score !== expected.score || row.action_class !== expected.action_class) {
      problems.push(`the map's text list shows ${row.name} as ${row.score}, class ${row.action_class}; the bundle has ${expected.score}, class ${expected.action_class}`);
    }
  }
  const scores = new Set(retained.map((row) => row.score));
  const classes = new Set(retained.map((row) => row.action_class));
  const strangers = decimalNumbers(text).filter((number) => /^\d+\.\d$/.test(number.value) && !scores.has(number.value)).map((number) => number.value);
  if (strangers.length > 0) problems.push(`a number with one decimal that is not one of the retained values: ${[...new Set(strangers)].join(", ")}`);
  const strangeClasses = [...text.matchAll(WORKSPACE_CLASS)].map((match) => match[1]).filter((letter) => !classes.has(letter));
  if (strangeClasses.length > 0) problems.push(`a class that no retained subdistrict has: ${[...new Set(strangeClasses)].join(", ")}`);
  return problems;
}

/** The rows of the ranking rail and of the map's text list in the built HTML of the map workspace. */
export function readWorkspaceMarkup(html) {
  const plain = html.replace(/<script\b[\s\S]*?<\/script>/g, " ").replace(/<!--[\s\S]*?-->/g, "");
  const rows = [...plain.matchAll(/<span class="rank-name"><b>[^<]*<\/b><small>([^<]*)<\/small><\/span><span class="rank-score class-([a-e])"><b>([^<]*)<\/b><small>(?:Class|ชั้น) ([A-E])<\/small>/g)]
    .map((match) => ({ id: match[1], badge: match[2], score: match[3], action_class: match[4] }));
  const results = plain.match(/<ul class="map-area-results">([\s\S]*?)<\/ul>/)?.[1] ?? "";
  const list = [...results.matchAll(/<button\b[^>]*>([^<:]*): (?:class|ชั้น) ([A-E]), FPPS (\d+\.\d),/g)]
    .map((match) => ({ name: match[1], action_class: match[2], score: match[3] }));
  return { rows, list, text: visibleText(html) };
}

/** Runs in the page (pass it to `page.evaluate`): the same rows, read from the rendered map workspace. */
export function collectWorkspaceRanking() {
  const rows = [...document.querySelectorAll(".ranked-areas ol > li")].map((item) => ({
    id: item.querySelector(".rank-name small")?.textContent?.trim() ?? "",
    badge: [...(item.querySelector(".rank-score")?.classList ?? [])].find((name) => /^class-[a-e]$/.test(name))?.slice(-1) ?? "",
    score: item.querySelector(".rank-score > b")?.textContent?.trim() ?? "",
    action_class: item.querySelector(".rank-score > small")?.textContent?.trim().split(/\s+/).at(-1) ?? "",
  }));
  const list = [...document.querySelectorAll(".map-area-results button")].map((button) => {
    const match = button.textContent?.match(/^(.*?): (?:class|ชั้น) ([A-E]), FPPS (\d+\.\d),/);
    return { name: match?.[1] ?? button.textContent ?? "", action_class: match?.[2] ?? "", score: match?.[3] ?? "" };
  });
  return { rows, list };
}

/**
 * Where the first retained score or class stands in the workspace's text: the first number with one decimal, the
 * first "FPPS <number>" or the first class, whichever comes first. The page's label has to stand before it.
 */
export function firstWorkspaceScoreAt(text) {
  const positions = [
    decimalNumbers(text).find((number) => /^\d+\.\d$/.test(number.value))?.index,
    text.search(new RegExp(SCORE_AFTER_WORD.source)),
    text.search(new RegExp(WORKSPACE_CLASS.source)),
  ].filter((position) => position !== undefined && position >= 0);
  return positions.length > 0 ? Math.min(...positions) : -1;
}
