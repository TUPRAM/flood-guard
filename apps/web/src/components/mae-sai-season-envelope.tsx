"use client";

import { formatFileSize, type Language, type SeasonEnvelopeBlock, type SeasonEnvelopeCheck, type TambonProps } from "@/lib/flood-timeline";
import { localizedText } from "@/lib/flood-timeline-copy";
import {
  ENVELOPE_COPY,
  ENVELOPE_RGBA,
  envelopeDifferenceList,
  envelopeIou,
  envelopeShare,
  type SeasonEnvelopeDocument,
} from "@/lib/flood-timeline-envelope";

import styles from "./mae-sai-flood-timeline.module.css";

/**
 * What the page holds of the 2024 season envelope (UNOSAT and GISTDA product 4009, lane SCN-ENV): nothing when the
 * manifest carries no shippable envelope, the manifest block while its files load, and the statistics file with the
 * raster's cells once they have. A failed load leaves the block only: the layer and the comparison are then not shown.
 */
export type SeasonEnvelopeState =
  | { status: "absent" }
  | { status: "loading" | "error"; block: SeasonEnvelopeBlock }
  | { status: "ready"; block: SeasonEnvelopeBlock; document: SeasonEnvelopeDocument; cells: Uint32Array };

const rgba = ([r, g, b, a]: readonly number[]) => `rgb(${r} ${g} ${b} / ${Math.round((a / 255) * 100)}%)`;
/** The layer's hatch as a CSS background, for the legend key and the toggle: the same colours and direction as the map. */
export const ENVELOPE_SWATCH_BACKGROUND = `repeating-linear-gradient(45deg, ${rgba(ENVELOPE_RGBA.dark)} 0 2px, ${rgba(ENVELOPE_RGBA.light)} 2px 3.5px, ${rgba(ENVELOPE_RGBA.wash)} 3.5px 7px), #fff`;

/** Hatched key of the season envelope (legend and layer toggle). */
export function SeasonEnvelopeSwatch() {
  return <i className={styles.envelopeSwatch} aria-hidden="true" style={{ background: ENVELOPE_SWATCH_BACKGROUND }} />;
}

function Sentence({ text, language }: { text: string; language: Language }) {
  const value = localizedText(text, language);
  return <span lang={value.lang}>{value.text}</span>;
}

/** The scenario chip on the map while the layer is visible: "Scenario (SCN-ENV): 2024 season envelope". */
export function SeasonEnvelopeChip({ envelope, language }: { envelope: Pick<SeasonEnvelopeBlock, "label">; language: Language }) {
  const label = localizedText(envelope.label, language);
  return <p className={styles.envelopeChip} data-testid="envelope-chip" lang={label.lang}><SeasonEnvelopeSwatch />{label.text}</p>;
}

/**
 * The caption under the map while the layer is visible: what the layer is, that it includes August and early-October
 * water, that it is not an observation for any replay day, who made it and what FloodGuard changed, then the licence
 * and the credit.
 */
export function SeasonEnvelopeCaption({ envelope, language }: { envelope: SeasonEnvelopeBlock; language: Language }) {
  const th = language === "th";
  const label = localizedText(envelope.label, language);
  return (
    <p className={styles.envelopeCaption} data-testid="envelope-caption">
      <strong lang={label.lang}>{label.text}{label.lang === "th" ? "" : "."}</strong>{" "}
      <Sentence text={envelope.caption} language={language} />{" "}
      <span data-testid="envelope-caption-credit">
        {th ? "สัญญาอนุญาต" : "Licence"}: <a href={envelope.licence_url} target="_blank" rel="noopener noreferrer license" className={styles.inlineLink} lang="en">{envelope.licence}</a>{" · "}
        {th ? "เครดิต" : "Credit"}: <span lang="en">{envelope.credit}</span>{th ? "" : "."}
      </span>
    </p>
  );
}

/** Legend entry of the season envelope: hatched, a scenario, and not an observation for any replay day. */
export function SeasonEnvelopeLegend({ language }: { language: Language }) {
  return (
    <div data-testid="envelope-legend">
      <strong>{ENVELOPE_COPY.legendTitle[language]}</strong>
      <ul>
        <li><SeasonEnvelopeSwatch />{ENVELOPE_COPY.legend[language]}</li>
      </ul>
    </div>
  );
}

/**
 * Third group of the Checks: "Season envelope comparison (scenario; plausibility, not validation)". The figures come
 * from the envelope's own statistics file, never from the manifest. The group says where the modelled water and the
 * envelope differ most, by subdistrict, and never which of the two is right: the envelope also holds August and
 * early-October water and the modelled peak is illustrative. Without the statistics file it gives the use sentence
 * and says that the figures are not shown.
 */
export function SeasonEnvelopeComparison({ check, envelope, names, language }: {
  check: SeasonEnvelopeCheck;
  envelope: SeasonEnvelopeState;
  names: Record<string, TambonProps>;
  language: Language;
}) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const km2 = t("km²", "ตร.กม.");
  const name = (id: string) => names[id]?.[language] ?? id;
  const title = localizedText(check.title, language);
  const people = (value: number) => Math.round(value).toLocaleString("en-US");
  const document = envelope.status === "ready" ? envelope.document : null;
  const comparison = document?.comparison ?? null;
  const rows = comparison ? [...comparison.by_tambon].sort((a, b) => (b.agreement_iou ?? -1) - (a.agreement_iou ?? -1)) : [];
  return (
    <div data-testid="envelope-comparison">
      <p><strong lang={title.lang}>{title.text}</strong></p>
      <p><Sentence text={check.use} language={language} /></p>
      {!comparison || !document ? (
        <p className={styles.muted} role="status" data-testid="envelope-comparison-status">{envelope.status === "loading"
          ? ENVELOPE_COPY.loading[language]
          : t("The figures of this comparison are not shown: its statistics file could not be loaded.", "ไม่แสดงตัวเลขของการเทียบนี้ เนื่องจากโหลดไฟล์สถิติไม่สำเร็จ")}</p>
      ) : (
        <>
          <ul className={styles.list} data-testid="envelope-district">
            {comparison.district.map((row) => {
              const extent = localizedText(row.model_extent, language);
              return (
                <li key={row.id} data-row={row.id}>
                  <span lang={extent.lang}>{extent.text}</span>{t(` (${row.model_stage_m} m stage): `, ` (ระดับน้ำ ${row.model_stage_m} ม.): `)}
                  {t(
                    `agreement (IoU) ${envelopeIou(row.agreement_iou)}; ${envelopeShare(row.containment_model_in_envelope)} of the modelled water lies inside the envelope; the modelled water reaches ${envelopeShare(row.containment_envelope_in_model)} of the envelope. Modelled water ${row.model_km2.toFixed(1)} ${km2}, envelope ${row.envelope_km2.toFixed(1)} ${km2}, both ${row.overlap_km2.toFixed(1)} ${km2}.`,
                    `ความสอดคล้อง (IoU) ${envelopeIou(row.agreement_iou)} น้ำจากแบบจำลอง ${envelopeShare(row.containment_model_in_envelope)} อยู่ภายในขอบเขตน้ำตลอดฤดู และน้ำจากแบบจำลองครอบคลุม ${envelopeShare(row.containment_envelope_in_model)} ของขอบเขตนี้ น้ำจากแบบจำลอง ${row.model_km2.toFixed(1)} ${km2} ขอบเขตน้ำตลอดฤดู ${row.envelope_km2.toFixed(1)} ${km2} ซ้อนทับกัน ${row.overlap_km2.toFixed(1)} ${km2}`,
                  )}
                </li>
              );
            })}
          </ul>
          <p data-testid="envelope-by-tambon">
            {t("Agreement (IoU) by subdistrict at the modelled peak: ", "ความสอดคล้อง (IoU) รายตำบล ณ ระดับสูงสุดของแบบจำลอง: ")}
            {rows.map((row) => `${name(row.tambon_id)} ${envelopeIou(row.agreement_iou)}`).join(" · ")}{th ? "" : "."}
          </p>
          <p data-testid="envelope-disagreement">
            {t(
              `Where the two differ most: envelope water the modelled peak does not reach is largest in ${envelopeDifferenceList(comparison.disagreement.envelope_water_the_model_lacks, comparison.by_tambon, "envelope_only_km2", name, "en")}; modelled water outside the envelope is largest in ${envelopeDifferenceList(comparison.disagreement.modelled_water_outside_the_envelope, comparison.by_tambon, "model_only_km2", name, "en")}. These are the places to check evacuation and shelter figures first; the comparison does not say which of the two is right.`,
              `จุดที่ทั้งสองต่างกันมากที่สุด: น้ำในขอบเขตน้ำตลอดฤดูที่ระดับสูงสุดของแบบจำลองไปไม่ถึง มีมากที่สุดใน${envelopeDifferenceList(comparison.disagreement.envelope_water_the_model_lacks, comparison.by_tambon, "envelope_only_km2", name, "th")} ส่วนน้ำจากแบบจำลองที่อยู่นอกขอบเขตนี้ มีมากที่สุดใน${envelopeDifferenceList(comparison.disagreement.modelled_water_outside_the_envelope, comparison.by_tambon, "model_only_km2", name, "th")} พื้นที่เหล่านี้ควรตรวจสอบตัวเลขการอพยพและที่พักพิงก่อน การเทียบนี้ไม่ได้บอกว่าข้อมูลใดถูกต้อง`,
            )}
          </p>
          <ul className={styles.list} data-testid="envelope-details">
            <li data-testid="envelope-low-confidence">{t(
              `Low-confidence modelled water: ${envelopeShare(comparison.low_confidence.share_inside_envelope_low_confidence)} of it lies inside the envelope, against ${envelopeShare(comparison.low_confidence.share_inside_envelope_other)} of the other modelled water.`,
              `น้ำจากแบบจำลองที่มีความเชื่อมั่นต่ำ: ${envelopeShare(comparison.low_confidence.share_inside_envelope_low_confidence)} อยู่ภายในขอบเขตน้ำตลอดฤดู เทียบกับ ${envelopeShare(comparison.low_confidence.share_inside_envelope_other)} ของน้ำจากแบบจำลองส่วนอื่น`,
            )}</li>
            <li data-testid="envelope-residents">{t(
              `Residents inside the envelope, district total: about ${people(comparison.residents.residents_in_envelope)} (WorldPop 2020 modelled estimates, counted like the replay's residents in water); the modelled peak has ${people(comparison.residents.model_residents_in_water)} residents in water.`,
              `ผู้อยู่อาศัยภายในขอบเขตน้ำตลอดฤดู รวมทั้งอำเภอ: ประมาณ ${people(comparison.residents.residents_in_envelope)} คน (ค่าประมาณจากแบบจำลอง WorldPop 2020 นับด้วยเกณฑ์เดียวกับผู้อยู่อาศัยในน้ำของการย้อนดู) ส่วนระดับสูงสุดของแบบจำลองมีผู้อยู่อาศัยในน้ำ ${people(comparison.residents.model_residents_in_water)} คน`,
            )}</li>
            {!comparison.land_cover.computed && <li data-testid="envelope-land-cover"><Sentence text={comparison.land_cover.reason} language={language} /></li>}
            {document.assumptions.filter((item) => /surface model/.test(item)).map((item) => (
              <li key={item} data-testid="envelope-dsm"><Sentence text={item} language={language} /></li>
            ))}
            <li data-testid="envelope-tuning"><Sentence text={comparison.tuning.statement} language={language} />{" "}<Sentence text={comparison.tuning.rule} language={language} /></li>
          </ul>
          <p className={styles.muted} data-testid="envelope-comparison-footer">
            {t("Confidence", "ความเชื่อมั่น")}: {document.confidence.toLowerCase() === "low" ? t("low", "ต่ำ") : document.confidence} — <Sentence text={document.confidence_reason} language={language} />{" "}
            {t("Source timestamp", "เวลาของข้อมูลต้นทาง")}: <span lang="en">{document.source_timestamp}</span> · {t("licence", "สัญญาอนุญาต")}: <span lang="en">{document.licence.name}</span> · {t("credit", "เครดิต")}: <span lang="en">{document.credit}</span>
          </p>
        </>
      )}
      {check.urls.map((url) => (
        <span key={url}><a href={url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{url}</a>{" "}</span>
      ))}
    </div>
  );
}

/**
 * The envelope's entry in "Sources, assumptions and limits": what it is, the standard sentence, the licence, the credit
 * and the change notice, its three files (with the licence file) and its limits. Renders nothing without an envelope.
 */
export function SeasonEnvelopeSources({ envelope, language }: { envelope: SeasonEnvelopeState; language: Language }) {
  if (envelope.status === "absent") return null;
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const { block } = envelope;
  const document = envelope.status === "ready" ? envelope.document : null;
  const files: [string, string, { href: string; bytes: number }][] = [
    [t("Season-envelope raster (PNG)", "ภาพราสเตอร์ขอบเขตน้ำตลอดฤดู (PNG)"), "envelope.png", block.files.raster],
    [t("Areas and comparison (JSON)", "พื้นที่และการเทียบ (JSON)"), "envelope.json", block.files.statistics],
    [t("Licence, credit and change notice (text)", "สัญญาอนุญาต เครดิต และประกาศการเปลี่ยนแปลง (ข้อความ)"), "LICENSE", block.files.licence],
  ];
  return (
    <>
      <h3 id="mae-sai-season-envelope">{t("Season envelope (scenario layer)", "ขอบเขตน้ำตลอดฤดู (ชั้นข้อมูลสถานการณ์จำลอง)")}</h3>
      <ul className={styles.list} data-testid="envelope-sources">
        <li><strong><Sentence text={block.label} language={language} /></strong>{th ? " " : ". "}<Sentence text={block.caption} language={language} /></li>
        {block.standard_sentence && <li><Sentence text={block.standard_sentence} language={language} /></li>}
        <li data-testid="envelope-licence">
          {t("Licence", "สัญญาอนุญาต")}: <a href={block.licence_url} target="_blank" rel="noopener noreferrer license" className={styles.inlineLink} lang="en">{block.licence}</a>{" · "}
          {t("Credit", "เครดิต")}: <span lang="en">{block.credit}</span>{th ? " " : ". "}
          {t(
            "The files derived from the product keep a folder of their own and this licence: you may reuse them with the credit, the licence and a note of what you changed.",
            "ไฟล์ที่ดัดแปลงจากผลิตภัณฑ์นี้เก็บไว้ในโฟลเดอร์ของตนเองภายใต้สัญญาอนุญาตนี้ ท่านนำไปใช้ต่อได้โดยให้เครดิต ระบุสัญญาอนุญาต และระบุสิ่งที่ท่านเปลี่ยนแปลง",
          )}
        </li>
        {document && <li data-testid="envelope-change-notice">{t("Change notice", "ประกาศการเปลี่ยนแปลง")}: <span lang="en">{document.change_notice}</span></li>}
        <li data-testid="envelope-files">
          {t("Files", "ไฟล์")}:{" "}
          {files.map(([title, fileName, file]) => (
            <span key={fileName}><a href={file.href} download={fileName} className={styles.inlineLink}>{title}</a><span className={styles.muted}>({formatFileSize(file.bytes)})</span>{" "}</span>
          ))}
        </li>
        {block.rights_note && <li><Sentence text={block.rights_note} language={language} /></li>}
        {(document?.limitations ?? []).map((item) => <li key={item}><Sentence text={item} language={language} /></li>)}
        {envelope.status === "error" && <li role="status">{ENVELOPE_COPY.failed[language]}</li>}
      </ul>
    </>
  );
}
