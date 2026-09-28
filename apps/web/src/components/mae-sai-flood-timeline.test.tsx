import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ARRIVAL_RAMP,
  arrivalClasses,
  codeTimings,
  districtStats,
  hourlyStages,
  manifestRevision,
  roadCut,
  roadCutGroups,
  stageAt,
  tFromDate,
  TIMELINE_MANIFEST_URL,
  type FacilityProps,
  type GeoCollection,
  type LineGeometry,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import { facilityStatusText, Hydrograph, ImpactCard, MaeSaiFloodTimeline, RadarCheck, RouteCutsCard, TimelineLegend, WetFacilitiesCard } from "./mae-sai-flood-timeline";
import { pickVideoType, pngFileName, ReplayExportPanel, VIDEO_TYPES, videoReplayT } from "./mae-sai-replay-export";

// Fixture paths come from the page's one manifest constant and the hrefs inside that manifest.
const publicRoot = resolve(import.meta.dirname, "../../public");
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(resolve(publicRoot, href.replace(/^\//, "")), "utf8")) as T;
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const roadCollection = readJson<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href);
const roads = roadCollection.features.map((feature) => feature.properties);
const facilities = readJson<GeoCollection<unknown, FacilityProps>>(manifest.vectors.facilities.href).features.map((feature) => feature.properties);
const tambons = readJson<GeoCollection<unknown, TambonProps>>(manifest.vectors.tambons.href).features.map((feature) => feature.properties);
const peakStage = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
const derived = {
  facilityProps: facilities,
  names: Object.fromEntries(tambons.map((tambon) => [tambon.id, tambon])),
  tambonScale: Math.max(...manifest.days.flatMap((day) => Object.values(day.stats.tambon_flooded_km2)), 0.001),
};
const observations = manifest.observations.map((observation) => ({ observation, at: tFromDate(observation.local) }));
const text = (html: string) => html.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">");

describe("Mae Sai flood replay page shell", () => {
  it("labels the replay as a historical reconstruction before any data loads", () => {
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    expect(html).toContain("Mae Sai flood, September 2024 — day by day");
    expect(html).toContain("Historical reconstruction for preparedness learning — not real-time, not an official warning.");
    expect(html).toContain('href="/studio/"');
    expect(html).toContain("Loading figures");
    expect(html).not.toMatch(/real-time (flood )?detection|live warning|\blive\b/i);
  });
});

describe("Mae Sai replay panels", () => {
  it("scopes the impact figures to the modelled part of the district", () => {
    const stats = districtStats(manifest, peakStage, roads, facilities);
    const html = text(renderToStaticMarkup(<ImpactCard manifest={manifest} stats={stats} derived={derived} language="en" />));
    const modelled = Math.round(manifest.model_coverage.modelled_km2);
    const district = Math.round(manifest.model_coverage.district_km2);
    expect(html).toContain(`Modelled parts of the eight Mae Sai subdistricts — ${modelled} of ${district} km²`);
    expect(html).toContain(manifest.model_coverage.reason);
    expect(html).toContain("Computed in your browser from the terrain model at this stage.");
    expect(html).toContain(`${stats.facilities_wet} / ${manifest.facilities_count.modelled}`);
    expect(html).toContain(`${manifest.roads_not_modelled_km.toFixed(2)} km of mapped road`);
    // Subdistricts under 99% coverage carry their modelled share; fully modelled ones do not.
    const partial = Object.entries(manifest.tambon_coverage).filter(([, item]) => item.modelled_km2 / item.total_km2 < 0.99);
    expect(partial.length).toBeGreaterThan(0);
    for (const [, item] of partial) expect(html).toContain(`(${Math.round((item.modelled_km2 / item.total_km2) * 100)}% modelled)`);
    expect(html.match(/% modelled\)/g)).toHaveLength(partial.length);
    expect(html).not.toMatch(/\blive\b/i);
  });

  it("uses Thai units and keeps the candidate qualifier in Thai", () => {
    const stats = districtStats(manifest, peakStage, roads, facilities);
    const html = text(renderToStaticMarkup(<ImpactCard manifest={manifest} stats={stats} derived={derived} language="th" />));
    expect(html).toContain("สถานที่สำคัญที่เป็นไปได้ (ข้อมูล OSM)");
    expect(html).toContain("ตร.กม.");
    expect(html).toContain("กม.");
    expect(html).not.toMatch(/km²|\d km\b/);
    const legend = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads unmodelledFacilities={false} />));
    expect(legend).toContain("สถานที่สำคัญที่เป็นไปได้ (ข้อมูล OSM)");
    expect(legend).toContain("ไม่ได้จำลอง");
  });

  it("adds not-modelled legend entries only for symbols that are on the map", () => {
    const both = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities />));
    expect(both.match(/Not modelled/g)).toHaveLength(2);
    const none = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} />));
    expect(none).not.toContain("Not modelled");
    expect(none).not.toMatch(/above the (modelled )?flood range/i);
  });

  it("renders the radar check from data, with its footprint-wide scope", () => {
    const anchor = manifest.s1_anchor;
    const html = text(renderToStaticMarkup(<RadarCheck manifest={manifest} radarSpan="6 Sep → 16 Sep 06:16 ICT" language="en" />));
    expect(html).toContain(`${anchor.newly_dark_km2.toFixed(2)} km² turned newly water-like`);
    expect(html).toContain(`at a ${anchor.best_fit_stage_m.toFixed(2)} m stage`);
    expect(html).toContain(`${anchor.reconstruction_stage_at_pass_m.toFixed(3)} m`);
    expect(html).toContain(`Spatial agreement is weak (IoU ${anchor.iou_at_best_fit.toFixed(2)})`);
    expect(html).toContain(anchor.scope!);
    expect(html).toContain("including Tachileik (Myanmar)");
    const thai = text(renderToStaticMarkup(<RadarCheck manifest={manifest} radarSpan="" language="th" />));
    expect(thai).toContain("ท่าขี้เหล็ก (เมียนมา)");
    expect(thai).toContain("ขอบเขตการตรวจสอบ");
  });

  it("lists facilities in water deepest first and hides the list when none are wet", () => {
    const html = renderToStaticMarkup(<WetFacilitiesCard facilities={facilities} stage={peakStage} language="en" />);
    const peakDay = manifest.days.find((day) => day.stage_m === peakStage)!;
    expect(html.match(/<li>/g)).toHaveLength(peakDay.stats.facilities_wet);
    const depths = [...text(html).matchAll(/depth ≈ (<?\s?[\d.]+) m/g)].map((match) => Number(match[1].replace("<", "").trim()));
    depths.slice(1).forEach((depth, index) => expect(depth).toBeLessThanOrEqual(depths[index]));
    expect(renderToStaticMarkup(<WetFacilitiesCard facilities={facilities} stage={0} language="en" />)).toBe("");
  });

  it("gives a dry facility's terrain height above drainage (h × k), not its effective HAND", () => {
    // e.g. OSM-6388482785: effective HAND 4.8 m with k = 0.391 is about 1.9 m of terrain above drainage.
    const site = facilities.find((facility) => facility.m && facility.h !== null && (facility.k ?? 1) < 0.5)!;
    expect(site).toBeDefined();
    const dry = facilityStatusText(site, 0, "en");
    expect(dry).toContain(`about ${(site.h! * site.k!).toFixed(1)} m above drainage`);
    expect(dry).toContain(`floods once the assumed stage exceeds ${site.h!.toFixed(2)} m`);
    expect(dry).not.toContain(`(${site.h!.toFixed(1)} m above drainage`);
    expect(facilityStatusText(site, site.h! + 1, "en")).toBe(`Reconstructed depth ≈ ${site.k!.toFixed(1)} m`);
    expect(facilityStatusText(site, 0, "th")).toContain(`สูงจากร่องน้ำ ≈ ${(site.h! * site.k!).toFixed(1)} ม.`);
    expect(facilityStatusText({ h: null, m: true }, 3, "en")).toBe("Above the modelled flood range");
  });

  it("plots the stage anchor polyline and labels acquisitions outside the SVG", () => {
    const html = renderToStaticMarkup(<Hydrograph manifest={manifest} time={0.5} stage={0} observations={observations} language="en" />);
    const path = /<path d="(M[^"]+)" class="[^"]*hydroLine/.exec(html)?.[1];
    expect(path).toBeDefined();
    const inside = manifest.stage_anchors.filter((anchor) => anchor.t > 0 && anchor.t < 11);
    expect(path!.split(/[ML]/).filter(Boolean)).toHaveLength(inside.length + 2);
    // The whole of 9 Sep sits on the zero line: the first three vertices share the baseline y.
    const ys = path!.split(/[ML]/).filter(Boolean).map((point) => Number(point.trim().split(" ")[1]));
    expect(ys[1]).toBe(ys[0]);
    expect(ys[2]).toBe(ys[0]);
    expect(stageAt(0.99, manifest.stage_anchors)).toBe(0);
    expect(html).not.toMatch(/<text[^>]*>S[12] /);
    expect(text(html)).toContain("Sentinel-2 · 15 Sep 10:58 ICT");
    expect(text(html)).toContain("Sentinel-1 · 16 Sep 06:16 ICT");
    // r2 scales each cell's rise by k, so the curve is the Sai main-stem reference stage, not every channel's.
    expect(text(html)).toContain("Assumed Sai main-stem stage at the Mae Sai bridges (m) — illustrative; tributaries rise k × stage");
  });
});

describe("Mae Sai replay water modes, route cuts and exports", () => {
  const stages = hourlyStages(manifest.stage_anchors);
  const timings = codeTimings(stages, manifest.hand.step_m, manifest.hand.never_code);
  const arrival = arrivalClasses(timings.arrivalHour, ARRIVAL_RAMP, manifest.hand.channel_code);
  const cuts = roadCollection.features.map((feature) => roadCut(feature.properties.m ? feature.properties.h : null, stages, manifest.impassable_depth_m, feature.properties.k ?? 1));
  const groups = roadCutGroups(roadCollection.features, cuts, 10);
  const names = Object.fromEntries(tambons.map((tambon) => [tambon.id, tambon]));

  it("labels each water mode's legend as a model in local time or hours", () => {
    const arrivalLegend = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities waterMode="arrival" arrival={arrival} />));
    expect(arrivalLegend).toContain("First flooded (model, local time)");
    expect(arrivalLegend).toContain("Not yet flooded at this moment (faded)");
    expect(arrivalLegend).toMatch(/\d{1,2} Sep \d{2}:00/);
    const durationLegend = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads={false} unmodelledFacilities={false} waterMode="duration" roadMode="hours" />));
    expect(durationLegend).toContain("จำนวนชั่วโมงที่จมน้ำ 9–19 ก.ย. (แบบจำลอง)");
    expect(durationLegend).toContain("ถนน — ชั่วโมงที่สัญจรไม่ได้ ≥ 0.3 ม. (แบบจำลอง)");
    expect(durationLegend).toContain("≥ 48 ชม.");
    const hoursLegend = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities={false} roadMode="hours" />));
    expect(hoursLegend).toContain("Roads — hours impassable ≥ 0.3 m (model)");
    for (const label of ["Not cut", "< 6 h", "6–24 h", "24–48 h", "≥ 48 h"]) expect(hoursLegend).toContain(label);
  });

  it("lists the longest-cut routes as modelled closures with local first-cut and reopen times", () => {
    const html = renderToStaticMarkup(<RouteCutsCard groups={groups} names={names} language="en" focused={null} onFocus={() => undefined} onReset={() => undefined} />);
    const plain = text(html);
    expect(plain).toContain("Longest-cut routes (Keep Routes Open)");
    expect(plain).toContain("Modelled, not observed closures");
    expect(html.match(/<li>/g)).toHaveLength(groups.length);
    expect(plain).toContain(`Up to ${groups[0].maxHours} h cut`);
    expect(plain).toMatch(/First cut \d{1,2} Sep \d{2}:00 → reopened/);
    expect(plain).not.toContain("Show the whole area");
    expect(plain.replaceAll("not observed", "")).not.toMatch(/observed|real-time|\blive\b/i);
    expect(plain).toContain("THEME: KEEP ROUTES OPEN · NO ACTION CLASS ASSIGNED");
    expect(plain).not.toMatch(/ACTION CLASS [A-E]\b/);
    const thai = text(renderToStaticMarkup(<RouteCutsCard groups={groups} names={names} language="th" focused={groups[0].key} onFocus={() => undefined} onReset={() => undefined} />));
    expect(thai).toContain("เส้นทางที่ถูกตัดขาดนานที่สุด");
    expect(thai).toContain("แสดงทั้งพื้นที่");
    const none = text(renderToStaticMarkup(<RouteCutsCard groups={[]} names={names} language="en" focused={null} onFocus={() => undefined} onReset={() => undefined} />));
    expect(none).toContain("No modelled road piece reaches 0.3 m");
  });

  it("prefers MP4, then VP9 WebM, then WebM, and times the video at two seconds per day", () => {
    expect(VIDEO_TYPES.map((type) => type.mime)).toEqual(["video/mp4;codecs=avc1.42E01E", "video/webm;codecs=vp9", "video/webm"]);
    expect(pickVideoType(() => true)?.ext).toBe("mp4");
    expect(pickVideoType((mime) => mime.startsWith("video/webm"))?.mime).toBe("video/webm;codecs=vp9");
    expect(pickVideoType((mime) => mime === "video/webm")?.mime).toBe("video/webm");
    expect(pickVideoType(() => false)).toBeNull();
    expect(pickVideoType(() => { throw new Error("unsupported"); })).toBeNull();
    expect(videoReplayT(0)).toBe(0);
    expect(videoReplayT(-1)).toBe(0);
    expect(videoReplayT(7)).toBe(3.5);
    expect(videoReplayT(60)).toBeLessThan(11);
    expect(videoReplayT(60)).toBeGreaterThan(10.99);
    expect(pngFileName(3.5)).toBe("mae-sai-flood-2024-09-12-1200-ict.png");
    expect(pngFileName(0)).toBe("mae-sai-flood-2024-09-09-0000-ict.png");
  });

  it("names the served data revision, which is also the manifest's own revision field", () => {
    expect(manifestRevision()).toBe("r2");
    expect(manifest.revision).toBe(manifestRevision());
    expect(manifestRevision("/studies/x/r9/timeline.json")).toBe("r9");
  });

  it("keeps exports disabled until the water model is ready and never offers video without a recorder", () => {
    const html = renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="en" waterOpacity={0.85} />);
    expect(text(html)).toContain("Save PNG of this moment");
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Save PNG of this moment/);
    expect(text(html)).not.toContain("Record video");
    expect(text(html)).toContain("Exports become available once the water model has loaded.");
    const thai = text(renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="th" waterOpacity={0.85} />));
    expect(thai).toContain("บันทึกภาพ PNG ของช่วงเวลานี้");
  });
});
