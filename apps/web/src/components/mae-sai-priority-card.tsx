"use client";

/**
 * Scenario FPPS card for the Mae Sai replay: ranks the eight subdistricts at the current moment and for the chosen
 * shelter set, shows how each of the five components adds up to the score, and applies the locked A–E rules — so with
 * the replay's LOW confidence every class is E, and the class the score alone implies is shown separately.
 */

import type { ActionClass } from "@floodguard/contracts";

import { ACTION_PLAYBOOK, PLAYBOOK_STAGES, STAGE_LABELS, stageForPhase, type PlaybookStage } from "@/lib/action-playbook";
import type { Language, TambonProps } from "@/lib/flood-timeline";
import { DEFAULT_FPPS_WEIGHTS, FPPS_COMPONENTS, type FppsComponent } from "@/lib/fpps";
import { pointShares, REPLAY_FPPS_ANCHORS, type ReplayFppsRaw, type ReplayFppsRow } from "@/lib/replay-fpps";

import { formatPeople, ProvenanceNote } from "./mae-sai-evacuation-panels";
import styles from "./mae-sai-flood-timeline.module.css";

type Translate = (en: string, th: string) => string;
const translator = (language: Language): Translate => (en, th) => (language === "th" ? th : en);
const pct = (share: number) => `${Math.round(share * 100)}%`;

/** Component colours: distinct from the water blues and each other; flood keeps the page's blue. */
export const COMPONENT_COLOURS: Record<FppsComponent, string> = {
  flood_likelihood_0_100: "#1f5fa8",
  exposure_0_100: "#b3261e",
  access_gap_0_100: "#7b3fb0",
  road_criticality_0_100: "#a86a00",
  vulnerability_context_0_100: "#2e7d4f",
};

const COMPONENT_NAMES: Record<FppsComponent, [string, string]> = {
  flood_likelihood_0_100: ["Flood likelihood", "โอกาสน้ำท่วม"],
  exposure_0_100: ["Exposure", "การสัมผัสน้ำท่วม"],
  access_gap_0_100: ["Access gap", "ช่องว่างการเข้าถึง"],
  road_criticality_0_100: ["Road criticality", "ความสำคัญของถนน"],
  vulnerability_context_0_100: ["Vulnerability/context", "ความเปราะบาง/บริบท"],
};

export const componentName = (key: FppsComponent, language: Language) => COMPONENT_NAMES[key][language === "th" ? 1 : 0];
export const actionClassName = (actionClass: ActionClass, language: Language) => ACTION_PLAYBOOK[actionClass].name[language];

/** The measured figure behind one component, in words. */
export function componentBasis(key: FppsComponent, raw: ReplayFppsRaw, language: Language, shelterLabel: string): string {
  const t = translator(language);
  const a = REPLAY_FPPS_ANCHORS;
  const km = (value: number) => value.toFixed(1);
  switch (key) {
    case "flood_likelihood_0_100": {
      const share = raw.modelledKm2 > 0 ? raw.floodedKm2 / raw.modelledKm2 : 0;
      return t(
        `${km(raw.floodedKm2)} of ${km(raw.modelledKm2)} km² modelled area under water (${pct(share)}); ${pct(a.floodSaturationShare)} scores 100.`,
        `น้ำท่วม ${km(raw.floodedKm2)} จาก ${km(raw.modelledKm2)} ตร.กม. ที่จำลอง (${pct(share)}) ท่วม ${pct(a.floodSaturationShare)} ได้ 100`,
      );
    }
    case "exposure_0_100": {
      const share = raw.residents > 0 ? raw.peopleInWater / raw.residents : 0;
      return t(
        `${formatPeople(raw.peopleInWater)} of ${formatPeople(raw.residents)} residents in water (${pct(share)}). Half the score is the share (${pct(a.exposureShareSaturation)} = full), half the headcount (${formatPeople(a.exposurePeopleSaturation)} = full).`,
        `ผู้อยู่อาศัยในน้ำ ${formatPeople(raw.peopleInWater)} จาก ${formatPeople(raw.residents)} คน (${pct(share)}) ครึ่งหนึ่งของคะแนนมาจากสัดส่วน (${pct(a.exposureShareSaturation)} = เต็ม) อีกครึ่งจากจำนวนคน (${formatPeople(a.exposurePeopleSaturation)} คน = เต็ม)`,
      );
    }
    case "access_gap_0_100":
      return raw.evacuees > 0
        ? t(
          `${formatPeople(raw.evacueesWithoutAccess)} of ${formatPeople(raw.evacuees)} people whose homes are in water cannot walk to an open, dry shelter (${shelterLabel}) within 2 km.`,
          `${formatPeople(raw.evacueesWithoutAccess)} จาก ${formatPeople(raw.evacuees)} คนที่บ้านอยู่ในน้ำ เดินไปที่พักพิงที่แห้ง (${shelterLabel}) ภายใน 2 กม. ไม่ได้`,
        )
        : t("Nobody's home is in the reconstructed water now, so nobody needs to evacuate.", "ขณะนี้ไม่มีบ้านใดอยู่ในน้ำจำลอง จึงไม่มีผู้ต้องอพยพ");
    case "road_criticality_0_100": {
      const share = raw.roadWeightedKm > 0 ? raw.roadWeightedImpassableKm / raw.roadWeightedKm : 0;
      return t(
        `${pct(share)} of mapped road length impassable (≥ 0.3 m), trunk and primary roads counted ×3, secondary and tertiary ×2; ${pct(a.roadSaturationShare)} scores 100.`,
        `ถนน ${pct(share)} ของความยาวสัญจรไม่ได้ (≥ 0.3 ม.) ทางหลวงสายหลักและสายรองนับ ×3 ทางสายรองและสายย่อยนับ ×2 ตัดขาด ${pct(a.roadSaturationShare)} ได้ 100`,
      );
    }
    case "vulnerability_context_0_100": {
      const share = raw.nodeResidents > 0 ? raw.vulnerableResidents / raw.nodeResidents : 0;
      return t(
        `${pct(share)} of residents live on slopes of 8° or more, or 750 m or more from a drivable road (terrain/remoteness proxy, not age, disability or income); ${pct(a.vulnerableSaturationShare)} scores 100.`,
        `ผู้อยู่อาศัย ${pct(share)} อยู่บนความลาดชัน 8° ขึ้นไป หรือห่างถนนที่รถเข้าได้ 750 ม. ขึ้นไป (ตัวแทนด้านภูมิประเทศ/ความห่างไกล ไม่ใช่อายุ ความพิการ หรือรายได้) ${pct(a.vulnerableSaturationShare)} ได้ 100`,
      );
    }
  }
}

/**
 * One class's steps through the flood: the canonical headline, then before / during / after for responders and
 * residents. The stage matching the replay's current phase is open and marked "Now"; the following one is marked "Next".
 */
export function ClassPlaybook({ actionClass, stage, language, step }: {
  actionClass: ActionClass;
  stage: PlaybookStage;
  language: Language;
  /** Optional step label, e.g. "Step 2 · once verified". */
  step?: string;
}) {
  const t = translator(language);
  const book = ACTION_PLAYBOOK[actionClass];
  const nowIndex = PLAYBOOK_STAGES.indexOf(stage);
  return (
    <div className={styles.playbook} data-class={actionClass} data-testid={`playbook-${actionClass}`}>
      <p className={styles.playbookHead}>
        {step && <small>{step}</small>}
        <strong>{t("Class", "กลุ่ม")} {actionClass} — {book.name[language]}</strong>
        <span>{book.headline[language]}</span>
      </p>
      <ol className={styles.playbookStages}>
        {PLAYBOOK_STAGES.map((key, index) => {
          const actions = book.stages[key];
          const marker = index === nowIndex ? t("Now", "ตอนนี้") : index === nowIndex + 1 ? t("Next", "ถัดไป") : null;
          return (
            <li key={key} data-now={index === nowIndex ? "" : undefined}>
              <details open={index === nowIndex}>
                <summary>
                  <span>{index + 1}. {STAGE_LABELS[key][language]}</span>
                  {marker && <em>{marker}</em>}
                </summary>
                <div className={styles.playbookColumns}>
                  <div>
                    <h4>{t("Responders and local officials", "ผู้ปฏิบัติงานและเจ้าหน้าที่ท้องถิ่น")}</h4>
                    <ul>{actions.responders.map((line) => <li key={line.en}>{line[language]}</li>)}</ul>
                  </div>
                  <div>
                    <h4>{t("Residents", "ประชาชน")}</h4>
                    <ul>{actions.residents.map((line) => <li key={line.en}>{line[language]}</li>)}</ul>
                  </div>
                </div>
              </details>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** What a row asks for: verify first while the class is gated to E, then the class the score implies. */
export function RowActions({ row, stage, language }: { row: Pick<ReplayFppsRow, "action_class" | "action_reason_code" | "score_implied_class">; stage: PlaybookStage; language: Language }) {
  const t = translator(language);
  const gated = row.action_class === "E" && row.action_reason_code === "low_confidence" && row.score_implied_class !== "E";
  return (
    <div className={styles.rowActions} data-testid="row-actions">
      <h3>{t("What to do", "ควรทำอะไร")}</h3>
      {gated ? (
        <>
          <p className={styles.muted}>{t(
            `The score alone would put this subdistrict in class ${row.score_implied_class}, but the inputs are low confidence, so the class is E. Verify first; once the water is confirmed, move straight to class ${row.score_implied_class}.`,
            `คะแนนเพียงอย่างเดียวจะจัดตำบลนี้อยู่ในกลุ่ม ${row.score_implied_class} แต่ข้อมูลมีความเชื่อมั่นต่ำ จึงอยู่ในกลุ่ม E ให้ตรวจสอบก่อน เมื่อยืนยันน้ำแล้วให้ดำเนินการตามกลุ่ม ${row.score_implied_class} ทันที`,
          )}</p>
          <ClassPlaybook actionClass="E" stage={stage} language={language} step={t("Step 1 · now", "ขั้นที่ 1 · ตอนนี้")} />
          <ClassPlaybook actionClass={row.score_implied_class} stage={stage} language={language} step={t("Step 2 · once verified", "ขั้นที่ 2 · เมื่อยืนยันแล้ว")} />
        </>
      ) : (
        <ClassPlaybook actionClass={row.action_class} stage={stage} language={language} />
      )}
    </div>
  );
}

/** A–E in one line each, with the rule that assigns it. */
export function ClassGuide({ language }: { language: Language }) {
  const t = translator(language);
  return (
    <details className={styles.classGuide}>
      <summary>{t("What the classes A–E mean", "กลุ่ม A–E หมายถึงอะไร")}</summary>
      <dl>
        {(["A", "B", "C", "D", "E"] as const).map((key) => (
          <div key={key} data-class={key}>
            <dt>{key} — {ACTION_PLAYBOOK[key].name[language]}</dt>
            <dd>{ACTION_PLAYBOOK[key].when[language]}</dd>
          </div>
        ))}
      </dl>
      <p className={styles.muted}>{t(
        "Rules are checked in order A, B, C, D; the first that fits wins. Low confidence or a score under 35 always gives E.",
        "ตรวจกฎตามลำดับ A B C D กฎแรกที่เข้าเกณฑ์จะถูกใช้ ความเชื่อมั่นต่ำหรือคะแนนต่ำกว่า 35 จะได้กลุ่ม E เสมอ",
      )}</p>
    </details>
  );
}

/** Stacked bar of weighted points: its full width is 100 FPPS points. */
function PointsBar({ row, language }: { row: ReplayFppsRow; language: Language }) {
  return (
    <span className={styles.fppsTrack} aria-hidden="true">
      {FPPS_COMPONENTS.map((key) => (
        <span key={key} title={`${componentName(key, language)}: ${row.points[key].toFixed(1)}`}
          style={{ width: `${row.points[key]}%`, background: COMPONENT_COLOURS[key] }} />
      ))}
    </span>
  );
}

export function PriorityCard({ rows, names, confidence, confidenceReason, timestamp, shelterLabel, moment, phaseId, language }: {
  rows: readonly ReplayFppsRow[];
  names: Record<string, TambonProps>;
  confidence: string;
  confidenceReason: string;
  timestamp: string;
  /** The shelter set the access gap uses, e.g. "shelters reported in 2024" or "ranked plan, k = 8". */
  shelterLabel: string;
  moment: string;
  /** Replay phase id at this moment (dry, onset, peak, receding, gone): picks the playbook stage. */
  phaseId: string | null;
  language: Language;
}) {
  const t = translator(language);
  const stage = stageForPhase(phaseId);
  const lowConfidence = confidence.toLowerCase() !== "high" && confidence.toLowerCase() !== "medium";
  const weights = FPPS_COMPONENTS.map((key) => `${DEFAULT_FPPS_WEIGHTS[key].toFixed(2)} ${componentName(key, language).toLowerCase()}`).join(" + ");
  return (
    <section className={styles.card} aria-labelledby="mae-sai-priority-title" data-testid="priority-card">
      <p className={styles.eyebrow}>{t("SCENARIO FPPS · THIS MOMENT · NOT AN OFFICIAL PRIORITY LIST", "FPPS ตามสถานการณ์จำลอง · ช่วงเวลานี้ · ไม่ใช่ลำดับความสำคัญทางการ")}</p>
      <h2 id="mae-sai-priority-title">{t("Which subdistrict to act on first", "ควรดำเนินการที่ตำบลใดก่อน")}</h2>
      <p>{t(
        `Flood Preparedness Priority Score (0–100) for each subdistrict at ${moment}, with the access gap measured against ${shelterLabel}. Move the timeline or change the shelter set above and the ranking updates.`,
        `คะแนนลำดับความสำคัญด้านการเตรียมพร้อมรับน้ำท่วม (FPPS 0–100) รายตำบล ณ ${moment} โดยวัดช่องว่างการเข้าถึงเทียบกับ${shelterLabel} เลื่อนช่วงเวลาหรือเปลี่ยนชุดที่พักพิงด้านบนแล้วลำดับจะเปลี่ยนตาม`,
      )}</p>
      <p className={styles.muted}>FPPS = {weights}</p>

      <ul className={styles.fppsLegend} aria-label={t("Score components", "องค์ประกอบคะแนน")}>
        {FPPS_COMPONENTS.map((key) => (
          <li key={key}><i style={{ background: COMPONENT_COLOURS[key] }} />{componentName(key, language)} ({Math.round(DEFAULT_FPPS_WEIGHTS[key] * 100)}%)</li>
        ))}
      </ul>

      {lowConfidence && (
        <p className={styles.fppsGate} data-testid="priority-gate">{t(
          "Action class is E (Monitor and Verify) for every subdistrict: the project rule forces E whenever confidence is low, and this replay's water is a terrain-model reconstruction with assumed stages. “Score implies” is the class the same score would get once the inputs are verified — use it to plan checks, not to dispatch.",
          "กลุ่มการดำเนินการเป็น E (เฝ้าระวังและตรวจสอบ) ทุกตำบล: กฎของโครงการกำหนดให้เป็น E เสมอเมื่อความเชื่อมั่นต่ำ และน้ำในการย้อนดูนี้จำลองจากภูมิประเทศด้วยระดับน้ำสมมุติ “คะแนนบ่งชี้” คือกลุ่มที่คะแนนเดียวกันจะได้เมื่อข้อมูลผ่านการตรวจสอบแล้ว ใช้วางแผนการตรวจสอบ ไม่ใช่สั่งการ",
        )}</p>
      )}

      <ClassGuide language={language} />
      <p className={styles.muted}>{t(
        `Open a subdistrict for its score breakdown and what to do. Steps follow the flood: ${STAGE_LABELS.before.en.toLowerCase()}, ${STAGE_LABELS.during.en.toLowerCase()}, ${STAGE_LABELS.after.en.toLowerCase()}; this moment is “${STAGE_LABELS[stage].en.toLowerCase()}”.`,
        `เปิดตำบลเพื่อดูรายละเอียดคะแนนและสิ่งที่ควรทำ ขั้นตอนเป็นไปตามช่วงน้ำท่วม: ${STAGE_LABELS.before.th} ${STAGE_LABELS.during.th} ${STAGE_LABELS.after.th} ช่วงเวลานี้คือ “${STAGE_LABELS[stage].th}”`,
      )}</p>

      <ol className={styles.fppsList}>
        {rows.map((row) => {
          const name = names[row.id]?.[language] ?? row.id;
          const shares = pointShares(row.points);
          const implied = row.score_implied_class !== row.action_class;
          return (
            <li key={row.id} data-testid="priority-row">
              <details>
                <summary>
                  <span className={styles.fppsRank}>{row.rank}</span>
                  <span className={styles.fppsName}>{name}</span>
                  <PointsBar row={row} language={language} />
                  <span className={styles.fppsScore}>{row.fpps_0_100.toFixed(1)}</span>
                  <span className={styles.fppsClass} data-class={row.action_class}>
                    {t("Class", "กลุ่ม")} {row.action_class}
                    {implied && <small>{t("score implies", "คะแนนบ่งชี้")} {row.score_implied_class}</small>}
                  </span>
                </summary>
                {language === "en" && <p className={styles.muted}>{row.top_reason}</p>}
                <table className={styles.fppsTable}>
                  <thead>
                    <tr>
                      <th scope="col">{t("Component", "องค์ประกอบ")}</th>
                      <th scope="col" title={t("Component value, 0–100", "ค่าองค์ประกอบ 0–100")}>{t("Value", "ค่า")}</th>
                      <th scope="col">{t("Weight", "น้ำหนัก")}</th>
                      <th scope="col" title={t("Value × weight", "ค่า × น้ำหนัก")}>{t("Pts", "คะแนน")}</th>
                      <th scope="col" title={t("Share of this score", "สัดส่วนของคะแนนนี้")}>{t("Share", "สัดส่วน")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {FPPS_COMPONENTS.map((key) => (
                      <tr key={key}>
                        <th scope="row"><i style={{ background: COMPONENT_COLOURS[key] }} />{componentName(key, language)}
                          <small>{componentBasis(key, row.raw, language, shelterLabel)}</small></th>
                        <td>{row.components[key].toFixed(0)}</td>
                        <td>{DEFAULT_FPPS_WEIGHTS[key].toFixed(2)}</td>
                        <td>{row.points[key].toFixed(1)}</td>
                        <td>{pct(shares[key])}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr><th scope="row">FPPS</th><td /><td /><td>{row.fpps_0_100.toFixed(1)}</td><td>100%</td></tr>
                  </tfoot>
                </table>
                <RowActions row={row} stage={stage} language={language} />
              </details>
            </li>
          );
        })}
      </ol>

      <ProvenanceNote kind="priority" confidence={confidence} reason={confidenceReason} timestamp={timestamp} language={language}>
        {t(
          `Components use fixed scale anchors (${REPLAY_FPPS_ANCHORS.version}), so a score means the same at every moment. Weights and A–E rules are the project's locked FPPS policy. This ranking stays in the replay and does not change the Planning areas.`,
          `องค์ประกอบใช้ค่าอ้างอิงคงที่ (${REPLAY_FPPS_ANCHORS.version}) คะแนนจึงมีความหมายเท่ากันทุกช่วงเวลา น้ำหนักและกฎกลุ่ม A–E เป็นนโยบาย FPPS ที่โครงการกำหนดไว้ ลำดับนี้ใช้ในการย้อนดูเท่านั้น ไม่เปลี่ยนพื้นที่ในหน้า Planning`,
        )}
      </ProvenanceNote>
    </section>
  );
}
