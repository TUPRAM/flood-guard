"use client";

/**
 * Region B1 of the Command exercise replay: the replay clock and the model figures of the district at the replay
 * hour. The replay time is the largest text of the page; under it stand the phase and the assumed river stage, then
 * the three model figures with their captions, the line that says what changed since the hour before, and from
 * 13 Sep the model-limit chip. Every figure here is a T1 scenario (model) with low confidence, rounded as such.
 * In focus mode the card is one line.
 */

import { useMemo } from "react";

import { formatHourStamp, phaseAt, type Language, type TimelineManifest } from "@/lib/flood-timeline";
import { changeSinceHourBefore, clampCommandHour, commandStage, districtFiguresAt, type CommandModel } from "@/lib/flood-timeline-command";
import {
  COMMAND_CLOCK,
  COMMAND_FIGURES,
  COMMAND_SITUATION,
  commandChangeLine,
  commandFigureCells,
  commandFocusFigures,
  commandHourOf,
  commandHourShort,
  commandMoment,
  commandMomentShort,
  commandPhaseLine,
  commandPhaseShortLine,
  commandText,
} from "@/lib/flood-timeline-command-copy";

import styles from "./mae-sai-command-exercise.module.css";

/** Phases in which the model dries faster than the ground did: the card says so. */
const MODEL_LIMIT_PHASES: readonly string[] = ["receding", "gone"];

export function MaeSaiCommandSituation({ language, hour, manifest, model, collapsed = false, failed = false, onRetry }: {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  /** The replay data; null while it loads. */
  manifest: TimelineManifest | null;
  model: CommandModel | null;
  /** Focus mode: one 44 px line. */
  collapsed?: boolean;
  /** The replay data could not be loaded. */
  failed?: boolean;
  onRetry?: () => void;
}) {
  const at = clampCommandHour(hour);
  const t = (entry: { en: string; th: string }) => commandText(entry, language);
  const figures = useMemo(() => (model ? districtFiguresAt(model, at) : null), [model, at]);
  const change = useMemo(() => (model ? changeSinceHourBefore(model, at) : null), [model, at]);
  const phase = manifest ? phaseAt(at / 24, manifest.phases) : null;
  const stage = model ? commandStage(model, at) : 0;

  if (collapsed) {
    return (
      <section className={`${styles.panel} ${styles.situationLine}`} data-region="B1" data-clear-panel aria-label={t(COMMAND_SITUATION.label)} lang={language}>
        <strong data-command-clock>{commandMomentShort(at, language)} · {commandHourShort(at, language)}</strong>
        {figures && <span title={t(COMMAND_FIGURES.modelTag)}>{commandFocusFigures(figures, language)}</span>}
      </section>
    );
  }

  const cells = figures ? commandFigureCells(figures, language) : [];
  const changeLine = change ? commandChangeLine(change, change.sinceHour === null ? "" : formatHourStamp(change.sinceHour, language), language) : null;
  const limit = phase !== null && MODEL_LIMIT_PHASES.includes(phase.id);
  return (
    <section className={`${styles.panel} ${styles.situation}`} data-region="B1" data-clear-panel aria-label={t(COMMAND_SITUATION.label)} lang={language}>
      <div className={styles.clockHead}>
        <span className={styles.eyebrow}>{t(COMMAND_CLOCK.label)}</span>
        <span className={styles.hourOf}>{commandHourOf(at, language)}</span>
        <span className={styles.replayTag} title={t(COMMAND_CLOCK.tagMeaning)}>{t(COMMAND_CLOCK.tag)}</span>
      </div>
      {/* The replay time stands alone on its line: the largest text of the page, in either language. */}
      <p className={styles.clock}>
        <span className={styles.clockTime} data-command-clock>
          <span className={styles.clockLong}>{commandMoment(at, language)}</span>
          <span className={styles.clockShort}>{commandMomentShort(at, language)}</span>
        </span>
      </p>
      {phase && model ? (
        <>
          <p className={styles.phaseLine} title={t(COMMAND_CLOCK.stageMeaning)} data-command-phase={phase.id}>
            <span className={styles.phaseLong}>{commandPhaseLine(phase.label, stage, language)}</span>
            <span className={styles.phaseShort}>{commandPhaseShortLine(phase.label, stage, language)}</span>
          </p>
          <div className={styles.figuresHead}><span className={styles.laneTag}>{t(COMMAND_FIGURES.modelTag)}</span></div>
          <ul className={styles.figures} aria-label={t(COMMAND_FIGURES.label)}>
            {cells.map((cell) => (
              <li key={cell.id} className={styles.figure} title={cell.meaning} data-figure={cell.id}>
                <strong>{cell.value}</strong>
                <span>{cell.caption}</span>
                {cell.sub && <small>{cell.sub}</small>}
              </li>
            ))}
            {/* The fourth figure, open exercise items, arrives with the exercise calls; its slot is kept. */}
            <li className={`${styles.figure} ${styles.figureSlot}`} data-figure="exerciseItems" title={t(COMMAND_FIGURES.noExerciseItems)}>
              <strong aria-hidden="true">–</strong>
              <span>{t(COMMAND_SITUATION.exerciseSlot)}</span>
              <small className={styles.srOnly}>{t(COMMAND_FIGURES.noExerciseItems)}</small>
            </li>
          </ul>
          <div className={styles.notes} data-limit={limit ? "on" : "off"} lang={language}>
            {changeLine && <p className={styles.change} title={changeLine.text} data-command-change>{changeLine.text}</p>}
            {limit && <p className={styles.limitChip} title={t(COMMAND_FIGURES.modelLimit)} data-command-limit>{t(COMMAND_SITUATION.modelLimitShort)}</p>}
          </div>
        </>
      ) : (
        <p className={styles.loadingLine} role="status">
          {failed ? t(COMMAND_SITUATION.error) : t(COMMAND_SITUATION.loading)}
          {failed && onRetry && <button type="button" onClick={onRetry}>{t(COMMAND_SITUATION.retry)}</button>}
        </p>
      )}
    </section>
  );
}
