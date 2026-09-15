"use client";

import { useId, useRef, type ReactNode } from "react";
import { assetRoot, scenes, sceneAnchor, story, type Scene } from "@/lib/landing-v1/story";
import { StoryPlate } from "./story-plate";
import styles from "./landing.module.css";
import { DeferredArtwork } from "./deferred-artwork";
import fallbackStyles from "./fallback-scene.module.css";

export function Header({ motion, onMotion }: { motion?: boolean; onMotion?: () => void }) {
  return <header className={styles.header}>
    <a href="#top" className={styles.brand} aria-label="FloodGuard home">FloodGuard<span aria-hidden="true">.</span></a>
    <nav className={styles.headerLinks} aria-label="Main navigation"><a href="#story-everyday">The story</a><a href="#evidence">Evidence</a><a href="#workspaces">Workspaces</a></nav>
    <a className={styles.headerCta} href="/command/">Planning demo <span aria-hidden="true">↗</span></a>
    {onMotion && <button className={styles.motion} type="button" aria-pressed={motion} onClick={onMotion}>{motion ? "Motion reduced" : "Reduce motion"}</button>}
  </header>;
}

export function Actions({ closing = false }: { closing?: boolean }) {
  return <div className={`${styles.actions} ${closing ? styles.closingActions : ""}`}>
    <a className={styles.primary} href={story.primaryCta.href}>{story.primaryCta.label}<span aria-hidden="true"> ↗</span></a>
    {closing ? <div className={styles.secondaryLinks}><a href="/public/">Public preparedness <span aria-hidden="true">↗</span></a><a href="/studio/">Inspect the evidence <span aria-hidden="true">↗</span></a></div> : <a className={styles.secondary} href={story.secondaryCta.href}>{story.secondaryCta.label}<span aria-hidden="true"> ↓</span></a>}
  </div>;
}

export function ChapterNav({ scene, review = false }: { scene: Scene; review?: boolean }) {
  const index = scenes.findIndex((item) => item.id === scene.id);
  const href = (target: Scene) => review ? `?fgReview=${target.id}&fgStill=1` : `#${target.id === "H-01" ? "top" : sceneAnchor(target)}`;
  return <nav className={styles.chapterNav} aria-label="Story chapters and steps">
    <a className={styles.step} href={href(scenes[Math.max(0, index - 1)])} aria-label="Previous story step"><span aria-hidden="true">←</span><span className={styles.stepWord}>Previous</span></a>
    <ol>{story.chapters.map((chapter) => <li key={chapter.id}><a href={review ? `?fgReview=${chapter.firstScene}&fgStill=1` : `#${chapter.anchor}`} aria-current={chapter.id === scene.chapter ? "step" : undefined}><span>{chapter.id}</span><span>{chapter.label}</span></a></li>)}</ol>
    <details className={styles.chapterMenu}><summary> {scene.chapter} / {story.chapters.find((chapter) => chapter.id === scene.chapter)?.label} <span aria-hidden="true">⌄</span></summary><div>{story.chapters.map((chapter) => <a key={chapter.id} href={review ? `?fgReview=${chapter.firstScene}&fgStill=1` : `#${chapter.anchor}`} onClick={(event) => { const menu = event.currentTarget.closest("details"); if (menu) menu.open = false; }}>{chapter.id} · {chapter.label}</a>)}</div></details>
    {index < scenes.length - 1 ? <a className={styles.step} href={href(scenes[index + 1])} aria-label="Next story step"><span className={styles.stepWord}>Next</span><span aria-hidden="true">→</span></a> : <a className={styles.step} href={review ? "/#workspaces" : "#workspaces"}><span className={styles.stepWord}>Workspaces</span><span aria-hidden="true">↓</span></a>}
  </nav>;
}

function Rows({ rows }: { rows: { label: string; value: string }[] }) {
  return <dl className={styles.cardRows}>{rows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>;
}

export function SceneFrame({ scene, eager = false, review = false, standalone = false, phase = "idle", onReady }: { scene: Scene; eager?: boolean; review?: boolean; standalone?: boolean; phase?: string; onReady?: () => void }) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const finding = useRef<HTMLDivElement>(null);
  const details = useRef<HTMLDetailsElement>(null);
  const lastTrigger = useRef<HTMLElement | null>(null);
  const hero = scene.id === "H-01";
  const closing = scene.id === "S4-END";
  const chapter = story.chapters.find((item) => item.id === scene.chapter);
  const firstInChapter = chapter?.firstScene === scene.id;
  const Title = hero ? "h1" : firstInChapter || review || standalone ? "h2" : "h3";
  const CardHeading = firstInChapter || review || standalone ? "h3" : "h4";
  const compactCard = ["preparedness", "changing", "observation", "public"].includes(scene.card ?? "");
  const inspect = (kind: "observation" | "finding") => {
    lastTrigger.current = document.activeElement as HTMLElement;
    if (kind === "finding" && finding.current) {
      finding.current.focus({ preventScroll: true });
      finding.current.scrollIntoView({ block: "nearest", behavior: "instant" });
    } else dialog.current?.showModal();
  };
  const openBrief = () => {
    if (!details.current) return;
    details.current.open = true;
    details.current.focus({ preventScroll: true });
    details.current.scrollIntoView({ block: "nearest", behavior: "instant" });
  };
  let card: ReactNode = null;
  if (scene.card === "preparedness" || scene.card === "changing") {
    const data = story.cards[scene.card];
    card = <><CardHeading>{data.title}</CardHeading><p>{data.body}</p><div className={styles.cardStatus}>{data.status}</div></>;
  } else if (scene.card === "observation") {
    const data = story.cards.observation;
    card = <><p className={styles.cardEyebrow}>{data.eyebrow}</p><p>{data.body}</p><span className={styles.badge}>{data.status}</span><details className={styles.observationDetails}><summary className={styles.textButton} onClick={(event) => { event.preventDefault(); inspect("observation"); }}>{data.interactionLabel} <span aria-hidden="true">↗</span></summary><p>{data.interactionScope}</p></details><noscript><p>{data.interactionScope}</p></noscript></>;
  } else if (scene.card === "analysis") {
    const data = story.cards.analysis;
    card = <><p className={styles.cardEyebrow}>{data.eyebrow}</p><CardHeading>{data.title}</CardHeading><p>{data.body}</p><Rows rows={data.rows} /></>;
  } else if (scene.card === "brief") {
    const data = story.cards.brief;
    card = <><p className={styles.cardEyebrow}>{data.eyebrow}</p><CardHeading>{data.title}</CardHeading><Rows rows={data.rows} /><details className={styles.briefDetails} ref={details} tabIndex={-1} onKeyDown={(event) => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}><summary>{data.actionLabel} <span aria-hidden="true">↗</span></summary><p>{data.details}</p></details></>;
  } else if (scene.card === "public") {
    card = <><p className={styles.cardEyebrow}>{story.cards.public.eyebrow}</p><ul className={styles.publicItems}>{story.cards.public.items.map((item, index) => <li key={item}><span aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={["M9 5H5v16h14V5h-4M9 3h6v4H9zM8 12h8M8 16h6", "M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 20h4M12 2v2", "M12 8v.1M10 11h2v6m-2 0h4M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0"][index]} /></svg></span>{item}</li>)}</ul><a className={styles.textButton} href="/public/">Public preparedness <span aria-hidden="true">↗</span></a></>;
  }
  return <div className={`${styles.scene} ${hero ? styles.hero : ""} ${closing ? styles.closing : ""} ${fallbackStyles.frame}`} data-fg-fallback-frame data-fg-scene={scene.id} data-fg-active-scene={scene.id} data-fg-phase={phase} data-fg-settled={phase === "idle" ? "true" : "false"} data-fg-card={scene.card ?? "none"} onLoad={onReady}>
    <div className={`${styles.sceneBody} ${fallbackStyles.body}`} inert={phase === "out"}>
      <div className={`${styles.narrative} ${fallbackStyles.narrative}`}>
        {!hero && <p className={styles.eyebrow}>{chapter?.id}<span aria-hidden="true"> / </span>{chapter?.label}</p>}
        <Title className={`${styles.storyTitle} ${fallbackStyles.title}`}>{scene.title.split("\n").map((line, index) => <span key={line}>{index > 0 && <span className={styles.lineSpace}> </span>}{line}</span>)}</Title>
        <p className={styles.bodyCopy}>{scene.body}</p>
        {closing && <Actions closing />}
      </div>
      <div className={`${styles.mapArea} ${fallbackStyles.map}`}><StoryPlate scene={scene} eager={eager} onInspect={scene.card === "brief" ? (kind) => kind === "finding" ? openBrief() : inspect(kind) : inspect} /></div>
      {card && <div className={`${styles.card} ${compactCard ? styles.compactCard : styles.findingCard} ${fallbackStyles.card}`} ref={finding} tabIndex={-1} aria-label={scene.card === "brief" ? "Illustrative review brief" : "Illustrative story explanation"}>{card}</div>}
      {scene.question && <blockquote className={`${styles.question} ${fallbackStyles.question}`}>{scene.question}</blockquote>}
      {scene.character && <div className={`${styles.character} ${scene.character === "planner" ? styles.planner : ""} ${fallbackStyles.portrait}`}><DeferredArtwork src={`${assetRoot}/characters/${scene.character}-800.webp`} srcSet={[480, 800, 1374].map((width) => `${assetRoot}/characters/${scene.character}-${width}.webp ${width}w`).join(", ")} sizes="(min-width: 1000px) 320px, 70vw" width={1374} height={1145} alt="" eager={eager} decoding="async" onError={(event) => { event.currentTarget.style.visibility = "hidden"; }} /></div>}
    </div>
    {!hero && <ChapterNav scene={scene} review={review} />}
    <dialog className={styles.dialog} ref={dialog} aria-labelledby={`${id}-observation`} onClose={() => lastTrigger.current?.focus({ preventScroll: true })}>
      <form method="dialog"><button aria-label="Close sample observation" className={styles.dialogClose}>×</button></form>
      <p className={styles.cardEyebrow}>Illustrative local example</p><h2 id={`${id}-observation`}>{story.cards.observation.eyebrow}</h2><p>{story.cards.observation.body}</p><span className={styles.badge}>{story.cards.observation.status}</span><p>{story.cards.observation.interactionScope}</p>
    </dialog>
  </div>;
}
