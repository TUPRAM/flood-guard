"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { beats, sceneAnchor, sceneFromId, scenes, type Scene } from "@/lib/landing-v1/story";
import { sampleTimeline, timelineLength, timelinePosition, timelineStops } from "@/lib/landing-v1/timeline";
import { Header, SceneFrame } from "./scene-frame";
import { ContinuousStage } from "./continuous-stage";
import styles from "./landing.module.css";
import stageStyles from "./continuous-stage.module.css";

const motionKey = "floodguard:landing-reduced-motion";
let memoryMotion = false;
const subscribeHydration = () => () => {};
const onClient = () => true;
const onServer = () => false;
const emptyQuery = () => "";
const readQuery = () => window.location.search;
const readEnlargedText = () => parseFloat(getComputedStyle(document.documentElement).fontSize) > 20;
const subscribeTextSize = (listener: () => void) => {
  const observer = new MutationObserver(listener);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["style", "class"] });
  window.addEventListener("resize", listener);
  return () => { observer.disconnect(); window.removeEventListener("resize", listener); };
};
const subscribeLocation = (listener: () => void) => {
  window.addEventListener("popstate", listener);
  return () => window.removeEventListener("popstate", listener);
};
const readMotion = () => { try { return localStorage.getItem(motionKey) === "1" || memoryMotion; } catch { return memoryMotion; } };
const subscribeMotion = (listener: () => void) => {
  window.addEventListener("fg-motion", listener);
  window.addEventListener("storage", listener);
  return () => { window.removeEventListener("fg-motion", listener); window.removeEventListener("storage", listener); };
};
function setMotion(reduced: boolean) {
  memoryMotion = reduced;
  try { localStorage.setItem(motionKey, reduced ? "1" : "0"); } catch { /* The in-memory preference still works when storage is unavailable. */ }
  window.dispatchEvent(new Event("fg-motion"));
}
function useMedia(query: string) {
  return useSyncExternalStore((listener) => {
    const media = window.matchMedia(query);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, () => window.matchMedia(query).matches, onServer);
}

function scrollToStoryTarget(target: HTMLElement | null, track: HTMLElement | null, enhanced: boolean) {
  const hold = target?.dataset.fgAnchorPosition;
  if (enhanced && track && hold !== undefined) {
    const unit = track.offsetHeight / (timelineLength + 1);
    const origin = window.scrollY + track.getBoundingClientRect().top;
    window.scrollTo({ top: Math.ceil(origin + Number(hold) * unit) + 2, behavior: "instant" });
  } else target?.scrollIntoView({ block: "start", behavior: "instant" });
}

function ReviewFrame({ scene }: { scene: Scene }) {
  const element = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let checking = false;
    const check = () => {
      if (checking || element.current?.querySelector<HTMLElement>("[data-fg-continuous-stage]")?.dataset.fgArtReady !== "true") return;
      checking = true;
      const images = [...(element.current?.querySelectorAll<HTMLImageElement>("img[src]") ?? [])];
      Promise.all([document.fonts.ready, ...images.map((image) => image.decode().catch(() => undefined))]).then(() => {
        requestAnimationFrame(() => requestAnimationFrame(() => { if (!cancelled) setReady(true); }));
      });
    };
    const observer = new MutationObserver(check);
    if (element.current) observer.observe(element.current, { attributes: true, subtree: true });
    check();
    return () => { cancelled = true; observer.disconnect(); };
  }, [scene]);
  return <div ref={element} className={stageStyles.review} data-testid="fg-review-frame" data-fg-ready={String(ready)}>
    <ContinuousStage frame={sampleTimeline(timelinePosition(scene.id))} review />
  </div>;
}

/** Native document scroll samples one persistent stage; readable flow remains the SSR and motion fallback. */
export function LandingExperience({ reviewEnabled, children }: { reviewEnabled: boolean; children: ReactNode }) {
  const hydrated = useSyncExternalStore(subscribeHydration, onClient, onServer);
  const manualMotion = useSyncExternalStore(subscribeMotion, readMotion, onServer);
  const osMotion = useMedia("(prefers-reduced-motion: reduce)");
  const stageFits = useMedia("(min-width: 320px) and (min-height: 560px)");
  const enlargedText = useSyncExternalStore(subscribeTextSize, readEnlargedText, onServer);
  const query = useSyncExternalStore(subscribeLocation, readQuery, emptyQuery);
  const review = reviewEnabled ? sceneFromId(new URLSearchParams(query).get("fgReview")) : undefined;
  const reduced = manualMotion || osMotion;
  const enhanced = hydrated && stageFits && !reduced && !review && !enlargedText;
  const [position, setPosition] = useState(0);
  const track = useRef<HTMLDivElement>(null);
  const modeRef = useRef(enhanced);
  const hasEnhanced = useRef(false);
  const activeRef = useRef(scenes[0]);
  const frame = sampleTimeline(position);

  useEffect(() => {
    let scheduled = 0;
    let restoreFrame = 0;
    const priorRestoration = window.history.scrollRestoration;
    if (enhanced) window.history.scrollRestoration = "manual";
    const sample = () => {
      scheduled = 0;
      if (!track.current) return;
      if (enhanced) {
        const unit = track.current.offsetHeight / (timelineLength + 1);
        const next = Math.max(0, -track.current.getBoundingClientRect().top / unit);
        activeRef.current = sampleTimeline(next).scene;
        setPosition((current) => Math.abs(current - next) < 0.00001 ? current : next);
      } else {
        let next = scenes[0];
        for (const element of track.current.querySelectorAll<HTMLElement>("[data-fg-anchor]")) {
          if (element.getBoundingClientRect().top <= window.innerHeight * .4) next = sceneFromId(element.dataset.fgAnchor) ?? next;
        }
        activeRef.current = next;
      }
    };
    const schedule = () => { if (!scheduled) scheduled = requestAnimationFrame(sample); };
    const restoreHistory = () => {
      cancelAnimationFrame(restoreFrame);
      restoreFrame = requestAnimationFrame(() => {
        scrollToStoryTarget(document.getElementById(window.location.hash.slice(1) || "top"), track.current, enhanced);
        schedule();
      });
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("hashchange", restoreHistory);
    window.addEventListener("popstate", restoreHistory);
    schedule();
    return () => {
      cancelAnimationFrame(scheduled);
      cancelAnimationFrame(restoreFrame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("hashchange", restoreHistory);
      window.removeEventListener("popstate", restoreHistory);
      window.history.scrollRestoration = priorRestoration;
    };
  }, [enhanced, review]);

  useEffect(() => {
    const previous = modeRef.current;
    modeRef.current = enhanced;
    const firstEnhancement = enhanced && !hasEnhanced.current;
    if (enhanced) hasEnhanced.current = true;
    let initialFrame = 0;
    let initialCancelled = false;
    const cancelInitialAlignment = () => {
      initialCancelled = true;
      cancelAnimationFrame(initialFrame);
    };
    const alignInitialHash = () => {
      if (initialCancelled) return;
      initialFrame = requestAnimationFrame(() => {
        initialFrame = requestAnimationFrame(() => {
          if (!initialCancelled) scrollToStoryTarget(document.getElementById(window.location.hash.slice(1)), track.current, enhanced);
        });
      });
    };
    if (previous !== enhanced) {
      const hashTarget = document.getElementById(window.location.hash.slice(1));
      const destination = firstEnhancement && hashTarget?.dataset.fgAnchor
        ? hashTarget
        : document.getElementById(activeRef.current.id === "H-01" ? "top" : sceneAnchor(activeRef.current));
      if (window.scrollY > window.innerHeight * .5 || (firstEnhancement && hashTarget)) {
        scrollToStoryTarget(destination, track.current, enhanced);
      }
    }
    if (firstEnhancement && window.location.hash) {
      window.addEventListener("wheel", cancelInitialAlignment, { passive: true });
      window.addEventListener("touchstart", cancelInitialAlignment, { passive: true });
      window.addEventListener("keydown", cancelInitialAlignment);
      if (document.readyState === "complete") alignInitialHash();
      else window.addEventListener("load", alignInitialHash, { once: true });
    }
    const prior = document.documentElement.style.scrollBehavior;
    if (reduced) document.documentElement.style.scrollBehavior = "auto";
    return () => {
      document.documentElement.style.scrollBehavior = prior;
      cancelInitialAlignment();
      window.removeEventListener("load", alignInitialHash);
      window.removeEventListener("wheel", cancelInitialAlignment);
      window.removeEventListener("touchstart", cancelInitialAlignment);
      window.removeEventListener("keydown", cancelInitialAlignment);
    };
  }, [enhanced, reduced]);

  return <main id="main-content" lang="en" className={styles.landing} data-fg-landing data-fg-mode={review ? "review" : enhanced ? "enhanced" : "flow"} data-fg-renderer="continuous-3d" data-fg-text-enlarged={String(enlargedText)} data-fg-reduced-motion={String(reduced)}>
    <div id="top" />
    <div className={stageStyles.headerContext}><Header motion={reduced} onMotion={hydrated ? () => setMotion(!manualMotion) : undefined} /></div>
    {review ? <ReviewFrame key={review.id} scene={review} /> : <>
      {enhanced ? <div ref={track} className={stageStyles.track} style={{ height: `${(timelineLength + 1) * 100}svh` }}>
        <ContinuousStage frame={frame} />
        {timelineStops.slice(1).map(({ scene, hold }) => <section key={scene.id} id={sceneAnchor(scene)} data-fg-anchor={scene.id} data-fg-anchor-position={hold} aria-label={scene.title.replaceAll("\n", " ")} className={stageStyles.anchor} style={{ top: `calc(${hold * 100}svh + 2px)`, scrollMarginTop: 0 } as CSSProperties} />)}
      </div> : <>
        <SceneFrame scene={scenes[0]} eager />
        <div ref={track}>{beats.map((scene) => <section key={scene.id} id={sceneAnchor(scene)} data-fg-anchor={scene.id}><SceneFrame scene={scene} /></section>)}</div>
      </>}
      {children}
    </>}
  </main>;
}
