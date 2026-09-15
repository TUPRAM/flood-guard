"use client";

import Image from "next/image";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import type { StudyAsset, StudyMetrics, StudyModel, StudyRole } from "@/lib/study-report-types";
import { StudioLibraryHeader } from "./studio-library";
import styles from "./c2s-study.module.css";

export const STUDY_BASE = "/studio/studies/c2s-ms-20260915";
export const STUDY_ASSETS = "/studies/c2s-ms-20260915/r1/";
export const SECTIONS = [
  ["overview", "Overview", ""], ["data", "Data & event split", "/data"],
  ["models", "Models & training", "/models"], ["results", "Benchmark results", "/results"],
  ["rtc", "Matched RTC comparison", "/rtc"], ["explorer", "Visual error explorer", "/explorer"],
  ["files", "Files & reproducibility", "/files"], ["mae-sai", "Mae Sai application", "/mae-sai"],
] as const;
export type StudySection = typeof SECTIONS[number][0];
export const MODEL_NAMES: Record<StudyModel, string> = { random_forest: "Random Forest", xgboost: "XGBoost", unet: "U-Net", vh_otsu: "VH Otsu" };
export const ROLE_NAMES: Record<StudyRole, string> = { train: "Training", tune: "Tuning", calibration: "Calibration", selection: "Selection", test: "Final test" };
export const ROLE_COLORS: Record<StudyRole, string> = { train: "#4a8b73", tune: "#8272bb", calibration: "#c79a3e", selection: "#3c8cac", test: "#cf6b54" };
export const num = (n: number | null | undefined, digits = 4) => n == null || !Number.isFinite(n) ? "Unavailable" : n.toFixed(digits);
export const count = (n: number | null | undefined) => n == null || !Number.isFinite(n) ? "Unavailable" : n.toLocaleString("en-US");
export const percent = (n: number | null | undefined, digits = 2) => n == null || !Number.isFinite(n) ? "Unavailable" : `${(n * 100).toFixed(digits)}%`;

export function useStudyResource<T>(key: string, load: () => Promise<T>) {
  const [state, setState] = useState<{ key: string; data: T | null; error: string | null }>({ key: "", data: null, error: null });
  useEffect(() => {
    if (!key) return;
    let active = true;
    load().then((data) => { if (active) setState({ key, data, error: null }); })
      .catch((error: unknown) => { if (active) setState({ key, data: null, error: error instanceof Error ? error.message : "The study asset could not be read." }); });
    return () => { active = false; };
  }, [key, load]);
  return state.key === key ? state : { key, data: null, error: null };
}

function subscribeQuery(notify: () => void) { window.addEventListener("popstate", notify); return () => window.removeEventListener("popstate", notify); }
function querySnapshot() { return window.location.search; }
export function useStudyQuery() {
  const query = useSyncExternalStore(subscribeQuery, querySnapshot, () => "");
  const values = new URLSearchParams(query);
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(changes)) { if (value == null || value === "") next.delete(key); else next.set(key, value); }
    const suffix = next.toString();
    window.history.pushState(null, "", `${window.location.pathname}${suffix ? `?${suffix}` : ""}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  return { values, update };
}

export function SectionHeading({ title, note }: { title: string; note?: string }) { return <div className={styles.sectionHeading}><h2>{title}</h2>{note ? <span>{note}</span> : null}</div>; }
export function Unavailable({ reason, title = "Study asset unavailable" }: { reason: string; title?: string }) { return <div className={styles.error} role="alert"><h3>{title}</h3><p>{reason}</p><p>This record does not substitute data from another study, model or revision.</p></div>; }
export function Loading({ children = "Loading the recorded study evidence…" }: { children?: ReactNode }) { return <div className={styles.loading} role="status">{children}</div>; }
export function Notice({ children }: { children: ReactNode }) { return <aside className={styles.notice}>{children}</aside>; }
export function AssetLink({ asset }: { asset: StudyAsset }) { return <a href={asset.href} download><span>{asset.label}<small>{count(asset.bytes)} bytes · SHA-256 {asset.sha256.slice(0, 12)}…</small></span><span aria-hidden="true">↓</span></a>; }

export function MetricTable({ rows, caption }: { rows: Array<{ label: string; metrics: StudyMetrics; note?: string }>; caption: string }) {
  return <div className={styles.tableWrap}><table className={styles.table}><caption>{caption}</caption><thead><tr><th scope="col">Model / event</th><th scope="col">Water IoU ↑</th><th scope="col">Dice / F1 ↑</th><th scope="col">Precision ↑</th><th scope="col">Recall ↑</th><th scope="col">Brier ↓</th><th scope="col">ECE ↓</th><th scope="col">Valid pixels</th></tr></thead><tbody>{rows.map(({ label, metrics: m, note }) => <tr key={label}><td><strong>{label}</strong>{note ? <small>{note}</small> : null}</td>{[m.iou, m.f1_dice, m.precision, m.recall].map((value, i) => <td className={styles.num} key={i}>{num(value)}</td>)}<td className={styles.num}>{num(m.brier, 6)}</td><td className={styles.num}>{num(m.ece, 6)}</td><td className={styles.num}>{count(m.n_pixels)}</td></tr>)}</tbody></table></div>;
}

export function ConfusionTable({ metrics }: { metrics: StudyMetrics }) {
  return <div className={styles.tableWrap}><table className={styles.table}><caption>Pixel counts against the C2S-MS human water reference. Unknown and invalid pixels are excluded.</caption><thead><tr><th>Reference / prediction</th><th>Predicted water</th><th>Predicted non-water</th></tr></thead><tbody><tr><th scope="row">Reference water</th><td><strong>{count(metrics.true_positive)}</strong><small>True positive · found water</small></td><td><strong>{count(metrics.false_negative)}</strong><small>False negative · missed water</small></td></tr><tr><th scope="row">Reference non-water</th><td><strong>{count(metrics.false_positive)}</strong><small>False positive · false alarm</small></td><td><strong>{count(metrics.true_negative)}</strong><small>True negative · correctly dry</small></td></tr></tbody></table></div>;
}

export interface VisualLayer {
  url: string; sha256?: string; width?: number; height?: number;
  display?: { kind?: string; min?: number; max?: number; palette?: string; units?: string; invalid_color?: string; legend?: Array<{ value: string | number; label: string; color: string }> };
}
export function isStudyVisualUrl(url: string) { return url.startsWith(`${STUDY_ASSETS}visuals/`) && !url.includes("..") && /^[a-zA-Z0-9_./-]+\.png$/.test(url); }
export function studyVisualRequestUrl(layer: VisualLayer) { return layer.sha256 && /^[a-f0-9]{64}$/.test(layer.sha256) ? `${layer.url}?sha256=${layer.sha256}` : layer.url; }
export function VisualLegend({ layer }: { layer: VisualLayer }) {
  const display = layer.display;
  if (!display) return null;
  const palette = display.palette === "magma" ? "linear-gradient(90deg,#000004,#51127c,#b63679,#fb8861,#fcfdbf)" : display.palette === "gray" ? "linear-gradient(90deg,#000,#fff)" : undefined;
  return <span className={styles.legend}>{display.legend?.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}</span>)}{display.min != null && display.max != null ? <span>{display.min}<i className={styles.gradient} style={{ background:palette, width:110 }} />{display.max} {display.units}</span> : null}<span><i style={{ background:display.invalid_color ?? "#b9b9b9" }} />Invalid</span></span>;
}
export function StudyFigure({ layer, title, description, overlay }: { layer?: VisualLayer; title: string; description?: string; overlay?: VisualLayer }) {
  const [failed, setFailed] = useState<string | null>(null);
  const [overlayLoaded, setOverlayLoaded] = useState<string | null>(null);
  const [overlayFailed, setOverlayFailed] = useState<string | null>(null);
  const available = layer && isStudyVisualUrl(layer.url) && failed !== layer.url;
  const overlayAvailable = available && overlay && isStudyVisualUrl(overlay.url) && overlayFailed !== overlay.url && overlay.width === layer?.width && overlay.height === layer?.height;
  return <figure className={styles.figure}>{available ? <a className={styles.imageStack} href={studyVisualRequestUrl(layer)} target="_blank" rel="noreferrer"><Image src={studyVisualRequestUrl(layer)} alt={title} width={layer.width ?? 512} height={layer.height ?? 512} unoptimized loading="lazy" onError={() => setFailed(layer.url)} />{overlayAvailable ? <Image className={styles.overlayImage} style={{visibility:overlayLoaded === overlay.url ? "visible" : "hidden"}} src={studyVisualRequestUrl(overlay)} alt="Abstention overlay at 35 percent opacity" width={overlay.width ?? 512} height={overlay.height ?? 512} unoptimized loading="lazy" onLoad={() => setOverlayLoaded(overlay.url)} onError={() => setOverlayFailed(overlay.url)} /> : null}</a> : <div className={styles.imageUnavailable}>Preview unavailable for this record.<br />No replacement image is shown.</div>}<figcaption><strong>{title}</strong>{description ? <span>{description}</span> : null}{overlay ? overlayAvailable ? overlayLoaded === overlay.url ? <span className={styles.overlayNote}>Abstention overlay applied at 35% opacity (multiply). Light green: accepted; magenta: abstained; grey: invalid. Turn it off to read the original probability or entropy colours.</span> : <span role="status">Loading the abstention overlay…</span> : <span role="alert">Abstention overlay unavailable or incompatible. The base image is shown without the overlay.</span> : null}{available ? <><VisualLegend layer={layer}/><span>Open the recorded preview · benchmark metrics use full-resolution source pixels.</span></> : null}</figcaption></figure>;
}

export function StudyFrame({ section, children }: { section: StudySection; children: ReactNode }) {
  const mae = section === "mae-sai";
  return <div className={styles.page} lang="en"><StudioLibraryHeader /><main id="main-content" className={styles.main}><nav aria-label="Breadcrumb" className={styles.breadcrumb}><a href="/studio/">Studies &amp; evidence</a><span>/</span><a href={`${STUDY_BASE}/`}>C2S-MS</a>{section !== "overview" ? <><span>/</span><span>{SECTIONS.find(([id]) => id === section)?.[1]}</span></> : null}</nav><header className={styles.hero}><p className={styles.eyebrow}>{mae ? "Separate inference record · Thailand" : "Public benchmark · Human water reference"}</p><h1>{mae ? "Mae Sai · application of C2S models" : "C2S-MS public benchmark"}</h1><p>{mae ? "Frozen C2S-trained models applied to the August / September 2024 Sentinel-1 pair. Inspect probability, uncertainty and abstention for the recorded acquisition." : "A reproducible study of Random Forest, XGBoost and SAR U-Net across independent events. The target is event-date water, including permanent water."}</p><div className={styles.badges}><span className={styles.badge}>{mae ? "Inference completed" : "Benchmark completed"}</span><span className={styles.badge}>Report only</span><span className={styles.badge}>{mae ? "Thai accuracy unmeasured" : "C2S-MS human labels"}</span></div><dl className={styles.context}><div><dt>{mae ? "Observations · UTC" : "Observation period"}</dt><dd>{mae ? "22 Aug / 15 Sep 2024" : "12 Aug 2016 – 20 Oct 2020"}</dd></div><div><dt>{mae ? "Evaluation status" : "Held-out evaluation"}</dt><dd>{mae ? "No qualified Thai reference" : "Australia · Nigeria · Pakistan"}</dd></div><div><dt>Study / revision</dt><dd>c2s-ms-20260915 · r1</dd></div><div><dt>{mae ? "Model lineage" : "Experiment date"}</dt><dd>{mae ? "Evaluated on C2S-MS; applied to Mae Sai" : "15 September 2026"}</dd></div></dl></header><div className={styles.layout}><nav className={styles.sidebar} aria-label="C2S study sections"><p>Inside this study</p>{SECTIONS.map(([id, label, path], i) => <a key={id} href={`${STUDY_BASE}${path}/`} aria-current={section === id ? "page" : undefined}><span>{String(i + 1).padStart(2, "0")}</span>{label}</a>)}</nav><div className={styles.content}><label className={styles.mobileNav}>Study section<select value={section} onChange={(e) => { const item = SECTIONS.find(([id]) => id === e.target.value); if (item) window.location.assign(`${STUDY_BASE}${item[2]}/`); }}>{SECTIONS.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>{children}<footer className={styles.footer}>C2S-MS · revision r1 · research report only. These outputs cannot feed exposure, road risk, access, equity or FPPS. FloodGuard supports preparedness and rapid post-event prioritisation; this study is not an official warning.<br /><a href="/studio/">All studies</a> · <a href="/studio/planning-evidence/">Planning evidence</a> · <a href="/studio/archive/mae-sai-geoai/">Historical research</a></footer></div></div></main></div>;
}
