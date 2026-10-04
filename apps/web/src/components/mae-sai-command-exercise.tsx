"use client";

/**
 * The Command exercise replay (Mae Sai, September 2024): a full-screen map that replays the flood hour by hour for
 * people who coordinate rescue, as an exercise and after-action tool. This file is the shell: it loads the replay
 * data, keeps the replay hour (play, steps, speeds, keys, the hour in the address bar), what is selected (a
 * subdistrict, an invented item of the exercise, or the reports saved on this device) and the choices of the table,
 * and lays the panels over the map. It also keeps the mode of the exercise: in trainee mode nothing of a later replay
 * hour is shown; hindsight mode shows everything. The page is a reconstruction of a 2024 event: it is not real-time,
 * not an official warning and not a dispatch system, and every modelled figure is low confidence. The banner says so
 * on every screen.
 *
 * Regions (plan section 3): A banner, B1 clock and figures, B2 subdistrict table, C navigation, D right card (detail
 * and what is known), E tool rail, F time dock, G legend, H watermark and credits, I one-line notice.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import type { Language, Localized } from "@/lib/flood-timeline";
import { buildCommandModel, commandStage, holdTambonOrder, tambonOrderByHour, tambonRowsAt, type CommandModel, type CommandShelterSet } from "@/lib/flood-timeline-command";
import { COMMAND_INSPECTOR, COMMAND_MAP, COMMAND_NAV, commandDetailChip, commandFindKindText, commandText, commandToleranceText } from "@/lib/flood-timeline-command-copy";
import {
  loadCommandEnvelope,
  loadCommandExercise,
  loadCommandHand,
  loadCommandOverlays,
  loadCommandPeakSummary,
  loadCommandReplay,
  type CommandEnvelope,
  type CommandHandRaster,
  type CommandReplayData,
} from "@/lib/flood-timeline-command-data";
import {
  buildCommandFeed,
  DEFAULT_COMMAND_MODE,
  feedAt,
  feedEventHours,
  placeRecordsAt,
  placeRecordTally,
  type CommandFeedPlace,
  type CommandMode,
} from "@/lib/flood-timeline-command-feed";
import {
  arrivedExerciseItems,
  deviceReportsByTambon,
  exerciseArrivals,
  exerciseCounts,
  exerciseHandling,
  lifeAtRiskHours,
  modelDepthAt,
  mostUrgentItem,
  tambonsWithoutReports,
  type ExerciseFile,
  type ExerciseHandlingMap,
  type ExerciseItem,
} from "@/lib/flood-timeline-command-incidents";
import { reportedSiteWetAt } from "@/lib/flood-timeline-command-map";
import { COMMAND_FEED, commandKnownCount, commandNewItemsNotice } from "@/lib/flood-timeline-command-reports-copy";
import {
  commandDayChips,
  commandEventStops,
  commandKeyAction,
  commandMarkStops,
  commandPhaseSpans,
  commandReplayReducer,
  commandSpeed,
  initialCommandReplay,
  mergeCommandLink,
  parseCommandLink,
  type CommandKeyTarget,
  type CommandReplayState,
} from "@/lib/flood-timeline-command-replay";
import {
  buildCommandFindIndex,
  commandHoldReducer,
  commandTableRows,
  DEFAULT_POSITION_CASE,
  hasPlanningPositions,
  lostAccessScale,
  NO_COMMAND_HOLD,
  NO_COMMAND_OVERLAYS,
  placeRecordsOfTambons,
  planningCells,
  planningFacts,
  tambonDetailAt,
  tambonRowsBefore,
  type CommandFindEntry,
  type CommandHoldSource,
  type CommandOrderBy,
  type CommandOverlays,
  type CommandPeakRecord,
  type CommandPlanningCase,
} from "@/lib/flood-timeline-command-table";
import { countedInReportedSet } from "@/lib/flood-timeline-evacuation";
import { clearRect, type ScreenRect } from "@/lib/flood-timeline-layout";
import { useLanguage } from "@/lib/use-language";
import { useStoredPublicReports } from "@/lib/use-public-reports";

import {
  CommandBanner,
  CommandCredits,
  CommandHelpSheet,
  CommandInfoDrawer,
  CommandLegend,
  CommandNav,
  CommandNotice,
  CommandToolRail,
  CommandViewPopover,
  CommandWatermark,
} from "./mae-sai-command-chrome";
import { MaeSaiCommandFeed } from "./mae-sai-command-feed";
import { findEntryNames, MaeSaiCommandFind } from "./mae-sai-command-find";
import { CommandDeviceDetailBody, CommandItemDetailBody } from "./mae-sai-command-incident";
import {
  CommandCardChip,
  CommandDetailEmpty,
  CommandKnownPlaceholder,
  CommandTambonDetailBody,
  MaeSaiCommandInspector,
  type CommandCardTab,
  type CommandPeakStatus,
} from "./mae-sai-command-inspector";
import { MaeSaiCommandMap, type CommandBasemap, type CommandEnvelopeLayer, type CommandFitTarget, type CommandMapHandle, type CommandMapPlace, type CommandMapView } from "./mae-sai-command-map";
import type { CommandMarkerFrame, CommandReportSelection } from "./mae-sai-command-markers";
import { MaeSaiCommandQueue, type CommandLeftTab } from "./mae-sai-command-queue";
import { MaeSaiCommandSituation } from "./mae-sai-command-situation";
import { MaeSaiCommandTimebar, type CommandPhaseBandItem } from "./mae-sai-command-timebar";
import styles from "./mae-sai-command-exercise.module.css";

/** The address bar is rewritten at most this often while the replay hour changes. */
const LINK_WRITE_MS = 300;
/** While the replay plays, the line that says an invented item has arrived stays this long. */
const ARRIVAL_NOTICE_MS = 8000;
const NO_ITEMS: readonly ExerciseItem[] = [];
const NO_HOURS: ReadonlySet<number> = new Set();
/** Until the act flow is built every invented item is new: nothing has been acknowledged, assigned or closed. */
const NO_HANDLING: ExerciseHandlingMap = new Map();

/** What is selected: a subdistrict of the table, or a report on the map. Never both. */
interface CommandSelection { tambon: string | null; report: CommandReportSelection | null; fit: number }
/** The invented items a step forward brought, for the one-line notice. */
interface CommandArrival { hour: number; ids: string[]; calls: number; reports: number; lifeAtRisk: boolean }

type LoadState = { status: "loading" } | { status: "error" } | { status: "ready"; data: CommandReplayData; model: CommandModel };
/** The panels that open over the map; one at a time, so they never cover each other. The legend and the right card are two of them. */
type OpenPanel = "legend" | "view" | "menu" | "find" | "card" | null;

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
/** A tablet in landscape: the right card does not exist, and its panels are tabs of the left column. */
const TABLET_QUERY = "(max-width: 1180px)";
/** A short or narrow screen: the controls above the table start behind their button, so the eight rows have room. */
const COMPACT_QUERY = "(max-height: 840px), (max-width: 1180px)";
function useMediaQuery(query: string): boolean {
  const subscribe = useCallback((notify: () => void) => {
    const list = window.matchMedia(query);
    list.addEventListener("change", notify);
    return () => list.removeEventListener("change", notify);
  }, [query]);
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false);
}
function subscribeOnline(notify: () => void) {
  window.addEventListener("online", notify);
  window.addEventListener("offline", notify);
  return () => {
    window.removeEventListener("online", notify);
    window.removeEventListener("offline", notify);
  };
}
/** Browser connectivity; the street basemap is the one online-only layer of the page. */
function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
}

/** Where a key was pressed, for `commandKeyAction`. */
function keyTarget(target: EventTarget | null): CommandKeyTarget {
  if (!(target instanceof HTMLElement)) return "page";
  if (target.matches("input[type='range']")) return "slider";
  if (target.isContentEditable || target.closest("textarea, select, input:not([type='checkbox']):not([type='range']), [contenteditable]:not([contenteditable='false'])")) return "field";
  if (target.closest("button, a[href], summary, input[type='checkbox'], [role='button']")) return "control";
  return "page";
}

/** A place of "Known by now" as the map marks it: the Thai name first, the romanised name and its stated tolerance. */
function feedPlaceOnMap(place: CommandFeedPlace, language: Language): CommandMapPlace | null {
  if (place.lat === null || place.lon === null) return null;
  return {
    target: { type: "point", lat: place.lat, lon: place.lon, toleranceM: place.toleranceM, siteId: place.siteId },
    title: place.th,
    lines: [place.en, ...(place.toleranceM ? [commandToleranceText(place.toleranceM, language)] : [])],
  };
}

/** A found name as the map marks it: the Thai name first, then what kind of name it is and how closely it is placed. */
function placeOnMap(entry: CommandFindEntry, language: Language): CommandMapPlace | null {
  const { target } = entry;
  if (!target || target.type === "tambon") return null;
  const names = findEntryNames(entry);
  return {
    target,
    title: names.first.text,
    lines: [
      ...(names.second ? [names.second.text] : []),
      commandFindKindText(entry, language),
      ...(target.type === "point" && target.toleranceM ? [commandToleranceText(target.toleranceM, language)] : []),
    ],
  };
}

export function MaeSaiCommandExercise({ initial }: {
  /** Where the replay starts before the address is read: the hour, and whether focus mode is on. */
  initial?: Partial<Pick<CommandReplayState, "hour" | "focus">>;
} = {}) {
  const [language, setLanguage] = useLanguage("en");
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [hand, setHand] = useState<CommandHandRaster | null>(null);
  const [handFailed, setHandFailed] = useState(false);
  const [overlays, setOverlays] = useState<CommandOverlays>(NO_COMMAND_OVERLAYS);
  const [peaks, setPeaks] = useState<{ status: CommandPeakStatus; records: ReadonlyMap<string, CommandPeakRecord> }>({ status: "loading", records: new Map() });
  const [replay, dispatch] = useReducer(commandReplayReducer, initial, (start) => ({ ...initialCommandReplay(start?.hour), focus: start?.focus ?? false }));
  const [linkReady, setLinkReady] = useState(false);
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const [dialog, setDialog] = useState<"info" | "help" | null>(null);
  const [basemap, setBasemap] = useState<CommandBasemap>("street");
  const [facilities, setFacilities] = useState(false);
  const [tileIssue, setTileIssue] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [view, setView] = useState<CommandMapView | null>(null);
  const [nextFit, setNextFit] = useState<CommandFitTarget>("town");
  // The table: the shelter set its figures count, what its rows are ordered by, and the case of the planning position.
  const [shelterSet, setShelterSet] = useState<CommandShelterSet>("reported");
  const [orderBy, setOrderBy] = useState<CommandOrderBy>("hour");
  const [positionFrom, setPositionFrom] = useState<CommandPlanningCase>(DEFAULT_POSITION_CASE);
  const [optionsChoice, setOptionsChoice] = useState<boolean | null>(null);
  const [hold, setHold] = useReducer(commandHoldReducer, NO_COMMAND_HOLD);
  // The selection: one subdistrict or one report, shown in the right card (on a tablet, in the tabs of the left column).
  const [selection, setSelection] = useState<CommandSelection>({ tambon: null, report: null, fit: 0 });
  const [cardTab, setCardTab] = useState<CommandCardTab>("detail");
  const [leftTab, setLeftTab] = useState<CommandLeftTab>("queue");
  // A place the reader asked the map to show: a name of the find-place box, or a place of "Known by now".
  const [found, setFound] = useState<{ entry: CommandFindEntry } | { place: CommandFeedPlace } | null>(null);
  // The exercise: what it shows of the future, its invented items, and whether playback pauses for a life-at-risk item.
  const [mode, setMode] = useState<CommandMode>(DEFAULT_COMMAND_MODE);
  const [exerciseFile, setExerciseFile] = useState<ExerciseFile | null>(null);
  const [itemsOn, setItemsOn] = useState(true);
  const [pauseOnLife, setPauseOnLife] = useState(true);
  const [arrival, setArrival] = useState<CommandArrival | null>(null);
  const [envelope, setEnvelope] = useState<CommandEnvelope | null>(null);
  const deviceReports = useStoredPublicReports();
  const reducedMotion = useMediaQuery(REDUCED_MOTION_QUERY);
  const tablet = useMediaQuery(TABLET_QUERY);
  const compact = useMediaQuery(COMPACT_QUERY);
  const online = useOnline();

  const stage = useRef<HTMLDivElement | null>(null);
  const map = useRef<CommandMapHandle | null>(null);
  // The layer of the map the watermark is drawn into: over the markers, under the popups.
  const [watermarkPane, setWatermarkPane] = useState<HTMLElement | null>(null);
  const languageRef = useRef<Language>(language);
  const shownOrder = useRef<readonly string[] | null>(null);
  const lastLinkWrite = useRef(0);
  const lastHour = useRef<number | null>(null);
  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  // --- The replay data, then the hour the address names -------------------------------------------------
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      // The address is read first, before any file arrives, so the clock shows the hour it names at once.
      const link = parseCommandLink(window.location.search);
      if (link.hour !== null) dispatch({ type: "seek", hour: link.hour });
      if (link.language && link.language !== languageRef.current) setLanguage(link.language);
      setLinkReady(true);
      try {
        // The invented items of the exercise are a file of their own: without it the replay still runs.
        loadCommandExercise(signal).then((file) => { if (!signal.aborted) setExerciseFile(file); }, () => undefined);
        const data = await loadCommandReplay(signal);
        if (signal.aborted) return;
        // The season envelope is drawn in hindsight mode only; its raster loads in the background.
        loadCommandEnvelope(data.manifest, signal).then((layer) => { if (!signal.aborted) setEnvelope(layer); }, () => undefined);
        // The water raster loads on its own: the figures, the roads and the clock do not wait for it.
        loadCommandHand(data.manifest, signal).then(
          (raster) => { if (!signal.aborted) setHand(raster); },
          () => { if (!signal.aborted) setHandFailed(true); },
        );
        // So do the planning overlays (none exists yet: the table then shows its empty state) and the peak summary.
        loadCommandOverlays(signal).then((files) => { if (!signal.aborted) setOverlays(files); }, () => undefined);
        loadCommandPeakSummary(data.manifest, signal).then(
          (records) => { if (!signal.aborted) setPeaks({ status: records.size > 0 ? "ready" : "missing", records }); },
          () => { if (!signal.aborted) setPeaks({ status: "missing", records: new Map() }); },
        );
        const model = buildCommandModel({ manifest: data.manifest, roads: data.roads.features, tambons: data.tambons.features, nodes: data.nodes });
        setLoad({ status: "ready", data, model });
      } catch {
        if (!signal.aborted) setLoad({ status: "error" });
      }
    })();
    return () => controller.abort();
  }, [reloadKey, setLanguage]);
  const retry = useCallback(() => {
    setLoad({ status: "loading" });
    setHand(null);
    setHandFailed(false);
    setPeaks({ status: "loading", records: new Map() });
    setReloadKey((key) => key + 1);
  }, []);

  const data = load.status === "ready" ? load.data : null;
  const model = load.status === "ready" ? load.model : null;
  const manifest = data?.manifest ?? null;
  const { hour, playing, speed, focus } = replay;
  const stageNow = model ? commandStage(model, hour) : 0;

  // --- "Known by now": every dated row of the replay data, cut at the replay hour in trainee mode --------
  const feed = useMemo(() => (manifest && model ? buildCommandFeed(manifest, model, shelterSet) : null), [manifest, model, shelterSet]);
  const feedRows = useMemo(() => (feed ? feedAt(feed, hour, mode) : null), [feed, hour, mode]);
  // The event buttons stop at every hour that has a mark on the track; before the data has loaded, at the phases.
  const stops = useMemo(() => (feed ? commandMarkStops(feedEventHours(feed)) : manifest && model ? commandEventStops(manifest, model.stages) : []), [feed, manifest, model]);
  const recordsNow = useMemo(() => placeRecordsAt(manifest?.reported_depths?.reports ?? [], hour, mode), [manifest, hour, mode]);
  const tally = useMemo(() => (manifest ? placeRecordTally(recordsNow) : null), [manifest, recordsNow]);

  // --- The exercise: invented items on the replay clock, and the reports saved on this device ----------------
  const items = itemsOn && exerciseFile ? exerciseFile.items : NO_ITEMS;
  const handling = NO_HANDLING;
  const counts = useMemo(() => (exerciseFile && itemsOn ? exerciseCounts(items, hour, handling) : null), [exerciseFile, itemsOn, items, hour, handling]);
  const pauseAt = useMemo(() => (pauseOnLife ? lifeAtRiskHours(items) : NO_HOURS), [pauseOnLife, items]);
  const tambonIds = useMemo(() => model?.tambons.map((tambon) => tambon.id) ?? [], [model]);
  const deviceByTambon = useMemo(() => deviceReportsByTambon(deviceReports, tambonIds), [deviceReports, tambonIds]);
  const days = useMemo(() => (manifest ? commandDayChips(manifest.days) : []), [manifest]);
  const phases = useMemo<CommandPhaseBandItem[]>(() => {
    if (!manifest) return [];
    const spans = commandPhaseSpans(manifest.phases);
    return manifest.phases.map((phase, index) => ({ ...spans[index], label: phase.label }));
  }, [manifest]);
  const unmodelledRoads = useMemo(() => Boolean(data?.roads.features.some((road) => !road.properties.m)), [data]);
  const wetSites = useMemo(() => {
    if (!manifest || !model) return false;
    const highest = Math.max(...model.stages);
    return Boolean(manifest.shelters?.reported.some((site) => reportedSiteWetAt(site, highest)));
  }, [manifest, model]);

  // --- The table: this hour's rows, their order (held while the reader is in the table) and the plan cells ----
  const orders = useMemo(() => (model ? tambonOrderByHour(model, shelterSet) : null), [model, shelterSet]);
  const recordPlaces = useMemo(() => (data ? placeRecordsOfTambons(data.manifest.reported_depths?.reports ?? [], data.tambons.features) : null), [data]);
  // The place records of each subdistrict that the mode shows at this hour: in trainee mode, those published by now.
  const placesNow = useMemo(() => {
    if (!recordPlaces) return null;
    const known = new Set(recordsNow.map((report) => report.id));
    return new Map([...recordPlaces].map(([id, places]) => [id, places
      .map((place) => ({ ...place, reports: place.reports.filter((report) => known.has(report.id)) }))
      .filter((place) => place.reports.length > 0)] as const));
  }, [recordPlaces, recordsNow]);
  const rowsNow = useMemo(() => {
    if (!model) return null;
    const rows = tambonRowsAt(model, hour, shelterSet);
    if (!placesNow) return rows;
    return rows.map((row) => ({ ...row, placeRecords: (placesNow.get(row.id) ?? []).reduce((sum, place) => sum + place.reports.length, 0) }));
  }, [model, hour, shelterSet, placesNow]);
  // Residents in modelled water and no place record or invented item by this hour: the map says "no reports received".
  const noReports = useMemo(() => {
    if (!rowsNow) return [];
    const withRecords = new Set(rowsNow.filter((row) => row.placeRecords > 0).map((row) => row.id));
    const withItems = new Set(arrivedExerciseItems(items, hour).map((item) => item.tambonId));
    return tambonsWithoutReports(rowsNow, withRecords, withItems);
  }, [rowsNow, items, hour]);
  const rowsBefore = useMemo(() => (model ? tambonRowsBefore(model, hour, shelterSet) : null), [model, hour, shelterSet]);
  const scale = useMemo(() => (model ? lostAccessScale(model) : 1), [model]);
  const cells = useMemo(() => ({ O1: planningCells(overlays.O1, "O1"), SE1: planningCells(overlays.SE1, "SE1") }), [overlays]);
  const facts = useMemo(() => ({ O1: overlays.O1 ? planningFacts(overlays.O1) : null, SE1: overlays.SE1 ? planningFacts(overlays.SE1) : null }), [overlays]);
  const setSites = useMemo<Record<CommandShelterSet, number>>(() => ({
    reported: manifest?.shelters?.reported.filter(countedInReportedSet).length ?? 0,
    plan: manifest?.shelters?.knee_k ?? 0,
  }), [manifest]);
  const order = orders ? holdTambonOrder(hold.frozen ? { order: hold.frozen } : null, orders[hour], hold.frozen !== null) : null;
  const canOrderByPlanning = hasPlanningPositions(cells[positionFrom]);
  const tableRows = rowsNow && order
    ? commandTableRows({ rows: rowsNow, before: rowsBefore, order: order.order, scale, orderBy: orderBy === "planning" && canOrderByPlanning ? "planning" : "hour", positionFrom, cells })
    : null;
  useEffect(() => {
    shownOrder.current = order?.order ?? null;
  });
  const onHold = useCallback((source: CommandHoldSource, held: boolean) => setHold({ source, held, order: shownOrder.current }), []);
  const onDrag = useCallback((dragging: boolean) => onHold("drag", dragging), [onHold]);

  // --- The selected subdistrict or report, and its inspector ----------------------------------------------
  const selected = selection.tambon;
  const selectedReport = selection.report;
  const selectedItem = selectedReport?.type === "exercise" ? items.find((item) => item.id === selectedReport.id && item.hour <= hour) ?? null : null;
  const selectedDevice = selectedReport?.type === "device" ? model?.tambons.find((tambon) => tambon.id === selectedReport.tambonId) ?? null : null;
  const facilityProps = useMemo(() => data?.facilities.features.map((feature) => feature.properties) ?? [], [data]);
  const detail = useMemo(() => (model && selected ? tambonDetailAt(model, facilityProps, hour, shelterSet, selected) : null), [model, facilityProps, hour, shelterSet, selected]);
  const findIndex = useMemo(() => (data ? buildCommandFindIndex({ manifest: data.manifest, tambons: data.tambons.features, facilities: data.facilities.features, roads: data.roads.features }) : []), [data]);
  const select = useCallback((id: string) => {
    setSelection((current) => ({ tambon: id, report: null, fit: current.fit + 1 }));
    setFound(null);
    setCardTab("detail");
    setLeftTab("detail");
    setOpenPanel("card");
  }, []);
  /** An invented item or a device sign was chosen (its marker's "Assign" or "Details", or the notice of a new item). */
  const selectReport = useCallback((report: CommandReportSelection) => {
    setSelection((current) => ({ tambon: null, report, fit: current.fit + 1 }));
    setFound(null);
    setCardTab("detail");
    setLeftTab("detail");
    setOpenPanel("card");
  }, []);
  const deselect = useCallback(() => {
    setSelection((current) => (current.tambon === null && current.report === null ? current : { tambon: null, report: null, fit: current.fit }));
    setLeftTab("queue");
    setOpenPanel((current) => (current === "card" ? null : current));
  }, []);
  // The map moves to what was selected once the card has opened, so the move uses the clear rectangle beside it: a
  // selected thing is never under a panel.
  useEffect(() => {
    if (!mapReady || (!selection.tambon && !selection.report)) return;
    const { tambon, report } = selection;
    const frame = window.requestAnimationFrame(() => {
      if (tambon) map.current?.fitTambon(tambon);
      else if (report) map.current?.focusReport(report);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selection, mapReady]);
  // A found place keeps its mark until another thing is chosen; its name follows the page language.
  const shownPlace = useCallback((language: Language): CommandMapPlace | null => {
    if (!found) return null;
    return "entry" in found ? placeOnMap(found.entry, language) : feedPlaceOnMap(found.place, language);
  }, [found]);
  useEffect(() => {
    if (mapReady) map.current?.showPlace(shownPlace(language));
  }, [shownPlace, language, mapReady]);
  const pickPlace = useCallback((entry: CommandFindEntry) => {
    if (!entry.target) return;
    if (entry.target.type === "tambon") {
      select(entry.target.id);
      return;
    }
    setFound({ entry });
    setOpenPanel(null);
    // Once the box has closed, the place is brought inside the clear rectangle.
    window.requestAnimationFrame(() => map.current?.showPlace(placeOnMap(entry, languageRef.current), true));
  }, [select]);
  /** A place link of "Known by now": the map shows the place inside the clear rectangle; time does not change. */
  const showFeedPlace = useCallback((place: CommandFeedPlace) => {
    if (place.lat === null || place.lon === null) return;
    setFound({ place });
    window.requestAnimationFrame(() => map.current?.showPlace(feedPlaceOnMap(place, languageRef.current), true));
  }, []);

  // --- Playback: one replay hour per beat of the chosen speed. It pauses at the hour a life-at-risk item of the
  // exercise arrives, unless the reader has switched that off.
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => dispatch({ type: "tick", pauseAt }), commandSpeed(speed).hourMs);
    return () => window.clearInterval(timer);
  }, [playing, speed, pauseAt]);

  // --- The notice of new invented items: what a step forward brought. A jump back takes it away.
  useEffect(() => {
    const before = lastHour.current;
    lastHour.current = hour;
    if (before === null || hour === before) return;
    const arrivals = hour > before ? exerciseArrivals(items, before, hour) : [];
    const calls = arrivals.filter((item) => item.kind === "call").length;
    setArrival(arrivals.length === 0
      ? (current) => (hour < before || (current && current.hour > hour) ? null : current)
      : { hour, ids: arrivals.map((item) => item.id), calls, reports: arrivals.length - calls, lifeAtRisk: arrivals.some((item) => item.urgency === "life_at_risk") });
  }, [hour, items]);
  useEffect(() => {
    if (!arrival || !playing) return;
    const timer = window.setTimeout(() => setArrival((current) => (current === arrival ? null : current)), ARRIVAL_NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [arrival, playing]);
  const openArrival = useCallback(() => {
    if (!arrival) return;
    const item = mostUrgentItem(items.filter((entry) => arrival.ids.includes(entry.id)));
    setArrival(null);
    if (item) selectReport({ type: "exercise", id: item.id });
  }, [arrival, items, selectReport]);

  // --- The hour in the address bar: the same `t` as on the Studio replay --------------------------------
  useEffect(() => {
    if (!linkReady) return;
    const write = () => {
      lastLinkWrite.current = performance.now();
      const query = mergeCommandLink(window.location.search, { hour, language });
      if (`?${query}` !== window.location.search) window.history.replaceState(window.history.state, "", `${window.location.pathname}?${query}${window.location.hash}`);
    };
    const wait = LINK_WRITE_MS - (performance.now() - lastLinkWrite.current);
    if (wait <= 0) {
      write();
      return;
    }
    const timer = window.setTimeout(write, wait);
    return () => window.clearTimeout(timer);
  }, [linkReady, hour, language]);

  // --- Keys ---------------------------------------------------------------------------------------------
  const ready = model !== null;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // A modal dialog (the drawer, the help sheet) has the keys while it is open; the browser closes it on Escape.
      if (event.defaultPrevented || document.querySelector("dialog[open]")) return;
      const action = commandKeyAction(event, keyTarget(event.target));
      if (!action) return;
      switch (action.type) {
        case "escape":
          // Escape closes what is open, then clears the selection, then leaves focus mode: one thing per key press.
          // A popup of the map goes first (the map uses the key up itself when the keyboard is inside the map).
          if (map.current?.closePopup()) break;
          if (openPanel && openPanel !== "card") setOpenPanel(null);
          else if (selected || selectedReport || openPanel === "card") deselect();
          else if (found) setFound(null);
          else if (focus) dispatch({ type: "focus", on: false });
          else return;
          break;
        case "help":
          setDialog("help");
          break;
        case "toggle_focus":
          dispatch({ type: "focus" });
          break;
        case "toggle_play":
          if (!ready) return;
          dispatch({ type: "toggle_play" });
          break;
        case "step":
          if (!ready) return;
          dispatch(action);
          break;
        case "event":
          if (!ready) return;
          dispatch({ ...action, stops });
          break;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ready, stops, openPanel, focus, selected, selectedReport, found, deselect]);

  // --- Keyboard focus: a panel that opens takes it, and a panel that closes hands it back to what opened it, so
  // the focus is never dropped to the page (from where the next Tab would start at the top).
  const focusState = useRef<{ panel: OpenPanel; leftTab: CommandLeftTab; focus: boolean }>({ panel: null, leftTab: "queue", focus: false });
  useEffect(() => {
    const before = focusState.current;
    focusState.current = { panel: openPanel, leftTab, focus };
    const root = stage.current;
    if (!root) return;
    const active = document.activeElement;
    const lost = !active || active === document.body;
    const to = (selector: string): boolean => {
      const target = root.querySelector<HTMLElement>(selector);
      if (!target || target.hidden || target.getClientRects().length === 0) return false;
      target.focus({ preventScroll: true });
      return true;
    };
    const within = (selector: string): boolean => active instanceof Element && active.closest(selector) !== null;
    if (openPanel !== before.panel) {
      // What opened: the legend and the card replace their chip, so the focus is lost with it; the view popover and
      // the menu open beside a button that keeps the focus, and take it from there.
      if (openPanel === "legend" && lost && to('[data-command-legend="open"] [data-command-panel-title]')) return;
      if (openPanel === "card" && lost && to('[data-region="D"] [role="tab"][aria-selected="true"]')) return;
      if (openPanel === "view" && (lost || within('[data-command-tool="view"]')) && to('[data-command-popover="view"] [data-command-panel-title]')) return;
      if (openPanel === "menu" && (lost || within("[data-command-menu]")) && to("[data-command-menu-panel] a, [data-command-menu-panel] button")) return;
      // What closed, with the focus inside it: back to its opener.
      if (lost) {
        if (before.panel === "legend" && to('[data-command-legend="chip"]')) return;
        if (before.panel === "card" && to('[data-command-card="chip"]')) return;
        if (before.panel === "view" && to('[data-command-tool="view"]')) return;
        if (before.panel === "menu" && to("[data-command-menu]")) return;
      }
    }
    if (!lost) return;
    // A tablet swaps the table for the detail when a row is chosen; focus mode folds the table away.
    if (tablet && leftTab !== before.leftTab && to(`[data-command-tab="${leftTab}"]`)) return;
    if (focus !== before.focus) to('[data-command-tool="focus"]');
  }, [openPanel, leftTab, focus, tablet]);

  // --- The clear rectangle: the part of the map no panel covers, measured when a fit or a popup asks -----
  const getClear = useCallback((): ScreenRect => {
    const element = stage.current;
    if (!element) return { left: 0, top: 0, right: 0, bottom: 0 };
    const box = element.getBoundingClientRect();
    const panels = [...element.querySelectorAll<HTMLElement>("[data-clear-panel]")].map((panel) => {
      const rect = panel.getBoundingClientRect();
      return { left: rect.left - box.left, top: rect.top - box.top, right: rect.right - box.left, bottom: rect.bottom - box.top };
    });
    return clearRect({ width: box.width, height: box.height }, panels);
  }, []);

  const toggle = (panel: Exclude<OpenPanel, null>) => setOpenPanel((current) => (current === panel ? null : panel));
  const fit = () => {
    map.current?.fit(nextFit);
    setNextFit(nextFit === "town" ? "district" : "town");
  };
  const switchBasemap = () => setBasemap((current) => (current === "street" ? "terrain" : "street"));
  const onMapReady = useCallback(() => setMapReady(true), []);

  const basemapFallback = basemap === "street" && (tileIssue || !online);
  // One line at a time: what failed, then an invented item that has just arrived, then the basemap note.
  const arrivalNotice = arrival ? commandNewItemsNotice(arrival.calls, arrival.reports, arrival.lifeAtRisk && !playing && arrival.hour === hour && pauseOnLife, language) : null;
  const notice = handFailed
    ? commandText(COMMAND_MAP.waterError, language)
    : arrivalNotice ?? (mapReady && basemapFallback ? commandText(COMMAND_MAP.basemapFallback, language) : null);

  // --- What the map draws of the reports, and the season envelope of hindsight mode ------------------------
  const reportFrame = useMemo<CommandMarkerFrame | null>(() => (data ? { hour, mode, items, handling, device: deviceByTambon, noReports, selected: selectedReport } : null),
    [data, hour, mode, items, handling, deviceByTambon, noReports, selectedReport]);
  const envelopeLayer = useMemo<CommandEnvelopeLayer | null>(() => (mode === "hindsight" && envelope ? { cells: envelope.cells, credit: envelope.block.map_credit } : null), [mode, envelope]);
  const tambonName = (id: string): Localized | null => model?.tambons.find((tambon) => tambon.id === id) ?? null;
  // The modelled depth at the selected item's point, at this replay hour (model, low confidence; no current).
  const itemDepth = selectedItem && manifest && hand
    ? modelDepthAt({ codes: hand.codes, factorKeys: hand.factorKeys, width: manifest.hand.width, height: manifest.hand.height, bounds: manifest.bounds, step: manifest.hand.step_m, channelCode: manifest.hand.channel_code, neverCode: manifest.hand.never_code },
      selectedItem.point.lat, selectedItem.point.lon, stageNow)
    : handFailed ? null : undefined;

  const selectedRow = selected ? rowsNow?.find((row) => row.id === selected) ?? null : null;
  const detailPanel = selectedItem && exerciseFile ? (
    <CommandItemDetailBody language={language} hour={hour} item={selectedItem} handling={exerciseHandling(handling, selectedItem.id)} tambon={tambonName(selectedItem.tambonId)} depth={itemDepth} rule={exerciseFile.rule} />
  ) : selectedDevice ? (
    <CommandDeviceDetailBody language={language} tambon={selectedDevice} reports={deviceByTambon.get(selectedDevice.id) ?? []} />
  ) : detail && selected ? (
    <CommandTambonDetailBody language={language} hour={hour} detail={detail} set={shelterSet} peak={peaks.records.get(selected) ?? null} peakStatus={peaks.status}
      places={placesNow?.get(selected) ?? []} depths={manifest?.reported_depths ?? null} unlocated={recordsNow.filter((report) => !report.point).length}
      cells={{ O1: cells.O1.get(selected) ?? null, SE1: cells.SE1.get(selected) ?? null }} facts={facts} mode={mode} />
  ) : null;
  const knownPanel = feedRows
    ? <MaeSaiCommandFeed language={language} hour={hour} mode={mode} onMode={setMode} items={feedRows} tally={tally} depths={manifest?.reported_depths ?? null} onPlace={showFeedPlace} />
    : <CommandKnownPlaceholder language={language} />;
  const knownCount = feedRows?.length;
  const chipLabel = selectedRow
    ? commandDetailChip(selectedRow.th, language)
    : selectedItem ? commandDetailChip(selectedItem.id, language)
      : selectedDevice ? commandDetailChip(selectedDevice.th, language)
        : knownCount === undefined ? commandText(COMMAND_INSPECTOR.chipKnown, language) : commandKnownCount(COMMAND_FEED.title, knownCount, language);
  const cardOpen = openPanel === "card" && !tablet;
  const openCard = (tab: CommandCardTab) => {
    setCardTab(tab);
    setOpenPanel("card");
  };

  return (
    <main id="main-content" className={`command-page ${styles.page}`} data-command-exercise data-focus={focus ? "on" : "off"} data-hour={hour} data-mode={mode} data-selected={selected ?? undefined}
      data-selected-report={selectedItem?.id ?? selectedDevice?.id ?? undefined}
      data-command-ready={mapReady && ready && (hand !== null || handFailed) ? "true" : "false"} lang={language}>
      <CommandBanner language={language} onInfo={() => setDialog("info")} infoOpen={dialog === "info"} />
      <div ref={stage} className={styles.stage}>
        {/* The map's fifteen site markers come first in the tab order: this link passes them. */}
        <a className={styles.skipLink} href="#command-time">{commandText(COMMAND_NAV.skip, language)}</a>
        {data && (
          <MaeSaiCommandMap data={data} hand={hand} hour={hour} stage={stageNow} playing={playing} language={language} basemap={basemap} facilities={facilities} selected={selected}
            reports={reportFrame} envelope={envelopeLayer} onReportAction={selectReport}
            getClear={getClear} reducedMotion={reducedMotion} onReady={onMapReady} onBasemapIssue={setTileIssue} onView={setView} onWatermarkPane={setWatermarkPane} handle={map} />
        )}
        {/* The watermark is drawn inside the map, over the markers and under the popups; until the map is there it lies over the stage. */}
        {watermarkPane ? createPortal(<CommandWatermark />, watermarkPane) : <CommandWatermark />}
        <CommandCredits language={language} view={view} revision={manifest?.revision ?? null} layerCredit={envelopeLayer?.credit ?? null} />
        <div className={styles.left}>
          <MaeSaiCommandSituation language={language} hour={hour} manifest={manifest} model={model} set={shelterSet} exercise={counts} tally={tally}
            onRecords={() => { setCardTab("known"); setLeftTab("known"); setOpenPanel("card"); }} collapsed={focus} failed={load.status === "error"} onRetry={retry} />
          <MaeSaiCommandQueue language={language} rows={tableRows} selected={selected} onSelect={select} set={shelterSet} onSet={setShelterSet} setSites={setSites}
            orderBy={orderBy} onOrderBy={setOrderBy} canOrderByPlanning={canOrderByPlanning} positionFrom={positionFrom} onPositionFrom={setPositionFrom}
            pending={order?.pending ?? false} onHold={onHold} optionsOpen={optionsChoice ?? !compact} onOptions={setOptionsChoice}
            collapsed={focus} failed={load.status === "error"} layout={tablet ? "tablet" : "desktop"} tab={leftTab} onTab={setLeftTab}
            detail={detailPanel ?? <CommandDetailEmpty language={language} />} known={knownPanel} knownCount={knownCount} />
        </div>
        <CommandNotice message={notice} language={language} onSelect={!handFailed && arrivalNotice ? openArrival : undefined} />
        <CommandNav language={language} hour={hour} menuOpen={openPanel === "menu"} onMenu={(open) => setOpenPanel(open ? "menu" : null)}
          onLanguage={setLanguage} onHelp={() => setDialog("help")} basemap={basemap} onBasemap={switchBasemap} />
        {!tablet && (cardOpen
          ? <MaeSaiCommandInspector language={language} tab={cardTab} onTab={setCardTab} onClose={deselect} detail={detailPanel} known={knownPanel} knownCount={knownCount} />
          : <CommandCardChip language={language} label={chipLabel} onOpen={() => openCard(detailPanel ? "detail" : "known")} />)}
        <CommandToolRail language={language} focus={focus} basemap={basemap} nextFit={nextFit} viewOpen={openPanel === "view"} findOpen={openPanel === "find"} disabled={!mapReady}
          onView={() => toggle("view")} onBasemap={switchBasemap} onZoom={(delta) => map.current?.zoomBy(delta)} onFit={fit} onFind={() => toggle("find")} onFocus={() => dispatch({ type: "focus" })} />
        {openPanel === "view" && (
          <CommandViewPopover language={language} facilities={facilities} facilityCount={data?.facilities.features.length ?? 0} onFacilities={setFacilities} onClose={() => setOpenPanel(null)}
            exercise={exerciseFile ? { count: exerciseFile.items.length, items: itemsOn, onItems: setItemsOn, pause: pauseOnLife, onPause: setPauseOnLife } : undefined} />
        )}
        {openPanel === "find" && <MaeSaiCommandFind language={language} index={findIndex} onPick={pickPlace} onClose={() => setOpenPanel(null)} />}
        <CommandLegend language={language} open={openPanel === "legend"} onToggle={(open) => setOpenPanel(open ? "legend" : null)} facilities={facilities} unmodelledRoads={unmodelledRoads} wetSites={wetSites} mode={mode} />
        <div id="command-time" tabIndex={-1}>
          <MaeSaiCommandTimebar language={language} hour={hour} playing={playing} speed={speed} collapsed={focus} disabled={!ready} days={days} phases={phases} stops={stops}
            rainfall={manifest?.rainfall ?? null} feed={feed} mode={mode} onMode={setMode} onDrag={onDrag}
            onTogglePlay={() => dispatch({ type: "toggle_play" })} onStep={(hours) => dispatch({ type: "step", hours })} onSeek={(next) => dispatch({ type: "seek", hour: next })}
            onEvent={(direction) => dispatch({ type: "event", direction, stops })} onSpeed={(next) => dispatch({ type: "speed", speed: next })} />
        </div>
      </div>
      {/* A dialog clears the state only while it is the open one: "About this exercise" in the help sheet swaps the two. */}
      <CommandInfoDrawer open={dialog === "info"} onClose={() => setDialog((current) => (current === "info" ? null : current))} language={language} manifest={manifest} />
      <CommandHelpSheet open={dialog === "help"} onClose={() => setDialog((current) => (current === "help" ? null : current))} onAbout={() => setDialog("info")} language={language} />
    </main>
  );
}
