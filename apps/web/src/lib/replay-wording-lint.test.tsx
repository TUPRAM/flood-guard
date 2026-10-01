/**
 * Wording lint for the Mae Sai replay (web side).
 *
 * Scans three bodies of text with the shared rules in `replay-wording-rules.json`:
 *   1. every string in the replay's source files (literals, templates and JSX text, in English and Thai), which also
 *      covers the captions drawn into the exported PNG and video;
 *   2. every text value of the served manifest;
 *   3. the reader-visible text of the main panels rendered with that manifest, in both languages.
 * It must pass on the current text and fail on one seeded bad string per rule. The Python twin is
 * `tests/test_replay_wording_lint.py`.
 */

import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { describe, expect, it } from "vitest";

import { ExternalChecks, PeopleInWaterCard, ReportedSheltersCard, ShelterPlanCard } from "@/components/mae-sai-evacuation-panels";
import {
  HowToRead,
  Hydrograph,
  ImpactCard,
  LowConfidenceEvidence,
  MaeSaiFloodTimeline,
  RadarCheck,
  RouteCutsCard,
  SourcesPanel,
  TimelineLegend,
  WetFacilitiesCard,
} from "@/components/mae-sai-flood-timeline";
import { RainChart, ViirsComparisonCard } from "@/components/mae-sai-observed-panels";
import { ReplayExportPanel } from "@/components/mae-sai-replay-export";
import {
  districtStats,
  hourlyStages,
  roadCut,
  roadCutGroups,
  tFromDate,
  TIMELINE_MANIFEST_URL,
  type FacilityProps,
  type GeoCollection,
  type Language,
  type LineGeometry,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import {
  describeWordingFindings,
  findWordingViolations,
  normaliseWording,
  REPLAY_WORDING_RULES,
  visibleText,
  type WordingFinding,
} from "./replay-wording-lint";

const webRoot = resolve(import.meta.dirname, "../..");
const publicRoot = resolve(webRoot, "public");
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(resolve(publicRoot, href.replace(/^\//, "")), "utf8")) as T;
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const ruleIds = REPLAY_WORDING_RULES.rules.map((rule) => rule.id);
const idsOf = (findings: WordingFinding[]) => [...new Set(findings.map((finding) => finding.rule))].sort();

// --- 1. Strings in the replay's source files ----------------------------------------------------------

/** Replay source files: the `mae-sai-*` components, the `flood-timeline*` modules and the route's page. */
function replaySourceFiles(): string[] {
  const list = (folder: string, pattern: RegExp) => readdirSync(resolve(webRoot, folder))
    .filter((name) => pattern.test(name) && !/\.test\.tsx?$/.test(name))
    .map((name) => `${folder}/${name}`);
  return [
    ...list("src/components", /^mae-sai-.*\.tsx$/),
    ...list("src/lib", /^flood-timeline.*\.ts$/),
    "src/app/studio/cases/mae-sai-2024/page.tsx",
  ].sort();
}

/**
 * Every string a source file can put in front of a reader: string literals, template literals (expressions shown
 * as "{…}") and JSX text. Comments, identifiers, import paths, type-level literals and regular expressions are code,
 * not copy, and are left out.
 */
function sourceStrings(code: string, fileName: string): string[] {
  const file = ts.createSourceFile(fileName, code, ts.ScriptTarget.Latest, true, fileName.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: string[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node) || ts.isLiteralTypeNode(node) || ts.isRegularExpressionLiteral(node)) return;
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) out.push(node.text);
    else if (ts.isTemplateExpression(node)) out.push([node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join(" {…} "));
    else if (ts.isJsxText(node) && node.text.trim()) out.push(node.text);
    ts.forEachChild(node, visit);
  };
  visit(file);
  return out;
}

// --- 2. Manifest text -----------------------------------------------------------------------------------

const NON_TEXT_KEYS = new Set(["href", "url", "urls", "source_url", "sha256", "scene", "source_file"]);

/** Every string value of a JSON document with its path (keys, addresses, hashes and file names are not copy). */
function jsonStrings(value: unknown, path = "$"): { path: string; text: string }[] {
  if (typeof value === "string") return [{ path, text: value }];
  if (Array.isArray(value)) return value.flatMap((item, index) => jsonStrings(item, `${path}[${index}]`));
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) => (NON_TEXT_KEYS.has(key) ? [] : jsonStrings(item, `${path}.${key}`)));
  }
  return [];
}

// --- 3. Rendered panels -----------------------------------------------------------------------------------

function renderedPanels(language: Language): { name: string; html: string }[] {
  const roadCollection = readJson<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href);
  const roads = roadCollection.features.map((feature) => feature.properties);
  const facilities = readJson<GeoCollection<unknown, FacilityProps>>(manifest.vectors.facilities.href).features.map((feature) => feature.properties);
  const tambons = readJson<GeoCollection<unknown, TambonProps>>(manifest.vectors.tambons.href).features.map((feature) => feature.properties);
  const names = Object.fromEntries(tambons.map((tambon) => [tambon.id, tambon]));
  const peak = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
  const stats = districtStats(manifest, peak, roads, facilities);
  const derived = { facilityProps: facilities, names, tambonScale: Math.max(...manifest.days.flatMap((day) => Object.values(day.stats.tambon_flooded_km2)), 0.001) };
  const observations = manifest.observations.map((observation) => ({ observation, at: tFromDate(observation.local) }));
  const stages = hourlyStages(manifest.stage_anchors);
  const cuts = roads.map((road) => roadCut(road.m ? road.h : null, stages, manifest.impassable_depth_m, road.k ?? 1));
  const groups = roadCutGroups(roadCollection.features, cuts, 10);
  // An empty list would lint only the card's empty state, not the route wording.
  if (groups.length === 0) throw new Error("The replay manifest has no modelled road cuts to lint");
  const viirs = manifest.viirs_daily!;
  const noop = () => undefined;
  const panel = (name: string, node: React.ReactElement) => ({ name: `${name} (${language})`, html: renderToStaticMarkup(node) });
  return [
    panel("HowToRead", <HowToRead manifest={manifest} language={language} />),
    panel("ImpactCard", <ImpactCard manifest={manifest} stats={stats} derived={derived} language={language} />),
    panel("TimelineLegend", <TimelineLegend language={language} unmodelledRoads unmodelledFacilities />),
    panel("TimelineLegend hours", <TimelineLegend language={language} unmodelledRoads unmodelledFacilities={false} roadMode="hours" />),
    panel("RadarCheck", <RadarCheck manifest={manifest} radarSpan="6 Sep → 16 Sep 06:16 ICT" language={language} />),
    panel("WetFacilitiesCard", <WetFacilitiesCard facilities={facilities} stage={peak} language={language} />),
    panel("Hydrograph", <Hydrograph manifest={manifest} time={3.5} stage={peak} observations={observations} language={language} />),
    panel("RouteCutsCard", <RouteCutsCard groups={groups} names={names} language={language} focused={null} onFocus={noop} onReset={noop} />),
    panel("ReplayExportPanel", <ReplayExportPanel source={null} time={3.5} language={language} waterOpacity={0.85} />),
    panel("ViirsComparisonCard", <ViirsComparisonCard viirs={viirs} activeDate={viirs.days[0].date} showOnMap={false} onShowOnMap={noop} language={language} />),
    panel("RainChart", <RainChart rainfall={manifest.rainfall!} time={3.5} dayLabels={manifest.days.map((day) => String(Number(day.date.slice(8))))} language={language} />),
    panel("SourcesPanel", <SourcesPanel manifest={manifest} language={language} offlineCopy={null} />),
    panel("LowConfidenceEvidence", <dl><LowConfidenceEvidence hand={manifest.hand} language={language} /></dl>),
    panel("PeopleInWaterCard", <PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language={language} />),
    panel("ExternalChecks", <ExternalChecks manifest={manifest} language={language} />),
    panel("ShelterPlanCard", <ShelterPlanCard shelters={manifest.shelters!} k={manifest.shelters!.knee_k} onPlanK={noop} language={language} onShowCandidate={noop} />),
    panel("ReportedSheltersCard", <ReportedSheltersCard shelters={manifest.shelters!} language={language} onShowReported={noop} />),
  ];
}

function corpus(): { source: string; text: string }[] {
  const sources = replaySourceFiles().flatMap((file) =>
    sourceStrings(readFileSync(resolve(webRoot, file), "utf8"), file).map((text) => ({ source: file, text })));
  const manifestText = jsonStrings(manifest).map(({ path, text }) => ({ source: `timeline.json ${path}`, text }));
  const rendered = [
    { name: "MaeSaiFloodTimeline shell (en)", html: renderToStaticMarkup(<MaeSaiFloodTimeline />) },
    ...renderedPanels("en"),
    ...renderedPanels("th"),
  ].map(({ name, html }) => ({ source: name, text: visibleText(html) }));
  return [...sources, ...manifestText, ...rendered];
}

const lint = (items: { source: string; text: string }[]) => items.flatMap(({ source, text }) => findWordingViolations(text, source));

describe("Replay wording rules (shared with Python)", () => {
  it("cover the six banned groups of the replay roadmap", () => {
    expect(ruleIds).toEqual([
      "real_time", "live", "forecast", "warning", // affirmative real-time, live, forecast or warning
      "validation_as_agreement", // validated, validation or accuracy used for agreement
      "precision_recall", // precision or recall for product 4009
      "september_extent", // "September extent", "GISTDA's map"
      "return_period", // 25-year, 100-year
      "road_schedule", // schedule or closure plan for modelled roads
    ]);
    expect(new Set(REPLAY_WORDING_RULES.allow.map((item) => item.id)).size).toBe(REPLAY_WORDING_RULES.allow.length);
  });

  it("uses patterns that mean the same in JavaScript and Python", () => {
    for (const item of [...REPLAY_WORDING_RULES.rules, ...REPLAY_WORDING_RULES.allow]) {
      // \b, \w, \d and \s differ between the engines once Thai text is involved.
      expect(item.pattern, item.id).not.toMatch(/\\[bBwWdDsS]/);
      expect(() => new RegExp(item.pattern, "giu"), item.id).not.toThrow();
    }
  });

  it("flags every seeded bad string with its own rule", () => {
    for (const rule of REPLAY_WORDING_RULES.rules) {
      expect(rule.bad.length, rule.id).toBeGreaterThan(0);
      for (const bad of rule.bad) expect(idsOf(findWordingViolations(bad)), `${rule.id}: ${bad}`).toContain(rule.id);
    }
  });

  it("lets every allowlisted negation through", () => {
    for (const item of REPLAY_WORDING_RULES.allow) {
      expect(item.ok.length, item.id).toBeGreaterThan(0);
      for (const ok of item.ok) expect(describeWordingFindings(findWordingViolations(ok)), `${item.id}: ${ok}`).toBe("");
    }
  });

  it("does not let a negation excuse an affirmative claim in the same text", () => {
    for (const { text, rules } of REPLAY_WORDING_RULES.mixed) expect(idsOf(findWordingViolations(text)), text).toEqual([...rules].sort());
  });

  it("reads text the way the Python linter does: no web addresses, plain apostrophes and hyphens, single spaces", () => {
    expect(normaliseWording("GISTDA’s  map\n(see https://gistda.or.th/live/forecast) real‑time")).toBe("GISTDA's map (see ) real-time");
    expect(idsOf(findWordingViolations("GISTDA’s map, real‑time"))).toEqual(["real_time", "september_extent"]);
  });
});

describe("Replay wording lint: current text", () => {
  const items = corpus();

  it("scans the replay's source strings, the manifest text and the rendered panels in English and Thai", () => {
    const files = replaySourceFiles();
    for (const file of [
      "src/components/mae-sai-flood-timeline.tsx", "src/components/mae-sai-evacuation-panels.tsx", "src/components/mae-sai-observed-panels.tsx",
      "src/components/mae-sai-replay-export.tsx", "src/lib/flood-timeline.ts", "src/lib/flood-timeline-copy.ts",
      "src/lib/flood-timeline-evacuation.ts", "src/lib/flood-timeline-link.ts", "src/app/studio/cases/mae-sai-2024/page.tsx",
    ]) expect(files).toContain(file);
    const sources = new Set(items.map((item) => item.source));
    for (const file of files) expect(sources.has(file), file).toBe(true);
    expect(items.filter((item) => item.source.startsWith("timeline.json")).length).toBeGreaterThan(100);
    expect(items.filter((item) => / \((en|th)\)$/.test(item.source)).length).toBe(35);
    // The corpus really holds the standing disclaimer in both languages, export caption included.
    const all = items.map((item) => item.text).join("\n");
    expect(all).toContain("not real-time, not an official warning");
    expect(all).toContain("ไม่ใช่ข้อมูลเรียลไทม์หรือคำเตือนทางการ");
    expect(all).toContain("Not a real-time product or an official warning");
    expect(all).toMatch(/[฀-๿]/);
  });

  it("finds no banned wording in today's replay text", () => {
    expect(describeWordingFindings(lint(items))).toBe("");
  });

  it("fails on one seeded bad string per rule, wherever it is planted", () => {
    const source = items.find((item) => item.source === "src/components/mae-sai-replay-export.tsx")!;
    const manifestItem = items.find((item) => item.source.startsWith("timeline.json $.limitations"))!;
    const rendered = items.find((item) => item.source === "SourcesPanel (th)")!;
    for (const rule of REPLAY_WORDING_RULES.rules) {
      for (const target of [source, manifestItem, rendered]) {
        const seeded = items.map((item) => (item === target ? { ...item, text: `${item.text} ${rule.bad[0]}` } : item));
        const findings = lint(seeded);
        expect(idsOf(findings), `${rule.id} planted in ${target.source}`).toContain(rule.id);
        expect(findings.every((finding) => finding.source === target.source), rule.id).toBe(true);
      }
    }
  });
});

describe("Replay wording lint: what counts as text in a source file", () => {
  it("reads literals, templates and JSX text, and skips comments, imports, type literals and regular expressions", () => {
    const code = [
      'import { live } from "./live-forecast";',
      "// A live preview while it records.",
      "/** Warning shown when the capacity is unknown. */",
      'type Mode = "live" | "replay";',
      "const pattern = /forecast|warning/;",
      'const label = t("Flood forecast", "พยากรณ์น้ำท่วม");',
      "const caption = `Stage ${stage} m · live`;",
      "export const Card = () => <p title=\"Accuracy\">Road closure schedule</p>;",
    ].join("\n");
    const strings = sourceStrings(code, "seed.tsx");
    expect(strings).toEqual(["Flood forecast", "พยากรณ์น้ำท่วม", "Stage  {…}  m · live", "Accuracy", "Road closure schedule"]);
    expect(idsOf(strings.flatMap((text) => findWordingViolations(text, "seed.tsx")))).toEqual(["forecast", "live", "road_schedule", "validation_as_agreement"]);
  });

  it("reads aria labels, titles and alternative text of rendered markup as visible text", () => {
    const html = '<section aria-label="Live map"><img alt="Forecast chart" src="x.png"/><p class="warning" data-kind="live">Stage 3.5&nbsp;m</p><style>.live{}</style></section>';
    const plain = visibleText(html);
    expect(plain).toContain("Live map");
    expect(plain).toContain("Forecast chart");
    expect(plain).not.toContain("x.png");
    expect(idsOf(findWordingViolations(plain))).toEqual(["forecast", "live"]); // Class names and data attributes are not copy.
  });
});
