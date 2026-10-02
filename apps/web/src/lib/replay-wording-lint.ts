/**
 * Wording lint for the Mae Sai replay.
 *
 * The replay is a historical reconstruction and a planning scenario. Its text must not claim real-time detection, a
 * forecast, an official warning, a validation, return periods or a road schedule. The rules live in
 * `replay-wording-rules.json`, which `src/floodguard/wording_lint.py` reads too, so the web tests and the Python
 * tests apply the same patterns. No DOM access in this module; it is used by tests, not by the page.
 */

import rulesFile from "./replay-wording-rules.json";

export interface WordingRule { id: string; pattern: string; message: string; bad: string[] }
export interface WordingAllowance { id: string; pattern: string; why: string; ok: string[] }
export interface WordingRules {
  schema: string;
  allow: WordingAllowance[];
  rules: WordingRule[];
  mixed: { text: string; rules: string[] }[];
}
export interface WordingFinding {
  /** Rule id, e.g. "forecast". */
  rule: string;
  /** The text that matched. */
  match: string;
  /** The match with up to 40 characters on each side, for the failure message. */
  context: string;
  /** Where the text came from (a file, a manifest path, a component). */
  source: string;
  message: string;
}

export const REPLAY_WORDING_RULES: WordingRules = rulesFile;

const URL_PATTERN = /https?:\/\/[^\s"'<>)\]]+/g;
const compiled = new WeakMap<WordingRules, { allow: RegExp[]; rules: { rule: WordingRule; pattern: RegExp }[] }>();

function compile(rules: WordingRules) {
  let entry = compiled.get(rules);
  if (!entry) {
    entry = {
      allow: rules.allow.map((item) => new RegExp(item.pattern, "giu")),
      rules: rules.rules.map((rule) => ({ rule, pattern: new RegExp(rule.pattern, "giu") })),
    };
    compiled.set(rules, entry);
  }
  return entry;
}

/**
 * Text as the linter reads it: web addresses removed, white space collapsed, curly apostrophes made plain and every
 * hyphen-like dash (non-breaking hyphen, figure dash, en dash, minus sign) made a plain hyphen. The same steps as
 * `floodguard.wording_lint.normalise`.
 */
export function normaliseWording(text: string): string {
  return text
    .replace(URL_PATTERN, " ")
    .replace(/[‘’]/g, "'")
    .replace(/[‐‑‒–−]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

/** Findings in `text`: every banned pattern that is still there once the allowed negations are taken out. */
export function findWordingViolations(text: string, source = "", rules: WordingRules = REPLAY_WORDING_RULES): WordingFinding[] {
  const { allow, rules: banned } = compile(rules);
  let remaining = normaliseWording(text);
  // A removed negation leaves a marker, so two halves of a sentence cannot join into a new match.
  for (const pattern of allow) remaining = remaining.replace(pattern, " ∅ ");
  const findings: WordingFinding[] = [];
  for (const { rule, pattern } of banned) {
    for (const match of remaining.matchAll(pattern)) {
      const start = match.index ?? 0;
      findings.push({
        rule: rule.id,
        match: match[0],
        context: remaining.slice(Math.max(0, start - 40), start + match[0].length + 40),
        source,
        message: rule.message,
      });
    }
  }
  return findings;
}

/** One line per finding, for an assertion message. */
export function describeWordingFindings(findings: readonly WordingFinding[]): string {
  return findings.map((finding) => `[${finding.rule}] ${finding.source}: "…${finding.context}…" — ${finding.message}`).join("\n");
}

/** Reader-visible text of rendered markup: text nodes plus `aria-label`, `title`, `alt` and `placeholder` values. */
export function visibleText(html: string): string {
  const attributes = [...html.matchAll(/\s(?:aria-label|title|alt|placeholder)="([^"]*)"/g)].map((match) => match[1]);
  const body = html.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/g, " ").replace(/<[^>]+>/g, " ");
  return [body, ...attributes].join(" │ ")
    .replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/ /g, " ");
}
