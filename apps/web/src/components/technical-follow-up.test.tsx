import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { PipelineTopic } from "@/lib/pipeline-progress";
import { describeWordingFindings, findWordingViolations } from "@/lib/replay-wording-lint";
import { ALL_STAGES, BLOCKERS, FOLLOW_UP_TOPICS, followUpTopic, PIPELINE_STEPS } from "@/lib/technical-follow-up";

import { TechnicalFollowUp } from "./technical-follow-up";

const REPOSITORY_ROOT = resolve(process.cwd(), "..", "..");
const PUBLIC_ROOT = resolve(process.cwd(), "public");

function topicText(topic: PipelineTopic): string[] {
  return [
    topic.title, topic.summary, topic.proposal, ...topic.now,
    ...(topic.numbers ?? []).flatMap((number) => [number.label, number.value]),
    ...(topic.chart ? [topic.chart.title, topic.chart.axis, topic.chart.note, ...topic.chart.bars.map((bar) => bar.label)] : []),
    ...(topic.media ?? []).flatMap((media) => [media.alt, media.caption]),
    ...(topic.missing ?? []),
    ...topic.links.map((link) => link.label),
  ];
}

describe("technical follow-up: the data", () => {
  it("draws fourteen stages in four steps, with unique ids", () => {
    expect(PIPELINE_STEPS).toHaveLength(4);
    expect(ALL_STAGES).toHaveLength(14);
    expect(new Set(ALL_STAGES.map((stage) => stage.id)).size).toBe(14);
  });

  it("gives every stage a topic, and keeps the counts the presentation states: 9 run, 3 with limits, 2 not done", () => {
    const counts = { done: 0, in_progress: 0, not_started: 0 };
    for (const stage of ALL_STAGES) {
      const topic = followUpTopic(stage.topic);
      expect(topic, stage.id).toBeDefined();
      counts[topic.status] += 1;
    }
    expect(counts).toEqual({ done: 9, in_progress: 3, not_started: 2 });
  });

  it("links only to files that exist and images this site serves", () => {
    for (const topic of FOLLOW_UP_TOPICS) {
      for (const link of topic.links) if (link.path) expect(existsSync(resolve(REPOSITORY_ROOT, link.path)), link.path).toBe(true);
      for (const media of topic.media ?? []) expect(existsSync(resolve(PUBLIC_ROOT, `.${media.src}`)), media.src).toBe(true);
    }
    for (const image of ["geoai-decisions.png", "uncertainty.png"]) expect(existsSync(resolve(PUBLIC_ROOT, "studio-pipeline", image))).toBe(true);
  });

  it("passes the shared wording lint in every sentence of its own topics and of the blockers", () => {
    const texts = [...FOLLOW_UP_TOPICS.flatMap(topicText), ...BLOCKERS.flatMap((item) => [item.blocker, item.unblock])];
    for (const text of texts) expect(describeWordingFindings(findWordingViolations(text, "technical follow-up")), text).toBe("");
  });
});

describe("technical follow-up: the page", () => {
  const html = renderToStaticMarkup(<TechnicalFollowUp />);

  it("shows the four parts in order, with the pipeline headline", () => {
    const order = ["part-1-title", "part-2-title", "part-3-title", "part-4-title"].map((id) => html.indexOf(`id="${id}"`));
    expect(order.every((position) => position > 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(html).toContain("Data pipeline: 9 of 14 stages run end to end");
  });

  it("makes every stage a button that opens its details, and opens none before a choice", () => {
    for (const stage of ALL_STAGES) expect(html).toContain(`data-stage="${stage.id}"`);
    expect(html.match(/data-stage="/g)).toHaveLength(14);
    expect(html).not.toContain('role="dialog"');
  });

  it("lists every blocker and says what the figures are not", () => {
    for (const item of BLOCKERS) expect(html).toContain(item.blocker.replace(/'/g, "&#x27;"));
    expect(html).toContain("Not real-time and not an official warning.");
  });

  it("passes the shared wording lint outside the image descriptions", () => {
    const text = html.replace(/<img[^>]*>/g, " ").replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"");
    expect(describeWordingFindings(findWordingViolations(text, "technical follow-up page"))).toBe("");
  });
});
