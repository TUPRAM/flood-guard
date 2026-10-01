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
  summarizeAccessSets,
  tambonResidents,
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
  ExternalChecks,
  freeboardText,
  indefiniteArticle,
  ineligibleReasonText,
  OtherCandidatesCard,
  OtherCandidatesList,
  PeopleInWaterCard,
  reportedCheckText,
  ReportedSheltersCard,
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

function accessCard(language: "en" | "th", set: "reported" | "plan", k = shelters.knee_k, stage = peak, scope: "flooded" | "all" = "all") {
  const index = access.sets.indexOf(set === "reported" ? REPORTED_SET_ID : planSetId(k));
  const model = scoped[scope];
  const summary = model.summaries[index];
  return renderToStaticMarkup(
    <AccessCard access={access} shelters={shelters} snapshot={accessSnapshot(summary, stage, access.levels)}
      series={accessLostSeries(summary, hourlyStages(manifest.stage_anchors), access.levels)} time={3.5} names={names}
      tambonTotals={model.tambonTotals} shelterSet={set} planK={k} onShelterSet={noop} onPlanK={noop} showCutoff={false}
      onShowCutoff={noop} scope={scope} onScope={noop} scopeTotals={model.totals} allResidents={scoped.all.totals.population}
      floodedResidents={scoped.flooded.totals.population} language={language} status="ready" />,
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
  it("splits people without a dry shelter into lost during the flood and never within reach, and labels it a scenario", () => {
    const summary = summaries[access.sets.indexOf(REPORTED_SET_ID)];
    const snapshot = accessSnapshot(summary, peak, access.levels);
    const html = accessCard("en", "reported");
    const plain = text(html);
    expect(plain).toContain("Walking access to a dry shelter (scenario)");
    expect(plain).toContain("not observed evacuation outcomes");
    expect(plain).toContain(`${Math.round(snapshot.lost.population + snapshot.never.population).toLocaleString("en-US")} / ${access.totals.population.toLocaleString("en-US")}`);
    // The flood's own effect is the hero figure; residents already out of reach are grey context after it.
    const hero = html.indexOf('data-testid="access-lost"');
    const context = html.indexOf('data-testid="access-never"');
    expect(hero).toBeGreaterThan(0);
    expect(context).toBeGreaterThan(hero);
    expect(plain).toContain(`Lost walking access because of the flood, at this replay hour ${Math.round(snapshot.lost.population).toLocaleString("en-US")} of ${access.totals.population.toLocaleString("en-US")}`);
    expect(plain).toContain(`Already more than 2 km from a shelter of this set before the flood ${Math.round(snapshot.never.population).toLocaleString("en-US")}`);
    expect(html).toMatch(/data-tone="alert" data-testid="access-lost"/);
    expect(html).not.toMatch(/data-tone="[a-z]+" data-testid="access-never"/);
    expect(plain).not.toMatch(/\bnow\b/);
    expect(plain).toContain("Evacuation Equity Gap");
    expect(plain).toContain("terrain/remoteness proxy");
    expect(plain).toContain("not demographic vulnerability");
    expect(plain).toContain("Shelters reported used in Sep 2024");
    expect(plain).not.toContain("Plan size k");
    expect(unsafeClaim(plain)).toBe(false);
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

  it("counts the residents whose homes flood at the peak by default, so the reported set and the plan compare like with like", () => {
    const flooded = scoped.flooded.totals.population;
    expect(Math.abs(flooded - shelters.demand_people)).toBeLessThan(1);
    const people = (value: number) => Math.round(value).toLocaleString("en-US");
    for (const set of ["reported", "plan"] as const) {
      const html = accessCard("en", set, shelters.knee_k, peak, "flooded");
      const plain = text(html);
      expect(radioChecked(html, "mae-sai-access-scope", "flooded")).toBe(true);
      expect(radioChecked(html, "mae-sai-access-scope", "all")).toBe(false);
      expect(plain).toContain(`Residents whose homes flood at the peak (${people(flooded)})`);
      expect(plain).toContain(`All residents at road nodes (${people(access.totals.population)})`);
      expect(plain).toContain(`What the ranked plan optimises: sites that as many as possible of the ${people(shelters.demand_people)} residents whose homes flood at the modelled peak can walk to before the water rises`);
      const summary = scoped.flooded.summaries[access.sets.indexOf(set === "reported" ? REPORTED_SET_ID : planSetId(shelters.knee_k))];
      const snapshot = accessSnapshot(summary, peak, access.levels);
      expect(plain).toContain(`${people(snapshot.lost.population)} of ${people(flooded)}`);
      expect(plain).toContain("residents at road nodes whose homes flood at the modelled peak");
      expect(plain).not.toContain(`/ ${people(access.totals.population)}`);
    }
    // Before the flood, the plan's scoped "already out of reach" is the demand minus the plan's own coverage.
    const dry = text(accessCard("en", "plan", shelters.knee_k, 0, "flooded"));
    const coverage = shelters.plan[shelters.knee_k - 1].cumulative_demand;
    expect(dry).toContain(`Already more than 2 km from a shelter of this set before the flood ${people(shelters.demand_people - coverage)}`);
    // The other scope counts everyone at a road node.
    const all = accessCard("en", "reported", shelters.knee_k, peak, "all");
    expect(radioChecked(all, "mae-sai-access-scope", "all")).toBe(true);
    expect(text(all)).toContain(`of ${people(access.totals.population)}`);
  });

  it("words the Equity Gap plainly, says why the proxy points this way, and shows a dash before anyone loses access", () => {
    // With the ranked plan both groups lose access at the peak: a ratio, a plain comparison and why it points this way.
    const peakText = text(withoutTips(accessCard("en", "plan", shelters.knee_k, peak, "all")));
    expect(peakText).toMatch(/Evacuation Equity Gap: \d+\.\d{2} · Proxy-vulnerable residents are about [\d.]+× less likely to lose access \(\d+\.\d{2}% vs \d+\.\d{2}%\)\./);
    expect(peakText).toContain("How to read this: the proxy marks homes on slopes or far from a drivable road");
    expect(peakText).not.toMatch(/times as likely/);
    // With the reported set no proxy-vulnerable resident loses access at the peak: said in words, not as "0.00 times".
    const reported = text(withoutTips(accessCard("en", "reported", shelters.knee_k, peak, "all")));
    expect(reported).toMatch(/Evacuation Equity Gap: 0\.00 · No proxy-vulnerable resident has lost access, against \d+\.\d{2}% of everyone else\./);
    const dry = text(accessCard("en", "reported", shelters.knee_k, 0, "all"));
    expect(dry).toContain("Evacuation Equity Gap: — (no one has lost access at this replay hour)");
    expect(dry).not.toContain("How to read this: the proxy");
    const thai = text(accessCard("th", "reported", shelters.knee_k, 0, "all"));
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ: — (ไม่มีผู้สูญเสียการเข้าถึง ณ ชั่วโมงนี้)");
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
        scope="flooded" onScope={noop} scopeTotals={null} allResidents={access.totals.population} floodedResidents={shelters.demand_people} language="en" status="loading" />,
    ));
    expect(loading).toContain("Preparing the access scenario");
    const failed = text(renderToStaticMarkup(
      <AccessCard access={access} shelters={shelters} snapshot={null} series={null} time={0} names={names} tambonTotals={null}
        shelterSet="reported" planK={8} onShelterSet={noop} onPlanK={noop} showCutoff={false} onShowCutoff={noop}
        scope="flooded" onScope={noop} scopeTotals={null} allResidents={access.totals.population} floodedResidents={shelters.demand_people} language="en" status="error" />,
    ));
    expect(failed).toContain("could not be loaded");
    expect(failed).not.toMatch(/Evacuation Equity Gap/);
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
