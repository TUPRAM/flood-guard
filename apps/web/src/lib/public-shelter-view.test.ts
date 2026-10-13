import { describe, expect, it } from "vitest";

import { SHELTER_PAGE_COPY, shelterBanner, type ShelterBannerInput } from "./public-shelter-view";
import { findWordingViolations } from "./replay-wording-lint";

const STATES: Record<string, ShelterBannerInput> = {
  none: { draft: "", destination: "" },
  blank: { draft: "   ", destination: "" },
  typed: { draft: " Wat Tham Pha Chom ", destination: "" },
  set: { draft: "Wat Tham Pha Chom", destination: "Wat Tham Pha Chom" },
  direct: { draft: "Wat Tham Pha Chom", destination: "Wat Tham Pha Chom", directMetres: 1460 },
  walk: { draft: "Wat Tham Pha Chom", destination: "Wat Tham Pha Chom", directMetres: 1460, walk: { metres: 7300, minutes: 97 } },
};

describe("shelterBanner", () => {
  it("is grey with no destination, whatever blanks stand in the field", () => {
    expect(shelterBanner(STATES.none, "en")).toEqual({ tone: "neutral", icon: "shelter", text: "No destination chosen yet" });
    expect(shelterBanner(STATES.blank, "en")).toEqual(shelterBanner(STATES.none, "en"));
    expect(shelterBanner(STATES.none, "th").text).toBe("ยังไม่ได้เลือกจุดหมาย");
  });

  it("is amber while the destination in the field has not been confirmed", () => {
    expect(shelterBanner(STATES.typed, "en")).toEqual({ tone: "watch", icon: "hazard", text: "Not confirmed yet: Wat Tham Pha Chom" });
    expect(shelterBanner(STATES.typed, "th").text).toBe("ยังไม่ได้ยืนยัน: Wat Tham Pha Chom");
  });

  it("gives the walking route once the router answered, the figures before the name", () => {
    expect(shelterBanner(STATES.walk, "en")).toEqual({
      tone: "easing",
      icon: "route",
      text: "Walking route 7.3 km · about 97 min · Wat Tham Pha Chom",
    });
    expect(shelterBanner(STATES.walk, "th").text).toBe("เส้นทางเดิน 7.3 กม. · ประมาณ 97 นาที · Wat Tham Pha Chom");
  });

  it("says that a straight line is not a walking route", () => {
    expect(shelterBanner(STATES.direct, "en").text).toBe("Straight line 1.5 km · not a walking route · Wat Tham Pha Chom");
    expect(shelterBanner(STATES.direct, "th").text).toBe("เส้นตรง 1.5 กม. · ไม่ใช่เส้นทางเดิน · Wat Tham Pha Chom");
  });

  it("says only that the destination is set when no distance could be worked out", () => {
    expect(shelterBanner(STATES.set, "en")).toEqual({ tone: "easing", icon: "route", text: "Destination set: Wat Tham Pha Chom" });
  });

  it("is never the green of an all-clear: the page knows no shelter that is open today", () => {
    for (const input of Object.values(STATES)) {
      expect(shelterBanner(input, "en").tone).not.toBe("calm");
    }
  });
});

describe("the words of the Shelter page", () => {
  it("say on the first screen and in the sheet what the page does not know", () => {
    expect(SHELTER_PAGE_COPY.noteUnknown.en).toBe("This app does not know which place is open today · confirm with DDPM 1784");
    expect(SHELTER_PAGE_COPY.noteUnknown.th).toContain("1784");
    expect(SHELTER_PAGE_COPY.unknown.en).toContain("does not know its current capacity or operating status");
    expect(SHELTER_PAGE_COPY.routeDirect.en).toContain("not a walking route");
    expect(SHELTER_PAGE_COPY.safety.en).toContain("Do not walk or drive into moving or deep floodwater");
  });

  it("stay within the wording rules of the replay", () => {
    const texts: { source: string; text: string }[] = [];
    for (const [key, value] of Object.entries(SHELTER_PAGE_COPY)) {
      texts.push({ source: `${key} (en)`, text: value.en }, { source: `${key} (th)`, text: value.th });
    }
    for (const [key, input] of Object.entries(STATES)) {
      texts.push({ source: `banner ${key} (en)`, text: shelterBanner(input, "en").text }, { source: `banner ${key} (th)`, text: shelterBanner(input, "th").text });
    }
    const findings = texts.flatMap(({ source, text }) => findWordingViolations(text, source));
    expect(findings.map((finding) => `[${finding.rule}] ${finding.source}: ${finding.context}`)).toEqual([]);
  });
});
