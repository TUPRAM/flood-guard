"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { EvidenceAvailability, EvidenceLibraryCatalog, EvidenceLibraryGauge, EvidenceLibraryPackage } from "@floodguard/contracts";
import { LanguageToggle } from "@/components/language-toggle";
import { EvidenceFeatureBrowser } from "./evidence-library-features";
import { useLanguage } from "@/lib/use-language";
import { EVIDENCE_CATALOG_URL, evidenceAssetUrl, fetchEvidencePackage, gaugeSegments, parseEvidenceCatalog, selectEvidencePackage, sourceClockCoordinate } from "@/lib/evidence-library";
import styles from "./evidence-library.module.css";

const EvidenceMap = dynamic(() => import("./evidence-library-map").then((module) => module.EvidenceLibraryMap), { ssr: false });
const STATUS: Record<EvidenceAvailability, [string, string]> = {
  available: ["Available", "มีข้อมูล"], partial: ["Partial coverage", "ข้อมูลบางส่วน"],
  metadata_only: ["Metadata only", "เฉพาะข้อมูลกำกับ"], missing: ["Not acquired", "ยังไม่ได้ข้อมูล"], blocked: ["Blocked", "ยังใช้ไม่ได้"],
};
const SUPPORTING_SOURCES = new Set(["project-scenarios", "context-osm", "context-worldpop"]);

export function EvidenceGaugeChart({ gauge, th }: { gauge: EvidenceLibraryGauge; th: boolean }) {
  const segments = gaugeSegments(gauge.points, 10 * 60 * 1000, gauge.timezone);
  const numeric = segments.flat();
  const times = gauge.points.map((point) => sourceClockCoordinate(point.time, gauge.timezone)).filter(Number.isFinite);
  const values = numeric.map((point) => point.value as number);
  const minTime = Math.min(...times); const maxTime = Math.max(...times);
  const minimum = Math.min(...values); const maximum = Math.max(...values);
  const x = (time: string) => 55 + ((sourceClockCoordinate(time, gauge.timezone) - minTime) / (maxTime - minTime || 1)) * 660;
  const y = (value: number) => 175 - ((value - minimum) / (maximum - minimum || 1)) * 130;
  return <article className={styles.gauge}>
    <h3>{gauge.name} <small>{gauge.id}</small></h3>
    <p>{gauge.units} · {th ? "เขตเวลา" : "Timezone"}: {gauge.timezone ?? (th ? "ยังไม่ยืนยัน" : "not confirmed")}</p>
    {numeric.length ? <svg viewBox="0 0 750 215" role="img" aria-label={`${gauge.name}: ${th ? "ระดับน้ำ เว้นช่องว่างเมื่อไม่มีข้อมูล" : "water level; gaps remain disconnected"}`} className={styles.chart}>
      <line x1="55" y1="175" x2="715" y2="175" stroke="#9aaab4" />
      <text x="5" y="48">{maximum.toFixed(2)}</text><text x="5" y="178">{minimum.toFixed(2)}</text>
      <text x="55" y="203">{gauge.points[0]?.time.slice(0, 16)}</text><text x="715" y="203" textAnchor="end">{gauge.points.at(-1)?.time.slice(0, 16)}</text>
      {segments.map((segment, index) => segment.length === 1
        ? <circle key={index} cx={x(segment[0].time)} cy={y(segment[0].value as number)} r="2.5" fill="#087e8b" />
        : <path key={index} data-gauge-segment="true" d={segment.map((point, pointIndex) => `${pointIndex ? "L" : "M"}${x(point.time).toFixed(2)},${y(point.value as number).toFixed(2)}`).join(" ")} fill="none" stroke="#087e8b" strokeWidth="2" />)}
    </svg> : <p className={styles.empty}>{th ? "ไม่มีค่าตรวจวัดที่แสดงได้" : "No usable observations to plot."}</p>}
    <p className={styles.hint}>{th ? "แกนเวลาใช้เวลาของแหล่งข้อมูล ไม่แปลงเป็นเขตเวลาของผู้ดู ช่องว่างไม่ใช่ศูนย์ ไม่มีการประมาณจุดสูงสุด ระดับน้ำไม่ใช่ความลึกน้ำท่วม" : "Source-clock axis; no conversion to the viewer's timezone. Gaps are not zero. No peak interpolation. Water-surface elevation is not flood depth."}</p>
    <ul>{gauge.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
  </article>;
}

export function EvidenceLibrary({ initialCatalog = null, initialPackage = null, initialAoiId, initialEventId }: {
  initialCatalog?: EvidenceLibraryCatalog | null; initialPackage?: EvidenceLibraryPackage | null; initialAoiId?: string; initialEventId?: string;
} = {}) {
  const [language, setLanguage] = useLanguage("en");
  const th = language === "th";
  const [catalog, setCatalog] = useState(initialCatalog);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selection, setSelection] = useState({ aoi: initialAoiId ?? initialCatalog?.packages[0]?.aoi_id ?? "", event: initialEventId ?? initialCatalog?.packages[0]?.event_id ?? "" });
  const [loaded, setLoaded] = useState<{ package: EvidenceLibraryPackage | null; referenceId: string; error: string | null }>({ package: initialPackage, referenceId: initialPackage?.id ?? "", error: null });

  useEffect(() => {
    if (initialCatalog) return;
    const controller = new AbortController();
    fetch(EVIDENCE_CATALOG_URL, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`Catalog unavailable (${response.status}).`);
      return parseEvidenceCatalog(await response.json());
    }).then((next) => {
      if (controller.signal.aborted) return;
      const query = new URLSearchParams(window.location.search);
      setCatalog(next);
      setSelection({ aoi: query.get("aoi") ?? next.packages[0]?.aoi_id ?? "", event: query.get("event") ?? next.packages[0]?.event_id ?? "" });
    }).catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    return () => controller.abort();
  }, [initialCatalog]);

  const reference = catalog ? selectEvidencePackage(catalog, selection.aoi, selection.event) : null;
  useEffect(() => {
    if (!catalog || !reference || initialPackage?.id === reference.id) return;
    const controller = new AbortController();
    fetchEvidencePackage(catalog, reference, controller.signal)
      .then((next) => { if (!controller.signal.aborted) setLoaded({ package: next, referenceId: reference.id, error: null }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoaded({ package: null, referenceId: reference.id, error: error instanceof Error ? error.message : "Package unavailable" }); });
    return () => controller.abort();
  }, [catalog, reference, initialPackage]);

  function choose(next: typeof selection) {
    setSelection(next);
    const query = new URLSearchParams({ aoi: next.aoi, event: next.event });
    window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
  }
  const evidence = reference && loaded.referenceId === reference.id ? loaded.package : null;
  const packageError = reference && loaded.referenceId === reference.id ? loaded.error : null;
  const aoi = catalog?.aois.find((item) => item.id === selection.aoi);
  const event = catalog?.events.find((item) => item.id === selection.event);
  const reportUrl = evidenceAssetUrl(evidence?.report_url);

  return <main id="main-content" className={styles.library} data-evidence-library="true">
    <header className={styles.header}>
      <a className={styles.brand} href="/studio/">FloodGuard <span>Studio</span></a>
      <nav aria-label={th ? "หน้าหลักฐาน" : "Evidence navigation"}><a href="/studio/">{th ? "รายงานการตรวจสอบ" : "Validation report"}</a><a href="/studio/library/" aria-current="page">{th ? "คลังข้อมูล" : "Evidence library"}</a></nav>
      <LanguageToggle language={language} onChange={setLanguage} />
    </header>
    <div className={styles.content}>
      <div className={styles.heading}><div><p className={styles.eyebrow}>{th ? "หลักฐานสำหรับต้นแบบ" : "PROTOTYPE EVIDENCE"}</p><h1>{th ? "คลังข้อมูลพื้นที่ศึกษา" : "Study-area evidence library"}</h1><p>{th ? "ตรวจสอบข้อมูลที่มี ช่องว่าง และสมมติฐานของแต่ละพื้นที่และเหตุการณ์" : "Inspect acquired data, coverage gaps and assumptions for each area and event."}</p></div><span className={styles.badge}>{th ? "ไม่ใช่ระบบปฏิบัติการ" : "Non-operational"}</span></div>
      <aside className={styles.notice}>{th ? "ข้อมูลวิจัยที่ยังไม่ผ่านการรับรอง ไม่ใช่คำเตือนภัย เส้นทางปลอดภัย หรือการยืนยันความพร้อมของศูนย์พักพิง ไม่มีการเปลี่ยนเกณฑ์รับรองหลักฐาน" : "Candidate research evidence. This is not an official warning, a safe-route recommendation or confirmation of shelter availability. Evidence acceptance gates remain unchanged."}</aside>
      {catalogError ? <div className={styles.error} role="alert">{th ? "โหลดคลังข้อมูลไม่ได้" : "Evidence catalog unavailable"}: {catalogError}</div> : null}
      {!catalog && !catalogError ? <p role="status">{th ? "กำลังโหลดคลังข้อมูล…" : "Loading evidence catalog…"}</p> : null}
      {catalog ? <>
        <section className={styles.selectors} aria-label={th ? "เลือกพื้นที่และเหตุการณ์" : "Area and event selection"}>
          <label htmlFor="evidence-aoi">{th ? "พื้นที่ศึกษา" : "Study area"}<select id="evidence-aoi" value={selection.aoi} onChange={(e) => choose({ ...selection, aoi: e.target.value })}>
            {!aoi ? <option value={selection.aoi}>{selection.aoi || (th ? "เลือกพื้นที่" : "Select area")}</option> : null}
            {catalog.aois.map((item) => <option key={item.id} value={item.id}>{th ? item.name_th ?? item.name : item.name}</option>)}
          </select></label>
          <label htmlFor="evidence-event">{th ? "เหตุการณ์" : "Event"}<select id="evidence-event" value={selection.event} onChange={(e) => choose({ ...selection, event: e.target.value })}>
            {!event ? <option value={selection.event}>{selection.event || (th ? "เลือกเหตุการณ์" : "Select event")}</option> : null}
            {catalog.events.map((item) => <option key={item.id} value={item.id}>{th ? item.name_th ?? item.name : item.name}</option>)}
          </select></label>
          <div className={styles.selectionMeta}>{event ? `${event.start} — ${event.end}` : null}<small>{catalog.packages.length} {th ? "ชุดพื้นที่/เหตุการณ์" : "area/event packages"} · {catalog.package_version}</small></div>
        </section>
        {!reference ? <p className={styles.error} role="alert">{th ? "ไม่มีชุดข้อมูลสำหรับพื้นที่และเหตุการณ์ที่เลือก ระบบจะไม่ใช้ข้อมูลของพื้นที่อื่นแทน" : "No package exists for this area/event selection. Another area's data will not be substituted."}</p> : null}
        {packageError ? <p className={styles.error} role="alert">{th ? "ชุดข้อมูลใช้ไม่ได้" : "Evidence package unavailable"}: {packageError}</p> : null}
        {reference && !evidence && !packageError ? <p role="status">{th ? "กำลังโหลดและตรวจสอบชุดข้อมูล…" : "Loading and verifying evidence package…"}</p> : null}
        {evidence && aoi ? <>
          <section className={styles.panel} aria-labelledby="evidence-map-title"><div className={styles.sectionTitle}><h2 id="evidence-map-title">{th ? "แผนที่หลักฐาน" : "Evidence map"}</h2><span>{th ? aoi.name_th ?? aoi.name : aoi.name}</span></div>
            <EvidenceMap key={evidence.id} aoi={aoi} layers={evidence.layers} th={th} />
            <ul className={styles.layerList}>{evidence.layers.map((layer) => <li key={layer.id}><b>{layer.title}</b><span>{STATUS[layer.availability][th ? 1 : 0]}</span>{layer.reason ? <small>{layer.reason}</small> : null}</li>)}</ul>
            <EvidenceFeatureBrowser key={evidence.id} layers={evidence.layers} th={th} />
          </section>
          <section className={styles.panel} aria-labelledby="evidence-source-title"><h2 id="evidence-source-title">{th ? "ข้อมูลที่ได้และข้อจำกัด" : "Acquired data and coverage"}</h2>
            <p>{catalog.datasets.filter((item) => !SUPPORTING_SOURCES.has(item.id)).length} {th ? "กลุ่มข้อมูลที่ได้มา" : "acquired data groups"} · {catalog.datasets.filter((item) => SUPPORTING_SOURCES.has(item.id)).length} {th ? "แหล่งข้อมูลสนับสนุนหรือสถานการณ์สมมติ" : "supporting or scenario sources"}. {th ? "วันที่หมายถึงช่วงเวลาของแหล่งข้อมูล ไม่ใช่วันที่ดาวน์โหลด" : "Dates describe source coverage, not download time."}</p>
            <div className={styles.tableWrap}><table><thead><tr><th>{th ? "ข้อมูล" : "Dataset"}</th><th>{th ? "เริ่ม" : "Start"}</th><th>{th ? "สิ้นสุด" : "End"}</th><th>{th ? "สถานะ" : "Availability"}</th><th>{th ? "ขอบเขตและคุณภาพ" : "Coverage and quality"}</th></tr></thead><tbody>
              {evidence.datasets.map((row) => { const source = catalog.datasets.find((item) => item.id === row.dataset_id); return source ? <tr key={row.dataset_id}><th scope="row">{th ? source.title_th ?? source.title : source.title}<small>{source.temporal.label}</small>{SUPPORTING_SOURCES.has(source.id) ? <small>{th ? "ข้อมูลสนับสนุน / สถานการณ์สมมติ" : "Supporting / scenario input"}</small> : null}</th><td>{source.temporal.start ?? "—"}</td><td>{source.temporal.end ?? "—"}</td><td><span className={styles.status}>{STATUS[row.availability][th ? 1 : 0]}</span></td><td>{row.coverage}<p>{row.summary}</p>{row.qc.length ? <ul>{row.qc.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}<details><summary>{th ? "แหล่งข้อมูล สิทธิ์ และข้อจำกัด" : "Sources, rights and limitations"}</summary><p>{source.rights.license ?? (th ? "ยังไม่ระบุสิทธิ์แน่ชัด" : "Exact license unresolved")} · {source.rights.status}</p><p>{source.rights.public_derivatives ? (th ? "อนุญาตผลลัพธ์ที่ผ่านการคัดกรองในชุดนี้" : "Cleared derivatives may appear in this package.") : (th ? "แสดงข้อมูลกำกับเท่านั้น ไม่รวมข้อมูลต้นฉบับที่มีข้อจำกัด" : "Metadata only; restricted source assets are not included.")}</p><ul>{source.source_urls.map((url) => <li key={url}><a href={url} target="_blank" rel="noopener noreferrer">{new URL(url).hostname}</a></li>)}{[...source.limitations, ...source.rights.attribution].map((item, index) => <li key={index}>{item}</li>)}</ul></details></td></tr> : null; })}
            </tbody></table></div>
          </section>
          <section className={styles.panel} aria-labelledby="evidence-gauge-title"><h2 id="evidence-gauge-title">{th ? "ข้อมูลระดับน้ำย้อนหลัง" : "Historical gauge context"}</h2>{evidence.gauges.length ? evidence.gauges.map((gauge) => <EvidenceGaugeChart key={gauge.id} gauge={gauge} th={th} />) : <p className={styles.empty}>{th ? "ไม่มีชุดระดับน้ำที่เผยแพร่ได้สำหรับพื้นที่/เหตุการณ์นี้ ตรวจสอบสถานะและข้อจำกัดในตารางข้อมูล" : "No publishable gauge series is included for this area/event. See source availability and limitations above."}</p>}</section>
          <section className={styles.panel} aria-labelledby="evidence-score-title"><h2 id="evidence-score-title">{th ? "ความครบถ้วนขององค์ประกอบคะแนน" : "Score component completeness"}</h2><p>{th ? "FPPS หลัก: ยังไม่มี · ระดับการดำเนินการ: ยังไม่มี · ไม่มีการปรับน้ำหนักหรือแทนค่าที่ขาดด้วยศูนย์" : "Primary FPPS: unavailable. Action class: unavailable. Missing inputs are not zero and weights are not redistributed."}</p>
            <div className={styles.tableWrap}><table><thead><tr><th>{th ? "องค์ประกอบ" : "Component"}</th><th>{th ? "น้ำหนัก" : "Weight"}</th><th>{th ? "ค่า" : "Value"}</th><th>{th ? "ข้อจำกัด" : "Limitation"}</th></tr></thead><tbody>{evidence.assessment.components.map((item) => <tr key={item.id}><th scope="row">{item.label}</th><td>{Math.round(item.weight * 100)}%</td><td>{item.value ?? (th ? "ยังไม่มี" : "Unavailable")}</td><td>{item.reason ?? "—"}</td></tr>)}</tbody></table></div>
            {evidence.assessment.bounds ? <p className={styles.bound}>{th ? "ช่วงความไวทางคณิตศาสตร์ ไม่ใช่คะแนนที่รับรอง" : "Mathematical sensitivity range, not a qualified score"}: {evidence.assessment.bounds.lower.toFixed(2)}–{evidence.assessment.bounds.upper.toFixed(2)}</p> : null}
            <ul>{evidence.assessment.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </section>
          <section className={styles.panel} aria-labelledby="evidence-scenario-title"><h2 id="evidence-scenario-title">{th ? "สถานการณ์สมมติเพื่อทดสอบวิธี" : "Explicit scenario comparisons"}</h2><p>{th ? "ผลคำนวณล่วงหน้าตามสมมติฐาน ไม่ใช่ค่าที่สังเกตหรือเส้นทางปลอดภัยที่ยืนยัน" : "Precomputed results under stated assumptions, not observed outcomes or confirmed safe routes."}</p><div className={styles.scenarios}>{evidence.scenarios.map((scenario) => <article key={scenario.id}><p className={styles.eyebrow}>{scenario.kind}</p><h3>{scenario.title}</h3><p>{scenario.summary}</p><dl>{scenario.metrics.map((metric, index) => <div key={index}><dt>{metric.label}</dt><dd>{metric.value ?? (th ? "ยังไม่มี" : "Unavailable")} {metric.unit}</dd></div>)}</dl><details><summary>{th ? "สมมติฐาน" : "Assumptions"}</summary><ul>{scenario.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></details></article>)}</div>{!evidence.scenarios.length ? <p>{th ? "ไม่มีผลสถานการณ์สมมติในชุดนี้" : "No scenario results are included in this package."}</p> : null}</section>
          <footer className={styles.provenance}><div><strong>{th ? "ชุดข้อมูลที่ตรวจสอบย้อนกลับได้" : "Traceable evidence package"}</strong><p>{evidence.id} · {evidence.generated_at}</p><p>{th ? "ความเชื่อมั่น: ต่ำ · เวลาของแหล่งข้อมูล: " : "Confidence: low · Source timestamp: "}{evidence.source_timestamp ?? (th ? "หลายช่วงเวลา ดูข้อมูลกำกับแต่ละแหล่ง" : "mixed source periods; see dataset metadata")}</p><details><summary>{th ? "สมมติฐานของชุดข้อมูล" : "Package assumptions"}</summary><ul>{evidence.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></details><details><summary>{th ? "ค่าแฮชข้อมูลนำเข้า" : "Input checksums"}</summary><dl>{Object.entries(evidence.input_hashes).map(([name, hash]) => <div key={name}><dt>{name}</dt><dd><code>{hash}</code></dd></div>)}</dl></details></div><div className={styles.downloads}>{reportUrl ? <a className={styles.download} href={reportUrl} download>{th ? "ดาวน์โหลดรายงาน" : "Download report"}</a> : <span>{th ? "ไม่มีรายงานให้ดาวน์โหลด" : "Report download unavailable"}</span>}{evidence.downloads?.map((item) => { const url = evidenceAssetUrl(item.url); return url ? <div key={url}><a className={styles.download} href={url} download>{item.title}</a><small>SHA-256: <code>{item.sha256}</code></small></div> : null; })}</div></footer>
        </> : null}
      </> : null}
    </div>
  </main>;
}
