"use client";

/**
 * The find-place box of the Command exercise replay, opened from the tool rail. It searches the names the replay data
 * holds and nothing else: the eight subdistricts, the shelters reported in use in 2024 and the command centre, the
 * places of the place records (news, not surveyed), the named key facilities and the named roads. The data holds no
 * list of villages or sois, and the box says so. A name without a point in the data is listed and cannot be shown.
 */

import { Building2, Diamond, LandPlot, MessageSquare, Route, Search, Star, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import type { Language, Localized } from "@/lib/flood-timeline";
import { COMMAND_FIND, commandFindCount, commandFindKindText, commandText } from "@/lib/flood-timeline-command-copy";
import { searchCommandPlaces, type CommandFindEntry, type CommandFindKind } from "@/lib/flood-timeline-command-table";

import exercise from "./mae-sai-command-exercise.module.css";
import styles from "./mae-sai-command-find.module.css";

/** How many names the box lists at once. */
export const COMMAND_FIND_LIMIT = 6;

const KIND_ICON: Record<CommandFindKind, typeof Search> = {
  tambon: LandPlot,
  shelter: Star,
  command_centre: Diamond,
  place_record: MessageSquare,
  facility: Building2,
  road: Route,
};

/** The two names of an entry in reading order: the Thai name first, the romanised name under it. */
export function findEntryNames(entry: Pick<CommandFindEntry, "th" | "en">): { first: { text: string; lang: Language }; second: { text: string; lang: Language } | null } {
  if (entry.th) return { first: { text: entry.th, lang: "th" }, second: entry.en ? { text: entry.en, lang: "en" } : null };
  return { first: { text: entry.en ?? "", lang: "en" }, second: null };
}

export function MaeSaiCommandFind({ language, index, onPick, onClose, initialQuery = "" }: {
  language: Language;
  /** The names of the replay data; empty until the data has loaded. */
  index: readonly CommandFindEntry[];
  onPick: (entry: CommandFindEntry) => void;
  onClose: () => void;
  initialQuery?: string;
}) {
  const t = (entry: Localized) => commandText(entry, language);
  const [query, setQuery] = useState(initialQuery);
  const [active, setActive] = useState(0);
  const field = useRef<HTMLInputElement | null>(null);
  const title = useId();
  const list = useId();
  const results = useMemo(() => searchCommandPlaces(index, query, COMMAND_FIND_LIMIT), [index, query]);
  const typed = query.trim() !== "";
  const current = Math.min(active, Math.max(0, results.length - 1));
  useEffect(() => {
    field.current?.focus({ preventScroll: true });
  }, []);
  const pick = (entry: CommandFindEntry | undefined) => { if (entry?.target) onPick(entry); };
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (results.length === 0) return;
      event.preventDefault();
      setActive((current + (event.key === "ArrowDown" ? 1 : results.length - 1)) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      pick(results[current]);
    }
  };
  return (
    <div className={`${exercise.panel} ${styles.find}`} role="group" aria-labelledby={title} lang={language} data-command-popover="find" data-clear-panel>
      <div className={exercise.popoverHead}>
        <h2 id={title}>{t(COMMAND_FIND.title)}</h2>
        <button type="button" className={exercise.iconButton} onClick={onClose} aria-label={t(COMMAND_FIND.close)}><X size={18} aria-hidden="true" /></button>
      </div>
      <label className={styles.field}>
        <Search size={16} aria-hidden="true" />
        <span className={exercise.srOnly}>{t(COMMAND_FIND.field)}</span>
        <input ref={field} type="search" value={query} placeholder={t(COMMAND_FIND.placeholder)} autoComplete="off" spellCheck={false} role="combobox" aria-expanded={typed && results.length > 0} aria-controls={list}
          aria-activedescendant={typed && results[current] ? `${list}-${current}` : undefined} onChange={(event) => { setQuery(event.currentTarget.value); setActive(0); }} onKeyDown={onKey} data-command-find-field />
      </label>
      <p className={exercise.srOnly} role="status">{typed ? (results.length > 0 ? commandFindCount(results.length, language) : t(COMMAND_FIND.none)) : ""}</p>
      {typed && results.length > 0 && (
        <ul id={list} className={styles.results} role="listbox" aria-label={t(COMMAND_FIND.results)}>
          {results.map((entry, position) => {
            const Icon = KIND_ICON[entry.kind];
            const names = findEntryNames(entry);
            return (
              <li key={entry.id} id={`${list}-${position}`} role="option" aria-selected={position === current} aria-disabled={entry.target ? undefined : true} data-kind={entry.kind} data-command-find-result={entry.id}
                onClick={() => pick(entry)} onPointerMove={() => { if (position !== current) setActive(position); }}>
                <Icon size={16} aria-hidden="true" />
                <span className={styles.names}>
                  <strong lang={names.first.lang}>{names.first.text}</strong>
                  {names.second && <span lang={names.second.lang}>{names.second.text}</span>}
                  <small>{commandFindKindText(entry, language)}{entry.target ? "" : ` · ${t(COMMAND_FIND.noPoint)}`}</small>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {typed && results.length === 0 && <p className={styles.hint}>{t(COMMAND_FIND.none)}</p>}
      {!typed && <p className={styles.hint}>{t(COMMAND_FIND.hint)}</p>}
    </div>
  );
}
