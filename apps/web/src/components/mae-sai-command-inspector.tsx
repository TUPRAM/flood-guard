"use client";

/**
 * Region D of the Command exercise replay: the right card, with two tabs. "Detail" is the inspector of the selected
 * subdistrict; "Known by now" will list what had been reported or observed by the replay hour (not built yet).
 *
 * The inspector keeps the two kinds of figure apart, as the table does (decision D7). Its top half follows the replay
 * hour: model figures of the subdistrict, low confidence, with the summary at the modelled peak and the place records
 * news reported there (anecdotal, not surveyed). Its bottom half is fixed in time: one card per protocol case with the
 * planning class and its action text. No class has been issued for a Mae Sai subdistrict yet, and the cards say so.
 * On a tablet there is no right card: the same panels join the tabs of the left column.
 */

import { List, Lock, X } from "lucide-react";
import { useId, type ReactNode } from "react";

import { formatShortDate, TIMELINE_EPOCH_MS, type Language, type Localized, type ReportedDepths } from "@/lib/flood-timeline";
import { roundModelFigure, roundModelKm, type CommandShelterSet } from "@/lib/flood-timeline-command";
import {
  COMMAND_FIGURES,
  COMMAND_INSPECTOR,
  COMMAND_TABLE,
  commandBaseText,
  commandCaseLane,
  commandCaseTitle,
  commandClassLine,
  commandFacilityCount,
  commandFacilityType,
  commandHourOf,
  commandMoment,
  commandNoReachLine,
  commandPeakLines,
  commandPlanningFactLines,
  commandRecordCount,
  commandRoadBase,
  commandRoadKmList,
  commandStabilityText,
  commandText,
  commandUnlocatedRecords,
} from "@/lib/flood-timeline-command-copy";
import {
  COMMAND_PLANNING_CASES,
  type CommandPeakRecord,
  type CommandPlanningCase,
  type CommandPlanningCell,
  type CommandPlanningFacts,
  type CommandRecordPlace,
  type CommandTambonDetail,
} from "@/lib/flood-timeline-command-table";
import { reportedDepthOutcome, reportedDepthText } from "@/lib/flood-timeline-reported-depths";

import { ACTION_TEXT } from "./command-workspace";
import exercise from "./mae-sai-command-exercise.module.css";
import styles from "./mae-sai-command-inspector.module.css";
import { CommandPlanChip } from "./mae-sai-command-queue";

export type CommandCardTab = "detail" | "known";
export const COMMAND_CARD_TABS: readonly CommandCardTab[] = ["detail", "known"];

/** Whether the export pack's summary at the modelled peak has arrived. */
export type CommandPeakStatus = "loading" | "ready" | "missing";

/** One protocol case: the class of the signed protocol with its name and action text, or the honest empty state. */
export function CommandCaseCard({ planningCase, cell, facts, language }: {
  planningCase: CommandPlanningCase;
  cell: CommandPlanningCell | null;
  /** The protocol versions and anchors of the overlay the cell comes from. */
  facts: CommandPlanningFacts | null;
  language: Language;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  const issued = cell !== null && facts !== null;
  return (
    <article className={styles.caseCard} data-case={planningCase} data-issued={issued ? "true" : "false"} lang={language}>
      <header>
        <h5>{commandCaseTitle(planningCase, language)}</h5>
        <p className={styles.lane}>{commandCaseLane(planningCase, language)}</p>
      </header>
      {issued ? (
        <>
          <div className={styles.classRow}>
            <CommandPlanChip planningCase={planningCase} cell={cell} language={language} large />
            <div>
              <strong>{cell.letter ? commandClassLine(cell.letter, language) : t(COMMAND_TABLE.noClass)}</strong>
              <span>{commandStabilityText(cell.headline, language)}</span>
            </div>
          </div>
          {cell.letter && (
            <p className={styles.action}>
              <span className={exercise.eyebrow}>{t(COMMAND_INSPECTOR.action)}</span>
              {ACTION_TEXT[cell.letter][language]}
            </p>
          )}
          {cell.letter === "E" && <p className={styles.never} data-command-e-never-safe>{t(COMMAND_TABLE.eNeverSafe)}.</p>}
          <ul className={styles.facts}>{commandPlanningFactLines(cell, facts, language).map((line) => <li key={line}>{line}</li>)}</ul>
        </>
      ) : (
        <div className={styles.classRow}>
          <CommandPlanChip planningCase={planningCase} cell={null} language={language} large />
          <div>
            <strong data-command-not-issued>{t(COMMAND_TABLE.notIssuedTask)}</strong>
            <span>{t(COMMAND_INSPECTOR.notIssuedLine)}</span>
          </div>
        </div>
      )}
    </article>
  );
}

export interface CommandTambonDetailProps {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  detail: CommandTambonDetail;
  set: CommandShelterSet;
  /** The record of the subdistrict in the export pack's summary at the modelled peak, once it has loaded. */
  peak: CommandPeakRecord | null;
  peakStatus: CommandPeakStatus;
  /** The places news reported water at inside the subdistrict, with their records. */
  places: readonly CommandRecordPlace[];
  /** The depth classes of the reported depths, for the wording of a depth. */
  depths: Pick<ReportedDepths, "depth_classes"> | null;
  /** Place records of the district without a point: they are in no subdistrict's list. */
  unlocated: number;
  cells: Record<CommandPlanningCase, CommandPlanningCell | null>;
  facts: Record<CommandPlanningCase, CommandPlanningFacts | null>;
}

/** The inspector of one subdistrict. */
export function CommandTambonDetailBody({ language, hour, detail, set, peak, peakStatus, places, depths, unlocated, cells, facts }: CommandTambonDetailProps) {
  const t = (entry: Localized) => commandText(entry, language);
  const { row } = detail;
  const records = places.reduce((sum, place) => sum + place.reports.length, 0);
  const peakHour = peak ? Math.round((Date.parse(peak.peakLocalTime) - TIMELINE_EPOCH_MS) / 3_600_000) : null;
  const peakAccess = peak?.access[set] ?? null;
  const facilityNames = detail.facilities.inWater.map((facility) => facility.name || commandFacilityType(facility.type, language));
  return (
    <div className={styles.detail} data-command-detail={row.id} lang={language}>
      <header className={styles.title}>
        <span className={exercise.eyebrow}>{t(COMMAND_INSPECTOR.kind)}</span>
        <h3><span lang="th">{row.th}</span><small lang="en">{row.en}</small></h3>
      </header>

      <section data-command-section="hour">
        <div className={styles.sectionHead}>
          <h4>{t(COMMAND_INSPECTOR.sectionHour)}</h4>
          <span className={exercise.laneTag}>{t(COMMAND_FIGURES.modelTag)}</span>
        </div>
        <p className={styles.when}>{commandMoment(hour, language)} · {commandHourOf(hour, language)}</p>
        <ul className={styles.figures}>
          <li title={t(COMMAND_FIGURES.lostAccessMeaning)}>
            <strong>{roundModelFigure(row.lostAccess).text}</strong>
            <span>{t(COMMAND_FIGURES.lostAccess)}</span>
            <small>{commandBaseText(detail.withinReachBefore, language, true)}</small>
          </li>
          <li title={t(COMMAND_FIGURES.inWaterMeaning)}>
            <strong>{roundModelFigure(row.inWater).text}</strong>
            <span>{t(COMMAND_FIGURES.inWater)}</span>
          </li>
          <li title={t(COMMAND_FIGURES.roadsMeaning)}>
            <strong>{roundModelKm(detail.roadKmImpassable).text} {language === "th" ? "กม." : "km"}</strong>
            <span>{t(COMMAND_FIGURES.roads)}</span>
            <small>{commandRoadBase(detail.roadKmModelled, language)}</small>
          </li>
          <li>
            <strong>{detail.facilities.modelled > 0 ? commandFacilityCount(detail.facilities.inWater.length, detail.facilities.modelled, language) : "–"}</strong>
            <span>{t(detail.facilities.modelled > 0 ? COMMAND_INSPECTOR.facilities : COMMAND_INSPECTOR.facilitiesNone)}</span>
          </li>
        </ul>
        {row.noReachBefore >= 0.5 && (
          <p className={styles.note} data-mark={row.mostHadNoReach ? "plus" : "none"}>
            {row.mostHadNoReach && <b aria-hidden="true">+ </b>}
            {commandNoReachLine(row.noReachBefore, row.residents, row.noReachShare, language)}
          </p>
        )}
        {detail.roadsImpassable.length > 0 && <p className={styles.note}><b>{t(COMMAND_INSPECTOR.roadsNamed)}:</b> {commandRoadKmList(detail.roadsImpassable, language)}</p>}
        {facilityNames.length > 0 && <p className={styles.note}><b>{t(COMMAND_INSPECTOR.facilitiesWet)}:</b> <span lang="th">{facilityNames.join(" · ")}</span></p>}
      </section>

      <section data-command-section="peak">
        <div className={styles.sectionHead}>
          <h4>{t(COMMAND_INSPECTOR.sectionPeak)}</h4>
          {peak && peakHour !== null && Number.isFinite(peakHour) && <span className={styles.sectionMeta}>{commandMoment(peakHour, language)}</span>}
        </div>
        {peak ? (
          <>
            <ul className={styles.lines}>
              {commandPeakLines({ ...peak, access: peakAccess }, language).map((line) => <li key={line}>{line}</li>)}
            </ul>
            <p className={styles.source}>{t(COMMAND_INSPECTOR.peakSource)}</p>
          </>
        ) : (
          <p className={styles.note} role="status">{t(peakStatus === "loading" ? COMMAND_INSPECTOR.peakLoading : COMMAND_INSPECTOR.peakMissing)}</p>
        )}
      </section>

      <section data-command-section="records">
        <div className={styles.sectionHead}>
          <h4>{t(COMMAND_INSPECTOR.sectionRecords)}</h4>
          <span className={styles.reportedTag}>{t(COMMAND_INSPECTOR.recordsTag)}</span>
        </div>
        {places.length > 0 ? (
          <>
            <p className={styles.note}>{commandRecordCount(records, language)}</p>
            <ul className={styles.places}>
              {places.map((place) => (
                <li key={place.key}>
                  <strong lang="th">{place.reports[0].place.th}</strong>
                  <span className={styles.placeEn} lang="en">{place.reports[0].place.en}</span>
                  <ul>
                    {place.reports.map((report) => (
                      <li key={report.id}>
                        {/* The whole record is the link to its source, so the target is as tall as the record. */}
                        <a href={report.source.url} target="_blank" rel="noopener noreferrer" data-command-record={report.id}>
                          <span>{depths ? reportedDepthText(report, depths, language) : report.depth.statement[language]}</span>
                          <span className={styles.modelTag}>{reportedDepthOutcome(report.consistency, language)}</span>
                          <span className={styles.sourceLink}>{report.source.publisher}, {formatShortDate(report.source.published, language)}</span>
                        </a>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className={styles.note}>{t(COMMAND_INSPECTOR.recordsNone)}</p>
        )}
        {unlocated > 0 && <p className={styles.source}>{commandUnlocatedRecords(unlocated, language)}</p>}
      </section>

      <section data-command-section="plan" className={styles.plan}>
        <div className={styles.sectionHead}>
          <h4>{t(COMMAND_INSPECTOR.sectionPlan)}</h4>
          <Lock size={12} strokeWidth={2.4} aria-hidden="true" />
        </div>
        <p className={styles.note}>{t(COMMAND_TABLE.planLine)}</p>
        {COMMAND_PLANNING_CASES.map((id) => <CommandCaseCard key={id} planningCase={id} cell={cells[id]} facts={facts[id]} language={language} />)}
      </section>
    </div>
  );
}

/** What the "Known by now" tab says until its list is built. */
export function CommandKnownPlaceholder({ language }: { language: Language }) {
  return (
    <div className={styles.placeholder} lang={language} data-command-known>
      <List size={22} aria-hidden="true" />
      <strong>{commandText(COMMAND_INSPECTOR.tabKnown, language)}</strong>
      <span>{commandText(COMMAND_INSPECTOR.knownSoon, language)}</span>
    </div>
  );
}

/** What the "Detail" tab says while nothing is selected. */
export function CommandDetailEmpty({ language }: { language: Language }) {
  return (
    <div className={styles.placeholder} lang={language} data-command-detail="none">
      <span>{commandText(COMMAND_INSPECTOR.empty, language)}</span>
    </div>
  );
}

/** Region D: the right card of a desktop, left of the tool rail. The legend and this card are never open together. */
export function MaeSaiCommandInspector({ language, tab, onTab, onClose, detail, known }: {
  language: Language;
  tab: CommandCardTab;
  onTab: (tab: CommandCardTab) => void;
  /** Closes the card and clears the selection. */
  onClose: () => void;
  /** The inspector of the selected subdistrict; null while nothing is selected. */
  detail: ReactNode | null;
  known: ReactNode;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  const panel = useId();
  const label: Record<CommandCardTab, Localized> = { detail: COMMAND_INSPECTOR.tabDetail, known: COMMAND_INSPECTOR.tabKnown };
  return (
    <aside className={`${exercise.panel} ${styles.card}`} data-region="D" data-clear-panel aria-label={t(COMMAND_INSPECTOR.label)} lang={language}>
      <div className={styles.cardHead}>
        <div className={styles.cardTabs} role="tablist" aria-label={t(COMMAND_INSPECTOR.label)}>
          {COMMAND_CARD_TABS.map((id) => (
            <button key={id} type="button" role="tab" aria-selected={id === tab} aria-controls={panel} onClick={() => onTab(id)} data-command-card-tab={id}>{t(label[id])}</button>
          ))}
        </div>
        <button type="button" className={exercise.closeButton} onClick={onClose} aria-label={t(detail ? COMMAND_INSPECTOR.deselect : COMMAND_INSPECTOR.close)} title={t(detail ? COMMAND_INSPECTOR.deselect : COMMAND_INSPECTOR.close)} data-command-card-close>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <div id={panel} className={styles.cardBody} role="tabpanel" tabIndex={0} data-tab={tab}>
        {tab === "detail" ? detail ?? <CommandDetailEmpty language={language} /> : known}
      </div>
    </aside>
  );
}

/** The chip the card collapses to: it reopens the card on the selected subdistrict, or on what is known by now. */
export function CommandCardChip({ language, label, onOpen }: { language: Language; label: string; onOpen: () => void }) {
  return (
    <button type="button" className={styles.cardChip} onClick={onOpen} aria-expanded="false" data-region="D" data-command-card="chip" data-clear-panel lang={language}>
      <List size={15} aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
}
