import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PLANNING_OVERVIEW_ROUTE, PLANNING_WORKSPACE_ROUTE } from "@/lib/case-selection";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";

import { CandidateCaseContext } from "./candidate-case-context";
import { CommandArchiveForward, commandArchiveForwardTarget } from "./command-archive-forward";
import { CommandWorkspace } from "./command-workspace";
import { EvidenceLibrary } from "./evidence-library";
import { PlanningCandidateOverview } from "./planning-candidate-overview";

const preference = vi.hoisted(() => ({ language: "en" as "en" | "th" }));
vi.mock("@/lib/use-language", () => ({ useLanguage: () => [preference.language, vi.fn()] }));

/** The text a reader sees, in page order. */
const visible = (html: string) => html.replace(/<!-- -->/g, "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
const SCORE = /FPPS\s*\d+(?:\.\d+)?/g;
const CLASS = /(?:(?<![A-Za-z])[Cc]lass|ชั้น)\s+[A-E](?![A-Za-z])/g;

/**
 * The three Planning addresses since the owner's request of 5 Oct 2026 (decision log R19): the map workspace is the
 * default page at /command/, the candidate planning overview is at /command/ver2/, and /command/archive/ forwards.
 *
 * The route files under src/app/command/ are not imported here: the public-production build moves that folder
 * aside and still type-checks every test. These are the components each route file renders; the built pages, their
 * titles and their addresses are checked by scripts/offline-smoke.mjs and scripts/browser-offline-smoke.mjs.
 */
const workspacePage = () => <CommandWorkspace />;
const overviewPage = () => <><CandidateCaseContext role="planning" /><PlanningCandidateOverview /></>;
const forwardPage = () => <CommandArchiveForward />;

describe("Planning pages after the swap of 5 Oct 2026", () => {
  beforeEach(() => { preference.language = "en"; });

  it("keeps the two addresses apart", () => {
    expect(PLANNING_WORKSPACE_ROUTE).toBe("/command/");
    expect(PLANNING_OVERVIEW_ROUTE).toBe("/command/ver2/");
  });

  it("serves the map workspace at /command/, with its label before any of its retained scores, in both languages", () => {
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
      // The header's Planning link is this page.
      expect(html).toContain(`<a href="/command/" aria-current="page">${language === "th" ? "การวางแผน" : "Planning"}</a>`);
    }
  });

  it("serves the planning overview at /command/ver2/ with no research score or class, and a link back to the map workspace", () => {
    for (const [language, back, planning] of [
      ["en", "Back to the map workspace", "Planning"],
      ["th", "กลับไปที่พื้นที่ทำงานแผนที่", "การวางแผน"],
    ] as const) {
      preference.language = language;
      const html = renderToStaticMarkup(overviewPage());
      const text = visible(html);
      expect(html).toContain("data-planning-candidate=");
      expect(html).toContain('data-shared-case="planning"');
      expect(html).not.toContain('class="command-page');
      expect([...text.matchAll(SCORE), ...text.matchAll(CLASS)].map((match) => match[0])).toEqual([]);
      // The notice of the overview: where the historical report is kept, and nothing about a ranking on this page.
      expect(html).toContain('data-research-report-notice="true"');
      expect(html).not.toContain("data-research-retained-ranking");
      // The link back is there before any case has loaded, and it leads to /command/, not to the old archive address.
      expect(html).toContain(`<a href="/command/" data-planning-workspace-link="true">← ${back}</a>`);
      expect(html).not.toContain('href="/command/archive/');
      // The header's Planning link leads to another page, the workspace: it marks the section, not the current page.
      expect(html).toContain(`<a href="/command/" aria-current="true">${planning}</a>`);
      expect(html).not.toContain(`aria-current="page">${planning}</a>`);
    }
  });

  it("marks no Planning link on the Studio view of the shared case", () => {
    const html = renderToStaticMarkup(<CandidateCaseContext role="studio" />);
    expect(html).toContain('<a href="/command/">Planning</a>');
    expect(html).toContain('aria-current="page">Studio</a>');
  });

  it("leaves a sentence, a link and no content of its own at /command/archive/", () => {
    const html = renderToStaticMarkup(forwardPage());
    const text = visible(html);
    expect(html).toContain('data-command-forward="/command/"');
    expect(html).toContain('<p lang="en">This page has moved. The Planning map workspace is now at <a href="/command/">/command/</a>.</p>');
    expect(html).toContain('<p lang="th">หน้านี้ย้ายแล้ว พื้นที่ทำงานแผนที่สำหรับการวางแผนอยู่ที่ <a href="/command/">/command/</a></p>');
    expect([...text.matchAll(SCORE), ...text.matchAll(CLASS)].map((match) => match[0])).toEqual([]);
    expect(html).not.toMatch(/data-research-report-notice|rank-score|command-page|data-planning-candidate|<table|<h1|<h2/);
    // The old link's query and fragment go with the reader.
    expect(commandArchiveForwardTarget("", "")).toBe("/command/");
    expect(commandArchiveForwardTarget("?aoi=aoi-01_mae_sai_core&event=mae_sai_2024", "#main-content"))
      .toBe("/command/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024#main-content");
  });

  it("points the comparison page's links at the page each one means", () => {
    const { catalog, evidence } = evidenceFixtures();
    for (const [language, overview, workspace, planning] of [
      ["en", "Overview", "Map workspace", "Planning"],
      ["th", "ภาพรวม", "พื้นที่ทำงานแผนที่", "การวางแผน"],
    ] as const) {
      preference.language = language;
      const html = renderToStaticMarkup(<EvidenceLibrary view="brief" role="planning" initialCatalog={catalog} initialPackage={evidence} />);
      expect(html).toMatch(new RegExp(`<a href="/command/ver2/[^"]*">${overview}</a>`));
      expect(html).toMatch(new RegExp(`<a href="/command/(?:\\?[^"]*)?">${workspace}</a>`));
      expect(html).toMatch(new RegExp(`<a href="/command/(?:\\?[^"]*)?"[^>]*>${planning}</a>`));
      expect(html).not.toContain('href="/command/archive/');
    }
  });
});
