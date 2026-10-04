/**
 * Wording lint for the Mae Sai replay (web side).
 *
 * Scans three bodies of text with the shared rules in `replay-wording-rules.json`:
 *   1. every string in the replay's source files (literals, templates and JSX text, in English and Thai), which also
 *      covers the captions drawn into the exported PNG and video, and the files of the Command exercise replay
 *      (`mae-sai-command-*`, `mae-sai-map-kit`, `flood-timeline-command*` and the page of its route);
 *   2. every text value of the served manifest;
 *   3. the reader-visible text of the main panels rendered with that manifest, in both languages, the lines the
 *      Command exercise copy builds from the replay data, and the panels of the Command exercise page as rendered,
 *      in both languages: the subdistrict table, the inspector and the find-place box among them, with the plan group
 *      of the table rendered once on the invented units of the planning overlay fixture.
 * It must pass on the current text and fail on one seeded bad string per rule. The Python twin is
 * `tests/test_replay_wording_lint.py`.
 */

import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { describe, expect, it } from "vitest";

import {
  CommandBanner,
  CommandCredits,
  CommandHelpSheet,
  CommandInfoBody,
  CommandLegend,
  CommandNav,
  CommandToolRail,
  CommandViewPopover,
} from "@/components/mae-sai-command-chrome";
import { MaeSaiCommandExercise } from "@/components/mae-sai-command-exercise";
import { MaeSaiCommandFind } from "@/components/mae-sai-command-find";
import { CommandCardChip, CommandCaseCard, CommandKnownPlaceholder, CommandTambonDetailBody, MaeSaiCommandInspector } from "@/components/mae-sai-command-inspector";
import { CommandQueueTable, MaeSaiCommandQueue } from "@/components/mae-sai-command-queue";
import { MaeSaiCommandSituation } from "@/components/mae-sai-command-situation";
import { MaeSaiCommandTimebar } from "@/components/mae-sai-command-timebar";
import { AccessCard, ExternalChecks, PeopleInWaterCard, ReportedSheltersCard, ShelterPlanCard } from "@/components/mae-sai-evacuation-panels";
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
import { RainChart, Sentinel2Evidence, ViirsComparisonCard } from "@/components/mae-sai-observed-panels";
import { ReplayExportPanel } from "@/components/mae-sai-replay-export";
import { ReportedDepthsSources } from "@/components/mae-sai-reported-depths";
import { SeasonEnvelopeCaption, SeasonEnvelopeChip, SeasonEnvelopeLegend, type SeasonEnvelopeState } from "@/components/mae-sai-season-envelope";
import {
  districtStats,
  formatHourStamp,
  hourlyStages,
  roadCut,
  roadCutGroups,
  tFromDate,
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type Language,
  type LineGeometry,
  type Localized,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import fixtureOverlay from "./__fixtures__/planning-assessment-overlay.fixture.json";
import { buildCommandModel, changeSinceHourBefore, COMMAND_SHELTER_SETS, districtFiguresAt, tambonOrderByHour, tambonRowsAt, type CommandShelterSet, type CommandTambonRow } from "./flood-timeline-command";
import {
  COMMAND_BANNER,
  COMMAND_CLASS_NAMES,
  COMMAND_CLOCK,
  COMMAND_DRAWER,
  COMMAND_FIGURES,
  COMMAND_FIND,
  COMMAND_FIND_KIND,
  COMMAND_INSPECTOR,
  COMMAND_LANE_ORDER,
  COMMAND_TABLE,
  commandBannerLine,
  commandBaseText,
  commandCaseLane,
  commandCaseTitle,
  commandChangeLine,
  commandChipLabel,
  commandClassLine,
  commandDataLine,
  commandDrawerHeading,
  commandFigureCells,
  commandFindCount,
  commandFindKindText,
  commandHourOf,
  commandHourShort,
  commandLaneMeaning,
  commandLaneTag,
  commandLifeAtRisk,
  commandMoment,
  commandMomentShort,
  commandNoReachNote,
  commandOpenItems,
  commandPhaseLine,
  commandPlaceRecordLine,
  commandPlanPositionLabel,
  commandRecordCount,
  commandRowChange,
  commandSetLabel,
  commandSetMeaning,
  commandToleranceText,
  commandUnlocatedRecords,
} from "./flood-timeline-command-copy";
import { commandDayChips, commandEventStops, commandPhaseSpans } from "./flood-timeline-command-replay";
import {
  buildCommandFindIndex,
  COMMAND_PLANNING_CASES,
  commandTableRows,
  lostAccessScale,
  parsePeakSummary,
  placeRecordsOfTambons,
  planningCells,
  planningFacts,
  tambonDetailAt,
  tambonRowsBefore,
  type CommandPlanningCell,
} from "./flood-timeline-command-table";
import { parseSeasonEnvelopeDocument, shippableEnvelope } from "./flood-timeline-envelope";
import { reportedDepthPopup, shippableReportedDepths } from "./flood-timeline-reported-depths";
import {
  accessLostSeries,
  accessSnapshot,
  floodedHomeMask,
  parseAccessNodes,
  planSetId,
  REPORTED_SET_ID,
  scopeTotals,
  shelterSetComparison,
  summarizeAccessSets,
  tambonResidents,
} from "./flood-timeline-evacuation";
import { parsePlanningAssessmentOverlay } from "./planning-assessment-overlay";
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
// The season envelope (UNOSAT and GISTDA product 4009) as the page holds it once its files have loaded.
const envelopeBlock = shippableEnvelope(manifest)!;
const envelopeDocument = parseSeasonEnvelopeDocument(readJson<unknown>(envelopeBlock.files.statistics.href), envelopeBlock);
const envelopeReady: SeasonEnvelopeState = { status: "ready", block: envelopeBlock, document: envelopeDocument, cells: new Uint32Array(0) };
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
    // The route of the Command exercise replay: its title and description are replay text too.
    "src/app/command/exercise/page.tsx",
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
  // The access card with its side-by-side shelter-set comparison, as the page builds it from the node file.
  const access = manifest.access!;
  const shelters = manifest.shelters!;
  const nodes = parseAccessNodes(new Uint8Array(readFileSync(resolve(publicRoot, access.nodes.href.replace(/^\//, "")))), access);
  const mask = floodedHomeMask(nodes, shelters.method.peak_stage_m, manifest.hand.step_m, manifest.hand.channel_code, manifest.hand.never_code);
  const scopes = {
    all: { summaries: summarizeAccessSets(nodes, access), totals: scopeTotals(nodes) },
    flooded: { summaries: summarizeAccessSets(nodes, access, mask), totals: scopeTotals(nodes, mask) },
  };
  const bothScopes = (setId: string, stage: number) => {
    const index = access.sets.indexOf(setId);
    return {
      all: shelterSetComparison(scopes.all.summaries[index], scopes.all.totals, stage, stages, access.levels),
      flooded: shelterSetComparison(scopes.flooded.summaries[index], scopes.flooded.totals, stage, stages, access.levels),
    };
  };
  const accessCard = (set: "reported" | "plan", stage: number, scope: "flooded" | "all" = "flooded") => {
    const summary = scopes[scope].summaries[access.sets.indexOf(set === "reported" ? REPORTED_SET_ID : planSetId(shelters.knee_k))];
    return (
      <AccessCard access={access} shelters={shelters} snapshot={accessSnapshot(summary, stage, access.levels)}
        series={accessLostSeries(summary, stages, access.levels)} time={3.5} names={names}
        tambonTotals={tambonResidents(nodes, access.tambons.length, scope === "flooded" ? mask : null)} shelterSet={set} planK={shelters.knee_k}
        onShelterSet={noop} onPlanK={noop} showCutoff={false} onShowCutoff={noop} scope={scope} onScope={noop}
        scopeTotals={scopes[scope].totals} allResidents={scopes.all.totals.population} floodedResidents={scopes.flooded.totals.population}
        comparison={{ reported: bothScopes(REPORTED_SET_ID, stage), plan: bothScopes(planSetId(shelters.knee_k), stage) }}
        language={language} status="ready" />
    );
  };
  return [
    panel("AccessCard reported, peak", accessCard("reported", peak)),
    panel("AccessCard plan, peak", accessCard("plan", peak)),
    panel("AccessCard plan, before the flood", accessCard("plan", 0)),
    // All residents at road nodes: the views where the Evacuation Equity Gap states a ratio, or that nobody has lost access.
    panel("AccessCard reported, all residents, peak", accessCard("reported", peak, "all")),
    panel("AccessCard plan, all residents, peak", accessCard("plan", peak, "all")),
    panel("AccessCard plan, all residents, before the flood", accessCard("plan", 0, "all")),
    panel("HowToRead", <HowToRead manifest={manifest} language={language} />),
    panel("ImpactCard", <ImpactCard manifest={manifest} stats={stats} derived={derived} language={language} />),
    panel("TimelineLegend", <TimelineLegend language={language} unmodelledRoads unmodelledFacilities />),
    panel("TimelineLegend hours", <TimelineLegend language={language} unmodelledRoads unmodelledFacilities={false} roadMode="hours" />),
    // The season envelope (product 4009, a scenario layer): its chip, caption and legend entry while it is visible, its
    // comparison as the third group of the checks, its entry in the Sources panel and the export panel with its credit.
    panel("TimelineLegend with the season envelope", <TimelineLegend language={language} unmodelledRoads unmodelledFacilities envelope />),
    panel("SeasonEnvelopeChip", <SeasonEnvelopeChip envelope={envelopeBlock} language={language} />),
    panel("SeasonEnvelopeCaption", <SeasonEnvelopeCaption envelope={envelopeBlock} language={language} />),
    panel("SeasonEnvelopeLegend", <SeasonEnvelopeLegend language={language} />),
    panel("ExternalChecks with the season envelope", <ExternalChecks manifest={manifest} language={language} envelope={envelopeReady} names={names} />),
    panel("ExternalChecks while the season envelope loads", <ExternalChecks manifest={manifest} language={language} envelope={{ status: "loading", block: envelopeBlock }} names={names} />),
    panel("ExternalChecks without the season envelope's files", <ExternalChecks manifest={manifest} language={language} envelope={{ status: "error", block: envelopeBlock }} names={names} />),
    panel("SourcesPanel with the season envelope", <SourcesPanel manifest={manifest} language={language} offlineCopy={null} envelope={envelopeReady} />),
    panel("SourcesPanel with the season envelope's statistics and without its raster", <SourcesPanel manifest={manifest} language={language} offlineCopy={null} envelope={{ status: "error", block: envelopeBlock, document: envelopeDocument }} />),
    panel("ReplayExportPanel with the season envelope", <ReplayExportPanel source={null} time={3.5} language={language} waterOpacity={0.85}
      envelope={{ cells: new Uint32Array(0), credit: envelopeBlock.credit, licence: envelopeBlock.licence, licence_url: envelopeBlock.licence_url }} />),
    panel("RadarCheck", <RadarCheck manifest={manifest} radarSpan="6 Sep → 16 Sep 06:16 ICT" language={language} />),
    panel("WetFacilitiesCard", <WetFacilitiesCard facilities={facilities} stage={peak} language={language} />),
    panel("Hydrograph", <Hydrograph manifest={manifest} time={3.5} stage={peak} observations={observations} language={language} />),
    panel("RouteCutsCard", <RouteCutsCard groups={groups} names={names} language={language} focused={null} onFocus={noop} onReset={noop} />),
    panel("ReplayExportPanel", <ReplayExportPanel source={null} time={3.5} language={language} waterOpacity={0.85} />),
    panel("ViirsComparisonCard", <ViirsComparisonCard viirs={viirs} activeDate={viirs.days[0].date} showOnMap={false} onShowOnMap={noop} language={language} />),
    // 15 Sep: the Sentinel-2 water check beside VIIRS, in the evidence list and on the VIIRS card.
    panel("Sentinel2Evidence", <dl><Sentinel2Evidence check={manifest.s2_crosscheck!} viirsDay={viirs.days.find((day) => day.date === "2024-09-15") ?? null} language={language} /></dl>),
    panel("ViirsComparisonCard on 15 Sep", <ViirsComparisonCard viirs={viirs} activeDate="2024-09-15" showOnMap={false} onShowOnMap={noop} language={language} s2={manifest.s2_crosscheck!} />),
    panel("RainChart", <RainChart rainfall={manifest.rainfall!} time={3.5} dayLabels={manifest.days.map((day) => String(Number(day.date.slice(8))))} language={language} />),
    panel("SourcesPanel", <SourcesPanel manifest={manifest} language={language} offlineCopy={null} />),
    panel("LowConfidenceEvidence", <dl><LowConfidenceEvidence hand={manifest.hand} language={language} /></dl>),
    panel("PeopleInWaterCard", <PeopleInWaterCard population={manifest.population!} stats={stats} names={names} scale={1} language={language} />),
    panel("ExternalChecks", <ExternalChecks manifest={manifest} language={language} />),
    panel("ShelterPlanCard", <ShelterPlanCard shelters={manifest.shelters!} k={manifest.shelters!.knee_k} onPlanK={noop} language={language} onShowCandidate={noop} />),
    panel("ReportedSheltersCard", <ReportedSheltersCard shelters={manifest.shelters!} language={language} onShowReported={noop} />),
    // Reported depths (news, not surveyed): the Sources entry with its counts table, and the legend entry of the layer.
    panel("ReportedDepthsSources", <ReportedDepthsSources block={shippableReportedDepths(manifest)!} language={language} />),
    panel("TimelineLegend with reported depths", <TimelineLegend language={language} unmodelledRoads unmodelledFacilities reportedDepths />),
  ];
}

// --- 4. The Command exercise copy as the page builds it ------------------------------------------------------

/**
 * Every line of the Command exercise copy in one language: each `{ en, th }` entry, and the lines its functions build
 * from the served replay data (the banner, the clock, the figures of several replay hours for both shelter sets, what
 * changed since the hour before, the lane tags and the drawer's headings). Joined lines are linted as built, so two
 * clean parts cannot join into a banned claim.
 */
let commandModelCache: ReturnType<typeof buildCommandModel> | null = null;
/** The model of the Command exercise page, built once from the served replay files. */
function commandModel(): ReturnType<typeof buildCommandModel> {
  const access = manifest.access!;
  commandModelCache ??= buildCommandModel({
    manifest,
    roads: readJson<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href).features,
    tambons: readJson<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href).features,
    nodes: parseAccessNodes(new Uint8Array(readFileSync(resolve(publicRoot, access.nodes.href.replace(/^\//, "")))), access),
  });
  return commandModelCache;
}

function commandCopyLines(language: Language): string[] {
  const model = commandModel();
  const blocks: Record<string, Localized>[] = [COMMAND_BANNER, COMMAND_CLOCK, COMMAND_FIGURES, COMMAND_DRAWER, COMMAND_TABLE, COMMAND_INSPECTOR, COMMAND_FIND, COMMAND_FIND_KIND, COMMAND_CLASS_NAMES];
  const letters = ["A", "B", "C", "D", "E"] as const;
  const headlines = ["not_evaluated", "headline_eligible", "unstable_verify"] as const;
  const hours = [0, 36, 44, 45, 60, 84, 85, 100, 153, 200, 264];
  const depthCounts = manifest.reported_depths!.counts.all;
  return [
    ...blocks.flatMap((block) => Object.values(block).map((text) => text[language])),
    ...COMMAND_LANE_ORDER.flatMap((lane) => [commandLaneTag(lane, language), commandLaneMeaning(lane, language)]),
    commandBannerLine(language),
    ...manifest.phases.map((phase) => commandPhaseLine(phase.label, model.stages[84], language)),
    ...hours.flatMap((hour) => [
      `${commandMoment(hour, language)} · ${commandHourOf(hour, language)}`,
      `${commandMomentShort(hour, language)} · ${commandHourShort(hour, language)}`,
      ...COMMAND_SHELTER_SETS.flatMap((set) => {
        const change = changeSinceHourBefore(model, hour, set);
        const cells = commandFigureCells(districtFiguresAt(model, hour, set), language);
        return [
          ...cells.map((cell) => [cell.value, cell.caption, ...(cell.sub ? [cell.sub] : []), cell.meaning].join(" · ")),
          commandChangeLine(change, change.sinceHour === null ? "" : formatHourStamp(change.sinceHour, language), language, 9).text,
        ];
      }),
    ]),
    commandBaseText(model.sets.reported.withinReachBefore, language),
    commandOpenItems(3, language),
    commandLifeAtRisk(1, language),
    commandPlaceRecordLine({ located: model.placeRecords.located, consistent: depthCounts.consistent, wet: depthCounts.model_wet, dry: depthCounts.model_dry }, language),
    commandDrawerHeading("assumptions", manifest.assumptions.length, language),
    commandDrawerHeading("limits", manifest.limitations.length, language),
    commandDrawerHeading("sources", manifest.sources.length, language),
    commandDataLine(manifest.revision, "3 Oct 2026", "3-19 Sep 2024", language),
    // The table, the inspector and the find-place box: the lines their functions build, joined as the page joins them.
    ...COMMAND_SHELTER_SETS.flatMap((set) => [commandSetLabel(set, 12, language), commandSetMeaning(set, 12, language), commandNoReachNote(set, language)]),
    ...COMMAND_PLANNING_CASES.flatMap((planningCase) => [
      commandCaseTitle(planningCase, language),
      commandCaseLane(planningCase, language),
      commandPlanPositionLabel(planningCase, language),
      commandChipLabel(planningCase, null, language),
      commandChipLabel(planningCase, { letter: null, headline: "not_evaluated" }, language),
      ...letters.flatMap((letter) => headlines.map((headline) => commandChipLabel(planningCase, { letter, headline }, language))),
    ]),
    ...letters.map((letter) => commandClassLine(letter, language)),
    ...[0, 1, 9].map((records) => commandRecordCount(records, language)),
    ...[1, 9].map((records) => commandUnlocatedRecords(records, language)),
    ...[{ text: "+~100", direction: 1 as const }, { text: "−<10", direction: -1 as const }, { text: "0", direction: 0 as const }].map((change) => commandRowChange(change, language)),
    ...[1, 3].map((names) => commandFindCount(names, language)),
    ...(["tambon", "shelter", "command_centre", "place_record", "facility", "road"] as const).map((kind) => commandFindKindText({ kind, facilityType: "school", records: 2 }, language)),
    commandToleranceText(150, language),
  ];
}

// --- 5. The panels of the Command exercise page as rendered -------------------------------------------------

/**
 * The panels of the Command exercise page in one language, rendered with the served replay data: the banner, the clock
 * and figures at the peak and in the receding phase (with the model-limit chip) and as the one line of focus mode,
 * the time dock, the information drawer, the help sheet, the navigation with its menu, the tool rail, the view
 * popover, the open legend with every entry and the map credits; then the subdistrict table at the peak and in the
 * receding phase, with both shelter sets and with its order held, its card as it waits, in focus mode and on a tablet,
 * the inspector of every subdistrict, the right card and its chip, and the find-place box with and without results.
 * The plan group with classes is rendered on the invented units of the planning overlay fixture: once as the table, and
 * as one case card per invented class.
 */
function commandPanels(language: Language): { name: string; html: string }[] {
  const model = commandModel();
  const noop = () => undefined;
  const panel = (name: string, node: React.ReactElement) => ({ name: `Command ${name} (${language})`, html: renderToStaticMarkup(node) });
  const phases = commandPhaseSpans(manifest.phases).map((span, index) => ({ ...span, label: manifest.phases[index].label }));
  return [
    panel("banner", <CommandBanner language={language} onInfo={noop} infoOpen={false} />),
    panel("situation, hour 84", <MaeSaiCommandSituation language={language} hour={84} manifest={manifest} model={model} />),
    panel("situation, hour 130", <MaeSaiCommandSituation language={language} hour={130} manifest={manifest} model={model} />),
    panel("situation in focus mode", <MaeSaiCommandSituation language={language} hour={44} manifest={manifest} model={model} collapsed />),
    panel("time dock", <MaeSaiCommandTimebar language={language} hour={84} playing={false} speed="drill" days={commandDayChips(manifest.days)} phases={phases}
      stops={commandEventStops(manifest, model.stages)} rainfall={manifest.rainfall ?? null} onTogglePlay={noop} onStep={noop} onSeek={noop} onEvent={noop} onSpeed={noop} />),
    panel("information drawer", <CommandInfoBody language={language} manifest={manifest} />),
    panel("help sheet", <CommandHelpSheet open={false} onClose={noop} onAbout={noop} language={language} />),
    panel("navigation and menu", <CommandNav language={language} hour={84} menuOpen onMenu={noop} onLanguage={noop} onHelp={noop} basemap="terrain" onBasemap={noop} />),
    panel("tool rail", <CommandToolRail language={language} focus basemap="street" nextFit="district" viewOpen={false} disabled={false} onView={noop} onBasemap={noop} onZoom={noop} onFit={noop} onFocus={noop} />),
    panel("view popover", <CommandViewPopover language={language} facilities facilityCount={manifest.facilities_count.total} onFacilities={noop} onClose={noop} />),
    panel("legend", <CommandLegend language={language} open onToggle={noop} facilities unmodelledRoads wetSites />),
    panel("credits", <CommandCredits language={language} view={{ metresPerPixel: 35.8, zoom: 12 }} revision={manifest.revision} />),
    ...commandTablePanels(language).map(({ name, node }) => panel(name, node)),
  ];
}

/** How many panels `commandTablePanels` renders in one language. */
const COMMAND_TABLE_PANEL_COUNT = 30;

/** The panels of the subdistrict table, the inspector and the find-place box in one language. */
function commandTablePanels(language: Language): { name: string; node: React.ReactElement }[] {
  const model = commandModel();
  const noop = () => undefined;
  const scale = lostAccessScale(model);
  const tambonFeatures = readJson<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href).features;
  const facilityFeatures = readJson<GeoCollection<{ coordinates: number[] }, FacilityProps>>(manifest.vectors.facilities.href).features;
  const roadFeatures = readJson<GeoCollection<LineGeometry, RoadProps>>(manifest.vectors.roads.href).features;
  const noCells = { O1: new Map<string, CommandPlanningCell>(), SE1: new Map<string, CommandPlanningCell>() };
  const rows = (hour: number, set: CommandShelterSet = "reported") => commandTableRows({
    rows: tambonRowsAt(model, hour, set), before: tambonRowsBefore(model, hour, set), order: tambonOrderByHour(model, set)[hour], scale, orderBy: "hour", positionFrom: "SE1", cells: noCells,
  });
  const queue = (more: Partial<Parameters<typeof MaeSaiCommandQueue>[0]> = {}) => (
    <MaeSaiCommandQueue language={language} rows={rows(84)} selected="TH570901" onSelect={noop} set="reported" onSet={noop} setSites={{ reported: 12, plan: 8 }} orderBy="hour" onOrderBy={noop}
      canOrderByPlanning={false} positionFrom="SE1" onPositionFrom={noop} pending={false} optionsOpen onOptions={noop} {...more} />
  );
  const table = (hour: number, set: CommandShelterSet, pending = false) => (
    <CommandQueueTable language={language} rows={rows(hour, set)} selected={null} onSelect={noop} set={set} positionFrom="SE1" pending={pending} />
  );
  const peaks = parsePeakSummary(readJson<unknown>(manifest.exports!.files.find((file) => file.id === "tambon_replay_summary")!.href));
  const places = placeRecordsOfTambons(manifest.reported_depths!.reports, tambonFeatures);
  const facilityProps = facilityFeatures.map((feature) => feature.properties);
  const detail = (id: string, hour: number, set: CommandShelterSet, peak: boolean) => (
    <CommandTambonDetailBody language={language} hour={hour} detail={tambonDetailAt(model, facilityProps, hour, set, id)!} set={set} peak={peak ? peaks.get(id) ?? null : null}
      peakStatus={peak ? "ready" : "missing"} places={places.get(id) ?? []} depths={manifest.reported_depths ?? null} unlocated={model.placeRecords.unlocated}
      cells={{ O1: null, SE1: null }} facts={{ O1: null, SE1: null }} />
  );
  // The planning overlay fixture: invented units, read in tests only, on invented rows of the left group.
  const overlay = parsePlanningAssessmentOverlay(fixtureOverlay);
  const cells = { O1: planningCells(overlay, "O1"), SE1: planningCells(overlay, "SE1") };
  const invented: CommandTambonRow[] = ["FX-U03", "FX-U13", "FX-U14", "FX-U15"].map((id, index) => ({
    id, th: `หน่วยทดสอบ ${id.slice(-2)}`, en: `Fixture unit ${id.slice(-2)}`, lostAccess: 400 - index * 100, inWater: 900 - index * 50,
    residents: 2000, noReachBefore: 100, noReachShare: 0.05, mostHadNoReach: false, placeRecords: 0,
  }));
  const fixtureRows = commandTableRows({ rows: invented, before: null, order: invented.map((row) => row.id), scale: 1000, orderBy: "planning", positionFrom: "SE1", cells });
  const index = buildCommandFindIndex({ manifest, tambons: tambonFeatures, facilities: facilityFeatures, roads: roadFeatures });
  const find = (query: string) => <MaeSaiCommandFind language={language} index={index} onPick={noop} onClose={noop} initialQuery={query} />;
  const panels = [
    { name: "table card with its controls", node: queue() },
    { name: "table card, waiting", node: queue({ rows: null }) },
    { name: "table card, data failed", node: queue({ rows: null, failed: true }) },
    { name: "table card in focus mode", node: queue({ collapsed: true }) },
    { name: "table card on a tablet", node: queue({ layout: "tablet", tab: "queue" }) },
    { name: "table, hour 0", node: table(0, "reported") },
    { name: "table, hour 84, plan set", node: table(84, "plan") },
    { name: "table, hour 130, order held", node: table(130, "reported", true) },
    { name: "table, fixture units", node: <CommandQueueTable language={language} rows={fixtureRows} selected={null} onSelect={noop} set="reported" positionFrom="SE1" pending={false} /> },
    ...model.tambons.map((tambon) => ({ name: `inspector ${tambon.id}`, node: detail(tambon.id, 84, "reported", true) })),
    { name: "inspector, plan set, hour 130", node: detail("TH570901", 130, "plan", true) },
    { name: "inspector without the peak summary", node: detail("TH570906", 44, "reported", false) },
    ...COMMAND_PLANNING_CASES.flatMap((planningCase) => [...cells[planningCase].values()].map((cell) => ({
      name: `case card ${cell.rowId}`, node: <CommandCaseCard planningCase={planningCase} cell={cell} facts={planningFacts(overlay)} language={language} />,
    }))),
    { name: "right card, known by now", node: <MaeSaiCommandInspector language={language} tab="known" onTab={noop} onClose={noop} detail={null} known={<CommandKnownPlaceholder language={language} />} /> },
    { name: "right card, nothing selected", node: <MaeSaiCommandInspector language={language} tab="detail" onTab={noop} onClose={noop} detail={null} known={null} /> },
    { name: "right card chip", node: <CommandCardChip language={language} label={COMMAND_INSPECTOR.chipKnown[language]} onOpen={noop} /> },
    { name: "find-place box", node: find("") },
    { name: "find-place box, names found", node: find(language === "th" ? "วัด" : "mae") },
    { name: "find-place box, roads", node: find("ถนน") },
    { name: "find-place box, nothing found", node: find("zzz") },
  ];
  if (panels.length !== COMMAND_TABLE_PANEL_COUNT) throw new Error(`Expected ${COMMAND_TABLE_PANEL_COUNT} table panels, got ${panels.length}`);
  return panels;
}

function corpus(): { source: string; text: string }[] {
  const sources = replaySourceFiles().flatMap((file) =>
    sourceStrings(readFileSync(resolve(webRoot, file), "utf8"), file).map((text) => ({ source: file, text })));
  const manifestText = [
    ...jsonStrings(manifest).map(({ path, text }) => ({ source: `timeline.json ${path}`, text })),
    // The season envelope's statistics file: text derived from product 4009, read by the page.
    ...jsonStrings(envelopeDocument).map(({ path, text }) => ({ source: `unosat4009/envelope.json ${path}`, text })),
    // The licence notice that ships beside it, English and Thai halves (the Thai half states the changes in Thai).
    { source: "unosat4009/LICENSE", text: readFileSync(resolve(publicRoot, envelopeBlock.files.licence.href.replace(/^\//, "")), "utf8") },
  ];
  // The map popups of the reported depths are built from text nodes on the page; their lines are linted as they are built.
  const depths = shippableReportedDepths(manifest)!;
  const popups = (["en", "th"] as const).flatMap((language) => depths.reports.filter((report) => report.point).map((report) => {
    const { lines, link } = reportedDepthPopup(report, depths, language);
    return { source: `reported-depth popup ${report.id} ${language}`, text: [...lines.map((line) => line.text), link.text].join("\n") };
  }));
  const rendered = [
    { name: "MaeSaiFloodTimeline shell (en)", html: renderToStaticMarkup(<MaeSaiFloodTimeline />) },
    ...renderedPanels("en"),
    ...renderedPanels("th"),
    // The Command exercise page: its shell before the data loads, and its panels with the served data.
    { name: "Command exercise shell (en)", html: renderToStaticMarkup(<MaeSaiCommandExercise />) },
    ...commandPanels("en"),
    ...commandPanels("th"),
  ].map(({ name, html }) => ({ source: name, text: visibleText(html) }));
  // The Command exercise copy, one item per language, as the page builds its lines.
  const command = (["en", "th"] as const).map((language) => ({ source: `Command exercise copy (${language})`, text: commandCopyLines(language).join("\n") }));
  return [...sources, ...manifestText, ...popups, ...rendered, ...command];
}

const lint = (items: { source: string; text: string }[]) => items.flatMap(({ source, text }) => findWordingViolations(text, source));

describe("Replay wording rules (shared with Python)", () => {
  it("cover the six banned groups of the replay roadmap and the shelter-comparison rules", () => {
    expect(ruleIds).toEqual([
      "real_time", "live", "forecast", "warning", // affirmative real-time, live, forecast or warning
      "validation_as_agreement", // validated, validation or accuracy used for agreement
      "precision_recall", // precision or recall for product 4009
      "corroboration", // the season envelope "corroborating" the model, or the reverse
      "envelope_verdict", // "the model is too low" or "too high", or under- or overestimates, against the season envelope
      "envelope_as_observation", // the season envelope called observed, or an observation
      "september_extent", // "September extent", "GISTDA's map"
      "return_period", // 25-year, 100-year
      "road_schedule", // schedule or closure plan for modelled roads
      "set_ranking", // a shelter set or plan called better, best or worse (P2-4)
      "safe_departure", // the modelled cut-off hour presented as a safe time to leave (P2-4)
      "shelter_directive", // "open these shelters": the plans list candidates to verify (P2-9)
      "equity_denominator", // the equity rates stated over all residents counted, not those within reach before the flood (R8)
      "report_confirmation", // a news report "confirming" the model, or the model "confirmed by" reports (C-2)
      "report_count", // the reported depths counted as news reports: they are place records (one statement per community)
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
    // En dashes, figure dashes and minus signs read as hyphens, so "real–time" cannot slip past as another word.
    expect(normaliseWording("real–time, real‒time, real−time, 10–14 Sep")).toBe("real-time, real-time, real-time, 10-14 Sep");
    expect(idsOf(findWordingViolations("A real–time view"))).toEqual(["real_time"]);
  });

  it("flags the Thai renderings a translator would use for a banned claim, and lets their denials pass", () => {
    const banned: [string, string][] = [
      ["แผนที่น้ำท่วมตามเวลาจริง", "real_time"], ["คาดการณ์น้ำท่วม", "forecast"], ["ทำนายระดับน้ำ", "forecast"],
      ["แบบจำลองแม่นยำ 48%", "validation_as_agreement"], ["ผ่านการตรวจสอบแล้ว", "validation_as_agreement"],
      ["ประกาศเตือน", "warning"], ["คาบการเกิดซ้ำ 100 ปี", "return_period"], ["รอบ ๑๐๐ ปี", "return_period"], ["รอบ ๒๕ ปี", "return_period"],
    ];
    for (const [text, rule] of banned) expect(idsOf(findWordingViolations(text)), text).toContain(rule);
    for (const denial of ["ไม่ใช่แผนที่ตามเวลาจริง", "ไม่ใช่การคาดการณ์", "ยังไม่ผ่านการตรวจสอบภาคสนาม", "ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ", "ไม่ใช่ความแม่นยำ"]) {
      expect(findWordingViolations(denial), denial).toEqual([]);
    }
    // One denial does not cover a claim joined with "and": the warning needs its own "not".
    expect(idsOf(findWordingViolations("not real-time, warning: flooding expected"))).toEqual(["warning"]);
    expect(idsOf(findWordingViolations("This is not real-time and an official warning"))).toEqual(["warning"]);
    expect(idsOf(findWordingViolations("ไม่ใช่ข้อมูลเรียลไทม์และคำเตือนอย่างเป็นทางการ"))).toEqual(["warning"]);
    expect(findWordingViolations("It is a model, not real-time or a warning.")).toEqual([]);
    expect(idsOf(findWordingViolations("100 yr flood; Flood alert; the plan is the better option"))).toEqual(["return_period", "set_ranking", "warning"]);
    // The equity rates divide by the residents within reach before the flood (R8, option B); the earlier sentence fails.
    expect(idsOf(findWordingViolations("Each rate divides the residents who lost access by all residents counted in that group"))).toEqual(["equity_denominator"]);
    expect(idsOf(findWordingViolations("แต่ละอัตราคือผู้ที่สูญเสียการเข้าถึงหารด้วยผู้อยู่อาศัยทั้งหมดที่นับในกลุ่มนั้น"))).toEqual(["equity_denominator"]);
    // Text about the season envelope (product 4009): none of the five words, and no verdict on the model.
    const envelopeBanned: [string, string][] = [
      ["Precision against product 4009: 0.61", "precision_recall"], ["Recall of the season envelope: 0.70", "precision_recall"],
      ["Accuracy against the season envelope: 48%", "validation_as_agreement"], ["The model is validated by product 4009", "validation_as_agreement"],
      ["The season envelope corroborates the modelled peak", "corroboration"], ["59% corroboration of the low-confidence water", "corroboration"],
      ["Against the envelope the model is too low in town", "envelope_verdict"], ["The model is likely too high in Ban Dai", "envelope_verdict"],
      ["Compared with the September extent of product 4009", "september_extent"], ["GISTDA's map of the season", "september_extent"],
      ["ขอบเขตน้ำตลอดฤดูช่วยยืนยันแบบจำลอง", "corroboration"], ["แบบจำลองต่ำเกินไปในเขตเมือง", "envelope_verdict"],
      // A verdict in other words: under- or overestimate verbs, and "too low/large" a few words after the model.
      ["The model underestimates the town against the envelope", "envelope_verdict"], ["Modelled water in town is too low", "envelope_verdict"],
      ["The modelled extent in Ban Dai is too large", "envelope_verdict"], ["The model overestimates Ban Dai", "envelope_verdict"],
      ["The town is underestimated by the model", "envelope_verdict"], ["แบบจำลองประเมินต่ำเกินไปในเขตเมือง", "envelope_verdict"],
      // The envelope is a scenario layer: never observed water, never an observation.
      ["the envelope observed in September", "envelope_as_observation"], ["The season envelope was observed on 12 Sep", "envelope_as_observation"],
      ["The observed envelope covers the town", "envelope_as_observation"], ["Product 4009 is the observed flood extent", "envelope_as_observation"],
      ["ขอบเขตน้ำตลอดฤดูที่สังเกตได้ในเดือนกันยายน", "envelope_as_observation"],
      ["ขอบเขตน้ำตลอดฤดูยืนยันผลการจำลอง", "corroboration"],
    ];
    for (const [text, rule] of envelopeBanned) expect(idsOf(findWordingViolations(text)), text).toContain(rule);
    for (const allowed of [
      "Plausibility against a season envelope, not a validation.",
      "Season envelope comparison (scenario; plausibility, not validation)",
      "60% of the modelled water lies inside the envelope; the modelled water reaches 70% of the envelope.",
      "The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.",
      "Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.",
      "เป็นการดูความสมเหตุสมผลเทียบกับขอบเขตน้ำตลอดฤดู ไม่ใช่การยืนยันความถูกต้อง",
      "Scenario (SCN-ENV): 2024 season envelope; not an observation for any replay day.",
      "The envelope is never an observation for a replay day. VIIRS daily flood map (375 m, observed).",
      // "ยืนยันผล" and "รับรองผล" are the start of "...ผลิตภัณฑ์" (product) in the licence limits: no finding there.
      "UNOSAT และ GISTDA ไม่ได้รับรองผลิตภัณฑ์นี้",
      "UNOSAT และ GISTDA ไม่ได้รับรอง FloodGuard หรือการใช้ผลิตภัณฑ์นี้ของ FloodGuard",
      "แบบจำลองพื้นผิวความละเอียด 30 ม. ทำให้ระดับพื้นดินในเขตสิ่งปลูกสร้างสูงกว่าจริง น้ำจากแบบจำลองและจำนวนผู้อยู่อาศัยในน้ำในเขตเมืองจึงน่าจะต่ำกว่าความเป็นจริง",
    ]) expect(describeWordingFindings(findWordingViolations(allowed)), allowed).toBe("");
    // The disclosed terrain bias is allowed in its own words only: the same claim in other words is a finding.
    expect(idsOf(findWordingViolations("The 30 m surface model raises the ground, so the model underestimates the town."))).toEqual(["envelope_verdict"]);
    expect(findWordingViolations("Each rate divides the residents of a group who lost access by the residents of that group who had a shelter of this set within reach before the flood.")).toEqual([]);
    expect(findWordingViolations("Proxy-vulnerable: 320 lost of 373 within reach before the flood (7,152 residents counted).")).toEqual([]);
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
      // The Command exercise replay: the shared map kit, the pure figures and the copy.
      "src/components/mae-sai-map-kit.tsx", "src/lib/flood-timeline-command.ts", "src/lib/flood-timeline-command-copy.ts",
      // Its page: the route, the shell, the map, the clock card, the time dock and the panels around the map, and
      // the replay controls, the map arithmetic and the loader behind them.
      "src/app/command/exercise/page.tsx", "src/components/mae-sai-command-exercise.tsx", "src/components/mae-sai-command-map.tsx",
      "src/components/mae-sai-command-situation.tsx", "src/components/mae-sai-command-timebar.tsx", "src/components/mae-sai-command-chrome.tsx",
      "src/lib/flood-timeline-command-replay.ts", "src/lib/flood-timeline-command-map.ts", "src/lib/flood-timeline-command-data.ts",
      // The subdistrict table, the inspector and the find-place box, and the pure functions behind them.
      "src/components/mae-sai-command-queue.tsx", "src/components/mae-sai-command-inspector.tsx", "src/components/mae-sai-command-find.tsx",
      "src/lib/flood-timeline-command-table.ts",
    ]) expect(files).toContain(file);
    const sources = new Set(items.map((item) => item.source));
    for (const file of files) expect(sources.has(file), file).toBe(true);
    expect(items.filter((item) => item.source.startsWith("timeline.json")).length).toBeGreaterThan(100);
    // 75 rendered panels of the Studio replay, the Command exercise copy in its two languages, and the Command exercise
    // page: its shell, and in each language 12 panels around the map and the panels of the table, the inspector and
    // the find-place box.
    expect(items.filter((item) => / \((en|th)\)$/.test(item.source)).length).toBe(77 + 1 + 2 * (12 + COMMAND_TABLE_PANEL_COUNT));
    const commandRendered = items.filter((item) => /^Command (?!exercise copy)/.test(item.source));
    expect(commandRendered).toHaveLength(1 + 2 * (12 + COMMAND_TABLE_PANEL_COUNT));
    const commandText = commandRendered.map((item) => item.text).join(" ");
    expect(commandText).toContain("reconstructed, not real-time");
    expect(commandText).toContain("จำลองย้อนหลัง ไม่ใช่ข้อมูลเรียลไทม์");
    expect(commandText).toContain("Model limit: standing water and mud are not reconstructed");
    expect(commandText).toContain("not yet known at this hour");
    expect(commandText).toContain("It has not been reviewed by a native speaker.");
    expect(commandText).toContain("Not for emergency response, evacuation orders or any operational decision; not an official warning.");
    // The table and the inspector are in the corpus with their honest empty state, and the fixture table with its E.
    expect(commandText).toContain("Not issued yet.");
    expect(commandText).toContain("Planning class from the signed protocol. Fixed in time. Not computed from this replay hour.");
    expect(commandText).toContain("Not issued yet (task E8)");
    expect(commandText).toContain("Class E never means safe.");
    expect(commandText).toContain("ระดับ E ไม่ได้หมายความว่าปลอดภัย");
    expect(commandText).toContain("Own model candidate: verify before action");
    expect(commandText).toContain("+ most residents had no reported shelter within 2 km before the flood");
    expect(commandText).toContain("The data holds no list of villages or sois.");
    const commandCopy = items.filter((item) => item.source.startsWith("Command exercise copy ("));
    expect(commandCopy.map((item) => item.source)).toEqual(["Command exercise copy (en)", "Command exercise copy (th)"]);
    expect(commandCopy[0].text).toContain("Exercise replay · Mae Sai, September 2024 · reconstructed, not real-time · not an official warning");
    expect(commandCopy[0].text).toContain("~7,100 · lost shelter access · of ~34,500 in reach");
    expect(commandCopy[0].text).toContain("It has not been reviewed by a native speaker.");
    expect(commandCopy[1].text).toContain("ฝึกซ้อมย้อนดูเหตุการณ์ · แม่สาย กันยายน 2567 (2024) · จำลองย้อนหลัง ไม่ใช่ข้อมูลเรียลไทม์ · ไม่ใช่คำเตือนทางการ");
    expect(commandCopy[1].text).toContain("ถนนที่เริ่มสัญจรไม่ได้: ");
    // Reported depths: the Sources entry and the legend in both languages, and the popup of every located report.
    expect(items.filter((item) => item.source.startsWith("reported-depth popup ")).length).toBe(24);
    const depthText = items.filter((item) => /ReportedDepths|reported depths|reported-depth popup/.test(item.source)).map((item) => item.text).join(" ");
    expect(depthText).toContain("Status: reported (anecdotal, not surveyed).");
    expect(depthText).toContain("never a validation");
    expect(depthText).toContain("สถานะ: ตามรายงาน (คำบอกเล่า ไม่ได้สำรวจ)");
    // Product 4009 text is in the corpus three ways: the page's own strings, the statistics file and the rendered panels.
    for (const file of ["src/components/mae-sai-season-envelope.tsx", "src/lib/flood-timeline-envelope.ts"]) expect(files).toContain(file);
    expect(items.filter((item) => item.source.startsWith("unosat4009/envelope.json")).length).toBeGreaterThan(30);
    const licence = items.find((item) => item.source === "unosat4009/LICENSE")!.text;
    expect(licence).toContain("FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย");
    expect(licence).toContain("UNOSAT และ GISTDA ไม่ได้รับรอง FloodGuard หรือการใช้ผลิตภัณฑ์นี้ของ FloodGuard");
    const envelopeText = items.filter((item) => /season envelope|SeasonEnvelope/.test(item.source)).map((item) => item.text).join(" ");
    expect(envelopeText).toContain("Scenario (SCN-ENV): 2024 season envelope");
    expect(envelopeText).toContain("Season envelope comparison (scenario; plausibility, not validation)");
    expect(envelopeText).toContain("Plausibility against a season envelope, not a validation.");
    expect(envelopeText).toContain("UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0)");
    expect(envelopeText).toContain("clipped to Mae Sai district and rasterised by FloodGuard");
    expect(envelopeText).toContain("Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.");
    expect(envelopeText).toContain("FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย");
    expect(envelopeText).toContain("สถานการณ์จำลอง (SCN-ENV): ขอบเขตน้ำตลอดฤดูปี 2567 (2024)");
    // The access card is linted with both shelter sets side by side, at the peak and before the flood, for both ways of
    // counting residents: every wording of the Evacuation Equity Gap (a ratio, no loss, a group too small) is in the corpus.
    const accessText = items.filter((item) => item.source.startsWith("AccessCard")).map((item) => item.text).join(" ");
    expect(accessText).toContain("Modelled access cut-off hour");
    expect(accessText).toContain("No single figure ranks the sets");
    expect(accessText).toContain("no ratio shown");
    expect(accessText).toContain("ไม่แสดงอัตราส่วน");
    expect(accessText).toContain("Of the residents in each group who had a shelter within reach before the flood, the share who lost it.");
    expect(accessText).toContain("Among residents with a shelter within reach before the flood, proxy-vulnerable residents are about 1.6× more likely to lose it (85.77% vs 53.42%)");
    expect(accessText).toContain("no proxy-vulnerable resident has lost access");
    expect(accessText).toContain("so none could lose it");
    expect(accessText).toContain("No one in either group has lost access at this replay hour");
    expect(accessText).toContain("มากกว่ากลุ่มอื่นประมาณ 1.6 เท่า");
    expect(accessText).toContain("จึงไม่มีผู้ใดในกลุ่มนี้สูญเสียการเข้าถึงได้");
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
    // Product 4009 text: the page's own strings, the statistics file and the rendered comparison.
    const envelopeSource = items.find((item) => item.source === "src/components/mae-sai-season-envelope.tsx")!;
    const envelopeFile = items.find((item) => item.source === "unosat4009/envelope.json $.comparison.use")!;
    const envelopeRendered = items.find((item) => item.source === "ExternalChecks with the season envelope (en)")!;
    // The Command exercise replay: its copy file, and the lines it builds in Thai.
    const commandSource = items.find((item) => item.source === "src/lib/flood-timeline-command-copy.ts")!;
    const commandBuilt = items.find((item) => item.source === "Command exercise copy (th)")!;
    // Its page: a component file, the route's page and two rendered panels.
    const commandComponent = items.find((item) => item.source === "src/components/mae-sai-command-chrome.tsx")!;
    const commandRoute = items.find((item) => item.source === "src/app/command/exercise/page.tsx")!;
    const commandDock = items.find((item) => item.source === "Command time dock (th)")!;
    const commandDrawer = items.find((item) => item.source === "Command information drawer (en)")!;
    // The table and the inspector: a component file, the pure functions, and three rendered panels.
    const commandQueue = items.find((item) => item.source === "src/components/mae-sai-command-queue.tsx")!;
    const commandTable = items.find((item) => item.source === "src/lib/flood-timeline-command-table.ts")!;
    const commandTableCard = items.find((item) => item.source === "Command table card with its controls (th)")!;
    const commandInspector = items.find((item) => item.source === "Command inspector TH570901 (en)")!;
    const commandFixture = items.find((item) => item.source === "Command table, fixture units (en)")!;
    const targets = [source, manifestItem, rendered, envelopeSource, envelopeFile, envelopeRendered, commandSource, commandBuilt, commandComponent, commandRoute, commandDock, commandDrawer,
      commandQueue, commandTable, commandTableCard, commandInspector, commandFixture];
    // The rest of the corpus is clean (the test above), so only the planted items need linting again.
    const others = items.filter((item) => !targets.includes(item));
    expect(lint(others)).toEqual([]);
    for (const rule of REPLAY_WORDING_RULES.rules) {
      for (const target of targets) {
        const findings = lint([{ ...target, text: `${target.text} ${rule.bad[0]}` }]);
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
