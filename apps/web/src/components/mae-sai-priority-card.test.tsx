import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { TambonProps } from "@/lib/flood-timeline";
import { replayFpps, type ReplayFppsInputs } from "@/lib/replay-fpps";

import { PriorityCard } from "./mae-sai-priority-card";

const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();

const names: Record<string, TambonProps> = {
  T1: { id: "T1", en: "Riverside", th: "ริมน้ำ" },
  T2: { id: "T2", en: "Hillside", th: "บนเขา" },
};

function inputs(confidence: string): ReplayFppsInputs {
  return {
    tambonIds: ["T1", "T2"],
    accessTambons: ["T1", "T2"],
    modelledKm2: { T1: 10, T2: 10 },
    floodedKm2: { T1: 5, T2: 0.1 },
    residents: { T1: 8000, T2: 2000 },
    peopleInWater: { T1: 4000, T2: 10 },
    need: { evacuees: Float64Array.from([4000, 10]), withoutAccess: Float64Array.from([3600, 10]) },
    nodeResidents: [8000, 2000],
    vulnerable: [200, 900],
    roadWeightedKm: { T1: 40, T2: 20 },
    roadWeightedImpassableKm: { T1: 25, T2: 0 },
    confidence,
  };
}

const render = (confidence: string, language: "en" | "th" = "en", phaseId: string | null = "peak") => renderToStaticMarkup(
  <PriorityCard rows={replayFpps(inputs(confidence))} names={names} confidence={confidence} confidenceReason="Terrain model."
    timestamp="2024-09-09/2024-09-19" shelterLabel="the shelters reported in use in Sep 2024" moment="Thu 12 Sep 2024 · 12:00 ICT" phaseId={phaseId} language={language} />,
);

describe("PriorityCard", () => {
  it("ranks subdistricts and gates every class to E under low confidence", () => {
    const html = render("low");
    const plain = text(html);
    expect(html.match(/data-testid="priority-row"/g)).toHaveLength(2);
    expect(plain.indexOf("Riverside")).toBeLessThan(plain.indexOf("Hillside"));
    expect(plain).toContain("Action class is E (Monitor and Verify) for every subdistrict");
    // Every row badge is E; classes A–D appear only as "once verified" steps.
    expect(plain).not.toMatch(/\d\.\d Class [A-D]\b/);
    expect(plain.match(/\d\.\d Class E\b/g)).toHaveLength(2);
    expect(plain).toContain("score implies A");
    expect(plain).toContain("NOT AN OFFICIAL PRIORITY LIST");
    expect(plain).toContain("CONFIDENCE: LOW");
    expect(plain).toContain("Source timestamp");
  });

  it("shows the working: components, weights, points and shares that sum to the score", () => {
    const plain = text(render("low"));
    for (const label of ["Flood likelihood", "Exposure", "Access gap", "Road criticality", "Vulnerability/context"]) expect(plain).toContain(label);
    expect(plain).toContain("FPPS = 0.30 flood likelihood + 0.25 exposure + 0.20 access gap + 0.15 road criticality + 0.10 vulnerability/context");
    expect(plain).toContain("3,600 of 4,000 people whose homes are in water cannot walk");
    expect(plain).toContain("100%");
  });

  it("assigns the score's class once confidence allows it", () => {
    const plain = text(render("medium"));
    expect(plain).not.toContain("Action class is E (Monitor and Verify) for every subdistrict");
    expect(plain).toContain("Class A");
    expect(plain).toContain("High exposure and access loss require life-safety action.");
  });

  it("asks to verify first, then gives the implied class's steps, while confidence is low", () => {
    const html = render("low");
    const plain = text(html);
    expect(plain).toContain("What to do");
    expect(plain).toContain("Step 1 · now Class E — Monitor and Verify");
    expect(plain).toContain("Step 2 · once verified Class A — Protect Lives Now");
    expect(plain).toContain("Pre-position rescue assets, open shelters, issue targeted warnings, and coordinate medical continuity.");
    expect(plain).toContain("Responders and local officials");
    expect(plain).toContain("DDPM (hotline 1784)");
  });

  it("opens the stage that matches the flood phase and marks the next one", () => {
    const peak = render("medium", "en", "peak");
    const block = peak.slice(peak.indexOf('data-testid="playbook-A"'));
    expect(block).toMatch(/<li data-now=""><details open=""><summary><span>2\. While the water is high<\/span><em>Now<\/em>/);
    expect(block).toMatch(/3\. As the water recedes<\/span><em>Next<\/em>/);
    const dry = render("medium", "en", "dry");
    expect(dry).toMatch(/<li data-now=""><details open=""><summary><span>1\. Before the water arrives<\/span><em>Now<\/em>/);
  });

  it("gives one playbook for the assigned class when confidence allows it", () => {
    const html = render("medium");
    const first = html.slice(html.indexOf('data-testid="row-actions"'), html.indexOf('data-testid="priority-row"', html.indexOf('data-testid="row-actions"')));
    expect(first).toContain('data-testid="playbook-A"');
    expect(first).not.toContain('data-testid="playbook-E"');
  });

  it("explains every class A–E", () => {
    const plain = text(render("low"));
    expect(plain).toContain("What the classes A–E mean");
    for (const name of ["Protect Lives Now", "Keep Routes Open", "Protect Essential Services", "Build Resilience", "Monitor and Verify"]) expect(plain).toContain(name);
    expect(plain).toContain("E does not mean no risk");
  });

  it("renders in Thai", () => {
    const plain = text(render("low", "th"));
    expect(plain).toContain("ควรดำเนินการที่ตำบลใดก่อน");
    expect(plain).toContain("ริมน้ำ");
    expect(plain).toContain("คะแนนบ่งชี้ A");
  });
});
