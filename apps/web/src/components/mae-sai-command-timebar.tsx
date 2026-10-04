"use client";

/**
 * Region F of the Command exercise replay: the time dock. From the left: previous event, play or pause, next event,
 * minus and plus one hour and the three speeds; then the eleven day chips over the track. The track carries the
 * phase band with the phase names printed in it and, on a desktop, the hourly rain of the two gauges (observed).
 * Everything right of the playhead is hatched: it is not yet known at this replay hour.
 * In focus mode the dock is one line: play, the replay time and a plain slider.
 */

import { Pause, Play, RotateCcw, SkipBack, SkipForward } from "lucide-react";
import { memo } from "react";

import type { Language, Localized, Rainfall } from "@/lib/flood-timeline";
import { clampCommandHour, COMMAND_LAST_HOUR } from "@/lib/flood-timeline-command";
import {
  COMMAND_PHASE_SHORT,
  COMMAND_SPEED_COPY,
  COMMAND_TIMEBAR,
  commandDayLabel,
  commandMomentShort,
  commandSliderText,
  commandText,
} from "@/lib/flood-timeline-command-copy";
import {
  COMMAND_SPEEDS,
  commandDayIndex,
  commandHourShare,
  nextEventStop,
  previousEventStop,
  type CommandDayChip,
  type CommandEventStop,
  type CommandPhaseSpan,
  type CommandSpeedId,
} from "@/lib/flood-timeline-command-replay";

import styles from "./mae-sai-command-exercise.module.css";

/** A phase of the band with the label of the replay data. */
export interface CommandPhaseBandItem extends CommandPhaseSpan { label: Localized }

const pct = (share: number): string => `${(share * 100).toFixed(3)}%`;

/** Hourly rain of the gauges as bars over the 264 hours; drawn once, it does not follow the playhead. */
const RainRow = memo(function RainRow({ rainfall }: { rainfall: Pick<Rainfall, "stations" | "hourly_mm"> }) {
  const series = rainfall.stations.map((station) => rainfall.hourly_mm[station.code] ?? []);
  const top = Math.max(1, ...series.flatMap((values) => values.map((value) => value ?? 0)));
  return (
    <svg viewBox={`0 0 ${COMMAND_LAST_HOUR} 100`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
      {series.map((values, index) => values.map((value, hour) => (value && value > 0
        ? <rect key={`${index}-${hour}`} x={hour + (index === 0 ? 0.1 : 0.35)} y={100 - (value / top) * 100} width={index === 0 ? 0.8 : 0.3} height={(value / top) * 100} fill={index === 0 ? "#8496aa" : "#3d5169"} />
        : null)))}
    </svg>
  );
});

export function MaeSaiCommandTimebar({ language, hour, playing, speed, collapsed = false, disabled = false, days, phases, stops, rainfall, onTogglePlay, onStep, onSeek, onEvent, onSpeed }: {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  playing: boolean;
  speed: CommandSpeedId;
  /** Focus mode: one 44 px line. */
  collapsed?: boolean;
  /** True until the replay data has loaded. */
  disabled?: boolean;
  days: readonly CommandDayChip[];
  phases: readonly CommandPhaseBandItem[];
  stops: readonly CommandEventStop[];
  /** Observed hourly rain of the gauges; null hides the row. */
  rainfall: Pick<Rainfall, "stations" | "hourly_mm"> | null;
  onTogglePlay: () => void;
  onStep: (hours: number) => void;
  onSeek: (hour: number) => void;
  onEvent: (direction: -1 | 1) => void;
  onSpeed: (speed: CommandSpeedId) => void;
}) {
  const at = clampCommandHour(hour);
  const t = (entry: Localized) => commandText(entry, language);
  const share = commandHourShare(at);
  const atEnd = at >= COMMAND_LAST_HOUR;
  const playLabel = playing ? t(COMMAND_TIMEBAR.pause) : atEnd ? t(COMMAND_TIMEBAR.playAgain) : t(COMMAND_TIMEBAR.play);
  const PlayIcon = playing ? Pause : atEnd ? RotateCcw : Play;
  const activeDay = commandDayIndex(at, days.length);
  const speedIndex = COMMAND_SPEEDS.findIndex((item) => item.id === speed);
  const nextSpeed = COMMAND_SPEEDS[(speedIndex + 1) % COMMAND_SPEEDS.length].id;

  return (
    <section className={`${styles.panel} ${styles.dock}`} data-region="F" data-clear-panel data-collapsed={collapsed ? "true" : "false"} aria-label={t(COMMAND_TIMEBAR.label)} lang={language}>
      {/* Focus mode shows this play button and the replay time; the full controls below are hidden then. */}
      <button type="button" className={styles.focusPlay} onClick={onTogglePlay} disabled={disabled} aria-label={playLabel} title={playLabel} data-command-play="focus">
        <span><PlayIcon size={18} aria-hidden="true" /></span>
      </button>
      <span className={styles.focusTime}>{commandMomentShort(at, language)}</span>

      <div className={styles.transport}>
        <button type="button" className={`${styles.ctl} ${styles.ctlEvent}`} onClick={() => onEvent(-1)} disabled={disabled || previousEventStop(stops, at) === null} aria-label={t(COMMAND_TIMEBAR.previousEvent)} title={`${t(COMMAND_TIMEBAR.previousEvent)} ( [ )`}>
          <SkipBack size={18} aria-hidden="true" />
        </button>
        <button type="button" className={`${styles.ctl} ${styles.ctlPlay}`} onClick={onTogglePlay} disabled={disabled} aria-label={playLabel} title={playLabel} data-command-play="dock">
          <PlayIcon size={18} aria-hidden="true" />
        </button>
        <button type="button" className={`${styles.ctl} ${styles.ctlEvent}`} onClick={() => onEvent(1)} disabled={disabled || nextEventStop(stops, at) === null} aria-label={t(COMMAND_TIMEBAR.nextEvent)} title={`${t(COMMAND_TIMEBAR.nextEvent)} ( ] )`}>
          <SkipForward size={18} aria-hidden="true" />
        </button>
        <span className={styles.ctlGap} aria-hidden="true" />
        <button type="button" className={styles.ctl} onClick={() => onStep(-1)} disabled={disabled || at <= 0} aria-label={t(COMMAND_TIMEBAR.back)} title={t(COMMAND_TIMEBAR.back)}>
          {t(COMMAND_TIMEBAR.backShort)}
        </button>
        <button type="button" className={styles.ctl} onClick={() => onStep(1)} disabled={disabled || atEnd} aria-label={t(COMMAND_TIMEBAR.forward)} title={t(COMMAND_TIMEBAR.forward)}>
          {t(COMMAND_TIMEBAR.forwardShort)}
        </button>
        <span className={styles.ctlGap} aria-hidden="true" />
        <div className={styles.speeds} role="group" aria-label={t(COMMAND_TIMEBAR.speed)}>
          {COMMAND_SPEEDS.map(({ id }) => (
            <button key={id} type="button" aria-pressed={id === speed} onClick={() => onSpeed(id)} title={t(COMMAND_SPEED_COPY[id].meaning)} aria-label={t(COMMAND_SPEED_COPY[id].meaning)} data-command-speed={id}>
              {t(COMMAND_SPEED_COPY[id].short)}
            </button>
          ))}
        </div>
        {/* On a tablet the three speeds are one button that steps through them. */}
        <button type="button" className={`${styles.ctl} ${styles.speedCycle}`} onClick={() => onSpeed(nextSpeed)} aria-label={`${t(COMMAND_TIMEBAR.speed)}: ${t(COMMAND_SPEED_COPY[speed].meaning)}`} title={t(COMMAND_SPEED_COPY[speed].meaning)}>
          {t(COMMAND_SPEED_COPY[speed].short)}
        </button>
        <p className={styles.speedNote}>{t(COMMAND_SPEED_COPY[speed].meaning)}</p>
      </div>

      <div className={styles.timeline}>
        <div className={styles.days} role="group" aria-label={t(COMMAND_TIMEBAR.days)}>
          {days.map((day, index) => (
            <button key={day.date} type="button" className={styles.day} style={{ left: pct(commandHourShare(day.hour)) }} onClick={() => onSeek(day.hour)} disabled={disabled}
              aria-label={commandDayLabel(day.date, language)} aria-current={index === activeDay ? "true" : undefined} data-command-day={day.day}>
              <span>{day.day}</span>
            </button>
          ))}
        </div>
        <div className={styles.track}>
          <div className={styles.phaseBand} role="img" aria-label={`${t(COMMAND_TIMEBAR.phases)}: ${phases.map((phase) => commandText(phase.label, language)).join(", ")}`}>
            {phases.map((phase) => (
              <span key={phase.id} className={styles.phase} data-phase={phase.id} style={{ width: pct((phase.to - phase.from) / COMMAND_LAST_HOUR) }} lang={language}>
                <span className={styles.phaseName}>{commandText(phase.label, language)}</span>
                <span className={styles.phaseShortName}>{commandText(COMMAND_PHASE_SHORT[phase.id] ?? phase.label, language)}</span>
              </span>
            ))}
          </div>
          {rainfall && (
            <div className={styles.rain} role="img" aria-label={t(COMMAND_TIMEBAR.rain)}>
              <RainRow rainfall={rainfall} />
              <span className={styles.rainLabel} aria-hidden="true">{t(COMMAND_TIMEBAR.rainShort)}</span>
            </div>
          )}
          <div className={styles.line} aria-hidden="true"><i style={{ width: pct(share) }} /></div>
          {!atEnd && <div className={styles.future} style={{ left: pct(share) }} data-command-future><span>{t(COMMAND_TIMEBAR.notYetKnown)}</span></div>}
          <div className={styles.playhead} style={{ left: pct(share) }} aria-hidden="true" />
          <input type="range" className={styles.range} min={0} max={COMMAND_LAST_HOUR} step={1} value={at} disabled={disabled}
            onChange={(event) => onSeek(Number(event.currentTarget.value))}
            aria-label={t(COMMAND_TIMEBAR.slider)} aria-valuetext={commandSliderText(at, language)} data-command-slider />
        </div>
      </div>
    </section>
  );
}
