"use client";

/**
 * The brief sheet of the Command exercise replay: the short text a coordinator hands to a team in an exercise, and the
 * situation brief of one replay hour.
 *
 * A brief is exercise text. Its first and its last line are the exercise tag; it is written in Thai unless the reader
 * asks for English; it holds no rain value, no note of a report and no statement of a place record. The page sends
 * nothing: Share hands the text to the device's own share sheet where the browser has one, Copy puts it on the
 * clipboard, and the message link opens the device's message app with the two-line version and no recipient, so an
 * exercise brief cannot go to a hotline by a slip.
 */

import { Copy, MessageSquare, Share2, X } from "lucide-react";
import { useId, useRef, useState, useSyncExternalStore } from "react";

import type { Language, Localized } from "@/lib/flood-timeline";
import { COMMAND_BRIEF, commandBriefLineCount, commandBriefTitle, commandSmsCount } from "@/lib/flood-timeline-command-act-copy";
import { BRIEF_DEFAULT_LANGUAGE, BRIEF_TAG, BRIEF_TAG_SHORT, SMS_MAX_CHARS, smsHref, smsParts } from "@/lib/flood-timeline-command-brief";
import { COMMAND_DRAWER, commandText } from "@/lib/flood-timeline-command-copy";

import act from "./mae-sai-command-act.module.css";
import { ModalDialog } from "./mae-sai-command-chrome";
import exercise from "./mae-sai-command-exercise.module.css";

/** What the sheet shows: the brief of one invented item, or the situation brief. */
export interface CommandBriefContent {
  /** "EX-05" for the brief of an item; null for the situation brief. */
  itemId: string | null;
  /** The lines of the brief in each language; the exercise tag is the first and the last of them. */
  lines: Record<Language, readonly string[]>;
  /** The text-message version in each language; null where the brief has none (the situation brief). */
  sms: Record<Language, string> | null;
}

/** What the reader did with a brief, for the exercise log: the brief itself is never stored. */
export type CommandBriefEvent = "brief_shared" | "brief_copied" | "brief_sms";

const BRIEF_LANGUAGES: readonly Language[] = ["th", "en"];
const noSubscription = () => () => undefined;
/** Whether this browser has a share sheet of its own; a page rendered on the server has none. */
const useCanShare = (): boolean => useSyncExternalStore(noSubscription, () => typeof navigator !== "undefined" && typeof navigator.share === "function", () => false);

/** A line of a brief with its exercise tag set apart, at its start or at its end, so the tag reads as a tag. */
function BriefLine({ line, tag }: { line: string; tag: string }) {
  if (line.startsWith(tag)) return <><span className={act.briefTag}>{tag}</span>{line.slice(tag.length)}</>;
  if (line.endsWith(tag)) return <>{line.slice(0, -tag.length)}<span className={act.briefTag}>{tag}</span></>;
  return <>{line}</>;
}

function BriefBody({ content, language, onEvent }: { content: CommandBriefContent; language: Language; onEvent?: (event: CommandBriefEvent, briefLanguage: Language) => void }) {
  const t = (entry: Localized) => commandText(entry, language);
  const [briefLanguage, setBriefLanguage] = useState<Language>(BRIEF_DEFAULT_LANGUAGE);
  const [status, setStatus] = useState<"copied" | "failed" | null>(null);
  const canShare = useCanShare();
  const text = useRef<HTMLPreElement | null>(null);
  const lines = content.lines[briefLanguage];
  const whole = lines.join("\n");
  const sms = content.sms?.[briefLanguage] ?? null;
  const count = sms ? smsParts(sms) : null;

  const share = async () => {
    try {
      await navigator.share({ text: whole });
      onEvent?.("brief_shared", briefLanguage);
    } catch {
      // The reader closed the share sheet: nothing was handed over, and nothing is logged.
    }
  };
  const copy = async () => {
    let done = false;
    try {
      await navigator.clipboard.writeText(whole);
      done = true;
    } catch {
      // Without the clipboard permission the text is selected, so the reader's own copy key takes it.
      const node = text.current;
      const selection = window.getSelection();
      if (node && selection) {
        const range = document.createRange();
        range.selectNodeContents(node);
        selection.removeAllRanges();
        selection.addRange(range);
        node.focus();
      }
    }
    setStatus(done ? "copied" : "failed");
    if (done) onEvent?.("brief_copied", briefLanguage);
  };

  return (
    <div className={`${act.sheetBody} ${act.briefSheet}`} data-command-brief={content.itemId ?? "situation"} data-brief-language={briefLanguage}>
      <div className={act.lead}>
        <div className={act.segments} role="group" aria-label={t(COMMAND_BRIEF.language)}>
          {BRIEF_LANGUAGES.map((id) => (
            <button key={id} type="button" aria-pressed={id === briefLanguage} onClick={() => { setBriefLanguage(id); setStatus(null); }} data-command-brief-language={id}>
              <span lang={id}>{id === "th" ? "ไทย" : "English"}</span>
            </button>
          ))}
        </div>
        <span className={act.hint}>{commandBriefLineCount(lines.length, language)}</span>
      </div>
      <pre ref={text} className={act.briefText} lang={briefLanguage} tabIndex={0} aria-label={t(COMMAND_BRIEF.text)} data-command-brief-text>
        {lines.map((line, index) => (
          <span key={`${index}:${line}`}><BriefLine line={line} tag={BRIEF_TAG[briefLanguage]} />{index < lines.length - 1 ? "\n" : ""}</span>
        ))}
      </pre>
      <div className={act.buttonRow}>
        {canShare && (
          <button type="button" className={act.primaryButton} onClick={share} data-command-brief-share><Share2 size={16} aria-hidden="true" />{t(COMMAND_BRIEF.share)}</button>
        )}
        <button type="button" className={canShare ? act.secondaryButton : act.primaryButton} onClick={copy} data-command-brief-copy><Copy size={16} aria-hidden="true" />{t(COMMAND_BRIEF.copy)}</button>
        <span className={act.status} role="status" data-command-brief-status>{status === "copied" ? t(COMMAND_BRIEF.copied) : status === "failed" ? t(COMMAND_BRIEF.copyFailed) : ""}</span>
      </div>
      {sms && count && (
        <section className={act.field} data-command-brief-sms>
          <h3 className={act.fieldTitle} lang={language}>{t(COMMAND_BRIEF.smsTitle)}</h3>
          <pre className={act.briefText} lang={briefLanguage} tabIndex={0} aria-label={t(COMMAND_BRIEF.smsTitle)} data-command-sms-text>
            {sms.split("\n").map((line, index, all) => (
              <span key={`${index}:${line}`}><BriefLine line={line} tag={BRIEF_TAG_SHORT[briefLanguage]} />{index < all.length - 1 ? "\n" : ""}</span>
            ))}
          </pre>
          <div className={act.briefMeta}>
            {/* The link names no recipient: the reader types the number in the message app. */}
            <a className={act.secondaryButton} href={smsHref(sms)} onClick={() => onEvent?.("brief_sms", briefLanguage)} data-command-sms>
              <MessageSquare size={16} aria-hidden="true" />{t(COMMAND_BRIEF.smsOpen)}
            </a>
            <div>
              <strong data-command-sms-count>{commandSmsCount(count.characters, SMS_MAX_CHARS, count.parts, language)}</strong>
              <span>{t(COMMAND_BRIEF.smsNoRecipient)}</span>
            </div>
          </div>
        </section>
      )}
      <div className={act.briefNotes} lang={language}>
        <p>{t(COMMAND_BRIEF.rule)}</p>
        <p>{t(COMMAND_BRIEF.sends)}</p>
      </div>
    </div>
  );
}

/** The brief sheet. It opens in Thai each time, whatever the language of the page. */
export function CommandBriefSheet({ open, onClose, language, content, onEvent }: {
  open: boolean;
  onClose: () => void;
  language: Language;
  /** The brief to show; null while there is none (the sheet is then closed). */
  content: CommandBriefContent | null;
  onEvent?: (event: CommandBriefEvent, briefLanguage: Language) => void;
}) {
  const title = useId();
  const t = (entry: Localized) => commandText(entry, language);
  return (
    <ModalDialog open={open && content !== null} onClose={onClose} className={`${exercise.sheet} ${act.sheetWide}`} labelledBy={title} language={language} name="brief">
      <div className={exercise.dialogHead}>
        <h2 id={title}>{commandBriefTitle(content?.itemId ?? null, language)}</h2>
        <button type="button" className={exercise.closeButton} onClick={onClose} aria-label={t(COMMAND_DRAWER.close)}><X size={20} aria-hidden="true" /></button>
      </div>
      {/* A new brief starts in Thai again: the body is keyed by what it shows. */}
      {content && <BriefBody key={`${content.itemId ?? "situation"}:${open ? "open" : "closed"}`} content={content} language={language} onEvent={onEvent} />}
    </ModalDialog>
  );
}
