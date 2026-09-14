"use client";

import dynamic from "next/dynamic";
import { Component, type ReactNode, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Pause, Play } from "lucide-react";
import { createStoryStore, mapStoryProgress } from "@/lib/landing/story-store";
import { DESKTOP_STORY_BOUNDARIES, DESKTOP_STORY_CHAPTERS, DESKTOP_STORY_OPENING_BOUNDARIES, sampleDesktopStory } from "@/lib/landing/sample-desktop-story";

gsap.registerPlugin(useGSAP, ScrollTrigger);

const DesktopNarrativeCanvas = dynamic(() => import("./desktop-narrative-canvas.client"), {
  ssr: false,
  loading: () => null,
});

type Connection = EventTarget & { saveData?: boolean };
type ReadingPosition = { element: HTMLElement; top: number; key?: string; chapterId?: string; scope?: HTMLElement };

function isReadable(element: HTMLElement): boolean {
  const bounds = element.getBoundingClientRect();
  if (bounds.width < 8 || bounds.height < 8) return false;
  for (let ancestor: HTMLElement | null = element; ancestor; ancestor = ancestor.parentElement) {
    const style = getComputedStyle(ancestor);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
  }
  return true;
}

function captureReadingPosition(element: HTMLElement): ReadingPosition | null {
  const threshold = 180;
  const candidates = Array.from(element.querySelectorAll<HTMLElement>("[data-story-reading], h2, p"))
    .filter(isReadable)
    .map((candidate) => ({ element: candidate, bounds: candidate.getBoundingClientRect() }))
    .filter(({ bounds }) => bounds.height > 0 && bounds.bottom > threshold && bounds.top < window.innerHeight);
  candidates.sort((a, b) => Number(b.element.hasAttribute("data-story-reading")) - Number(a.element.hasAttribute("data-story-reading"))
    || Math.abs(a.bounds.top - threshold) - Math.abs(b.bounds.top - threshold));
  const selected = candidates[0];
  if (!selected) return null;
  const chapter = selected.element.closest<HTMLElement>("[data-story-chapter], [data-story-panel]");
  return {
    element: selected.element,
    top: selected.bounds.top,
    key: selected.element.dataset.storyReading,
    chapterId: chapter?.dataset.storyPanel ?? chapter?.id,
    scope: element,
  };
}

function restoreReadingPosition(position: ReadingPosition | null): void {
  if (!position) return;
  const chapterId = position.chapterId ?? position.key;
  if (chapterId && position.scope?.dataset.renderMode === "enhanced") {
    // Fixed copy cannot move with scroll; restore its corresponding semantic chapter instead.
    const section = Array.from(position.scope.querySelectorAll<HTMLElement>("[data-story-chapter]"))
      .find((candidate) => candidate.id === chapterId);
    if (section) {
      section.scrollIntoView({ block: "start", behavior: "instant" });
      return;
    }
  }
  const counterpart = position.key ? Array.from(position.scope?.querySelectorAll<HTMLElement>("[data-story-reading]") ?? [])
    .find((element) => element.dataset.storyReading === position.key && isReadable(element)) : undefined;
  const element = counterpart ?? position.element;
  if (!element.isConnected) return;
  const difference = element.getBoundingClientRect().top - position.top;
  if (Math.abs(difference) > 1) window.scrollBy({ top: difference, behavior: "instant" });
}

function fragmentPosition(element: HTMLElement): ReadingPosition | null {
  if (!window.location.hash) return null;
  try {
    const target = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
    return target && element.contains(target)
      ? { element: target, top: Number.parseFloat(getComputedStyle(target).scrollMarginTop) || 116 }
      : null;
  } catch {
    return null;
  }
}

function canRenderScene(): boolean {
  try {
    const probe = document.createElement("canvas");
    const context = probe.getContext("webgl2", { powerPreference: "low-power" });
    if (!context) return false;
    context.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

function getConnection(): Connection | undefined {
  return (navigator as Navigator & { connection?: Connection }).connection;
}

function getMotionSnapshot(): string {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? "reduced"
    : window.innerWidth < 1100 || window.innerHeight < 700
      ? "compact"
      : getConnection()?.saveData
        ? "data-saving"
        : navigator.onLine === false
          ? "offline"
          : !("IntersectionObserver" in window) || !("ResizeObserver" in window)
            ? "unsupported"
            : "eligible";
}

function subscribeMotion(notify: () => void): () => void {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const connection = getConnection();
  window.addEventListener("resize", notify);
  window.addEventListener("online", notify);
  window.addEventListener("offline", notify);
  reducedMotion.addEventListener("change", notify);
  connection?.addEventListener("change", notify);
  return () => {
    window.removeEventListener("resize", notify);
    window.removeEventListener("online", notify);
    window.removeEventListener("offline", notify);
    reducedMotion.removeEventListener("change", notify);
    connection?.removeEventListener("change", notify);
  };
}

function subscribeVisibility(notify: () => void): () => void {
  document.addEventListener("visibilitychange", notify);
  return () => document.removeEventListener("visibilitychange", notify);
}

class SceneBoundary extends Component<{
  children: ReactNode;
  onFailure: (reason?: string) => void;
}, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onFailure("renderer-load-failed");
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

interface NarrativeExperienceProps {
  children: ReactNode;
  poster?: ReactNode;
  opening?: ReactNode;
  openingVisual?: ReactNode;
  desktopOverlay?: ReactNode;
  desktopPoster?: ReactNode;
  chapterIds?: readonly string[];
  chapterLabels?: readonly string[];
}

const DEFAULT_CHAPTER_IDS = DESKTOP_STORY_CHAPTERS.map(({ id }) => id);
const DEFAULT_CHAPTER_LABELS = DESKTOP_STORY_CHAPTERS.map(({ label }) => label);

function sceneCaption(progress: number): string {
  const frame = sampleDesktopStory(progress);
  if (frame.chapterId === "place") return "Synthetic neighborhood: homes connected to an illustrative essential facility.";
  if (frame.chapterId === "flood") return "Illustrative flood evidence. Overlap alone does not confirm a road closure.";
  if (frame.chapterId === "access") return "One connection is assumed disrupted. Road and facility status remain unconfirmed.";
  return "Synthetic planning finding. Verify the connection and review contingency options.";
}

export default function NarrativeExperience({
  children,
  poster,
  opening,
  openingVisual,
  desktopOverlay,
  desktopPoster,
  chapterIds = DEFAULT_CHAPTER_IDS,
  chapterLabels = DEFAULT_CHAPTER_LABELS,
}: NarrativeExperienceProps) {
  const root = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const desktopPosterElement = useRef<HTMLDivElement | null>(null);
  const posterDecodeGeneration = useRef(0);
  const pendingReadingPosition = useRef<ReadingPosition | null>(null);
  const initialFragment = useRef<ReadingPosition | null>(null);
  const hasEnhanced = useRef(false);
  const [store] = useState(createStoryStore);
  const [prepared, setPrepared] = useState(false);
  const [inView, setInView] = useState(false);
  const [ready, setReady] = useState(false);
  const [desktopPosterReady, setDesktopPosterReady] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [motionReduced, setMotionReduced] = useState(false);
  const subscribeToMotion = useCallback((notify: () => void) => {
    let previous = getMotionSnapshot();
    return subscribeMotion(() => {
      const next = getMotionSnapshot();
      if (next === previous) return;
      pendingReadingPosition.current = root.current ? captureReadingPosition(root.current) : null;
      if (root.current) root.current.dataset.annotationReady = "false";
      setReady(false);
      previous = next;
      notify();
    });
  }, []);
  const policy = useSyncExternalStore(subscribeToMotion, getMotionSnapshot, () => "pending");
  const eligible = policy === "eligible" && !motionReduced && failure === null;
  const visible = useSyncExternalStore(subscribeVisibility, () => document.visibilityState !== "hidden", () => false);
  const getChapter = useCallback(() => sampleDesktopStory(store.getSnapshot()).chapterIndex, [store]);
  const chapter = useSyncExternalStore(store.subscribe, getChapter, () => 0);
  const getCaption = useCallback(() => sceneCaption(store.getSnapshot()), [store]);
  const caption = useSyncExternalStore(store.subscribe, getCaption, () => sceneCaption(0));
  const getBeat = useCallback(() => sampleDesktopStory(store.getSnapshot()).beat, [store]);
  const beat = useSyncExternalStore(store.subscribe, getBeat, () => sampleDesktopStory(0).beat);
  const chapterId = DESKTOP_STORY_CHAPTERS[chapter].id;
  const enhanced = eligible;

  const decodeDesktopPoster = useCallback((image: HTMLImageElement) => {
    const container = desktopPosterElement.current;
    if (!container?.contains(image) || !image.complete || image.naturalWidth <= 0) return;
    const generation = ++posterDecodeGeneration.current;
    const source = image.currentSrc || image.src;
    const decoded = typeof image.decode === "function" ? image.decode() : Promise.resolve();
    void decoded.then(() => {
      if (generation === posterDecodeGeneration.current && desktopPosterElement.current === container
        && container.contains(image) && image.naturalWidth > 0 && (image.currentSrc || image.src) === source) {
        setDesktopPosterReady(true);
      }
    }).catch(() => {
      // A failed poster decode keeps the existing aerial visible until the scene is ready.
    });
  }, []);

  const attachDesktopPoster = useCallback((element: HTMLDivElement | null) => {
    desktopPosterElement.current = element;
    posterDecodeGeneration.current += 1;
    setDesktopPosterReady(false);
    const image = element?.querySelector("img");
    if (image) decodeDesktopPoster(image);
  }, [decodeDesktopPoster]);

  const onReady = useCallback(() => {
    initialFragment.current = null;
    setReady(true);
  }, []);
  const onPending = useCallback(() => {
    if (root.current) root.current.dataset.annotationReady = "false";
    setReady(false);
  }, []);
  const onFailure = useCallback((reason?: string) => {
    initialFragment.current = null;
    pendingReadingPosition.current = root.current ? captureReadingPosition(root.current) : null;
    if (root.current) root.current.dataset.annotationReady = "false";
    setReady(false);
    setFailure(reason ?? "renderer-unavailable");
  }, []);

  useEffect(() => {
    const cancelFragmentRestore = () => {
      initialFragment.current = null;
      pendingReadingPosition.current = null;
    };
    const events = ["wheel", "touchstart", "pointerdown", "keydown"] as const;
    events.forEach((event) => window.addEventListener(event, cancelFragmentRestore, { passive: true }));
    return () => events.forEach((event) => window.removeEventListener(event, cancelFragmentRestore));
  }, []);

  useEffect(() => {
    const element = content.current;
    if (!element || !eligible || !inView || prepared || !("IntersectionObserver" in window)) return;
    let nearStory = false;
    let started = false;
    const prepare = () => {
      if (!nearStory || started) return;
      started = true;
      prepareObserver.disconnect();
      if (!canRenderScene()) {
        onFailure("webgl-unavailable");
        return;
      }
      setPrepared(true);
    };
    const prepareObserver = new IntersectionObserver(([entry]) => {
      nearStory = entry.isIntersecting;
      prepare();
    }, { rootMargin: "100px 0px" });
    const unsubscribe = store.subscribe(prepare);
    prepareObserver.observe(element);
    return () => {
      unsubscribe();
      prepareObserver.disconnect();
    };
  }, [eligible, inView, prepared, onFailure, store]);

  useEffect(() => {
    const element = stage.current?.querySelector("[data-story-visual]");
    if (!element || !("IntersectionObserver" in window)) return;
    const visibilityObserver = new IntersectionObserver(([entry]) => {
      setInView(entry.isIntersecting);
    });
    visibilityObserver.observe(element);
    return () => visibilityObserver.disconnect();
  }, [enhanced]);

  useEffect(() => {
    if (!enhanced || !stage.current || !root.current) return;
    const element = root.current;
    let frame = 0;
    const updateInset = () => {
      frame = 0;
      // The sticky stage initially sits below the header, outside viewport zero.
      element.style.setProperty("--stage-viewport-offset", `${Math.max(0, stage.current?.getBoundingClientRect().top ?? 0)}px`);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(updateInset); };
    updateInset();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      element.style.removeProperty("--stage-viewport-offset");
    };
  }, [enhanced]);

  useGSAP(() => {
    if (policy === "pending" && root.current && content.current && window.scrollY > 0) {
      // Native reload restoration uses the SSR layout before desktop enhancement compacts it.
      initialFragment.current = fragmentPosition(content.current) ?? captureReadingPosition(root.current);
    }
    if (enhanced && !hasEnhanced.current && content.current) {
      hasEnhanced.current = true;
      initialFragment.current = fragmentPosition(content.current) ?? initialFragment.current;
    }
    if (!enhanced) {
      restoreReadingPosition(pendingReadingPosition.current);
      pendingReadingPosition.current = null;
    }
  }, { scope: root, dependencies: [enhanced, policy], revertOnUpdate: true });

  useGSAP(() => {
    if (!enhanced || !root.current || !content.current) return;
    const sections = Array.from(content.current.querySelectorAll<HTMLElement>("[data-story-chapter]"));
    if (sections.length !== DESKTOP_STORY_CHAPTERS.length) return;
    const openingElement = content.current.querySelector<HTMLElement>("[data-story-opening]");
    const boundaries = openingElement ? DESKTOP_STORY_OPENING_BOUNDARIES : DESKTOP_STORY_BOUNDARIES;
    const clock = { position: 0 };
    let start = 0;
    let end = 1;
    let anchors: readonly number[] = boundaries;
    const measure = () => {
      const stageTop = stage.current ? Number.parseFloat(getComputedStyle(stage.current).top) || 112 : 112;
      const threshold = Math.max(112, stageTop) + Math.min(160, window.innerHeight * 0.16);
      const positions = sections.map((section) => section.getBoundingClientRect().top + window.scrollY - threshold);
      const endMarker = content.current?.querySelector<HTMLElement>("[data-story-end]");
      const finalSection = sections[sections.length - 1];
      positions.push(endMarker
        ? endMarker.getBoundingClientRect().top + window.scrollY - threshold
        : finalSection.getBoundingClientRect().bottom + window.scrollY - threshold);
      if (openingElement) {
        const openingBounds = openingElement.getBoundingClientRect();
        positions.unshift(Math.min(positions[0] - 1, openingBounds.top + window.scrollY));
        root.current?.style.setProperty("--opening-height", `${openingBounds.height}px`);
      }
      start = positions[0];
      end = Math.max(start + 1, positions[positions.length - 1]);
      anchors = positions.map((position) => (position - start) / (end - start));
      if (root.current) root.current.dataset.storyScrollStops = JSON.stringify(positions.map((scrollY, index) => ({ scrollY, progress: boundaries[index] })));
    };

    measure();
    pendingReadingPosition.current ??= initialFragment.current;
    const update = () => {
      const progress = mapStoryProgress(clock.position, anchors, boundaries);
      store.setProgress(progress);
      const frame = sampleDesktopStory(progress);
      const element = root.current;
      if (!element) return;
      element.style.setProperty("--desktop-cover-progress", frame.coverProgress.toFixed(5));
      element.style.setProperty("--desktop-interlude", "0");
      element.style.setProperty("--desktop-flight", frame.flight.toFixed(5));
      element.style.setProperty("--desktop-flood", frame.flood.toFixed(5));
      element.style.setProperty("--desktop-network", frame.network.toFixed(5));
      element.style.setProperty("--desktop-result", frame.result.toFixed(5));
      element.dataset.desktopProgress = progress.toFixed(6);
      element.dataset.desktopCoverProgress = frame.coverProgress.toFixed(5);
      element.dataset.desktopInterlude = "0";
      element.dataset.desktopFlight = frame.flight.toFixed(5);
      element.dataset.desktopFlood = frame.flood.toFixed(5);
      element.dataset.networkProgress = frame.network.toFixed(5);
      element.dataset.resultProgress = frame.result.toFixed(5);
      element.dataset.assumptionApplied = String(frame.assumptionApplied);
    };
    const tween = gsap.fromTo(clock, { position: 0 }, {
      position: 1,
      ease: "none",
      immediateRender: false,
      onUpdate: update,
      scrollTrigger: {
        trigger: root.current,
        start: () => start,
        end: () => end,
        scrub: 0.45,
        invalidateOnRefresh: true,
        onRefreshInit: measure,
        onRefresh: update,
      },
    });
    tween.totalProgress(Math.min(1, Math.max(0, (window.scrollY - start) / (end - start))));
    update();

    let disposed = false;
    let refreshFrame = 0;
    const refresh = () => {
      cancelAnimationFrame(refreshFrame);
      refreshFrame = requestAnimationFrame(() => {
        if (!disposed) {
          tween.scrollTrigger?.refresh();
          const position = pendingReadingPosition.current ?? initialFragment.current;
          if (position) {
            // Restore only after the new layout is measured, then settle its scrub immediately.
            restoreReadingPosition(position);
            pendingReadingPosition.current = null;
            ScrollTrigger.update();
            tween.scrollTrigger?.getTween()?.progress(1);
            update();
          }
        }
      });
    };
    refresh();
    const measuredSizes = new WeakMap<Element, { width: number; height: number }>();
    const observer = new ResizeObserver((entries) => {
      let changed = false;
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const previous = measuredSizes.get(entry.target);
        if (previous && Math.abs(width - previous.width) < 1 && Math.abs(height - previous.height) < 1) continue;
        measuredSizes.set(entry.target, { width, height });
        changed = true;
      }
      if (changed) refresh();
    });
    observer.observe(content.current);
    if (openingElement) observer.observe(openingElement);
    void document.fonts.ready.then(() => {
      if (!disposed) refresh();
    });
    const onHashChange = () => {
      initialFragment.current = null;
      pendingReadingPosition.current = null;
      refresh();
    };
    window.addEventListener("hashchange", onHashChange);
    return () => {
      disposed = true;
      observer.disconnect();
      window.removeEventListener("hashchange", onHashChange);
      cancelAnimationFrame(refreshFrame);
    };
  }, { scope: root, dependencies: [enhanced, store], revertOnUpdate: true });

  const toggleMotion = () => {
    initialFragment.current = null;
    pendingReadingPosition.current = root.current ? captureReadingPosition(root.current) : null;
    if (root.current) root.current.dataset.annotationReady = "false";
    setReady(false);
    setMotionReduced((value) => !value);
  };
  const motionLabel = motionReduced ? "Enable motion" : "Reduce motion";
  const motionDisabledReason = policy === "reduced" ? "Reduced motion is enabled on your device"
    : policy === "compact" ? "Still illustrations on this screen size"
      : policy === "data-saving" ? "Data saving is enabled on your device"
        : policy === "offline" ? "Offline illustrations"
          : policy === "unsupported" ? "Still illustrations in this browser"
            : failure ? "Still illustrations are available" : undefined;

  return (
    <div ref={root} data-story data-story-variant={eligible ? "desktop-world" : undefined} data-render-mode={enhanced ? "enhanced" : "static"} data-motion-policy={policy} data-motion-preference={motionReduced ? "reduced" : "auto"} data-active-chapter={chapter} data-active-chapter-id={chapterId} data-story-beat={beat} data-desktop-beat={eligible ? beat : undefined} data-scene-ready={ready ? "true" : "false"} data-annotation-ready={ready ? "true" : "false"} data-desktop-poster-ready={eligible && desktopPosterReady ? "true" : "false"} data-render-failure={failure ?? undefined}>
      <div data-motion-controls>
        <button type="button" onClick={toggleMotion} disabled={policy !== "eligible" || failure !== null} aria-label={motionLabel} title={motionDisabledReason ?? motionLabel}>
          {motionReduced ? <Play size={18} aria-hidden="true" /> : <Pause size={18} aria-hidden="true" />}
        </button>
      </div>
      <div data-story-layout>
        <div ref={stage} data-story-stage data-active-chapter={chapter} data-active-chapter-id={chapterId} data-story-beat={beat} data-scene-ready={ready ? "true" : "false"}>
          <div data-story-visual>
            {poster}
            {eligible && desktopPoster ? <div ref={attachDesktopPoster} data-desktop-poster onLoadCapture={(event) => {
              if (event.target instanceof HTMLImageElement) decodeDesktopPoster(event.target);
            }}>{desktopPoster}</div> : null}
            {prepared && eligible ? (
              <div data-story-canvas data-scene-active={eligible && inView && visible ? "true" : "false"} aria-hidden="true">
                <SceneBoundary onFailure={onFailure}>
                  <DesktopNarrativeCanvas store={store} onReady={onReady} onPending={onPending} onFailure={onFailure} active={eligible && inView && visible} />
                </SceneBoundary>
              </div>
            ) : null}
            {openingVisual ? <div data-story-aerial>{openingVisual}</div> : null}
          </div>
          {eligible && desktopOverlay ? <div data-desktop-overlay aria-hidden="true">{desktopOverlay}</div> : null}
          <p data-story-caption>Illustrative scenario · Not current conditions</p>
          <p data-story-status>{caption}</p>
          <nav data-story-controls aria-label="Story chapters">
            {chapterIds.map((id, index) => (
              <a key={id} href={`#${id}`} aria-current={chapter === index ? "step" : undefined}>
                {chapterLabels[index] ?? DEFAULT_CHAPTER_LABELS[index] ?? id}
              </a>
            ))}
          </nav>
        </div>
        <div ref={content} data-story-content>
          {opening ? <div data-story-opening>{opening}</div> : null}
          {children}
          <div data-story-end aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}
