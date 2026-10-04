"use client";

/**
 * Region B1 of the Command exercise replay: the replay clock and the model figures of the district at the replay
 * hour. The replay time is the largest text of the page; under it stand the phase and the assumed river stage, then
 * the three model figures with their captions, the line that says what changed since the hour before, and from
 * 13 Sep the model-limit chip. Every figure here is a T1 scenario (model) with low confidence, rounded as such.
 * Two things on the card are not model figures and say so: the count of open exercise items (invented, plain digits,
 * under the exercise tag), and the chip that says how many place records have a point and at how many of those the
 * model is dry. In focus mode the card is one line.
 */

import { useMemo } from "react";

import { formatHourStamp, phaseAt, type Language, type TimelineManifest } from "@/lib/flood-timeline";
import { changeSinceHourBefore, clampCommandHour, commandStage, districtFiguresAt, type CommandModel, type CommandShelterSet } from "@/lib/flood-timeline-command";
import type { PlaceRecordTally } from "@/lib/flood-timeline-command-feed";
import type { ExerciseCounts } from "@/lib/flood-timeline-command-incidents";
import { COMMAND_EXERCISE, commandOpenItemsText, commandRecordTallyChip, commandRecordTallyLine } from "@/lib/flood-timeline-command-reports-copy";
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
import { EXERCISE_MARKER_VIEWBOX, exerciseMarkerNodes, MarkerGlyph } from "./mae-sai-command-markers";

/** The small "!!" octagon beside the count of life-at-risk items: the same drawing as the marker. */
const LIFE_GLYPH = exerciseMarkerNodes({ shape: "octagon", size: 36, symbol: "!!", fill: "#D55E00", symbolColour: "#ffffff", halo: false, outline: "none", closed: false, showsCallsign: false, showsWaiting: false });

/** Phases in which the model dries faster than the ground did: the card says so. */
const MODEL_LIMIT_PHASES: readonly string[] = ["receding", "gone"];

export function MaeSaiCommandSituation({ language, hour, manifest, model, set = "reported", exercise = null, tally = null, onRecords, collapsed = false, failed = false, onRetry }: {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  /** The replay data; null while it loads. */
  manifest: TimelineManifest | null;
  model: CommandModel | null;
  /** The shelter set the access figure counts: the one the table's switch has chosen. */
  set?: CommandShelterSet;
  /** Counted exercise items at this replay hour; null while the exercise file has not loaded or its items are switched off. */
  exercise?: ExerciseCounts | null;
  /** How the model reads at the points of the place records known by now; null until the replay data has loaded. */
  tally?: PlaceRecordTally | null;
  /** The place-record chip was pressed: the page opens "Known by now". */
  onRecords?: () => void;
  /** Focus mode: one 44 px line. */
  collapsed?: boolean;
  /** The replay data could not be loaded. */
  failed?: boolean;
  onRetry?: () => void;
}) {
  const at = clampCommandHour(hour);
  const t = (entry: { en: string; th: string }) => commandText(entry, language);
  const figures = useMemo(() => (model ? districtFiguresAt(model, at, set) : null), [model, at, set]);
  const change = useMemo(() => (model ? changeSinceHourBefore(model, at, set) : null), [model, at, set]);
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
        <span className={styles.hourOf}>
          <span className={styles.hourLong}>{commandHourOf(at, language)}</span>
          <span className={styles.hourShort}>{commandHourShort(at, language)}</span>
        </span>
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
          <div className={styles.figuresHead}>
            <span className={styles.laneTag}>{t(COMMAND_FIGURES.modelTag)}</span>
            <span className={styles.figuresRule} aria-hidden="true" />
            {/* Reported against model: how many place records have a point by now, and at how many the model is dry. */}
            {tally && tally.located > 0 && (
              <button type="button" className={styles.recordChip} onClick={onRecords} title={commandRecordTallyLine(tally, language)} aria-label={commandRecordTallyLine(tally, language)} data-command-record-chip>
                {commandRecordTallyChip(tally, language)}
              </button>
            )}
          </div>
          <ul className={styles.figures} aria-label={t(COMMAND_FIGURES.label)}>
            {cells.map((cell) => (
              <li key={cell.id} className={styles.figure} title={cell.meaning} data-figure={cell.id}>
                <strong>{cell.value}</strong>
                <span>{cell.caption}</span>
                {cell.sub && <small>{cell.sub}</small>}
              </li>
            ))}
            {/* The fourth figure is a plain count of invented items, under the exercise tag: it is not a model figure. */}
            {exercise ? (
              <li className={`${styles.figure} ${styles.figureExercise}`} data-figure="exerciseItems" data-open={exercise.open} data-life={exercise.lifeAtRisk} title={commandOpenItemsText(exercise.open, exercise.lifeAtRisk, language)}>
                <strong aria-hidden="true">{exercise.open}<b className={styles.exTag}>{t(COMMAND_EXERCISE.short)}</b></strong>
                <span aria-hidden="true">{t(COMMAND_EXERCISE.openCaption)}</span>
                <small aria-hidden="true" data-life={exercise.lifeAtRisk > 0 ? "true" : "false"}>
                  {exercise.lifeAtRisk > 0 && <><MarkerGlyph nodes={LIFE_GLYPH} viewBox={EXERCISE_MARKER_VIEWBOX} size={15} />{exercise.lifeAtRisk} {t(COMMAND_EXERCISE.atRisk)}</>}
                </small>
                <span className={styles.srOnly}>{commandOpenItemsText(exercise.open, exercise.lifeAtRisk, language)}</span>
              </li>
            ) : (
              <li className={`${styles.figure} ${styles.figureSlot}`} data-figure="exerciseItems" title={t(COMMAND_EXERCISE.itemsOff)}>
                <strong aria-hidden="true">–</strong>
                <span>{t(COMMAND_SITUATION.exerciseSlot)}</span>
                <small className={styles.srOnly}>{t(COMMAND_EXERCISE.itemsOff)}</small>
              </li>
            )}
          </ul>
          <div className={styles.notes} data-limit={limit ? "on" : "off"} lang={language}>
            {/* A tablet has three figure columns: the open exercise items stand on this line there. */}
            {exercise && (
              <p className={styles.exerciseLine} title={commandOpenItemsText(exercise.open, exercise.lifeAtRisk, language)} data-command-exercise-line>
                <b className={styles.exTag}>{t(COMMAND_EXERCISE.short)}</b>
                <span>{exercise.open} {t(COMMAND_EXERCISE.openCaption)}</span>
                {exercise.lifeAtRisk > 0 && <span className={styles.exerciseLife}><MarkerGlyph nodes={LIFE_GLYPH} viewBox={EXERCISE_MARKER_VIEWBOX} size={15} />{exercise.lifeAtRisk}</span>}
              </p>
            )}
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
