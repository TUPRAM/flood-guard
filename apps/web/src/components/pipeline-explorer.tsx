"use client";

import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { figuresOfTopic, PIPELINE_FIGURES, type FigureBox, type FigureLine, type PipelineFigure } from "@/lib/pipeline-figures";
import {
  linkHref, PIPELINE_AS_OF, statusCounts, STATUS_LABEL, STATUS_MEANING, TOPIC_BY_ID,
  type DetailChart, type PipelineTopic, type StageStatus,
} from "@/lib/pipeline-progress";

import styles from "./pipeline-explorer.module.css";

const STATUSES: StageStatus[] = ["done", "in_progress", "not_started"];
const FILL: Record<StageStatus, string> = { done: "#e5f4ea", in_progress: "#fff1cf", not_started: "#eef0ef" };
const ALL_TOPICS = PIPELINE_FIGURES.flatMap((figure) => figure.boxes.map((box) => box.topic));

interface Selection { topic: string; box: string }

/** The proposal's five figures with the state of every box; a box opens what is behind it. */
export function PipelineExplorer() {
  const [selection, setSelection] = useState<Selection | null>(null);
  const opener = useRef<HTMLElement | SVGElement | null>(null);

  const open = useCallback((box: FigureBox) => {
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement || active instanceof SVGElement ? active : null;
    setSelection({ topic: box.topic, box: box.id });
    try {
      window.history.replaceState(null, "", `#${box.id}`);
    } catch {
      // The address stays as it is.
    }
  }, []);

  const close = useCallback(() => {
    setSelection(null);
    try {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    } catch {
      // The address stays as it is.
    }
    opener.current?.focus?.();
  }, []);

  // A link to a box (#f2-rf) opens it, when the page loads and when the address changes to it.
  useEffect(() => {
    let frame = 0;
    const openFromHash = () => {
      const id = window.location.hash.slice(1);
      const box = PIPELINE_FIGURES.flatMap((figure) => figure.boxes).find((item) => item.id === id);
      if (!box) return;
      frame = window.requestAnimationFrame(() => setSelection({ topic: box.topic, box: box.id }));
    };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", openFromHash);
    };
  }, []);

  const overall = statusCounts(ALL_TOPICS);
  const total = overall.done + overall.in_progress + overall.not_started;

  return (
    <main id="main-content" className={styles.page} lang="en">
      <header className={styles.head}>
        <a className={styles.back} href="/studio/">← Studio</a>
        <p className={styles.eyebrow}>STUDIO · THE PROPOSAL&apos;S PIPELINE, BOX BY BOX</p>
        <h1>Pipeline progress</h1>
        <p className={styles.lead}>The five figures of our GeoHackathon 2026 proposal, with the state of every box as of {PIPELINE_AS_OF}. Select a box to see what it does, where the work stands, and the figures, charts, images and files behind it.</p>
        <div className={styles.overall} aria-label="Overall progress">
          <p><strong>{total}</strong> pieces of work across the five figures (a box drawn in several figures counts once):</p>
          <ul className={styles.counts}>
            {STATUSES.map((status) => (
              <li key={status} data-status={status}><StatusIcon status={status} /> <strong>{overall[status]}</strong> {STATUS_LABEL[status]}</li>
            ))}
          </ul>
          <ProgressBar counts={overall} />
        </div>
        <details className={styles.legend}>
          <summary>How to read the figures</summary>
          <dl>
            {STATUSES.map((status) => (
              <div key={status}><dt><span className={styles.swatch} data-status={status} /> {STATUS_LABEL[status]}</dt><dd>{STATUS_MEANING[status]}</dd></div>
            ))}
            <div><dt><StatusIcon status="done" /> Badge</dt><dd>The same status, as an icon in the corner of each box.</dd></div>
            <div><dt>Line style</dt><dd>As in the proposal: dashed for a conditional or isolated component, bold for a protected one, hatched for blocked or report-only, dotted for roadmap. Labels and captions are the proposal&apos;s own wording.</dd></div>
          </dl>
        </details>
        <p className={styles.limit}>Every figure on this page is a modelled planning figure or an agreement with another map or image, not an observation of a flood. FloodGuard is not a real-time product or an official warning.</p>
      </header>

      {PIPELINE_FIGURES.map((figure) => (
        <FigureSection key={figure.id} figure={figure} selectedBox={selection?.box ?? null} onOpen={open} />
      ))}

      {selection ? <DetailPanel topic={TOPIC_BY_ID[selection.topic]} onClose={close} /> : null}
    </main>
  );
}

function FigureSection({ figure, selectedBox, onOpen }: { figure: PipelineFigure; selectedBox: string | null; onOpen: (box: FigureBox) => void }) {
  const counts = statusCounts(figure.boxes.map((box) => box.topic));
  const titleId = `${figure.id}-title`;
  return (
    <section className={styles.figure} aria-labelledby={titleId} data-figure={figure.id}>
      <h2 id={titleId}><span className={styles.figureNumber}>Figure {figure.number}.</span> {figure.caption}</h2>
      <p className={styles.figureMeta}>
        {figure.section} · {STATUSES.filter((status) => counts[status]).map((status) => `${counts[status]} ${STATUS_LABEL[status].toLowerCase()}`).join(" · ")}
      </p>
      <div className={styles.frame}>
        <FigureDiagram figure={figure} selectedBox={selectedBox} onOpen={onOpen} />
      </div>
      <ul className={styles.chips} aria-label={`Boxes in figure ${figure.number}`}>
        {figure.boxes.map((box) => {
          const topic = TOPIC_BY_ID[box.topic];
          return (
            <li key={box.id}>
              <button type="button" className={styles.chip} data-status={topic.status} data-box={box.id} onClick={() => onOpen(box)}>
                <StatusIcon status={topic.status} /> {boxLabel(box)}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function boxLabel(box: FigureBox): string {
  const titles = box.lines.filter((line) => line.kind === "title" || line.kind === undefined);
  return (titles.length ? titles : box.lines).map((line) => line.text).join(" ").replace(/\s+/g, " ");
}

function FigureDiagram({ figure, selectedBox, onOpen }: { figure: PipelineFigure; selectedBox: string | null; onOpen: (box: FigureBox) => void }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const arrowEnd = `${uid}-arrow-end`;
  const arrowStart = `${uid}-arrow-start`;
  const hatch = `${uid}-hatch`;
  return (
    <svg className={styles.diagram} viewBox={`0 0 ${figure.width} ${figure.height}`} role="group" aria-label={`Figure ${figure.number}, redrawn: select a box for its details`} style={{ minWidth: Math.min(figure.width, 900) }}>
      <defs>
        <marker id={arrowEnd} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill="#26332d" />
        </marker>
        <marker id={arrowStart} viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" orient="auto">
          <path d="M10 0 L0 5 L10 10 z" fill="#26332d" />
        </marker>
        <pattern id={hatch} width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="10" stroke="#26332d" strokeWidth="1.3" opacity="0.5" />
        </pattern>
      </defs>

      {figure.frames?.map((frame) => (
        <g key={`${frame.x}-${frame.y}`}>
          <rect x={frame.x} y={frame.y} width={frame.w} height={frame.h} rx="3" fill="#ffffff" stroke="#26332d" strokeWidth={frame.stroke === "bold" ? 3.5 : 1.5} />
          {frame.title ? <text x={frame.x + frame.w / 2} y={frame.y + 26} textAnchor="middle" className={styles.svgTitle}>{frame.title}</text> : null}
        </g>
      ))}

      {figure.edges.map((edge, index) => (
        <polyline
          key={index}
          points={edge.points.map((point) => point.join(",")).join(" ")}
          fill="none"
          stroke="#26332d"
          strokeWidth={edge.dotted ? 1.2 : 1.8}
          strokeDasharray={edge.dashed ? "7 5" : edge.dotted ? "2 4" : undefined}
          markerEnd={edge.arrow === "none" ? undefined : `url(#${arrowEnd})`}
          markerStart={edge.arrow === "both" ? `url(#${arrowStart})` : undefined}
        />
      ))}

      {figure.notes.map((note) => (
        <text key={`${note.x}-${note.y}-${note.text}`} x={note.x} y={note.y} textAnchor={note.anchor ?? "start"} className={note.kind === "heading" ? styles.svgHeading : note.kind === "italic" ? styles.svgItalic : styles.svgSmall}>{note.text}</text>
      ))}

      {figure.boxes.map((box) => (
        <DiagramBox key={box.id} box={box} hatch={hatch} selected={selectedBox === box.id} onOpen={onOpen} />
      ))}
    </svg>
  );
}

function shapeOf(box: FigureBox) {
  const { x, y, w, h } = box;
  switch (box.shape) {
    case "data": {
      const skew = Math.min(28, w * 0.08);
      return { kind: "polygon" as const, points: `${x + skew},${y} ${x + w},${y} ${x + w - skew},${y + h} ${x},${y + h}` };
    }
    case "diamond":
      return { kind: "polygon" as const, points: `${x + w / 2},${y} ${x + w},${y + h / 2} ${x + w / 2},${y + h} ${x},${y + h / 2}` };
    case "terminal":
      return { kind: "rect" as const, rx: h / 2 };
    case "row":
      return { kind: "rect" as const, rx: 0 };
    default:
      return { kind: "rect" as const, rx: 5 };
  }
}

/** The status badge sits on the box's top-right corner, half outside it, so it never covers the label. */
function badgePosition(box: FigureBox): [number, number] {
  const { x, y, w, h } = box;
  if (box.shape === "diamond") return [x + w * 0.75 + 6, y + h * 0.25 - 6];
  if (box.shape === "row") return [x + w - 22, y + h / 2];
  if (box.shape === "terminal") return [x + w - Math.min(h / 2, 24) + 4, y + 2];
  if (box.shape === "data") return [x + w - 4, y + 2];
  return [x + w - 2, y + 2];
}

function DiagramBox({ box, hatch, selected, onOpen }: { box: FigureBox; hatch: string; selected: boolean; onOpen: (box: FigureBox) => void }) {
  const topic = TOPIC_BY_ID[box.topic];
  const shape = shapeOf(box);
  const stroke = box.stroke ?? "plain";
  const common = {
    fill: FILL[topic.status],
    stroke: "#26332d",
    strokeWidth: stroke === "bold" ? 3.5 : box.shape === "row" ? 1 : 1.6,
    strokeDasharray: stroke === "dashed" ? "8 6" : stroke === "dotted" ? "2 5" : undefined,
    className: styles.shape,
  };
  const onKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen(box);
    }
  };
  const [bx, by] = badgePosition(box);
  return (
    <g
      className={styles.box}
      data-box={box.id}
      data-status={topic.status}
      data-selected={selected}
      role="button"
      tabIndex={0}
      aria-label={`${boxLabel(box)}: ${STATUS_LABEL[topic.status]}`}
      onClick={() => onOpen(box)}
      onKeyDown={onKeyDown}
    >
      {shape.kind === "polygon"
        ? <polygon points={shape.points} {...common} />
        : <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={shape.rx} {...common} />}
      {stroke === "hatched"
        ? (shape.kind === "polygon"
          ? <polygon points={shape.points} fill={`url(#${hatch})`} pointerEvents="none" />
          : <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={shape.rx} fill={`url(#${hatch})`} pointerEvents="none" />)
        : null}
      <BoxText box={box} />
      <SvgBadge status={topic.status} x={bx} y={by} />
    </g>
  );
}

const LINE_STYLE: Record<NonNullable<FigureLine["kind"]>, { size: number; className: string }> = {
  title: { size: 22, className: styles.svgTitle },
  sub: { size: 20, className: styles.svgSub },
  kicker: { size: 30, className: styles.svgKicker },
  question: { size: 40, className: styles.svgQuestion },
};

function BoxText({ box }: { box: FigureBox }) {
  const heights = box.lines.map((line) => LINE_STYLE[line.kind ?? "title"].size);
  const total = heights.reduce((sum, height) => sum + height, 0);
  const top = box.y + box.h / 2 - total / 2;
  // The baseline of each line: the top of the block plus the heights of this line and the ones above it.
  const baselines = heights.map((_, index) => top + heights.slice(0, index + 1).reduce((sum, height) => sum + height, 0));
  return (
    <text textAnchor="middle" pointerEvents="none">
      {box.lines.map((line, index) => {
        const style = LINE_STYLE[line.kind ?? "title"];
        return <tspan key={index} x={box.x + box.w / 2} y={baselines[index] - style.size * 0.28} className={style.className}>{line.text}</tspan>;
      })}
    </text>
  );
}

function SvgBadge({ status, x, y }: { status: StageStatus; x: number; y: number }) {
  if (status === "done") {
    return (
      <g pointerEvents="none" aria-hidden="true">
        <circle cx={x} cy={y} r="10" fill="#1f7a4d" />
        <path d={`M${x - 4.5} ${y} L${x - 1} ${y + 3.5} L${x + 5} ${y - 3.5}`} fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    );
  }
  if (status === "in_progress") {
    return (
      <g pointerEvents="none" aria-hidden="true">
        <circle cx={x} cy={y} r="10" fill="#fff" stroke="#b26a00" strokeWidth="2.4" />
        <path d={`M${x} ${y - 7.6} A7.6 7.6 0 0 1 ${x} ${y + 7.6} Z`} fill="#b26a00" />
      </g>
    );
  }
  return (
    <g pointerEvents="none" aria-hidden="true">
      <circle cx={x} cy={y} r="10" fill="#fff" stroke="#7d8781" strokeWidth="2.2" strokeDasharray="3 2.4" />
    </g>
  );
}

export function StatusIcon({ status }: { status: StageStatus }) {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <SvgBadge status={status} x={12} y={12} />
    </svg>
  );
}

function ProgressBar({ counts }: { counts: Record<StageStatus, number> }) {
  const total = counts.done + counts.in_progress + counts.not_started || 1;
  return (
    <div className={styles.bar} role="img" aria-label={STATUSES.map((status) => `${counts[status]} ${STATUS_LABEL[status].toLowerCase()}`).join(", ")}>
      {STATUSES.map((status) => counts[status] ? <span key={status} data-status={status} style={{ width: `${(counts[status] / total) * 100}%` }} /> : null)}
    </div>
  );
}

export function DetailPanel({ topic, onClose }: { topic: PipelineTopic; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [topic.id, onClose]);

  const figures = figuresOfTopic(topic.id);
  return (
    <div className={styles.overlay} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className={styles.panel} role="dialog" aria-modal="true" aria-labelledby={titleId} data-topic={topic.id}>
        <div className={styles.panelHead}>
          <span className={styles.pill} data-status={topic.status}><StatusIcon status={topic.status} /> {STATUS_LABEL[topic.status]}</span>
          <button ref={closeButton} type="button" className={styles.close} onClick={onClose} aria-label="Close the details">×</button>
        </div>
        <h2 id={titleId}>{topic.title}</h2>
        <p className={styles.panelMeta}>{figures.length ? `Drawn in proposal figure${figures.length > 1 ? "s" : ""} ${figures.join(", ")} · ` : ""}as of {PIPELINE_AS_OF}</p>
        <p className={styles.summary}>{topic.summary}</p>

        <h3>What the proposal plans</h3>
        <p>{topic.proposal}</p>

        <h3>Where it stands</h3>
        {topic.now.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}

        {topic.numbers?.length ? (
          <>
            <h3>Figures</h3>
            <dl className={styles.numbers}>
              {topic.numbers.map((number) => <div key={number.label}><dt>{number.label}</dt><dd>{number.value}</dd></div>)}
            </dl>
          </>
        ) : null}

        {topic.chart ? <DetailBarChart chart={topic.chart} /> : null}

        {topic.media?.map((media) => (
          <figure key={media.src} className={styles.media}>
            <a href={media.src} target="_blank" rel="noreferrer" title="Open the image at full size">
              {/* eslint-disable-next-line @next/next/no-img-element -- static files of this site, shown at their own size */}
              <img src={media.src} alt={media.alt} loading="lazy" />
            </a>
            <figcaption>{media.caption}</figcaption>
          </figure>
        ))}

        {topic.missing?.length ? (
          <>
            <h3>Still missing</h3>
            <ul className={styles.missing}>{topic.missing.map((item) => <li key={item}>{item}</li>)}</ul>
          </>
        ) : null}

        <h3>Open the evidence</h3>
        <ul className={styles.links}>
          {topic.links.map((link) => {
            const href = linkHref(link);
            const external = !href.startsWith("/");
            return (
              <li key={link.label}>
                <a href={href} target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined}>
                  {link.label}{external ? <span aria-hidden="true"> ↗</span> : null}
                </a>
                {link.path ? <code>{link.path}</code> : null}
              </li>
            );
          })}
        </ul>
        <p className={styles.panelFoot}>Planning guidance from modelled figures. Not real-time and not an official warning.</p>
      </aside>
    </div>
  );
}

function DetailBarChart({ chart }: { chart: DetailChart }) {
  const labelWidth = 210;
  const plot = 250;
  const row = 34;
  const top = 8;
  const height = top + chart.bars.length * row + 34;
  const scale = (value: number) => (value / chart.max) * plot;
  const ticks = [0, chart.max / 2, chart.max];
  const tick = (value: number) => chart.max <= 1 ? String(Number(value.toFixed(2))) : value.toLocaleString("en-US");
  return (
    <figure className={styles.chart}>
      <figcaption className={styles.chartTitle}>{chart.title}</figcaption>
      <svg viewBox={`0 0 ${labelWidth + plot + 90} ${height}`} role="img" aria-label={`${chart.title}: ${chart.bars.map((bar) => `${bar.label} ${bar.display ?? bar.value}`).join("; ")}`}>
        {ticks.map((value) => (
          <g key={value}>
            <line x1={labelWidth + scale(value)} x2={labelWidth + scale(value)} y1={top - 4} y2={height - 26} stroke="#e1e5e3" />
            <text x={labelWidth + scale(value)} y={height - 10} textAnchor="middle" className={styles.chartTick}>{tick(value)}</text>
          </g>
        ))}
        {chart.bars.map((bar, index) => {
          const y = top + index * row;
          return (
            <g key={bar.label}>
              <text x={labelWidth - 10} y={y + 19} textAnchor="end" className={bar.highlight ? styles.chartLabelStrong : styles.chartLabel}>{bar.label}</text>
              <rect x={labelWidth} y={y + 4} width={Math.max(2, scale(Math.min(bar.value, chart.max)))} height={row - 12} rx="3" fill={bar.highlight ? "#087f8c" : "#a9b2ad"} />
              <text x={labelWidth + scale(Math.min(bar.value, chart.max)) + 6} y={y + 19} className={styles.chartValue}>{bar.display ?? bar.value}</text>
            </g>
          );
        })}
        {chart.rule ? (
          <g>
            <line x1={labelWidth + scale(chart.rule.value)} x2={labelWidth + scale(chart.rule.value)} y1={top - 6} y2={height - 26} stroke="#b3261e" strokeWidth="2" strokeDasharray="5 4" />
          </g>
        ) : null}
      </svg>
      <p className={styles.chartNote}>
        {chart.rule ? <><span className={styles.ruleKey} aria-hidden="true" /> {chart.rule.label}. </> : null}
        {chart.axis}. {chart.note}
      </p>
    </figure>
  );
}
