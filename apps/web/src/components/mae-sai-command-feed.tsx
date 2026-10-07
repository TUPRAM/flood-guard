"use client";

/**
 * "Known by now" of the Command exercise replay (Mae Sai, September 2024): what had been reported or observed by the
 * replay hour, what is only model, and what is missing. The rows come from `knownBy(t)`; this file lays them out.
 *
 * Its first lines never change with the hour: no public hourly river-level record for the Sai was found, and how the
 * model reads at the points of the place records known by now. Then the rows, newest first, grouped by day: a lane
 * tag, a headline, the time the data gives and how long before the replay hour that is, the places (a place with a
 * point moves the map) and the source. Once the reader has scrolled, new rows do not move the list: a button offers
 * to jump to the newest. The list is a reconstruction of a 2024 event; nothing in it is a message of today.
 */

import { ArrowUp, MapPin } from "lucide-react";
import { useRef, useState } from "react";

import type { Language, Localized, ReportedDepths } from "@/lib/flood-timeline";
import { COMMAND_INSPECTOR, commandLaneTag, commandText } from "@/lib/flood-timeline-command-copy";
import { COMMAND_MODES, groupFeedByDay, type CommandFeedItem, type CommandFeedPlace, type CommandMode, type PlaceRecordTally } from "@/lib/flood-timeline-command-feed";
import {
  COMMAND_FEED,
  COMMAND_MODE,
  commandFeedAge,
  commandFeedGroupTitle,
  commandFeedHeadline,
  commandFeedJump,
  commandFeedNote,
  commandFeedTime,
  commandModeLine,
  commandRecordTallyLine,
} from "@/lib/flood-timeline-command-reports-copy";
import { localizedText } from "@/lib/flood-timeline-copy";

import styles from "./mae-sai-command-feed.module.css";

/** The switch between the two modes as two buttons: what the exercise shows of the future. */
export function CommandModeSegments({ language, mode, onMode }: { language: Language; mode: CommandMode; onMode: (mode: CommandMode) => void }) {
  const t = (entry: Localized) => commandText(entry, language);
  return (
    <div className={styles.segments} role="group" aria-label={t(COMMAND_MODE.label)} data-command-mode={mode}>
      {COMMAND_MODES.map((id) => (
        <button key={id} type="button" aria-pressed={id === mode} onClick={() => onMode(id)} title={t(id === "trainee" ? COMMAND_MODE.traineeMeaning : COMMAND_MODE.hindsightMeaning)} data-mode={id}>
          {t(id === "trainee" ? COMMAND_MODE.trainee : COMMAND_MODE.hindsight)}
        </button>
      ))}
    </div>
  );
}

/** The same switch as one line of the time dock: "Trainee mode · the future is hidden". */
export function CommandModeSwitch({ language, mode, onMode }: { language: Language; mode: CommandMode; onMode: (mode: CommandMode) => void }) {
  const t = (entry: Localized) => commandText(entry, language);
  const hindsight = mode === "hindsight";
  return (
    <button type="button" className={styles.modeSwitch} aria-pressed={!hindsight} aria-label={t(COMMAND_MODE.switchLabel)} onClick={() => onMode(hindsight ? "trainee" : "hindsight")}
      title={t(hindsight ? COMMAND_MODE.hindsightMeaning : COMMAND_MODE.traineeMeaning)} data-command-mode-switch={mode} lang={language}>
      <i aria-hidden="true" />
      <span>{commandModeLine(mode, language)}</span>
    </button>
  );
}

function FeedRow({ item, hour, depths, language, onPlace }: {
  item: CommandFeedItem;
  hour: number;
  depths: Pick<ReportedDepths, "depth_classes"> | null;
  language: Language;
  onPlace: (place: CommandFeedPlace) => void;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  const note = commandFeedNote(item, language);
  const age = commandFeedAge(item, hour, language);
  const later = item.time !== null && item.fromHour > hour;
  const envelope = item.detail.kind === "season_envelope" ? item.detail : null;
  const sentence = envelope ? localizedText(envelope.sentence, language) : null;
  const located = item.places.filter((place) => place.lat !== null && place.lon !== null);
  return (
    <li className={styles.row} data-feed-item={item.id} data-lane={item.lane} data-later={later ? "true" : "false"}>
      <p className={styles.headline}>
        <span className={styles.tag} data-lane={item.lane}>{commandLaneTag(item.lane, language)}</span>
        {commandFeedHeadline(item, depths, language)}
        {note && <span className={styles.rowNote}> {note}</span>}
        {envelope && sentence && (
          <span className={styles.rowNote}> <span lang={sentence.lang}>{sentence.text}</span> {t(COMMAND_FEED.credit)}: <span lang="en">{envelope.credit}</span>{language === "th" ? "" : "."}</span>
        )}
      </p>
      <p className={styles.meta}>
        <time>{commandFeedTime(item, language)}</time>
        {age && <span>{age}</span>}
        {item.source && (
          <span><a className={styles.sourceLink} href={item.source.href} target="_blank" rel="noopener noreferrer">{item.source.publisher}</a></span>
        )}
      </p>
      {/* A place with a point is a link that moves the map; a place without one is named in the headline only. */}
      {located.length > 0 && (
        <div className={styles.places}>
          {located.map((place, index) => (
            <button key={`${place.en}-${index}`} type="button" className={styles.placeLink} onClick={() => onPlace(place)} title={t(COMMAND_FEED.showOnMap)} data-feed-place>
              <MapPin size={11} strokeWidth={2.2} aria-hidden="true" />
              <span lang={language}>{language === "th" ? place.th : place.en}</span>
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

export interface CommandFeedProps {
  language: Language;
  /** Whole replay hour, 0 … 264. */
  hour: number;
  mode: CommandMode;
  onMode: (mode: CommandMode) => void;
  /** The rows the mode shows at this hour, newest first; null until the replay data has loaded. */
  items: readonly CommandFeedItem[] | null;
  /** How the model reads at the points of the place records the mode shows. */
  tally: PlaceRecordTally | null;
  depths: Pick<ReportedDepths, "depth_classes"> | null;
  /** A place link was chosen: the map shows the place. */
  onPlace: (place: CommandFeedPlace) => void;
}

/** The body of the "Known by now" tab: the fixed lines, then the rows in a list that scrolls on its own. */
export function MaeSaiCommandFeed({ language, hour, mode, onMode, items, tally, depths, onPlace }: CommandFeedProps) {
  const t = (entry: Localized) => commandText(entry, language);
  const list = useRef<HTMLDivElement | null>(null);
  // The rows that were in the list when the reader left its top; null while the list is at its top.
  const [away, setAway] = useState<ReadonlySet<string> | null>(null);
  const rows = items ?? [];
  const pending = away ? rows.filter((item) => !away.has(item.id)).length : 0;
  const onScroll = () => {
    const top = (list.current?.scrollTop ?? 0) < 8;
    if (top) setAway(null);
    else if (away === null) setAway(new Set(rows.map((item) => item.id)));
  };
  const jump = () => {
    list.current?.scrollTo({ top: 0 });
    setAway(null);
  };
  const groups = groupFeedByDay(rows);
  return (
    <div className={styles.feed} lang={language} data-command-known={mode} data-rows={rows.length}>
      <div className={styles.feedHead}>
        <div className={styles.mode}>
          <span className={styles.modeText}>{commandModeLine(mode, language)}</span>
          <CommandModeSegments language={language} mode={mode} onMode={onMode} />
        </div>
        <p className={styles.fixedLine} data-feed-fixed="missing">
          <span className={styles.tag} data-lane="missing">{t(COMMAND_FEED.missingTag)}</span>
          <span>{t(COMMAND_FEED.missing)}</span>
        </p>
        {tally && (
          <p className={styles.fixedLine} data-feed-fixed="records">
            <span className={styles.tag} data-lane="reported">{commandLaneTag("reported", language)}</span>
            <span>{commandRecordTallyLine(tally, language)}</span>
          </p>
        )}
      </div>
      <div ref={list} className={styles.list} onScroll={onScroll} tabIndex={0} role="group" aria-label={t(COMMAND_INSPECTOR.tabKnown)} data-feed-list>
        {pending > 0 && (
          <div className={styles.jump}>
            <button type="button" onClick={jump} data-feed-jump><ArrowUp size={14} aria-hidden="true" />{commandFeedJump(pending, language)}</button>
          </div>
        )}
        {rows.length === 0 ? (
          <p className={styles.empty} role="status">{t(items ? COMMAND_FEED.empty : COMMAND_INSPECTOR.knownSoon)}</p>
        ) : (
          <ol className={styles.groups}>
            {groups.map((group) => (
              <li key={group.key} className={styles.group} data-feed-group={group.key}>
                <h4>{commandFeedGroupTitle(group.key, language)}</h4>
                <ul className={styles.rows}>
                  {group.items.map((item) => <FeedRow key={item.id} item={item} hour={hour} depths={depths} language={language} onPlace={onPlace} />)}
                </ul>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
