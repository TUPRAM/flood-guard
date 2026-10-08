import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TIMELINE_MANIFEST_URL } from "@/lib/flood-timeline";
import { COMMAND_OVERLAY_HREFS, COMMAND_OVERLAY_INDEX_HREF, planningCells, readCommandOverlay } from "@/lib/flood-timeline-command-table";
import { POLICY_CASE, POLICY_CASE_REASONS, POLICY_CASE_ROUTE, POLICY_CASE_SCORE_LABEL } from "@/lib/policy-case";
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
    for (const id of ["purpose", "case", "evidence", "signed-frame", "priorities", "access", "thailand", "responsibility"]) {
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
    expect(caveat).toContain("r4, the current replay, covers 100%");
    expect(caveat).toContain("replay_fpps_anchor_v1");
    expect(caveat).toContain("flood saturates at 0.25 instead of 0.20");
    expect(caveat).toContain("exposure mixes a share with a 5,000-person headcount instead of using the share only");
    expect(caveat).toContain("vulnerability is a terrain/remoteness proxy at 0.25 instead of national P10/P90 anchors of the dependent share");
    expect(caveat).toContain("before protocol v1b was hashed");
    expect(caveat).toContain("must not be cited as the Mae Sai case score");
    expect(caveat).toContain("The D4/v1 scores are those of case SE1 at the top of this page.");
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
    // No score of the example, and no other two-decimal figure, appears anywhere outside that card. The scored case
    // prints its scores to one decimal inside its own card (tested below).
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
    // The replay's equity denominator (owner decision R8, option B) and its minimum group size.
    expect(access).toContain("Each rate counts only people who had a shelter within reach before the flood: of those, the share who lost it.");
    expect(access).toContain("No ratio is given when a group has fewer than 50 such people or when nobody has lost access.");
    expect(access).not.toMatch(/all residents counted/i);
    expect(access).toContain("terrain/remoteness proxy (slopes of 8° or more, or 750 m or more from a drivable road)");
    expect(access).toContain("no single number makes one set better");
  });

  it("links the current r4 replay with its tier and calibration roles", () => {
    const link = elementAt(html, html.lastIndexOf("<div", html.indexOf('data-testid="replay-link"')), "div");
    expect(link).toContain(`href="${MAE_SAI_REPLAY_ROUTE}"`);
    const line = plain(link);
    expect(line).toContain("T1 scenario model with 100% district coverage");
    expect(line).toContain("VIIRS");
    expect(line).toContain("GISTDA’s 10 Sep flooded-area figure (about 9.9 km²) sets a stage knot, so it is a calibration anchor");
    expect(line).toContain("Current replay (r4):");
    expect(line).toContain("the UNOSAT 3991 size check is calibration-informed, not independent (R1)");
    expect(line).toContain("The 16 Sep Sentinel-1 radar pass was used to tune the recession, so that size comparison is calibration-informed too.");
    expect(line).not.toContain("10 Sep map");
  });

  it("keeps the calibration roles and GISTDA figure equal to the served replay manifest", () => {
    const manifest = JSON.parse(readFileSync(resolve("public", TIMELINE_MANIFEST_URL.slice(1)), "utf8")) as {
      revision: string;
      external_checks: { id: string; role: string; reported_km2: number }[];
      s1_anchor: { role: string };
      exploratory_knowledge: { items: { id: string; relation: string; known_during_tuning: boolean }[] };
    };
    const replay = POLICY_EVIDENCE.currentReplay;
    expect(manifest.revision).toBe(replay.revision);
    const byId = new Map(manifest.external_checks.map((check) => [check.id, check]));
    expect(byId.get(replay.calibrationAnchor.id)).toMatchObject({ role: replay.calibrationAnchor.role, reported_km2: replay.calibrationAnchor.reportedKm2 });
    expect(byId.get(replay.calibrationInformedCheck.id)?.role).toBe(replay.calibrationInformedCheck.role);
    // The Sentinel-1 pass tuned the recession keyframes, so the manifest and the policy page both call it calibration-informed.
    expect(manifest.s1_anchor.role).toBe(replay.recessionTuning.role);
    expect(manifest.exploratory_knowledge.items.find((item) => item.id === replay.recessionTuning.id)).toMatchObject({ relation: replay.recessionTuning.relation, known_during_tuning: true });
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

describe("policy page: the scored case SE1", () => {
  const html = renderToStaticMarkup(<PolicyPage />);
  const cardStart = html.indexOf('data-testid="scored-case"');
  const card = html.slice(html.lastIndexOf("<article", cardStart), html.indexOf("</article>", cardStart) + "</article>".length);
  const cardText = plain(card);
  const count = (value: number) => Math.round(value).toLocaleString("en-US");

  it("leads the page: the case comes before the signed frame and the earlier example is last", () => {
    expect(cardStart).toBeGreaterThan(0);
    const order = ['id="purpose"', 'id="case"', 'id="signed-frame"', 'id="priorities"', 'id="access"', 'id="thailand"', 'id="responsibility"', 'id="evidence"'].map((id) => html.indexOf(id));
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(html).toContain('href="#case"');
    expect(plain(html)).toContain("Ko Chang comes first: lost roads, not flooded area.");
    expect(plain(html)).toContain("It is a scenario for planning, not a flood of any day.");
  });

  it("prints only what the published overlay holds, read through the strict parser", () => {
    const file = readFileSync(resolve("public", COMMAND_OVERLAY_HREFS.SE1.slice(1)));
    const index = JSON.parse(readFileSync(resolve("public", COMMAND_OVERLAY_INDEX_HREF.slice(1)), "utf8")) as { cases: { case_id: string; sha256: string }[] };
    const sha256 = createHash("sha256").update(file).digest("hex");
    expect(POLICY_CASE.derived_from).toEqual({ file: COMMAND_OVERLAY_HREFS.SE1, sha256 });
    expect(index.cases.find((item) => item.case_id === "SE1")?.sha256).toBe(sha256);
    const { overlay, refusal } = readCommandOverlay(JSON.parse(file.toString("utf8")), "SE1");
    expect(refusal).toBeNull();
    if (!overlay) throw new Error("the published overlay of case SE1 was refused");
    expect(POLICY_CASE).toMatchObject({
      case_id: overlay.case.case_id, publication_eligibility: "public", official_warning: false, operational_status: "non_operational",
      can_feed_decision_layer: false, accepted_fpps: null, accepted_action_class: null, generated_at: overlay.generated_at,
      source_timestamp: overlay.source_timestamp, class_rule_version: overlay.class_rule_version, normalisation_version: overlay.normalisation_version,
      protocol_sha256: overlay.protocol_sha256,
    });
    expect(file.toString("utf8")).toContain(`"source_timestamp": "${POLICY_CASE.source_period}"`);
    const cells = planningCells(overlay, "SE1");
    expect(POLICY_CASE.rows).toHaveLength(cells.size);
    expect(POLICY_CASE.rows.map((row) => row.fpps_0_100)).toEqual([...POLICY_CASE.rows.map((row) => row.fpps_0_100)].sort((a, b) => b - a));
    for (const row of POLICY_CASE.rows) {
      const cell = cells.get(row.unit_id);
      const source = overlay.rows.find((item) => item.row_id === cell?.rowId);
      if (!cell || !source) throw new Error(`no overlay row for ${row.unit_id}`);
      expect([row.fpps_0_100, row.action_class, row.action_reason_code, row.confidence_class, row.headline_stability]).toEqual([cell.fpps, cell.letter, cell.reasonCode, cell.confidenceClass, cell.headline]);
      expect([row.name_en, row.name_th, POLICY_CASE.tier, POLICY_CASE.lane, POLICY_CASE.flood_input]).toEqual([source.unit_name_en, source.unit_name_th, cell.tier, cell.lane, cell.floodInput]);
      // The counts behind the three count columns are the inputs of the row's own components.
      const inputs = JSON.stringify(source.components);
      const raw = (key: string) => Number(new RegExp(`"${key}":\\s*([0-9.eE+-]+)`).exec(inputs)?.[1]);
      expect(row.residents_inside_the_layer).toBe(Math.round(raw("residents_inside_flood_extent")));
      expect(row.residents).toBe(Math.round(raw("unit_residents")));
      expect(row.residents_losing_every_route).toBe(Math.round(raw("residents_losing_all_routes")));
      expect(row.residents_with_a_route_before).toBe(Math.round(raw("residents_with_baseline_route")));
      expect(row.residents_with_hospital_access_before).toBe(Math.round(raw("baseline_access_residents")));
      expect(row.residents_losing_hospital_access).toBe(Math.round(raw("newly_lost_residents")));
      expect(POLICY_CASE_REASONS[row.action_reason_code]).toBeDefined();
      // Every figure of the row is on the page, inside the card.
      for (const figure of [row.fpps_0_100.toFixed(1), `${count(row.residents_inside_the_layer)} of ${count(row.residents)}`, `${count(row.residents_losing_every_route)} of ${count(row.residents_with_a_route_before)}`]) {
        expect(cardText).toContain(figure);
      }
    }
  });

  it("keeps every score of the case inside its card, after the scenario caveat and under its label", () => {
    const caveat = plain(card.slice(card.indexOf('data-testid="scored-case-caveat"'), card.indexOf("</ul>")));
    expect(caveat).toContain("A scenario, not an observation.");
    expect(caveat).toContain("No day of 2024 looked like this.");
    expect(caveat).toContain("Water crossing a road does not prove the road was closed.");
    expect(caveat).toContain("FloodGuard did not validate it");
    expect(caveat).toContain("The roads have not been checked on the ground.");
    expect(caveat).toContain("no class here is headline-eligible yet");
    expect(caveat).toContain("The class names a kind of action, not a size of harm.");
    expect(POLICY_CASE.rows.every((row) => row.headline_stability === "not_evaluated")).toBe(true);
    const [first, second] = POLICY_CASE.rows;
    expect([first.name_en, first.action_class, second.name_en]).toEqual(["Ko Chang", "B", "Mae Sai"]);
    // What the heading and the caveat say of the two tambons holds in the figures.
    expect(first.residents_inside_the_layer).toBeLessThan(second.residents_inside_the_layer);
    expect(first.residents_losing_every_route).toBe(first.residents_with_a_route_before);
    expect(Math.max(...POLICY_CASE.rows.map((row) => row.residents_losing_hospital_access))).toBe(second.residents_losing_hospital_access);
    expect(card.indexOf('data-testid="scored-case-caveat"')).toBeLessThan(card.indexOf(first.fpps_0_100.toFixed(1)));
    // The label is on each of the three tiles and above the table: four times.
    expect(cardText.split(POLICY_CASE_SCORE_LABEL.en).length - 1).toBe(4);
    const outside = plain(html.replace(card, ""));
    for (const row of POLICY_CASE.rows) expect(outside).not.toMatch(new RegExp(`(?<![0-9.])${row.fpps_0_100.toFixed(1).replace(".", "[.]")}(?![0-9])`));
    const provenance = plain(card.slice(card.indexOf('data-testid="scored-case-provenance"'), card.indexOf("</p>", card.indexOf('data-testid="scored-case-provenance"'))));
    for (const part of ["T1", "SCN-ENV", "class_rule_v1", "planning_frame_v1", "closure_rule_v1", POLICY_CASE.protocol_sha256.v1b.slice(0, 8), "1 Aug – 12 Oct 2024", "medium, declared for a scenario"]) {
      expect(provenance).toContain(part);
    }
    expect(card).toContain(`dateTime="${POLICY_CASE.source_period}"`);
    expect(card).toContain(`dateTime="${POLICY_CASE.generated_at}"`);
    const note = plain(card.slice(card.indexOf('data-testid="scored-case-note"')));
    expect(note).toContain("Class E never means safe.");
    expect(note).toContain("4 tambons are class E because their score is under 35");
    expect(note).toContain("not an official warning");
    expect(note).toContain("CC BY-SA 4.0");
    expect(cardText).not.toMatch(/real-time|live |observed flood|accuracy|validated/i);
  });

  it("links to the case on the map only where the competition pages are deployed", () => {
    expect(card).toContain(`href="${POLICY_CASE_ROUTE}"`);
    vi.stubEnv("NEXT_PUBLIC_FLOODGUARD_APP_PROFILE", "public-production");
    const publicHtml = renderToStaticMarkup(<PolicyPage />);
    vi.unstubAllEnvs();
    expect(publicHtml).not.toContain(`href="${POLICY_CASE_ROUTE}"`);
    expect(publicHtml).toContain('data-testid="scored-case-caveat"');
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
    // The scored case in Thai: its label on three tiles and above the table, its caveat and its count columns.
    expect(text.split(POLICY_CASE_SCORE_LABEL.th).length - 1).toBe(4);
    expect(text).toContain("สถานการณ์จำลอง ไม่ใช่การสังเกตการณ์");
    expect(text).toContain("เกาะช้างมาก่อน: เพราะถนนที่ขาด ไม่ใช่พื้นที่น้ำท่วม");
    expect(text).toContain("5,972 จาก 5,972");
    // No English sentence from those parts leaks into the Thai render.
    for (const english of ["Read this before any number", "Historical example", "calibration anchor", "Superseded label", "Public level", "Class E never means safe.", "A scenario, not an observation", "Lose every road route", "stability not evaluated", "Keep routes open"]) {
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

  it("records r2's model coverage from its manifest figures and the current replay at full coverage", () => {
    const coverage = POLICY_EVIDENCE.reconstructionCoverage;
    expect(coverage.manifestField).toBe("model_coverage");
    expect([coverage.modelledKm2, coverage.districtKm2]).toEqual([294.4, 305.6]);
    expect(POLICY_EVIDENCE.reconstructionCoverageShare).toBeCloseTo(coverage.modelledKm2 / coverage.districtKm2, 3);
    expect(POLICY_EVIDENCE.reconstructionCoverageShare).toBeLessThan(1);
    expect(POLICY_EVIDENCE.currentReplay).toMatchObject({ route: MAE_SAI_REPLAY_ROUTE, revision: "r4", coverageShare: 1, computesFpps: false });
  });
});
