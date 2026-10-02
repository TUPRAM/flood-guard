import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ARRIVAL_RAMP,
  arrivalClasses,
  codeTimings,
  coverageComplete,
  districtStats,
  hourlyStages,
  manifestRevision,
  parseTimelineManifest,
  rainAt,
  referencesNotIngested,
  rgbaCss,
  roadCut,
  roadCutGroups,
  s2CrosscheckAt,
  s2CrosscheckDate,
  s2CrosscheckScenes,
  stageAt,
  viirsReading,
  tFromDate,
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type LineGeometry,
  type RoadProps,
  type S2Crosscheck,
  type TambonProps,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import { localizedText, plainManifestText, STANDALONE_K } from "@/lib/flood-timeline-copy";
import type { WaterMode } from "@/lib/flood-timeline-link";
import { lowConfidenceKey, residentsPendingText } from "@/lib/flood-timeline-water";
import { findWordingViolations, visibleText } from "@/lib/replay-wording-lint";
import {
  facilityStatusText,
  GeneratedAt,
  HowToRead,
  Hydrograph,
  ImpactCard,
  LicencesByInput,
  LowConfidenceEvidence,
  MaeSaiFloodTimeline,
  playLabel,
  playLabels,
  postEventOptical,
  RadarCheck,
  RouteCutsCard,
  SourcesPanel,
  TimelineLegend,
  TuningDisclosure,
  WetFacilitiesCard,
} from "./mae-sai-flood-timeline";
import {
  bothObservationsText,
  followingDayText,
  followingViirsDay,
  formatDateSet,
  observedLargerThanModel,
  RainChart,
  s2ModelText,
  s2ObservedText,
  s2SensitivityText,
  Sentinel2Evidence,
  ViirsComparisonCard,
  viirsMomentText,
} from "./mae-sai-observed-panels";
import {
  exportPlaceLabels,
  exportScaleBar,
  exportViewText,
  pickVideoType,
  pngFileName,
  ReplayExportPanel,
  VIDEO_END_CARD_SECONDS,
  VIDEO_FORMATS,
  VIDEO_TITLE_SECONDS,
  VIDEO_TOTAL_SECONDS,
  VIDEO_TYPES,
  videoFileName,
  videoPart,
  videoReplayT,
  wrapText,
} from "./mae-sai-replay-export";

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
const text = (html: string) => html.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\u00a0/g, " ");

describe("Mae Sai flood replay page shell", () => {
  it("labels the replay as a historical reconstruction before any data loads", () => {
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    expect(html).toContain("Mae Sai flood, September 2024 — day by day");
    expect(html).toContain("Historical reconstruction for preparedness learning — not real-time, not an official warning.");
    expect(html).toContain('href="/studio/"');
    expect(html).toContain("Loading figures");
    // The shared replay wording lint: no affirmative real-time, live, forecast or warning wording.
    expect(findWordingViolations(visibleText(html), "page shell")).toEqual([]);
  });

  it("puts Play, the readout and a 'Map layers' drawer above the map, with the controls folded away", () => {
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    const play = html.indexOf('data-testid="play-button"');
    const readout = html.indexOf('data-testid="replay-readout"');
    const layers = html.indexOf('aria-controls="mae-sai-map-layers"');
    const map = html.indexOf('role="region"');
    expect(play).toBeGreaterThan(0);
    expect(readout).toBeGreaterThan(play);
    expect(layers).toBeGreaterThan(readout);
    // Play, readout and the drawer button come before the map; the layer controls live in a hidden drawer over it.
    expect(map).toBeGreaterThan(layers);
    expect(html).toMatch(/<div id="mae-sai-map-layers"[^>]*hidden=""/);
    expect(html).toMatch(/aria-expanded="false"[^>]*aria-controls="mae-sai-map-layers"/);
    expect(text(html)).toContain("Play 9 → 19 Sep (");
    expect(text(html)).toContain("Map layers");
    // The shared "How to read these numbers" box sits in the hero, collapsed.
    expect(html).toContain('data-testid="how-to-read"');
    expect(html).not.toMatch(/<details[^>]*data-testid="how-to-read"[^>]*open/);
    // The key facilities start hidden: the layer switch is off.
    const facilitiesSwitch = /<label><input type="checkbox"[^>]*\/><span[^>]*><i[^>]*><\/i><\/span><span>Key facilities \(OSM\)<\/span><\/label>/.exec(html)?.[0] ?? "";
    expect(facilitiesSwitch).not.toBe("");
    expect(facilitiesSwitch).not.toMatch(/checked/);
  });

  it("labels the play button with the window and its length, then Pause, Play from here and Replay", () => {
    expect(playLabel(0.5, false, "en")).toBe("Play 9 → 19 Sep (26\u00a0s)");
    expect(playLabel(0.5, false, "th")).toBe("เล่น 9 → 19 ก.ย. (26\u00a0วินาที)");
    expect(playLabel(3, true, "en")).toBe("Pause");
    expect(playLabel(3, false, "en")).toBe("Play from here");
    expect(playLabel(11, false, "en")).toBe("Replay");
  });

  it("reserves the width of every Play label, so the button and the bar never reflow between Play and Pause", () => {
    for (const language of ["en", "th"] as const) {
      const labels = playLabels(language);
      // Every label the button can show over the replay, playing or not, is among the reserved ones.
      for (let hour = 0; hour <= 264; hour += 1) {
        expect(labels, `${language} hour ${hour}`).toContain(playLabel(hour / 24, false, language));
        expect(labels, `${language} hour ${hour}`).toContain(playLabel(hour / 24, true, language));
      }
      expect(new Set(labels).size).toBe(labels.length);
    }
    expect(playLabels("en")).toEqual(expect.arrayContaining(["Pause", "Replay", "Play from here", "Play 9 → 19 Sep (26\u00a0s)"]));
    // The button carries them for the style sheet; its visible text is the one current label.
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    const button = /<button[^>]*data-testid="play-button"[^>]*>([\s\S]*?)<\/button>/.exec(html)![1];
    const reserved = /data-labels="([^"]*)"/.exec(button)![1].split("\n");
    expect(reserved).toEqual(playLabels("en"));
    expect(text(button).replace(/[▶❚]/g, "").trim()).toBe(playLabel(0.5, false, "en").replace(/\u00a0/g, " "));
  });

  it("keeps the notes, the legend and the bottom stack in one overlay, and makes the drawer focusable", () => {
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    const notes = html.indexOf('data-testid="map-notes"');
    const legend = html.indexOf('data-testid="map-legend"');
    const foot = html.indexOf('data-testid="map-foot"');
    const drawer = html.indexOf('id="mae-sai-map-layers"');
    expect(notes).toBeGreaterThan(0);
    // Reading order: notes, legend, then the stack that holds the basemap note and "Clear route selection".
    expect(legend).toBeGreaterThan(notes);
    expect(foot).toBeGreaterThan(legend);
    expect(drawer).toBeGreaterThan(foot);
    expect(html).toMatch(/<div[^>]*data-map-foot=""[^>]*data-testid="map-foot"><\/div>/);
    // The drawer can take focus when it opens (it is not a tab stop itself), and is labelled as a group.
    expect(html).toMatch(/<div id="mae-sai-map-layers" tabindex="-1"[^>]*role="group"[^>]*aria-label="Map layers"/);
  });

  it("names the first clear optical image after the flood began, so its brown areas read as flood mud", () => {
    const after = postEventOptical("s2-20240915", manifest.observations, manifest.phases);
    expect(after?.id).toBe("s2-20240915");
    expect(postEventOptical("s2-20240905", manifest.observations, manifest.phases)).toBeNull();
    expect(postEventOptical("s1-20240915", manifest.observations, manifest.phases)).toBeNull();
    expect(postEventOptical(null, manifest.observations, manifest.phases)).toBeNull();
    expect(postEventOptical("hillshade", manifest.observations, manifest.phases)).toBeNull();
  });

  it("explains how to read the numbers: model, observed and reported, confidence, timestamps, assumptions and terms", () => {
    const html = renderToStaticMarkup(<HowToRead manifest={manifest} language="en" />);
    const plain = text(html);
    expect(plain).toContain("How to read these numbers");
    expect(plain).toContain("Model: the blue water, impacts, access and shelter plans are model outputs");
    expect(plain).toContain("Reported: the event narrative and the 2024 shelter list come from public reporting.");
    expect(plain).toContain(`Confidence: ${manifest.confidence.toLowerCase() === "low" ? "low" : manifest.confidence}`);
    expect(plain).toContain(manifest.source_timestamp);
    expect(html).toContain('href="#mae-sai-sources"');
    for (const term of ["Stage", "HAND", "Freeboard", "Road nodes", "T1 scenario", "Low-confidence water"]) expect(plain).toContain(term);
    expect(findWordingViolations(visibleText(html), "HowToRead")).toEqual([]);
    const thai = text(renderToStaticMarkup(<HowToRead manifest={manifest} language="th" />));
    expect(thai).toContain("วิธีอ่านตัวเลขเหล่านี้");
    expect(thai).toContain("2567 (2024)");
  });
});

describe("Mae Sai replay panels", () => {
  it("scopes the impact figures to the modelled part of the district, or says the whole district is modelled", () => {
    const stats = districtStats(manifest, peakStage, roads, facilities);
    const html = text(renderToStaticMarkup(<ImpactCard manifest={manifest} stats={stats} derived={derived} language="en" />));
    const modelled = Math.round(manifest.model_coverage.modelled_km2);
    const district = Math.round(manifest.model_coverage.district_km2);
    if (coverageComplete(manifest.model_coverage)) {
      expect(html).toContain(`All eight Mae Sai subdistricts, fully modelled — ${district} km²`);
      expect(html).toContain(`Model coverage: ${manifest.model_coverage.reason}`);
      expect(html).not.toMatch(/Not modelled|Modelled parts/);
    } else {
      expect(html).toContain(`Modelled parts of the eight Mae Sai subdistricts — ${modelled} of ${district} km²`);
      expect(html).toContain(`Not modelled: ${manifest.model_coverage.reason}`);
    }
    expect(html).toContain("Computed in your browser from the terrain model at this stage.");
    expect(html).toContain(`${stats.facilities_wet} / ${manifest.facilities_count.modelled}`);
    // Roads and facilities outside the model are mentioned only when the manifest has some.
    expect(html.includes("km of mapped road")).toBe(manifest.roads_not_modelled_km > 0);
    const facilitiesOutside = manifest.facilities_count.total - manifest.facilities_count.modelled;
    expect(html.includes("outside the model (grey hollow markers)")).toBe(facilitiesOutside > 0);
    // Subdistricts under 99% coverage carry their modelled share; fully modelled ones do not.
    const partial = Object.entries(manifest.tambon_coverage).filter(([, item]) => item.modelled_km2 / item.total_km2 < 0.99);
    for (const [, item] of partial) expect(html).toContain(`(${Math.round((item.modelled_km2 / item.total_km2) * 100)}% modelled)`);
    expect(html.match(/% modelled\)/g) ?? []).toHaveLength(partial.length);
    expect(findWordingViolations(html, "ImpactCard")).toEqual([]);
    // The same card still names unmodelled land, roads and facilities when a revision has them.
    const firstTambon = Object.keys(manifest.tambon_coverage)[0];
    const partialManifest: TimelineManifest = {
      ...manifest,
      model_coverage: { modelled_km2: 294.4, district_km2: 305.6, reason: "The DEM tile used stops at 100°E." },
      tambon_coverage: { ...manifest.tambon_coverage, [firstTambon]: { modelled_km2: 10, total_km2: 20 } },
      roads_not_modelled_km: 1.83,
      facilities_count: { total: manifest.facilities_count.total, modelled: manifest.facilities_count.total - 2 },
    };
    const partialHtml = text(renderToStaticMarkup(<ImpactCard manifest={partialManifest} stats={stats} derived={derived} language="en" />));
    expect(partialHtml).toContain("Modelled parts of the eight Mae Sai subdistricts — 294 of 306 km²");
    expect(partialHtml).toContain("Not modelled: The DEM tile used stops at 100°E.");
    expect(partialHtml).toContain("1.83 km of mapped road");
    expect(partialHtml).toContain("2 key facilities (OSM) are outside the model");
    expect(partialHtml).not.toMatch(/candidate facilit/i);
    expect(partialHtml).toContain("(50% modelled)");
  });

  it("uses Thai units and keeps the candidate qualifier in Thai", () => {
    const stats = districtStats(manifest, peakStage, roads, facilities);
    const html = text(renderToStaticMarkup(<ImpactCard manifest={manifest} stats={stats} derived={derived} language="th" />));
    expect(html).toContain("สถานที่สำคัญ (ข้อมูล OSM)");
    expect(html).toContain("ตร.กม.");
    expect(html).toContain("กม.");
    expect(html).not.toMatch(/km²|\d km\b/);
    const legend = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads unmodelledFacilities={false} />));
    expect(legend).toContain("สถานที่สำคัญ (ข้อมูล OSM)");
    expect(legend).toContain("ไม่ได้จำลอง");
  });

  it("adds not-modelled legend entries only for symbols that are on the map", () => {
    const both = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities />));
    expect(both.match(/Not modelled/g)).toHaveLength(2);
    const none = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} />));
    expect(none).not.toContain("Not modelled");
    expect(none).not.toMatch(/above the (modelled )?flood range/i);
  });

  it("renders the radar size comparison from data as calibration-informed, with its footprint-wide scope", () => {
    const anchor = manifest.s1_anchor;
    const html = text(renderToStaticMarkup(<RadarCheck manifest={manifest} radarSpan="6 Sep → 16 Sep 06:16 ICT" language="en" />));
    expect(html).toContain(`${anchor.newly_dark_km2.toFixed(2)} km² turned newly water-like`);
    expect(html).toContain(`at a ${anchor.best_fit_stage_m.toFixed(2)} m stage`);
    expect(html).toContain(`${anchor.reconstruction_stage_at_pass_m.toFixed(3)} m`);
    expect(html).toContain(`Spatial agreement is weak (IoU ${anchor.iou_at_best_fit.toFixed(2)})`);
    // The recession keyframes were tuned to this pass (the manifest says so), so the page never calls it a check.
    expect(anchor.role).toBe("calibration_informed_magnitude_check");
    expect(html).toContain("Radar size comparison (Sentinel-1, 6 Sep → 16 Sep 06:16 ICT; calibration-informed, not an independent check)");
    expect(html).toContain("The recession keyframes were tuned to this pass, so the sizes agree by construction.");
    expect(html).toContain("so this constrains size, not location");
    expect(html).not.toMatch(/Radar check|this checks size/);
    expect(html).toContain(anchor.scope!);
    expect(html).toContain("including Tachileik (Myanmar)");
    const thai = text(renderToStaticMarkup(<RadarCheck manifest={manifest} radarSpan="" language="th" />));
    expect(thai).toContain("ท่าขี้เหล็ก (เมียนมา)");
    expect(thai).toContain("ขอบเขตการเทียบ");
    expect(thai).toContain("มีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ");
    expect(thai).not.toContain("ตรวจสอบกับเรดาร์");
  });

  it("adds the low-confidence water entry to the legend and the evidence only when the manifest declares the flag", () => {
    const withFlag = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} lowConfidence />));
    expect(withFlag).toContain("Low-confidence water: flat or filled low ground in the elevation model");
    const thai = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads={false} unmodelledFacilities={false} lowConfidence />));
    expect(thai).toContain("น้ำที่มีความเชื่อมั่นต่ำ: พื้นที่ต่ำที่ราบเรียบหรือถูกถมในแบบจำลองความสูง");
    const people = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} waterMode="people" densityMax={31.33} lowConfidence />));
    expect(people).toContain("Low-confidence water");
    expect(text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} />))).not.toContain("Low-confidence");
    // First flooded and hours under water hatch the same cells, so their legends carry the same entry.
    const classes = arrivalClasses(codeTimings(hourlyStages(manifest.stage_anchors), manifest.hand.step_m, manifest.hand.never_code).arrivalHour, ARRIVAL_RAMP, manifest.hand.channel_code);
    for (const waterMode of ["arrival", "duration"] as const) {
      const html = renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} waterMode={waterMode} arrival={classes} lowConfidence part="overlay" />);
      expect(html, waterMode).toContain('data-testid="low-confidence-legend"');
      expect(text(html), waterMode).toContain("Low-confidence water: flat or filled low ground in the elevation model");
      const thaiMode = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads={false} unmodelledFacilities={false} waterMode={waterMode} arrival={classes} lowConfidence part="overlay" />));
      expect(thaiMode, waterMode).toContain("น้ำที่มีความเชื่อมั่นต่ำ");
      expect(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} waterMode={waterMode} arrival={classes} part="overlay" />), waterMode)
        .not.toContain("low-confidence-legend");
    }
    // The key is drawn in the colours the map gives low-confidence water in that view: blue for depth, purple for the
    // first-flooded and hours-under-water views. A fixed blue key would match no hatched area there.
    const swatch = (html: string) => html.match(/<i class="[^"]*lowConfidenceSwatch[^"]*"[^>]*>/)?.[0] ?? "";
    const gradient = (waterMode: WaterMode) => {
      const key = lowConfidenceKey(waterMode, classes);
      return `repeating-linear-gradient(45deg, ${rgbaCss(key.stripe)} 0 2px, ${rgbaCss(key.wash)} 2px 5px)`;
    };
    const keys = new Set<string>();
    for (const waterMode of ["depth", "arrival", "duration"] as const) {
      const html = renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} waterMode={waterMode} arrival={classes} lowConfidence part="overlay" />);
      expect(swatch(html), waterMode).toContain(`data-view="${waterMode}"`);
      expect(swatch(html), waterMode).toContain(`style="background:${gradient(waterMode)}"`);
      keys.add(gradient(waterMode));
    }
    expect(keys.size).toBe(3);
    // Evidence: the share at the modelled peak, from the manifest (14 of 88.7 km²), and what it means.
    const share = manifest.hand.low_confidence_share!;
    const evidence = text(renderToStaticMarkup(<dl><LowConfidenceEvidence hand={manifest.hand} language="en" /></dl>));
    expect(evidence).toContain(`${share.low_confidence_km2.toFixed(1)} of the ${share.peak_flooded_km2.toFixed(1)} km² wet at the modelled peak is flat or filled low ground in the elevation model`);
    expect(evidence).toContain(manifest.hand.low_confidence!.meaning);
    expect(text(renderToStaticMarkup(<dl><LowConfidenceEvidence hand={manifest.hand} language="th" /></dl>))).toContain(`${share.low_confidence_km2.toFixed(1)} จาก ${share.peak_flooded_km2.toFixed(1)} ตร.กม.`);
    expect(renderToStaticMarkup(<dl><LowConfidenceEvidence hand={{ ...manifest.hand, low_confidence_channel: null }} language="en" /></dl>)).toBe("<dl></dl>");
    // The evidence names every view that is hatched, not only depth and people.
    expect(evidence).toContain("paler and hatched in every view that shows water (depth, first flooded, hours under water and people in flood water)");
    expect(evidence).toContain("It is still counted in every flooded-area, road, people and access figure.");
    expect(text(renderToStaticMarkup(<dl><LowConfidenceEvidence hand={manifest.hand} language="th" /></dl>))).toContain("ในทุกมุมมองที่แสดงน้ำ (ความลึก เวลาที่เริ่มท่วม จำนวนชั่วโมงที่จมน้ำ และประชากรในพื้นที่น้ำท่วม)");
  });

  it("says in the legend that the map shows water depth while a resident view waits for its raster", () => {
    // The page passes the view the map draws (depth) and why; the legend must not show the residents key meanwhile.
    for (const language of ["en", "th"] as const) {
      for (const pending of ["loading", "error"] as const) {
        const html = renderToStaticMarkup(<TimelineLegend language={language} unmodelledRoads={false} unmodelledFacilities={false} waterMode="depth" densityMax={31.33} lowConfidence residentsPending={pending} part="overlay" />);
        const plain = text(html);
        expect(html).toContain('data-testid="legend-residents-pending"');
        expect(plain).toContain(residentsPendingText(pending, language));
        expect(plain).toContain(language === "th" ? "ความลึกของน้ำ (แบบจำลอง)" : "Water depth (model)");
        expect(plain).not.toMatch(/residents per hectare|คนต่อเฮกตาร์/);
        expect(html).toContain('data-testid="low-confidence-legend"');
      }
    }
    // Once the raster is ready the page passes the resident view and no pending state: the residents key, no notice.
    const ready = renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} waterMode="people" densityMax={31.33} lowConfidence part="overlay" />);
    expect(ready).not.toContain("legend-residents-pending");
    expect(text(ready)).toContain("People in flood water: residents per hectare");
    expect(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} part="overlay" />)).not.toContain("legend-residents-pending");
  });

  it("splits the legend into the on-map part (water and roads) and the marker key", () => {
    const shelters = { reported: true, candidates: true, ineligible: false };
    const overlay = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} shelters={shelters} cutoff part="overlay" />));
    expect(overlay).toContain("Water depth (model)");
    expect(overlay).toContain("Roads (model)");
    expect(overlay).toContain("People cut off from a dry shelter (scenario)");
    expect(overlay).not.toMatch(/Shelters|Key facilities/);
    const symbols = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} shelters={shelters} facilities={false} part="symbols" />));
    expect(symbols).toContain("Reported, but floods at the modelled peak (struck-through star)");
    expect(symbols).toContain("capacity unknown or far below its load");
    expect(symbols).not.toMatch(/Water depth|Key facilities/);
    const empty = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} facilities={false} part="symbols" />));
    expect(empty).toContain("No marker layers are on");
  });

  it("lists facilities in water deepest first and hides the list when none are wet", () => {
    const html = renderToStaticMarkup(<WetFacilitiesCard facilities={facilities} stage={peakStage} language="en" />);
    expect(text(html)).toContain("Key facilities (OSM) in water at this replay hour");
    expect(text(html)).not.toMatch(/\bnow\b/);
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
    // Each cell's rise is scaled by a factor (from r2 on), so the curve is the Sai main-stem reference stage, not every
    // channel's; the page does not call that factor "k" (k is the plan size).
    expect(text(html)).toContain("Assumed Sai main-stem stage at the Mae Sai bridges (m) — illustrative; tributaries rise to a fraction of this level");
    expect(text(html)).not.toContain("k ×");
    expect(html).toMatch(/aria-label="[^"]*at this replay hour\."/);
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
    // Named roads and unnamed street groups are listed separately; known roads carry an English label.
    expect(plain).toMatch(/Named roads \(\d+\)/);
    expect(plain).toMatch(/Unnamed street groups \(top \d+\)/);
    if (groups.some((group) => group.name === "ถนนพหลโยธิน")) expect(plain).toContain("Phahonyothin Rd (Hwy 1) (ถนนพหลโยธิน)");
    expect(plain).not.toContain("20 Sep 00:00");
    expect(plain).toContain("Modelled, not observed closures");
    expect(html.match(/<li>/g)).toHaveLength(groups.length);
    expect(plain).toContain(`Up to ${groups[0].maxHours} h cut`);
    expect(plain).toMatch(/First cut \d{1,2} Sep \d{2}:00 → reopened/);
    expect(plain).not.toContain("Show the whole area");
    expect(plain.replaceAll("not observed", "")).not.toMatch(/observed/i);
    expect(findWordingViolations(visibleText(html), "RouteCutsCard")).toEqual([]);
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

  it("opens and closes the video with a one-second card around the 9-19 Sep replay, in portrait or 16:9", () => {
    expect(VIDEO_TITLE_SECONDS).toBe(1);
    expect(VIDEO_END_CARD_SECONDS).toBe(1);
    expect(videoPart(0)).toEqual({ part: "title" });
    expect(videoPart(0.99)).toEqual({ part: "title" });
    expect(videoPart(1)).toEqual({ part: "replay", t: 0 });
    expect(videoPart(1 + 7)).toEqual({ part: "replay", t: 3.5 });
    // The last replay frame is 19 Sep 23:00, never 20 Sep 00:00, and it holds briefly before the end card.
    const last = videoPart(VIDEO_TOTAL_SECONDS - VIDEO_END_CARD_SECONDS - 0.01);
    expect(last.part).toBe("replay");
    expect(last.part === "replay" && last.t).toBeLessThan(11);
    expect(videoPart(VIDEO_TOTAL_SECONDS - 0.5)).toEqual({ part: "end" });
    expect(videoPart(VIDEO_TOTAL_SECONDS + 0.01)).toEqual({ part: "done" });
    expect(Math.round(VIDEO_TOTAL_SECONDS)).toBe(24);
    expect(VIDEO_FORMATS.landscape.width).toBe(1280);
    expect(VIDEO_FORMATS.portrait.width).toBe(720);
    expect(videoFileName("portrait", "mp4")).toBe("mae-sai-flood-2024.mp4");
    expect(videoFileName("landscape", "webm")).toBe("mae-sai-flood-2024-16x9.webm");
  });

  it("places orientation labels from the data: the Hwy 1 border bridge, Mae Sai town and Myanmar to the north", () => {
    const tambonShapes = readJson<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href).features;
    const labels = exportPlaceLabels(roadCollection.features, tambonShapes, manifest.bounds);
    expect(labels.map((label) => label.kind)).toEqual(["bridge", "town", "country"]);
    const [bridge, town, country] = labels;
    expect(bridge.text.en).toContain("Sai River");
    expect(town.text).toEqual({ en: "Mae Sai town", th: "ตัวเมืองแม่สาย" });
    expect(country.text.en).toContain("MYANMAR");
    expect(country.lat).toBeGreaterThan(bridge.lat);
    const [[south, west], [north, east]] = manifest.bounds;
    for (const label of labels) {
      expect(label.lat).toBeGreaterThanOrEqual(south);
      expect(label.lat).toBeLessThanOrEqual(north);
      expect(label.lon).toBeGreaterThanOrEqual(west);
      expect(label.lon).toBeLessThanOrEqual(east);
    }
    // The bridge is the northernmost vertex of Highway 1.
    const hwy1 = roadCollection.features.filter((feature) => feature.properties.n?.trim() === "ถนนพหลโยธิน");
    expect(bridge.lat).toBe(Math.max(...hwy1.flatMap((feature) => feature.geometry.coordinates.map(([, lat]) => lat))));
    expect(exportPlaceLabels([], tambonShapes, manifest.bounds)).toEqual([]);
  });

  it("gives exported frames a round-number scale bar and wraps caption text to the panel", () => {
    const bar = exportScaleBar(manifest.bounds, 720, 720 * 0.22);
    expect([1, 2, 5, 10]).toContain(bar.km);
    expect(bar.pixels).toBeLessThanOrEqual(720 * 0.22);
    expect(bar.pixels).toBeGreaterThan(0);
    // Doubling the frame width doubles the pixels per kilometre.
    const wide = exportScaleBar(manifest.bounds, 1440, 1440 * 0.22);
    expect(wide.km).toBe(bar.km);
    expect(wide.pixels).toBeCloseTo(bar.pixels * 2, 6);
    const measure = (value: string) => value.length * 10;
    expect(wrapText(measure, "one two three four", 100, "en")).toEqual(["one two", "three four"]);
    expect(wrapText(measure, "unbreakableword", 50, "en")).toEqual(["unbreakableword"]);
  });

  it("names the served data revision, which is also the manifest's own revision field", () => {
    expect(manifestRevision()).toBe("r4");
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

  it("says which water view the PNG and the video draw: the view on the map, or water depth for the resident views", () => {
    expect(exportViewText("depth", "en")).toBe("The PNG and the video show water depth (model), as on the map.");
    expect(exportViewText("arrival", "en")).toBe("The PNG and the video show the first flooded hour (model), as on the map.");
    expect(exportViewText("duration", "en")).toBe("The PNG and the video show hours under water (model), as on the map.");
    for (const mode of ["people", "residents"] as const) {
      expect(exportViewText(mode, "en")).toBe("The PNG and the video show water depth (model); the resident views are not exported.");
      expect(exportViewText(mode, "th")).toContain("มุมมองผู้อยู่อาศัยไม่ถูกส่งออก");
    }
    for (const mode of ["depth", "arrival", "duration", "people", "residents"] as WaterMode[]) {
      expect(exportViewText(mode, "th")).not.toMatch(/[A-Za-z]{4,}/);
      expect(exportViewText(mode, "th")).toContain("(แบบจำลอง)");
    }
    const panel = renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="en" waterOpacity={0.85} waterMode="arrival" />);
    expect(panel).toContain('data-testid="export-view"');
    expect(text(panel)).toContain(exportViewText("arrival", "en"));
    // Without the prop the panel exports (and says) water depth, as before.
    expect(text(renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="en" waterOpacity={0.85} />))).toContain(exportViewText("depth", "en"));
  });
});

describe("Mae Sai observed evidence panels", () => {
  const viirs = manifest.viirs_daily!;
  const rainfall = manifest.rainfall!;
  const dayLabels = manifest.days.map((day) => String(Number(day.date.slice(8))));
  const noop = () => undefined;

  it("tabulates VIIRS against the model in clear-sky pixels, day by day, and never calls it a validation", () => {
    const active = viirs.days[Math.min(3, viirs.days.length - 1)];
    const html = renderToStaticMarkup(<ViirsComparisonCard viirs={viirs} activeDate={active.date} showOnMap={false} onShowOnMap={noop} language="en" />);
    const plain = text(html);
    expect(plain).toContain("Observed vs modelled (VIIRS, clear sky only)");
    expect(html.match(/<tr/g)).toHaveLength(viirs.days.length + 1);
    expect(html.match(/aria-current="date"/g)).toHaveLength(1);
    // A day with no clear sky shows dashes, never a zero that would read as "no flood".
    const rows = html.split("<tr").slice(2);
    viirs.days.forEach((day, index) => expect(rows[index].includes("—"), day.date).toBe(!(day.clear_km2 > 0)));
    for (const day of viirs.days) {
      expect(plain).toContain(viirsReading(day).en);
      expect(plain).toContain(`${Math.round(day.cloud_share * 100)}%`);
    }
    expect(plain).toContain(viirs.caveat);
    expect(plain).toContain(viirs.comparison_rule);
    expect(plain).toContain("not a validation of the model");
    // "not a validation" is an allowlisted negation; any other validation or accuracy wording is a finding.
    expect(findWordingViolations(visibleText(html), "ViirsComparisonCard")).toEqual([]);
    expect(plain).toContain("standing water in rice paddies can read as flood water");
    const cloudy = viirs.days.filter((day) => day.cloud_share >= 0.5).map((day) => day.date);
    if (cloudy.length > 0) expect(plain).toContain(`Cloud hid at least half of the district on ${cloudy.length} of ${viirs.days.length} days (${formatDateSet(cloudy, "en")})`);
    expect(html).toContain(`href="${viirs.source_url}"`);
    expect(html).toContain('rel="noopener noreferrer"');
    const thai = text(renderToStaticMarkup(<ViirsComparisonCard viirs={viirs} activeDate={null} showOnMap onShowOnMap={noop} language="th" />));
    expect(thai).toContain("การสังเกตเทียบกับแบบจำลอง (VIIRS เฉพาะท้องฟ้าโปร่ง)");
    expect(thai).toContain(viirsReading(active).th);
    expect(formatDateSet(["2024-09-12", "2024-09-10", "2024-09-11", "2024-09-18"], "en")).toBe("10–12 Sep, 18 Sep");
    expect(formatDateSet(["2024-09-30", "2024-10-01"], "en")).toBe("30 Sep – 1 Oct");
  });

  it("describes the VIIRS map at this moment, or why there is none, and labels its legend as observed", () => {
    const clear = viirs.days.find((day) => day.clear_km2 > 0)!;
    expect(viirsMomentText(clear, viirs, "en")).toContain(`VIIRS shows ${clear.viirs_flood_km2_clear.toFixed(1)} km² of flood water and the model ${clear.model_flood_km2_clear.toFixed(1)} km²`);
    const overcast = viirs.days.find((day) => !(day.clear_km2 > 0));
    if (overcast) expect(viirsMomentText(overcast, viirs, "en")).toContain("cloud covered the whole district, so there is no observation");
    expect(viirsMomentText(null, viirs, "en")).toContain("No VIIRS daily map for this moment");
    expect(viirsMomentText(null, viirs, "th")).toMatch(/[\u0E00-\u0E7F]/);
    const legend = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} viirs={viirs} gauges />));
    expect(legend).toContain("VIIRS daily flood map (375 m, observed)");
    for (const [code, label] of Object.entries(viirs.legend)) if (code !== "transparent") expect(legend).toContain(label);
    expect(legend).toContain("Purple is observed flood water; the model's water is blue.");
    expect(legend).toContain("Hourly rain gauge (forcing, not flooding)");
    expect(text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} />))).not.toMatch(/VIIRS|rain gauge/);
  });

  it("charts hourly rain per gauge on the replay's time axis, with only the playhead moving", () => {
    const html = renderToStaticMarkup(<RainChart rainfall={rainfall} time={3.5} dayLabels={dayLabels} language="en" />);
    const plain = text(html);
    expect(html).toContain('role="img"');
    for (const station of rainfall.stations) {
      expect(plain).toContain(`${station.code} · rain, mm/h · total ${station.total_mm.toFixed(1)} mm · wettest hour ${station.max_hour_mm.toFixed(1)} mm`);
      const wetHours = rainfall.hourly_mm[station.code].filter((value) => typeof value === "number" && value > 0).length;
      const bars = new RegExp(`data-station="${station.code}"[\\s\\S]*?<path d="([^"]+)" class="[^"]*rainBar`).exec(html)![1];
      expect(bars.match(/M/g)).toHaveLength(wetHours);
      const now = rainAt(rainfall, station.code, 84);
      expect(plain).toContain(`${station.code} ${now === null ? "no record" : `${now.toFixed(1)} mm`}`);
    }
    expect(plain).toContain("the forcing, not flooding");
    expect(plain).toContain(rainfall.licence);
    // Everything but the playhead and the "this hour" readout is identical at another moment.
    const later = renderToStaticMarkup(<RainChart rainfall={rainfall} time={7.25} dayLabels={dayLabels} language="en" />);
    const strip = (value: string) => value
      .replace(/<line[^>]*class="[^"]*playhead[^"]*"[^>]*>(<\/line>)?/, "")
      .replace(/<span[^>]*data-testid="rain-now"[^>]*>[\s\S]*?<\/span>/, "");
    expect(strip(later)).toBe(strip(html));
    expect(later).not.toBe(html);
    const thai = text(renderToStaticMarkup(<RainChart rainfall={rainfall} time={3.5} dayLabels={dayLabels} language="th" />));
    expect(thai).toContain("ไม่ใช่ขอบเขตน้ำท่วม");
  });

  it("lists every source, assumption and limitation from the manifest, with the observed data linked and ingested references dropped", () => {
    const html = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />);
    const plain = text(html);
    expect(manifest.sources.map((source) => source.id)).toEqual(expect.arrayContaining(["viirs", "hii-rain"]));
    for (const source of manifest.sources) {
      expect(plain).toContain(plainManifestText(source.name));
      expect(plain).toContain(source.licence);
      expect(plain).toContain(source.attribution);
    }
    // Each manifest sentence is listed, after the page's documented plain-language clean-up (internal ids out, and
    // the tributary factor described in words because "k" on this page is the plan size).
    for (const item of manifest.assumptions) expect(plain).toContain(plainManifestText(item));
    for (const item of manifest.limitations) expect(plain).toContain(plainManifestText(item));
    const tributary = manifest.assumptions.find((item) => item.includes("k x stage"));
    if (tributary) {
      expect(plain).not.toContain("k x stage");
      expect(plain).toContain("tributaries rise to a fraction of the stage");
    }
    // The depth factor is named in words and written f; no standalone "k" (the plan size) is left in the panel.
    expect(manifest.assumptions.some((item) => STANDALONE_K.test(item))).toBe(true);
    expect(plain).toContain("scaled by the depth factor f = clip(");
    expect(plain).toContain("the exported depth factor f makes h + 0.3/f equal the earliest sample closure");
    expect(plain).toContain("The depth factor f = clip(");
    expect(plain).not.toMatch(STANDALONE_K);
    const thaiPanel = text(renderToStaticMarkup(<SourcesPanel manifest={manifest} language="th" offlineCopy={null} />));
    expect(thaiPanel).toContain("ตัวคูณความลึก f = clip(");
    expect(thaiPanel).not.toMatch(STANDALONE_K);
    for (const url of [viirs.source_url, rainfall.source_url]) expect(html).toContain(`href="${url}"`);
    expect(plain).toContain(viirs.caveat);
    expect(plain).toContain(rainfall.note);
    const pending = referencesNotIngested(manifest);
    for (const reference of manifest.external_references ?? []) {
      expect(plain.includes(reference.name), reference.name).toBe(pending.includes(reference));
    }
    expect(plain).toContain(`${manifest.study_id} ${manifestRevision()}`);
  });

  it("keeps internal ids out of the sources panel and states its explanations in Thai", () => {
    const english = text(renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />));
    const thaiHtml = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="th" offlineCopy={null} />);
    const thai = text(thaiHtml);
    for (const plain of [english, thai]) {
      expect(plain).not.toMatch(/reported_2024|tha_ppp_2020|late_cumulative_share|m=false|decision D\d|\(D\d\)/);
    }
    // Page-authored labels are translated; manifest sentences use their Thai rendering.
    expect(thai).not.toMatch(/\b(Travel|Residents|Units|Stations):/);
    expect(thai).toContain("การเดินทาง: เดินบนถนนที่สัญจรได้");
    expect(thai).toContain("สถานการณ์จำลองระดับ T1 (แบบจำลอง) ไม่ใช่ผลการอพยพที่สังเกตได้จริง");
    expect(thai).toContain("ปริมาณฝนที่ตรวจวัดได้ (ปัจจัยที่ทำให้เกิดน้ำ) ไม่ใช่ขอบเขตน้ำท่วม");
    expect(thai).toContain(rainfall.stations[0].name_th);
    expect(thai).not.toContain(viirs.caveat);
    // Source names and licences stay as published, marked as English.
    expect(thaiHtml).toContain(`<strong lang="en">${manifest.sources[0].name}</strong>`);
  });
});

describe("Mae Sai Sentinel-2 water check on 15 Sep", () => {
  const THAI = /[฀-๿]/;
  const check = manifest.s2_crosscheck!;
  const viirs = manifest.viirs_daily!;
  const scenes = s2CrosscheckScenes(check)!;
  const viirsDay = viirs.days.find((day) => day.date === s2CrosscheckDate(check))!;
  const noop = () => undefined;
  const km = (value: number | null) => (value ?? Number.NaN).toFixed(1);
  const pct = (share: number) => `${Math.round(share * 100)}%`;
  const READING = "The larger observed area is consistent with water or saturated mud left after the river fell; the terrain-only model cannot hold water once the river level drops.";
  const NEXT_DAY_READING = "A day later the VIIRS map shows less flood water than the model in its clear pixels, so the larger area on the day of the scene is consistent with saturated mud or short-lived water rather than lasting ponding.";
  const model = check.model_at_event_scene;
  const nextDay = followingViirsDay(check, viirs)!;

  it("is one observation of one day: on show from 15 Sep 00:00 to 24:00 ICT and at no other time", () => {
    expect(s2CrosscheckDate(check)).toBe("2024-09-15");
    expect(scenes.event.id).toBe("s2-20240915");
    expect(scenes.pre.id).toBe("s2-20240905");
    expect(viirsDay.date).toBe("2024-09-15");
    const start = tFromDate("2024-09-15T00:00:00+07:00");
    expect(start).toBe(6);
    expect(s2CrosscheckAt(start, check)).toBe(check);
    expect(s2CrosscheckAt(start + 0.5, check)).toBe(check);
    expect(s2CrosscheckAt(start + 1 - 1e-6, check)).toBe(check);
    for (const t of [0, 3.5, start - 1e-6, start + 1, 10.9, Number.NaN]) expect(s2CrosscheckAt(t, check), String(t)).toBeNull();
    expect(s2CrosscheckAt(start + 0.5, undefined)).toBeNull();
    expect(s2CrosscheckAt(start + 0.5, null)).toBeNull();
    // A block without both scenes, or with an unreadable time, is never shown.
    expect(s2CrosscheckAt(start + 0.5, { scenes: [scenes.event] })).toBeNull();
    expect(s2CrosscheckAt(start + 0.5, { scenes: [scenes.pre, { ...scenes.event, source_timestamp: "soon" }] })).toBeNull();
    // 03:58 UTC is 10:58 ICT the same day; a scene late in the UTC day belongs to the next local day.
    expect(s2CrosscheckDate({ scenes: [scenes.pre, { ...scenes.event, source_timestamp: "2024-09-15T18:30:00Z" }] })).toBe("2024-09-16");
  });

  it("labels the observation with its product, acquisition time and clear share, as water or saturated mud", () => {
    const english = s2ObservedText(check, "en");
    expect(english).toBe(
      `Observed (Sentinel-2 L2A, 15 Sep 10:58 ICT, ${pct(scenes.event.clear_share)} of the district clear): ${km(scenes.event.water_km2)} km² of water or saturated mud outside the mapped channels, `
      + `against ${km(scenes.pre.water_km2)} km² on 5 Sep, before the flood (${pct(scenes.pre.clear_share)} clear). Where both dates are clear, ${km(check.change.new_water_km2)} km² is new.`);
    expect(english).not.toMatch(/flood extent|flood water|flooded/);
    expect(check.label).toBe("water or saturated mud");
    expect(scenes.event.local_time).toBe("2024-09-15T10:58:15+07:00");
    const modelText = s2ModelText(check, "en");
    expect(modelText).toBe(`Model at that time (assumed stage ${check.model_at_event_scene.model_stage_m.toFixed(2)} m): ${km(check.model_at_event_scene.model_flood_km2_clear)} km² in the same clear pixels. This comparison is indicative.`);
    expect(check.comparison).toBe("indicative");
    const thai = `${s2ObservedText(check, "th")} ${s2ModelText(check, "th")}`;
    expect(thai).toContain("สังเกตการณ์ (Sentinel-2 L2A 15 ก.ย. 10:58 น.");
    expect(thai).toContain(`มองเห็นพื้นที่อำเภอ ${pct(scenes.event.clear_share)}`);
    expect(thai).toContain(`น้ำหรือโคลนอิ่มน้ำ ${km(scenes.event.water_km2)} ตร.กม.`);
    expect(thai).toContain("การเปรียบเทียบนี้เป็นเพียงข้อบ่งชี้");
    expect(thai.replace("Sentinel-2 L2A", "")).not.toMatch(/[A-Za-z]{3,}/);  // Nothing is left in English but the product name.
    // A scene with nothing clear is no observation, never a zero.
    const hidden: S2Crosscheck = { ...check, scenes: [scenes.pre, { ...scenes.event, clear_share: 0, clear_km2: 0, water_km2: null }] };
    expect(s2ObservedText(hidden, "en")).toBe("Observed (Sentinel-2 L2A, 15 Sep 10:58 ICT): cloud covered the whole district, so there is no observation.");
    expect(s2ObservedText(hidden, "en")).not.toMatch(/0\.0 km²/);
    expect(bothObservationsText(hidden, viirsDay, "en")).toBe("");
    expect(observedLargerThanModel(hidden, viirsDay)).toBe(false);
  });

  it("names both observations of the day and says what the larger observed area is consistent with, never a cause", () => {
    const html = renderToStaticMarkup(<dl><Sentinel2Evidence check={check} viirsDay={viirsDay} language="en" /></dl>);
    const plain = text(html);
    expect(html).toContain('data-testid="s2-evidence"');
    expect(html).toContain('data-testid="observed-reading"');
    expect(plain).toContain("Sentinel-2 (observed)");
    expect(plain).toContain(s2ObservedText(check, "en"));
    expect(plain).toContain("This comparison is indicative.");
    expect(plain).toContain(
      `Two observations on this day: VIIRS (15 Sep 13:30 ICT, nominal) shows ${km(viirsDay.viirs_flood_km2_clear)} km² of flood water against the model's ${km(viirsDay.model_flood_km2_clear)} km², `
      + `and Sentinel-2 (15 Sep 10:58 ICT) shows ${km(scenes.event.water_km2)} km² of water or saturated mud against the model's ${km(model.model_flood_km2_clear)} km², `
      + `of which ${km(check.change.new_water_km2)} km² is new since 5 Sep against the model's ${km(model.model_flood_km2_both_clear!)} km² where both dates are clear. Each is counted in its own clear pixels.`);
    // Both observations exceed the model in this bake, so the reading is shown, word for word from the manifest. For
    // Sentinel-2 the test is like for like: the water that is new since 5 Sep against the model where both dates are clear.
    expect(viirsDay.viirs_flood_km2_clear).toBeGreaterThan(viirsDay.model_flood_km2_clear);
    expect(check.change.new_water_km2!).toBeGreaterThan(model.model_flood_km2_both_clear!);
    expect(model.model_flood_km2_both_clear!).toBeLessThanOrEqual(model.model_flood_km2_clear);
    expect(observedLargerThanModel(check, viirsDay)).toBe(true);
    // No land-cover map is an input: the reading names no kind of land.
    expect(plain).not.toMatch(/on fields|cropland|farmland/i);
    expect(check.reading).toBe(READING);
    expect(html).toContain(`<strong data-testid="s2-reading"><span lang="en">${READING}</span></strong>`);
    expect(plain).toContain(check.caveat);
    expect(plain).toContain("not a flood extent");
    // "is consistent with" is the claim; the text never says the observation explains the gap or proves a cause.
    expect(plain).not.toMatch(/explain|because of|caused by|due to|proves?\b|confirms?\b/i);
    expect(findWordingViolations(visibleText(html), "Sentinel2Evidence")).toEqual([]);

    const thaiHtml = renderToStaticMarkup(<dl><Sentinel2Evidence check={check} viirsDay={viirsDay} language="th" /></dl>);
    const thai = text(thaiHtml);
    expect(thai).toContain("Sentinel-2 (สังเกตการณ์)");
    expect(thai).toContain("วันนี้มีการสังเกตการณ์สองแหล่ง: VIIRS (15 ก.ย. 13:30 น. โดยประมาณ)");
    expect(thai).toContain("พื้นที่ที่สังเกตได้ซึ่งกว้างกว่าสอดคล้องกับน้ำหรือโคลนอิ่มน้ำที่ยังค้างอยู่หลังระดับแม่น้ำลดลง");
    expect(thai).toContain("แบบจำลองที่ใช้เฉพาะภูมิประเทศไม่สามารถกักน้ำไว้ได้เมื่อระดับแม่น้ำลดลง");
    expect(thai).toContain(`เพิ่มขึ้นใหม่หลัง 5 ก.ย. เทียบกับแบบจำลอง ${km(model.model_flood_km2_both_clear!)} ตร.กม. ในบริเวณที่มองเห็นได้ทั้งสองวัน`);
    expect(thai).not.toContain("ไร่นา");
    expect(thai).toContain("ไม่ใช่ขอบเขตน้ำท่วม");
    expect(thai).not.toContain(READING);
    expect(thai).not.toContain(check.caveat);
    expect(thai).not.toMatch(/อธิบาย|เพราะ|สาเหตุ/);
    expect(thaiHtml).not.toContain('lang="en"');
    expect(findWordingViolations(visibleText(thaiHtml), "Sentinel2Evidence th")).toEqual([]);
    for (const sentence of [check.reading, check.caveat, check.index, check.water_rule, check.clear_rule, check.permanent_water_rule,
      check.comparison_rule, check.confidence_reason, check.scope]) {
      const rendered = localizedText(sentence, "th");
      expect(rendered.lang, sentence).toBe("th");
      expect(rendered.text, sentence).toMatch(THAI);
    }
  });

  it("gives the next clear VIIRS day beside the reading, because it cuts against lasting ponding", () => {
    // The manifest names the day and says what it is consistent with; the figures come from the VIIRS rows.
    expect(check.following_day).toEqual({ viirs_date: "2024-09-16", reading: NEXT_DAY_READING });
    expect(nextDay.date).toBe("2024-09-16");
    expect(nextDay.viirs_flood_km2_clear).toBeLessThan(nextDay.model_flood_km2_clear);
    const figures = followingDayText(nextDay, "en");
    expect(figures).toBe(
      `The next clear VIIRS map (16 Sep 13:30 ICT, nominal) shows ${km(nextDay.viirs_flood_km2_clear)} km² of flood water against the model's ${km(nextDay.model_flood_km2_clear)} km², in ${km(nextDay.clear_km2)} km² of clear sky.`);
    const html = renderToStaticMarkup(<dl><Sentinel2Evidence check={check} viirsDay={viirsDay} nextViirsDay={nextDay} language="en" /></dl>);
    const plain = text(html);
    expect(html).toContain('data-testid="s2-following-day"');
    expect(plain).toContain(`${READING} ${figures} ${NEXT_DAY_READING} ${check.caveat}`);
    expect(plain).not.toMatch(/explain|because of|caused by|due to|proves?\b|confirms?\b|on fields/i);
    expect(findWordingViolations(visibleText(html), "Sentinel2Evidence with the next day")).toEqual([]);
    const thaiHtml = renderToStaticMarkup(<dl><Sentinel2Evidence check={check} viirsDay={viirsDay} nextViirsDay={nextDay} language="th" /></dl>);
    expect(thaiHtml).not.toContain('lang="en"');
    expect(text(thaiHtml)).toContain("แผนที่ VIIRS ที่ท้องฟ้าโปร่งถัดมา (16 ก.ย. 13:30 น. โดยประมาณ)");
    expect(text(thaiHtml)).toContain("สอดคล้องกับโคลนอิ่มน้ำหรือน้ำที่ค้างอยู่ช่วงสั้น ๆ มากกว่าน้ำขังที่คงอยู่นาน");
    expect(text(thaiHtml)).not.toMatch(/อธิบาย|เพราะ|สาเหตุ/);
    expect(findWordingViolations(visibleText(thaiHtml), "Sentinel2Evidence with the next day th")).toEqual([]);
    expect(localizedText(NEXT_DAY_READING, "th").lang).toBe("th");
    // Without the manifest's sentence, without the day's row, or when the day's reading is not shown, nothing is added.
    const without = (s2: S2Crosscheck, day: typeof nextDay | null, same = viirsDay) =>
      renderToStaticMarkup(<dl><Sentinel2Evidence check={s2} viirsDay={same} nextViirsDay={day} language="en" /></dl>);
    expect(without(check, null)).not.toContain('data-testid="s2-following-day"');
    expect(without({ ...check, following_day: undefined }, nextDay)).not.toContain('data-testid="s2-following-day"');
    expect(without(check, nextDay, { ...viirsDay, viirs_flood_km2_clear: 0 })).not.toContain('data-testid="s2-following-day"');
    expect(followingViirsDay({ following_day: undefined }, viirs)).toBeNull();
    expect(followingViirsDay(check, null)).toBeNull();
    expect(followingViirsDay({ following_day: { viirs_date: "2024-09-30", reading: NEXT_DAY_READING } }, viirs)).toBeNull();
    expect(followingViirsDay(check, { days: viirs.days.map((day) => (day.date === nextDay.date ? { ...day, clear_km2: 0 } : day)) })).toBeNull();
  });

  it("does not speak of a larger observed area unless every observation of the day is larger than the model", () => {
    const smallS2: S2Crosscheck = { ...check, model_at_event_scene: { ...model, model_flood_km2_both_clear: (check.change.new_water_km2 ?? 0) + 5 } };
    expect(observedLargerThanModel(smallS2, viirsDay)).toBe(false);
    // The whole wet area alone does not decide: it also holds ponds, paddies and mud that were there before the flood.
    // Here the total stays above the model while the water that is new since 5 Sep falls below it: no reading.
    const preFlood: S2Crosscheck = { ...check, change: { ...check.change, new_water_km2: model.model_flood_km2_both_clear! - 1 } };
    expect(scenes.event.water_km2!).toBeGreaterThan(model.model_flood_km2_clear);
    expect(observedLargerThanModel(preFlood, viirsDay)).toBe(false);
    expect(renderToStaticMarkup(<dl><Sentinel2Evidence check={preFlood} viirsDay={viirsDay} nextViirsDay={nextDay} language="en" /></dl>)).not.toMatch(/s2-reading|s2-following-day/);
    // A manifest without the like-for-like figures (an earlier r4 bake, or cloud on the earlier date) gives no reading.
    const older: S2Crosscheck = { ...check, model_at_event_scene: { ...model, model_flood_km2_both_clear: undefined } };
    expect(observedLargerThanModel(older, viirsDay)).toBe(false);
    expect(bothObservationsText(older, viirsDay, "en")).toContain(`against the model's ${km(model.model_flood_km2_clear)} km². Each is counted in its own clear pixels.`);
    expect(observedLargerThanModel({ ...check, change: { ...check.change, new_water_km2: null } }, viirsDay)).toBe(false);
    const html = renderToStaticMarkup(<dl><Sentinel2Evidence check={smallS2} viirsDay={viirsDay} language="en" /></dl>);
    expect(html).not.toContain('data-testid="s2-reading"');
    expect(text(html)).not.toContain("consistent with the larger observed area");
    expect(text(html)).toContain(check.caveat);
    // VIIRS not larger than the model on that day: the same.
    const smallViirs = { ...viirsDay, viirs_flood_km2_clear: viirsDay.model_flood_km2_clear - 1 };
    expect(observedLargerThanModel(check, smallViirs)).toBe(false);
    expect(renderToStaticMarkup(<dl><Sentinel2Evidence check={check} viirsDay={smallViirs} language="en" /></dl>)).not.toContain('data-testid="s2-reading"');
    // Without a VIIRS map with clear sky for the day, only Sentinel-2 is named and judged.
    for (const missing of [null, { ...viirsDay, clear_km2: 0, viirs_flood_km2_clear: 0, model_flood_km2_clear: 0 }]) {
      const only = text(renderToStaticMarkup(<dl><Sentinel2Evidence check={check} viirsDay={missing} language="en" /></dl>));
      expect(only).toContain(`One observation on this day: Sentinel-2 (15 Sep 10:58 ICT) shows ${km(scenes.event.water_km2)} km² of water or saturated mud against the model's`);
      expect(only).not.toContain("Two observations");
      expect(only).toContain(READING);
    }
    expect(bothObservationsText(check, null, "th")).toContain("วันนี้มีการสังเกตการณ์หนึ่งแหล่ง");
  });

  it("adds the second observation to the VIIRS card on that day only", () => {
    const card = (s2: S2Crosscheck | null, language: "en" | "th") =>
      renderToStaticMarkup(<ViirsComparisonCard viirs={viirs} activeDate={viirsDay.date} showOnMap={false} onShowOnMap={noop} language={language} s2={s2} />);
    const withCheck = card(check, "en");
    expect(withCheck).toContain('data-testid="viirs-s2-note"');
    const plain = text(withCheck);
    expect(plain).toContain(`Second observation on 15 Sep: ${s2ObservedText(check, "en")} ${s2ModelText(check, "en")} ${READING} ${followingDayText(nextDay, "en")} ${NEXT_DAY_READING}`);
    expect(findWordingViolations(visibleText(withCheck), "ViirsComparisonCard with Sentinel-2")).toEqual([]);
    expect(card(null, "en")).not.toContain("viirs-s2-note");
    // The card applies the same condition as the evidence list: no "larger observed area" unless both are larger.
    const smallS2: S2Crosscheck = { ...check, model_at_event_scene: { ...model, model_flood_km2_both_clear: (check.change.new_water_km2 ?? 0) + 5 } };
    const smaller = text(card(smallS2, "en"));
    expect(smaller).toContain("Second observation on 15 Sep:");
    expect(smaller).not.toContain("The larger observed area is consistent with");
    expect(smaller).not.toContain("The next clear VIIRS map");
    expect(renderToStaticMarkup(<ViirsComparisonCard viirs={viirs} activeDate={viirsDay.date} showOnMap={false} onShowOnMap={noop} language="en" />)).toBe(card(null, "en"));
    const thai = text(card(check, "th"));
    expect(thai).toContain("การสังเกตการณ์แหล่งที่สองของวันที่ 15 ก.ย.");
    expect(thai).toContain("พื้นที่ที่สังเกตได้ซึ่งกว้างกว่าสอดคล้องกับ");
    expect(thai).toContain("แผนที่ VIIRS ที่ท้องฟ้าโปร่งถัดมา (16 ก.ย. 13:30 น. โดยประมาณ)");
    expect(findWordingViolations(visibleText(card(check, "th")), "ViirsComparisonCard with Sentinel-2 th")).toEqual([]);
  });

  it("describes the water check in the sources panel: index, rules, caveat, stricter readings, confidence and both acquisition times", () => {
    const html = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />);
    const item = text(html.slice(html.indexOf('data-testid="s2-source"')).split("</li>")[0]);
    for (const sentence of [check.product, check.attribution, check.index, check.water_rule, check.clear_rule, check.permanent_water_rule,
      check.comparison_rule, check.caveat, check.confidence_reason]) {
      expect(item, sentence).toContain(sentence);
    }
    expect(item).toContain("Water check (water or saturated mud):");
    expect(item).toContain("Confidence: low — ");
    expect(item).toContain(`${scenes.pre.source_timestamp} / ${scenes.event.source_timestamp}`);
    const strict = check.sensitivity.find((row) => row.id === "strict_clear")!;
    const tenth = check.sensitivity.find((row) => row.id === "threshold_0_1")!;
    const fifth = check.sensitivity.find((row) => row.id === "threshold_0_2")!;
    expect(s2SensitivityText(check, "en")).toBe(
      `Under stricter rules the 15 Sep area is ${km(strict.event_water_km2)} km² (only vegetation, bare ground and water classes count as clear); `
      + `${km(tenth.event_water_km2)} km² (MNDWI above 0.1); ${km(fifth.event_water_km2)} km² (MNDWI above 0.2).`);
    expect(item).toContain(s2SensitivityText(check, "en"));
    // A stricter rule never finds more than the main one.
    for (const row of [strict, tenth, fifth]) expect(row.event_water_km2!).toBeLessThanOrEqual(scenes.event.water_km2!);
    expect(s2SensitivityText({ ...check, sensitivity: [{ ...strict, id: "another_rule" }] }, "en")).toBe("");
    // The top-level lists carry the limitation and the assumption.
    const plain = text(html);
    expect(manifest.limitations.some((line) => line.startsWith("No ponding or storage after the river falls"))).toBe(true);
    expect(plain).toContain("No ponding or storage after the river falls: the terrain-only model dries every cell as soon as the assumed river level drops below it");
    expect(plain).toContain("The Sentinel-2 water check counts water or saturated mud (MNDWI above 0) on the clear pixels");
    const thaiHtml = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="th" offlineCopy={null} />);
    const thaiItem = text(thaiHtml.slice(thaiHtml.indexOf('data-testid="s2-source"')).split("</li>")[0]);
    expect(thaiItem).toContain("การตรวจน้ำ (น้ำหรือโคลนอิ่มน้ำ):");
    expect(thaiItem).toContain("ความเชื่อมั่น: ต่ำ — ");
    expect(thaiItem).toContain(s2SensitivityText(check, "th"));
    for (const sentence of [check.index, check.water_rule, check.clear_rule, check.permanent_water_rule, check.comparison_rule, check.caveat, check.confidence_reason]) {
      expect(thaiItem, sentence).not.toContain(sentence);
    }
    expect(text(thaiHtml)).toContain("ไม่จำลองน้ำขังหรือการกักเก็บน้ำหลังระดับแม่น้ำลดลง");
    // A manifest baked before the check has no such entry, and the panel still renders.
    const before = { ...manifest, s2_crosscheck: undefined };
    expect(renderToStaticMarkup(<SourcesPanel manifest={before} language="en" offlineCopy={null} />)).not.toContain("s2-source");
  });
});

describe("Mae Sai replay evidence envelope on the page (r4)", () => {
  const THAI = /[฀-๿]/;
  // The r3 shape a client may still hold in its offline copy (trimmed; see the fixture's own notes).
  const r3 = parseTimelineManifest((JSON.parse(readFileSync(resolve(import.meta.dirname, "../lib/__fixtures__/mae-sai-timeline-r3-shape.json"), "utf8")) as { manifest: unknown }).manifest);
  /** Visible text of the element that carries `testId`, up to the first closing `tag`. */
  const inside = (html: string, testId: string, tag: string) => text(html.slice(html.indexOf(">", html.indexOf(`data-testid="${testId}"`)) + 1).split(`</${tag}>`)[0]);

  it("says the replay is non-operational and when its data files were generated, in the how-to-read box", () => {
    const html = renderToStaticMarkup(<HowToRead manifest={manifest} language="en" />);
    const status = inside(html, "how-to-status", "li");
    expect(status).toContain("Status: non-operational. A historical reconstruction for planning and exercises; it gives no priority score and no action class.");
    expect(manifest.operational_status).toBe("non_operational");
    expect(manifest.generated_at_basis).toBe("declared");
    expect(status).toMatch(/Data files generated: \d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2} ICT\.$/);
    expect(html).toContain(`<time dateTime="${manifest.generated_at}">`);
    // The top-level source timestamp now reaches the last rain hour and the last VIIRS day.
    expect(text(html)).toContain(`Source data: ${manifest.source_timestamp}.`);
    expect(Date.parse(manifest.source_timestamp.split("/")[1])).toBeGreaterThanOrEqual(Date.parse(manifest.viirs_daily!.days.at(-1)!.nominal_local_time));
    const thai = text(renderToStaticMarkup(<HowToRead manifest={manifest} language="th" />));
    expect(thai).toContain("สถานะ: ไม่ใช้ในการปฏิบัติการ");
    expect(thai).toContain("ไม่ให้คะแนนลำดับความสำคัญและไม่กำหนดระดับการดำเนินการ");
    expect(thai).toMatch(/สร้างไฟล์ข้อมูลเมื่อ \d{1,2} \S+ 25\d{2} \(20\d{2}\) \d{2}:\d{2} น\./);
    // Before any data loads the status is still stated; only the generation time waits for the manifest.
    const empty = text(renderToStaticMarkup(<HowToRead manifest={null} language="en" />));
    expect(empty).toContain("Status: non-operational.");
    expect(empty).not.toContain("Data files generated");
  });

  it("labels a generation time that was not declared as the newest input date, and shows nothing without one", () => {
    const declared = text(renderToStaticMarkup(<GeneratedAt manifest={{ generated_at: "2026-10-01T16:10:00+07:00", generated_at_basis: "declared" }} language="en" />));
    expect(declared).toBe(" · Data files generated: 1 Oct 2026, 16:10 ICT");
    const newest = text(renderToStaticMarkup(<GeneratedAt manifest={{ generated_at: "2026-09-27T00:00:00Z", generated_at_basis: "newest_input_timestamp" }} language="en" />));
    expect(newest).toBe(" · Newest input dated: 27 Sep 2026, 07:00 ICT");
    const thai = text(renderToStaticMarkup(<GeneratedAt manifest={{ generated_at: "2026-09-27T00:00:00Z", generated_at_basis: "newest_input_timestamp" }} language="th" lead />));
    expect(thai).toBe(" ข้อมูลนำเข้าล่าสุดลงวันที่ 27 ก.ย. 2569 (2026) 07:00 น.");
    expect(renderToStaticMarkup(<GeneratedAt manifest={{}} language="en" />)).toBe("");
    expect(renderToStaticMarkup(<GeneratedAt manifest={{ generated_at: "soon" }} language="th" />)).toBe("");
  });

  it("lists a licence and its terms for every input in the sources panel, with product 4009 marked as not shown", () => {
    const html = renderToStaticMarkup(<LicencesByInput manifest={manifest} language="en" />);
    const plain = text(html);
    expect(plain).toContain("Licence per input");
    const inputs = manifest.publication_eligibility!.inputs;
    expect(inputs.length).toBeGreaterThanOrEqual(12);
    for (const input of inputs) {
      expect(plain, input.id).toContain(`${plainManifestText(input.name)} — ${input.licence.replace(/\.$/, "")}. `);
      expect(plain, input.id).toContain(plainManifestText(input.terms));
    }
    for (const licence of ["CC BY-NC", "ODbL 1.0", "CC BY 4.0", "CC BY-IGO", "No licence stated by the provider", "CC BY-SA 4.0", "Copernicus DEM licence", "Copernicus Sentinel data terms"]) {
      expect(plain).toContain(licence);
    }
    // Only product 4009 is listed without being shown; it comes last and says why.
    expect(html.match(/data-shown="false"/g)).toHaveLength(1);
    const last = text(html.slice(html.lastIndexOf("<li data-shown=")).split("</li>")[0]);
    expect(last).toContain("UNOSAT/GISTDA product 4009");
    expect(last).toContain("Not yet shown; rights record pending owner confirmation.");
    expect(html).toContain("<strong><span lang=\"en\">Not yet shown; rights record pending owner confirmation.</span></strong>");
    // An input that is not shown and gives no status still says so.
    const bare = { ...manifest, publication_eligibility: { ...manifest.publication_eligibility!, inputs: inputs.map((input) => ({ ...input, status: undefined })) } };
    expect(text(renderToStaticMarkup(<LicencesByInput manifest={bare} language="en" />))).toContain("Not shown on this page.");
    expect(text(renderToStaticMarkup(<LicencesByInput manifest={bare} language="th" />))).toContain("ยังไม่แสดงในหน้านี้");
    expect(plain).toContain(`Conditions of use: ${manifest.publication_eligibility!.scope}`);
    for (const condition of manifest.publication_eligibility!.conditions) expect(plain).toContain(condition);
    expect(plain).not.toMatch(/tha_ppp_2020|rights_basis_4009|docs\/|\.\./);
    expect(findWordingViolations(visibleText(html), "LicencesByInput")).toEqual([]);

    const thaiHtml = renderToStaticMarkup(<LicencesByInput manifest={manifest} language="th" />);
    const thai = text(thaiHtml);
    expect(thai).toContain("สัญญาอนุญาตของข้อมูลแต่ละชุด");
    expect(thai).toContain("ยังไม่แสดง รอเจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูล");
    expect(thai).toContain("เงื่อนไขการใช้");
    // Names and published licence names stay as published (marked English); every term and condition has a Thai
    // rendering, and so has the licence wording the project wrote itself.
    expect(thaiHtml).toContain('<span lang="en" data-licence="">CC BY-NC.</span>');
    expect(thaiHtml).toContain('<span lang="en" data-licence="">CC BY-SA 4.0.</span>');
    const published = /^(CC BY|ODbL)/;
    const written = inputs.map((input) => input.licence.replace(/\.$/, "")).filter((licence) => !published.test(licence));
    expect(written).toEqual(expect.arrayContaining(["Project summary text", "Cited figures with links; no data copied", "No licence stated by the provider",
      "Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)"]));
    for (const licence of written) {
      expect(thai, licence).not.toContain(licence);
      expect(html, licence).toContain(`<span lang="en" data-licence="">${licence.replaceAll("&", "&amp;")}.</span>`);
    }
    expect(thai).toContain("ข้อความสรุปของโครงการ");
    expect(thai).toContain("ผู้ให้บริการไม่ได้ระบุสัญญาอนุญาต");
    expect(thai).toContain("ตัวเลขที่อ้างอิงพร้อมลิงก์ ไม่ได้คัดลอกข้อมูล");
    // A Thai licence phrase takes no Latin full stop.
    expect(thaiHtml).toContain('<span lang="th" data-licence="">ข้อความสรุปของโครงการ</span>');
    for (const sentence of [...inputs.map((input) => input.terms), ...manifest.publication_eligibility!.conditions, manifest.publication_eligibility!.scope]) {
      expect(thai, sentence).not.toContain(plainManifestText(sentence));
    }
    expect(findWordingViolations(visibleText(thaiHtml), "LicencesByInput th")).toEqual([]);
  });

  it("states which external figures were used or known while the model was tuned", () => {
    const html = renderToStaticMarkup(<TuningDisclosure manifest={manifest} language="en" />);
    const plain = text(html);
    expect(plain).toContain("What was known when the model was tuned");
    expect(plain).toContain("Used for tuning: GISTDA's RADARSAT-2 figure for 10 Sep 18:15 (9.9 km² flooded in Mae Sai) was used on purpose to set the onset stage knot");
    expect(plain).toContain("Used for tuning: The Sentinel-1 pass of 16 Sep 06:16 ICT was used to re-tune the recession keyframes (best-fit stage 0.10 m)");
    expect(plain).toContain("Known during tuning: UNOSAT 3991 (about 70 km² over 13-19 Sep) was known while the stage keyframes were tuned");
    // VIIRS: only what the build history supports. The comparison and the last stage-knot edit are in one commit.
    expect(plain).toContain("Not used for tuning: The VIIRS daily comparison was not used for tuning. It was first computed in the change of 29 Sep 2026 (commit 129ff03)");
    expect(plain).toContain("The build history does not record which came first within that change, so the comparison is not presented as an independent check.");
    expect(plain).not.toContain("The VIIRS daily comparison was computed after the keyframes were final");
    expect(plain).toContain("Not used for tuning: The comparison with UNOSAT/GISTDA product 4009 was computed after the keyframes were final");
    // The Sentinel-2 water check entered the bake after the last keyframe change; the images themselves had been seen.
    expect(plain).toContain("Not used for tuning: The Sentinel-2 water check (MNDWI on the 5 Sep and 15 Sep scenes) was computed after the keyframes were final and was not used for tuning");
    expect(plain).toContain("they were seen while the keyframes were set, but no water area had been derived from them.");
    expect(html.match(/data-relation="used_for_tuning"/g)).toHaveLength(2);
    expect(html.match(/data-relation="known_during_tuning"/g)).toHaveLength(1);
    expect(html.match(/data-relation="computed_after_keyframes_final"/g)).toHaveLength(2);
    expect(html.match(/data-relation="not_used_for_tuning"/g)).toHaveLength(1);
    expect(plain).toContain(plainManifestText(manifest.exploratory_knowledge!.rule));
    expect(findWordingViolations(visibleText(html), "TuningDisclosure")).toEqual([]);
    // The disclosure and the radar label agree: both call the Sentinel-1 comparison calibration-informed.
    const radar = text(renderToStaticMarkup(<RadarCheck manifest={manifest} radarSpan="6 Sep → 16 Sep 06:16 ICT" language="en" />));
    expect(radar).toContain("calibration-informed, not an independent check");
    expect(plain).toContain("the radar size comparison is calibration-informed, not an independent check");
    const thai = text(renderToStaticMarkup(<TuningDisclosure manifest={manifest} language="th" />));
    expect(thai).toContain("สิ่งที่ทราบขณะปรับแบบจำลอง");
    expect(thai).toContain("ใช้ปรับแบบจำลอง:");
    expect(thai).toContain("ทราบขณะปรับแบบจำลอง:");
    expect(thai).toContain("ไม่ได้ใช้ปรับแบบจำลอง:");
    for (const item of manifest.exploratory_knowledge!.items) expect(thai, item.id).not.toContain(plainManifestText(item.statement));
  });

  it("puts the licences, the disclosure, the status and the generation time in the sources panel", () => {
    const html = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />);
    const plain = text(html);
    expect(html).toContain('data-testid="licences-by-input"');
    expect(html).toContain('data-testid="licence-conditions"');
    expect(html).toContain('data-testid="tuning-disclosure"');
    // Both elevation tiles and the residents grid are sources; the residents note sits on that line, once.
    expect(plain).toContain("Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100)");
    expect(plain).toContain("WorldPop Thailand 100 m population 2020, unconstrained top-down — CC BY 4.0. WorldPop (www.worldpop.org), University of Southampton. Modelled residential population, not a census count or the 2024 population.");
    expect(plain.split(manifest.population!.note)).toHaveLength(2);
    const footer = inside(html, "sources-footer", "p");
    expect(footer).toContain(`Source timestamp: ${manifest.source_timestamp}`);
    expect(footer).toContain(`${manifest.study_id} r4`);
    expect(footer).toContain("confidence: low · status: non-operational · Data files generated: ");
    expect(plain).toContain(manifest.source_timestamp_note!);
    const thai = text(renderToStaticMarkup(<SourcesPanel manifest={manifest} language="th" offlineCopy={null} />));
    expect(thai).toContain("สถานะ: ไม่ใช้ในการปฏิบัติการ");
    expect(thai).toContain("สร้างไฟล์ข้อมูลเมื่อ");
    expect(thai).not.toContain(manifest.source_timestamp_note!);
    expect(thai).toMatch(THAI);
  });

  it("still renders an r3-shaped manifest: its own sources, no licence table, no disclosure, no generation time", () => {
    expect(r3.revision).toBe("r3");
    const html = renderToStaticMarkup(<SourcesPanel manifest={r3} language="en" offlineCopy={null} />);
    const plain = text(html);
    for (const source of r3.sources) expect(plain).toContain(source.licence);
    // r3 lists the residents grid only in its population block; the panel still shows it, once.
    expect(r3.sources.some((source) => source.id === "worldpop")).toBe(false);
    expect(plain.split(`${plainManifestText(r3.population!.source)} — ${r3.population!.licence}.`)).toHaveLength(2);
    expect(html).not.toContain('data-testid="licences-by-input"');
    expect(html).not.toContain('data-testid="tuning-disclosure"');
    expect(html).not.toContain('data-testid="generated-at"');
    expect(renderToStaticMarkup(<LicencesByInput manifest={r3} language="en" />)).toBe("");
    expect(renderToStaticMarkup(<TuningDisclosure manifest={r3} language="th" />)).toBe("");
    // The status does not depend on the revision: the replay is non-operational either way.
    expect(plain).toContain("status: non-operational");
    const howTo = text(renderToStaticMarkup(<HowToRead manifest={r3} language="en" />));
    expect(howTo).toContain("Status: non-operational.");
    expect(howTo).not.toContain("Data files generated");
    // The radar comparison is labelled calibration-informed even when the manifest predates the label.
    expect(r3.s1_anchor.role).toBeUndefined();
    expect(text(renderToStaticMarkup(<RadarCheck manifest={r3} radarSpan="6 Sep → 16 Sep 06:16 ICT" language="en" />))).toContain("calibration-informed, not an independent check");
    expect(findWordingViolations(visibleText(html), "SourcesPanel r3")).toEqual([]);
  });
});
