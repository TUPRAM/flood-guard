"use client";

/**
 * The facilitator's sheets of the Command exercise replay: the exercise setup, and the exercise log.
 *
 * The setup holds what an exercise needs before it starts: the roster of callsigns with the kind of each team, the
 * staging point, the start hour, what the exercise shows of the future, whether the invented items are on, the
 * playback speed and the pause for a life-at-risk item. The roster takes callsigns only: at most 12 characters, and
 * an entry with seven or more digits is refused, so no name and no phone number is stored. The log lists what was
 * done, newest first, and exports as a CSV file whose every row is marked as simulated.
 *
 * Everything on these sheets is saved on this device only. "Reset exercise" clears every Command key of the device;
 * like every other action it asks nothing and can be undone for ten seconds.
 */

import { Download, HardDrive, MapPin, Play, Plus, RotateCcw, X } from "lucide-react";
import { useId, useState } from "react";

import type { Language, Localized } from "@/lib/flood-timeline";
import { clampCommandHour, COMMAND_LAST_HOUR } from "@/lib/flood-timeline-command";
import {
  COMMAND_CALLSIGN_PROBLEM,
  COMMAND_LOG,
  COMMAND_ROLE,
  COMMAND_SETUP,
  COMMAND_TEAM_TYPE,
  commandDeviceTime,
  commandLogActionText,
  commandLogReplayTime,
  commandLogShown,
  commandPointText,
  commandRemoveTeam,
} from "@/lib/flood-timeline-command-act-copy";
import { COMMAND_DRAWER, COMMAND_SPEED_COPY, commandHourOf, commandMoment, commandText } from "@/lib/flood-timeline-command-copy";
import { COMMAND_MODES, type CommandMode } from "@/lib/flood-timeline-command-feed";
import {
  addRosterTeam,
  callsignProblem,
  COMMAND_LOG_FILE_NAME,
  commandLogCsv,
  removeRosterTeam,
  setRosterTeamType,
  TEAM_TYPES,
  type CommandLogEntry,
  type CommandSetup,
  type RosterTeam,
  type StagingChoice,
  type TeamType,
} from "@/lib/flood-timeline-command-log";
import { COMMAND_MODE } from "@/lib/flood-timeline-command-reports-copy";
import { COMMAND_SPEEDS, type CommandSpeedId } from "@/lib/flood-timeline-command-replay";

import act from "./mae-sai-command-act.module.css";
import { ModalDialog } from "./mae-sai-command-chrome";
import exercise from "./mae-sai-command-exercise.module.css";
import { TeamIcon } from "./mae-sai-command-incident";

/** The chip every sheet of the exercise wears: what is here stays on this device. */
export function CommandDeviceChip({ language }: { language: Language }) {
  return <span className={act.chip} data-command-device-chip lang={language}><HardDrive size={13} aria-hidden="true" />{commandText(COMMAND_SETUP.deviceOnly, language)}</span>;
}

/** A site the staging point can be at: one of the two sites reported in use in 2024 that the pick-list offers. */
export interface CommandStagingSite { id: string; name: Localized }

export interface CommandSetupSheetProps {
  open: boolean;
  onClose: () => void;
  language: Language;
  setup: CommandSetup;
  /** Whole replay hour on screen, for "use the hour on screen". */
  hour: number;
  stagingSites: readonly CommandStagingSite[];
  /** How many invented items the exercise file holds; null when it has none. */
  itemCount: number | null;
  onRoster: (roster: RosterTeam[]) => void;
  onStaging: (staging: StagingChoice) => void;
  /** The facilitator wants to tap the staging point on the map: the sheet closes, and opens again once the point is set. */
  onPickStaging: () => void;
  onStartHour: (hour: number) => void;
  /** Go to the start hour and pause there. */
  onStart: () => void;
  onMode: (mode: CommandMode) => void;
  onItems: (shown: boolean) => void;
  onPause: (pause: boolean) => void;
  onSpeed: (speed: CommandSpeedId) => void;
  onReset: () => void;
}

/** The roster: its teams, and the row that adds one. The rule is checked as the facilitator types. */
function RosterField({ language, roster, onRoster }: { language: Language; roster: readonly RosterTeam[]; onRoster: (roster: RosterTeam[]) => void }) {
  const t = (entry: Localized) => commandText(entry, language);
  const [text, setText] = useState("");
  const [type, setType] = useState<TeamType>("boat");
  const input = useId();
  const kind = useId();
  const note = useId();
  const problem = text.trim() ? callsignProblem(text, roster) : null;
  const add = () => {
    if (!text.trim() || problem) return;
    onRoster(addRosterTeam(roster, text, type));
    setText("");
  };
  return (
    <fieldset className={act.field} data-command-setup="roster">
      <legend className={act.fieldTitle} lang={language}>{t(COMMAND_SETUP.roster)}</legend>
      <p className={act.hint}>{t(COMMAND_SETUP.rosterRule)}</p>
      <ul className={act.rosterList}>
        {roster.map((team) => (
          <li key={team.callsign} className={act.rosterRow} data-command-team={team.callsign}>
            <TeamIcon type={team.type} />
            <strong>{team.callsign}</strong>
            <select className={act.select} value={team.type} onChange={(event) => onRoster(setRosterTeamType(roster, team.callsign, event.currentTarget.value as TeamType))} aria-label={`${t(COMMAND_SETUP.type)}: ${team.callsign}`} lang={language}>
              {TEAM_TYPES.map((id) => <option key={id} value={id}>{t(COMMAND_TEAM_TYPE[id])}</option>)}
            </select>
            <button type="button" className={act.removeButton} onClick={() => onRoster(removeRosterTeam(roster, team.callsign))} aria-label={commandRemoveTeam(team.callsign, language)} title={commandRemoveTeam(team.callsign, language)}>
              <X size={18} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <div className={act.addRow}>
        <input id={input} className={act.input} type="text" value={text} onChange={(event) => setText(event.currentTarget.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); add(); } }}
          placeholder={t(COMMAND_SETUP.callsign)} aria-label={t(COMMAND_SETUP.callsign)} aria-describedby={note} aria-invalid={problem !== null} autoComplete="off" autoCapitalize="characters" spellCheck={false} enterKeyHint="done" lang={language} data-command-callsign-input />
        <select id={kind} className={act.select} value={type} onChange={(event) => setType(event.currentTarget.value as TeamType)} aria-label={t(COMMAND_SETUP.type)} lang={language}>
          {TEAM_TYPES.map((id) => <option key={id} value={id}>{t(COMMAND_TEAM_TYPE[id])}</option>)}
        </select>
        <button type="button" className={act.secondaryButton} onClick={add} disabled={!text.trim() || problem !== null} data-command-roster-add><Plus size={16} aria-hidden="true" />{t(COMMAND_SETUP.add)}</button>
      </div>
      <div id={note} role="status">
        {problem && <p className={act.problem} data-command-callsign-problem={problem}>{t(COMMAND_CALLSIGN_PROBLEM[problem])}</p>}
      </div>
      <p className={act.hint}>{t(COMMAND_SETUP.rosterExample)}</p>
    </fieldset>
  );
}

/** The facilitator's setup sheet. Every change is stored at once; nothing here needs a "save". */
export function CommandSetupSheet(props: CommandSetupSheetProps) {
  const { open, onClose, language, setup, hour, stagingSites } = props;
  const t = (entry: Localized) => commandText(entry, language);
  const title = useId();
  const stagingName = useId();
  const stagingPoint = useId();
  const { staging } = setup;
  return (
    <ModalDialog open={open} onClose={onClose} className={`${exercise.sheet} ${act.sheetWide}`} labelledBy={title} language={language} name="setup">
      <div className={exercise.dialogHead}>
        <h2 id={title}>{t(COMMAND_SETUP.title)}</h2>
        <button type="button" className={exercise.closeButton} onClick={onClose} aria-label={t(COMMAND_DRAWER.close)}><X size={20} aria-hidden="true" /></button>
      </div>
      <div className={act.sheetBody} data-command-setup-sheet>
        <div className={act.lead}>
          <span>{t(COMMAND_SETUP.intro)}</span>
          <CommandDeviceChip language={language} />
        </div>

        <RosterField language={language} roster={setup.roster} onRoster={props.onRoster} />

        <fieldset className={act.field} data-command-setup="staging">
          <legend className={act.fieldTitle} lang={language}>{t(COMMAND_SETUP.staging)}</legend>
          <p className={act.hint}>{t(COMMAND_SETUP.stagingNote)}</p>
          {stagingSites.map((site) => (
            <label key={site.id} className={act.option} lang={language}>
              <input type="radio" name={stagingName} checked={staging.type === "site" && staging.id === site.id} onChange={() => props.onStaging({ type: "site", id: site.id })} data-command-staging={site.id} />
              <span><span lang="th">{site.name.th}</span></span>
              <small><span lang="en">{site.name.en}</span> · {t(COMMAND_SETUP.stagingReported)}</small>
            </label>
          ))}
          {/* The point has no stored value until it is tapped, so choosing it starts the tap on the map. */}
          <div className={act.option} lang={language}>
            <input id={stagingPoint} type="radio" name={stagingName} checked={staging.type === "point"} onChange={props.onPickStaging} data-command-staging="point" />
            <div className={act.optionText}>
              <label htmlFor={stagingPoint}>{t(COMMAND_SETUP.stagingPoint)}</label>
              <small data-command-staging-point>{staging.type === "point" ? commandPointText(staging) : t(COMMAND_SETUP.stagingNotSet)}</small>
            </div>
            <button type="button" className={act.secondaryButton} onClick={props.onPickStaging} data-command-staging-pick><MapPin size={16} aria-hidden="true" />{t(COMMAND_SETUP.stagingPick)}</button>
          </div>
        </fieldset>

        <fieldset className={act.field} data-command-setup="start">
          <legend className={act.fieldTitle} lang={language}>{t(COMMAND_SETUP.start)}</legend>
          <div className={act.startRow}>
            <p className={act.startMoment} data-command-start-hour={setup.startHour}>{commandMoment(setup.startHour, language)}<small>{commandHourOf(setup.startHour, language)}</small></p>
            <input type="range" className={act.range} min={0} max={COMMAND_LAST_HOUR} step={1} value={setup.startHour} onChange={(event) => props.onStartHour(clampCommandHour(Number(event.currentTarget.value)))}
              aria-label={t(COMMAND_SETUP.start)} aria-valuetext={`${commandMoment(setup.startHour, language)}, ${commandHourOf(setup.startHour, language)}`} />
          </div>
          <div className={act.buttonRow}>
            <button type="button" className={act.primaryButton} onClick={props.onStart} data-command-start><Play size={16} aria-hidden="true" />{t(COMMAND_SETUP.startGo)}</button>
            <button type="button" className={act.secondaryButton} onClick={() => props.onStartHour(clampCommandHour(hour))} disabled={clampCommandHour(hour) === setup.startHour} data-command-start-now>{t(COMMAND_SETUP.startUseNow)}</button>
          </div>
          <p className={act.hint}>{t(COMMAND_SETUP.startNote)}</p>
        </fieldset>

        <fieldset className={act.field} data-command-setup="shows">
          <legend className={act.fieldTitle} lang={language}>{t(COMMAND_SETUP.shows)}</legend>
          <div className={act.segments} role="group" aria-label={t(COMMAND_MODE.label)}>
            {COMMAND_MODES.map((id) => (
              <button key={id} type="button" aria-pressed={id === setup.mode} onClick={() => props.onMode(id)} data-command-setup-mode={id}>{t(id === "trainee" ? COMMAND_MODE.trainee : COMMAND_MODE.hindsight)}</button>
            ))}
          </div>
          <p className={act.hint}>{t(setup.mode === "trainee" ? COMMAND_MODE.traineeMeaning : COMMAND_MODE.hindsightMeaning)}</p>
          <label className={act.option} lang={language}>
            <input type="checkbox" checked={setup.itemsOn} onChange={(event) => props.onItems(event.currentTarget.checked)} data-command-setup-items />
            <span>{t(COMMAND_MODE.items)}{props.itemCount === null ? "" : ` (${props.itemCount})`}</span>
            <small>{t(COMMAND_MODE.itemsNote)}</small>
          </label>
          <label className={act.option} lang={language}>
            <input type="checkbox" checked={setup.pauseOnLife} disabled={!setup.itemsOn} onChange={(event) => props.onPause(event.currentTarget.checked)} data-command-setup-pause />
            <span>{t(COMMAND_MODE.pause)}</span>
            <small>{t(COMMAND_MODE.pauseNote)}</small>
          </label>
        </fieldset>

        <fieldset className={act.field} data-command-setup="speed">
          <legend className={act.fieldTitle} lang={language}>{t(COMMAND_SETUP.speed)}</legend>
          <div className={act.segments} role="group" aria-label={t(COMMAND_SETUP.speed)}>
            {COMMAND_SPEEDS.map(({ id }) => (
              <button key={id} type="button" aria-pressed={id === setup.speed} onClick={() => props.onSpeed(id)} title={t(COMMAND_SPEED_COPY[id].meaning)} data-command-setup-speed={id}>{t(COMMAND_SPEED_COPY[id].short)}</button>
            ))}
          </div>
          <p className={act.hint}>{t(COMMAND_SPEED_COPY[setup.speed].meaning)}</p>
        </fieldset>

        <div className={act.resetBox} data-command-setup="reset">
          <p className={act.hint}>{t(COMMAND_SETUP.resetNote)}</p>
          <div className={act.buttonRow}>
            <button type="button" className={act.secondaryButton} onClick={props.onReset} data-command-reset><RotateCcw size={16} aria-hidden="true" />{t(COMMAND_SETUP.reset)}</button>
          </div>
        </div>
      </div>
    </ModalDialog>
  );
}

/** How many rows of the log the sheet lists; the export holds every row. */
export const COMMAND_LOG_ROWS_SHOWN = 50;

/** Hand the log to the reader as a CSV file. Nothing leaves the device unless the reader sends the file on. */
export function downloadCommandLog(log: readonly CommandLogEntry[]): void {
  // The byte order mark lets a spreadsheet read the Thai callsigns of the file.
  const url = URL.createObjectURL(new Blob(["﻿", commandLogCsv(log)], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = COMMAND_LOG_FILE_NAME;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The exercise log: a short history, newest first, with its export and the reset. */
export function CommandLogSheet({ open, onClose, language, log, onExport, onReset, timeZone }: {
  open: boolean;
  onClose: () => void;
  language: Language;
  log: readonly CommandLogEntry[];
  onExport: () => void;
  onReset: () => void;
  /** The time zone the device times are printed in; the device's own unless a test names one. */
  timeZone?: string;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  const title = useId();
  const shown = log.slice(-COMMAND_LOG_ROWS_SHOWN).reverse();
  return (
    <ModalDialog open={open} onClose={onClose} className={`${exercise.sheet} ${act.sheetWide}`} labelledBy={title} language={language} name="log">
      <div className={exercise.dialogHead}>
        <h2 id={title}>{t(COMMAND_LOG.title)}</h2>
        <button type="button" className={exercise.closeButton} onClick={onClose} aria-label={t(COMMAND_DRAWER.close)}><X size={20} aria-hidden="true" /></button>
      </div>
      <div className={act.sheetBody} data-command-log-sheet data-rows={log.length}>
        <div className={act.lead}>
          <span>{t(COMMAND_LOG.intro)}</span>
          <CommandDeviceChip language={language} />
        </div>
        {shown.length > 0 ? (
          <>
            <div className={act.logScroll} tabIndex={0} role="group" aria-label={t(COMMAND_LOG.title)}>
              <table className={act.logTable}>
                <thead>
                  <tr>
                    <th scope="col">{t(COMMAND_LOG.replay)}</th>
                    <th scope="col">{t(COMMAND_LOG.device)}</th>
                    <th scope="col">{t(COMMAND_LOG.role)}</th>
                    <th scope="col">{t(COMMAND_LOG.callsign)}</th>
                    <th scope="col">{t(COMMAND_LOG.action)}</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((entry) => (
                    <tr key={entry.seq} data-command-log-row={entry.seq} data-action={entry.action}>
                      <td>{commandLogReplayTime(entry.replayHour, language)}</td>
                      <td>{commandDeviceTime(entry.deviceTime, language, timeZone)}</td>
                      <td>{t(COMMAND_ROLE[entry.role])}</td>
                      <td>{entry.callsign ? <code>{entry.callsign}</code> : "–"}</td>
                      <td>{commandLogActionText(entry, language)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={act.hint} data-command-log-count>{commandLogShown(shown.length, log.length, language)}</p>
          </>
        ) : (
          <p className={act.empty} data-command-log-empty>{t(COMMAND_LOG.empty)}</p>
        )}
        <div className={act.buttonRow}>
          <button type="button" className={act.primaryButton} onClick={onExport} disabled={log.length === 0} data-command-log-export><Download size={16} aria-hidden="true" />{t(COMMAND_LOG.export)}</button>
          <button type="button" className={act.secondaryButton} onClick={onReset} data-command-reset><RotateCcw size={16} aria-hidden="true" />{t(COMMAND_SETUP.reset)}</button>
        </div>
        <p className={act.hint}>{t(COMMAND_LOG.exportNote)}</p>
        <p className={act.hint}>{t(COMMAND_SETUP.resetNote)}</p>
      </div>
    </ModalDialog>
  );
}
