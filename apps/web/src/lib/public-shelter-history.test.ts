import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { parseTimelineManifest, TIMELINE_MANIFEST_URL } from "./flood-timeline";
import {
  formatListDate,
  SHELTER_EVIDENCE_COPY,
  SHELTER_HISTORY_COPY,
  shelterHistorySites,
  shelterListCompiled,
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

describe("the places the walk of the practice counts", () => {
  it("are the located places in use by 12 Sep 2024, as the bake counted them", () => {
    const notCounted = sites.filter((item) => item.point && !item.countedForWalk).map((item) => item.id);
    // Wat Mueang Daeng (first used on 21 Sep) and the housing project (14 Sep), both after the peak.
    expect(notCounted).toEqual(["R04", "R19"]);
    expect(site("R01").countedForWalk).toBe(true);
    // A place without a position cannot be counted, whatever the manifest says of it.
    expect(site("R09").countedForWalk).toBe(false);
    expect(site("R04").walkNote.en).toContain("served as a shelter from 21 Sep");
    expect(site("R04").walkNote.th).toContain("21 ก.ย.");
  });
});

describe("the words about a place of 2024", () => {
  const today = { compiled: "2026-09-27", practice: false };
  const practising = { compiled: "2026-09-27", practice: true };

  it("say in every popup that the report is of 2024, when the list was compiled, and that it says nothing about today", () => {
    for (const item of sites) {
      const lines = shelterSiteLines(item, "en", today);
      expect(lines[0]).toContain("Reported in use as a shelter in September 2024.");
      expect(lines).toContain("List compiled on 27 Sep 2026 from public sources; not an official list.");
      expect(lines.at(-1)).toBe("This says nothing about today. Confirm with DDPM 1784 that it is open before you go.");
      expect(lines.includes("Its position on the map is approximate.")).toBe(item.approximate);
      expect(shelterSiteLines(item, "th", today).at(-1)).toContain("1784");
    }
    expect(shelterSiteLines(site("R01"), "en", today)[0]).toBe("Reported in use as a shelter in September 2024. Official source.");
  });

  it("say in a practice scenario why the walk does not count a place, and only there", () => {
    const line = "Not counted for the walk in this practice replay. The temple was itself flooded and evacuated at the peak; it served as a shelter from 21 Sep.";
    expect(shelterSiteLines(site("R04"), "en", practising)).toContain(line);
    expect(shelterSiteLines(site("R04"), "en", today)).not.toContain(line);
    expect(shelterSiteLines(site("R01"), "en", practising).some((text) => text.startsWith("Not counted"))).toBe(false);
    expect(shelterSiteSummary(site("R04"), "en", true)).toBe("Official source · not counted for the walk");
    expect(shelterSiteSummary(site("R04"), "en")).toBe("Official source");
  });

  it("say in the list where the report came from and how well the place is located", () => {
    expect(shelterSiteSummary(site("R01"), "en")).toBe("Official source");
    expect(shelterSiteSummary(site("R06"), "en")).toBe("Several media reports · position approximate");
    expect(shelterSiteSummary(site("R09"), "en")).toBe("Several media reports · position not known");
    expect(shelterSiteSummary(site("R16"), "th")).toBe("รายงานสื่อแหล่งเดียว · ตำแหน่งโดยประมาณ");
  });

  it("give the date the list was compiled, from the manifest, and say that it is not official and not about today", () => {
    expect(manifest.shelters?.reported_compiled).toBe("2026-09-27");
    expect(formatListDate("2026-09-27", "en")).toBe("27 Sep 2026");
    expect(formatListDate("2026-09-27", "th")).toBe("27 ก.ย. 2569 (2026)");
    expect(formatListDate("not a date", "en")).toBe("not a date");
    expect(shelterListCompiled("2026-09-27", "th")).toBe("รวบรวมรายชื่อเมื่อ 27 ก.ย. 2569 (2026) จากแหล่งข้อมูลสาธารณะ ไม่ใช่รายชื่อทางการ");
    expect(shelterListCompiled("", "en")).toBe("");
    expect(SHELTER_HISTORY_COPY.listNote.en).toContain("says nothing about today");
  });

  it("stay within the wording rules of the replay", () => {
    const texts: { source: string; text: string }[] = [];
    for (const [key, value] of [...Object.entries(SHELTER_HISTORY_COPY), ...Object.entries(SHELTER_EVIDENCE_COPY)]) {
      texts.push({ source: `${key} (en)`, text: value.en }, { source: `${key} (th)`, text: value.th });
    }
    for (const item of sites) {
      for (const language of ["en", "th"] as const) {
        texts.push({
          source: `${item.id} (${language})`,
          text: [item.name[language], ...shelterSiteLines(item, language, { compiled: "2026-09-27", practice: true }), shelterSiteSummary(item, language, true)].join(" │ "),
        });
      }
    }
    const findings = texts.flatMap(({ source, text }) => findWordingViolations(text, source));
    expect(findings.map((finding) => `[${finding.rule}] ${finding.source}: ${finding.context}`)).toEqual([]);
  });
});
