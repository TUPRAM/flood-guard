"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { PHONE_PAGE_FILL, quadBounds, quadIsDrawable, quadToMatrix3d, type Quad } from "@/lib/journey/screen-projection";
import {
  CHAPTERS,
  TIMELINE_END,
  chapterAt,
  chapterEntry,
  clampScrollTarget,
  locate,
  parseScene,
  sceneAt,
  scenePosition,
  stepToward,
  stopAt,
  stopPosition,
  storyBeats,
  type ChapterId,
  type SceneId,
  type SegmentId,
  type StopId,
} from "@/lib/journey/timeline";
import { useLanguage } from "@/lib/use-language";

import { CAPTIONS, CHAPTER_LABELS, LABELS, STOPS, UI, stopFrameSrc, type JourneyLanguage } from "./journey-copy";
import type { JourneyStage, ScreenAspects, ScreenId, StageFrame } from "./stage/journey-stage";

import styles from "./journey.module.css";

/** Which 3D screen hosts the real page for each stop. */
const STOP_SCREEN: Record<StopId, ScreenId> = { public: "phone", "public-sos": "phone", case: "monitor", command: "table" };
const SCREEN_STOP: Record<ScreenId, StopId> = { phone: "public", monitor: "case", table: "command" };
const SCENE_ORDER: SceneId[] = ["opening", "everyday", "public", "conditions", "public-sos", "affected", "case", "response", "command"];
const REDUCED_MOTION_KEY = "floodguard:journey:reduced-motion";
const FADE_MS = 260;

interface Sizes {
  width: number;
  height: number;
  mobile: boolean;
  aspects: ScreenAspects;
  /** CSS pixel size each real page is laid out at while it sits on a 3D screen. */
  css: Record<ScreenId, { width: number; height: number }>;
  /** True when docking leaves the page at exactly the size it had on the screen (no reflow). */
  exact: Record<ScreenId, boolean>;
}

export function computeSizes(width: number, height: number): Sizes {
  const ratio = width / height;
  const mobile = width < 700 || ratio < 0.9;
  const phoneAspect = mobile ? Math.min(0.62, Math.max(0.42, ratio)) : 0.4615;
  // On desktop the public app is laid out at a real phone size (at least 390 CSS px wide), whatever the window height:
  // short windows and zoomed browsers would otherwise give it a column too narrow for its layout. The projection
  // scales the page onto the 3D phone, so the CSS size need not match the window.
  const phoneWidth = Math.max(390, Math.round(height * phoneAspect));
  const landscapeExact = ratio >= 1.2 && ratio <= 2.2;
  const landscapeAspect = landscapeExact ? ratio : 1.6;
  const landscapeCss = landscapeExact ? { width, height } : { width: 1280, height: 800 };
  return {
    width,
    height,
    mobile,
    aspects: { phone: phoneAspect, monitor: landscapeAspect, table: landscapeAspect },
    css: {
      phone: mobile ? { width, height } : { width: phoneWidth, height: Math.round(phoneWidth / phoneAspect) },
      monitor: landscapeCss,
      table: landscapeCss,
    },
    exact: { phone: true, monitor: landscapeExact, table: landscapeExact },
  };
}

interface View {
  segment: SegmentId;
  caption: number;
  chapter: ChapterId;
  docked: StopId | null;
  heroVisible: boolean;
  atStart: boolean;
  atEnd: boolean;
}

function captionIndex(segment: SegmentId, progress: number): number {
  return CAPTIONS[segment].findIndex((caption) => progress >= caption.from && progress < caption.to);
}

const REDUCED_MOTION_EVENT = "floodguard:journey:reduced-motion";

function readReducedMotion(): boolean {
  try {
    const stored = window.localStorage.getItem(REDUCED_MOTION_KEY);
    if (stored === "on") return true;
    if (stored === "off") return false;
  } catch {
    // Storage can be unavailable; fall back to the system preference.
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function subscribeReducedMotion(notify: () => void): () => void {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", notify);
  window.addEventListener(REDUCED_MOTION_EVENT, notify);
  return () => {
    query.removeEventListener("change", notify);
    window.removeEventListener(REDUCED_MOTION_EVENT, notify);
  };
}

/** The visitor's reduced-motion choice (stored toggle first, then the system setting). */
function useReducedMotion(): [boolean, (next: boolean) => void] {
  const value = useSyncExternalStore(subscribeReducedMotion, readReducedMotion, () => false);
  const change = useCallback((next: boolean) => {
    try { window.localStorage.setItem(REDUCED_MOTION_KEY, next ? "on" : "off"); } catch { /* optional */ }
    window.dispatchEvent(new Event(REDUCED_MOTION_EVENT));
  }, []);
  return [value, change];
}

export function JourneyExperience() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fadeRef = useRef<HTMLDivElement>(null);
  const hostRefs = useRef<Record<ScreenId, HTMLDivElement | null>>({ phone: null, monitor: null, table: null });
  const frameRefs = useRef<Record<ScreenId, HTMLIFrameElement | null>>({ phone: null, monitor: null, table: null });
  /** Where each page was last drawn on its 3D screen: docking starts there, undocking returns there. */
  const lastQuads = useRef<Partial<Record<ScreenId, Quad>>>({});
  const labelRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const barRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<JourneyStage | null>(null);
  const sizesRef = useRef<Sizes | null>(null);
  const motion = useRef({ target: 0, display: 0, docked: null as StopId | null, busy: false, reduced: false, wheelBuffer: 0, lastScene: "" as string, fromPopState: false });

  // The same shared preference the FloodGuard pages use, so the real pages follow the story's language.
  const [language, changeLanguage] = useLanguage("en") as [JourneyLanguage, (next: JourneyLanguage) => void];
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  const [reducedMotion, setReducedMotion] = useReducedMotion();
  const [view, setView] = useState<View>({ segment: "opening", caption: -1, chapter: "opening", docked: null, heroVisible: true, atStart: true, atEnd: false });
  const [mounted, setMounted] = useState<Record<ScreenId, boolean>>({ phone: false, monitor: false, table: false });
  const [loaded, setLoaded] = useState<Record<ScreenId, boolean>>({ phone: false, monitor: false, table: false });
  const [skipOpen, setSkipOpenState] = useState(false);
  const skipTrigger = useRef<HTMLElement | null>(null);
  const skipDialog = useRef<HTMLDivElement>(null);
  const setSkipOpen = useCallback((open: boolean) => {
    if (open) skipTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSkipOpenState(open);
    // Return focus to whatever opened the dialog.
    if (!open) window.setTimeout(() => skipTrigger.current?.focus(), 0);
  }, []);
  /** Keeps keyboard focus inside the skip dialog; Escape closes it. */
  const onSkipKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setSkipOpen(false);
      return;
    }
    if (event.key !== "Tab" || !skipDialog.current) return;
    const focusable = Array.from(skipDialog.current.querySelectorAll<HTMLElement>("button, a[href]"));
    if (focusable.length === 0) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  const [announcement, setAnnouncement] = useState("");
  const [sizes, setSizes] = useState<Sizes | null>(null);

  const tr = useCallback((text: Record<JourneyLanguage, string>) => text[language], [language]);
  const trRef = useRef(tr);
  useEffect(() => { trRef.current = tr; }, [tr]);
  /** Each real page keeps the address it was first opened with, so a language switch never reloads it. */
  const frameSrc = useRef<Partial<Record<ScreenId, string>>>({});

  // --- Preferences -------------------------------------------------------------------------------------------------
  useEffect(() => { motion.current.reduced = reducedMotion; }, [reducedMotion]);
  const toggleReducedMotion = () => setReducedMotion(!reducedMotion);

  // --- Real-page hosts ---------------------------------------------------------------------------------------------
  const ensureMounted = useCallback((screen: ScreenId) => {
    setMounted((current) => (current[screen] ? current : { ...current, [screen]: true }));
  }, []);

  /**
   * While a real page sits on a 3D screen its own scrollbar is hidden (it would show as a grey bar on the device);
   * docked, the page is itself again. Same-origin frames, so the parent can set this on the framed document.
   */
  const setFrameScrollbar = useCallback((screen: ScreenId, visible: boolean) => {
    try {
      const root = frameRefs.current[screen]?.contentDocument?.documentElement;
      if (root) root.style.setProperty("scrollbar-width", visible ? "" : "none");
    } catch {
      /* not reachable (still loading); applied again on load */
    }
  }, []);

  /** Puts a host into "on a 3D screen" mode at its CSS layout size. */
  const projectHost = useCallback((screen: ScreenId) => {
    const host = hostRefs.current[screen];
    const size = sizesRef.current;
    if (!host || !size) return;
    setFrameScrollbar(screen, false);
    host.dataset.mode = "screen";
    host.style.transition = "";
    host.style.left = "0px";
    host.style.top = "0px";
    host.style.width = `${size.css[screen].width}px`;
    host.style.height = `${size.css[screen].height}px`;
  }, [setFrameScrollbar]);

  const barHeight = () => barRef.current?.getBoundingClientRect().height ?? 0;

  /**
   * The rectangle a page occupies at the end of the push onto its screen: where it was last drawn there, or (when the
   * story opened directly at a stop) where the end pose puts it. The page keeps its layout size and is scaled.
   */
  const endRect = useCallback((screen: ScreenId) => {
    const size = sizesRef.current!;
    const css = size.css[screen];
    const quad = lastQuads.current[screen];
    if (quad && quadIsDrawable(quad, size.width, size.height)) {
      const bounds = quadBounds(quad);
      return { left: bounds.left, top: bounds.top, width: css.width, height: css.height, scale: bounds.height / css.height };
    }
    const scale = (size.height * (screen === "phone" ? PHONE_PAGE_FILL : 1)) / css.height;
    return { left: (size.width - css.width * scale) / 2, top: (size.height - css.height * scale) / 2, width: css.width, height: css.height, scale };
  }, []);

  /** Docks a host: the real page becomes the viewport and receives input. */
  const dockHost = useCallback((screen: ScreenId, animate: boolean) => {
    const host = hostRefs.current[screen];
    const size = sizesRef.current;
    if (!host || !size) return;
    // Start from exactly where the page sits at the end of the push (on the phone, inside its border), then open out
    // to the whole viewport.
    const start = endRect(screen);
    setFrameScrollbar(screen, true);
    host.dataset.mode = "docked";
    host.style.transformOrigin = "0 0";
    host.style.transform = `scale(${start.scale})`;
    host.style.opacity = "1";
    host.style.visibility = "visible";
    host.style.transition = "";
    host.style.left = `${start.left}px`;
    host.style.top = `${start.top}px`;
    host.style.width = `${start.width}px`;
    host.style.height = `${start.height}px`;
    const settle = () => {
      host.style.transition = animate ? "left 620ms cubic-bezier(.65,0,.35,1), width 620ms cubic-bezier(.65,0,.35,1), top 420ms ease, height 420ms ease, transform 620ms cubic-bezier(.65,0,.35,1)" : "";
      host.style.transform = "none";
      host.style.left = "0px";
      host.style.width = "100%";
      host.style.top = `var(--journey-bar, 0px)`;
      host.style.height = `calc(100% - var(--journey-bar, 0px))`;
    };
    if (!size.exact[screen] && animate) {
      host.style.opacity = "0";
      window.setTimeout(() => { settle(); host.style.transition = "opacity 220ms ease"; host.style.opacity = "1"; }, 120);
    } else if (animate) {
      requestAnimationFrame(() => requestAnimationFrame(settle));
    } else settle();
  }, [endRect, setFrameScrollbar]);

  /** Reverse of docking: back to the end-of-push rectangle, then onto the 3D screen. */
  const undockHost = useCallback((screen: ScreenId, animate: boolean): Promise<void> => {
    const host = hostRefs.current[screen];
    const size = sizesRef.current;
    if (!host || !size) return Promise.resolve();
    if (!animate) {
      projectHost(screen);
      return Promise.resolve();
    }
    const end = endRect(screen);
    host.style.transition = "left 420ms cubic-bezier(.65,0,.35,1), width 420ms cubic-bezier(.65,0,.35,1), top 420ms cubic-bezier(.65,0,.35,1), height 420ms cubic-bezier(.65,0,.35,1), transform 420ms cubic-bezier(.65,0,.35,1)";
    host.style.transformOrigin = "0 0";
    host.style.transform = `scale(${end.scale})`;
    host.style.left = `${end.left}px`;
    host.style.top = `${end.top}px`;
    host.style.width = `${end.width}px`;
    host.style.height = `${end.height}px`;
    return new Promise((resolve) => window.setTimeout(() => { projectHost(screen); resolve(); }, 440));
  }, [endRect, projectHost]);

  // --- Navigation --------------------------------------------------------------------------------------------------
  const updateHistory = useCallback((scene: SceneId, push: boolean) => {
    const url = new URL(window.location.href);
    url.searchParams.set("scene", scene);
    if (url.href === window.location.href) return;
    if (push) window.history.pushState({ scene }, "", url);
    else window.history.replaceState({ scene }, "", url);
  }, []);

  const undockIfNeeded = useCallback(async (animate: boolean) => {
    const m = motion.current;
    if (!m.docked) return;
    const screen = STOP_SCREEN[m.docked];
    m.docked = null;
    m.busy = true;
    setView((current) => ({ ...current, docked: null }));
    if (canvasRef.current) canvasRef.current.style.visibility = "visible";
    await undockHost(screen, animate);
    m.busy = false;
  }, [undockHost]);

  /** Animate (or, with reduced motion / long distances, cross-fade) to a timeline position. */
  const goTo = useCallback(async (position: number, options: { animate?: boolean } = {}) => {
    const m = motion.current;
    const destination = Math.min(TIMELINE_END, Math.max(0, position));
    const far = Math.abs(destination - m.display) > 2.6;
    const animate = options.animate ?? (!m.reduced && !far);
    await undockIfNeeded(!m.reduced);
    if (animate) {
      m.target = destination;
      return;
    }
    const fade = fadeRef.current;
    if (fade) fade.dataset.on = "true";
    // Freeze the timeline while the screen is covered, so the old position cannot re-dock the page just left.
    m.busy = true;
    await new Promise((resolve) => window.setTimeout(resolve, m.reduced ? 120 : FADE_MS));
    m.display = m.target = destination;
    m.busy = false;
    // Let one frame render at the new position before revealing it.
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (fade) fade.dataset.on = "false";
  }, [undockIfNeeded]);

  const sceneNeighbour = useCallback((direction: 1 | -1) => {
    const position = motion.current.display;
    const ordered = SCENE_ORDER.map((scene) => ({ scene, at: scenePosition(scene) }));
    const candidate = direction > 0
      ? ordered.find((entry) => entry.at > position + 1e-3)
      : [...ordered].reverse().find((entry) => entry.at < position - 1e-3);
    return candidate ?? null;
  }, []);

  const continueFrom = useCallback((stop: StopId) => {
    const next: Record<StopId, number> = {
      public: stopPosition("public-sos"),
      "public-sos": stopPosition("case"),
      case: stopPosition("command"),
      command: 0,
    };
    if (stop === "command") void goTo(0, { animate: false });
    // With reduced motion the story steps through beats; continuing lands on the next chapter's first beat.
    else if (motion.current.reduced) void goTo(stopPosition(stop) + 0.5, { animate: false });
    else void goTo(next[stop], { animate: true });
  }, [goTo]);

  const backToStory = useCallback((stop: StopId) => {
    void goTo(stopPosition(stop) - 0.55, { animate: !motion.current.reduced });
  }, [goTo]);

  const jumpToStop = useCallback((stop: StopId) => {
    setSkipOpen(false);
    ensureMounted(STOP_SCREEN[stop]);
    void goTo(stopPosition(stop), { animate: false });
  }, [ensureMounted, goTo, setSkipOpen]);

  // --- Stage lifecycle ---------------------------------------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let disposed = false;
    let raf = 0;
    let last = performance.now();
    let stage: JourneyStage | null = null;
    const m = motion.current;

    const initialScene = parseScene(window.location.search);
    if (initialScene) {
      m.display = m.target = scenePosition(initialScene);
    }

    const applySizes = () => {
      const next = computeSizes(window.innerWidth, window.innerHeight);
      sizesRef.current = next;
      setSizes(next);
      stage?.setViewport({ width: next.width, height: next.height }, next.aspects);
      (Object.keys(hostRefs.current) as ScreenId[]).forEach((screen) => {
        const host = hostRefs.current[screen];
        if (host && host.dataset.mode !== "docked") projectHost(screen);
      });
    };

    const onContextLost = (event: Event) => {
      event.preventDefault();
      setStatus("failed");
    };

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!stage || document.hidden) return;
      const size = sizesRef.current;
      if (!size) return;
      if (m.docked) return; // the real page owns the viewport; no 3D rendering while docked

      if (!m.busy) m.display = stepToward(m.display, m.target, dt);
      const position = m.display;
      const result: StageFrame = stage.update(position, dt);

      // Real pages on the 3D screens.
      (Object.keys(result.screens) as ScreenId[]).forEach((screen) => {
        const host = hostRefs.current[screen];
        if (!host || host.dataset.mode === "docked") return;
        const info = result.screens[screen];
        const css = size.css[screen];
        if (info.quad && info.opacity > 0.005 && quadIsDrawable(info.quad, size.width, size.height)) {
          host.style.transform = quadToMatrix3d(css.width, css.height, info.quad);
          lastQuads.current[screen] = info.quad;
          host.style.opacity = String(info.opacity);
          host.style.visibility = "visible";
        } else {
          host.style.visibility = "hidden";
        }
      });

      // Projected labels.
      for (const label of result.labels) {
        const element = labelRefs.current[label.id];
        if (!element) continue;
        element.style.transform = `translate3d(${label.x.toFixed(1)}px, ${label.y.toFixed(1)}px, 0)`;
        element.dataset.visible = String(label.visible);
      }

      // Lazy-load the real pages a little before they are needed.
      if (position > 0.25 || m.target > 0.25) ensureMounted("phone");
      if (position > stopPosition("public") + 0.5 || m.target >= stopPosition("public-sos")) ensureMounted("monitor");
      if (position > stopPosition("case") - 0.4 || m.target >= stopPosition("case")) ensureMounted("table");

      // View state (React only when something visible changes).
      const where = locate(position);
      const caption = captionIndex(where.segment, where.progress);
      const chapter = chapterAt(position);
      const heroVisible = where.segment === "opening" && where.progress < 0.35;
      const atStart = position < 1e-3, atEnd = position > TIMELINE_END - 1e-3;
      setView((current) => (current.segment === where.segment && current.caption === caption && current.chapter === chapter
        && current.heroVisible === heroVisible && current.atStart === atStart && current.atEnd === atEnd
        ? current
        : { ...current, segment: where.segment, caption, chapter, heroVisible, atStart, atEnd }));

      // Address bar: replace while moving, push when a real page is entered.
      const scene = sceneAt(position);
      // Stops are pushed when docked (below); replacing here would overwrite the entry Back should return to.
      if (scene !== m.lastScene && Math.abs(position - m.target) < 1e-4 && !stopAt(position)) {
        m.lastScene = scene;
        if (!m.fromPopState) updateHistory(scene, false);
      }

      // Arrived at a stop: dock the real page.
      const stop = stopAt(position);
      if (stop && Math.abs(position - m.target) < 1e-4 && !m.busy) {
        const screen = STOP_SCREEN[stop];
        ensureMounted(screen);
        m.docked = stop;
        dockHost(screen, !m.reduced);
        canvas.style.visibility = "hidden";
        setView((current) => ({ ...current, docked: stop }));
        setAnnouncement(`${trRef.current(STOPS[stop].page)}. ${trRef.current(STOPS[stop].note)}`);
        if (!m.fromPopState) updateHistory(stop, true);
        m.fromPopState = false;
        window.setTimeout(() => frameRefs.current[screen]?.focus({ preventScroll: true }), 700);
      }
    };

    (async () => {
      try {
        const probe = document.createElement("canvas");
        const gl = probe.getContext("webgl2") ?? probe.getContext("webgl");
        if (!gl) throw new Error("WebGL unavailable");
        const lowPower = window.innerWidth < 700 || (navigator.hardwareConcurrency ?? 8) < 4 || ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8) < 4;
        const { JourneyStage: Stage } = await import("./stage/journey-stage");
        if (disposed) return;
        stage = new Stage(canvas, { quality: lowPower ? "low" : "high" });
        stageRef.current = stage;
        canvas.addEventListener("webglcontextlost", onContextLost);
        applySizes();
        // The rigged people are a few megabytes: wait for them briefly so the story starts with them; if they are
        // slow, start anyway with the procedural figures and swap when they arrive.
        await Promise.race([stage.charactersReady, new Promise((resolve) => window.setTimeout(resolve, 9000))]);
        if (disposed) return;
        stage.precompile();
        stage.update(m.display, 0);
        setStatus("ready");
        last = performance.now();
        raf = requestAnimationFrame(frame);
      } catch {
        if (!disposed) setStatus("failed");
      }
    })();

    // Visual-review hook: jump the camera to a timeline position. Development only, or a production build made with
    // NEXT_PUBLIC_JOURNEY_DEBUG=1 for profiling; normal production builds do not include it.
    const debug = window as Window & { __journeySeek?: (t: number) => void; __journeyStage?: () => JourneyStage | null };
    if (process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_JOURNEY_DEBUG === "1") {
      debug.__journeySeek = (t: number) => { m.display = m.target = t; };
      debug.__journeyStage = () => stage;
    }

    window.addEventListener("resize", applySizes);
    return () => {
      disposed = true;
      delete debug.__journeySeek;
      delete debug.__journeyStage;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", applySizes);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      stage?.dispose();
      stageRef.current = null;
    };
  }, [dockHost, ensureMounted, projectHost, updateHistory]);

  // Mount the public app shortly after load even without input, so the phone screen is ready.
  useEffect(() => {
    if (status !== "ready") return;
    const timer = window.setTimeout(() => ensureMounted("phone"), 1800);
    return () => window.clearTimeout(timer);
  }, [ensureMounted, status]);

  // A newly mounted host starts on its 3D screen.
  useEffect(() => {
    (Object.keys(mounted) as ScreenId[]).forEach((screen) => {
      const host = hostRefs.current[screen];
      if (mounted[screen] && host && !host.dataset.mode) projectHost(screen);
    });
  }, [mounted, projectHost]);

  // Keep the docked page below the story bar.
  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const observer = new ResizeObserver(() => document.documentElement.style.setProperty("--journey-bar", `${barHeight()}px`));
    observer.observe(bar);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty("--journey-bar");
    };
  }, [view.docked]);

  // --- Input -------------------------------------------------------------------------------------------------------
  useEffect(() => {
    const m = motion.current;
    const beats = storyBeats();

    const advance = (delta: number) => {
      if (m.docked || m.busy) return;
      if (m.reduced) {
        m.wheelBuffer += delta;
        if (Math.abs(m.wheelBuffer) < 0.12) return;
        const direction = Math.sign(m.wheelBuffer);
        m.wheelBuffer = 0;
        const next = direction > 0 ? beats.find((beat) => beat > m.display + 1e-3) : [...beats].reverse().find((beat) => beat < m.display - 1e-3);
        if (next === undefined) return;
        void goTo(clampScrollTarget(m.display, next), { animate: false });
        return;
      }
      m.target = clampScrollTarget(m.display, m.target + delta);
    };

    const onWheel = (event: WheelEvent) => {
      if (m.docked) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 32 : event.deltaMode === 2 ? window.innerHeight : 1;
      advance((event.deltaY * unit) / 1700);
    };
    let touchY: number | null = null;
    const onTouchStart = (event: TouchEvent) => { touchY = event.touches[0]?.clientY ?? null; };
    const onTouchMove = (event: TouchEvent) => {
      if (m.docked || touchY === null) return;
      const y = event.touches[0]?.clientY ?? touchY;
      advance(((touchY - y) * 2.2) / 1700);
      touchY = y;
    };
    const onKey = (event: KeyboardEvent) => {
      if (m.docked) return;
      const active = document.activeElement;
      const interactive = active instanceof HTMLButtonElement || active instanceof HTMLAnchorElement || active instanceof HTMLInputElement;
      if (["ArrowDown", "PageDown"].includes(event.key) || (event.key === " " && !interactive)) {
        event.preventDefault();
        advance(0.35);
      } else if (["ArrowUp", "PageUp"].includes(event.key)) {
        event.preventDefault();
        advance(-0.35);
      } else if (event.key === "Home" && !interactive) {
        void goTo(0);
      }
    };
    const onPopState = () => {
      const scene = parseScene(window.location.search) ?? "opening";
      m.fromPopState = true;
      m.lastScene = scene;
      const position = scenePosition(scene);
      const stop = stopAt(position);
      if (stop) ensureMounted(STOP_SCREEN[stop]);
      void goTo(position, { animate: false }).then(() => {
        if (!stop) m.fromPopState = false;
      });
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("keydown", onKey);
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("popstate", onPopState);
    };
  }, [ensureMounted, goTo]);

  // --- Render ------------------------------------------------------------------------------------------------------
  const caption = view.caption >= 0 ? CAPTIONS[view.segment][view.caption] : null;
  const docked = view.docked;
  const stopCopy = docked ? STOPS[docked] : null;
  const chapterIndex = CHAPTERS.indexOf(view.chapter);
  const step = (direction: 1 | -1) => {
    const target = sceneNeighbour(direction);
    if (target) void goTo(target.at);
  };

  return (
    // `data-floodguard-journey` marks this route's chunks as online-only for the offline installer (write-offline-assets.mjs).
    <main id="main-content" className={styles.root} data-docked={docked ? "true" : "false"} data-floodguard-journey="" lang={language}>
      <canvas ref={canvasRef} className={styles.canvas} aria-hidden="true" />

      {/* Real FloodGuard pages, each in its own same-origin frame so its routing and state stay its own. */}
      <div className={styles.screens}>
        {(["phone", "monitor", "table"] as const).map((screen) => (
          <div
            key={screen}
            ref={(element) => { hostRefs.current[screen] = element; }}
            className={styles.host}
            data-screen={screen}
            style={{ visibility: "hidden" }}
          >
            {mounted[screen] && (
              <>
                <iframe
                  ref={(element) => { frameRefs.current[screen] = element; }}
                  className={styles.frame}
                  src={(frameSrc.current[screen] ??= stopFrameSrc(SCREEN_STOP[screen], language))}
                  title={tr(STOPS[SCREEN_STOP[screen]].page)}
                  onLoad={() => {
                    setLoaded((current) => ({ ...current, [screen]: true }));
                    setFrameScrollbar(screen, hostRefs.current[screen]?.dataset.mode === "docked");
                  }}
                  tabIndex={docked && STOP_SCREEN[docked] === screen ? 0 : -1}
                />
                {!loaded[screen] && <div className={styles.frameLoading} role="status">{tr(UI.loadingPage)}</div>}
              </>
            )}
          </div>
        ))}
      </div>

      {/* Projected scene labels. */}
      <div className={styles.labels} aria-hidden="true" data-hidden={docked || status !== "ready" ? "true" : "false"}>
        {Object.keys(LABELS).map((id) => (
          <div key={id} ref={(element) => { labelRefs.current[id] = element; }} className={styles.label} data-id={id} data-visible="false">
            <span>{tr(LABELS[id])}</span>
          </div>
        ))}
      </div>

      <div ref={fadeRef} className={styles.fade} data-on="false" aria-hidden="true" />

      {/* Cinematic chrome (hidden while a real page is docked). */}
      {!docked && status !== "failed" && (
        <>
          <header className={styles.topbar}>
            <Link className={styles.wordmark} href="/">FloodGuard<span>.</span></Link>
            <div className={styles.topActions}>
              <button type="button" className={styles.ghost} onClick={() => setSkipOpen(true)}>{tr(UI.skip)}</button>
              <div className={styles.language} role="group" aria-label="Language">
                <button type="button" aria-pressed={language === "en"} onClick={() => changeLanguage("en")}>EN</button>
                <button type="button" aria-pressed={language === "th"} onClick={() => changeLanguage("th")}>ไทย</button>
              </div>
              <button type="button" className={styles.ghost} aria-pressed={reducedMotion} onClick={toggleReducedMotion}>{tr(UI.reduceMotion)}</button>
            </div>
          </header>

          {view.heroVisible && status === "ready" && (
            <div className={styles.heroScrim} aria-hidden="true" />
          )}
          {view.heroVisible && status === "ready" && (
            <section className={styles.hero} aria-labelledby="journey-title">
              <h1 id="journey-title">{tr(UI.title).split("\n").map((line) => <span key={line}>{line}</span>)}</h1>
              <p>{tr(UI.subtitle)}</p>
              <div className={styles.heroActions}>
                <button type="button" className={styles.primary} onClick={() => void goTo(stopPosition("public"), { animate: !reducedMotion })}>{tr(UI.begin)}</button>
                <button type="button" className={styles.secondary} onClick={() => setSkipOpen(true)}>{tr(UI.skip)}</button>
              </div>
              <small>{tr(UI.scrollHint)}</small>
            </section>
          )}

          {caption && (
            <div className={styles.caption} key={`${view.segment}-${view.caption}-${language}`} aria-live="polite">
              {caption.eyebrow && <span className={styles.eyebrow}>{tr(caption.eyebrow)}</span>}
              <p>{tr(caption.text)}</p>
            </div>
          )}

          <p className={styles.illustrative}>{tr(UI.illustrative)}</p>

          <nav className={styles.chapterNav} aria-label={tr(UI.chapters)}>
            <button type="button" className={styles.step} disabled={view.atStart} onClick={() => step(-1)} aria-label={tr(UI.previous)}>←</button>
            <ol>
              {CHAPTERS.map((chapter, index) => (
                <li key={chapter}>
                  <button type="button" aria-current={chapter === view.chapter ? "step" : undefined} data-done={index < chapterIndex} onClick={() => void goTo(chapterEntry(chapter))}>
                    {CHAPTER_LABELS[chapter].number && <b>{CHAPTER_LABELS[chapter].number}</b>}
                    <span>{tr(CHAPTER_LABELS[chapter].title)}</span>
                  </button>
                </li>
              ))}
            </ol>
            <button type="button" className={styles.step} disabled={view.atEnd} onClick={() => step(1)} aria-label={tr(UI.next)}>→</button>
          </nav>
        </>
      )}

      {/* Story bar while a real page is docked. */}
      {docked && stopCopy && (
        <div ref={barRef} className={styles.storyBar} role="region" aria-label={tr(stopCopy.page)}>
          <div className={styles.barMain}>
            <span className={styles.barChapter}>{CHAPTER_LABELS[view.chapter].number} {tr(CHAPTER_LABELS[view.chapter].title)}</span>
            <strong>{tr(stopCopy.page)}</strong>
            <span className={styles.barNote}>{tr(stopCopy.note)}</span>
            <div className={styles.barActions}>
              <button type="button" className={styles.secondary} onClick={() => backToStory(docked)}>
                <span className={styles.long}>{tr(UI.backToStory)}</span><span className={styles.short} aria-hidden="true">← {tr(UI.story)}</span>
              </button>
              {stopCopy.continueLabel && (
                <button type="button" className={docked === "public-sos" ? styles.sos : styles.primary} onClick={() => continueFrom(docked)}>
                  {tr(stopCopy.continueLabel)}
                </button>
              )}
              {docked === "command" && (
                <>
                  <button type="button" className={styles.primary} onClick={() => continueFrom("command")}>{tr(UI.replay)}</button>
                  <Link className={styles.secondary} href="/" target="_top">{tr(UI.home)}</Link>
                </>
              )}
              <a className={styles.link} href={stopCopy.href(language)} target="_top" aria-label={tr(UI.openPage)}>
                <span className={styles.long}>{tr(UI.openPage)} ↗</span><span className={styles.short} aria-hidden="true">↗</span>
              </a>
            </div>
          </div>
          {stopCopy.warning && <p className={styles.barWarning}>{tr(stopCopy.warning)}</p>}
        </div>
      )}

      {skipOpen && (
        <div className={styles.skipPanel} role="dialog" aria-modal="true" aria-labelledby="journey-skip-title" onKeyDown={onSkipKeyDown}>
          <div ref={skipDialog}>
            <h2 id="journey-skip-title">{tr(UI.skipTitle)}</h2>
            <ul>
              {(["public", "case", "command"] as const).map((stop) => (
                <li key={stop}>
                  <button type="button" onClick={() => jumpToStop(stop)} autoFocus={stop === "public"}>{tr(STOPS[stop].page)}</button>
                  <a href={STOPS[stop].href(language)}>{tr(UI.openPage)} ↗</a>
                </li>
              ))}
            </ul>
            <button type="button" className={styles.secondary} onClick={() => setSkipOpen(false)}>{tr(UI.close)}</button>
          </div>
        </div>
      )}

      {status === "loading" && <div className={styles.loading} role="status">{tr(UI.loadingWorld)}</div>}

      {status === "failed" && (
        <section className={styles.fallback} aria-labelledby="journey-fallback">
          <Link className={styles.wordmark} href="/">FloodGuard<span>.</span></Link>
          <h1 id="journey-fallback">{tr(UI.fallbackTitle)}</h1>
          <p>{tr(UI.fallbackBody)}</p>
          <ol>
            {(["everyday", "conditions", "affected", "response"] as const).map((chapter, index) => {
              const stop = (["public", "public-sos", "case", "command"] as const)[index];
              return (
                <li key={chapter}>
                  <b>{CHAPTER_LABELS[chapter].number} {tr(CHAPTER_LABELS[chapter].title)}</b>
                  <p>{CAPTIONS[(["everyday", "conditions", "sos-signal", "aerial"] as const)[index]].map((entry) => tr(entry.text)).join(" ")}</p>
                  <a href={STOPS[stop].href(language)}>{tr(STOPS[stop].page)} ↗</a>
                </li>
              );
            })}
          </ol>
          <p className={styles.illustrativeStatic}>{tr(UI.illustrative)}</p>
        </section>
      )}

      <p className={styles.srOnly} aria-live="polite">{announcement}</p>
      {sizes === null && <span className={styles.srOnly}>{tr(UI.loadingWorld)}</span>}
    </main>
  );
}
