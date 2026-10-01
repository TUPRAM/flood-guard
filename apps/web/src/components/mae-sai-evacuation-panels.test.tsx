import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  coverageComplete,
  districtStats,
  hourlyStages,
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
  capacityFlag,
  floodedHomeMask,
  parseAccessNodes,
  planCoverageSentence,
  planSites,
  planSetId,
  REPORTED_SET_ID,
  reportedSetExclusions,
  reportedShelterCheck,
  reportedSiteCounts,
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

  it("words the Equity Gap plainly, never as 0.00, and says why the proxy points this way", () => {
    // With the ranked plan both groups lose access at the peak: a ratio, a plain comparison and why it points this way.
    const peakText = text(withoutTips(accessCard("en", "plan", shelters.knee_k, peak, "all")));
    expect(peakText).toMatch(/Evacuation Equity Gap: \d+\.\d{2} · Proxy-vulnerable residents are about [\d.]+× less likely to lose access \(\d+\.\d{2}% vs \d+\.\d{2}%\)\./);
    expect(peakText).toContain("How to read this: the proxy marks homes on slopes or far from a drivable road");
    expect(peakText).not.toMatch(/times as likely/);
    // Both denominators of each group: all residents counted, and those within reach before the flood.
    expect(peakText).toContain("Proxy-vulnerable residents who lost access: 320 of 7,152 counted (373 had a shelter of this set within reach before the flood); everyone else: 13,109 of 74,647 (24,537 within reach before the flood).");
    expect(peakText).toContain("T1 scenario (model). Vulnerable = terrain/remoteness proxy. Hours from illustrative stage keyframes, not observed.");
    // With the reported set no proxy-vulnerable resident loses access at the peak: said in words, never "0.00".
    const reportedHtml = accessCard("en", "reported", shelters.knee_k, peak, "all");
    const reported = text(withoutTips(reportedHtml));
    expect(reported).toMatch(/Evacuation Equity Gap: no proxy-vulnerable resident has lost access · At this replay hour, \d+\.\d{2}% of everyone else have\./);
    expect(reported).not.toContain("Evacuation Equity Gap: 0.00");
    expect(reported).toContain("Proxy-vulnerable residents who lost access: 0 of 7,152 counted (2,440 had a shelter of this set within reach before the flood); everyone else: 7,086 of 74,647 (32,085 within reach before the flood).");
    expect(reportedHtml).not.toContain("data-reason=");
    expect(reportedHtml).not.toContain("equity-no-baseline");
    const thaiPeak = text(accessCard("th", "reported", shelters.knee_k, peak, "all"));
    expect(thaiPeak).toContain("ช่องว่างความเท่าเทียมในการอพยพ: ไม่มีผู้ใดในกลุ่มเปราะบางตามตัวแทนสูญเสียการเข้าถึง · ณ ชั่วโมงนี้ของการย้อนดู กลุ่มอื่นสูญเสียการเข้าถึง");
    // "ยังไม่มี" ("not yet") would imply the loss is about to happen.
    expect(thaiPeak).not.toContain("ยังไม่มีผู้อยู่อาศัยกลุ่มเปราะบาง");
    expect(thaiPeak).toContain("สถานการณ์จำลองระดับ T1 (แบบจำลอง) กลุ่มเปราะบาง = ตัวแทนจากภูมิประเทศและความห่างไกล");
  });

  it("shows no ratio and says why when no one has lost access (reason no_loss)", () => {
    const html = accessCard("en", "reported", shelters.knee_k, 0, "all");
    const dry = text(html);
    expect(html).toContain('data-testid="equity-gap" data-reason="no_loss"');
    expect(dry).toContain("Evacuation Equity Gap: no ratio shown · No one in either group has lost access at this replay hour, so there are no loss rates to compare.");
    expect(dry).not.toMatch(/Evacuation Equity Gap: (—|1\.00|0\.00)/);
    expect(dry).not.toContain("How to read this: the proxy");
    const thai = text(accessCard("th", "reported", shelters.knee_k, 0, "all"));
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ: ไม่แสดงอัตราส่วน · ไม่มีผู้ใดในทั้งสองกลุ่มสูญเสียการเข้าถึง ณ ชั่วโมงนี้ของการย้อนดู จึงไม่มีอัตราการสูญเสียให้เปรียบเทียบ");
  });

  it("shows no ratio and says why when a group has fewer than 50 residents (reason insufficient_group_denominator)", () => {
    const small: AccessGroupSums = { population: 14_169, vulnerable: 26.5, nonVulnerable: 14_142.5 };
    const html = accessCard("en", "plan", shelters.knee_k, peak, "flooded", small);
    const plain = text(html);
    expect(html).toContain('data-testid="equity-gap" data-reason="insufficient_group_denominator"');
    expect(plain).toContain("Evacuation Equity Gap: no ratio shown · The proxy-vulnerable group has 26 residents in this count, fewer than the 50 a ratio needs in each group.");
    expect(plain).not.toContain("How to read this: the proxy");
    expect(plain).toContain("No ratio is shown when a group has fewer than 50 residents, when no one has lost access, or when only proxy-vulnerable residents have");
    const thai = text(accessCard("th", "plan", shelters.knee_k, peak, "flooded", small));
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ: ไม่แสดงอัตราส่วน · กลุ่มเปราะบางตามตัวแทนมีผู้อยู่อาศัยในการนับนี้ 26 คน น้อยกว่า 50 คนที่ต้องมีในแต่ละกลุ่มจึงจะแสดงอัตราส่วนได้");
    // On the served data both scopes have at least 50 residents in each group, so the rule does not hide a ratio today.
    for (const scope of ["all", "flooded"] as const) {
      expect(scoped[scope].totals.vulnerable).toBeGreaterThanOrEqual(50);
      expect(scoped[scope].totals.nonVulnerable).toBeGreaterThanOrEqual(50);
    }
  });

  it("says so when no proxy-vulnerable resident could lose access because none was within reach before the flood", () => {
    // Reported set, residents whose homes flood: the proxy-vulnerable group is counted but none had a reported shelter in reach.
    const html = accessCard("en", "reported", shelters.knee_k, peak, "flooded");
    const plain = text(html);
    expect(cellText(html, "equity-no-baseline")).toBe("No proxy-vulnerable resident counted here had a shelter of this set within reach before the flood, so none could lose it.");
    expect(plain).toMatch(/Proxy-vulnerable residents who lost access: 0 of 103 counted \(0 had a shelter of this set within reach before the flood\)/);
    expect(text(accessCard("th", "reported", shelters.knee_k, peak, "flooded"))).toContain("จึงไม่มีผู้ใดสูญเสียการเข้าถึงได้");
  });

  it("explains terms on hover or focus with the glossary definition as the accessible description", () => {
    const html = renderToStaticMarkup(<Term id="road_nodes" language="en">road nodes</Term>);
    const id = /aria-describedby="([^"]+)"/.exec(html)![1];
    expect(html).toContain(`tabindex="0"`);
    expect(html).toContain(`role="tooltip" id="${id}"`);
    expect(text(html)).toContain("Points on the OpenStreetMap road network");
    expect(text(accessCard("en", "reported"))).toContain("Points on the OpenStreetMap road network");
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
    const items = html.split("<li").slice(1);
    const unmodelled = shelters.candidates.filter((candidate) => !candidate.m).map((candidate) => candidate.id);
    expect(unmodelled.length).toBeGreaterThan(0);
    expect(unmodelled.every((id) => shelters.candidates.find((item) => item.id === id)!.ineligible_reasons.includes("outside_model"))).toBe(true);
    for (const id of unmodelled) {
      const candidate = shelters.candidates.find((item) => item.id === id)!;
      const title = candidateTitle(candidate, "en").replaceAll("&", "&amp;");
      const item = text(items.find((entry) => entry.includes(title))!);
      expect(item).toContain("Outside the terrain model (no flood result)");
      expect(item).toContain("Not modelled: the site lies outside the terrain model");
      expect(item).not.toContain("High ground");
      expect(item).not.toContain("keeps less than");
    }
    const thai = text(renderToStaticMarkup(<OtherCandidatesList shelters={shelters} k={3} language="th" onShowCandidate={noop} />));
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
    for (const check of manifest.external_checks!) {
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
    const anchor = manifest.external_checks!.find((check) => check.role === "calibration_anchor")!;
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
    const unosatCheck = manifest.external_checks!.find((check) => check.role === "calibration_informed_magnitude_check")!;
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
