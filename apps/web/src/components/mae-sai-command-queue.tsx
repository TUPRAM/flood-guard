"use client";

/**
 * Region B2 of the Command exercise replay: the table of the eight subdistricts. One table, one row per subdistrict,
 * two column groups that are never merged (decision D7):
 *
 *   - "This hour · model": the place of the row in this hour's count, the subdistrict (Thai name first), residents who
 *     lost shelter access with a thin bar on a fixed scale and the change since the hour before, and residents in
 *     modelled water. A T1 scenario (model), low confidence. This group holds no rating of any kind.
 *   - "Plan · fixed": the planning class of the signed protocol's cases O1 and SE1 and one planning position. Fixed in
 *     time. No class has been issued for a Mae Sai subdistrict yet, so the cells show a dash.
 *
 * The order of the rows is held while the pointer or the keyboard is in the table, so a row never moves under a
 * finger; the numbers still follow the replay hour. On a tablet the card also carries the tabs of the left column.
 */

import { ArrowDown, ArrowUp, Lock, MessageSquare, SlidersHorizontal, Table2 } from "lucide-react";
import { useEffect, useId, useRef, type FocusEvent, type ReactNode } from "react";

import type { Language, Localized } from "@/lib/flood-timeline";
import { COMMAND_SHELTER_SETS, type CommandShelterSet } from "@/lib/flood-timeline-command";
import {
  COMMAND_FIGURES,
  COMMAND_INSPECTOR,
  COMMAND_SITUATION,
  COMMAND_TABLE,
  commandCaseLane,
  commandChipLabel,
  commandNoReachNote,
  commandPlanPositionLabel,
  commandPlanScoreLabel,
  COMMAND_PLAN_SCORE,
  commandRecordCount,
  commandRowChange,
  commandSentences,
  commandSetLabel,
  commandSetMeaning,
  commandText,
} from "@/lib/flood-timeline-command-copy";
import { commandKnownCount } from "@/lib/flood-timeline-command-reports-copy";
import { COMMAND_PLANNING_CASES, type CommandOrderBy, type CommandPlanningCase, type CommandPlanningCell, type CommandTableRow } from "@/lib/flood-timeline-command-table";

import exercise from "./mae-sai-command-exercise.module.css";
import styles from "./mae-sai-command-queue.module.css";

/** The tabs of the left column on a tablet, where the right card does not exist. */
export type CommandLeftTab = "queue" | "detail" | "known";
export const COMMAND_LEFT_TABS: readonly CommandLeftTab[] = ["queue", "detail", "known"];

const pct = (share: number): string => `${(Math.min(1, Math.max(0, share)) * 100).toFixed(1)}%`;

/** A row of two or three choices, one of them pressed. The buttons are 28 px to the eye and 44 px to the finger. */
function Segments<T extends string>({ label, title, value, options, onChange }: {
  label: string;
  title?: string;
  value: T;
  options: readonly { id: T; text: string; title?: string; disabled?: boolean }[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <div className={styles.control}>
      <span id={id} className={styles.controlLabel} title={title}>{label}</span>
      <div className={styles.segments} role="group" aria-labelledby={id}>
        {options.map((option) => (
          <button key={option.id} type="button" aria-pressed={option.id === value} disabled={option.disabled} title={option.title} onClick={() => onChange(option.id)} data-option={option.id}>
            {option.text}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The controls above the table: what the rows are ordered by, which case the planning position comes from, and the shelter set. */
export function CommandQueueControls({ language, orderBy, onOrderBy, canOrderByPlanning, positionFrom, onPositionFrom, set, onSet, setSites }: {
  language: Language;
  orderBy: CommandOrderBy;
  onOrderBy: (value: CommandOrderBy) => void;
  /** False while the chosen case gives no unit a planning position: the rows cannot be ordered by it. */
  canOrderByPlanning: boolean;
  positionFrom: CommandPlanningCase;
  onPositionFrom: (value: CommandPlanningCase) => void;
  set: CommandShelterSet;
  onSet: (value: CommandShelterSet) => void;
  /** How many sites each shelter set counts. */
  setSites: Record<CommandShelterSet, number>;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  return (
    <div className={styles.controls} data-command-controls lang={language}>
      <Segments label={t(COMMAND_TABLE.orderBy)} value={orderBy} onChange={onOrderBy} options={[
        { id: "hour", text: t(COMMAND_TABLE.orderHour) },
        { id: "planning", text: t(COMMAND_TABLE.orderPlanning), disabled: !canOrderByPlanning, title: canOrderByPlanning ? undefined : t(COMMAND_TABLE.orderPlanningOff) },
      ]} />
      <Segments label={t(COMMAND_TABLE.positionFrom)} title={t(COMMAND_TABLE.positionFromMeaning)} value={positionFrom} onChange={onPositionFrom}
        options={COMMAND_PLANNING_CASES.map((id) => ({ id, text: id, title: commandCaseLane(id, language) }))} />
      <Segments label={t(COMMAND_TABLE.shelterSet)} value={set} onChange={onSet}
        options={COMMAND_SHELTER_SETS.map((id) => ({ id, text: commandSetLabel(id, setSites[id], language), title: commandSetMeaning(id, setSites[id], language) }))} />
      <p className={styles.setNote}>{t(COMMAND_TABLE.setNote)}</p>
    </div>
  );
}

/**
 * One chip of the plan group. A dash while no class is issued. O1 is the amber chip of the protocol's own-candidate
 * lane and SE1 the hatched chip of its scenario lane, so the lane is carried by the pattern as well as by the column.
 * A chip is filled only when the class is headline-eligible; a question mark says "unstable: verify".
 */
export function CommandPlanChip({ planningCase, cell, language, large = false }: { planningCase: CommandPlanningCase; cell: CommandPlanningCell | null; language: Language; large?: boolean }) {
  const label = commandChipLabel(planningCase, cell, language);
  const state = !cell || cell.letter === null ? "empty" : cell.filled ? "filled" : cell.headline === "unstable_verify" ? "unstable" : "outline";
  return (
    <span className={styles.chip} data-case={planningCase} data-state={state} data-size={large ? "large" : "small"} data-letter={cell?.letter ?? undefined} title={label} data-command-chip={planningCase}>
      <span aria-hidden="true">{cell?.letter ?? "–"}{state === "unstable" ? "?" : ""}</span>
      <span className={exercise.srOnly}>{label}</span>
    </span>
  );
}

function ChangeMark({ change, language }: { change: CommandTableRow["change"]; language: Language }) {
  if (change.direction === 0) return <span className={styles.delta} data-direction="0" aria-hidden="true" />;
  const Arrow = change.direction > 0 ? ArrowUp : ArrowDown;
  return (
    <span className={styles.delta} data-direction={change.direction > 0 ? "up" : "down"} title={commandRowChange(change, language)}>
      <Arrow size={10} strokeWidth={2.5} aria-hidden="true" />
      <span aria-hidden="true">{change.text.replace(/^[+−]/u, "")}</span>
      <span className={exercise.srOnly}>{commandRowChange(change, language)}</span>
    </span>
  );
}

/** The table itself: two header lines, the eight rows and the footer. */
export function CommandQueueTable({ language, rows, selected, onSelect, set, positionFrom, pending, onHold, toggle }: {
  language: Language;
  rows: readonly CommandTableRow[];
  /** The selected subdistrict, if any. */
  selected: string | null;
  onSelect: (id: string) => void;
  set: CommandShelterSet;
  positionFrom: CommandPlanningCase;
  /** True while the order shown is held and differs from the order the rules give at this hour. */
  pending: boolean;
  /** The pointer or the keyboard entered or left the rows: the page holds the order meanwhile. */
  onHold?: (source: "pointer" | "focus", held: boolean) => void;
  /** The button that shows or hides the controls, in the head of the table on a desktop. */
  toggle?: ReactNode;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  const foot = useId();
  const issued = rows.some((row) => COMMAND_PLANNING_CASES.some((id) => row.cells[id] !== null));
  const showsE = rows.some((row) => COMMAND_PLANNING_CASES.some((id) => row.cells[id]?.letter === "E"));
  const positionLabel = commandPlanPositionLabel(positionFrom, language);
  const scoreLabel = commandPlanScoreLabel(positionFrom, language);
  const scoreMeaning = `${scoreLabel}. ${t(COMMAND_PLAN_SCORE.meaning)}`;
  // Only keyboard focus holds the order: a row keeps the focus after a click, and that must not freeze the table.
  const focusIn = (event: FocusEvent<HTMLDivElement>) => { if (event.target.matches(":focus-visible")) onHold?.("focus", true); };
  const focusOut = (event: FocusEvent<HTMLDivElement>) => { if (!event.currentTarget.contains(event.relatedTarget)) onHold?.("focus", false); };
  // When the table goes away under the pointer (a tablet opens the detail tab, focus mode folds the card), no pointer
  // or focus event says so: the holds are released here.
  useEffect(() => () => {
    onHold?.("pointer", false);
    onHold?.("focus", false);
  }, [onHold]);
  // Where the table scrolls inside its card (a tablet), it fades at its lower edge so a cut row reads as "more
  // below". The fade is only as tall as what is cut below the last row: it never lies over a row that is in view, and
  // it is gone once the table is scrolled to its end.
  const wrap = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const element = wrap.current;
    if (!element || typeof ResizeObserver !== "function") return;
    const measure = () => {
      const rowsShown = element.querySelectorAll<HTMLElement>("[data-tambon]");
      const last = rowsShown.length > 0 ? rowsShown[rowsShown.length - 1] : null;
      const box = element.getBoundingClientRect();
      const atEnd = element.scrollTop + element.clientHeight >= element.scrollHeight - 1;
      const spare = last ? box.bottom - last.getBoundingClientRect().bottom : 0;
      const fade = atEnd ? 0 : spare >= 0 ? Math.min(22, Math.floor(spare)) : 22;
      element.style.setProperty("--fade", `${fade}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    element.addEventListener("scroll", measure, { passive: true });
    measure();
    return () => {
      observer.disconnect();
      element.removeEventListener("scroll", measure);
    };
  }, [rows.length, language]);
  return (
    <>
    {/* A screen reader hears that the order is held; the pill in the head says it to the eye. The line stands beside
        the table: a table holds rows only. */}
    <span className={exercise.srOnly} role="status" data-command-order-status>{pending ? commandSentences([t(COMMAND_TABLE.orderHeld), t(COMMAND_TABLE.orderHeldMeaning)], language) : ""}</span>
    <div ref={wrap} className={styles.tableWrap} role="table" aria-label={t(COMMAND_TABLE.title)} aria-describedby={foot} data-command-table data-order-held={pending ? "true" : "false"} lang={language}>
      <div className={styles.head} role="rowgroup">
        <div className={styles.headRow} role="row">
          <span className={`${styles.gHour} ${styles.groupTitle}`} role="columnheader" aria-colspan={4} data-group="hour">
            <span className={styles.groupName}>{t(COMMAND_TABLE.groupHour)}</span>
            <span className={exercise.laneTag} title={t(COMMAND_FIGURES.modelTag)}>{t(COMMAND_TABLE.groupHourTag)}</span>
            {toggle}
          </span>
          <span className={`${styles.gPlan} ${styles.groupTitle}`} role="columnheader" aria-colspan={3} data-group="plan" title={t(COMMAND_TABLE.groupPlanMeaning)}>
            <span className={styles.groupName}>{t(COMMAND_TABLE.groupPlan)}</span>
            <Lock size={11} strokeWidth={2.4} aria-hidden="true" />
            <span className={exercise.srOnly}>{t(COMMAND_TABLE.groupPlanMeaning)}</span>
          </span>
        </div>
        <div className={`${styles.headRow} ${styles.captions}`} role="row">
          <span className={styles.gHour} role="presentation" data-group="hour">
            <span role="columnheader" aria-label={t(COMMAND_TABLE.colPosition)} title={t(COMMAND_TABLE.colPosition)}>#</span>
            <span role="columnheader">
              {pending
                ? <span className={styles.held} title={t(COMMAND_TABLE.orderHeldMeaning)} data-command-order-held>{t(COMMAND_TABLE.orderHeld)}</span>
                : <span className={styles.colName}>{t(COMMAND_TABLE.colTambon)}</span>}
              {/* A narrow card has no line of group titles: the left group is named here, in the tag of a modelled figure. */}
              {!pending && <span className={`${exercise.laneTag} ${styles.headTag}`} title={t(COMMAND_FIGURES.modelTag)} aria-hidden="true">{t(COMMAND_TABLE.groupHour)}</span>}
            </span>
            <span role="columnheader" className={styles.right} title={t(COMMAND_FIGURES.lostAccessMeaning)}>{t(COMMAND_TABLE.colLost)}</span>
            <span role="columnheader" className={styles.right} title={t(COMMAND_FIGURES.inWaterMeaning)}>{t(COMMAND_TABLE.colWater)}</span>
          </span>
          <span className={styles.gPlan} role="presentation" data-group="plan">
            {COMMAND_PLANNING_CASES.map((id) => <span key={id} role="columnheader" title={commandCaseLane(id, language)}>{id}</span>)}
            <span role="columnheader" aria-label={scoreLabel} title={scoreMeaning}>{t(COMMAND_PLAN_SCORE.short)}</span>
          </span>
        </div>
      </div>
      <div className={styles.body} role="rowgroup" onPointerEnter={() => onHold?.("pointer", true)} onPointerLeave={() => onHold?.("pointer", false)} onFocus={focusIn} onBlur={focusOut}>
        {rows.map(({ row, position, lost, water, change, bar, cells, planningPosition }) => {
          // The planning score of the case the position comes from: shown beside the class, so that a class is never
          // read alone (a score of 70 in class D is not a low priority).
          const score = cells[positionFrom]?.fpps ?? null;
          const isSelected = row.id === selected;
          return (
            <div key={row.id} className={styles.row} role="row" data-tambon={row.id} data-selected={isSelected ? "true" : "false"} data-quiet={lost.kind === "zero" && water.kind === "zero" ? "true" : "false"} onClick={() => onSelect(row.id)}>
              <span className={styles.gHour} role="presentation" data-group="hour">
                <span className={styles.cIdx} role="cell">{position}</span>
                <span className={styles.cName} role="cell">
                  {/* The row is selected with this button; a click anywhere on the row reaches it too. */}
                  <button type="button" className={styles.rowButton} aria-pressed={isSelected} data-command-row={row.id}>
                    <span className={styles.nameTh} lang="th">{row.th}</span>
                    <span className={styles.nameEn} lang="en">{row.en}</span>
                    {row.placeRecords > 0 && (
                      <span className={styles.records} title={commandRecordCount(row.placeRecords, language)} data-command-records={row.placeRecords}>
                        <MessageSquare size={11} strokeWidth={2.2} aria-hidden="true" />
                        <span aria-hidden="true">{row.placeRecords}</span>
                        <span className={exercise.srOnly}>{commandRecordCount(row.placeRecords, language)}</span>
                      </span>
                    )}
                  </button>
                </span>
                <span className={styles.cLost} role="cell" data-kind={lost.kind}>
                  <ChangeMark change={change} language={language} />
                  <span className={styles.num}>
                    {lost.text}
                    {row.mostHadNoReach
                      ? <span className={styles.plus} title={t(COMMAND_TABLE.noReachMeaning)} data-command-no-reach>+<span className={exercise.srOnly}> {t(COMMAND_TABLE.noReachMeaning)}</span></span>
                      : <span className={styles.plus} aria-hidden="true" />}
                  </span>
                  <span className={styles.bar} aria-hidden="true"><i style={{ width: pct(bar) }} /></span>
                </span>
                <span className={styles.cWater} role="cell" data-kind={water.kind}><span className={styles.num}>{water.text}</span></span>
              </span>
              <span className={styles.gPlan} role="presentation" data-group="plan" title={t(COMMAND_TABLE.groupPlanMeaning)}>
                <Lock className={styles.pillLock} size={10} strokeWidth={2.4} aria-hidden="true" />
                {COMMAND_PLANNING_CASES.map((id) => (
                  <span key={id} className={styles.cChip} role="cell">
                    <span className={styles.inlineCaption} aria-hidden="true">{id}</span>
                    <CommandPlanChip planningCase={id} cell={cells[id]} language={language} />
                  </span>
                ))}
                <span className={styles.cPos} role="cell" data-command-score={score ?? undefined}
                  title={score === null ? scoreLabel : `${scoreLabel}: ${score.toFixed(1)} · ${positionLabel}: ${planningPosition ?? "–"}`}>
                  <span className={styles.inlineCaption} aria-hidden="true">{t(COMMAND_PLAN_SCORE.short)}</span>
                  <span aria-hidden="true">{score === null ? "–" : Math.round(score)}</span>
                  <span className={exercise.srOnly}>{commandSentences([`${scoreLabel}: ${score === null ? t(COMMAND_TABLE.notIssued) : score.toFixed(1)}`, `${positionLabel}: ${planningPosition ?? t(COMMAND_TABLE.notIssued)}`], language)}</span>
                </span>
              </span>
            </div>
          );
        })}
      </div>
      <div id={foot} className={styles.foot} data-command-table-foot>
        <p>{commandNoReachNote(set, language)}</p>
        {/* One line: the full sentence is in the inspector, on hover, and read out with the table. */}
        <p className={styles.planNote} title={t(COMMAND_TABLE.planLine)} data-command-plan-note>
          <Lock size={11} strokeWidth={2.4} aria-hidden="true" />
          <span>
            {!issued && <b data-command-not-issued>{commandSentences([t(COMMAND_TABLE.notIssued)], language)} </b>}
            <span aria-hidden="true">{commandSentences([t(COMMAND_TABLE.planLineShort)], language)}</span>
            <span className={exercise.srOnly}>{t(COMMAND_TABLE.planLine)}</span>
          </span>
        </p>
        {showsE && <p className={styles.never} data-command-e-never-safe>{commandSentences([t(COMMAND_TABLE.eNeverSafe)], language)}</p>}
        {issued && <p>{commandSentences([`O1 · ${commandCaseLane("O1", language)}`, `SE1 · ${commandCaseLane("SE1", language)}`, t(COMMAND_TABLE.chipKey)], language)}</p>}
      </div>
    </div>
    </>
  );
}

/**
 * The top row, as the card shows it in focus mode: the subdistrict with the model tag, and its two figures under it.
 * The figures are modelled, and the tag says so in words.
 */
function TopRowLine({ row, language }: { row: CommandTableRow; language: Language }) {
  return (
    <div className={styles.topRow} data-command-top-row={row.row.id}>
      <p className={styles.topName}>
        <span className={styles.cIdx}>{row.position}</span>
        <strong lang="th">{row.row.th}</strong>
        <span lang="en">{row.row.en}</span>
      </p>
      <span className={exercise.laneTag} data-command-lane="model">{commandText(COMMAND_FIGURES.modelTag, language)}</span>
      <p className={styles.topFigures}>{row.lost.text} {commandText(COMMAND_FIGURES.changeLost, language)} · {row.water.text} {commandText(COMMAND_FIGURES.changeWater, language)}</p>
    </div>
  );
}

export interface CommandQueueProps {
  language: Language;
  /** The rows as the table prints them; null until the replay data has loaded. */
  rows: readonly CommandTableRow[] | null;
  selected: string | null;
  onSelect: (id: string) => void;
  set: CommandShelterSet;
  onSet: (value: CommandShelterSet) => void;
  setSites: Record<CommandShelterSet, number>;
  orderBy: CommandOrderBy;
  onOrderBy: (value: CommandOrderBy) => void;
  canOrderByPlanning: boolean;
  positionFrom: CommandPlanningCase;
  onPositionFrom: (value: CommandPlanningCase) => void;
  pending: boolean;
  onHold?: (source: "pointer" | "focus", held: boolean) => void;
  /** Whether the controls above the table are shown. On a short screen and on a tablet they start hidden behind their button. */
  optionsOpen: boolean;
  onOptions: (open: boolean) => void;
  /** Focus mode: one 44 px line with the top row. */
  collapsed?: boolean;
  /** The replay data could not be loaded. */
  failed?: boolean;
  /** A tablet has no right card: this card then carries the tabs of the left column, and the two other panels. */
  layout?: "desktop" | "tablet";
  tab?: CommandLeftTab;
  onTab?: (tab: CommandLeftTab) => void;
  detail?: ReactNode;
  /** What stays fixed under the detail tab while it scrolls: the action bar of an invented item. */
  detailFooter?: ReactNode;
  known?: ReactNode;
  /** How many rows "Known by now" holds at this replay hour: printed on its tab. */
  knownCount?: number;
}

/** Region B2: the card of the subdistrict table. */
export function MaeSaiCommandQueue(props: CommandQueueProps) {
  const { language, rows, collapsed = false, failed = false, layout = "desktop", tab = "queue", onTab, optionsOpen, onOptions } = props;
  const t = (entry: Localized) => commandText(entry, language);
  const controlsId = useId();
  const panelId = useId();
  const section = (children: ReactNode, state: string) => (
    <section className={`${exercise.panel} ${styles.queue}`} data-region="B2" data-clear-panel data-state={state} data-layout={layout} aria-label={t(COMMAND_TABLE.title)} lang={language}>{children}</section>
  );
  if (collapsed) {
    const top = rows?.[0];
    return section(top ? <TopRowLine row={top} language={language} /> : <p className={styles.topRow}><strong>{t(COMMAND_TABLE.title)}</strong></p>, "collapsed");
  }
  const optionsButton = (
    <button type="button" className={styles.optionsButton} onClick={() => onOptions(!optionsOpen)} aria-expanded={optionsOpen} aria-controls={controlsId} aria-label={t(COMMAND_TABLE.options)} title={t(COMMAND_TABLE.options)} data-command-options>
      <SlidersHorizontal size={16} aria-hidden="true" />
    </button>
  );
  const tablet = layout === "tablet";
  const tabLabel: Record<CommandLeftTab, Localized> = { queue: COMMAND_TABLE.tabQueue, detail: COMMAND_INSPECTOR.tabDetail, known: COMMAND_INSPECTOR.tabKnownShort };
  const queuePanel = rows ? (
    <>
      <div id={controlsId} className={styles.controlsSlot} hidden={!optionsOpen}>
        {optionsOpen && (
          <CommandQueueControls language={language} orderBy={props.orderBy} onOrderBy={props.onOrderBy} canOrderByPlanning={props.canOrderByPlanning}
            positionFrom={props.positionFrom} onPositionFrom={props.onPositionFrom} set={props.set} onSet={props.onSet} setSites={props.setSites} />
        )}
      </div>
      <CommandQueueTable language={language} rows={rows} selected={props.selected} onSelect={props.onSelect} set={props.set} positionFrom={props.positionFrom}
        pending={props.pending} onHold={props.onHold} toggle={tablet ? undefined : optionsButton} />
    </>
  ) : (
    <div className={styles.waiting} role="status">
      <Table2 size={22} aria-hidden="true" />
      <strong>{t(COMMAND_TABLE.title)}</strong>
      <span>{t(failed ? COMMAND_SITUATION.error : COMMAND_TABLE.loading)}</span>
    </div>
  );
  if (!tablet) return section(queuePanel, rows ? "ready" : "waiting");
  return section(
    <>
      <div className={styles.tabBar}>
        <div className={styles.tabs} role="tablist" aria-label={t(COMMAND_TABLE.tabs)}>
          {COMMAND_LEFT_TABS.map((id) => (
            <button key={id} type="button" role="tab" aria-selected={id === tab} aria-controls={panelId} onClick={() => onTab?.(id)} data-command-tab={id}>
              {id === "known" && props.knownCount !== undefined ? commandKnownCount(tabLabel[id], props.knownCount, language) : t(tabLabel[id])}
            </button>
          ))}
        </div>
        {tab === "queue" && rows && optionsButton}
      </div>
      <div id={panelId} className={styles.tabPanel} role="tabpanel" data-tab={tab}>
        {tab === "queue" ? queuePanel : tab === "detail" ? props.detail : props.known}
      </div>
      {tab === "detail" && props.detailFooter}
    </>,
    rows ? "ready" : "waiting",
  );
}
