import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FORWARDED_ROUTES, PLANNING_OVERVIEW_ROUTE, PLANNING_WORKSPACE_ROUTE, RESEARCH_WORKSPACE_ROUTE } from "@/lib/case-selection";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";

import { CandidateCaseContext } from "./candidate-case-context";
import { CommandArchiveForward, CommandExerciseForward, PlanningOverviewForward, commandArchiveForwardTarget, forwardTarget } from "./command-archive-forward";
import { CommandCaseNoticeLine } from "./command-case-notice";
import { CommandWorkspace } from "./command-workspace";
import { EvidenceLibrary } from "./evidence-library";
import { PlanningCandidateOverview } from "./planning-candidate-overview";

const preference = vi.hoisted(() => ({ language: "en" as "en" | "th" }));
vi.mock("@/lib/use-language", () => ({ useLanguage: () => [preference.language, vi.fn()] }));

/** The text a reader sees, in page order. */
const visible = (html: string) => html.replace(/<!-- -->/g, "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
// The written forms of a research score or class, as scripts/research-score-guard.mjs lists them for the build checks:
// the word FPPS followed in the same sentence by a number, and a class followed by a letter A to E.
const SCORE = /FPPS[^.!?]{0,40}?\d+(?:\.\d+)?/g;
const CLASS = /(?:(?<![A-Za-z])(?:[Cc]lass(?:es)?|CLASS(?:ES)?)\W{0,3}|(?:ชั้น|ระดับ)[^\sA-Za-z0-9]{0,24}\s{0,2})[A-E](?![A-Za-z0-9])/g;
// The ranking's own markup, which only the map workspace has.
const RANKING_MARKUP = /class="[^"]*\b(?:rank-score|fpps-block|decision-class|action-class-legend|class-[a-e])\b/;

/**
 * The Planning addresses since the owner's decision of 7 Oct 2026 (decision log R24): the Command exercise replay is
 * the default page at /command/ (it has tests of its own), the candidate planning overview is at /command/planning/,
 * the older map workspace is historical research in Studio's archive, and the three earlier addresses forward.
 *
 * The route files under src/app/command/ are not imported here: the public-production build moves that folder
 * aside and still type-checks every test. These are the components each route file renders; the built pages, their
 * titles and their addresses are checked by scripts/offline-smoke.mjs and scripts/browser-offline-smoke.mjs.
 *
 * The overview is rendered here as it is before a case has loaded (these tests run no effect). The page with its
 * case loaded is checked for research scores in the browser, in English and in Thai, by browser-offline-smoke.mjs.
 */
const workspacePage = () => <CommandWorkspace />;
const overviewPage = () => <><CandidateCaseContext role="planning" /><PlanningCandidateOverview /></>;

describe("Planning pages after the swap of 7 Oct 2026", () => {
  beforeEach(() => { preference.language = "en"; });

  it("keeps the addresses apart, and says where each earlier address leads", () => {
    expect(PLANNING_WORKSPACE_ROUTE).toBe("/command/");
    expect(PLANNING_OVERVIEW_ROUTE).toBe("/command/planning/");
    expect(RESEARCH_WORKSPACE_ROUTE).toBe("/studio/archive/command-workspace/");
    expect(FORWARDED_ROUTES).toEqual({
      "/command/exercise/": "/command/",
      "/command/ver2/": "/command/planning/",
      "/command/archive/": "/studio/archive/command-workspace/",
    });
  });

  it("keeps the older map workspace in Studio's archive, with its label before any of its retained scores, in both languages", () => {
    for (const [language, label, summary] of [
      ["en", "Subdistrict scores and classes below are retained research comparisons, not accepted event-response priorities.",
        "The FPPS and class below are retained research comparisons, not accepted event-response priorities."],
      ["th", "คะแนนและชั้นของตำบลในแม่สายด้านล่างเป็นผลวิจัยที่เก็บไว้เพื่อเปรียบเทียบ ไม่ใช่การจัดอันดับรับมือเหตุการณ์ที่ยอมรับแล้ว",
        "คะแนน FPPS และชั้นด้านล่างเป็นการเปรียบเทียบงานวิจัยเดิม ไม่ใช่ลำดับรับมือเหตุการณ์ที่ยอมรับแล้ว"],
    ] as const) {
      preference.language = language;
      const html = renderToStaticMarkup(workspacePage());
      const text = visible(html);
      expect(html).toContain('class="command-page');
      expect(html).not.toContain("data-planning-candidate");
      // Eight retained scores in the ranking rail, and the label of the page before the first of them. The
      // small-screen summary repeats the label before its own readout.
      const scores = [...text.matchAll(SCORE)];
      const classes = [...text.matchAll(CLASS)];
      const rail = [...html.matchAll(/<span class="rank-score class-[a-e]"><b>(\d+\.\d)<\/b>/g)];
      expect(rail).toHaveLength(8);
      expect(scores.length).toBeGreaterThan(0);
      expect(classes.length).toBeGreaterThan(0);
      const labelAt = text.indexOf(label);
      expect(labelAt).toBeGreaterThan(-1);
      expect(labelAt).toBeLessThan(scores[0].index);
      expect(labelAt).toBeLessThan(classes[0].index);
      expect(html.indexOf(label)).toBeLessThan(html.indexOf('class="rank-score'));
      expect(text.indexOf(summary)).toBeGreaterThan(-1);
      expect(text.indexOf(summary)).toBeLessThan(scores[0].index);
      // Its notice names the retained ranking as a comparison apart from the GeoAI report's table.
      expect(html).toContain('data-research-retained-ranking="true"');
      // A link to the other Planning page, in the banner and in the small-screen summary.
      expect(html).toContain(`<a href="${PLANNING_OVERVIEW_ROUTE}" data-planning-overview-link="true">${language === "th" ? "ภาพรวมปัจจุบัน" : "Current planning overview"}</a>`);
      expect(html).toContain(`<a href="${PLANNING_OVERVIEW_ROUTE}">${language === "th" ? "เปิดภาพรวมกรณีศึกษาปัจจุบัน" : "Open the current candidate overview"}</a>`);
      // The header marks the Studio section: the page is historical research, and no Planning page.
      expect(html).toContain(`<a href="/studio/" aria-current="true">${language === "th" ? "สตูดิโอ" : "Studio"}</a>`);
      expect(html).toContain(`<a href="/command/">${language === "th" ? "การวางแผน" : "Planning"}</a>`);
    }
  });

  it("serves the planning overview at /command/planning/ with no research score or class, and a link to the default Planning page", () => {
    for (const [language, back, planning] of [
      ["en", "To the Command exercise replay", "Planning"],
      ["th", "ไปที่หน้าฝึกซ้อมสั่งการ", "การวางแผน"],
    ] as const) {
      preference.language = language;
      const html = renderToStaticMarkup(overviewPage());
      const text = visible(html);
      expect(html).toContain("data-planning-candidate=");
      expect(html).toContain('data-shared-case="planning"');
      expect(html).not.toContain('class="command-page');
      expect([...text.matchAll(SCORE), ...text.matchAll(CLASS)].map((match) => match[0])).toEqual([]);
      expect(html).not.toMatch(RANKING_MARKUP);
      // The notice of the overview: where the historical report is kept, and nothing about a ranking on this page.
      expect(html).toContain('data-research-report-notice="true"');
      expect(html).not.toContain("data-research-retained-ranking");
      // The link is there before any case has loaded, and it leads to /command/, not to an address that only forwards.
      expect(html).toContain(`<a href="/command/" data-planning-workspace-link="true">← ${back}</a>`);
      expect(html).not.toContain('href="/command/archive/');
      // The header's Planning link leads to another page, the exercise replay: it marks the section, not the current page.
      expect(html).toContain(`<a href="/command/" aria-current="true">${planning}</a>`);
      expect(html).not.toContain(`aria-current="page">${planning}</a>`);
    }
  });

  it("marks no Planning link on the Studio view of the shared case", () => {
    const html = renderToStaticMarkup(<CandidateCaseContext role="studio" />);
    expect(html).toContain('<a href="/command/">Planning</a>');
    expect(html).toContain('aria-current="page">Studio</a>');
  });

  it("leaves a sentence, a link and no content of its own at each address that has moved", () => {
    for (const [page, to, english, thai] of [
      [<CommandArchiveForward key="archive" />, "/studio/archive/command-workspace/",
        "This page has moved. The older Planning map workspace, kept as historical research, is now at",
        "หน้านี้ย้ายแล้ว พื้นที่ทำงานแผนที่เดิมซึ่งเก็บไว้เป็นงานวิจัยย้อนหลังอยู่ที่"],
      [<PlanningOverviewForward key="ver2" />, "/command/planning/", "This page has moved. The planning overview is now at", "หน้านี้ย้ายแล้ว ภาพรวมเพื่อการวางแผนอยู่ที่"],
      [<CommandExerciseForward key="exercise" />, "/command/", "This page has moved. The Command exercise replay is now at", "หน้านี้ย้ายแล้ว หน้าฝึกซ้อมสั่งการอยู่ที่"],
    ] as const) {
      const html = renderToStaticMarkup(page).replace(/<!-- -->/g, "");
      const text = visible(html);
      expect(html).toContain(`data-command-forward="${to}"`);
      expect(html).toContain(`<p lang="en">${english} <a href="${to}">${to}</a>.</p>`);
      expect(html).toContain(`<p lang="th">${thai} <a href="${to}">${to}</a></p>`);
      expect([...text.matchAll(SCORE), ...text.matchAll(CLASS)].map((match) => match[0])).toEqual([]);
      expect(html).not.toMatch(RANKING_MARKUP);
      expect(html).not.toMatch(/data-research-report-notice|command-page|data-planning-candidate|<table|<h1|<h2/);
    }
    // The old link's query and fragment go with the reader.
    expect(commandArchiveForwardTarget("", "")).toBe("/studio/archive/command-workspace/");
    expect(commandArchiveForwardTarget("?aoi=aoi-01_mae_sai_core&event=mae_sai_2024", "#main-content"))
      .toBe("/studio/archive/command-workspace/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024#main-content");
    expect(forwardTarget("/command/", "?t=84&lang=th", "")).toBe("/command/?t=84&lang=th");
    expect(forwardTarget("/command/planning/", "?aoi=aoi-05", "#main-content")).toBe("/command/planning/?aoi=aoi-05#main-content");
  });

  it("names the case a link carried to the exercise page, and leads to that case's planning overview", () => {
    // A "Planning" link of a published brief is /command/?aoi=...: the exercise replay does not read the case.
    const search = "?aoi=aoi-01_mae_sai_core&event=mae_sai_2024";
    const english = renderToStaticMarkup(<CommandCaseNoticeLine search={search} language="en" catalog={null} page="exercise" />);
    expect(english).toContain("This page replays the Mae Sai flood of September 2024 as an exercise. It does not show the results of that case.");
    expect(english).toContain('href="/command/planning/?aoi=aoi-01_mae_sai_core&amp;event=mae_sai_2024" data-command-case-overview-link="true"');
    expect(english).not.toContain("retained Mae Sai research comparison");
    const thai = renderToStaticMarkup(<CommandCaseNoticeLine search={search} language="th" catalog={null} page="exercise" />);
    expect(thai).toContain("หน้านี้เป็นการฝึกซ้อมย้อนเหตุการณ์น้ำท่วมแม่สาย เดือนกันยายน 2567 (2024) และไม่ได้แสดงผลของกรณีศึกษานั้น");
    // No case in the address, no line.
    expect(renderToStaticMarkup(<CommandCaseNoticeLine search="?t=84&lang=en" language="en" catalog={null} page="exercise" />)).toBe("");
  });

  it("points the comparison page's links at the page each one means", () => {
    const { catalog, evidence } = evidenceFixtures();
    for (const [language, overview, workspace, planning] of [
      ["en", "Overview", "Command exercise", "Planning"],
      ["th", "ภาพรวม", "ฝึกซ้อมสั่งการ", "การวางแผน"],
    ] as const) {
      preference.language = language;
      const html = renderToStaticMarkup(<EvidenceLibrary view="brief" role="planning" initialCatalog={catalog} initialPackage={evidence} />);
      expect(html).toMatch(new RegExp(`<a href="/command/planning/[^"]*">${overview}</a>`));
      expect(html).toMatch(new RegExp(`<a href="/command/(?:\\?[^"]*)?">${workspace}</a>`));
      // The header's Planning link leads to the exercise replay, another page: it marks the section. The one page this
      // header names as current is the comparison page itself, in the row of pages below it.
      expect(html).toMatch(new RegExp(`<a href="/command/(?:\\?[^"]*)?" aria-current="true">${planning}</a>`));
      expect(html.match(/aria-current="page"/g)).toHaveLength(1);
      expect(html).toMatch(/<a href="\/command\/cases\/[^"]*" aria-current="page">/);
      expect(html).not.toContain('href="/command/archive/');
    }
  });
});
