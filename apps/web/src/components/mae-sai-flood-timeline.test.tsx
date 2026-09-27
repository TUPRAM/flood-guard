import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  districtStats,
  stageAt,
  tFromDate,
  type FacilityProps,
  type GeoCollection,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import { Hydrograph, ImpactCard, MaeSaiFloodTimeline, RadarCheck, TimelineLegend, WetFacilitiesCard } from "./mae-sai-flood-timeline";

const dir = resolve(import.meta.dirname, "../../public/studies/mae-sai-2024-timeline/r1");
const readJson = <T,>(name: string): T => JSON.parse(readFileSync(resolve(dir, name), "utf8")) as T;
const manifest = readJson<TimelineManifest>("timeline.json");
const roads = readJson<GeoCollection<unknown, RoadProps>>("roads.geojson").features.map((feature) => feature.properties);
const facilities = readJson<GeoCollection<unknown, FacilityProps>>("facilities.geojson").features.map((feature) => feature.properties);
const tambons = readJson<GeoCollection<unknown, TambonProps>>("tambons.geojson").features.map((feature) => feature.properties);
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
  });
});
