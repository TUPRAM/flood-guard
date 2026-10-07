/**
 * The record a reviewer hands over from the validation-check page. The text format is read by
 * `src/floodguard/validation_records.py` (`parse_record`); keep the two in step.
 */

export const RECORD_HEADER = "floodguard-validation-record v1";
export const DECISIONS = ["accept", "change", "reject"] as const;
export type Choice = (typeof DECISIONS)[number];
export const NOTE_MAX_CHARS = 300;
export const ISSUE_LABEL = "validation-check";
export const DRAFT_STORAGE_KEY = "floodguard.validation-check.v1";

export type DraftEntry = { decision?: Choice; note: string };
export type Draft = { reviewer: string; entries: Record<string, DraftEntry> };

export type ItemEvidence = { label: string; path?: string; href?: string };
export type CheckItem = {
  id: string;
  group: string;
  title: string;
  check: string;
  evidence: ItemEvidence[];
  gates: string;
  ready: boolean;
  added: string;
};

export type ReviewerWord = { decision: Choice; note: string; received_at: string; record_id: string } | null;
export type ItemStatus = "accepted" | "changes_asked" | "waiting" | "evidence_not_ready";
export type ItemState = { status: ItemStatus; accepted_by: string[]; by_reviewer: Record<string, ReviewerWord> };

/** One line, no column separator, at most the length the importer keeps. */
export function cleanNote(note: string): string {
  return note.replace(/\|/g, "/").split(/\s+/).filter(Boolean).join(" ").slice(0, NOTE_MAX_CHARS);
}

/** The decisions of a draft that can be handed over, in the order of the item list. */
export function decided(draft: Draft, items: readonly CheckItem[]): { id: string; decision: Choice; note: string }[] {
  return items
    .filter((item) => item.ready && draft.entries[item.id]?.decision)
    .map((item) => ({ id: item.id, decision: draft.entries[item.id].decision as Choice, note: cleanNote(draft.entries[item.id].note ?? "") }));
}

/** Items whose decision is not "accept" and has no note: the importer refuses such a record. */
export function missingNotes(draft: Draft, items: readonly CheckItem[]): string[] {
  return decided(draft, items).filter((entry) => entry.decision !== "accept" && !entry.note).map((entry) => entry.id);
}

/** The text of the record. `recordedAt` is an ISO 8601 time in UTC. */
export function buildRecordText(draft: Draft, items: readonly CheckItem[], recordedAt: string): string {
  const lines = [RECORD_HEADER, `reviewer: ${draft.reviewer}`, `recorded_at: ${recordedAt}`];
  for (const entry of decided(draft, items)) {
    lines.push(`${entry.id}: ${entry.decision}${entry.note ? ` | ${entry.note}` : ""}`);
  }
  return `${lines.join("\n")}\n`;
}

/** A new-issue address on GitHub with the record as its body. The reviewer still presses "Submit" there. */
export function issueUrl(repository: string, reviewer: string, recordText: string, day: string): string {
  const parameters = new URLSearchParams({
    labels: ISSUE_LABEL,
    title: `Validation check: ${reviewer}, ${day}`,
    body: `\`\`\`\n${recordText}\`\`\`\n`,
  });
  return `${repository}/issues/new?${parameters.toString()}`;
}

/** Where a piece of evidence opens: a page of this site, or the file on the default branch of the repository. */
export function evidenceHref(repository: string, evidence: ItemEvidence): string {
  return evidence.href ?? `${repository}/blob/master/${evidence.path}`;
}

/** Read a stored draft; anything that is not a draft gives an empty one. */
export function parseDraft(raw: string | null, reviewers: readonly string[]): Draft {
  const empty: Draft = { reviewer: "", entries: {} };
  if (!raw) return empty;
  try {
    const value = JSON.parse(raw) as Partial<Draft>;
    const reviewer = typeof value.reviewer === "string" && reviewers.includes(value.reviewer) ? value.reviewer : "";
    const entries: Record<string, DraftEntry> = {};
    for (const [id, entry] of Object.entries(value.entries ?? {})) {
      if (!entry || typeof entry !== "object") continue;
      const decision = (DECISIONS as readonly string[]).includes(String(entry.decision)) ? (entry.decision as Choice) : undefined;
      entries[id] = { decision, note: typeof entry.note === "string" ? entry.note.slice(0, NOTE_MAX_CHARS) : "" };
    }
    return { reviewer, entries };
  } catch {
    return empty;
  }
}
