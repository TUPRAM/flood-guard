"use client";

import type { Map as LeafletMap } from "leaflet";
import { useEffect, useMemo, useState } from "react";

import type { PracticeMapData } from "@/components/public-practice-layer";

import type { ExerciseItem } from "./flood-timeline-command-incidents";
import type { PracticeView } from "./public-practice";
import { practiceScenario, type PracticeState } from "./public-practice-scenarios";
import type { Language } from "./types";

type LeafletModule = typeof import("leaflet");

/** The replay, read once, with the code that reads it: neither is fetched until a scenario is first chosen. */
interface PracticeRuntime {
  logic: typeof import("./public-practice");
  layer: typeof import("@/components/public-practice-layer");
  data: PracticeMapData & { nodes: import("./flood-timeline-evacuation").AccessNodes };
  exercise: readonly ExerciseItem[];
}

let runtimeRequest: Promise<PracticeRuntime> | null = null;

/**
 * The replay files of the practice mode and the modules that draw them. One request for the page; a failed one is
 * forgotten, so choosing a scenario again tries again. The terrain raster and the exercise file are each optional:
 * without the raster the roads are still drawn, without the file there are no practice reports.
 */
function loadPracticeRuntime(): Promise<PracticeRuntime> {
  runtimeRequest ??= (async () => {
    const [logic, layer, loader] = await Promise.all([
      import("./public-practice"),
      import("@/components/public-practice-layer"),
      import("./flood-timeline-command-data"),
    ]);
    const signal = new AbortController().signal;
    const replay = await loader.loadCommandReplay(signal);
    const [hand, exercise] = await Promise.all([
      loader.loadCommandHand(replay.manifest, signal).catch(() => null),
      loader.loadCommandExercise(signal),
    ]);
    return {
      logic,
      layer,
      data: { manifest: replay.manifest, roads: replay.roads, tambons: replay.tambons, nodes: replay.nodes, hand },
      exercise: exercise?.items ?? [],
    };
  })().catch((error: unknown) => {
    runtimeRequest = null;
    throw error;
  });
  return runtimeRequest;
}

let replayKeepRequested = false;

/**
 * Once the replay has been read online, ask the service worker to keep its files, with the message the Command
 * exercise replay and the Studio replay send. The practice then opens without a connection too; without it the page
 * fell back to the day without practice offline unless one of those pages had been opened on the device. The worker
 * acts on it in the competition build alone, and stores each file only when its hash matches this build.
 */
function keepReplayOffline(): void {
  if (replayKeepRequested || process.env.NODE_ENV !== "production" || typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  replayKeepRequested = true;
  navigator.serviceWorker.ready
    .then((registration) => registration.active?.postMessage({ type: "FLOODGUARD_CACHE_CASE_REPLAY" }))
    .catch(() => {
      replayKeepRequested = false;
    });
}

export type PublicPracticeStatus = "off" | "loading" | "ready" | "unavailable";

export interface PublicPractice {
  status: PublicPracticeStatus;
  /** What the page says for the chosen scenario; set when `status` is "ready". */
  view?: PracticeView;
  /** Draws the scenario on the map (`GeoMap`'s `overlay`); set when `status` is "ready". */
  overlay?: (map: LeafletMap, leaflet: LeafletModule) => () => void;
}

/**
 * The practice replay of the Public home map for the chosen scenario, in the reader's language. With no scenario
 * nothing is loaded and nothing is drawn.
 */
export function usePublicPractice(scenarioId: PracticeState | null, language: Language): PublicPractice {
  const [runtime, setRuntime] = useState<PracticeRuntime | null>(null);
  const [failedFor, setFailedFor] = useState<PracticeState | null>(null);
  const scenario = practiceScenario(scenarioId);

  useEffect(() => {
    if (!scenarioId || runtime) return;
    let current = true;
    loadPracticeRuntime().then(
      (loaded) => {
        if (current) setRuntime(loaded);
      },
      () => {
        if (current) setFailedFor(scenarioId);
      },
    );
    return () => {
      current = false;
    };
  }, [runtime, scenarioId]);

  useEffect(() => {
    if (runtime) keepReplayOffline();
  }, [runtime]);

  const view = useMemo(
    () => (runtime && scenario ? runtime.logic.practiceView(runtime.data, runtime.exercise, scenario, language) : null),
    [language, runtime, scenario],
  );
  const overlay = useMemo(() => {
    if (!runtime || !view) return undefined;
    const { layer, data } = runtime;
    const frame = { home: view.home, stage: view.status.stage, showPeakExtent: view.showPeakExtent, reports: view.reports, language };
    return (map: LeafletMap, leaflet: LeafletModule) => layer.mountPracticeLayers(leaflet, map, data, frame);
  }, [language, runtime, view]);

  if (!scenario) return { status: "off" };
  if (view && overlay) return { status: "ready", view, overlay };
  // The replay is loaded but has nothing for this scenario, or it could not be loaded for this choice.
  if (runtime || failedFor === scenarioId) return { status: "unavailable" };
  return { status: "loading" };
}
