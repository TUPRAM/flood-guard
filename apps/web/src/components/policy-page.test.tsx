import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TIMELINE_MANIFEST_URL } from "@/lib/flood-timeline";
import { POLICY_EVIDENCE, SIGNED_SCORING_FRAME } from "@/lib/policy-evidence";
import { MAE_SAI_REPLAY_ROUTE } from "@/lib/policy-links";
import { PolicyPage } from "./policy-page";

const plain = (markup: string) => markup.replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&#x27;/g, "'").replace(/\s+/g, " ");

/** The element that opens at `start` in `markup`, assuming no element of the same tag is nested inside it. */
function elementAt(markup: string, start: number, tag: string): string {
  expect(start).toBeGreaterThanOrEqual(0);
  const end = markup.indexOf(`</${tag}>`, start);
  expect(end).toBeGreaterThan(start);
  return markup.slice(start, end + tag.length + 3);
}

describe("policy mentoring brief", () => {
  const html = renderToStaticMarkup(<PolicyPage />);
  const text = plain(html);

  it("renders the full explanation and anchor destinations before JavaScript", () => {
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toContain('id="main-content"');
    for (const id of ["purpose", "evidence", "signed-frame", "priorities", "access", "thailand", "responsibility"]) {
      expect(html).toContain(`id="${id}"`);
      expect(html).toContain(`href="#${id}"`);
    }
    expect(html).toContain('aria-label="Use English"');
    expect(html).toContain('aria-label="ใช้ภาษาไทย"');
    expect(html).toMatch(/<main[^>]*lang="en"/);
    expect(text).toContain("Class E never means safe.");
    expect(text).toContain("PROPOSED GOVERNANCE");
    expect(text).toContain("Not an official warning system.");
    expect(text).not.toMatch(/latest reproduced|latest study|real-time|live warning/i);
  });

  it("keeps heading levels in order and every disclosure a native, keyboard-operable details/summary", () => {
    const levels = [...html.matchAll(/<h([1-6])\b/g)].map((match) => Number(match[1]));
    levels.forEach((level, index) => {
      if (index > 0) expect(level - levels[index - 1], `heading ${index} jumps from h${levels[index - 1]} to h${level}`).toBeLessThanOrEqual(1);
    });
    expect(html.match(/<details\b/g)?.length).toBe(html.match(/<summary\b/g)?.length);
    expect(html).not.toMatch(/<summary[^>]*tabindex="-1"/);
  });

  it("titles the fixed Mae Sai example as a historical worked example bound to its r2 source", () => {
    expect(text).toContain("Worked example from the 28 Sep study (before the signed scoring frame)");
    expect(text).not.toContain("Latest reproduced priority study");
    expect(text).toContain("Ko Chang");
    expect(text).toContain("76.38");
    expect(text).not.toMatch(/53\.6|44\.0/);
    expect(html).toContain(POLICY_EVIDENCE.sourceUrl);
    expect(html).toContain(POLICY_EVIDENCE.methodUrl);
    expect(html).toContain(POLICY_EVIDENCE.sourceSha256);
    expect(html).toContain(POLICY_EVIDENCE.scenario.timestamp);
    expect(POLICY_EVIDENCE.rankings).toHaveLength(8);
    expect(POLICY_EVIDENCE.rankings.every((row) => row.actionClass === "E")).toBe(true);
    expect(text).toContain("computes no FPPS and assigns no class (D7)");
    expect(text).toContain("not observed impacts or operational approval");
  });

  it("keeps every rendered score inside the card that carries the pre-D4, r2 and pre-v1b caveat", () => {
    const cardStart = html.indexOf('data-testid="worked-example"');
    const card = elementAt(html, html.lastIndexOf("<article", cardStart), "article");
    const cardText = plain(card);
    // The caveat: r2 reconstruction and its coverage, the pre-D4 anchors with each difference, and pre-v1b.
    const caveat = plain(elementAt(card, card.lastIndexOf("<div", card.indexOf('data-testid="worked-example-caveat"')), "ul"));
    expect(caveat).toContain("Computed on r2, which modelled 96.3% of the district (294.4 of 305.6 km²)");
    expect(caveat).toContain("r3, the current replay, covers 100%");
    expect(caveat).toContain("replay_fpps_anchor_v1");
    expect(caveat).toContain("flood saturates at 0.25 instead of 0.20");
    expect(caveat).toContain("exposure mixes a share with a 5,000-person headcount instead of using the share only");
    expect(caveat).toContain("vulnerability is a terrain/remoteness proxy at 0.25 instead of national P10/P90 anchors of the dependent share");
    expect(caveat).toContain("before protocol v1b was hashed");
    expect(caveat).toContain("must not be cited as the Mae Sai case score");
    expect(caveat).toContain("The D4/v1 scores will come from the planning assessment after v1b");
    expect(cardText).toContain("Class E never means safe.");
    // The caveat comes before the first number, and each of the three headline tiles carries its own chip.
    expect(card.indexOf('data-testid="worked-example-caveat"')).toBeLessThan(card.indexOf(POLICY_EVIDENCE.rankings[0].score.toFixed(2)));
    const headline = elementAt(card, card.indexOf("<dl"), "dl");
    const tiles = [...headline.matchAll(/<div><dt>[\s\S]*?<\/dd><\/div>/g)].map((match) => plain(match[0]));
    expect(tiles).toHaveLength(3);
    expect(POLICY_EVIDENCE.scoreLabel.en).toBe("Historical example · pre-D4 anchors · r2 · pre-v1b, not a protocol result");
    for (const tile of tiles) expect(tile).toContain(POLICY_EVIDENCE.scoreLabel.en);
    // The eight-row list carries the same chip, and "Class E never means safe." next to its E rows.
    const listStart = card.indexOf('data-testid="worked-example-rankings-caption"');
    const caption = plain(elementAt(card, card.lastIndexOf("<p", listStart), "p"));
    expect(caption).toContain(POLICY_EVIDENCE.scoreLabel.en);
    expect(caption).toContain("Class E never means safe.");
    expect(listStart).toBeLessThan(card.indexOf(POLICY_EVIDENCE.rankings[3].score.toFixed(2)));
    // R2: tier, method source and anchors are in view beside the numbers.
    const provenance = plain(elementAt(card, card.lastIndexOf("<p", card.indexOf('data-testid="worked-example-provenance"')), "p"));
    expect(provenance).toContain(POLICY_EVIDENCE.tier);
    expect(provenance).toContain("replay-fpps.ts");
    expect(provenance).toContain("replay_fpps_anchor_v1 (pre-D4)");
    // No score, and no other two-decimal figure, appears anywhere outside that card.
    const outside = html.replace(card, "");
    for (const row of POLICY_EVIDENCE.rankings) {
      expect(cardText).toContain(row.score.toFixed(2));
      expect(outside).not.toContain(row.score.toFixed(2));
    }
    expect(plain(outside)).not.toMatch(/\b\d{2}\.\d{2}\b/);
  });

  it("shows the signed D4 frame: five components, the 0.20 flood anchor and the AGENTS.md weights", () => {
    const table = elementAt(html, html.lastIndexOf("<table", html.indexOf('data-testid="signed-frame-table"')), "table");
    const rows = [...table.matchAll(/<tr role="row">(?:(?!<\/tr>)[\s\S])*<\/tr>/g)].map((match) => match[0]).filter((row) => row.includes('scope="row"'));
    expect(rows).toHaveLength(5);
    const weights = rows.map((row) => /data-label="Weight">([^<]+)</.exec(row)?.[1]);
    expect(weights).toEqual(["0.30", "0.25", "0.20", "0.15", "0.10"]);
    expect(SIGNED_SCORING_FRAME.components.reduce((sum, component) => sum + component.weight, 0)).toBeCloseTo(1, 10);
    expect(plain(rows[0])).toContain("÷ 0.20");
    expect(plain(rows[0])).toContain("WorldCover class 80");
    expect(plain(rows[0])).toContain("with JRC reported as a sensitivity note");
    expect(plain(rows[0])).toContain("0.10 and 0.30 run one at a time");
    expect(plain(rows[0])).toContain("÷ 0.25");
    expect(plain(rows[1])).toContain("Share only, no headcount");
    expect(plain(rows[1])).toContain("5,000 people");
    // Plan v2 §3.4 access levels, with the 30-minute walk to a DDPM-located shelter at the pitch level.
    expect(plain(rows[2])).toContain("Public level: hospital (vehicle, 30 min) + main-road entry (vehicle, 15 min).");
    expect(plain(rows[2])).toContain("Pitch level: adds DDPM located shelter (walking, 30 min).");
    expect(plain(rows[2])).toContain("Counted only for people with access before the flood.");
    expect(plain(rows[3])).toContain("who lose all routes ÷ those residents");
    expect(plain(rows[4])).toContain("P10 and P90");
    expect(plain(rows[4])).toContain("computed once in v1b before any case scoring");
    expect(plain(rows[4])).toContain("P5/P95 anchors");
    expect(plain(rows[4])).toContain("terrain/remoteness proxy on case O1 only");
    expect(plain(rows[4])).toContain("terrain/remoteness proxy group, full at 0.25");
    expect(SIGNED_SCORING_FRAME.floodAnchorShare).toBe(0.2);
    expect(SIGNED_SCORING_FRAME.floodSensitivityShares).toEqual([0.1, 0.3]);
    const section = plain(elementAt(html, html.lastIndexOf("<section", html.indexOf('id="signed-frame"')), "section"));
    expect(section).toContain("The signed scoring frame (D4)");
    expect(section).toContain("docs/decision-log-d1-d16.md");
    expect(section).toContain("chosen after seeing the data, so 0.10 and 0.30 run as sensitivity checks");
    expect(section).toContain("The v1 class rules (scoring.py) stay binding. The v2 triggers appear only as a labelled secondary axis.");
    expect(section).toContain("The Mae Sai replay is a narrative surface, not a scored case");
    expect(section).not.toMatch(/[A-Z]:\\|\/Users\/|AppData/);
  });

  it("explains the low-confidence gate before the ordered v1 action conditions", () => {
    const rules = text.slice(text.indexOf("Evaluate in this order."));
    expect(rules.indexOf("Low confidence OR FPPS <35")).toBeLessThan(rules.indexOf("Exposure ≥70"));
    expect(rules).toContain("Exposure ≥70 and access gap ≥70");
    expect(rules).toContain("Road criticality ≥75 and access gap ≥55");
    expect(rules).toContain("Exposure ≥65 and access gap ≥50");
    expect(rules).toContain("binding under D6");
    expect(html).toContain("src/floodguard/scoring.py#L187-L204");
    expect(text).toContain("not Thai warning levels");
    expect(text).toContain("Proposed fit, not agency adoption");
  });

  it("uses the replay's access, equity and shelter definitions without ranking shelter sets on one number", () => {
    const access = plain(elementAt(html, html.lastIndexOf("<section", html.indexOf('id="access"')), "section"));
    expect(access).toContain("within a 2 km walk (about 30 minutes) along roads still passable");
    expect(access).toContain("0.3 m of modelled water");
    expect(access).toContain("Above 1.20");
    expect(access).toContain("below 0.80");
    expect(access).toContain("terrain/remoteness proxy (slopes of 8° or more, or 750 m or more from a drivable road)");
    expect(access).toContain("no single number makes one set better");
  });

  it("links the current r3 replay with its tier and calibration roles", () => {
    const link = elementAt(html, html.lastIndexOf("<div", html.indexOf('data-testid="replay-link"')), "div");
    expect(link).toContain(`href="${MAE_SAI_REPLAY_ROUTE}"`);
    const line = plain(link);
    expect(line).toContain("T1 scenario model with 100% district coverage");
    expect(line).toContain("VIIRS");
    expect(line).toContain("GISTDA’s 10 Sep flooded-area figure (about 9.9 km²) sets a stage knot, so it is a calibration anchor");
    expect(line).toContain("the UNOSAT 3991 size check is calibration-informed, not independent (R1)");
    expect(line).not.toContain("10 Sep map");
  });

  it("keeps the r3 calibration roles and GISTDA figure equal to the r3 replay manifest", () => {
    const manifest = JSON.parse(readFileSync(resolve("public", TIMELINE_MANIFEST_URL.slice(1)), "utf8")) as {
      revision: string;
      external_checks: { id: string; role: string; reported_km2: number }[];
    };
    const replay = POLICY_EVIDENCE.currentReplay;
    expect(manifest.revision).toBe(replay.revision);
    const byId = new Map(manifest.external_checks.map((check) => [check.id, check]));
    expect(byId.get(replay.calibrationAnchor.id)).toMatchObject({ role: replay.calibrationAnchor.role, reported_km2: replay.calibrationAnchor.reportedKm2 });
    expect(byId.get(replay.calibrationInformedCheck.id)?.role).toBe(replay.calibrationInformedCheck.role);
    // R1: no external check on the replay is labelled independent now.
    expect(manifest.external_checks.some((check) => check.role.startsWith("independent"))).toBe(false);
  });

  it("notes beside the pinned r2 manifest link that its independent UNOSAT label is superseded (R1)", () => {
    const [label] = POLICY_EVIDENCE.supersededLabels;
    expect(label).toMatchObject({ field: "external_checks[unosat-3991].role", sourceValue: "independent_magnitude_check", currentValue: POLICY_EVIDENCE.currentReplay.calibrationInformedCheck.role, decision: "R1", decidedOn: "2026-09-30" });
    const linkAt = html.indexOf(`href="${POLICY_EVIDENCE.sourceUrl}"`);
    const dd = elementAt(html, html.lastIndexOf("<dd", linkAt), "dd");
    expect(dd).toContain('data-testid="superseded-label-note"');
    const note = plain(dd);
    expect(note).toContain("this r2 manifest gives UNOSAT 3991 the role independent_magnitude_check");
    expect(note).toContain("Since R1 (30 Sep 2026) it is calibration-informed, not independent.");
  });

  it("lets a slashed component name wrap after the slash", () => {
    expect(html).toContain("Vulnerability/<wbr/>context");
  });
});

describe("policy page in Thai", () => {
  afterEach(() => {
    vi.doUnmock("@/lib/use-language");
    vi.resetModules();
  });

  it("renders the caveat, chips, D4 table, replay line and superseded-label note in Thai", async () => {
    vi.resetModules();
    vi.doMock("@/lib/use-language", () => ({ useLanguage: () => ["th", () => undefined] as const }));
    const { PolicyPage: ThaiPolicyPage } = await import("./policy-page");
    const html = renderToStaticMarkup(<ThaiPolicyPage />);
    const text = plain(html);
    expect(html).toMatch(/<main[^>]*lang="th"/);
    // The caveat, and the pre-v1b chip on each headline tile and above the eight-row list.
    expect(text).toContain("โปรดอ่านก่อนดูตัวเลข");
    expect(text).toContain("ก่อนบันทึกค่าแฮชของโปรโตคอล v1b จึงไม่ใช่ผลตามโปรโตคอล และห้ามอ้างเป็นคะแนนของกรณีแม่สาย");
    expect(text.split(POLICY_EVIDENCE.scoreLabel.th).length - 1).toBe(4);
    expect(text).toContain("ระดับ E ไม่ได้หมายความว่าปลอดภัย");
    // The D4 table in Thai, mirroring plan v2 §3.4.
    const table = plain(elementAt(html, html.lastIndexOf("<table", html.indexOf('data-testid="signed-frame-table"')), "table"));
    for (const component of SIGNED_SCORING_FRAME.components) {
      expect(table).toContain(component.signed.th);
      expect(table).toContain(component.workedExample.th);
    }
    expect(table).toContain("ระดับนำเสนอ: เพิ่มศูนย์พักพิงที่ ปภ. ระบุตำแหน่ง (เดิน 30 นาที)");
    expect(table).toContain("ESA WorldCover คลาส 80 ในทุกกรณี และรายงาน JRC เป็นหมายเหตุด้านความไว");
    // The replay line uses the replay's own Thai for the calibration roles.
    const link = plain(elementAt(html, html.lastIndexOf("<div", html.indexOf('data-testid="replay-link"')), "div"));
    expect(link).toContain("จึงเป็นจุดอ้างอิงที่ใช้ปรับแบบจำลอง");
    expect(link).toContain("มีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ (R1)");
    expect(text).toContain("ตั้งแต่มติ R1 (30 ก.ย. 2569) ถือว่ามีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ");
    // No English sentence from those parts leaks into the Thai render.
    for (const english of ["Read this before any number", "Historical example", "calibration anchor", "Superseded label", "Public level", "Class E never means safe."]) {
      expect(text).not.toContain(english);
    }
  });
});

describe("policy page in a build without the competition pages", () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  it("leaves out the replay link where /studio/ is not deployed", () => {
    vi.stubEnv("NEXT_PUBLIC_FLOODGUARD_APP_PROFILE", "public-production");
    const html = renderToStaticMarkup(<PolicyPage />);
    expect(html).not.toContain('data-testid="replay-link"');
    expect(html).not.toContain(`href="${MAE_SAI_REPLAY_ROUTE}"`);
    // The historical example and its caveat do not depend on the profile.
    expect(html).toContain('data-testid="worked-example-caveat"');
  });
});

describe("POLICY_EVIDENCE status flags", () => {
  it("keeps the accepted results empty and records why the example is historical", () => {
    expect(POLICY_EVIDENCE.generatedAt).toBeNull();
    expect(POLICY_EVIDENCE.acceptedFpps).toBeNull();
    expect(POLICY_EVIDENCE.acceptedActionClass).toBeNull();
    expect(POLICY_EVIDENCE.officialWarning).toBe(false);
    expect(POLICY_EVIDENCE.canFeedDecisionLayer).toBe(false);
    expect(POLICY_EVIDENCE.status).toBe("historical_worked_example");
    expect(POLICY_EVIDENCE.conformsToSignedFrame).toBe(false);
    expect(POLICY_EVIDENCE.computedBeforeProtocolV1b).toBe(true);
    expect(POLICY_EVIDENCE.supersededBy).toBe("planning assessment after v1b (D4, D6, D7)");
    expect(POLICY_EVIDENCE.decisionRefs).toEqual(["D4", "D6", "D7", "R1", "R2"]);
    expect(POLICY_EVIDENCE.decisionLog).toBe("docs/decision-log-d1-d16.md");
    expect(POLICY_EVIDENCE.scenario.anchorVersion).toBe("replay_fpps_anchor_v1");
    expect(POLICY_EVIDENCE.anchors.floodAreaShare).toBe(0.25);
    expect(POLICY_EVIDENCE.anchors.exposedPeople).toBe(5000);
    expect(POLICY_EVIDENCE.confidence).toBe("low");
    expect(POLICY_EVIDENCE.sourceTimestamp).toBeTruthy();
    expect(POLICY_EVIDENCE.assumptions.length).toBeGreaterThan(0);
  });

  it("records r2's model coverage from its manifest figures and the r3 replay at full coverage", () => {
    const coverage = POLICY_EVIDENCE.reconstructionCoverage;
    expect(coverage.manifestField).toBe("model_coverage");
    expect([coverage.modelledKm2, coverage.districtKm2]).toEqual([294.4, 305.6]);
    expect(POLICY_EVIDENCE.reconstructionCoverageShare).toBeCloseTo(coverage.modelledKm2 / coverage.districtKm2, 3);
    expect(POLICY_EVIDENCE.reconstructionCoverageShare).toBeLessThan(1);
    expect(POLICY_EVIDENCE.currentReplay).toMatchObject({ route: MAE_SAI_REPLAY_ROUTE, revision: "r3", coverageShare: 1, computesFpps: false });
  });
});
