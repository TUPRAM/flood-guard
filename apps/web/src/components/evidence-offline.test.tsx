import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { evidenceFixtures } from "@/lib/evidence-library.fixtures";
import { evidenceActivity, type EvidenceActivity, type EvidenceAreaStatus } from "@/lib/evidence-offline";

import { EvidenceLibrary } from "./evidence-library";
import { EvidenceOfflineControl, EvidencePackageNotice } from "./evidence-offline";

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return { ...react, useState: vi.fn(react.useState) };
});

// The control reads the saves and removals of the page view from the library module: a test sets what it reads.
vi.mock("@/lib/evidence-offline", async (importOriginal) => {
  const library = await importOriginal<typeof import("@/lib/evidence-offline")>();
  return { ...library, evidenceActivity: vi.fn(library.evidenceActivity) };
});

/** Render the control with the worker's answer already in its state, and the page view's saves and removals. */
function control(areas: EvidenceAreaStatus[] | null, options: { th?: boolean; list?: boolean } & Partial<EvidenceActivity> = {}) {
  const { catalog } = evidenceFixtures();
  vi.mocked(useState).mockReturnValueOnce([areas, vi.fn()]);
  vi.mocked(evidenceActivity).mockReturnValue({ busy: options.busy ?? {}, failed: options.failed ?? {}, interrupted: options.interrupted ?? {} });
  return renderToStaticMarkup(<EvidenceOfflineControl catalog={catalog} aoiId="test-aoi" th={options.th ?? false} list={options.list ?? false} />);
}
const area = (state: EvidenceAreaStatus["state"], cached: number, bytes = 9_278_000): EvidenceAreaStatus => ({ aoiId: "test-aoi", state, cached, failed: 0, total: 3, bytes });

describe("study areas saved for offline use", () => {
  beforeEach(() => { vi.mocked(useState).mockReset(); });

  it("shows nothing until the worker has answered", () => {
    expect(control(null)).toBe("");
  });

  it("offers to save an area that is not saved, with its size, and no removal", () => {
    const html = control([area("none", 0)]);
    expect(html).toContain('data-evidence-offline-area="test-aoi" data-state="none"');
    expect(html).toContain("Not saved on this device. It opens only with a connection.");
    expect(html).toContain('data-action="save"');
    expect(html).toMatch(/<button type="button" data-action="save">Save this area for offline use \(9\.3 MB\)<\/button>/);
    expect(html).not.toContain('data-action="remove"');
    expect(html).toContain("The database files offered for download are not saved and need a connection.");
    expect(html).not.toContain("data-evidence-offline-list");
    // The rule for saving is stated once, under the row: on open up to 20 MB, on request above, never after a removal.
    expect(html).toContain("A study area up to 20 MB is saved on this device when you open it while connected; a larger one is saved when you ask.");
    expect(html).toContain("A copy you remove is not saved again until you ask.");
    // This area is small enough to be saved on open, so nothing says that it waits for a request.
    expect(html).not.toContain("saved only when you ask");
  });

  it("says that an area larger than 20 MB is saved only on request", () => {
    const html = control([area("none", 0, 51_296_688)]);
    expect(html).toContain("This area is larger than 20 MB, so it is saved only when you ask.");
    expect(html).toMatch(/<button type="button" data-action="save">Save this area for offline use \(51 MB\)<\/button>/);
    // Once it is saved the sentence goes.
    expect(control([area("saved", 3, 51_296_688)])).not.toContain("saved only when you ask");
    expect(control([area("none", 0, 51_296_688)], { th: true })).toContain("พื้นที่นี้ใหญ่กว่า 20 MB จึงบันทึกเฉพาะเมื่อคุณสั่ง");
  });

  it("says that a saved area was checked file by file and lets the reader remove it", () => {
    const html = control([area("saved", 3)]);
    expect(html).toContain('data-state="saved"');
    expect(html).toContain("Saved on this device: 3 files, 9.3 MB. Each file matched its SHA-256.");
    expect(html).toContain('data-action="remove"');
    expect(html).toContain("Remove saved copy");
    expect(html).not.toContain('data-action="save"');
  });

  it("does not call an incomplete copy saved, and reports files that failed their check", () => {
    const html = control([area("partial", 2)], { failed: { "test-aoi": 1 } });
    expect(html).toContain('data-state="partial"');
    expect(html).toContain("Saved copy incomplete or out of date: 2 of 3 files. It does not open offline yet.");
    expect(html).toContain("1 of 3 files could not be downloaded or did not match their SHA-256, and were not saved.");
    expect(html).toContain('data-action="save"');
    expect(html).toContain('data-action="remove"');
    expect(html).not.toContain("Each file matched");
  });

  it("disables both buttons while a save is running", () => {
    const html = control([area("partial", 1)], { busy: { "test-aoi": "saving" } });
    expect(html).toContain('data-state="saving"');
    expect(html).toContain("Saving and checking each file…");
    expect(html.match(/disabled=""/g)).toHaveLength(2);
    expect(html).not.toContain("data-interrupted");
  });

  it("says when a save was interrupted, with the buttons free again", () => {
    // The worker stopped before it answered: the row is not left on "Saving…" with its button disabled.
    const html = control([area("partial", 1)], { interrupted: { "test-aoi": "saving" } });
    expect(html).toContain('data-state="partial" data-interrupted="saving"');
    expect(html).toContain("The save stopped before it finished. Files that passed their check are kept. Try again while connected.");
    expect(html).not.toContain("Saving and checking each file…");
    expect(html).toContain('data-action="save"');
    expect(html).not.toContain('disabled=""');
    expect(control([area("none", 0)], { interrupted: { "test-aoi": "saving" }, th: true })).toContain("การบันทึกหยุดก่อนเสร็จสิ้น");
    expect(control([area("saved", 3)], { interrupted: { "test-aoi": "removing" } })).toContain("The removal stopped before it finished. Try again.");
  });

  it("lists every study area in the library list, each with its own request", () => {
    const html = control([area("saved", 3)], { list: true });
    expect(html).toContain('data-evidence-offline-list="true"');
    expect(html).toContain("All study areas: 1 of 1 saved on this device");
    expect(html).toContain("<strong>Synthetic test area</strong>");
    expect(html).toContain('aria-label="Remove the saved copy of Synthetic test area"');
    expect(html.match(/data-evidence-offline-area="test-aoi"/g)).toHaveLength(2);
  });

  it("is written in Thai as well", () => {
    const html = control([area("none", 0)], { th: true, list: true });
    expect(html).toContain("บันทึกพื้นที่นี้ไว้ใช้แบบออฟไลน์ (9.3 MB)");
    expect(html).toContain("ยังไม่ได้บันทึกไว้ในอุปกรณ์นี้");
    expect(html).toContain("พื้นที่ศึกษาทั้งหมด: บันทึกไว้ในอุปกรณ์นี้ 0 จาก 1 พื้นที่");
    expect(html).not.toMatch(/Save this area|Not saved on this device/);
  });
});

describe("a package that is not shown", () => {
  beforeEach(() => { vi.mocked(useState).mockReset(); });

  it("says plainly that the device is offline and the area is not saved, in both languages", () => {
    const offline = { kind: "offline_not_saved" as const, message: "" };
    const en = renderToStaticMarkup(<EvidencePackageNotice failure={offline} th={false} invalidLabel="Evidence package unavailable" />);
    expect(en).toContain('role="alert"');
    expect(en).toContain('data-evidence-unavailable="offline_not_saved"');
    expect(en).toContain("You are offline, and this study area is not saved on this device, so none of its data is shown.");
    expect(en).toContain("Opening it while connected saves it on this device; an area larger than 20 MB is saved when you choose “Save this area for offline use”.");
    expect(en).not.toContain("Evidence package unavailable");
    const th = renderToStaticMarkup(<EvidencePackageNotice failure={offline} th invalidLabel="ชุดข้อมูลใช้ไม่ได้" />);
    expect(th).toContain("ขณะนี้ออฟไลน์ และยังไม่ได้บันทึกพื้นที่ศึกษานี้ไว้ในอุปกรณ์");
    expect(th).toContain("“บันทึกพื้นที่นี้ไว้ใช้แบบออฟไลน์”");
    const brief = renderToStaticMarkup(<EvidencePackageNotice failure={offline} th={false} invalidLabel="x" brief />);
    expect(brief).toContain('role="status"');
    expect(brief).toContain("Not shown: you are offline, and this study area is not saved on this device.");
  });

  it("keeps a failed check apart from a missing connection", () => {
    const invalid = renderToStaticMarkup(<EvidencePackageNotice failure={{ kind: "invalid", message: "Evidence package checksum does not match the catalog." }} th={false} invalidLabel="Evidence package unavailable" />);
    expect(invalid).toBe('<p role="alert">Evidence package unavailable: Evidence package checksum does not match the catalog.</p>');
    const unreachable = renderToStaticMarkup(<EvidencePackageNotice failure={{ kind: "unreachable", message: "" }} th={false} invalidLabel="x" />);
    expect(unreachable).toContain('data-evidence-unavailable="unreachable"');
    expect(unreachable).toContain("could not be reached, and it is not saved on this device");
  });

  it("offers a download only for files a connection or the saved copy can answer", () => {
    const { catalog, evidence } = evidenceFixtures();
    evidence.downloads = [{ title: "Synthetic database", url: "/evidence-library/context.json.gz", sha256: "a".repeat(64) }];
    // The static page and the first render assume a connection: both links are offered.
    const html = renderToStaticMarkup(<EvidenceLibrary initialCatalog={catalog} initialPackage={evidence} />);
    expect(html).toContain('href="/evidence-library/test-report.md" download=""');
    expect(html).toContain('href="/evidence-library/context.json.gz" download=""');
    expect(html).not.toContain("data-evidence-download-offline");
  });
});
