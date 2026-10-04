"use client";

/**
 * Region B1 of the Command exercise replay: the replay clock and the model figures of the district at the replay
 * hour. The replay time is the largest text of the page; under it stand the phase and the assumed river stage, then
 * the three model figures with their captions, the line that says what changed since the hour before, and the model
 * limit of the phase. Every figure here is a T1 scenario (model) with low confidence, rounded as such.
 * Two things on the card are not model figures and say so: the count of open exercise items (invented, plain digits,
 * under the exercise tag), and the chip that says how many place records have a point and at how many of those the
 * model is dry. In focus mode the card is two short lines, and the model tag stays in sight.
 */

import { FileText } from "lucide-react";
import { useMemo } from "react";

import { phaseAt, type Language, type TimelineManifest } from "@/lib/flood-timeline";
import { COMMAND_BRIEF } from "@/lib/flood-timeline-command-act-copy";
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
  commandHourClock,
  commandHourOf,
  commandHourShort,
  commandMoment,
  commandMomentShort,
  commandPhaseLine,
  commandPhaseShortLine,
  commandText,
} from "@/lib/flood-timeline-command-copy";

import act from "./mae-sai-command-act.module.css";
import styles from "./mae-sai-command-exercise.module.css";
import { EXERCISE_MARKER_VIEWBOX, exerciseMarkerNodes, MarkerGlyph } from "./mae-sai-command-markers";

/** The small "!!" octagon beside the count of life-at-risk items: the same drawing as the marker. */
const LIFE_GLYPH = exerciseMarkerNodes({ shape: "octagon", size: 36, symbol: "!!", fill: "#D55E00", symbolColour: "#ffffff", halo: false, outline: "none", closed: false, showsCallsign: false, showsWaiting: false });

/** Phases in which the model dries faster than the ground did: the card says so. */
const MODEL_LIMIT_PHASES: readonly string[] = ["receding", "gone"];

/**
 * A rounded model value as the page sets it: the tilde lighter and the unit small, so the eye lands on the number.
 * The text is unchanged ("~164 km"): only its weight differs.
 */
export function ModelValue({ text, unit = null }: { text: string; unit?: string | null }) {
  const tilde = text.startsWith("~");
  return (
    <>
      {tilde && <span className={styles.tilde}>~</span>}
      {tilde ? text.slice(1) : text}
      {unit && <> <span className={styles.unit}>{unit}</span></>}
    </>
  );
}

export function MaeSaiCommandSituation({ language, hour, manifest, model, set = "reported", exercise = null, tally = null, onRecords, onBrief, collapsed = false, failed = false, onRetry }: {
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
  /** One tap opens the situation brief of this replay hour; without it the card has no such button. */
  onBrief?: () => void;
  /** Focus mode: the replay time with the model tag, and the two figures under it. */
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
        <strong data-command-clock>{commandMomentShort(at, language)}<span className={styles.focusHour}> · {commandHourShort(at, language)}</span></strong>
        {/* The figures of this line are modelled: the tag says so in words, not only on hover. */}
        {figures && <span className={styles.laneTag} data-command-lane="model">{t(COMMAND_FIGURES.modelTag)}</span>}
        {figures && <span className={styles.focusFigures} data-command-focus-figures>{commandFocusFigures(figures, language)}</span>}
      </section>
    );
  }

  const cells = figures ? commandFigureCells(figures, language) : [];
  const changeLine = change ? commandChangeLine(change, change.sinceHour === null ? "" : commandHourClock(change.sinceHour, language), language) : null;
  const limit = phase !== null && MODEL_LIMIT_PHASES.includes(phase.id);
  // The second line of the notes. While the river falls it is the model limit: the model dries at once, so a road it
  // calls passable again is the very thing the limit is about, and the card does not name such roads then.
  const roadsLine = !limit && changeLine ? changeLine.roadsCut ?? changeLine.roadsOpen : null;
  return (
    <section className={`${styles.panel} ${styles.situation}`} data-region="B1" data-clear-panel aria-label={t(COMMAND_SITUATION.label)} lang={language}>
      <div className={styles.clockHead}>
        <span className={styles.eyebrow}>{t(COMMAND_CLOCK.label)}</span>
        <span className={styles.hourOf}>
          <span className={styles.hourLong}>{commandHourOf(at, language)}</span>
          <span className={styles.hourShort}>{commandHourShort(at, language)}</span>
        </span>
        <span className={styles.replayTag} title={t(COMMAND_CLOCK.tagMeaning)}>{t(COMMAND_CLOCK.tag)}</span>
        {onBrief && figures && (
          <button type="button" className={act.briefButton} onClick={onBrief} aria-haspopup="dialog" aria-label={t(COMMAND_BRIEF.open)} title={t(COMMAND_BRIEF.open)} data-command-situation-brief>
            <FileText size={16} aria-hidden="true" />
          </button>
        )}
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
            <span className={styles.laneTag} data-command-lane="model">{t(COMMAND_FIGURES.modelTag)}</span>
            <span className={styles.figuresRule} aria-hidden="true" />
            {/* Reported against model: how many place records have a point by now, and at how many the model is dry. */}
            {tally && tally.located > 0 && (
              <button type="button" className={styles.recordChip} onClick={onRecords} title={commandRecordTallyLine(tally, language)} aria-label={commandRecordTallyLine(tally, language)} data-command-record-chip>
                {commandRecordTallyChip(tally, language)}
              </button>
            )}
            {/* A narrow card has three figure columns: the open exercise items stand beside the model tag there. */}
            {exercise && (
              <p className={styles.exerciseLine} title={commandOpenItemsText(exercise.open, exercise.lifeAtRisk, language)} data-command-exercise-line>
                <b className={styles.exTag}>{t(COMMAND_EXERCISE.short)}</b>
                <span>{exercise.open} {t(COMMAND_EXERCISE.openCaption)}</span>
                {exercise.lifeAtRisk > 0 && <span className={styles.exerciseLife}><MarkerGlyph nodes={LIFE_GLYPH} viewBox={EXERCISE_MARKER_VIEWBOX} size={15} />{exercise.lifeAtRisk}</span>}
              </p>
            )}
          </div>
          <ul className={styles.figures} aria-label={t(COMMAND_FIGURES.label)}>
            {cells.map((cell) => (
              <li key={cell.id} className={styles.figure} title={cell.meaning} data-figure={cell.id}>
                <strong><ModelValue text={cell.value} unit={cell.unit} /></strong>
                <span className={styles.captionLong}>{cell.caption}</span>
                <span className={styles.captionShort}>{cell.captionShort}</span>
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
          <div className={styles.notes} data-limit={limit ? "on" : "off"} data-second={roadsLine ? "roads" : "limit"} lang={language}>
            {/* The first line is never cut: the hour compared with, and the three differences. */}
            {changeLine && <p className={styles.change} title={changeLine.text} data-command-change>{changeLine.summary}</p>}
            {roadsLine && <p className={styles.changeRoads} title={roadsLine} data-command-change-roads>{roadsLine}</p>}
            {/* The limit of the model that matters in this phase: before the river falls, the current; after, the water left behind. */}
            {limit
              ? <p className={styles.limitChip} title={t(COMMAND_FIGURES.modelLimit)} data-command-limit data-command-model-note="receding">{t(COMMAND_SITUATION.modelLimitShort)}</p>
              : <p className={styles.limitChip} title={t(COMMAND_FIGURES.modelCurrent)} data-command-model-note="current">{t(COMMAND_SITUATION.modelCurrentShort)}</p>}
          </div>
          <p className={styles.narrowNote} data-command-narrow>{t(COMMAND_SITUATION.narrow)}</p>
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
