import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  POLICY_ATTENTION, POLICY_GOVERNMENT_POINTS, POLICY_GOVERNMENT_SOURCES, POLICY_GROUND_RULES, POLICY_PROPOSALS, POLICY_QUESTIONS, POLICY_READING,
} from "@/lib/policy-brief";
import { POLICY_CASE } from "@/lib/policy-case";
import { SIGNED_SCORING_FRAME } from "@/lib/policy-evidence";
import { POLICY_ROUTE, POLICY_TECHNICAL_ROUTE } from "@/lib/policy-links";
import { POLICY_WEIGHT_TEST, weightTestShare } from "@/lib/policy-weight-test";
import { PolicyBrief } from "./policy-brief";

const plain = (markup: string) => markup.replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, " ");
const THAI = /[฀-๿]/;
const KO_CHANG = "TH570903";
const MAE_SAI = "TH570901";

describe("plain-language policy page", () => {
  const html = renderToStaticMarkup(<PolicyBrief />);
  const text = plain(html);

  it("follows the order of the policy document: government, proposals, example, score, attention, rules, questions, sources", () => {
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toMatch(/<main[^>]*id="main-content"[^>]*lang="en"|<main[^>]*lang="en"/);
    const ids = ["government", "proposals", "example", "score", "attention", "rules", "questions", "reading"];
    const positions = ids.map((id) => html.indexOf(`<section id="${id}"`));
    positions.forEach((position, index) => expect(position, ids[index]).toBeGreaterThan(index === 0 ? 0 : positions[index - 1]));
    for (const id of ids) expect(html).toContain(`href="#${id}"`);
    expect(text).toContain("Flood maps show where the water goes. We show who could be cut off.");
    expect(text).toContain("Planning support only. Not an official warning. Local officials decide.");
    expect(text).toContain("The government says → so we propose → here is one example → here is who decides.");
    const levels = [...html.matchAll(/<h([1-6])\b/g)].map((match) => Number(match[1]));
    levels.forEach((level, index) => {
      if (index > 0) expect(level - levels[index - 1], `heading ${index}`).toBeLessThanOrEqual(1);
    });
  });

  it("never reads as a warning service, a forecast or a government plan", () => {
    expect(text).not.toMatch(/real-time|live warning|flood forecast|we warn/i);
    expect(text).toContain("POLICY BRIEF · PROPOSAL");
    expect(text).toContain("None replaces an official plan.");
    expect(text).toContain("E never means safe.");
    expect(text).toContain("No. These are our proposals. No agency has adopted them.");
    expect(text).toContain("FloodGuard does not issue warnings, order evacuations, allocate budgets or decide who receives relief.");
  });

  it("gives each of the three government points its words, its meaning and a link to each source it names", () => {
    expect(POLICY_GOVERNMENT_POINTS).toHaveLength(3);
    const known = new Map(POLICY_GOVERNMENT_SOURCES.map((source) => [source.id, source]));
    for (const point of POLICY_GOVERNMENT_POINTS) {
      expect(text).toContain(point.title.en);
      expect(text).toContain(point.says.en);
      expect(text).toContain(point.means.en);
      expect(point.sources.length).toBeGreaterThan(0);
      for (const item of point.sources) {
        expect(known.has(item.source), `${point.id}: ${item.source}`).toBe(true);
        expect(html).toContain(`<a href="${known.get(item.source)!.url}">${item.label.en}</a>`);
      }
    }
    // The figures of the Chiang Rai release of 15 May 2026, as the release gives them.
    expect(text).toContain("about 2.9 billion baht");
    expect(text).toContain("about 4 hours’ notice for Mae Sai and 9–12 hours for Chiang Rai city");
    expect(text).toContain("a tabletop exercise on 20 May 2026 (about 350 people) and a field exercise on 22 May (about 890 people)");
  });

  it("gives each proposal what it is, why now, what FloodGuard supplies and who decides", () => {
    expect(POLICY_PROPOSALS).toHaveLength(3);
    for (const proposal of POLICY_PROPOSALS) {
      for (const part of [proposal.title, proposal.what, proposal.whyNow, proposal.supplies, proposal.decides]) {
        expect(text).toContain(part.en);
        expect(part.th).toMatch(THAI);
      }
    }
    expect(html.match(/Who decides/g)!.length).toBe(3);
  });

  it("prints the example from the published case, never from typed figures", () => {
    const row = (unit: string) => POLICY_CASE.rows.find((item) => item.unit_id === unit)!;
    const koChang = row(KO_CHANG);
    const maeSai = row(MAE_SAI);
    const count = (value: number) => Math.round(value).toLocaleString("en-US");
    expect(text).toContain(`${Math.round((koChang.residents_inside_the_layer / koChang.residents) * 100)}% of residents live inside the flooded area`);
    expect(text).toContain(`(${count(koChang.residents_losing_every_route)} of ${count(koChang.residents_with_a_route_before)}) loses all routes`);
    // "Every resident who had a road route" is said only because the two counts are equal in the published case.
    expect(koChang.residents_losing_every_route).toBe(koChang.residents_with_a_route_before);
    expect(text).toContain(`${koChang.fpps_0_100.toFixed(1)} / 100`);
    expect(text).toContain(`${maeSai.fpps_0_100.toFixed(1)} / 100`);
    expect(text).toContain(`(${count(maeSai.residents_losing_every_route)} of ${count(maeSai.residents_with_a_route_before)}) lose every route`);
    // "More people lose hospital access here than anywhere else": true of the published rows.
    expect(Math.max(...POLICY_CASE.rows.map((item) => item.residents_losing_hospital_access))).toBe(maeSai.residents_losing_hospital_access);
    expect(text).toContain(`More people lose hospital access here (${count(maeSai.residents_losing_hospital_access)}) than anywhere else.`);
    // The classes the two sentences name are the published ones.
    expect([koChang.action_class, maeSai.action_class]).toEqual(["B", "D"]);
    expect(text).toContain("Suggested attention: keep routes open.");
    expect(text).toContain("Suggested attention: build resilience.");
    expect(text).toContain("this is a scenario, not a real day.");
    expect(text).toContain("Use it to decide what to check first, not what to do.");
  });

  it("states the five weights of the signed frame and what each part counts in the published score", () => {
    const weights = SIGNED_SCORING_FRAME.components.map((component) => Math.round(component.weight * 100));
    expect(weights).toEqual([30, 25, 20, 15, 10]);
    const five = html.slice(html.indexOf('data-testid="policy-five-things"'));
    for (const weight of weights) expect(five).toContain(`>${weight}%<`);
    expect(text).toContain("How much land floods");
    expect(text).toContain("Who lives in the flooded area");
    // The published score counts a hospital and a main road.
    expect(text).toContain("Who loses access they had to a hospital or a main road");
    expect(text).toContain("Who loses every route");
    expect(text).toContain("How many children and older people live there");
    expect(text).toContain("These weights are our choices, open for review. They are not Thai warning levels.");
    expect(text).toContain("A score of 65 out of 100 does not mean a 65% chance of flooding.");
  });

  it("reports the weight test from its file: what holds, and the one weighting under which it does not", () => {
    const test = POLICY_WEIGHT_TEST;
    expect(test.label).toBe("Report only. It changes no score, weight or class.");
    expect(test.published.order[0]).toBe(KO_CHANG);
    const equal = test.named.find((item) => item.id === "equal")!;
    expect(text).toContain(`With five equal weights Ko Chang is still first: ${equal.scores[KO_CHANG].toFixed(1)} against ${equal.scores[MAE_SAI].toFixed(1)} for Mae Sai town.`);
    const firsts = test.one_at_a_time.filter((item) => item.first === KO_CHANG).length;
    const same = test.one_at_a_time.filter((item) => item.same_order).length;
    expect(test.one_at_a_time).toHaveLength(10);
    // Both hold in every case of the committed report, so the page says "all"; the other wording is for a report where they do not.
    expect([firsts, same]).toEqual([10, 10]);
    expect(text).toContain("Ko Chang stays first in all 10 cases and the order of the eight tambons does not change.");
    expect(text).toContain(`Across ${test.random.draws.toLocaleString("en-US")} random sets of weights, Ko Chang is first in ${weightTestShare(test.random.share_first[KO_CHANG])}`);
    // The page does not hide the weighting that turns the order: without the two access parts Ko Chang is not first.
    const without = test.named.find((item) => item.id === "without_access")!;
    expect(without.order[0]).not.toBe(KO_CHANG);
    expect(text).toContain(`Only when the two access parts are left out does ${test.units[without.order[0]].en} come first.`);
    expect(text).toContain("No study gives the right weights for a score like this.");
    expect(text).toContain("Report only: the test changes no score, weight or class.");
    // A share is never rounded up to a certainty.
    expect(weightTestShare(0.9996)).toBe("99.9%");
    expect(weightTestShare(1)).toBe("100%");
    expect(weightTestShare(0.9121)).toBe("91%");
    expect(weightTestShare(0.9983)).toBe("99.8%");
  });

  it("lists the five kinds of attention, the ground rules and the questions of the document", () => {
    expect(POLICY_ATTENTION.map((item) => item.letter)).toEqual(["A", "B", "C", "D", "E"]);
    for (const item of POLICY_ATTENTION) expect(text).toContain(`${item.title.en} ${item.text.en}`);
    expect(POLICY_GROUND_RULES).toHaveLength(4);
    for (const rule of POLICY_GROUND_RULES) expect(text).toContain(`${rule.title.en} ${rule.text.en}`);
    expect(POLICY_QUESTIONS).toHaveLength(6);
    for (const item of POLICY_QUESTIONS) expect(text).toContain(`${item.question.en} ${item.answer.en}`);
  });

  it("links every source over https, once, and says what the page takes from each paper", () => {
    const readings = POLICY_READING.flatMap((group) => group.items);
    const urls = [...POLICY_GOVERNMENT_SOURCES.map((item) => item.url), ...readings.map((item) => item.url)];
    expect(new Set(urls).size).toBe(urls.length);
    for (const url of urls) {
      expect(url).toMatch(/^https:\/\/[a-z0-9.-]+\//);
      expect(html).toContain(`href="${url}"`);
    }
    expect(readings.length).toBeGreaterThanOrEqual(20);
    expect(new Set(readings.map((item) => item.id)).size).toBe(readings.length);
    for (const item of readings) {
      expect(item.use.en.length, item.id).toBeGreaterThan(40);
      expect(item.use.th, item.id).toMatch(THAI);
      expect(text).toContain(item.use.en);
    }
    // A peer-reviewed paper is linked by its DOI.
    for (const item of POLICY_READING.filter((group) => group.id !== "frameworks").flatMap((group) => group.items)) {
      if (item.id === "marks-2016" || item.id === "hallegatte-2019" || item.id === "oecd-2008") continue;
      expect(item.url, item.id).toMatch(/^https:\/\/doi\.org\/10\.\d{4,}\//);
    }
    expect(text).toContain("none endorses FloodGuard, and none gives our five weights");
  });

  it("links the technical record and says who wrote the Thai", () => {
    expect(POLICY_ROUTE).toBe("/policy/");
    expect(POLICY_TECHNICAL_ROUTE).toBe("/policy/technical/");
    expect(html).toContain(`href="${POLICY_TECHNICAL_ROUTE}"`);
    expect(html).toContain(`href="${POLICY_TECHNICAL_ROUTE}#case"`);
    expect(html).toContain(`href="${POLICY_TECHNICAL_ROUTE}#signed-frame"`);
    expect(text).toContain("The Thai text of this page was written by the project’s AI assistant and has not been reviewed by a native speaker.");
    const source = readFileSync(resolve(process.cwd(), "src/lib/policy-brief.ts"), "utf8");
    // Every English sentence of the page's text file has a Thai one.
    expect(source.match(/\ben: "/g)!.length).toBe(source.match(/\bth: "/g)!.length);
  });
});
