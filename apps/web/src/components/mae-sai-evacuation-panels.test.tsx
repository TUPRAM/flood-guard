import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  districtStats,
  hourlyStages,
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
  parseAccessNodes,
  planSetId,
  REPORTED_SET_ID,
  reportedSetExclusions,
  reportedShelterCheck,
  reportedSiteCounts,
  summarizeAccessSets,
  tambonResidents,
} from "@/lib/flood-timeline-evacuation";
import {
  AccessCard,
  AccessChart,
  candidateTitle,
  capacityText,
  CoverageCurve,
  ExternalChecks,
  freeboardText,
  ineligibleReasonText,
  OtherCandidatesCard,
  OtherCandidatesList,
  PeopleInWaterCard,
  reportedCheckText,
  ReportedSheltersCard,
  ShelterPlanCard,
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
const peak = Math.max(...manifest.days.map((day) => day.stage_m));
const peakDay = manifest.days.find((day) => day.stage_m === peak)!;
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ");
const noop = () => undefined;
// Model outputs may say "not observed"; they must never present themselves as observed or live.
const unsafeClaim = (value: string) => /\b(observed|real-time|live)\b/i.test(value.replaceAll(/not observed|not an? (official )?warning/gi, ""));

function accessCard(language: "en" | "th", set: "reported" | "plan", k = shelters.knee_k, stage = peak) {
  const index = access.sets.indexOf(set === "reported" ? REPORTED_SET_ID : planSetId(k));
  const summary = summaries[index];
  return renderToStaticMarkup(
    <AccessCard access={access} shelters={shelters} snapshot={accessSnapshot(summary, stage, access.levels)}
      series={accessLostSeries(summary, hourlyStages(manifest.stage_anchors), access.levels)} time={3.5} names={names}
      tambonTotals={tambonTotals} shelterSet={set} planK={k} onShelterSet={noop} onPlanK={noop} showCutoff={false}
      onShowCutoff={noop} language={language} status="ready" />,
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
    const thai = text(renderToStaticMarkup(<PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language="th" />));
    expect(thai).toContain("ประชากรในพื้นที่น้ำท่วม (แบบจำลอง)");
    expect(thai).toContain("ไม่ใช่ประชากรปี 2024");
    expect(unsafeClaim(plain)).toBe(false);
  });
});

describe("Evacuation access card (scenario)", () => {
  it("splits people without a dry shelter into lost during the flood and never within reach, and labels it a scenario", () => {
    const summary = summaries[access.sets.indexOf(REPORTED_SET_ID)];
    const snapshot = accessSnapshot(summary, peak, access.levels);
    const plain = text(accessCard("en", "reported"));
    expect(plain).toContain("Walking access to a dry shelter (scenario)");
    expect(plain).toContain("not observed evacuation outcomes");
    expect(plain).toContain(`${Math.round(snapshot.lost.population + snapshot.never.population).toLocaleString("en-US")} / ${access.totals.population.toLocaleString("en-US")}`);
    expect(plain).toContain(Math.round(snapshot.lost.population).toLocaleString("en-US"));
    expect(plain).toContain("Never had one within reach, even before the flood");
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
    expect(plain).toContain(shelters.reported_access_set_rule);
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

  it("shows the k slider for the ranked plan and matches the baked figures at the knee", () => {
    const html = accessCard("en", "plan");
    expect(html).toMatch(/type="range"[^>]*min="1"[^>]*max="12"/);
    expect(text(html)).toContain(`Plan size k = ${shelters.knee_k} (default: the knee)`);
    const baked = peakDay.stats.access![planSetId(shelters.knee_k)];
    expect(text(html)).toContain(baked.people_lost_access.toLocaleString("en-US"));
    const thai = text(accessCard("th", "plan", 3));
    expect(thai).toContain("การเดินถึงที่พักพิงที่แห้ง (สถานการณ์จำลอง)");
    expect(thai).toContain("จำนวนที่พักพิงในแผน k = 3");
    expect(thai).toContain("ช่องว่างความเท่าเทียมในการอพยพ");
  });

  it("reports loading and failure honestly instead of showing zeros", () => {
    const loading = text(renderToStaticMarkup(
      <AccessCard access={access} shelters={shelters} snapshot={null} series={null} time={0} names={names} tambonTotals={null}
        shelterSet="reported" planK={8} onShelterSet={noop} onPlanK={noop} showCutoff={false} onShowCutoff={noop} language="en" status="loading" />,
    ));
    expect(loading).toContain("Preparing the access scenario");
    const failed = text(renderToStaticMarkup(
      <AccessCard access={access} shelters={shelters} snapshot={null} series={null} time={0} names={names} tambonTotals={null}
        shelterSet="reported" planK={8} onShelterSet={noop} onPlanK={noop} showCutoff={false} onShowCutoff={noop} language="en" status="error" />,
    ));
    expect(failed).toContain("could not be loaded");
    expect(failed).not.toMatch(/Evacuation Equity Gap/);
  });

  it("draws the replay curve of people who lost access with the playhead", () => {
    const summary = summaries[access.sets.indexOf(REPORTED_SET_ID)];
    const series = accessLostSeries(summary, hourlyStages(manifest.stage_anchors), access.levels);
    const html = renderToStaticMarkup(<AccessChart series={series} time={3.5} language="en" label="Reported" />);
    expect(html).toContain('role="img"');
    expect(html).toMatch(/aria-label="Reported: people who lost walking access to a dry shelter, 9–19 Sep\. Peak [\d,]+ at \d+ Sep \d{2}:00; now [\d,]+\."/);
    expect(html.match(/<text/g)!.length).toBeGreaterThanOrEqual(11 + 3);
  });
});

describe("Shelter plan and reported shelters", () => {
  it("draws the coverage curve with the knee and the selected k, and states the gap", () => {
    const curve = renderToStaticMarkup(<CoverageCurve shelters={shelters} k={3} language="en" />);
    expect(curve).toContain(`knee k = ${shelters.knee_k}`);
    expect(curve).toMatch(/Selected k = 3: \d+% pre-emptive, \d+% late/);
    const html = renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={shelters.knee_k} onPlanK={noop} language="en" onShowCandidate={noop} />);
    const plain = text(html);
    expect(plain).toContain("Ranked range, not a fixed number: the first k entries are the plan for k shelters");
    expect(plain).toContain(`the default k = ${shelters.knee_k} is the smallest plan that reaches 90% of the achievable coverage`);
    expect(plain).toContain("Shelter gap");
    expect(plain).toContain(`${shelters.uncoverable_people.toLocaleString("en-US")} residents in the modelled peak flood zone have no eligible dry site`);
    expect(plain).toContain("planning scenario");
    expect(html.match(/<li>/g)!.length).toBeGreaterThanOrEqual(shelters.knee_k);
    expect(unsafeClaim(plain)).toBe(false);
    const thai = text(renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={2} onPlanK={noop} language="th" onShowCandidate={noop} />));
    expect(thai).toContain("ช่องว่างของที่พักพิง");
    expect(thai).toContain("2 แห่งแรกของแผน");
    expect(plain).toContain("CONFIDENCE: LOW");
    expect(plain).toContain(shelters.source_timestamp);
  });

  it("keeps the coverage curve's axis title clear of its tick labels", () => {
    const curve = renderToStaticMarkup(<CoverageCurve shelters={shelters} k={3} language="en" />);
    const ys = (pattern: RegExp) => [...curve.matchAll(pattern)].map((match) => Number(match[1]));
    const ticks = ys(/<text[^>]*y="([\d.]+)"[^>]*>\d+<\/text>/g).filter((y) => y > 150);
    const [title] = ys(/<text[^>]*y="([\d.]+)"[^>]*>k \(sites in the plan\)<\/text>/g);
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
    expect(unmodelled).toHaveLength(12);
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
    expect(plain).toContain("The model says this site floods at the modelled peak");
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
    for (const shelter of shelters.reported) expect(plain).toContain(shelter.access_set_note);
    expect(plain).toContain("not an official register");
    expect(plain).toContain(`reported list compiled ${shelters.reported_compiled}`);
    expect(plain).toContain("CONFIDENCE: LOW");
    const thai = text(renderToStaticMarkup(<ReportedSheltersCard shelters={shelters} language="th" onShowReported={noop} />));
    expect(thai).toContain(`สถานที่ที่มีรายงานว่าใช้จริง (${total}): ที่พักพิง ${total - 1} แห่ง ศูนย์บัญชาการและจุดช่วยเหลือ 1 แห่ง`);
    expect(thai).toContain("ศูนย์บัญชาการและจุดช่วยเหลือ (ไม่ใช่ที่พักพิง)");
  });

  it("renders the independent size checks with their sources", () => {
    const html = renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" />);
    for (const check of manifest.external_checks!) {
      expect(text(html)).toContain(`reported ${check.reported_km2} km²`);
      expect(text(html)).toContain(`${Number(check.model_km2.toFixed(1))} km²`);
      for (const url of check.urls) expect(html).toContain(`href="${url.replaceAll("&", "&amp;")}"`);
    }
    expect(text(html)).toContain("Magnitude check over the same window only");
    expect(renderToStaticMarkup(<ExternalChecks manifest={{ ...manifest, external_checks: [] }} language="en" />)).toBe("");
  });

  it("files the GISTDA onset figure as a calibration anchor and compares UNOSAT over its own window", () => {
    const plain = text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" />));
    const calibration = plain.indexOf("Calibration anchor (not an independent check)");
    const independent = plain.indexOf("Independent size checks");
    expect(calibration).toBeGreaterThanOrEqual(0);
    expect(independent).toBeGreaterThan(calibration);
    const gistda = plain.indexOf("GISTDA RADARSAT-2");
    const unosat = plain.indexOf("UNOSAT product 3991");
    expect(gistda).toBeGreaterThan(calibration);
    expect(gistda).toBeLessThan(independent);
    expect(unosat).toBeGreaterThan(independent);
    expect(plain).toContain("agreement holds by construction and does not test the model");
    expect(plain).toContain("time zone not stated; assumed ICT");
    expect(plain).toContain("The model gives 59.5 km² and ≈ 11,517 modelled residents in water at a 2.65 m stage");
    expect(plain).toContain("Largest modelled extent within 13-19 Sep ICT");
    expect(plain).toContain("For reference, the modelled peak gives 75.5 km² and ≈ 14,816 residents in water.");
    expect(plain).toContain("Model figures cover the modelled part of Mae Sai district (294 of 306 km²)");
    const thai = text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="th" />));
    expect(thai).toContain("จุดอ้างอิงที่ใช้ปรับแบบจำลอง (ไม่ใช่การตรวจสอบอิสระ)");
    expect(thai).toContain("แบบจำลองให้ค่า 59.5 ตร.กม.");
    expect(thai).toContain("ใช้ตรวจขนาดเท่านั้น ไม่ใช่การยืนยันตำแหน่ง");
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
