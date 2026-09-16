"use client";

import Image from "next/image";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import type { StudyAsset, StudyMetrics, StudyModel, StudyRole } from "@/lib/study-report-types";
import { useLanguage } from "@/lib/use-language";
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
const THAI_SECTION_NAMES: Record<StudySection, string> = {
  overview: "ภาพรวม", data: "ข้อมูลและการแบ่งเหตุการณ์", models: "โมเดลและการฝึก",
  results: "ผลการประเมิน", rtc: "การเปรียบเทียบภาพ RTC ที่จับคู่", explorer: "สำรวจข้อผิดพลาดจากภาพ",
  files: "ไฟล์และการทำซ้ำ", "mae-sai": "การประยุกต์ใช้ที่แม่สาย",
};
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
  const [language] = useLanguage("en");
  const th = language === "th";
  const text = (en: string, thai: string) => th ? thai : en;
  const sectionName = (id: StudySection, english: string) => th ? THAI_SECTION_NAMES[id] : english;
  const mae = section === "mae-sai";
  const currentSection = SECTIONS.find(([id]) => id === section);
  return <div className={styles.page} lang={language}>
    <StudioLibraryHeader />
    <main id="main-content" className={styles.main}>
      <nav aria-label={text("Breadcrumb", "เส้นทางนำทาง")} className={styles.breadcrumb}>
        <a href="/studio/">{text("Studies & evidence", "งานศึกษาและหลักฐาน")}</a><span>/</span>
        <a href={`${STUDY_BASE}/`}>C2S-MS</a>
        {section !== "overview" && currentSection ? <><span>/</span><span>{sectionName(section, currentSection[1])}</span></> : null}
      </nav>
      <header className={styles.hero}>
        <p className={styles.eyebrow}>{mae
          ? text("Separate inference record · Thailand", "บันทึกการอนุมานแยกต่างหาก · ประเทศไทย")
          : text("Public benchmark · Human water reference", "การประเมินด้วยข้อมูลสาธารณะ · ข้อมูลอ้างอิงพื้นที่น้ำที่มนุษย์กำกับ")}</p>
        <h1>{mae ? text("Mae Sai · application of C2S models", "แม่สาย · การประยุกต์ใช้โมเดล C2S") : text("C2S-MS public benchmark", "การประเมินด้วยข้อมูลสาธารณะ C2S-MS")}</h1>
        <p>{mae
          ? text("Frozen C2S-trained models applied to the August / September 2024 Sentinel-1 pair. Inspect probability, uncertainty and abstention for the recorded acquisition.", "นำโมเดลที่ฝึกด้วย C2S และตรึงเวอร์ชันแล้วมาใช้กับภาพ Sentinel-1 คู่เดือนสิงหาคมและกันยายน ค.ศ. 2024 สำรวจความน่าจะเป็น ความไม่แน่นอน และพื้นที่ที่โมเดลงดตัดสินจากภาพที่บันทึกไว้")
          : text("A reproducible study of Random Forest, XGBoost and SAR U-Net across independent events. The target is event-date water, including permanent water.", "งานศึกษาที่ทำซ้ำได้ของ Random Forest, XGBoost และ SAR U-Net โดยแยกเหตุการณ์ออกจากกัน เป้าหมายคือพื้นที่น้ำในวันที่บันทึกภาพเหตุการณ์ รวมถึงแหล่งน้ำถาวร")}</p>
        <div className={styles.badges}>
          <span className={styles.badge}>{mae ? text("Inference completed", "อนุมานเสร็จสิ้น") : text("Benchmark completed", "ประเมินเสร็จสิ้น")}</span>
          <span className={styles.badge}>{text("Report only", "ใช้เพื่อรายงานเท่านั้น")}</span>
          <span className={styles.badge}>{mae ? text("Thai accuracy unmeasured", "ยังไม่ได้วัดความแม่นยำในประเทศไทย") : text("C2S-MS human labels", "ป้ายกำกับ C2S-MS โดยมนุษย์")}</span>
        </div>
        <dl className={styles.context}>
          <div><dt>{mae ? text("Observations · UTC", "วันบันทึกภาพ · UTC") : text("Observation period", "ช่วงเวลาบันทึกภาพ")}</dt><dd>{mae ? text("22 Aug / 15 Sep 2024", "22 ส.ค. / 15 ก.ย. ค.ศ. 2024") : text("12 Aug 2016 – 20 Oct 2020", "12 ส.ค. ค.ศ. 2016 – 20 ต.ค. ค.ศ. 2020")}</dd></div>
          <div><dt>{mae ? text("Evaluation status", "สถานะการประเมิน") : text("Held-out evaluation", "เหตุการณ์ที่กันไว้ประเมิน")}</dt><dd>{mae ? text("No qualified Thai reference", "ยังไม่มีข้อมูลอ้างอิงไทยที่ผ่านเกณฑ์") : text("Australia · Nigeria · Pakistan", "ออสเตรเลีย · ไนจีเรีย · ปากีสถาน")}</dd></div>
          <div><dt>{text("Study / revision", "งานศึกษา / ฉบับ")}</dt><dd>c2s-ms-20260915 · r1</dd></div>
          <div><dt>{mae ? text("Model lineage", "ที่มาของโมเดล") : text("Experiment date", "วันที่ทดลอง")}</dt><dd>{mae ? text("Evaluated on C2S-MS; applied to Mae Sai", "ประเมินบน C2S-MS แล้วนำมาใช้กับแม่สาย") : text("15 September 2026", "15 กันยายน ค.ศ. 2026")}</dd></div>
        </dl>
      </header>
      <div className={styles.layout}>
        <nav className={styles.sidebar} aria-label={text("C2S study sections", "ส่วนต่าง ๆ ของงานศึกษา C2S")}>
          <p>{text("Inside this study", "ภายในงานศึกษานี้")}</p>
          {SECTIONS.map(([id, label, path], i) => <a key={id} href={`${STUDY_BASE}${path}/`} aria-current={section === id ? "page" : undefined}><span>{String(i + 1).padStart(2, "0")}</span>{sectionName(id, label)}</a>)}
        </nav>
        <div className={styles.content}>
          <label className={styles.mobileNav}>{text("Study section", "ส่วนของงานศึกษา")}<select value={section} onChange={(e) => { const item = SECTIONS.find(([id]) => id === e.target.value); if (item) window.location.assign(`${STUDY_BASE}${item[2]}/`); }}>{SECTIONS.map(([id, label]) => <option value={id} key={id}>{sectionName(id, label)}</option>)}</select></label>
          {th ? <Notice>รายละเอียดการทดลอง ผลลัพธ์ และหลักฐานต้นฉบับด้านล่างคงไว้เป็นภาษาอังกฤษ การเปลี่ยนภาษาส่วนติดต่อไม่เปลี่ยนข้อมูลหรือขอบเขตการประเมิน</Notice> : null}
          <div lang="en">{children}</div>
          <footer className={styles.footer}>
            {text("C2S-MS · revision r1 · research report only. These outputs cannot feed exposure, road risk, access, equity or FPPS. FloodGuard supports preparedness and rapid post-event prioritisation; this study is not an official warning.", "C2S-MS · ฉบับ r1 · รายงานวิจัยเท่านั้น ผลลัพธ์นี้ไม่สามารถนำไปใช้คำนวณการรับสัมผัสภัย ความเสี่ยงถนน การเข้าถึง ความเป็นธรรม หรือ FPPS ได้ FloodGuard สนับสนุนการเตรียมพร้อมและการจัดลำดับความสำคัญอย่างรวดเร็วหลังเหตุการณ์ งานศึกษานี้ไม่ใช่การแจ้งเตือนอย่างเป็นทางการ")}
            <br /><a href="/studio/">{text("All studies", "งานศึกษาทั้งหมด")}</a> · <a href="/studio/planning-evidence/">{text("Planning evidence", "หลักฐานเพื่อการวางแผน")}</a> · <a href="/studio/archive/mae-sai-geoai/">{text("Historical research", "งานวิจัยที่ผ่านมา")}</a>
          </footer>
        </div>
      </div>
    </main>
  </div>;
}
