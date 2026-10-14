import { describe, expect, it } from "vitest";

import { TIMELINE, segmentRange, stopPosition, type SegmentId } from "@/lib/journey/timeline";
import { describeWordingFindings, findWordingViolations } from "@/lib/replay-wording-lint";

import { CAPTIONS, CHAPTER_LABELS, CHARACTERS, LABELS, MONITOR, STOPS, UI, type CharacterId } from "./journey-copy";

/** Every caption, with its timeline position (its pause, or its start). */
const placedCaptions = (Object.keys(CAPTIONS) as SegmentId[]).flatMap((segment) => {
  const { start, end } = segmentRange(segment);
  return CAPTIONS[segment].map((caption) => ({ caption, at: start + (end - start) * (caption.pause ?? caption.from) }));
}).sort((a, b) => a.at - b.at);

describe("journey story copy", () => {
  it("passes the shared wording lint in both languages", () => {
    const texts = [
      ...Object.values(UI), ...Object.values(LABELS), ...Object.values(MONITOR),
      ...Object.values(CHAPTER_LABELS).map((chapter) => chapter.title),
      ...Object.values(CHARACTERS).flatMap((person) => [person.name, person.role, person.question]),
      ...placedCaptions.flatMap(({ caption }) => [caption.eyebrow, caption.text, ...(caption.points ?? [])]),
      ...Object.values(STOPS).flatMap((stop) => [stop.page, stop.note, stop.continueLabel, stop.warning]),
    ].filter((text) => text !== undefined);
    for (const language of ["en", "th"] as const) {
      const findings = texts.flatMap((text) => findWordingViolations(text[language], `journey copy (${language})`));
      expect(findings, describeWordingFindings(findings)).toEqual([]);
    }
  });

  it("introduces each person once, before any caption or real page is theirs", () => {
    const met = new Map<CharacterId, number>();
    for (const { caption, at } of placedCaptions) {
      if (!caption.meet || !caption.who) continue;
      expect(met.has(caption.who), `${caption.who} is introduced twice`).toBe(false);
      met.set(caption.who, at);
    }
    expect([...met.keys()].sort()).toEqual((Object.keys(CHARACTERS) as CharacterId[]).sort());
    for (const { caption, at } of placedCaptions) if (caption.who) expect(at).toBeGreaterThanOrEqual(met.get(caption.who)!);
    for (const item of TIMELINE) {
      if (item.kind === "stop") expect(stopPosition(item.id)).toBeGreaterThan(met.get(STOPS[item.id].who)!);
    }
  });

  it("follows Lalita, then Narin, then Pim, each with their own real page", () => {
    expect(STOPS.public.who).toBe("lalita");
    expect(STOPS["public-prepare"].who).toBe("lalita");
    expect(STOPS.case.who).toBe("narin");
    expect(STOPS.command.who).toBe("pim");
    expect(STOPS.public.tab).toBe("home");
    expect(STOPS["public-prepare"].tab).toBe("prepare");
  });

  it("keeps the request for help simulated and outside FloodGuard", () => {
    const call = placedCaptions.find(({ caption }) => caption.text.en.includes("1784"));
    expect(call).toBeDefined();
    const points = call!.caption.points!.map((point) => point.en).join(" ");
    expect(points).toMatch(/simulated/i);
    expect(points).toMatch(/not through FloodGuard/);
    expect(LABELS.signal.en).toMatch(/nothing dialled/);
    // The live public app sits inside the story: its SOS tab opens real hotline numbers, and the page says so.
    expect(STOPS["public-prepare"].warning?.en).toMatch(/real hotline numbers/);
  });
});
