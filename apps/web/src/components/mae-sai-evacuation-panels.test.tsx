import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  coverageComplete,
  districtStats,
  hourlyStages,
  sizeChecks,
  smallestFloodedExtent,
  TIMELINE_MANIFEST_URL,
  type FacilityProps,
  type GeoCollection,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import {
  accessLostSeries,
  accessSnapshot,
  capacityAwareView,
  capacityFlag,
  floodedHomeMask,
  overCapacitySites,
  parseAccessNodes,
  planCoverageSentence,
  planSites,
  planSetId,
  REPORTED_SET_ID,
  reportedSetExclusions,
  reportedShelterCheck,
  reportedSiteCounts,
  robustCore,
  scopeTotals,
  shelterSetComparison,
  summarizeAccessSets,
  tambonResidents,
  type AccessGroupSums,
} from "@/lib/flood-timeline-evacuation";
import { localizedText, plainManifestText } from "@/lib/flood-timeline-copy";
import { findWordingViolations } from "@/lib/replay-wording-lint";
import {
  AccessCard,
  AccessChart,
  candidateTitle,
  CapacityAwareBlock,
  capacityBoundsText,
  capacityCaveats,
  capacityFlagText,
  capacityText,
  CoverageCurve,
  cutoffText,
  ExternalChecks,
  freeboardText,
  indefiniteArticle,
  ineligibleReasonText,
  OtherCandidatesCard,
  OtherCandidatesList,
  PeopleInWaterCard,
  reportedCheckText,
  ReportedSheltersCard,
  SetComparisonTable,
  ShelterPlanCard,
  Term,
  timesOver,
  WhatIfBlock,
} from "./mae-sai-evacuation-panels";
import { TimelineLegend } from "./mae-sai-flood-timeline";

const publicRoot = resolve(import.meta.dirname, "../../public");
const publicFile = (href: string) => resolve(publicRoot, href.replace(/^\//, ""));
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(publicFile(href), "utf8")) as T;
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const roads = readJson<GeoCollection<unknown, RoadProps>>(manifest.vectors.roads.href).features.map((feature) => feature.properties);
const facilities = readJson<GeoCollection<unknown, FacilityProps>>(manifest.vectors.facilities.href).features.map((feature) => feature.properties);
const names = Object.fromEntries(readJson<GeoCollection<unknown, TambonProps>>(manifest.vectors.tambons.href).features.map((feature) => [feature.properties.id, feature.properties]));
const access = manifest.access!;
const shelters = manifest.shelters!;
const nodes = parseAccessNodes(new Uint8Array(readFileSync(publicFile(access.nodes.href))), access);
const summaries = summarizeAccessSets(nodes, access);
const tambonTotals = tambonResidents(nodes, access.tambons.length);
// The default "flooded" scope: residents whose home node floods at the modelled peak (the plan's demand).
const floodedMask = floodedHomeMask(nodes, shelters.method.peak_stage_m, manifest.hand.step_m, manifest.hand.channel_code, manifest.hand.never_code);
const scoped = {
  all: { summaries, tambonTotals, totals: scopeTotals(nodes) },
  flooded: { summaries: summarizeAccessSets(nodes, access, floodedMask), tambonTotals: tambonResidents(nodes, access.tambons.length, floodedMask), totals: scopeTotals(nodes, floodedMask) },
};
const peak = Math.max(...manifest.days.map((day) => day.stage_m));
const peakDay = manifest.days.find((day) => day.stage_m === peak)!;
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\u00a0/g, " ").replace(/\s+/g, " ");
// Glossary definitions render inside the text (shown on hover); drop them where a test reads a sentence end to end.
const withoutTips = (html: string) => html.replace(/<span role="tooltip"[^>]*>[^<]*<\/span>/g, "");
/** Whether the radio input with `name` and `value` is rendered checked (React may order the attributes either way). */
const radioChecked = (html: string, name: string, value: string) => {
  const tag = [...html.matchAll(/<input[^>]*>/g)].map((match) => match[0]).find((input) => input.includes(`name="${name}"`) && input.includes(`value="${value}"`));
  return Boolean(tag && /\schecked(=""|\s|\/|>)/.test(tag));
};
const noop = () => undefined;
// Model outputs may say "not observed"; they must never present themselves as observed, and they must pass the shared
// replay wording lint (no affirmative real-time, live, forecast, warning or validation wording).
const unsafeClaim = (value: string) => /\bobserved\b/i.test(value.replaceAll(/not observed/gi, "")) || findWordingViolations(value).length > 0;

const replayStages = hourlyStages(manifest.stage_anchors);
/** One shelter set counted for both scopes at `stage`, as the page passes it to the access card. */
const bothScopes = (setId: string, stage: number) => {
  const index = access.sets.indexOf(setId);
  const counted = (model: (typeof scoped)["all"]) => shelterSetComparison(model.summaries[index], model.totals, stage, replayStages, access.levels);
  return { all: counted(scoped.all), flooded: counted(scoped.flooded) };
};
const comparisons = (k: number, stage: number) => ({ reported: bothScopes(REPORTED_SET_ID, stage), plan: bothScopes(planSetId(k), stage) });
const people = (value: number) => Math.round(value).toLocaleString("en-US");
/** Text of the element with `testId` (tags stripped). */
const cellText = (html: string, testId: string) => {
  const match = new RegExp(`data-testid="${testId}"[^>]*>(.*?)</(?:td|p|div)>`, "s").exec(html);
  if (!match) throw new Error(`No element with data-testid ${testId}`);
  return text(match[1]).trim();
};

function accessCard(
  language: "en" | "th", set: "reported" | "plan", k = shelters.knee_k, stage = peak, scope: "flooded" | "all" = "all", totals?: AccessGroupSums,
) {
  const index = access.sets.indexOf(set === "reported" ? REPORTED_SET_ID : planSetId(k));
  const model = scoped[scope];
  const summary = model.summaries[index];
  return renderToStaticMarkup(
    <AccessCard access={access} shelters={shelters} snapshot={accessSnapshot(summary, stage, access.levels)}
      series={accessLostSeries(summary, replayStages, access.levels)} time={3.5} names={names}
      tambonTotals={model.tambonTotals} shelterSet={set} planK={k} onShelterSet={noop} onPlanK={noop} showCutoff={false}
      onShowCutoff={noop} scope={scope} onScope={noop} scopeTotals={totals ?? model.totals} allResidents={scoped.all.totals.population}
      floodedResidents={scoped.flooded.totals.population} comparison={comparisons(k, stage)} language={language} status="ready" />,
  );
}

describe("People in flood water card", () => {
  it("shows the modelled residents in water with the WorldPop caveat, in both languages", () => {
    const stats = districtStats(manifest, peak, roads, facilities);
    expect(stats.people_in_water).toBe(peakDay.stats.people_in_water);
    const html = renderToStaticMarkup(<PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language="en" />);
    const plain = text(html);
    expect(plain).toContain("People in flood water (model)");
    expect(plain).toContain(peakDay.stats.people_in_water!.toLocaleString("en-US"));
    expect(plain).toContain("not the 2024 population");
    expect(plain).toContain("not visitors or traders at the border market");
    expect(plain).toContain("WorldPop");
    expect(html.match(/<li>/g)).toHaveLength(Object.keys(manifest.population!.tambon_histograms).length);
    expect(plain).toContain("at this replay hour");
    expect(plain).not.toMatch(/\bnow\b/);
    expect(plain).toContain("(population grid)");
    // Without the access scenario there is nothing to reconcile against.
    expect(html).not.toContain("people-reconcile");
    const thai = text(renderToStaticMarkup(<PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language="th" />));
    expect(thai).toContain("ประชากรในพื้นที่น้ำท่วม (แบบจำลอง)");
    expect(thai).toContain("ไม่ใช่ประชากรปี 2567 (2024)");
    expect(thai).not.toContain("tha_ppp_2020");
    expect(unsafeClaim(plain)).toBe(false);
  });

  it("says where its totals come from when the access and plan cards count residents at road nodes", () => {
    const stats = districtStats(manifest, peak, roads, facilities);
    const plain = text(renderToStaticMarkup(<PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language="en"
      accessResidents={access.totals.population} demandPeople={shelters.demand_people} />));
    expect(plain).toContain("Where the totals differ: this card counts the population grid cell by cell.");
    expect(plain).toContain(`snapped to road nodes instead: ${access.totals.population.toLocaleString("en-US")} in all, of whom ${shelters.demand_people.toLocaleString("en-US")} have a home node that floods at the modelled peak.`);
  });
});

describe("Evacuation access card (scenario)", () => {
  it("puts the two shelter sets side by side with both denominators, in the agreed order, and labels it a scenario", () => {
    const html = accessCard("en", "reported");
    const plain = text(html);
    expect(plain).toContain("Walking access to a dry shelter (scenario)");
    expect(plain).toContain("T1 SCENARIO (MODEL) · EVACUATION ACCESS");
    expect(plain).toContain("not observed evacuation outcomes");
    // The eight figures of the roadmap critic, each with its own denominator.
    expect(cellText(html, "compare-reported-all-baseline")).toBe("34,525 of 81,799");
    expect(cellText(html, "compare-reported-all-lost")).toBe("7,086 of 34,525 (21%)");
    expect(cellText(html, "compare-reported-flooded-baseline")).toBe("5,698 of 14,169");
    expect(cellText(html, "compare-reported-flooded-keeping")).toBe("299");
    expect(cellText(html, "compare-plan-all-baseline")).toBe("24,910 of 81,799");
    expect(cellText(html, "compare-plan-all-lost")).toBe("13,429 of 24,910 (54%)");
    expect(cellText(html, "compare-plan-flooded-baseline")).toBe("7,580 of 14,169");
    expect(cellText(html, "compare-plan-flooded-keeping")).toBe("460");
    // Newly lost uses the set's own baseline as denominator, never the scope total.
    expect(cellText(html, "compare-reported-flooded-lost")).toBe("5,400 of 5,698 (95%)");
    expect(cellText(html, "compare-plan-flooded-lost")).toBe("7,120 of 7,580 (94%)");
    // Reported set: within reach before the flood, keeping access, newly lost, then the cut-off hour.
    const at = (testId: string) => html.indexOf(`data-testid="${testId}"`);
    const reportedOrder = ["baseline", "keeping", "lost", "cutoff"].map((row) => at(`compare-reported-all-${row}`));
    expect(reportedOrder.every((position) => position > 0)).toBe(true);
    expect([...reportedOrder].sort((a, b) => a - b)).toEqual(reportedOrder);
    // Both columns are always present: all residents first, then residents whose homes flood.
    expect(at("compare-reported-all-baseline")).toBeLessThan(at("compare-reported-flooded-baseline"));
    expect(html.match(/<th scope="col">All residents at road nodes<\/th><th scope="col">Residents whose homes flood at the peak<\/th>/g)).toHaveLength(2);
    // The set shown on the map is marked; that is the only difference between the two tables' frames.
    expect(html).toMatch(/data-testid="set-compare-reported" data-selected=""/);
    expect(html).not.toMatch(/data-testid="set-compare-plan" data-selected/);
    expect(accessCard("en", "plan")).toMatch(/data-testid="set-compare-plan" data-selected=""/);
    expect(plain).toContain(`Shelters reported used in Sep 2024 (${reportedSiteCounts(shelters).counted} sites counted) · shown on the map and in the chart`);
    expect(plain).not.toContain("Plan size k");
    expect(plain).not.toMatch(/\bnow\b/);
    expect(unsafeClaim(plain)).toBe(false);
  });

  it("leads the ranked plan with its cut-off hour and explains its loss at the peak instead of presenting it as failure", () => {
    const html = accessCard("en", "plan");
    const plain = text(html);
    const at = (testId: string) => html.indexOf(`data-testid="${testId}"`);
    const planOrder = ["cutoff", "baseline", "keeping", "lost"].map((row) => at(`compare-plan-all-${row}`));
    expect(planOrder.every((position) => position > 0)).toBe(true);
    expect([...planOrder].sort((a, b) => a - b)).toEqual(planOrder);
    expect(html).toMatch(/<tr data-lead="">/);
    expect(html.match(/data-lead=""/g)).toHaveLength(1);
    // Hours are replay hours from the illustrative stage keyframes.
    expect(cellText(html, "compare-plan-flooded-cutoff")).toBe("10 Sep 23:00");
    expect(cellText(html, "compare-plan-all-cutoff")).toBe("11 Sep 10:00");
    expect(cellText(html, "compare-reported-flooded-cutoff")).toBe("10 Sep 22:00");
    expect(cellText(html, "compare-reported-all-cutoff")).toBe("Not reached in this replay: at least half keep access at every hour");
    expect(plain).toContain("Modelled access cut-off hour First replay hour when fewer than half of those within reach before the flood still have access");
    expect(plain).toContain("Newly lost because of the flood Out of those within reach before it");
    expect(cellText(html, "set-comparison-label")).toBe(
      "T1 scenario (model). Each set is counted two ways: all residents at road nodes, and residents whose homes flood at the modelled peak. No single figure ranks the sets; read both columns. Hours from illustrative stage keyframes, not observed.",
    );
    expect(cellText(html, "plan-reading")).toBe(
      "How to read the plan: it is built for evacuating before the water rises, on normal roads, so its cut-off hour comes first. The loss at the modelled peak counts residents who are still at home by then; it does not grade the choice of sites.",
    );
    // The reported set gets no such note: its sites were in use during the flood.
    expect(html.match(/data-testid="plan-reading"/g)).toHaveLength(1);
    expect(unsafeClaim(plain)).toBe(false);
  });

  it("has no headline that ranks the sets and no winner wording, in either language", () => {
    for (const set of ["reported", "plan"] as const) {
      for (const scope of ["all", "flooded"] as const) {
        const html = accessCard("en", set, shelters.knee_k, peak, scope);
        const plain = text(html);
        // No alert-toned hero figure and no KPI tile: every figure sits in a table row with its denominator.
        expect(html).not.toContain("data-tone=");
        expect(html).not.toContain('data-testid="access-lost"');
        expect(plain).not.toMatch(/better|best|worse|worst|outperform|winner|beats|superior|fail(s|ed|ure)?\b|last safe departure/i);
        const thai = text(accessCard("th", set, shelters.knee_k, peak, scope));
        expect(thai).not.toMatch(/ดีกว่า|แย่กว่า|ดีที่สุดคือ|ชนะ|ล้มเหลว|ออกเดินทางอย่างปลอดภัย/);
        expect(findWordingViolations(plain)).toEqual([]);
        expect(findWordingViolations(thai)).toEqual([]);
      }
    }
    // The comparison does not depend on the chosen scope or set: only the marker moves.
    const strip = (html: string) => /data-testid="set-comparison">(.*?)<p class="[^"]*" data-testid="access-without"/s.exec(html)![1].replace(/ data-selected=""/g, "").replace(/<span[^>]*data-testid="set-shown"[^>]*>.*?<\/span>/g, "");
    expect(strip(accessCard("en", "reported", shelters.knee_k, peak, "all"))).toBe(strip(accessCard("en", "plan", shelters.knee_k, peak, "flooded")));
  });

  it("renders the comparison in Thai with the same figures and the hours label", () => {
    const html = accessCard("th", "plan");
    const plain = text(html);
    expect(plain).toContain("สถานการณ์จำลองระดับ T1 (แบบจำลอง) · การเข้าถึงการอพยพ");
    expect(plain).toContain("ชุดที่พักพิงสองชุดเทียบกัน");
    expect(plain).toContain("ไม่มีตัวเลขใดตัวเลขเดียวที่ใช้จัดอันดับชุดที่พักพิง");
    expect(plain).toContain("ชั่วโมงมาจากจุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่ค่าที่สังเกตได้");
    expect(cellText(html, "compare-reported-all-baseline")).toBe("34,525 จาก 81,799");
    expect(cellText(html, "compare-plan-all-lost")).toBe("13,429 จาก 24,910 (54%)");
    expect(cellText(html, "compare-plan-flooded-cutoff")).toBe("10 ก.ย. 23:00 น.");
    expect(cellText(html, "compare-reported-all-cutoff")).toBe("ไม่ถึงเกณฑ์ในการย้อนดูนี้: อย่างน้อยครึ่งหนึ่งยังเดินถึงได้ทุกชั่วโมง");
    expect(cellText(html, "plan-reading")).toContain("วิธีอ่านแผน: แผนนี้ออกแบบสำหรับการอพยพก่อนน้ำขึ้น");
    expect(plain).toContain("ผู้อยู่อาศัยทั้งหมดที่จุดถนน");
    expect(plain).toContain("ผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด");
    expect(plain).toContain("แสดงบนแผนที่และในกราฟ");
  });

  it("words a missing cut-off hour and a set nobody can reach, and shows a dash for a share without a baseline", () => {
    expect(cutoffText({ status: "reached", hour: 46 }, "en")).toBe("10 Sep 22:00");
    expect(cutoffText({ status: "reached", hour: 46 }, "th")).toBe("10 ก.ย. 22:00 น.");
    expect(cutoffText({ status: "not_reached", hour: null }, "en")).toContain("Not reached in this replay");
    expect(cutoffText({ status: "no_baseline", hour: null }, "en")).toBe("None: no resident of this group has a shelter of this set within reach");
    expect(cutoffText({ status: "no_baseline", hour: null }, "th")).toContain("ไม่มีผู้อยู่อาศัยกลุ่มนี้");
    const none = { residents: 120, baseline: 0, keeping: 0, lost: 0, lostShare: null, vulnerableBaseline: 0, vulnerableLost: 0, cutoff: { status: "no_baseline", hour: null } } as const;
    const html = renderToStaticMarkup(<SetComparisonTable kind="reported" title="A set" comparison={{ all: none, flooded: none }} selected={false} language="en" />);
    expect(cellText(html, "compare-reported-all-baseline")).toBe("0 of 120");
    expect(cellText(html, "compare-reported-all-lost")).toBe("—");
    expect(cellText(html, "compare-reported-all-cutoff")).toContain("None: no resident of this group");
    expect(html).not.toContain("data-selected");
    expect(html).not.toContain("plan-reading");
  });

  it("states who is without a shelter for the chosen set and scope as context, after the comparison", () => {
    const summary = summaries[access.sets.indexOf(REPORTED_SET_ID)];
    const snapshot = accessSnapshot(summary, peak, access.levels);
    const html = accessCard("en", "reported");
    const plain = text(html);
    expect(html.indexOf('data-testid="access-without"')).toBeGreaterThan(html.indexOf('data-testid="set-compare-plan"'));
    expect(cellText(html, "access-without")).toBe(
      `Shelters reported used in Sep 2024, all residents at road nodes: ${people(snapshot.lost.population + snapshot.never.population)} / ${people(access.totals.population)} have no dry shelter of this set within a 2 km walk at this replay hour (${people(snapshot.lost.population)} lost it because of the flood; ${people(snapshot.never.population)} were already out of reach before it). Modelled residents (WorldPop 2020).`,
    );
    expect(plain).toContain("Evacuation Equity Gap");
    expect(plain).toContain("terrain/remoteness proxy");
    expect(plain).toContain("not demographic vulnerability");
    expect(text(accessCard("th", "reported"))).toContain("คนไม่มีที่พักพิงที่แห้งของชุดนี้ในระยะเดิน 2 กม. ณ ชั่วโมงนี้ของการย้อนดู");
  });

  it("states the scenario's confidence and source timestamps, and what the reported set assumes", () => {
    const plain = text(accessCard("en", "reported"));
    expect(plain).toContain("CONFIDENCE: LOW");
    expect(plain).toContain(access.source_timestamp);
    expect(plain).toContain(access.confidence_reason);
    expect(plain).toContain(`The ${reportedSiteCounts(shelters).counted} counted sites are assumed open for the whole replay, from before the flood.`);
    // The rule is shown without the internal set id.
    expect(plain).toContain(plainManifestText(shelters.reported_access_set_rule));
    expect(plain).not.toContain("reported_2024");
    // Mapped sites the manifest leaves out of the reported set are named; the command centre is one of them.
    const excluded = reportedSetExclusions(shelters);
    expect(excluded.map((shelter) => shelter.id).sort()).toEqual(["R04", "R05", "R19"]);
    for (const shelter of excluded) expect(plain).toContain(shelter.name_en);
    const plan = text(accessCard("en", "plan"));
    expect(plan).toContain("CONFIDENCE: LOW");
    expect(plan).not.toContain("counted sites are assumed open");
    const thai = text(accessCard("th", "reported"));
    expect(thai).toContain("ความเชื่อมั่น: ต่ำ");
    expect(thai).toContain("แสดงบนแผนที่แต่ไม่นับรวม");
    expect(thai).toContain("สมมุติว่าสถานที่ที่นับรวม");
  });

  it("names planning themes without presenting them as FPPS action classes", () => {
    const stats = districtStats(manifest, peak, roads, facilities);
    for (const language of ["en", "th"] as const) {
      const cards = text([
        renderToStaticMarkup(<PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language={language} />),
        renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={3} onPlanK={noop} language={language} onShowCandidate={noop} />),
      ].join(" "));
      expect(cards).not.toMatch(/ACTION CLASS [A-E]\b|กลุ่มการดำเนินการ [A-E]\b/);
      expect(cards).toContain(language === "en" ? "NO ACTION CLASS ASSIGNED" : "ไม่ได้กำหนดกลุ่มการดำเนินการ");
      expect(cards).toContain(language === "en" ? "THEME: PROTECT LIVES NOW" : "ประเด็น: ปกป้องชีวิตทันที");
    }
  });

  it("shows the k slider for the ranked plan with a live coverage sentence and matches the baked figures at the default size", () => {
    const html = accessCard("en", "plan");
    expect(html).toMatch(/type="range"[^>]*min="1"[^>]*max="12"/);
    const plain = text(html);
    expect(plain).toContain(`Plan size k = ${shelters.knee_k}`);
    expect(plain).not.toMatch(/knee/i);
    expect(plain).toContain(`${planCoverageSentence(shelters, shelters.knee_k, "en")} (default: the smallest plan that gets most of the benefit)`);
    expect(html).toContain(`aria-valuetext="${planCoverageSentence(shelters, shelters.knee_k, "en")}"`);
    const baked = peakDay.stats.access![planSetId(shelters.knee_k)];
    expect(plain).toContain(baked.people_lost_access.toLocaleString("en-US"));
    const three = text(accessCard("en", "plan", 3));
    expect(three).toContain(planCoverageSentence(shelters, 3, "en"));
    expect(three).not.toContain("(default:");
    const thai = text(accessCard("th", "plan", 3));
    expect(thai).toContain("การเดินถึงที่พักพิงที่แห้ง (สถานการณ์จำลอง)");
    expect(thai).toContain("ขนาดแผน k = 3");
    expect(thai).toContain(planCoverageSentence(shelters, 3, "th"));
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ");
  });

  it("lets the scope choose who the equity gap, the bars, the chart and the map count, without changing the comparison", () => {
    const flooded = scoped.flooded.totals.population;
    expect(Math.abs(flooded - shelters.demand_people)).toBeLessThan(1);
    for (const set of ["reported", "plan"] as const) {
      const html = accessCard("en", set, shelters.knee_k, peak, "flooded");
      const plain = text(html);
      expect(radioChecked(html, "mae-sai-access-scope", "flooded")).toBe(true);
      expect(radioChecked(html, "mae-sai-access-scope", "all")).toBe(false);
      expect(plain).toContain("Residents counted in the equity gap, the subdistrict bars, the chart and the map");
      expect(plain).toContain(`Residents whose homes flood at the peak (${people(flooded)})`);
      expect(plain).toContain(`All residents at road nodes (${people(access.totals.population)})`);
      expect(plain).toContain(`What the ranked plan optimises: sites that as many as possible of the ${people(shelters.demand_people)} residents whose homes flood at the modelled peak can walk to before the water rises`);
      expect(plain).toContain("which is why the two ways of counting below give different pictures of it.");
      const summary = scoped.flooded.summaries[access.sets.indexOf(set === "reported" ? REPORTED_SET_ID : planSetId(shelters.knee_k))];
      const snapshot = accessSnapshot(summary, peak, access.levels);
      const context = cellText(html, "access-without");
      expect(context).toContain("residents at road nodes whose homes flood at the modelled peak");
      expect(context).toContain(`${people(snapshot.lost.population + snapshot.never.population)} / ${people(flooded)} have no dry shelter`);
      expect(context).not.toContain(`/ ${people(access.totals.population)}`);
    }
    // Before the flood, the plan's scoped "already out of reach" is the demand minus the plan's own coverage.
    const dry = accessCard("en", "plan", shelters.knee_k, 0, "flooded");
    const coverage = shelters.plan[shelters.knee_k - 1].cumulative_demand;
    expect(cellText(dry, "access-without")).toContain(`(0 lost it because of the flood; ${people(shelters.demand_people - coverage)} were already out of reach before it)`);
    // Before the flood nobody is newly lost, and the cut-off hour is already known for the whole replay.
    expect(cellText(dry, "compare-plan-flooded-lost")).toBe(`0 of ${people(coverage)} (0%)`);
    expect(cellText(dry, "compare-plan-flooded-keeping")).toBe(people(coverage));
    expect(cellText(dry, "compare-plan-flooded-cutoff")).toBe("10 Sep 23:00");
    // The other scope counts everyone at a road node.
    const all = accessCard("en", "reported", shelters.knee_k, peak, "all");
    expect(radioChecked(all, "mae-sai-access-scope", "all")).toBe(true);
    expect(cellText(all, "access-without")).toContain(`/ ${people(access.totals.population)} have no dry shelter`);
  });

  it("states the equity rule in one sentence, then the ratio, then both counts per group (R8, option B)", () => {
    // Ranked plan of 8, all residents, at the peak: 320 of 373 against 13,109 of 24,537 within reach before the flood.
    const peakHtml = accessCard("en", "plan", shelters.knee_k, peak, "all");
    const peakText = text(withoutTips(peakHtml));
    expect(peakText).toContain("Evacuation Equity Gap: 1.61 · Among residents with a shelter within reach before the flood, proxy-vulnerable residents are about 1.6× more likely to lose it (85.77% vs 53.42%).");
    expect(cellText(peakHtml, "equity-rule")).toBe("What is compared. Of the residents in each group who had a shelter within reach before the flood, the share who lost it.");
    // Both counts of each group: lost out of those within reach before the flood, and all residents counted as context.
    expect(cellText(peakHtml, "equity-counts")).toBe(
      "Proxy-vulnerable: 320 lost of 373 within reach before the flood (7,152 residents counted). Everyone else: 13,109 lost of 24,537 within reach before the flood (74,647 residents counted).",
    );
    // The earlier denominator (all residents counted) read "less likely"; nothing on the card divides by it now.
    expect(peakText).not.toMatch(/less likely to lose (?:access|it) \(/);
    // No sentence prints a rate without naming the residents it divides by.
    expect(peakText).not.toMatch(/Proxy-vulnerable residents are about|of everyone else have\./);
    expect(peakText).not.toMatch(/320 of 7,152|13,109 of 74,647|all residents counted in that group/);
    expect(peakText).not.toMatch(/times as likely/);
    expect(cellText(peakHtml, "equity-why")).toBe(
      "How to read this: the proxy marks homes on slopes or far from a drivable road, not age, disability or income, and the ratio counts only residents who had a shelter of this set within reach before the flood. So a high ratio says where those homes sit relative to the flooded valley floor, not who is more vulnerable.",
    );
    expect(peakText).toContain("T1 scenario (model). Vulnerable = terrain/remoteness proxy. Hours from illustrative stage keyframes, not observed.");
    // Reading order inside the block: the ratio, the rule, the counts, how to read it, the labels.
    const at = (testId: string) => peakHtml.indexOf(`data-testid="${testId}"`);
    const order = ["equity-gap", "equity-rule", "equity-counts", "equity-why", "equity-label"].map(at);
    expect(order.every((position) => position > 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(peakHtml).not.toContain("data-reason=");
    // The detail text names the same denominator and the same minimum.
    expect(peakText).toContain("Each rate divides the residents of a group who lost access by the residents of that group who had a shelter of this set within reach before the flood.");
    expect(peakText).toContain("No ratio is shown when a group has fewer than 50 residents within reach before the flood, when no one has lost access, or when only proxy-vulnerable residents have");
    expect(findWordingViolations(peakText)).toEqual([]);
  });

  it("words the Equity Gap plainly, never as 0.00, when no proxy-vulnerable resident within reach has lost access", () => {
    // Reported set, all residents, at the peak: none of the 2,440 proxy-vulnerable residents within reach lost access.
    const reportedHtml = accessCard("en", "reported", shelters.knee_k, peak, "all");
    const reported = text(withoutTips(reportedHtml));
    expect(reported).toContain("Evacuation Equity Gap: no proxy-vulnerable resident has lost access · At this replay hour, 22.08% of everyone else who had a shelter within reach before the flood have lost it.");
    expect(reported).not.toContain("Evacuation Equity Gap: 0.00");
    expect(cellText(reportedHtml, "equity-counts")).toBe(
      "Proxy-vulnerable: 0 lost of 2,440 within reach before the flood (7,152 residents counted). Everyone else: 7,086 lost of 32,085 within reach before the flood (74,647 residents counted).",
    );
    expect(cellText(reportedHtml, "equity-why")).toContain("So a low ratio says where those homes sit relative to the flooded valley floor");
    expect(reportedHtml).not.toContain("data-reason=");
    const thaiHtml = accessCard("th", "reported", shelters.knee_k, peak, "all");
    const thaiPeak = text(thaiHtml);
    expect(thaiPeak).toContain("ช่องว่างความเท่าเทียมในการอพยพ: ไม่มีผู้ใดในกลุ่มเปราะบางตามตัวแทนสูญเสียการเข้าถึง · ณ ชั่วโมงนี้ของการย้อนดู กลุ่มอื่นที่มีที่พักพิงในระยะเดินก่อนน้ำท่วมสูญเสียการเข้าถึง 22.08%");
    // "ยังไม่มี" ("not yet") would imply the loss is about to happen.
    expect(thaiPeak).not.toContain("ยังไม่มีผู้อยู่อาศัยกลุ่มเปราะบาง");
    expect(thaiPeak).toContain("สถานการณ์จำลองระดับ T1 (แบบจำลอง) กลุ่มเปราะบาง = ตัวแทนจากภูมิประเทศและความห่างไกล");
    expect(cellText(thaiHtml, "equity-rule")).toBe("สิ่งที่นำมาเปรียบเทียบ: ในบรรดาผู้อยู่อาศัยของแต่ละกลุ่มที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม สัดส่วนของผู้ที่สูญเสียการเข้าถึง");
    expect(cellText(thaiHtml, "equity-counts")).toBe(
      "กลุ่มเปราะบางตามตัวแทน: สูญเสีย 0 จาก 2,440 คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด 7,152 คน) กลุ่มอื่น: สูญเสีย 7,086 จาก 32,085 คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด 74,647 คน)",
    );
    const thaiPlan = text(accessCard("th", "plan", shelters.knee_k, peak, "all"));
    expect(thaiPlan).toContain("ช่องว่างความเท่าเทียมในการอพยพ: 1.61 · ในกลุ่มผู้อยู่อาศัยที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม กลุ่มเปราะบางตามตัวแทนมีโอกาสสูญเสียการเข้าถึงมากกว่ากลุ่มอื่นประมาณ 1.6 เท่า (85.77% เทียบกับ 53.42%)");
    expect(thaiPlan).toContain("ค่าที่สูงจึงบอกตำแหน่งของบ้านเหล่านั้นเทียบกับพื้นที่ราบที่ถูกน้ำท่วม");
    expect(findWordingViolations(thaiPlan)).toEqual([]);
  });

  it("shows no ratio and says why when no one has lost access (reason no_loss)", () => {
    const html = accessCard("en", "reported", shelters.knee_k, 0, "all");
    const dry = text(html);
    expect(html).toContain('data-testid="equity-gap" data-reason="no_loss"');
    expect(dry).toContain("Evacuation Equity Gap: no ratio shown · No one in either group has lost access at this replay hour, so there are no loss rates to compare.");
    expect(dry).not.toMatch(/Evacuation Equity Gap: (—|1\.00|0\.00)/);
    expect(dry).not.toContain("How to read this: the proxy");
    // The rule and the counts stay, so the reader sees who could lose access.
    expect(cellText(html, "equity-rule")).toContain("Of the residents in each group who had a shelter within reach before the flood, the share who lost it.");
    expect(cellText(html, "equity-counts")).toContain("Proxy-vulnerable: 0 lost of 2,440 within reach before the flood (7,152 residents counted).");
    const thai = text(accessCard("th", "reported", shelters.knee_k, 0, "all"));
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ: ไม่แสดงอัตราส่วน · ไม่มีผู้ใดในทั้งสองกลุ่มสูญเสียการเข้าถึง ณ ชั่วโมงนี้ของการย้อนดู จึงไม่มีอัตราการสูญเสียให้เปรียบเทียบ");
  });

  it("shows no ratio in the default view, and says in plain words that no proxy-vulnerable resident was within reach", () => {
    // The default view: the reported set, residents whose homes flood. 103 proxy-vulnerable residents are counted and
    // none had a reported shelter within reach before the flood, so the group has no loss rate.
    for (const stage of [peak, 0]) {
      const html = accessCard("en", "reported", shelters.knee_k, stage, "flooded");
      const plain = text(html);
      expect(html).toContain('data-testid="equity-gap" data-reason="insufficient_group_denominator"');
      expect(plain).toContain(
        "Evacuation Equity Gap: no ratio shown · No proxy-vulnerable resident counted here had a shelter within reach before the flood, so none could lose it. A ratio needs at least 50 such residents in each group.",
      );
      expect(cellText(html, "equity-counts")).toMatch(/^Proxy-vulnerable: 0 lost of 0 within reach before the flood \(103 residents counted\)\. Everyone else: [\d,]+ lost of 5,698 within reach before the flood \(14,067 residents counted\)\.$/);
      expect(plain).not.toContain("How to read this: the proxy");
      expect(plain).not.toMatch(/Evacuation Equity Gap: (—|\d)/);
      expect(findWordingViolations(plain)).toEqual([]);
    }
    expect(cellText(accessCard("en", "reported", shelters.knee_k, peak, "flooded"), "equity-counts")).toContain("Everyone else: 5,400 lost of 5,698");
    const thai = text(accessCard("th", "reported", shelters.knee_k, peak, "flooded"));
    expect(thai).toContain(
      "ช่องว่างความเท่าเทียมในการอพยพ: ไม่แสดงอัตราส่วน · ไม่มีผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนที่นับในที่นี้มีที่พักพิงในระยะเดินตั้งแต่ก่อนน้ำท่วม จึงไม่มีผู้ใดในกลุ่มนี้สูญเสียการเข้าถึงได้ การแสดงอัตราส่วนต้องมีผู้อยู่อาศัยเช่นนี้อย่างน้อยกลุ่มละ 50 คน",
    );
    expect(thai).toContain("กลุ่มเปราะบางตามตัวแทน: สูญเสีย 0 จาก 0 คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด 103 คน)");
    expect(findWordingViolations(thai)).toEqual([]);
  });

  it("shows no ratio and names the group when fewer than 50 of its residents were within reach (reason insufficient_group_denominator)", () => {
    // Ranked plan of 8, residents whose homes flood: 27 of the 103 proxy-vulnerable residents had a site within reach.
    const html = accessCard("en", "plan", shelters.knee_k, peak, "flooded");
    const plain = text(html);
    expect(html).toContain('data-testid="equity-gap" data-reason="insufficient_group_denominator"');
    expect(plain).toContain("Evacuation Equity Gap: no ratio shown · Only 27 proxy-vulnerable residents had a shelter within reach before the flood, fewer than the 50 a ratio needs in each group.");
    expect(cellText(html, "equity-counts")).toBe(
      "Proxy-vulnerable: 27 lost of 27 within reach before the flood (103 residents counted). Everyone else: 7,094 lost of 7,553 within reach before the flood (14,067 residents counted).",
    );
    expect(plain).not.toContain("How to read this: the proxy");
    expect(plain).toContain("No ratio is shown when a group has fewer than 50 residents within reach before the flood, when no one has lost access, or when only proxy-vulnerable residents have");
    const thai = text(accessCard("th", "plan", shelters.knee_k, peak, "flooded"));
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ: ไม่แสดงอัตราส่วน · กลุ่มเปราะบางตามตัวแทนมีผู้อยู่อาศัยที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม 27 คน น้อยกว่า 50 คนที่ต้องมีในแต่ละกลุ่มจึงจะแสดงอัตราส่วนได้");
    expect(thai).toContain("ไม่แสดงอัตราส่วนเมื่อกลุ่มใดมีผู้อยู่อาศัยที่มีที่พักพิงในระยะเดินก่อนน้ำท่วมน้อยกว่า 50 คน");
    // The residents counted are enough in both scopes; it is the residents within reach that fall short.
    for (const scope of ["all", "flooded"] as const) {
      expect(scoped[scope].totals.vulnerable).toBeGreaterThanOrEqual(50);
      expect(scoped[scope].totals.nonVulnerable).toBeGreaterThanOrEqual(50);
    }
    // No plan size reaches 50 proxy-vulnerable residents among those whose homes flood: the default scope never shows a ratio.
    for (let k = 1; k <= shelters.plan.length; k += 1) {
      expect(accessCard("en", "plan", k, peak, "flooded"), `plan of ${k}`).toContain('data-reason="insufficient_group_denominator"');
    }
  });

  it("explains terms on hover or focus with the glossary definition as the accessible description", () => {
    const html = renderToStaticMarkup(<Term id="road_nodes" language="en">road nodes</Term>);
    const id = /aria-describedby="([^"]+)"/.exec(html)![1];
    expect(html).toContain(`tabindex="0"`);
    expect(html).toContain(`role="tooltip" id="${id}"`);
    expect(text(html)).toContain("Points on the OpenStreetMap road network");
    expect(text(accessCard("en", "reported"))).toContain("Points on the OpenStreetMap road network");
    // Closed until the pointer or the focus reaches the term; the page opens it (and Escape closes it) from then on.
    expect(html).not.toContain("data-open");
    expect(html).toMatch(/<span role="tooltip" id="[^"]+" class="[^"]*termTip[^"]*">/);
  });

  it("reports loading and failure honestly instead of showing zeros", () => {
    const loading = text(renderToStaticMarkup(
      <AccessCard access={access} shelters={shelters} snapshot={null} series={null} time={0} names={names} tambonTotals={null}
        shelterSet="reported" planK={8} onShelterSet={noop} onPlanK={noop} showCutoff={false} onShowCutoff={noop}
        scope="flooded" onScope={noop} scopeTotals={null} allResidents={access.totals.population} floodedResidents={shelters.demand_people} comparison={null} language="en" status="loading" />,
    ));
    expect(loading).toContain("Preparing the access scenario");
    const failed = text(renderToStaticMarkup(
      <AccessCard access={access} shelters={shelters} snapshot={null} series={null} time={0} names={names} tambonTotals={null}
        shelterSet="reported" planK={8} onShelterSet={noop} onPlanK={noop} showCutoff={false} onShowCutoff={noop}
        scope="flooded" onScope={noop} scopeTotals={null} allResidents={access.totals.population} floodedResidents={shelters.demand_people} comparison={null} language="en" status="error" />,
    ));
    expect(failed).toContain("could not be loaded");
    expect(failed).not.toMatch(/Evacuation Equity Gap/);
    // No comparison table is drawn from nothing.
    expect(loading).not.toContain("side by side");
    expect(failed).not.toContain("side by side");
  });

  it("draws the replay curve of people who lost access with the playhead", () => {
    const summary = summaries[access.sets.indexOf(REPORTED_SET_ID)];
    const series = accessLostSeries(summary, hourlyStages(manifest.stage_anchors), access.levels);
    const html = renderToStaticMarkup(<AccessChart series={series} time={3.5} language="en" label="Reported" />);
    expect(html).toContain('role="img"');
    expect(html).toMatch(/aria-label="Reported: people who lost walking access to a dry shelter, 9–19 Sep\. Peak [\d,]+ at \d+ Sep \d{2}:00; [\d,]+ at this replay hour\."/);
    expect(html.match(/<text/g)!.length).toBeGreaterThanOrEqual(11 + 3);
  });
});

describe("Shelter plan and reported shelters", () => {
  it("draws the coverage curve with the default size and the selected k, and states the gap", () => {
    const curve = renderToStaticMarkup(<CoverageCurve shelters={shelters} k={3} language="en" />);
    expect(curve).toContain(`default k = ${shelters.knee_k}`);
    // Plain words only ("knee" survives only in CSS class names).
    expect(text(curve)).not.toMatch(/knee/i);
    expect(/aria-label="([^"]*)"/.exec(curve)![1]).not.toMatch(/knee/i);
    expect(curve).toMatch(/Selected k = 3: \d+% pre-emptive, \d+% late/);
    // The y axis says what the percentages are.
    expect(curve).toMatch(/<text[^>]*transform="rotate\(-90[^"]*"[^>]*>Flooded-home residents covered<\/text>/);
    const html = renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={shelters.knee_k} onPlanK={noop} language="en" onShowCandidate={noop} />);
    const plain = text(withoutTips(html));
    expect(plain).toContain("Ranked range, not a fixed number: the first k entries are the plan for k shelters");
    expect(plain).toContain(`The default, k = ${shelters.knee_k}, is the smallest plan that reaches 90% of what all ${shelters.plan.length} ranked sites reach.`);
    expect(plain).not.toMatch(/\(\d+%\)\.? ?$/m);
    // Same slider label and live sentence as the access card.
    expect(plain).toContain(`Plan size k = ${shelters.knee_k}`);
    expect(plain).toContain(planCoverageSentence(shelters, shelters.knee_k, "en"));
    expect(plain).toContain("Shelter gap");
    expect(plain).toContain(`${shelters.uncoverable_people.toLocaleString("en-US")} residents in the modelled peak flood zone have no eligible dry site`);
    expect(plain).toContain("planning scenario");
    expect(html.match(/<li[\s>]/g)!.length).toBeGreaterThanOrEqual(shelters.knee_k);
    expect(unsafeClaim(plain)).toBe(false);
    const thai = text(renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={2} onPlanK={noop} language="th" onShowCandidate={noop} />));
    expect(thai).toContain("ช่องว่างของที่พักพิง");
    expect(thai).toContain("2 แห่งแรกของแผน");
    expect(plain).toContain("CONFIDENCE: LOW");
    expect(plain).toContain(shelters.source_timestamp);
  });

  it("badges plan sites whose capacity is unknown or far below their load, and labels Thai-only names in English", () => {
    const k = shelters.knee_k;
    const sites = planSites(shelters, k);
    const html = renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={k} onPlanK={noop} language="en" onShowCandidate={noop} />);
    const plain = text(html);
    const flagged = sites.filter((site) => capacityFlag(site) !== null);
    expect(html.match(/data-testid="capacity-flag"/g)?.length ?? 0).toBe(flagged.length);
    for (const site of flagged) expect(plain).toContain(capacityFlagText(site, "en"));
    if (flagged.length > 0) expect(plain).toContain(`${flagged.length} of these site${flagged.length === 1 ? " is" : "s are"} marked “!”`);
    expect(capacityFlagText({ load: 1782, capacity: 41 }, "en")).toBe("Capacity far below its load: ≈ 41 places for ≈ 1,782 residents assigned");
    expect(capacityFlagText({ load: 500, capacity: null }, "en")).toContain("Capacity unknown");
    expect(capacityFlagText({ load: 10, capacity: 400 }, "en")).toBe("");
    // "an 8-site plan", "a 3-site plan".
    expect(plain).toContain(`residents in ${indefiniteArticle(k)} ${k}-site plan`);
    expect([indefiniteArticle(8), indefiniteArticle(3), indefiniteArticle(11), indefiniteArticle(18), indefiniteArticle(80), indefiniteArticle(12)]).toEqual(["an", "a", "an", "an", "an", "a"]);
    // Thai-only names get an English type label in English and stay as mapped in Thai.
    const thaiOnlySite = sites.find((site) => /^[฀-๿\s.()\-–]+$/.test(site.candidate.name.trim()) && site.candidate.name.trim().length > 0);
    if (thaiOnlySite) {
      const english = candidateTitle(thaiOnlySite.candidate, "en");
      expect(english).toMatch(new RegExp(`^[A-Z][A-Za-z ]+ · ${thaiOnlySite.candidate.name.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
      expect(plain).toContain(english);
      expect(candidateTitle(thaiOnlySite.candidate, "th")).toBe(thaiOnlySite.candidate.name.trim());
    }
  });

  it("keeps the coverage curve's axis title clear of its tick labels", () => {
    const curve = renderToStaticMarkup(<CoverageCurve shelters={shelters} k={3} language="en" />);
    const ys = (pattern: RegExp) => [...curve.matchAll(pattern)].map((match) => Number(match[1]));
    const ticks = ys(/<text[^>]*y="([\d.]+)"[^>]*>\d+<\/text>/g).filter((y) => y > 150);
    const [title] = ys(/<text[^>]*y="([\d.]+)"[^>]*>Plan size k \(sites in the plan\)<\/text>/g);
    expect(ticks.length).toBe(shelters.plan.length);
    // 18 viewBox units between baselines leaves room for the 12 px mobile labels.
    for (const tick of ticks) expect(title - tick).toBeGreaterThanOrEqual(18);
  });

  it("lists every candidate the map shows only as a ring or dot, with reasons, and marks those outside the model", () => {
    const closed = renderToStaticMarkup(<OtherCandidatesCard shelters={shelters} k={shelters.knee_k} language="en" onShowCandidate={noop} />);
    const eligibleOutside = shelters.eligible_count - shelters.knee_k;
    const ineligible = shelters.candidates.length - shelters.eligible_count;
    expect(text(closed)).toContain(`Other shelter candidates: ${eligibleOutside} eligible outside the first ${shelters.knee_k}, ${ineligible} not eligible`);
    const html = renderToStaticMarkup(<OtherCandidatesList shelters={shelters} k={shelters.knee_k} language="en" onShowCandidate={noop} />);
    expect(html.match(/>Show on map</g)).toHaveLength(eligibleOutside + ineligible);
    expect(text(html)).toContain(`Eligible, not in the first ${shelters.knee_k} (${eligibleOutside})`);
    expect(text(html)).toContain(`Not eligible (${ineligible})`);
    // The bake cuts OpenStreetMap to the replay area, so every candidate of the served revision lies inside the terrain
    // model. The outside-model wording is still the page's answer for a revision that has such a site, so it is
    // exercised on a copy with one ineligible candidate moved outside the model.
    expect(shelters.candidates.filter((candidate) => !candidate.m)).toEqual([]);
    expect(shelters.candidates.some((candidate) => candidate.ineligible_reasons.includes("outside_model"))).toBe(false);
    const moved = shelters.candidates.find((candidate) => !candidate.eligible)!;
    const outside = { ...moved, m: false, h: null, freeboard_m: null, high_ground: false, ineligible_reasons: ["outside_model", "no_road_within_400m"] };
    const withOutside = { ...shelters, candidates: shelters.candidates.map((candidate) => (candidate.id === moved.id ? outside : candidate)) };
    const outsideHtml = renderToStaticMarkup(<OtherCandidatesList shelters={withOutside} k={shelters.knee_k} language="en" onShowCandidate={noop} />);
    const title = candidateTitle(outside, "en").replaceAll("&", "&amp;");
    const item = text(outsideHtml.split("<li").slice(1).find((entry) => entry.includes(title))!);
    expect(item).toContain("Outside the terrain model (no flood result)");
    expect(item).toContain("Not modelled: the site lies outside the terrain model");
    expect(item).not.toContain("High ground");
    expect(item).not.toContain("keeps less than");
    expect(text(html)).not.toContain("Outside the terrain model");
    const thai = text(renderToStaticMarkup(<OtherCandidatesList shelters={withOutside} k={3} language="th" onShowCandidate={noop} />));
    expect(thai).toContain("อยู่นอกแบบจำลองภูมิประเทศ");
    expect(unsafeClaim(text(html))).toBe(false);
  });

  it("describes candidates, capacity basis, freeboard and screening reasons", () => {
    const unnamed = shelters.candidates.find((candidate) => !candidate.name.trim())!;
    expect(candidateTitle(unnamed, "en")).toMatch(/^Unnamed [a-z ]+ \(OSM (way|node|relation) \d+\)$/);
    expect(candidateTitle(unnamed, "th")).toMatch(/ไม่มีชื่อ \(OSM (way|node|relation) \d+\)$/);
    const sized = shelters.candidates.find((candidate) => candidate.capacity_est !== null)!;
    expect(capacityText(sized, shelters, "en")).toContain("× 50% usable ÷ 3.5 m² per person, Sphere minimum");
    expect(capacityText({ capacity_est: null, footprint_m2: 0 }, shelters, "en")).toContain("Capacity unknown");
    expect(freeboardText({ freeboard_m: 1.35, high_ground: false, m: true }, "en")).toBe("Freeboard at the modelled peak: 1.35 m.");
    expect(freeboardText({ freeboard_m: -0.6, high_ground: false, m: true }, "en")).toContain("Floods at the modelled peak");
    expect(freeboardText({ freeboard_m: null, high_ground: true, m: true }, "th")).toContain("พื้นที่สูง");
    expect(ineligibleReasonText("no_road_within_400m", shelters, "en")).toBe("No mapped road node within 400 m");
    expect(ineligibleReasonText("floods_or_under_freeboard_at_peak", shelters, "en")).toContain("0.5 m freeboard");
  });

  it("lists every reported shelter with sources, located or not, and its model check", () => {
    const html = renderToStaticMarkup(<ReportedSheltersCard shelters={shelters} language="en" onShowReported={noop} />);
    const plain = text(html);
    expect(html.match(/<details>/g)).toHaveLength(shelters.reported.length);
    for (const shelter of shelters.reported) {
      expect(plain).toContain(shelter.name_en);
      expect(plain).toContain(reportedCheckText(reportedShelterCheck(shelter), shelters, "en"));
      for (const source of shelter.sources) expect(html).toContain(`href="${source.url.replaceAll("&", "&amp;")}"`);
    }
    expect(plain).toContain("Not located on the map");
    // The flooding line appears only when the manifest flags a located site as flooding at the modelled peak.
    const floods = shelters.reported.some((shelter) => reportedShelterCheck(shelter).status === "floods");
    expect(plain.includes("The model says this site floods at the modelled peak")).toBe(floods);
    expect(plain).toContain("dry at the modelled peak");
    expect(html).toContain('rel="noopener noreferrer"');
    const unlocated = shelters.reported.filter((shelter) => shelter.lat === null).length;
    expect(html.match(/Show on map/g)).toHaveLength(shelters.reported.length - unlocated);
    const thai = text(renderToStaticMarkup(<ReportedSheltersCard shelters={shelters} language="th" onShowReported={noop} />));
    for (const shelter of shelters.reported) expect(thai).toContain(shelter.name_th);
  });

  it("presents the district office as a relief and command site and states the list's status and source dates", () => {
    const html = renderToStaticMarkup(<ReportedSheltersCard shelters={shelters} language="en" onShowReported={noop} />);
    const plain = text(html);
    const total = shelters.reported.length;
    const counts = reportedSiteCounts(shelters);
    expect(counts.commandCentres).toBe(1);
    expect(plain).toContain(`Sites reported in use (${total}): ${total - 1} shelters, 1 relief and command site`);
    expect(plain).not.toContain("Shelters reported in use");
    expect(html.match(/data-role="relief_command"/g)).toHaveLength(1);
    expect(plain).toContain("Relief command centre (not a shelter)");
    for (const shelter of shelters.reported) expect(plain).toContain(plainManifestText(shelter.access_set_note));
    expect(plain).toContain("not an official register");
    // The source timestamp already names the compile date: it is stated once, and the set rule lives on the access card.
    expect(plain).toContain(shelters.source_timestamp);
    // (Source dates such as "accessed 2026-09-27" are the sources' own and may repeat the day.)
    expect(plain.split(`compiled ${shelters.reported_compiled}`).length - 1).toBe(1);
    expect(plain).not.toContain(plainManifestText(shelters.reported_access_set_rule));
    expect(plain).toContain("CONFIDENCE: LOW");
    // The confidence line is a one-line chip that opens to the details.
    expect(html).toMatch(/<details class="[^"]*provenance[^"]*" data-testid="reported-provenance"><summary>/);
    expect(html).not.toMatch(/data-testid="reported-provenance"[^>]*open/);
    const thai = text(renderToStaticMarkup(<ReportedSheltersCard shelters={shelters} language="th" onShowReported={noop} />));
    expect(thai).toContain(`สถานที่ที่มีรายงานว่าใช้จริง (${total}): ที่พักพิง ${total - 1} แห่ง ศูนย์บัญชาการและจุดช่วยเหลือ 1 แห่ง`);
    expect(thai).toContain("ศูนย์บัญชาการและจุดช่วยเหลือ (ไม่ใช่ที่พักพิง)");
    // Thai: Buddhist-era year with the CE year, and each site's set note in Thai.
    expect(thai).toContain("รายงานสาธารณะ · กันยายน 2567 (2024)");
    for (const shelter of shelters.reported) expect(thai).toContain(localizedText(shelter.access_set_note, "th").text);
  });

  it("renders the size checks with their sources", () => {
    const html = renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" />);
    expect(sizeChecks(manifest.external_checks).map((check) => check.id)).toEqual(["gistda-radarsat2-20240910", "unosat-3991"]);
    for (const check of sizeChecks(manifest.external_checks)) {
      expect(text(html)).toContain(`reported ${check.reported_km2} km²`);
      expect(text(html)).toContain(`${Number(check.model_km2.toFixed(1))} km²`);
      for (const url of check.urls) expect(html).toContain(`href="${url.replaceAll("&", "&amp;")}"`);
    }
    const plain = text(html);
    expect(plain).toContain("Magnitude check over the same window only");
    // Said once (from the manifest), not twice; the source's own wording is quoted, so no brackets nest.
    expect(plain.match(/[Mm]agnitude check/g)).toHaveLength(1);
    expect(plain).not.toMatch(/\([^()]*\([^()]*\)[^()]*\)/);
    expect(plain).not.toMatch(/\bkm2\b/);
    expect(renderToStaticMarkup(<ExternalChecks manifest={{ ...manifest, external_checks: [] }} language="en" />)).toBe("");
    // Without a "use" sentence the page states the limit itself.
    const bare = text(renderToStaticMarkup(<ExternalChecks manifest={{ ...manifest, external_checks: manifest.external_checks!.map((check) => ({ ...check, use: "" })) }} language="en" />));
    expect(bare).toContain("Magnitude check only, not a spatial validation.");
    // The comparison with the season envelope is not a size check: without the envelope's own files the page shows
    // nothing of it, and it never appears under a size-check heading.
    expect(manifest.external_checks!.some((check) => check.role === "season_envelope_plausibility")).toBe(true);
    expect(plain).not.toMatch(/Season envelope|product 4009|undefined|NaN/);
    expect(text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" envelope={{ status: "absent" }} />))).toBe(plain);
  });

  it("files the GISTDA onset figure as a calibration anchor and UNOSAT as a calibration-informed check over its own window", () => {
    const plain = text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" />));
    const calibration = plain.indexOf("Calibration anchor (not an independent check)");
    const informed = plain.indexOf("Size checks (calibration-informed, not independent)");
    expect(calibration).toBeGreaterThanOrEqual(0);
    expect(informed).toBeGreaterThan(calibration);
    // Nothing on the replay is independent any more, so the page must not claim an independent check.
    expect(plain).not.toContain("Independent size checks");
    const gistda = plain.indexOf("GISTDA RADARSAT-2");
    const unosat = plain.indexOf("UNOSAT product 3991");
    expect(gistda).toBeGreaterThan(calibration);
    expect(gistda).toBeLessThan(informed);
    expect(unosat).toBeGreaterThan(informed);
    expect(plain).toContain("this figure was known while the stage keyframes were tuned");
    expect(plain).toContain("time zone not stated; assumed ICT");
    // The anchor text follows the manifest: matched by construction, or how far the closest stage stays and why.
    const anchor = sizeChecks(manifest.external_checks).find((check) => check.role === "calibration_anchor")!;
    const gap = Math.abs(anchor.model_km2 - anchor.reported_km2);
    if (gap / anchor.reported_km2 <= 0.1) {
      expect(plain).toContain("agreement holds by construction and does not test the model");
    } else {
      expect(plain).not.toContain("agreement holds by construction");
      expect(plain).toContain(`The model gives ${Number(anchor.model_km2.toFixed(1))} km² at the ${anchor.model_stage_m} m stage set closest to it.`);
      expect(plain).toContain(`even the closest stage stays ${gap.toFixed(1)} km² (${Math.round((gap / anchor.reported_km2) * 100)}%) ${anchor.model_km2 > anchor.reported_km2 ? "above" : "below"} it.`);
      const smallest = smallestFloodedExtent(manifest)!;
      if (smallest.km2 > anchor.reported_km2) {
        expect(plain).toContain(`its smallest non-zero extent, land within ${smallest.stage_m.toFixed(2)} m of the channel level, is already ${smallest.km2.toFixed(1)} km².`);
      }
    }
    const unosatCheck = sizeChecks(manifest.external_checks).find((check) => check.role === "calibration_informed_magnitude_check")!;
    const people = (value: number) => value.toLocaleString("en-US");
    expect(plain).toContain(`The model gives ${Number(unosatCheck.model_km2.toFixed(1))} km² and ≈ ${people(unosatCheck.model_people_in_water!)} modelled residents in water at a ${unosatCheck.model_stage_m} m stage`);
    expect(plain).toContain(unosatCheck.model_window!);
    expect(plain).toContain(`For reference, the modelled peak gives ${Number(unosatCheck.model_peak_km2!.toFixed(1))} km² and ≈ ${people(unosatCheck.model_peak_people_in_water!)} residents in water.`);
    const district = Math.round(manifest.model_coverage.district_km2);
    expect(plain).toContain(coverageComplete(manifest.model_coverage)
      ? `Model figures cover the whole of Mae Sai district (${district} km²)`
      : `Model figures cover the modelled part of Mae Sai district (${Math.round(manifest.model_coverage.modelled_km2)} of ${district} km²)`);
    const thai = text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="th" />));
    expect(thai).toContain("จุดอ้างอิงที่ใช้ปรับแบบจำลอง (ไม่ใช่การตรวจสอบอิสระ)");
    expect(thai).toContain("การตรวจสอบขนาด (มีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ)");
    expect(thai).toContain(`แบบจำลองให้ค่า ${Number(unosatCheck.model_km2.toFixed(1))} ตร.กม.`);
    // Every manifest sentence of the checks has a Thai rendering, so no "kept in the original" note is needed.
    expect(thai).toContain("ไม่ใช่การยืนยันตำแหน่งของแบบจำลอง");
    expect(thai).toContain("ผลิตภัณฑ์ UNOSAT 3991");
    expect(thai).not.toContain("คงไว้เป็นภาษาต้นฉบับ");
    expect(thai).not.toContain("Magnitude check");
  });
});

describe("Map legend for residents, shelters and the cut-off heat", () => {
  it("switches to a people-per-hectare legend and adds shelter and cut-off entries when shown", () => {
    const people = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities={false} waterMode="people"
      densityMax={manifest.population!.max_per_ha} shelters={{ reported: true, candidates: true, ineligible: true }} cutoff />));
    expect(people).toContain("People in flood water: residents per hectare (WorldPop 2020, model)");
    expect(people).toContain("Wet, no mapped residents");
    expect(people).toContain(`capped at ${manifest.population!.max_per_ha.toFixed(1)} people/ha`);
    expect(people).toContain("Reported in use, Sep 2024");
    expect(people).toContain("Reported, but floods at the modelled peak");
    expect(people).toContain("Plan rank (first k sites)");
    expect(people).toContain("Not eligible (reasons in the popup and the other-candidates list)");
    expect(people).not.toContain("Relief and command site");
    expect(people).not.toContain("Not modelled (outside the terrain model)");
    const full = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false}
      shelters={{ reported: true, candidates: false, ineligible: true, command: true, unmodelled: true }} />));
    expect(full).toContain("Relief and command site (not a shelter)");
    expect(full).toContain("Not modelled (outside the terrain model)");
    expect(people).toContain("People cut off from a dry shelter (scenario)");
    expect(people).not.toContain("Water depth (model)");
    const residents = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads={false} unmodelledFacilities={false} waterMode="residents" densityMax={31.33} />));
    expect(residents).toContain("ผู้อยู่อาศัยทั้งหมด คนต่อเฮกตาร์");
    expect(residents).not.toContain("ที่พักพิง");
    // Without a density raster the residents views fall back to the depth legend.
    const fallback = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} waterMode="people" />));
    expect(fallback).toContain("Water depth (model)");
  });
});

describe("Capacity-aware view and what-if levels on the shelter plan card", () => {
  const k = shelters.knee_k;
  const card = (language: "en" | "th", size = k, data = shelters) =>
    renderToStaticMarkup(<ShelterPlanCard shelters={data} k={size} onPlanK={noop} language={language} onShowCandidate={noop} />);

  it("shows who fits beside the existing plan, under both bounds, with overflow = demand − fit", () => {
    const html = card("en");
    const view = capacityAwareView(shelters, k)!;
    // The existing plan and its numbers stay: the coverage sentence, the list and the nearest-site loads.
    const plain = text(withoutTips(html));
    expect(plain).toContain(planCoverageSentence(shelters, k, "en"));
    expect(plain).toContain("Assigned ≈ 2,430 residents in an 8-site plan");
    // The capacity-aware block comes after the plan list, inside the same card.
    expect(html.indexOf('data-testid="capacity-aware"')).toBeGreaterThan(html.indexOf("Loads assign each covered resident"));
    expect(plain).toContain("If capacity counts: who fits (two bounds)");
    expect(plain).toContain("Lower bound: a site with no capacity estimate holds nobody. Upper bound: it holds the median estimate of its site kind.");
    for (const [name, part] of [["coverage", view.coverage], ["ranked", view.ranked], ["full", view.full], ["all", view.allEligible]] as const) {
      for (const bound of ["lower", "upper"] as const) {
        expect(cellText(html, `capacity-${name}-${bound}`), `${name} ${bound}`).toBe(`${people(part[bound].served)} overflow ${people(part[bound].overflow)}`);
        expect(part[bound].served + part[bound].overflow).toBe(shelters.demand_people);
      }
    }
    expect(cellText(html, "capacity-coverage-lower")).toBe("495 overflow 13,674");
    expect(cellText(html, "capacity-coverage-upper")).toBe("1,057 overflow 13,112");
    expect(plain).toContain("The first 8 sites of the plan above Ranked by who can walk there · 7,580 within the walk");
    expect(plain).toContain("The first 8 sites of the capacity-aware ranking");
    expect(plain).toContain("All 25 sites of the capacity-aware ranking The ranking ends when the next site adds less than 0.5% of demand");
    expect(plain).toContain("Every eligible candidate (95) 42 with a capacity estimate");
    expect(cellText(html, "capacity-aware-sentence")).toBe(
      "Reading for k = 8: 7,580 residents can walk to the first 8 sites of the plan above, and the capacity estimates hold 495 to 1,057 of them. That leaves 13,112 to 13,674 of the 14,169 without a place.",
    );
    expect(plain).toContain("Residents who fit, of the 14,169 whose homes flood at the peak (overflow = demand − fit)");
    // Confidence, reason and source timestamp of the block's own figures.
    const provenance = /data-testid="capacity-provenance".*?<\/details>/s.exec(html)![0];
    expect(text(provenance)).toContain("CONFIDENCE: LOW");
    expect(text(provenance)).toContain(shelters.capacitated!.confidence_reason);
    expect(text(provenance)).toContain(shelters.capacitated!.source_timestamp);
  });

  it("states the six caveats in English and Thai and never tells the reader which shelters to open", () => {
    const english = text(/data-testid="capacity-caveats".*?<\/ul>/s.exec(card("en"))![0]);
    for (const phrase of [
      "T1 scenario (model)",
      "Demand is every resident of a home that floods at the modelled peak. That is an upper bound: many people stay with relatives",
      "Capacity is an unverified estimate from mapped building footprints",
      "53 of the 95 eligible candidates have no footprint to estimate from",
      "Neither bound is a limit on who fits.",
      "More residents may fit than the upper bound gives, and fewer than the lower bound if a site turns out unusable.",
      "candidates to verify on the ground, not a list of sites to open",
      "The planning overlay's listed-capacity figures come from a different source",
    ]) expect(english).toContain(phrase);
    expect(capacityCaveats(shelters, "en")).toHaveLength(6);
    // The column headings say what each bound assumes, so "upper bound" is not read as the most that can fit.
    expect(card("en")).toContain('data-testid="capacity-bound-lower">Lower bound<small>a site with no footprint holds nobody</small></th>');
    expect(card("en")).toContain('data-testid="capacity-bound-upper">Upper bound<small>a site with no footprint holds a typical size; not a maximum</small></th>');
    expect(card("th")).toContain('data-testid="capacity-bound-upper">ขอบเขตบน<small>สถานที่ที่ไม่มีขอบเขตอาคารรับได้ตามขนาดทั่วไป ไม่ใช่ค่าสูงสุด</small></th>');
    expect(shelters.capacitated!.bounds.note).toContain("Neither is a limit on who fits");
    const thai = text(/data-testid="capacity-caveats".*?<\/ul>/s.exec(card("th"))![0]);
    for (const phrase of [
      "สถานการณ์จำลองระดับ T1 (แบบจำลอง)",
      "เป็นค่าขอบเขตบน เพราะหลายคนไปพักกับญาติ",
      "ยังไม่ได้ตรวจสอบ",
      "ทั้งสองขอบเขตไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้",
      "สถานที่ที่ควรตรวจสอบในพื้นที่ ไม่ใช่รายชื่อสถานที่ที่ต้องเปิด",
      "มาจากแหล่งข้อมูลอื่น",
    ]) expect(thai).toContain(phrase);
    for (const language of ["en", "th"] as const) {
      for (const size of [1, 3, k, shelters.plan.length]) {
        const html = card(language, size);
        expect(findWordingViolations(text(html)), `${language} k=${size}`).toEqual([]);
        expect(text(html)).not.toMatch(/open these shelters|shelters to open|เปิดที่พักพิงเหล่านี้/i);
        // No listed capacity from another source, no participation sweep, no score and no action class.
        expect(text(html)).not.toMatch(/participation|FPPS score|ACTION CLASS [A-E]\b/i);
      }
    }
    // The Thai card carries no English sentence of the new blocks.
    const thaiCard = text(card("th"));
    for (const english of ["If capacity counts", "Lower bound", "Upper bound", "overflow", "Robust core", "What-if levels", "capacity-aware ranking"]) {
      expect(thaiCard, english).not.toContain(english);
    }
    expect(thaiCard).toContain("เมื่อคิดความจุด้วย: รองรับได้กี่คน (สองขอบเขต)");
    expect(thaiCard).toContain("อ่านที่ k = 8: ผู้อยู่อาศัย 7,580 คนเดินไปถึง 8 แห่งของแผนด้านบนได้ และค่าประมาณความจุรองรับได้ 495 ถึง 1,057 คน จึงเหลือ 13,112 ถึง 13,674 คนจาก 14,169 คนที่ไม่มีที่รองรับ");
    expect(thaiCard).toContain("495 ไม่มีที่รองรับ 13,674");
  });

  it("flags the plan sites assigned more residents than their capacity estimate holds", () => {
    const html = card("en");
    const sites = planSites(shelters, k);
    const over = overCapacitySites(sites);
    expect(over.length).toBe(3);
    expect(html.match(/<li[^>]*data-over-capacity=""/g)?.length ?? 0).toBe(over.length);
    // The site with capacity 79 carrying about 2,430 residents: flagged on its row and named in the note.
    expect(text(html)).toContain("Capacity far below its load: ≈ 79 places for ≈ 2,430 residents assigned");
    expect(cellText(html, "over-capacity-note")).toBe(
      `3 of the first 8 sites of the plan above are assigned more residents than their capacity estimate holds. Largest gap: ${candidateTitle(over[0].candidate, "en")}, ≈ 79 places for ≈ 2,430 residents assigned (about 31 times the estimate).`,
    );
    expect(timesOver(2430, 79)).toBe("31");
    expect(timesOver(150, 100)).toBe("1.5");
    expect(cellText(card("th"), "over-capacity-note")).toContain("รองรับได้ ≈ 79 คน แต่ได้รับผู้อพยพ ≈ 2,430 คน (ประมาณ 31 เท่าของค่าประมาณ)");
    // One site: the sentence reads naturally and still names the gap.
    expect(cellText(card("en", 1), "over-capacity-note")).toMatch(/^The first site of the plan above is assigned more residents than its capacity estimate holds\. Largest gap: /);
    expect(cellText(card("en", 1), "capacity-aware-sentence")).toContain("can walk to the first site of the plan above");
    // Nobody over capacity: no note.
    const roomy = { ...shelters, candidates: shelters.candidates.map((candidate) => ({ ...candidate, capacity_est: candidate.capacity_est === null ? null : 99999 })) };
    expect(card("en", k, roomy)).not.toContain('data-testid="over-capacity-note"');
  });

  it("lists the capacity-aware ranking's sites with load against capacity and the capacity basis", () => {
    const html = card("en");
    const list = /data-testid="capacity-ranking-sites".*?<\/details>/s.exec(html)![0];
    const rows = shelters.capacitated!.plan.slice(0, k);
    expect(list.match(/<li[\s>]/g)!.length).toBe(rows.length);
    expect(text(list)).toContain("The first 8 sites of the capacity-aware ranking (candidates to verify)");
    const byId = new Map(shelters.candidates.map((candidate) => [candidate.id, candidate]));
    for (const row of rows) {
      const candidate = byId.get(row.candidate_id)!;
      expect(text(list)).toContain(candidateTitle(candidate, "en"));
      expect(text(list)).toContain(capacityBoundsText(row, candidate.kind, "en"));
      expect(text(list)).toContain(`Assigned ${people(row.lower.load)} of ${people(row.lower.capacity)} places (lower bound) · ${people(row.upper.load)} of ${people(row.upper.capacity)} (upper bound)`);
    }
    expect(list.match(/data-capacity-basis="unknown"/g)!.length).toBe(rows.filter((row) => row.capacity_est === null).length);
    const known = rows.find((row) => row.capacity_est !== null)!;
    const unknown = rows.find((row) => row.capacity_est === null)!;
    expect(capacityBoundsText(known, "school", "en")).toBe(`Capacity ≈ ${people(known.capacity_est!)} places in both bounds: OpenStreetMap footprint × 0.5 ÷ 3.5 m² per person (Sphere), unverified`);
    expect(capacityBoundsText(unknown, "school", "en")).toBe("Capacity unknown (no mapped building footprint): 0 in the lower bound, 253 in the upper bound, the median estimate of its site kind (school)");
    expect(capacityBoundsText({ ...unknown, upper_capacity_basis: "all_kinds_median" }, "community", "en")).toContain("the median of every estimate, because no site of its kind has one");
    expect(capacityBoundsText(unknown, "school", "th")).toBe("ไม่ทราบความจุ (ไม่มีขอบเขตอาคารในแผนที่): ขอบเขตล่างนับเป็น 0 ขอบเขตบนใช้ 253 คน ตามค่ามัธยฐานของค่าประมาณของสถานที่ประเภทเดียวกัน (โรงเรียน)");
    expect(capacityBoundsText(known, "school", "th")).toContain("ยังไม่ได้ตรวจสอบ");
  });

  it("shows the what-if levels, labelled as not return periods, and badges the robust core", () => {
    const html = card("en");
    const block = /data-testid="what-if-levels".*$/s.exec(html)![0];
    expect(cellText(block, "what-if-label")).toBe("T1 scenario (model) What-if levels around an illustrative peak, not return periods.");
    expect(text(block)).toContain("The 3.5 m peak of this replay is illustrative (no gauge record), so the ranking is repeated with the peak at 2.5 m and 4.0 m");
    expect([cellText(block, "what-if-demand-2.5"), cellText(block, "what-if-demand-3.5"), cellText(block, "what-if-demand-4.0")]).toEqual(["10,333", "14,169", "16,069"]);
    expect([cellText(block, "what-if-covered-2.5"), cellText(block, "what-if-covered-3.5"), cellText(block, "what-if-covered-4.0")]).toEqual(["5,480 53%", "7,580 53%", "8,148 51%"]);
    expect(text(block)).toContain("3.5 m (this replay)");
    const core = robustCore(shelters, k);
    expect(core.length).toBe(5);
    expect(cellText(block, "robust-core-sentence")).toBe(
      "5 of the first 8 sites of the plan above are among the first 8 at every level: the robust core, marked in the list above. A site in the robust core is still a candidate to verify.",
    );
    expect(html.match(/data-testid="robust-core"/g)!.length).toBe(core.length);
    expect(html.match(/<li[^>]*data-robust-core=""/g)!.length).toBe(core.length);
    expect(text(html)).toContain("Robust core: also among the first 8 sites at 2.5 m and 4.0 m");
    // One site: nothing holds at every level, and the card says so.
    const one = card("en", 1);
    expect(one).not.toContain('data-testid="robust-core"');
    expect(cellText(one, "robust-core-sentence")).toBe("The first site of the plan above is not the first site at every level, so a plan this small has no robust core.");
    const thai = card("th");
    expect(cellText(thai, "what-if-label")).toBe("สถานการณ์จำลองระดับ T1 (แบบจำลอง) ระดับน้ำสมมุติรอบ ๆ ระดับสูงสุดที่ใช้เพื่อการอธิบาย ไม่ใช่คาบการเกิดซ้ำ");
    expect(text(thai)).toContain("แกนที่คงทน: อยู่ใน 8 แห่งแรกที่ระดับ 2.5 ม. และ 4.0 ม. ด้วย");
    expect(text(thai)).toContain("3.5 ม. (การย้อนดูนี้)");
    for (const language of ["en", "th"] as const) expect(text(card(language))).not.toMatch(/\b(?:25|100)[- ]?year|รอบ ?(?:25|100) ?ปี/i);
    const provenance = /data-testid="robustness-provenance".*?<\/details>/s.exec(html)![0];
    expect(text(provenance)).toContain(shelters.robustness!.source_timestamp);
  });

  it("renders the card without the new blocks for a manifest baked before they existed", () => {
    const older = { ...shelters, capacitated: undefined, robustness: undefined };
    const html = card("en", k, older);
    expect(html).toContain('data-testid="shelter-plan-card"');
    expect(html).not.toContain('data-testid="capacity-aware"');
    expect(html).not.toContain('data-testid="what-if-levels"');
    expect(html).not.toContain('data-testid="robust-core"');
    expect(renderToStaticMarkup(<CapacityAwareBlock shelters={older} k={k} language="en" onShowCandidate={noop} />)).toBe("");
    expect(renderToStaticMarkup(<WhatIfBlock shelters={older} k={k} language="en" />)).toBe("");
  });
});
