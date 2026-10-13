import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { parseTimelineManifest, TIMELINE_MANIFEST_URL } from "./flood-timeline";
import {
  SHELTER_EVIDENCE_COPY,
  SHELTER_HISTORY_COPY,
  shelterHistorySites,
  shelterSiteLines,
  shelterSiteSummary,
  type ShelterHistorySite,
} from "./public-shelter-history";
import { findWordingViolations } from "./replay-wording-lint";

// The fixture is the published manifest of the replay itself (revision r5).
const publicRoot = resolve(import.meta.dirname, "../../public");
const manifest = parseTimelineManifest(JSON.parse(readFileSync(resolve(publicRoot, TIMELINE_MANIFEST_URL.replace(/^\//, "")), "utf8")));
const sites = shelterHistorySites(manifest);
const site = (id: string): ShelterHistorySite => {
  const found = sites.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`no site ${id}`);
  return found;
};

describe("shelterHistorySites", () => {
  it("lists the places reported as shelters and leaves the command centre out", () => {
    const reported = manifest.shelters?.reported ?? [];
    expect(reported).toHaveLength(19);
    expect(sites).toHaveLength(18);
    expect(sites.map((item) => item.id)).not.toContain("R05");
    expect(reported.find((item) => item.id === "R05")?.role).toBe("relief_command_centre");
  });

  it("gives a position only where the manifest has one", () => {
    const unlocated = sites.filter((item) => !item.point).map((item) => item.id);
    expect(unlocated).toEqual(["R09", "R13", "R14", "R17"]);
    expect(site("R01").point).toEqual({ latitude: 20.4265331, longitude: 99.8843199 });
  });

  it("marks a position approximate unless the manifest is sure of it", () => {
    expect(site("R01").approximate).toBe(false);
    expect(site("R08").approximate).toBe(true); // medium confidence
    expect(site("R06").approximate).toBe(true); // placed from a description
    // A place without a position has no position to qualify.
    expect(site("R09").approximate).toBe(false);
  });

  it("keeps how each place came to be in the list", () => {
    expect(site("R01").evidence).toBe("official");
    expect(site("R07").evidence).toBe("several_reports");
    expect(site("R16").evidence).toBe("one_report");
  });

  it("returns nothing for a manifest without the list", () => {
    expect(shelterHistorySites({})).toEqual([]);
  });
});

describe("the words about a place of 2024", () => {
  it("say in every popup that the report is of 2024 and says nothing about today", () => {
    for (const item of sites) {
      const lines = shelterSiteLines(item, "en");
      expect(lines[0]).toContain("Reported in use as a shelter in September 2024.");
      expect(lines.at(-1)).toBe("This says nothing about today. Confirm with DDPM 1784 that it is open before you go.");
      expect(lines.includes("Its position on the map is approximate.")).toBe(item.approximate);
      expect(shelterSiteLines(item, "th").at(-1)).toContain("1784");
    }
    expect(shelterSiteLines(site("R01"), "en")[0]).toBe("Reported in use as a shelter in September 2024. Official source.");
  });

  it("say in the list where the report came from and how well the place is located", () => {
    expect(shelterSiteSummary(site("R01"), "en")).toBe("Official source");
    expect(shelterSiteSummary(site("R06"), "en")).toBe("Several media reports · position approximate");
    expect(shelterSiteSummary(site("R09"), "en")).toBe("Several media reports · position not known");
    expect(shelterSiteSummary(site("R16"), "th")).toBe("รายงานสื่อแหล่งเดียว · ตำแหน่งโดยประมาณ");
  });

  it("say that the list is not official and not about today", () => {
    expect(SHELTER_HISTORY_COPY.listNote.en).toContain("not an official list");
    expect(SHELTER_HISTORY_COPY.listNote.en).toContain("says nothing about today");
    expect(SHELTER_HISTORY_COPY.listNote.th).toContain("ไม่ใช่รายชื่อทางการ");
  });

  it("stay within the wording rules of the replay", () => {
    const texts: { source: string; text: string }[] = [];
    for (const [key, value] of [...Object.entries(SHELTER_HISTORY_COPY), ...Object.entries(SHELTER_EVIDENCE_COPY)]) {
      texts.push({ source: `${key} (en)`, text: value.en }, { source: `${key} (th)`, text: value.th });
    }
    for (const item of sites) {
      for (const language of ["en", "th"] as const) {
        texts.push({ source: `${item.id} (${language})`, text: [item.name[language], ...shelterSiteLines(item, language), shelterSiteSummary(item, language)].join(" │ ") });
      }
    }
    const findings = texts.flatMap(({ source, text }) => findWordingViolations(text, source));
    expect(findings.map((finding) => `[${finding.rule}] ${finding.source}: ${finding.context}`)).toEqual([]);
  });
});
