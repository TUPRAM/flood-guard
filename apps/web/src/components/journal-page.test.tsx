import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  JOURNAL_CHECKED, JOURNAL_DATA, JOURNAL_GROUPS, JOURNAL_REPOSITORY, JOURNAL_ROUTE, JOURNAL_SOFTWARE, JOURNAL_THAI_SOURCES,
} from "@/lib/journal";
import { POLICY_GOVERNMENT_SOURCES, POLICY_READING } from "@/lib/policy-brief";
import { JournalPage } from "./journal-page";

const plain = (markup: string) => markup.replace(/<[^>]*>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, " ");
const unescape = (markup: string) => markup.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
const THAI = /[฀-๿]/;
const REPOSITORY_ROOT = resolve(process.cwd(), "..", "..");

describe("reference list page", () => {
  const html = renderToStaticMarkup(<JournalPage />);
  const text = plain(html);
  const entries = JOURNAL_GROUPS.flatMap((group) => group.items);

  it("has one title, a section and a chapter link for each group, then Thai law, data and software", () => {
    expect(JOURNAL_ROUTE).toBe("/journal/");
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    const ids = [...JOURNAL_GROUPS.map((group) => group.id), "thai-law", "data", "software"];
    const positions = ids.map((id) => html.indexOf(`<section id="${id}"`));
    positions.forEach((position, index) => expect(position, ids[index]).toBeGreaterThan(index === 0 ? 0 : positions[index - 1]));
    for (const id of ids) expect(html).toContain(`href="#${id}"`);
    const levels = [...html.matchAll(/<h([1-6])\b/g)].map((match) => Number(match[1]));
    levels.forEach((level, index) => {
      if (index > 0) expect(level - levels[index - 1], `heading ${index}`).toBeLessThanOrEqual(1);
    });
  });

  it("lists every paper of the policy page, so the two lists cannot drift apart", () => {
    const ids = entries.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const item of POLICY_READING.flatMap((group) => group.items)) {
      const found = entries.find((entry) => entry.id === item.id);
      expect(found, item.id).toBeDefined();
      expect(found!.reference).toBe(item.reference);
      expect(found!.checked).toBe(JOURNAL_CHECKED.policy);
    }
    expect(JOURNAL_THAI_SOURCES).toBe(POLICY_GOVERNMENT_SOURCES);
    expect(entries.filter((item) => item.checked === JOURNAL_CHECKED.methods).length).toBeGreaterThanOrEqual(20);
  });

  it("links every reference over https, once, and says in both languages what we take from it", () => {
    const urls = [...entries, ...JOURNAL_DATA, ...JOURNAL_SOFTWARE].map((item) => item.url);
    expect(new Set(urls).size).toBe(urls.length);
    const markup = unescape(html);
    for (const url of urls) {
      expect(url).toMatch(/^https:\/\/[a-z0-9.-]+\//);
      expect(markup).toContain(`href="${url}"`);
    }
    for (const item of [...entries, ...JOURNAL_DATA, ...JOURNAL_SOFTWARE]) {
      expect(item.use.en.length, item.id).toBeGreaterThan(10);
      expect(item.use.th, item.id).toMatch(THAI);
      expect(text, item.id).toContain(item.use.en);
    }
    // A method paper is linked by its DOI, or by its arXiv record when it has none.
    for (const item of entries.filter((entry) => entry.checked === JOURNAL_CHECKED.methods)) {
      expect(item.url, item.id).toMatch(/^https:\/\/(doi\.org\/10\.\d{4,}\/|arxiv\.org\/abs\/\d{4}\.\d{4,5}$)/);
    }
  });

  it("points each method at a file that exists in the repository", () => {
    for (const item of entries.filter((entry) => entry.code)) {
      expect(existsSync(resolve(REPOSITORY_ROOT, item.code!)), item.code).toBe(true);
      expect(html).toContain(`href="${JOURNAL_REPOSITORY}${item.code}"`);
    }
  });

  it("numbers the papers straight through and states what was and was not checked", () => {
    const numbers = [...html.matchAll(/aria-hidden="true">(\d+)<\/span>/g)].map((match) => Number(match[1]));
    expect(numbers).toEqual(entries.map((_, index) => index + 1));
    expect(text).toContain(`${entries.length} `);
    expect(text).toContain("We read the record of each paper (authors, year, venue, DOI) on 12 Oct 2026 or 28 Oct 2026, not always its full text.");
    expect(text).toContain("none endorses FloodGuard and none validates the score");
    expect(text).toContain("planning support, not an official warning");
    expect(text).toContain("has not been reviewed by a native speaker");
    expect(text).not.toMatch(/real-time|live warning|flood forecast|we warn/i);
  });

  it("writes a Thai sentence for every English one", () => {
    for (const file of ["src/lib/journal.ts", "src/components/journal-page.tsx"]) {
      const source = readFileSync(resolve(process.cwd(), file), "utf8");
      expect(source.match(/\ben: "/g)?.length ?? 0, file).toBe(source.match(/\bth: "/g)?.length ?? 0);
    }
  });
});
