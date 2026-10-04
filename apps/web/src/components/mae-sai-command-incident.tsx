"use client";

/**
 * The inspector of a report on the map of the Command exercise replay: an invented item of the exercise, or the
 * reports saved on this device for one subdistrict.
 *
 * An invented item says that it is invented before anything else. Its urgency was set by its author from the facts
 * the item states (the rule is printed under it), never by the model. The model line is a T1 scenario value with low
 * confidence, and the current is not modelled. A report saved on this device carries the date it was saved; it is
 * outside the replay clock, it names a subdistrict and no point, and it was sent to nobody.
 */

import { formatDateWithYear, type Language, type Localized } from "@/lib/flood-timeline";
import { COMMAND_FIGURES, commandText } from "@/lib/flood-timeline-command-copy";
import { exerciseMarkerSpec, isOpenStatus, waitingHours, type ExerciseHandling, type ExerciseItem } from "@/lib/flood-timeline-command-incidents";
import {
  COMMAND_DEPTH_BAND,
  COMMAND_DEVICE,
  COMMAND_EXERCISE,
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

import exercise from "./mae-sai-command-exercise.module.css";
import styles from "./mae-sai-command-feed.module.css";
import inspector from "./mae-sai-command-inspector.module.css";
import { EXERCISE_MARKER_VIEWBOX, exerciseMarkerNodes, MarkerGlyph } from "./mae-sai-command-markers";

export interface CommandItemDetailProps {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  item: ExerciseItem;
  handling: ExerciseHandling;
  /** The subdistrict the item is in. */
  tambon: Localized | null;
  /** The modelled depth at the item's point at this replay hour (m); null outside the grid, undefined before the raster has loaded. */
  depth: number | null | undefined;
  /** The urgency rule in words, from the exercise file. */
  rule: Localized;
}

/** The inspector of one invented item. */
export function CommandItemDetailBody({ language, hour, item, handling, tambon, depth, rule }: CommandItemDetailProps) {
  const t = (entry: Localized) => commandText(entry, language);
  const open = isOpenStatus(handling.status);
  const waiting = open ? waitingHours(item, hour) : null;
  const spec = exerciseMarkerSpec(item, handling.status);
  return (
    <div className={inspector.detail} data-command-item={item.id} data-urgency={item.urgency} lang={language}>
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

      <div className={styles.urgency} data-urgency={item.urgency} data-status={handling.status}>
        <MarkerGlyph nodes={exerciseMarkerNodes(spec)} viewBox={EXERCISE_MARKER_VIEWBOX} size={28} />
        <div>
          <strong>{t(COMMAND_URGENCY[item.urgency])} · {t(COMMAND_STATUS[handling.status])}{handling.status === "assigned" && handling.callsign ? ` · ${handling.callsign}` : ""}</strong>
          {waiting !== null && <span>{commandWaitingText(waiting, language)}</span>}
        </div>
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

      <section data-command-section="model">
        <div className={inspector.sectionHead}>
          <h4>{t(COMMAND_EXERCISE.modelHere)}</h4>
          <span className={exercise.laneTag}>{t(COMMAND_FIGURES.modelTag)}</span>
        </div>
        <p className={inspector.note} data-command-model-here>{commandModelHereLine(depth, language).replace(/^[^:]+: /u, "")}</p>
      </section>

      <section data-command-section="handling">
        <div className={inspector.sectionHead}><h4>{t(COMMAND_EXERCISE.handling)}</h4></div>
        <p className={inspector.note}><b>{t(COMMAND_STATUS[handling.status])}</b></p>
        <p className={inspector.source}>{t(COMMAND_EXERCISE.actionsSoon)}</p>
      </section>

      <section data-command-section="rule">
        <div className={inspector.sectionHead}><h4>{t(COMMAND_EXERCISE.ruleTitle)}</h4></div>
        <p className={inspector.source}>{t(rule)}</p>
        <p className={inspector.source}>{t(COMMAND_EXERCISE.notReal)}</p>
      </section>
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
        <p className={inspector.source}>{t(COMMAND_EXERCISE.actionsSoon)}</p>
      </section>
    </div>
  );
}
