"use client";

/**
 * The inspector of a report on the map of the Command exercise replay: an invented item of the exercise (incident
 * mode), or the reports saved on this device for one subdistrict.
 *
 * An invented item says that it is invented before anything else. Its urgency was set by its author from the facts
 * the item states (the rule is printed under it), never by the model; the operator can move it one step with one tap,
 * and that is logged. Under it the inspector states facts and gives no advice: how to get near (the modelled depth at
 * the point with "current not modelled", whether that is at or over the 0.3 m at which a road counts as impassable,
 * the nearest road piece under 0.3 m, the named roads impassable in the subdistrict, the straight line from the
 * staging point) and where people go (the three nearest of the located sites counted in the 2024 set, by straight
 * line, and one line from the access model). Every model line is a T1 scenario value with low confidence.
 *
 * The action bar is fixed under the inspector: Assign, Brief, Done. There are no confirmation dialogs; each action
 * can be undone for ten seconds. A report saved on this device carries the date it was saved; it is outside the
 * replay clock, it names a subdistrict and no point, it was sent to nobody, and no team is assigned to it.
 */

import { ArrowDown, ArrowUp, BriefcaseMedical, Ellipsis, Footprints, Sailboat, Truck } from "lucide-react";
import { useEffect, useRef } from "react";

import { formatDateWithYear, type Language, type Localized } from "@/lib/flood-timeline";
import {
  COMMAND_ACT,
  COMMAND_DROP_REASON,
  COMMAND_GO,
  COMMAND_NEAR,
  COMMAND_TEAM_TYPE,
  commandAssignTo,
  commandDepthFactLine,
  commandDropLabel,
  commandGoMeta,
  commandImpassableLead,
  commandNodeLine,
  commandReportedInUse,
  commandRoadFact,
  commandSiteState,
  commandStagingLine,
  commandUrgencyChanged,
} from "@/lib/flood-timeline-command-act-copy";
import { commandDistanceBearing, type ItemFacts } from "@/lib/flood-timeline-command-brief";
import { COMMAND_FIGURES, COMMAND_MAP, commandRoadKmList, commandText } from "@/lib/flood-timeline-command-copy";
import { EXERCISE_URGENCIES, exerciseMarkerSpec, isOpenStatus, waitingHours, type ExerciseHandling, type ExerciseItem, type ExerciseUrgency } from "@/lib/flood-timeline-command-incidents";
import { DROP_REASONS, type CommandItemAction, type RosterTeam, type TeamType } from "@/lib/flood-timeline-command-log";
import {
  COMMAND_DEPTH_BAND,
  COMMAND_DEVICE,
  COMMAND_EXERCISE,
  COMMAND_MARKERS,
  COMMAND_NEED,
  COMMAND_PEOPLE_BAND,
  COMMAND_STATUS,
  COMMAND_URGENCY,
  commandDeviceCount,
  commandDeviceMeta,
  commandItemKind,
  commandItemTolerance,
  commandItemWhenLine,
  commandModelHereLine,
  commandWaitingText,
} from "@/lib/flood-timeline-command-reports-copy";
import { publicReportWaterDepthLabel, type PublicReport } from "@/lib/public-report";

import act from "./mae-sai-command-act.module.css";
import exercise from "./mae-sai-command-exercise.module.css";
import styles from "./mae-sai-command-feed.module.css";
import inspector from "./mae-sai-command-inspector.module.css";
import { EXERCISE_MARKER_VIEWBOX, exerciseMarkerNodes, MarkerGlyph } from "./mae-sai-command-markers";

const STAR_PATH = "M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5L7 14.3l-5.3-5 7.2-.9z";

/** The sign of a team's kind beside its callsign. It says what the roster holds; the page never suggests a kind. */
export function TeamIcon({ type, size = 16 }: { type: TeamType; size?: number }) {
  const Icon = type === "boat" ? Sailboat : type === "wading" ? Footprints : type === "vehicle" ? Truck : BriefcaseMedical;
  return <Icon size={size} aria-hidden="true" />;
}

export interface CommandItemDetailProps {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  /** The item with the urgency in force: the operator's, when one was set. */
  item: ExerciseItem;
  handling: ExerciseHandling;
  /** The subdistrict the item is in. */
  tambon: Localized | null;
  /** The modelled depth at the item's point at this replay hour (m); null outside the grid, undefined before the raster has loaded. */
  depth: number | null | undefined;
  /** The urgency rule in words, from the exercise file. */
  rule: Localized;
  /** The urgency the author of the item set; it differs from the item's when the operator moved it. */
  authorUrgency?: ExerciseUrgency;
  /** The facts about the item's point at this replay hour; null until the replay data has loaded. */
  facts?: ItemFacts | null;
  /** The named roads the model has impassable in the item's subdistrict at this hour, the longest length first. */
  roadsImpassable?: readonly { name: string; km: number }[];
  /** How many located sites the 2024 set counts (twelve in the r4 data). */
  countedSites?: number;
  /** One step more urgent (1) or less urgent (-1); without it the urgency cannot be moved. */
  onUrgency?: (direction: 1 | -1) => void;
}

/** The inspector of one invented item. */
export function CommandItemDetailBody({ language, hour, item, handling, tambon, depth, rule, authorUrgency = item.urgency, facts = null, roadsImpassable = [], countedSites, onUrgency }: CommandItemDetailProps) {
  const t = (entry: Localized) => commandText(entry, language);
  const open = isOpenStatus(handling.status);
  const waiting = open ? waitingHours(item, hour) : null;
  const spec = exerciseMarkerSpec(item, handling.status);
  const level = EXERCISE_URGENCIES.indexOf(item.urgency);
  const callsign = handling.status !== "new" && handling.status !== "acknowledged" ? handling.callsign : null;
  const depthLine = facts ? commandDepthFactLine(facts.depthFact, language) : null;
  return (
    <div className={inspector.detail} data-command-item={item.id} data-urgency={item.urgency} data-status={handling.status} lang={language}>
      <header className={styles.itemHead}>
        <p className={styles.itemKind}>
          <span className={styles.tag} data-lane="exercise">{t(COMMAND_EXERCISE.tag)}</span>
          <span>{commandItemKind(item, language)}</span>
          <code>{item.id}</code>
        </p>
        <div className={inspector.title}>
          <h3><span lang="th">{item.place.th}</span><small lang="en">{item.place.en}</small></h3>
        </div>
        <p className={inspector.when}>
          {tambon && <>{language === "th" ? `ต.${tambon.th}` : `${tambon.en} subdistrict`} · </>}{commandItemTolerance(item.toleranceM, language)}
        </p>
      </header>

      <div className={act.urgencyRow} data-urgency={item.urgency} data-status={handling.status} data-open={open ? "true" : "false"} data-command-urgency>
        <MarkerGlyph nodes={exerciseMarkerNodes(spec)} viewBox={EXERCISE_MARKER_VIEWBOX} size={28} />
        <div>
          <strong><span>{t(COMMAND_URGENCY[item.urgency])}</span> · <span>{t(COMMAND_STATUS[handling.status])}</span></strong>
          {/* The callsign of the team the item is assigned to stays with the item when it is closed. */}
          {(callsign || waiting !== null) && (
            <span data-command-urgency-line>
              {callsign && <b data-command-item-callsign>{callsign}</b>}
              {callsign && waiting !== null ? " · " : ""}
              {waiting !== null && commandWaitingText(waiting, language)}
            </span>
          )}
          {authorUrgency !== item.urgency && <span data-command-urgency-changed>{commandUrgencyChanged(authorUrgency, item.urgency, language)}</span>}
        </div>
        {onUrgency && open && (
          <div className={act.steps}>
            <button type="button" className={act.step} onClick={() => onUrgency(1)} disabled={level <= 0} aria-label={t(COMMAND_ACT.raise)} title={t(COMMAND_ACT.raise)} data-command-urgency-step="raise">
              <ArrowUp size={18} aria-hidden="true" />
            </button>
            <button type="button" className={act.step} onClick={() => onUrgency(-1)} disabled={level >= EXERCISE_URGENCIES.length - 1} aria-label={t(COMMAND_ACT.lower)} title={t(COMMAND_ACT.lower)} data-command-urgency-step="lower">
              <ArrowDown size={18} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      <section data-command-section="said">
        <div className={inspector.sectionHead}><h4>{t(COMMAND_EXERCISE.said)}</h4></div>
        <p className={styles.said}>{t(item.text)}</p>
        <ul className={styles.facts} aria-label={t(COMMAND_EXERCISE.what)}>
          <li>{t(COMMAND_DEPTH_BAND[item.depthBand])}</li>
          <li>{t(COMMAND_PEOPLE_BAND[item.peopleBand])}</li>
          {item.needs.length > 0
            ? item.needs.map((need) => <li key={need}>{t(COMMAND_EXERCISE.needs)}: {t(COMMAND_NEED[need])}</li>)
            : <li>{t(COMMAND_EXERCISE.noNeeds)}</li>}
        </ul>
        <p className={inspector.source}>{commandItemWhenLine(item, null, language)}</p>
      </section>

      <section data-command-section="near">
        <div className={inspector.sectionHead}>
          <h4>{t(COMMAND_NEAR.title)}</h4>
          <span className={act.factTag}>{t(COMMAND_NEAR.factsOnly)}</span>
          <span className={exercise.laneTag}>{t(COMMAND_FIGURES.modelTag)}</span>
        </div>
        <ul className={act.facts} lang={language}>
          <li data-command-fact="depth">
            <span><b>{t(COMMAND_EXERCISE.modelHere)}:</b> <span data-command-model-here>{commandModelHereLine(depth, language).replace(/^[^:]+: /u, "")}</span></span>
            {depthLine && <small data-command-depth-fact={facts?.depthFact}>{depthLine}</small>}
          </li>
          {facts && (
            <li data-command-fact="road">
              <span>{commandRoadFact(facts.road, language)}</span>
              <small>{t(COMMAND_NEAR.roadLimit)}</small>
            </li>
          )}
          {facts && (
            <li data-command-fact="roads">
              {roadsImpassable.length > 0
                ? <span><b>{commandImpassableLead(tambon, language)}:</b> {commandRoadKmList(roadsImpassable, language)}</span>
                : <span>{t(COMMAND_NEAR.noNamedRoads)}</span>}
            </li>
          )}
          {facts?.staging && (
            <li data-command-fact="staging">
              <span>{commandStagingLine(facts.staging, language)}</span>
              <small>{t(COMMAND_NEAR.straightLine)}</small>
            </li>
          )}
        </ul>
        <p className={inspector.source}>{t(COMMAND_NEAR.noAdvice)}</p>
      </section>

      {facts && (
        <section data-command-section="go">
          <div className={inspector.sectionHead}>
            <h4>{t(COMMAND_GO.title)}</h4>
            <span className={inspector.sectionMeta}>{commandGoMeta(facts.sites.length, countedSites ?? facts.sites.length, language)}</span>
          </div>
          {facts.sites.length > 0 ? (
            <ol className={act.sites}>
              {facts.sites.map((site) => (
                <li key={site.id} className={act.site} data-command-site={site.id} data-state={site.state} data-pending={site.pending ? "true" : "false"}>
                  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                    <path d={STAR_PATH} fill={site.pending ? "#ffffff" : "#17616e"} stroke="#17616e" strokeWidth="1.6" strokeLinejoin="round" strokeDasharray={site.pending ? "2.6 2" : undefined} />
                  </svg>
                  <div>
                    <p className={act.siteName}><strong lang="th">{site.name.th}</strong><small lang="en">{site.name.en}</small></p>
                    <p className={act.siteWhere}>
                      <span>{commandDistanceBearing(site.distanceM, site.compass, language)}</span>
                      <span className={act.siteState} data-state={site.state}>{commandSiteState(site.state, language)}</span>
                    </p>
                    {site.pending ? (
                      <p className={act.sitePending}>{t(COMMAND_MARKERS.siteNotYet)}</p>
                    ) : (
                      <>
                        <p className={act.siteLine}>{commandReportedInUse(site.use, language)}</p>
                        {site.occupancyHeld
                          ? <p className={act.siteLine} data-command-occupancy="held">{t(COMMAND_GO.occupancyHeld)}</p>
                          : <p className={act.siteLine} data-command-occupancy="shown">{t(COMMAND_MAP.occupancy)}: {site.occupancy ? <span lang="en">{site.occupancy}</span> : t(COMMAND_MAP.notReported)}</p>}
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className={inspector.note}>{t(COMMAND_GO.none)}</p>
          )}
          <p className={inspector.note} data-command-node-line data-access={facts.node?.access ?? "none"}>{commandNodeLine(facts.node, language)}</p>
          <p className={inspector.source}>{t(COMMAND_GO.limit)}</p>
        </section>
      )}

      <section data-command-section="rule">
        <div className={inspector.sectionHead}><h4>{t(COMMAND_EXERCISE.ruleTitle)}</h4></div>
        <p className={inspector.source}>{t(rule)}</p>
        <p className={inspector.source}>{t(COMMAND_EXERCISE.notReal)}</p>
      </section>
    </div>
  );
}

/** Which tray of the action bar is open: the roster to assign from, or the further actions. */
export type CommandActTray = "assign" | "more" | null;

export interface CommandItemActionBarProps {
  language: Language;
  item: Pick<ExerciseItem, "id">;
  handling: ExerciseHandling;
  roster: readonly RosterTeam[];
  tray: CommandActTray;
  onTray: (tray: CommandActTray) => void;
  /** Take an action on the item. Nothing asks "are you sure": each action can be undone for ten seconds. */
  onAction: (action: CommandItemAction) => void;
  onBrief: () => void;
  /** Open the exercise setup, where the roster is typed. */
  onSetup: () => void;
}

/**
 * The fixed action bar of an invented item: Assign, Brief, Done. Assign opens the roster typed on this device; the
 * fourth button holds what is used less often (acknowledge, drop as a duplicate, drop as one that could not be
 * reached). A closed item offers Reopen in the place of Done.
 */
export function CommandItemActionBar({ language, item, handling, roster, tray, onTray, onAction, onBrief, onSetup }: CommandItemActionBarProps) {
  const t = (entry: Localized) => commandText(entry, language);
  const open = isOpenStatus(handling.status);
  const bar = useRef<HTMLDivElement | null>(null);
  const shownTray = useRef<CommandActTray>(null);
  // A tray that opens takes the keyboard focus (its first choice is the next key away); one that closes with the
  // focus inside it hands the focus back to the button that opened it.
  useEffect(() => {
    const before = shownTray.current;
    shownTray.current = tray;
    const root = bar.current;
    if (!root || before === tray) return;
    if (tray) root.querySelector<HTMLElement>("[data-command-tray] button:not(:disabled)")?.focus({ preventScroll: true });
    else if (before && (!document.activeElement || document.activeElement === document.body)) root.querySelector<HTMLElement>(`[data-command-act="${before}"]`)?.focus({ preventScroll: true });
  }, [tray]);
  return (
    <div ref={bar} className={act.bar} role="group" aria-label={t(COMMAND_ACT.barLabel)} data-command-actions={item.id} data-status={handling.status} lang={language}>
      {tray === "assign" && open && (
        <div className={act.tray} data-command-tray="assign">
          <p className={act.trayTitle}>{t(COMMAND_ACT.pickTitle)}</p>
          {roster.length > 0 ? (
            <ul className={act.roster}>
              {roster.map((team) => (
                <li key={team.callsign}>
                  <button type="button" className={act.team} onClick={() => onAction({ type: "assign", callsign: team.callsign })} aria-pressed={handling.status === "assigned" && handling.callsign === team.callsign}
                    aria-label={commandAssignTo(team.callsign, team.type, language)} data-command-callsign={team.callsign} data-team-type={team.type}>
                    <TeamIcon type={team.type} />
                    <strong>{team.callsign}</strong>
                    <small>{t(COMMAND_TEAM_TYPE[team.type])}</small>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={act.trayNote}>{t(COMMAND_ACT.rosterEmpty)}</p>
          )}
          <div className={act.trayFoot}>
            <span className={act.trayNote}>{t(COMMAND_ACT.pickNote)}</span>
            <button type="button" className={act.textButton} onClick={onSetup} data-command-edit-roster>{t(COMMAND_ACT.editRoster)}</button>
          </div>
        </div>
      )}
      {tray === "more" && (
        <div className={act.tray} data-command-tray="more">
          {open ? (
            <div className={act.moreRow}>
              <button type="button" className={act.act} onClick={() => onAction({ type: "acknowledge" })} disabled={handling.status !== "new"} data-command-act="acknowledge">{t(COMMAND_ACT.acknowledge)}</button>
              {DROP_REASONS.map((reason) => (
                <button key={reason} type="button" className={act.act} onClick={() => onAction({ type: "drop", reason })} aria-label={commandDropLabel(reason, language)} data-command-act={`drop-${reason}`}>
                  <small>{t(COMMAND_ACT.dropAs)}</small><span>{t(COMMAND_DROP_REASON[reason])}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className={act.trayNote}>{t(COMMAND_ACT.closedNote)}</p>
          )}
        </div>
      )}
      <div className={act.buttons}>
        <button type="button" className={act.act} data-primary="true" onClick={() => onTray(tray === "assign" ? null : "assign")} disabled={!open} aria-expanded={tray === "assign" && open} data-command-act="assign">{t(COMMAND_ACT.assign)}</button>
        <button type="button" className={act.act} onClick={onBrief} aria-haspopup="dialog" data-command-act="brief">{t(COMMAND_ACT.brief)}</button>
        {open
          ? <button type="button" className={act.act} onClick={() => onAction({ type: "done" })} data-command-act="done">{t(COMMAND_ACT.done)}</button>
          : <button type="button" className={act.act} onClick={() => onAction({ type: "reopen" })} data-command-act="reopen">{t(COMMAND_ACT.reopen)}</button>}
        <button type="button" className={act.act} onClick={() => onTray(tray === "more" ? null : "more")} aria-expanded={tray === "more"} aria-label={t(COMMAND_ACT.more)} title={t(COMMAND_ACT.more)} data-command-act="more">
          <Ellipsis size={18} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/** The inspector of the reports saved on this device for one subdistrict. Notes stay behind a tap. */
export function CommandDeviceDetailBody({ language, tambon, reports }: { language: Language; tambon: { id: string } & Localized; reports: readonly PublicReport[] }) {
  const t = (entry: Localized) => commandText(entry, language);
  return (
    <div className={inspector.detail} data-command-device={tambon.id} lang={language}>
      <header className={styles.itemHead}>
        <p className={styles.itemKind}><span className={styles.tag} data-lane="device">{t(COMMAND_DEVICE.title)}</span></p>
        <div className={inspector.title}>
          <h3><span lang="th">{tambon.th}</span><small lang="en">{tambon.en}</small></h3>
        </div>
        {reports.length > 0 && <p className={inspector.when} data-command-device-meta>{commandDeviceMeta(reports[0].created_at, language)}</p>}
      </header>
      <section data-command-section="device-reports">
        <div className={inspector.sectionHead}><h4>{commandDeviceCount(reports.length, language)}</h4></div>
        <ul className={styles.reports}>
          {reports.map((report) => (
            <li key={report.report_id}>
              <strong>{t(COMMAND_DEVICE.depth)}: {publicReportWaterDepthLabel(report.water_depth, language)}{report.water_depth_cm === undefined ? "" : ` · ${report.water_depth_cm} ${language === "th" ? "ซม." : "cm"}`}</strong>
              <span className={inspector.source}>{formatDateWithYear(report.created_at, language)}{report.photo_attached ? ` · ${t(COMMAND_DEVICE.photo)}` : ""}</span>
              {report.notes && (
                <details>
                  <summary>{t(COMMAND_DEVICE.note)}</summary>
                  <p>{report.notes}</p>
                </details>
              )}
            </li>
          ))}
        </ul>
        <p className={inspector.source}>{t(COMMAND_DEVICE.noteRule)}</p>
      </section>
      <section data-command-section="device-rule">
        <p className={inspector.note}>{t(COMMAND_DEVICE.notSent)}</p>
        <p className={inspector.source}>{t(COMMAND_DEVICE.noPoint)}</p>
        <p className={inspector.source} data-command-device-no-actions>{t(COMMAND_ACT.deviceNoActions)}</p>
      </section>
    </div>
  );
}
