import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import itemsFile from "@/lib/validation-check-items.json";
import stateFile from "@/lib/validation-check-records.json";
import {
  buildRecordText, cleanNote, decided, evidenceHref, issueUrl, missingNotes, parseDraft, RECORD_HEADER,
  type CheckItem, type Draft,
} from "@/lib/validation-check";

import { ValidationCheck } from "./validation-check";

const ITEMS = itemsFile.items as CheckItem[];
const READY = ITEMS.filter((item) => item.ready).map((item) => item.id);
const NOT_READY = ITEMS.filter((item) => !item.ready).map((item) => item.id);

describe("validation check: the record a reviewer hands over", () => {
  it("writes the text the Python importer reads, in the order of the list, and only for ready items", () => {
    const draft: Draft = {
      reviewer: "Putu",
      entries: {
        [READY[1]]: { decision: "change", note: "  reword the   second | sentence\n please " },
        [READY[0]]: { decision: "accept", note: "" },
        [NOT_READY[0]]: { decision: "accept", note: "" },
        [READY[2]]: { note: "a note without a decision" },
      },
    };
    expect(buildRecordText(draft, ITEMS, "2026-10-07T09:00:00Z")).toBe(
      `${RECORD_HEADER}\nreviewer: Putu\nrecorded_at: 2026-10-07T09:00:00Z\n${READY[0]}: accept\n${READY[1]}: change | reword the second / sentence please\n`,
    );
    expect(decided(draft, ITEMS).map((entry) => entry.id)).toEqual([READY[0], READY[1]]);
  });

  it("asks for a note on every decision that is not an acceptance", () => {
    const draft: Draft = { reviewer: "Callixta", entries: { [READY[0]]: { decision: "reject", note: " " }, [READY[1]]: { decision: "change", note: "why" }, [READY[2]]: { decision: "accept", note: "" } } };
    expect(missingNotes(draft, ITEMS)).toEqual([READY[0]]);
  });

  it("keeps a note on one line and within the length the importer keeps", () => {
    expect(cleanNote("a\n b |c")).toBe("a b /c");
    expect(cleanNote("x".repeat(400))).toHaveLength(300);
  });

  it("builds a new-issue address with the label and the record in a code block", () => {
    const url = new URL(issueUrl("https://github.com/TUPRAM/flood-guard", "Putu", "line one\nline two\n", "2026-10-07"));
    expect(url.origin + url.pathname).toBe("https://github.com/TUPRAM/flood-guard/issues/new");
    expect(url.searchParams.get("labels")).toBe("validation-check");
    expect(url.searchParams.get("title")).toBe("Validation check: Putu, 2026-10-07");
    expect(url.searchParams.get("body")).toBe("```\nline one\nline two\n```\n");
  });

  it("opens evidence on this site or in the repository", () => {
    expect(evidenceHref("https://github.com/o/r", { label: "x", href: "/command/" })).toBe("/command/");
    expect(evidenceHref("https://github.com/o/r", { label: "x", path: "docs/a.md" })).toBe("https://github.com/o/r/blob/master/docs/a.md");
  });

  it("reads back only a well-formed stored draft", () => {
    expect(parseDraft(null, ["Putu"])).toEqual({ reviewer: "", entries: {} });
    expect(parseDraft("not json", ["Putu"])).toEqual({ reviewer: "", entries: {} });
    expect(parseDraft(JSON.stringify({ reviewer: "Stranger", entries: { "V-01": { decision: "maybe", note: 5 }, "V-02": { decision: "accept", note: "ok" } } }), ["Putu"]))
      .toEqual({ reviewer: "", entries: { "V-01": { decision: undefined, note: "" }, "V-02": { decision: "accept", note: "ok" } } });
  });
});

describe("validation check: the page", () => {
  const html = renderToStaticMarkup(<ValidationCheck />);

  it("lists every item with its state and says what the records are not", () => {
    for (const item of ITEMS) {
      expect(html).toContain(`data-item="${item.id}"`);
      expect(html).toContain(item.title.replace(/'/g, "&#x27;"));
    }
    expect(html).toContain("not a review by an independent expert");
    expect(html).toContain("official approval or an official warning");
    expect(html).toContain("TEAM PAGE · NOT FOR THE PUBLIC");
  });

  it("offers a decision only where the evidence is ready", () => {
    for (const id of READY) expect(html).toContain(`name="decision-${id}"`);
    for (const id of NOT_READY) expect(html).not.toContain(`name="decision-${id}"`);
    expect(html.match(/The evidence is not ready/g)).toHaveLength(NOT_READY.length);
  });

  it("names the three reviewers and keeps the hand-over closed until there is a record", () => {
    for (const name of itemsFile.reviewers) expect(html).toContain(`value="${name}"`);
    expect(html).toContain("Choose your name above.");
    expect(html).toContain('aria-disabled="true"');
    expect(html).not.toContain("issues/new");
    expect(html).not.toContain('data-testid="record-text"');
  });

  it("shows no score and no class of its own beyond the wording of the items", () => {
    const outsideItems = html.replace(/<article[\s\S]*?<\/article>/g, "");
    expect(outsideItems).not.toMatch(/FPPS|class [A-E]\b/i);
  });

  it("reads a state file that covers exactly the items of the list", () => {
    expect(Object.keys(stateFile.items).sort()).toEqual(ITEMS.map((item) => item.id).sort());
    expect(stateFile.official_warning).toBe(false);
    expect(stateFile.operational_status).toBe("non_operational");
  });
});
