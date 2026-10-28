import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { figuresOfTopic, PIPELINE_FIGURES } from "@/lib/pipeline-figures";
import { linkHref, PIPELINE_TOPICS, statusCounts, TOPIC_BY_ID, type PipelineTopic } from "@/lib/pipeline-progress";
import { describeWordingFindings, findWordingViolations } from "@/lib/replay-wording-lint";

import { PipelineExplorer } from "./pipeline-explorer";

const REPOSITORY_ROOT = resolve(process.cwd(), "..", "..");
const PUBLIC_ROOT = resolve(process.cwd(), "public");
const BOXES = PIPELINE_FIGURES.flatMap((figure) => figure.boxes);

/** Every string the project wrote for a topic (box labels and captions are the proposal's own wording and stay as submitted). */
function topicText(topic: PipelineTopic): string[] {
  return [
    topic.title, topic.summary, topic.proposal, ...topic.now,
    ...(topic.numbers ?? []).flatMap((number) => [number.label, number.value]),
    ...(topic.chart ? [topic.chart.title, topic.chart.axis, topic.chart.note, topic.chart.rule?.label ?? "", ...topic.chart.bars.map((bar) => bar.label)] : []),
    ...(topic.media ?? []).flatMap((media) => [media.alt, media.caption]),
    ...(topic.missing ?? []),
    ...topic.links.map((link) => link.label),
  ];
}

describe("pipeline progress: the figures and their topics", () => {
  it("redraws the five figures of the proposal, numbered 1 to 5, with unique box ids", () => {
    expect(PIPELINE_FIGURES.map((figure) => figure.number)).toEqual([1, 2, 3, 4, 5]);
    const ids = BOXES.map((box) => box.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("points every box at a topic, and draws every topic in at least one figure", () => {
    for (const box of BOXES) expect(TOPIC_BY_ID[box.topic], box.id).toBeDefined();
    for (const topic of PIPELINE_TOPICS) expect(figuresOfTopic(topic.id).length, topic.id).toBeGreaterThan(0);
    expect(new Set(PIPELINE_TOPICS.map((topic) => topic.id)).size).toBe(PIPELINE_TOPICS.length);
  });

  it("keeps every box inside its figure", () => {
    for (const figure of PIPELINE_FIGURES) {
      for (const box of figure.boxes) {
        expect(box.x >= 0 && box.y >= 0, box.id).toBe(true);
        expect(box.x + box.w <= figure.width && box.y + box.h <= figure.height, box.id).toBe(true);
      }
    }
  });

  it("counts a topic once however often it is drawn", () => {
    const counts = statusCounts(BOXES.map((box) => box.topic));
    expect(counts.done + counts.in_progress + counts.not_started).toBe(PIPELINE_TOPICS.length);
  });

  it("names what is missing for every piece of work that is not done", () => {
    for (const topic of PIPELINE_TOPICS.filter((item) => item.status !== "done")) {
      expect((topic.missing?.length ?? 0) + topic.now.length, topic.id).toBeGreaterThan(0);
    }
  });

  it("draws every chart within its own scale", () => {
    for (const topic of PIPELINE_TOPICS) {
      if (!topic.chart) continue;
      for (const bar of topic.chart.bars) expect(bar.value >= 0 && bar.value <= topic.chart.max, `${topic.id} ${bar.label}`).toBe(true);
      if (topic.chart.rule) expect(topic.chart.rule.value <= topic.chart.max).toBe(true);
    }
  });

  it("links only to files that exist in the repository and to images this site serves", () => {
    for (const topic of PIPELINE_TOPICS) {
      for (const link of topic.links) {
        if (link.path) expect(existsSync(resolve(REPOSITORY_ROOT, link.path)), `${topic.id}: ${link.path}`).toBe(true);
        expect(link.path || link.href, `${topic.id}: ${link.label}`).toBeTruthy();
      }
      for (const media of topic.media ?? []) expect(existsSync(resolve(PUBLIC_ROOT, `.${media.src}`)), `${topic.id}: ${media.src}`).toBe(true);
    }
    expect(linkHref({ label: "x", path: "docs/a.md" })).toBe("https://github.com/TUPRAM/flood-guard/blob/master/docs/a.md");
  });

  it("passes the shared wording lint in every sentence the project wrote", () => {
    for (const topic of PIPELINE_TOPICS) {
      for (const text of topicText(topic)) expect(describeWordingFindings(findWordingViolations(text, topic.id)), text).toBe("");
    }
  });
});

describe("pipeline progress: the page", () => {
  const html = renderToStaticMarkup(<PipelineExplorer />);

  it("shows each figure under its number and the proposal's caption, then the figure", () => {
    for (const figure of PIPELINE_FIGURES) {
      expect(html).toContain(`Figure ${figure.number}.</span> ${figure.caption.replace(/&/g, "&amp;")}`);
      expect(html).toContain(`data-figure="${figure.id}"`);
    }
  });

  it("makes every box a control, in the figure and in the list under it", () => {
    for (const box of BOXES) expect(html.match(new RegExp(`data-box="${box.id}"`, "g"))?.length, box.id).toBe(2);
    expect(html.match(/role="button"/g)?.length).toBe(BOXES.length);
  });

  it("states the limits and opens no details panel before a box is chosen", () => {
    expect(html).toContain("not an observation of a flood");
    expect(html).toContain("not a real-time product or an official warning");
    expect(html).not.toContain('role="dialog"');
  });

  it("passes the shared wording lint outside the proposal's own labels", () => {
    const own = html
      .replace(/<svg[\s\S]*?<\/svg>/g, " ")
      .replace(/<h2[\s\S]*?<\/h2>/g, " ")
      .replace(/<ul class="[^"]*chips[\s\S]*?<\/ul>/g, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/&#x27;/g, "'");
    expect(describeWordingFindings(findWordingViolations(own, "pipeline page"))).toBe("");
  });
});
