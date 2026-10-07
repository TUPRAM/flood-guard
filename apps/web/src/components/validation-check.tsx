"use client";

import { useEffect, useMemo, useState } from "react";

import itemsFile from "@/lib/validation-check-items.json";
import stateFile from "@/lib/validation-check-records.json";
import {
  buildRecordText, decided, DRAFT_STORAGE_KEY, evidenceHref, issueUrl, missingNotes, NOTE_MAX_CHARS, parseDraft,
  type CheckItem, type Choice, type Draft, type ItemState, type ItemStatus,
} from "@/lib/validation-check";

import styles from "./validation-check.module.css";

const ITEMS = itemsFile.items as CheckItem[];
const REVIEWERS = itemsFile.reviewers;
const STATES = stateFile.items as unknown as Record<string, ItemState>;

const STATUS_LABEL: Record<ItemStatus, string> = {
  accepted_by_all_reviewers: "Accepted by all three",
  changes_asked: "Changes asked",
  waiting: "Waiting",
  evidence_not_ready: "Evidence not ready",
};
const CHOICE_LABEL: Record<Choice, string> = { accept: "Accept", change: "Ask for a change", reject: "Reject" };

/**
 * The team's validation check: what the three team members are asked to look at, and a way to hand their word over.
 *
 * The page keeps a draft in this browser only. A record leaves it as a GitHub issue the reviewer submits, as copied
 * text or as a file; `scripts/import_validation_records.py` takes those in and rewrites the state shown here. The
 * words recorded are the team's own, on its own work: the page says so, and that they qualify no flood map.
 */
export function ValidationCheck() {
  const [draft, setDraft] = useState<Draft>({ reviewer: "", entries: {} });
  const [loaded, setLoaded] = useState(false);
  const [stamp, setStamp] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      let stored: string | null = null;
      try {
        stored = window.localStorage.getItem(DRAFT_STORAGE_KEY);
      } catch {
        // Storage may be unavailable; the draft then lives in this page only.
      }
      setDraft(parseDraft(stored, REVIEWERS));
      setLoaded(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    const frame = window.requestAnimationFrame(() => setStamp(`${new Date().toISOString().slice(0, 19)}Z`));
    try {
      window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
    } catch {
      // The draft stays in memory.
    }
    return () => window.cancelAnimationFrame(frame);
  }, [draft, loaded]);

  const decisions = useMemo(() => decided(draft, ITEMS), [draft]);
  const withoutNote = useMemo(() => missingNotes(draft, ITEMS), [draft]);
  const recordText = draft.reviewer && decisions.length && stamp ? buildRecordText(draft, ITEMS, stamp) : "";
  const canHandOver = Boolean(recordText) && withoutNote.length === 0;

  const setEntry = (id: string, change: { decision?: Choice; note?: string }) => {
    setMessage("");
    setDraft((current) => ({
      ...current,
      entries: { ...current.entries, [id]: { ...(current.entries[id] ?? { note: "" }), ...change } },
    }));
  };
  const clearEntry = (id: string) => setDraft((current) => {
    const entries = { ...current.entries };
    delete entries[id];
    return { ...current, entries };
  });

  const copyRecord = async () => {
    try {
      await navigator.clipboard.writeText(recordText);
      setMessage("Record copied. Paste it to Putu, or into the chat of the working session.");
    } catch {
      setMessage("Copying is not available in this browser. Select the text below and copy it by hand.");
    }
  };
  const downloadRecord = () => {
    const url = URL.createObjectURL(new Blob([recordText], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `validation-record-${draft.reviewer}-${stamp.slice(0, 10)}.txt`;
    link.click();
    URL.revokeObjectURL(url);
    setMessage("Record downloaded. Send the file to Putu.");
  };

  const counts = stateFile.status_counts as Record<string, number>;
  return (
    <main id="main-content" className={styles.page} lang="en">
      <header className={styles.head}>
        <a className={styles.back} href="/studio/">← Studio</a>
        <p className={styles.eyebrow}>TEAM PAGE · NOT FOR THE PUBLIC</p>
        <h1>Validation check</h1>
        <p>What the three of us are asked to look at before a result goes on a page or into the pitch. Open the evidence, decide, and hand your record over at the foot of the page.</p>
        <p className={styles.limit}>These are the team&apos;s own words on its own work. They are not a review by an independent expert, they qualify no flood map, and nothing here is an official approval or an official warning.</p>
        <p className={styles.rule}><strong>Rule.</strong> {itemsFile.rule}</p>
        <ul className={styles.counts} aria-label="State of the list">
          {(Object.keys(STATUS_LABEL) as ItemStatus[]).map((status) => (
            <li key={status} data-status={status}><strong>{counts[status] ?? 0}</strong> {STATUS_LABEL[status]}</li>
          ))}
        </ul>
        <p className={styles.small}>Recorded state as of {stateFile.generated_at_utc} ({stateFile.records_counted} record(s) taken in). A record you hand over shows here after the next import and deploy.</p>
      </header>

      <section className={styles.who} aria-labelledby="who-title">
        <h2 id="who-title">Who is deciding?</h2>
        <div className={styles.reviewers} role="radiogroup" aria-labelledby="who-title">
          {REVIEWERS.map((name) => (
            <label key={name} className={styles.reviewer} data-checked={draft.reviewer === name}>
              <input type="radio" name="reviewer" value={name} checked={draft.reviewer === name} onChange={() => { setMessage(""); setDraft((current) => ({ ...current, reviewer: name })); }} />
              {name}
            </label>
          ))}
        </div>
        <p className={styles.small}>Your draft is kept in this browser only until you hand it over.</p>
      </section>

      {itemsFile.groups.map((group) => {
        const items = ITEMS.filter((item) => item.group === group.id);
        return (
          <section key={group.id} className={styles.group} aria-labelledby={`group-${group.id}`}>
            <h2 id={`group-${group.id}`}>{group.title}</h2>
            <p className={styles.small}>{group.note}</p>
            {items.map((item) => {
              const state = STATES[item.id];
              const entry = draft.entries[item.id];
              const needsNote = Boolean(entry?.decision && entry.decision !== "accept" && !entry.note.trim());
              return (
                <article key={item.id} className={styles.item} data-item={item.id} data-status={state.status} aria-labelledby={`title-${item.id}`}>
                  <div className={styles.itemHead}>
                    <span className={styles.itemId}>{item.id}</span>
                    <h3 id={`title-${item.id}`}>{item.title}</h3>
                    <span className={styles.status} data-status={state.status}>{STATUS_LABEL[state.status]}</span>
                  </div>
                  <p>{item.check}</p>
                  {item.evidence.length ? (
                    <ul className={styles.evidence} aria-label={`Evidence for ${item.id}`}>
                      {item.evidence.map((evidence) => (
                        <li key={evidence.label}><a href={evidenceHref(itemsFile.repository, evidence)} target="_blank" rel="noreferrer">{evidence.label} <span aria-hidden="true">↗</span></a></li>
                      ))}
                    </ul>
                  ) : null}
                  <p className={styles.gates}><strong>Unlocks:</strong> {item.gates}</p>
                  <ul className={styles.words} aria-label={`Recorded for ${item.id}`}>
                    {REVIEWERS.map((name) => {
                      const word = state.by_reviewer[name];
                      return <li key={name} data-word={word?.decision ?? "none"}>{name}: {word ? `${CHOICE_LABEL[word.decision]}${word.note ? ` (${word.note})` : ""}` : "no word yet"}</li>;
                    })}
                  </ul>
                  {item.ready ? (
                    <fieldset className={styles.decide}>
                      <legend>Your decision on {item.id}</legend>
                      <div className={styles.choices}>
                        {(Object.keys(CHOICE_LABEL) as Choice[]).map((choice) => (
                          <label key={choice} className={styles.choice} data-choice={choice} data-checked={entry?.decision === choice}>
                            <input type="radio" name={`decision-${item.id}`} value={choice} checked={entry?.decision === choice} onChange={() => setEntry(item.id, { decision: choice })} />
                            {CHOICE_LABEL[choice]}
                          </label>
                        ))}
                        {entry?.decision ? <button type="button" className={styles.clear} onClick={() => clearEntry(item.id)}>Clear</button> : null}
                      </div>
                      <label className={styles.note}>
                        <span>Note{entry?.decision && entry.decision !== "accept" ? " (needed: say what to change)" : " (optional)"}</span>
                        <input type="text" maxLength={NOTE_MAX_CHARS} value={entry?.note ?? ""} aria-invalid={needsNote} onChange={(event) => setEntry(item.id, { note: event.target.value })} />
                      </label>
                    </fieldset>
                  ) : (
                    <p className={styles.notReady}>The evidence is not ready. There is nothing to decide yet.</p>
                  )}
                </article>
              );
            })}
          </section>
        );
      })}

      <section className={styles.handOver} aria-labelledby="hand-over-title">
        <h2 id="hand-over-title">Hand over my record</h2>
        <p data-testid="hand-over-summary">
          {draft.reviewer ? `${draft.reviewer}: ` : "Choose your name above. "}
          {decisions.length} decision(s) in this record.
          {withoutNote.length ? ` Add a note to ${withoutNote.join(", ")}: a change or a rejection needs one.` : ""}
        </p>
        <div className={styles.actions}>
          {canHandOver ? (
            <a className={styles.primary} href={issueUrl(itemsFile.repository, draft.reviewer, recordText, stamp.slice(0, 10))} target="_blank" rel="noreferrer">Open a GitHub issue with my record <span aria-hidden="true">↗</span></a>
          ) : (
            <span className={styles.primary} aria-disabled="true">Open a GitHub issue with my record</span>
          )}
          <button type="button" className={styles.secondary} disabled={!canHandOver} onClick={copyRecord}>Copy the record</button>
          <button type="button" className={styles.secondary} disabled={!canHandOver} onClick={downloadRecord}>Download the record</button>
        </div>
        <p className={styles.small} role="status" aria-live="polite">{message}</p>
        <ol className={styles.how}>
          <li><strong>With a GitHub account:</strong> the first button opens a new issue with your record in it. Press &quot;Submit new issue&quot; there. It counts when it comes from the account listed for your name.</li>
          <li><strong>Without one:</strong> copy or download the record and send it to Putu.</li>
          <li>The next working session takes the records in with <code>scripts/import_validation_records.py</code>, and this page shows the new state after the next deploy. Your later record replaces your earlier word on the same item.</li>
        </ol>
        {recordText ? <pre className={styles.record} data-testid="record-text" aria-label="The record as it will be handed over">{recordText}</pre> : null}
      </section>
    </main>
  );
}
