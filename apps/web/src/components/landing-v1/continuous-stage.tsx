/* eslint-disable @next/next/no-img-element -- local pre-rendered 3D frame sequence, registered at native dimensions. */
"use client";

import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import manifest from "../../../public/landing/floodguard-v2/scene-manifest.json";
import { assetRoot, pathFromPoints, story, type Point, type Scene } from "@/lib/landing-v1/story";
import { artworkWeights, type TimelineFrame } from "@/lib/landing-v1/timeline";
import { registerCameraTriangle } from "@/lib/landing-v1/neighborhood";
import { Actions, ChapterNav } from "./scene-frame";
import styles from "./continuous-stage.module.css";

export type ContinuousSceneAssets = {
  width: number;
  height: number;
  cameraFrames: { src: string; at: number; projection: number[][] }[];
  closeStates: { W0: string; W1: string; W2: string };
  waterLayers?: { W1?: string; W2?: string };
  anchors: {
    home: number[];
    clinic: number[];
    route: number[][];
    affected: number[];
    report: number[];
    selection: number[][];
  };
};
const assets = manifest as ContinuousSceneAssets;
const residentSource = `${assetRoot}/characters/resident-800.webp`;
const plannerSource = `${assetRoot}/characters/planner-800.webp`;
const point = (value: number[]): Point => [value[0], value[1]];
const position = ([x, y]: number[]): CSSProperties => ({ left: `${x / assets.width * 100}%`, top: `${y / assets.height * 100}%` });
const route = assets.anchors.route.map(point);
const affected = route.slice(assets.anchors.affected[0], assets.anchors.affected[1] + 1);
const routePath = pathFromPoints(route);
const affectedPath = pathFromPoints(affected);
const selectionPath = assets.anchors.selection.length > 2 ? `${pathFromPoints(assets.anchors.selection.map(point))} Z` : "";
const connectionPoint = affected[Math.floor(affected.length / 2)] ?? route[Math.floor(route.length / 2)];

/** Decode in a bounded queue after first paint; the currently requested view takes priority. */
function useDecodedArtwork(critical: readonly string[], upcoming: readonly string[]) {
  const [ready, setReady] = useState<ReadonlySet<string>>(() => new Set());
  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set());
  const request = useRef<((sources: string[], priority?: boolean) => void) | null>(null);
  const criticalKey = critical.join("|");
  const upcomingKey = upcoming.join("|");
  useEffect(() => {
    let disposed = false;
    let running = 0;
    let firstPaint = 0;
    let afterPaint = 0;
    const queue: string[] = [];
    const completed = new Set<string>();
    const inFlight = new Set<string>();
    const urgent = new Set<string>();
    const pump = () => {
      while (!disposed && running < 3 && queue.length) {
        const source = queue.shift()!;
        running += 1;
        inFlight.add(source);
        const image = new Image();
        image.decoding = "async";
        image.fetchPriority = urgent.has(source) ? "high" : "low";
        image.src = source;
        image.decode().then(() => {
          if (!disposed) setReady((previous) => new Set(previous).add(source));
        }, () => {
          if (!disposed) setFailed((previous) => new Set(previous).add(source));
        }).finally(() => {
          running -= 1;
          inFlight.delete(source);
          completed.add(source);
          pump();
        });
      }
    };
    request.current = (sources, priority = false) => {
      if (priority) sources.forEach((source) => urgent.add(source));
      const pending = sources.filter((source, index) => source && sources.indexOf(source) === index && !completed.has(source) && !inFlight.has(source) && (priority || !queue.includes(source)));
      for (const source of pending) {
        const existing = queue.indexOf(source);
        if (existing !== -1) queue.splice(existing, 1);
      }
      if (priority) queue.unshift(...pending);
      else queue.push(...pending);
      pump();
    };
    firstPaint = requestAnimationFrame(() => {
      afterPaint = requestAnimationFrame(() => request.current?.([
        residentSource, plannerSource,
        ...assets.cameraFrames.map((item) => item.src),
      ]));
    });
    return () => {
      disposed = true;
      request.current = null;
      cancelAnimationFrame(firstPaint);
      cancelAnimationFrame(afterPaint);
    };
  }, []);
  useEffect(() => { request.current?.(criticalKey.split("|").filter(Boolean), true); }, [criticalKey]);
  useEffect(() => { request.current?.(upcomingKey.split("|").filter(Boolean)); }, [upcomingKey]);
  return { ready, failed };
}

function Rows({ rows }: { rows: { label: string; value: string }[] }) {
  return <dl>{rows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>;
}

function StoryCard({ scene, onObservation, briefRef }: {
  scene: Scene;
  onObservation: () => void;
  briefRef: RefObject<HTMLDetailsElement | null>;
}) {
  let body: ReactNode = null;
  switch (scene.card) {
    case "preparedness":
    case "changing": {
      const card = story.cards[scene.card];
      body = <><h3>{card.title}</h3><p>{card.body}</p><small>{card.status}</small></>;
      break;
    }
    case "observation":
      body = <><p className={styles.cardEyebrow}>{story.cards.observation.eyebrow}</p><p>{story.cards.observation.body}</p><strong className={styles.badge}>{story.cards.observation.status}</strong><button type="button" onClick={onObservation}>{story.cards.observation.interactionLabel} ↗</button><small>{story.cards.observation.interactionScope}</small></>;
      break;
    case "analysis":
      body = <><p className={styles.cardEyebrow}>{story.cards.analysis.eyebrow}</p><h3>{story.cards.analysis.title}</h3><p>{story.cards.analysis.body}</p><Rows rows={story.cards.analysis.rows} /></>;
      break;
    case "brief":
      body = <><p className={styles.cardEyebrow}>{story.cards.brief.eyebrow}</p><h3>{story.cards.brief.title}</h3><Rows rows={story.cards.brief.rows} /><details ref={briefRef} tabIndex={-1} onKeyDown={(event) => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus({ preventScroll: true }); } }}><summary>{story.cards.brief.actionLabel} ↗</summary><p>{story.cards.brief.details}</p></details></>;
      break;
    case "public":
      body = <><p className={styles.cardEyebrow}>{story.cards.public.eyebrow}</p><ul>{story.cards.public.items.map((item) => <li key={item}>{item}</li>)}</ul><a href="/public/">Public preparedness ↗</a></>;
      break;
  }
  return body ? <div className={styles.card} data-fg-card={scene.card}>{body}</div> : null;
}

/** The same world, window, paper panel and portrait nodes survive every scene change. */
export function ContinuousStage({ frame, review = false }: { frame: TimelineFrame; review?: boolean }) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const brief = useRef<HTMLDetailsElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const scene = frame.scene;
  useEffect(() => { panel.current?.scrollTo({ top: 0, behavior: "instant" }); }, [scene.id]);
  const chapter = story.chapters.find((item) => item.id === scene.chapter);
  const closed = scene.id === "S4-END";
  const css = {
    "--window-progress": frame.window,
    "--paper-progress": frame.background,
    "--hero-opacity": frame.heroOpacity,
    "--copy-opacity": frame.textOpacity,
    "--narrative-opacity": frame.narrativeOpacity,
    "--resident-opacity": frame.residentOpacity,
    "--planner-opacity": frame.plannerOpacity,
    "--world-ratio": `${assets.width} / ${assets.height}`,
    "--world-aspect": assets.width / assets.height,
  } as CSSProperties;
  let cameraIndex = 0;
  for (let index = 0; index < assets.cameraFrames.length; index += 1) {
    if (assets.cameraFrames[index].at <= frame.camera) cameraIndex = index;
  }
  const nextCamera = Math.min(cameraIndex + 1, assets.cameraFrames.length - 1);
  const interval = assets.cameraFrames[nextCamera].at - assets.cameraFrames[cameraIndex].at;
  const cameraBlend = interval > 0 ? (frame.camera - assets.cameraFrames[cameraIndex].at) / interval : 0;
  const cameraProjection = assets.cameraFrames[cameraIndex].projection;
  const nextProjection = assets.cameraFrames[nextCamera].projection;
  const blendedProjection = cameraProjection.map((point, index) => point.map((value, axis) => value + (nextProjection[index][axis] - value) * cameraBlend));
  const transformCamera = (projection: number[][]) => {
    const [a, b, c, d, x, y] = registerCameraTriangle(projection, blendedProjection);
    return `translate(${x / assets.width * 100}%, ${y / assets.height * 100}%) matrix(${a}, ${b}, ${c}, ${d}, 0, 0)`;
  };
  const cameraTransform = transformCamera(cameraProjection);
  const nextCameraTransform = transformCamera(nextProjection);
  const w1Source = assets.closeStates.W1;
  const w2Source = assets.closeStates.W2;
  const currentSources = [
    ...(frame.water > 1 ? [w2Source] : []),
    ...(frame.water > 0 && frame.water < 2 ? [w1Source] : []),
    assets.cameraFrames[cameraIndex].src,
    ...(cameraBlend > 0 ? [assets.cameraFrames[nextCamera].src] : []),
  ];
  const artwork = useDecodedArtwork(currentSources, frame.camera > 0.95 ? [w1Source, w2Source] : []);
  const failed = currentSources.some((source) => artwork.failed.has(source));
  const artReady = currentSources.every((source) => artwork.ready.has(source));
  const weights = artworkWeights(frame.water, cameraBlend, artReady);
  const dominant = (Object.keys(weights) as (keyof typeof weights)[]).reduce((largest, key) => weights[key] > weights[largest] ? key : largest, "poster");
  const nearestReady = [...assets.cameraFrames].filter((item) => artwork.ready.has(item.src)).sort((a, b) => Math.abs(a.at - frame.camera) - Math.abs(b.at - frame.camera))[0];
  const fallbackSource = nearestReady?.src ?? assets.cameraFrames[0].src;
  const fallbackTransform = transformCamera((nearestReady ?? assets.cameraFrames[0]).projection);
  const overlayOpacity = artReady ? frame.routeOpacity : 0;
  const observation = () => {
    lastTrigger.current = document.activeElement as HTMLElement;
    dialog.current?.showModal();
  };
  const finding = () => {
    if (brief.current) {
      brief.current.open = true;
      brief.current.focus({ preventScroll: true });
      if (panel.current) {
        const target = brief.current.getBoundingClientRect();
        const viewport = panel.current.getBoundingClientRect();
        panel.current.scrollBy({ top: target.top - viewport.top - 16, behavior: "instant" });
      }
    } else {
      panel.current?.focus({ preventScroll: true });
      panel.current?.scrollTo({ top: panel.current.scrollHeight, behavior: "instant" });
    }
  };
  return <div className={styles.stage} style={css} data-fg-continuous-stage data-fg-active-scene={scene.id} data-fg-scene={scene.id} data-fg-progress={frame.progress.toFixed(5)} data-fg-camera-progress={frame.camera.toFixed(5)} data-fg-window-progress={frame.window.toFixed(5)} data-fg-panel-progress={frame.background.toFixed(5)} data-fg-hero-opacity={frame.heroOpacity.toFixed(5)} data-fg-text-opacity={frame.textOpacity.toFixed(5)} data-fg-narrative-opacity={frame.narrativeOpacity.toFixed(5)} data-fg-resident-opacity={frame.residentOpacity.toFixed(5)} data-fg-planner-opacity={frame.plannerOpacity.toFixed(5)} data-fg-art-ready={String(artReady)} data-fg-reading-hold={String(frame.readingHold)} data-fg-phase={frame.contentInteractive || scene.id === "H-01" ? "idle" : "transition"} data-fg-settled={String(frame.readingHold)}>
    <div className={styles.artWindow} data-fg-art-window data-fg-selected={String(frame.selectionOpacity > 0)}>
      <div className={styles.world} data-fg-world data-fg-water={scene.waterState}>
        <div className={styles.artLayers} data-fg-art-layers>
        <img className={styles.worldImage} data-fg-retained-poster data-fg-dominant={String(dominant === "poster")} src={fallbackSource} width={assets.width} height={assets.height} alt="" fetchPriority="high" decoding="async" style={{ opacity: weights.poster, transformOrigin: "0 0", transform: fallbackTransform }} />
        {assets.cameraFrames.map((camera, index) => {
          const active = artwork.ready.has(camera.src) && (index === cameraIndex || (frame.camera > 0 && index === nextCamera));
          const opacity = (index === cameraIndex ? weights.camera : 0) + (index === nextCamera ? weights.next : 0);
          const chosen = (dominant === "camera" && index === cameraIndex) || (dominant === "next" && index === nextCamera);
          return <img key={camera.src} className={styles.worldImage} data-fg-camera-frame={index} data-fg-dominant={String(chosen)} src={active ? camera.src : undefined} width={assets.width} height={assets.height} alt="" decoding="async" style={{ opacity: active ? opacity : 0, transformOrigin: "0 0", transform: index === cameraIndex ? cameraTransform : index === nextCamera ? nextCameraTransform : undefined }} />;
        })}
        <img className={styles.worldImage} data-fg-water-layer="W1" data-fg-dominant={String(dominant === "w1")} src={frame.water > 0 && artwork.ready.has(w1Source) ? w1Source : undefined} width={assets.width} height={assets.height} alt="" decoding="async" style={{ opacity: weights.w1 }} />
        <img className={styles.worldImage} data-fg-water-layer="W2" data-fg-plate-image data-fg-dominant={String(dominant === "w2")} src={frame.water > 1 && artwork.ready.has(w2Source) ? w2Source : undefined} width={assets.width} height={assets.height} alt="" decoding="async" style={{ opacity: weights.w2 }} />
        </div>
        <svg className={styles.overlay} viewBox={`0 0 ${assets.width} ${assets.height}`} aria-hidden="true" focusable="false" style={{ opacity: overlayOpacity }}>
          <path d={routePath} className={styles.routeHalo} vectorEffect="non-scaling-stroke" />
          <path d={routePath} className={styles.route} vectorEffect="non-scaling-stroke" />
          <g style={{ opacity: frame.affectedOpacity }}><path d={affectedPath} className={styles.affectedHalo} vectorEffect="non-scaling-stroke" /><path d={affectedPath} className={styles.affected} vectorEffect="non-scaling-stroke" /></g>
          {[assets.anchors.home, assets.anchors.clinic].map(([x, y], index) => <circle key={index} cx={x} cy={y} r="10" className={styles.endpoint} vectorEffect="non-scaling-stroke" />)}
          <path d={selectionPath} className={styles.selection} vectorEffect="non-scaling-stroke" style={{ opacity: frame.selectionOpacity }} />
          <g style={{ opacity: frame.reportOpacity }}><path d={`M ${connectionPoint.join(" ")} L ${assets.anchors.report.join(" ")}`} className={styles.leader} vectorEffect="non-scaling-stroke" /><circle cx={assets.anchors.report[0]} cy={assets.anchors.report[1]} r="12" className={styles.reportPoint} vectorEffect="non-scaling-stroke" /></g>
        </svg>
        <div className={styles.labels} style={{ opacity: overlayOpacity }} aria-hidden={overlayOpacity < 0.97}>
          <span className={styles.label} style={position(assets.anchors.home)}>{story.routeLabels.homes}</span>
          <span className={styles.label} style={position(assets.anchors.clinic)}>{story.routeLabels.clinic}</span>
          <span className={`${styles.label} ${styles.connectionLabel}`} style={position([...connectionPoint])}>{frame.water > 1.5 ? story.routeLabels.affected : story.routeLabels.usual}</span>
        </div>
        <button type="button" className={`${styles.label} ${styles.reportLabel}`} style={{ ...position(assets.anchors.report), opacity: artReady ? frame.reportOpacity : 0 }} tabIndex={artReady && frame.reportOpacity > 0.97 ? 0 : -1} disabled={!artReady || frame.reportOpacity < 0.97} aria-hidden={!artReady || frame.reportOpacity < 0.97} onClick={observation} aria-label="Inspect sample observation DEMO-R01">DEMO-R01 <small>Not verified</small></button>
        {failed && <div className={styles.imageFallback} role="img" aria-label={scene.imageDescription}><strong>Illustration unavailable</strong><p>{scene.imageDescription}</p></div>}
        {!artReady && !failed && frame.camera > 0 && <p className={styles.loading}>Preparing this view…</p>}
      </div>
      <button type="button" className={styles.selectionButton} style={{ opacity: artReady ? frame.selectionOpacity : 0 }} tabIndex={artReady && frame.selectionOpacity > 0.97 ? 0 : -1} disabled={!artReady || frame.selectionOpacity < 0.97} aria-hidden={!artReady || frame.selectionOpacity < 0.97} onClick={finding}>{story.routeLabels.selection} ↗</button>
    </div>

    <div className={styles.heroCopy} inert={frame.heroOpacity < 0.97} aria-hidden={frame.heroOpacity < 0.01}>
      <h1>See the flood.<br />Understand what it changes.</h1>
      <p>{story.scenes[0].body}</p>
    </div>
    <aside className={styles.panel} data-fg-story-panel aria-label="Neighborhood story" inert={frame.background < 0.99} aria-hidden={frame.background < 0.01}>
      <div className={styles.panelPaper} data-fg-panel-background />
      <div className={styles.panelCopy} ref={panel} tabIndex={frame.contentInteractive ? 0 : -1} role="region" aria-label="Story explanation" data-fg-panel-copy>
        <div className={styles.copyInner}>
          <div className={styles.narrative} aria-hidden={frame.narrativeOpacity < 0.01}>
          {chapter && <p className={styles.eyebrow}>{chapter.id} / {chapter.label}</p>}
          <h2>{scene.title.replaceAll("\n", " ")}</h2>
          <p className={styles.body}>{scene.body}</p>
          {scene.question && <blockquote>{scene.question}</blockquote>}
          </div>
          <div className={styles.changingDetails} inert={!frame.contentInteractive} aria-hidden={frame.textOpacity < 0.01}>
            <StoryCard key={scene.id} scene={scene} onObservation={observation} briefRef={brief} />
            {closed && <Actions closing />}
          </div>
        </div>
      </div>
      <div className={styles.people} data-fg-portrait-shell aria-hidden="true">
        <img data-fg-portrait="resident" src={artwork.ready.has(residentSource) ? residentSource : undefined} width={1374} height={1145} alt="" decoding="async" className={styles.resident} />
        <img data-fg-portrait="planner" src={artwork.ready.has(plannerSource) ? plannerSource : undefined} width={1374} height={1145} alt="" decoding="async" className={styles.planner} />
        <span className={styles.personCaption} style={{ opacity: Math.max(frame.residentOpacity, frame.plannerOpacity) }}>{frame.plannerOpacity > frame.residentOpacity ? "A planning perspective" : "A resident’s perspective"}</span>
      </div>
    </aside>
    <div className={styles.navigation} inert={frame.background < 0.99} aria-hidden={frame.background < 0.01}><ChapterNav scene={scene} review={review} /></div>
    <p className={styles.srOnly}>{scene.imageDescription}</p>
    <dialog ref={dialog} className={styles.dialog} aria-labelledby={`${id}-observation`} onClose={() => lastTrigger.current?.isConnected ? lastTrigger.current.focus({ preventScroll: true }) : panel.current?.focus({ preventScroll: true })}>
      <form method="dialog"><button type="submit" aria-label="Close sample observation">×</button></form><p className={styles.eyebrow}>Illustrative local example</p><h2 id={`${id}-observation`}>{story.cards.observation.eyebrow}</h2><p>{story.cards.observation.body}</p><strong className={styles.badge}>{story.cards.observation.status}</strong><p>{story.cards.observation.interactionScope}</p>
    </dialog>
  </div>;
}
