"use client";

/**
 * The Command exercise replay (Mae Sai, September 2024): a full-screen map that replays the flood hour by hour for
 * people who coordinate rescue, as an exercise and after-action tool. This file is the shell: it loads the replay
 * data, keeps the replay hour (play, steps, speeds, keys, the hour in the address bar) and lays the panels over the
 * map. The page is a reconstruction of a 2024 event: it is not real-time, not an official warning and not a dispatch
 * system, and every modelled figure is low confidence. The banner says so on every screen.
 *
 * Regions (plan section 3): A banner, B1 clock and figures, B2 subdistrict table (reserved), C navigation, E tool
 * rail, F time dock, G legend, H watermark and credits, I one-line notice.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from "react";

import type { Language } from "@/lib/flood-timeline";
import { buildCommandModel, commandStage, type CommandModel } from "@/lib/flood-timeline-command";
import { COMMAND_MAP, COMMAND_NAV, commandText } from "@/lib/flood-timeline-command-copy";
import { loadCommandHand, loadCommandReplay, type CommandHandRaster, type CommandReplayData } from "@/lib/flood-timeline-command-data";
import { reportedSiteWetAt } from "@/lib/flood-timeline-command-map";
import {
  commandDayChips,
  commandEventStops,
  commandKeyAction,
  commandPhaseSpans,
  commandReplayReducer,
  commandSpeed,
  initialCommandReplay,
  mergeCommandLink,
  parseCommandLink,
  type CommandKeyTarget,
} from "@/lib/flood-timeline-command-replay";
import { clearRect, type ScreenRect } from "@/lib/flood-timeline-layout";
import { useLanguage } from "@/lib/use-language";

import {
  CommandBanner,
  CommandCredits,
  CommandHelpSheet,
  CommandInfoDrawer,
  CommandLegend,
  CommandNav,
  CommandNotice,
  CommandTableCard,
  CommandToolRail,
  CommandViewPopover,
  CommandWatermark,
} from "./mae-sai-command-chrome";
import { MaeSaiCommandMap, type CommandBasemap, type CommandFitTarget, type CommandMapHandle, type CommandMapView } from "./mae-sai-command-map";
import { MaeSaiCommandSituation } from "./mae-sai-command-situation";
import { MaeSaiCommandTimebar, type CommandPhaseBandItem } from "./mae-sai-command-timebar";
import styles from "./mae-sai-command-exercise.module.css";

/** The address bar is rewritten at most this often while the replay hour changes. */
const LINK_WRITE_MS = 300;

type LoadState = { status: "loading" } | { status: "error" } | { status: "ready"; data: CommandReplayData; model: CommandModel };
/** The panels that open over the map; one at a time, so they never cover each other. */
type OpenPanel = "legend" | "view" | "menu" | null;

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
function subscribeReducedMotion(notify: () => void) {
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
}
function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribeReducedMotion, () => window.matchMedia(REDUCED_MOTION_QUERY).matches, () => false);
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

export function MaeSaiCommandExercise() {
  const [language, setLanguage] = useLanguage("en");
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [hand, setHand] = useState<CommandHandRaster | null>(null);
  const [handFailed, setHandFailed] = useState(false);
  const [replay, dispatch] = useReducer(commandReplayReducer, undefined, () => initialCommandReplay());
  const [linkReady, setLinkReady] = useState(false);
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const [dialog, setDialog] = useState<"info" | "help" | null>(null);
  const [basemap, setBasemap] = useState<CommandBasemap>("street");
  const [facilities, setFacilities] = useState(false);
  const [tileIssue, setTileIssue] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [view, setView] = useState<CommandMapView | null>(null);
  const [nextFit, setNextFit] = useState<CommandFitTarget>("town");
  const reducedMotion = useReducedMotion();
  const online = useOnline();

  const stage = useRef<HTMLDivElement | null>(null);
  const map = useRef<CommandMapHandle | null>(null);
  const languageRef = useRef<Language>(language);
  const lastLinkWrite = useRef(0);
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
        const data = await loadCommandReplay(signal);
        if (signal.aborted) return;
        // The water raster loads on its own: the figures, the roads and the clock do not wait for it.
        loadCommandHand(data.manifest, signal).then(
          (raster) => { if (!signal.aborted) setHand(raster); },
          () => { if (!signal.aborted) setHandFailed(true); },
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
    setReloadKey((key) => key + 1);
  }, []);

  const data = load.status === "ready" ? load.data : null;
  const model = load.status === "ready" ? load.model : null;
  const manifest = data?.manifest ?? null;
  const { hour, playing, speed, focus } = replay;
  const stageNow = model ? commandStage(model, hour) : 0;

  const stops = useMemo(() => (manifest && model ? commandEventStops(manifest, model.stages) : []), [manifest, model]);
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

  // --- Playback: one replay hour per beat of the chosen speed -------------------------------------------
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => dispatch({ type: "tick" }), commandSpeed(speed).hourMs);
    return () => window.clearInterval(timer);
  }, [playing, speed]);

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
          if (openPanel) setOpenPanel(null);
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
  }, [ready, stops, openPanel, focus]);

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
  const notice = handFailed
    ? commandText(COMMAND_MAP.waterError, language)
    : mapReady && basemapFallback ? commandText(COMMAND_MAP.basemapFallback, language) : null;

  return (
    <main id="main-content" className={`command-page ${styles.page}`} data-command-exercise data-focus={focus ? "on" : "off"} data-hour={hour}
      data-command-ready={mapReady && ready && (hand !== null || handFailed) ? "true" : "false"} lang={language}>
      <CommandBanner language={language} onInfo={() => setDialog("info")} infoOpen={dialog === "info"} />
      <div ref={stage} className={styles.stage}>
        {data && (
          <MaeSaiCommandMap data={data} hand={hand} hour={hour} stage={stageNow} playing={playing} language={language} basemap={basemap} facilities={facilities}
            getClear={getClear} reducedMotion={reducedMotion} onReady={onMapReady} onBasemapIssue={setTileIssue} onView={setView} handle={map} />
        )}
        <CommandWatermark />
        <CommandCredits language={language} view={view} revision={manifest?.revision ?? null} />
        <a className={styles.srOnly} href="#command-time">{commandText(COMMAND_NAV.skip, language)}</a>
        <div className={styles.left}>
          <MaeSaiCommandSituation language={language} hour={hour} manifest={manifest} model={model} collapsed={focus} failed={load.status === "error"} onRetry={retry} />
          <CommandTableCard language={language} />
        </div>
        <CommandNotice message={notice} language={language} />
        <CommandNav language={language} hour={hour} menuOpen={openPanel === "menu"} onMenu={(open) => setOpenPanel(open ? "menu" : null)}
          onLanguage={setLanguage} onHelp={() => setDialog("help")} basemap={basemap} onBasemap={switchBasemap} />
        <CommandToolRail language={language} focus={focus} basemap={basemap} nextFit={nextFit} viewOpen={openPanel === "view"} disabled={!mapReady}
          onView={() => toggle("view")} onBasemap={switchBasemap} onZoom={(delta) => map.current?.zoomBy(delta)} onFit={fit} onFocus={() => dispatch({ type: "focus" })} />
        {openPanel === "view" && (
          <CommandViewPopover language={language} facilities={facilities} facilityCount={data?.facilities.features.length ?? 0} onFacilities={setFacilities} onClose={() => setOpenPanel(null)} />
        )}
        <CommandLegend language={language} open={openPanel === "legend"} onToggle={(open) => setOpenPanel(open ? "legend" : null)} facilities={facilities} unmodelledRoads={unmodelledRoads} wetSites={wetSites} />
        <div id="command-time">
          <MaeSaiCommandTimebar language={language} hour={hour} playing={playing} speed={speed} collapsed={focus} disabled={!ready} days={days} phases={phases} stops={stops}
            rainfall={manifest?.rainfall ?? null}
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
