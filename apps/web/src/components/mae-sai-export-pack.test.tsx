/**
 * The export pack on the replay page: the download links in the Sources panel and the local check of the shelter
 * candidates in the plan card. The pack's files are T1 scenario tables (modelled, not observed); the check is "not
 * conducted" until a verification sheet is returned, and no test here states a result for a real site.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  formatFileSize,
  manifestAssets,
  manifestExportAssets,
  parseTimelineManifest,
  TIMELINE_MANIFEST_URL,
  type ShelterInfo,
  type ShelterVerification,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import { localizedText } from "@/lib/flood-timeline-copy";
import { findWordingViolations, visibleText } from "@/lib/replay-wording-lint";
import { checkLabel, localCheck, localCheckText, ShelterPlanCard, ShelterVerificationBlock } from "./mae-sai-evacuation-panels";
import { ExportDownloads, SourcesPanel } from "./mae-sai-flood-timeline";

const publicRoot = resolve(import.meta.dirname, "../../public");
const manifest = JSON.parse(readFileSync(resolve(publicRoot, TIMELINE_MANIFEST_URL.slice(1)), "utf8")) as TimelineManifest;
const r3 = parseTimelineManifest((JSON.parse(readFileSync(resolve(import.meta.dirname, "../lib/__fixtures__/mae-sai-timeline-r3-shape.json"), "utf8")) as { manifest: unknown }).manifest);
const pack = manifest.exports!;
const shelters = manifest.shelters!;
const sheet = pack.files.find((file) => file.id === shelters.verification!.sheet)!;
const text = (html: string) => html.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/ /g, " ");
const THAI = /[฀-๿]/;
const noop = () => undefined;
const TIER = "T1 scenario (model) replay of a reconstructed 2024 event for preparedness planning and exercises; illustrative stage keyframes; not a forecast, not an observed closure record, not an official warning; non_operational; accepted_* null";

describe("Mae Sai export pack in the manifest", () => {
  it("lists eight download files with their hashes, apart from the replay's precache set", () => {
    expect(pack.files.map((file) => file.name)).toEqual([
      "shelter_plan_reported_2024.csv", "shelter_plan_k.csv", "shelter_plan_capacitated.csv", "shelter_sites.geojson",
      "modelled_road_inundation_by_hour.csv", "modelled_access_loss_by_hour.csv", "shelter_candidate_verification_sheet.csv",
      "README_licences.txt",
    ]);
    expect(pack.file_count).toBe(pack.files.length);
    expect(pack.bytes).toBe(pack.files.reduce((sum, file) => sum + file.bytes, 0));
    for (const file of pack.files) {
      const bytes = readFileSync(resolve(publicRoot, file.href.slice(1)));
      expect(createHash("sha256").update(bytes).digest("hex"), file.name).toBe(file.sha256);
      expect(bytes.byteLength, file.name).toBe(file.bytes);
      expect(file.href).toBe(`${pack.folder}${file.name}`);
      expect(file.licence).toBe("ODbL 1.0");
      expect(file.source_ids).toContain("osm");
      // No rain gauge, no product without a licence and nothing from product 4009 feeds a download file.
      expect(file.source_ids.filter((id) => ["hii-rain", "viirs", "unosat-4009"].includes(id))).toEqual([]);
      // A modelled table is never named as a list of closure times.
      expect(file.name).not.toMatch(/schedule|closure|cut[-_]?off|4009|unosat/i);
      expect(file.title.th).toMatch(THAI);
      expect(file.title.en).not.toMatch(THAI);
      // A Buddhist-era year always carries its CE year.
      expect(file.title.th).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    }
    // The download files are not part of the precache set, and the two lists do not overlap.
    const precached = new Set(manifestAssets(manifest).map((asset) => asset.href));
    const downloads = manifestExportAssets(manifest);
    expect(downloads.map((asset) => asset.href)).toEqual(pack.files.map((file) => file.href));
    expect(downloads.filter((asset) => precached.has(asset.href))).toEqual([]);
    expect([...precached].filter((href) => href.includes("/exports/"))).toEqual([]);
    expect(manifestExportAssets(r3)).toEqual([]);
    expect(manifestExportAssets(null)).toEqual([]);
  });

  it("carries the standing tier sentence, low confidence and a source timestamp", () => {
    expect(pack.tier).toBe(TIER);
    expect(pack.scenario_tier).toBe("T1 scenario (model)");
    expect(pack.confidence).toBe("low");
    expect(pack.confidence_reason.length).toBeGreaterThan(20);
    expect(pack.source_timestamp).toContain("OSM extract");
    expect(pack.assumptions.length).toBeGreaterThanOrEqual(3);
    const block = manifest.evidence_blocks!.find((item) => item.id === "export_pack")!;
    expect([block.lane, block.evidence_tier, block.temporal_relation]).toEqual(["SCN", "T1 scenario (model)", "event_window_reconstruction"]);
    expect(block.covers).toEqual(["exports"]);
    // Only the reported-shelter table and the site layer hold reported facts; everything else is model output.
    expect(pack.files.filter((file) => file.lanes.includes("REP")).map((file) => file.id).sort()).toEqual(["readme_licences", "shelter_plan_reported_2024", "shelter_sites"]);
    expect(findWordingViolations(JSON.stringify(pack), "manifest exports")).toEqual([]);
  });

  it("writes every CSV with a byte-order mark, LF line ends and the provenance lines its record counts", () => {
    for (const file of pack.files) {
      const bytes = readFileSync(resolve(publicRoot, file.href.slice(1)));
      expect(bytes.includes(13), file.name).toBe(false);
      const bom = bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf;
      expect(bom, file.name).toBe(file.media_type === "text/csv");
      const content = bytes.toString("utf8");
      for (const needle of [TIER, "non_operational", manifest.generated_at!, "confidence_class", "source_timestamp", "assumption_1", "input_set_sha256=", "ODbL 1.0"]) {
        expect(content.includes(needle), `${file.name}: ${needle}`).toBe(true);
      }
      if (file.media_type !== "text/csv") continue;
      const lines = content.replace(/^﻿/, "").split("\n");
      expect(lines[0]).toBe(`# floodguard_export,${file.name}`);
      expect(lines[1].startsWith(`# header_lines,${file.header_lines},`)).toBe(true);
      expect(lines.slice(0, file.header_lines!).every((line) => line.startsWith("#"))).toBe(true);
      const header = lines[file.header_lines!];
      expect(header.startsWith("#")).toBe(false);
      // Every header cell is the English key, then the Thai label in brackets.
      expect(header).toMatch(/^[a-z_0-9]+ \([^,]*[฀-๿]/);
      expect(lines.length).toBe(file.header_lines! + 1 + file.rows! + 1);
      expect(findWordingViolations(lines.slice(0, file.header_lines! + 1).join("\n"), file.name)).toEqual([]);
    }
  });

  it("formats a file size in the units of a download list", () => {
    expect([0, 999, 1000, 20_985, 342_491, 999_499, 999_500, 1_234_567].map(formatFileSize)).toEqual(
      ["0 B", "999 B", "1 kB", "21 kB", "342 kB", "999 kB", "1.0 MB", "1.2 MB"]);
    expect(formatFileSize(-1)).toBe("");
    expect(formatFileSize(Number.NaN)).toBe("");
  });
});

describe("Mae Sai export pack downloads", () => {
  it("links every file with what it holds, its size and its lanes, under the standing sentence", () => {
    const html = renderToStaticMarkup(<ExportDownloads manifest={manifest} language="en" offlineCopy={null} />);
    const plain = text(html);
    expect(plain).toContain("Download the tables (for spreadsheets and GIS)");
    expect(plain).toContain("T1 scenario (model): modelled, not observed.");
    expect(plain).toContain("for preparedness planning and exercises");
    expect(plain).toContain("illustrative stage keyframes");
    expect(plain).toContain("not a forecast, not an observed closure record and not an official warning");
    expect(plain).toContain("non-operational: no priority score and no action class is computed");
    for (const file of pack.files) {
      // A same-origin link with the download attribute: the saved replay serves it without a connection.
      expect(html).toContain(`<a href="${file.href}" download="${file.name}"`);
      expect(html).toContain(`data-testid="export-${file.id}"`);
      expect(plain).toContain(file.title.en);
      expect(plain).toContain(formatFileSize(file.bytes));
    }
    expect(html).not.toMatch(/href="https?:/);
    // The link text is what the file holds; the file name is the name it is saved under, and no internal id is shown.
    expect(plain).not.toMatch(/reported_2024|(?<![A-Za-z0-9_])k(?![A-Za-z0-9_])/);
    expect(plain).toMatch(/Modelled road inundation by hour, one row per OpenStreetMap way \(modelled, not observed\)\(CSV table, \d+ kB, 3,478 rows; modelled\)/);
    expect(plain).toMatch(/GeoJSON map layer, \d+ kB, 128 points; reported facts beside a model check\)/);
    expect(plain).toMatch(/not an official register\)\(CSV table, \d+ kB, 19 rows; reported facts beside a model check\)/);
    expect(plain).toContain("under ODbL 1.0 (attribution and share-alike)");
    expect(plain).toContain("no rain values and nothing from a source without a stated licence");
    expect(plain).toContain("UTF-8 with a byte-order mark");
    const footer = text(html.slice(html.indexOf('data-testid="export-footer"')));
    expect(footer).toContain("Confidence: low");
    expect(footer).toContain(`source timestamp: ${pack.source_timestamp}`);
    expect(footer).toContain(`8 files, ${formatFileSize(pack.bytes)} in all`);
    expect(footer).toContain("Data files generated");
    expect(html).not.toContain('data-testid="export-offline"');
    expect(plain).not.toMatch(/schedule|closure plan|cut-off list/i);
    expect(findWordingViolations(visibleText(html), "ExportDownloads")).toEqual([]);
  });

  it("says the same in Thai, with the CE year beside every Buddhist-era year", () => {
    const html = renderToStaticMarkup(<ExportDownloads manifest={manifest} language="th" offlineCopy={null} />);
    const plain = text(html);
    expect(plain).toContain("ดาวน์โหลดตาราง (สำหรับโปรแกรมตารางคำนวณและ GIS)");
    expect(plain).toContain("สถานการณ์จำลองระดับ T1 (แบบจำลอง): ค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้");
    expect(plain).toContain("ไม่ใช่การพยากรณ์ ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง และไม่ใช่การเตือนภัยอย่างเป็นทางการ");
    expect(plain).toContain("ไม่ใช้ในการปฏิบัติการ");
    expect(plain).toContain("เหตุการณ์ปี 2567 (2024)");
    for (const file of pack.files) {
      expect(plain).toContain(file.title.th);
      expect(html).toContain(`download="${file.name}"`);
    }
    expect(plain).toContain("ตาราง CSV");
    expect(plain).toContain("ความเชื่อมั่น: ต่ำ");
    expect(plain).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    // The English copy does not leak into the Thai page (file names and licence names stay as they are).
    expect(plain).not.toContain("modelled, not observed");
    expect(plain).not.toContain("Download the tables");
    // The footer is Thai throughout: the pack's source timestamp has a Thai rendering like every other one on the page.
    const start = html.indexOf('data-testid="export-footer"');
    const footerHtml = html.slice(start, html.indexOf("</p>", start));
    expect(footerHtml).not.toContain('lang="en"');
    expect(text(footerHtml)).toContain("เวลาของข้อมูลต้นทาง: ข้อมูล OSM 2026-07-09 · WorldPop 2020 · รวบรวมที่พักพิงที่มีรายงานเมื่อ 2026-09-27 · จุดกำหนดระดับน้ำเพื่อการอธิบายสำหรับ 2024-09-09/2024-09-19 เวลาประเทศไทย");
    expect(text(footerHtml)).not.toContain("OSM extract");
    expect(localizedText(pack.source_timestamp, "th").lang).toBe("th");
    expect(findWordingViolations(visibleText(html), "ExportDownloads th")).toEqual([]);
  });

  it("says whether the download files are saved for offline use, apart from the replay's own data", () => {
    const saved = { cached: 22, failed: 0, total: 22, exports: { cached: 8, failed: 0, total: 8 } };
    const all = text(renderToStaticMarkup(<ExportDownloads manifest={manifest} language="en" offlineCopy={saved} />));
    expect(all).toContain("Offline copy: the 8 download files are saved on this device too, so these links work without a connection.");
    const partial = { ...saved, exports: { cached: 5, failed: 3, total: 8 } };
    expect(text(renderToStaticMarkup(<ExportDownloads manifest={manifest} language="en" offlineCopy={partial} />)))
      .toContain("Offline copy incomplete: 5 of 8 download files saved on this device.");
    expect(text(renderToStaticMarkup(<ExportDownloads manifest={manifest} language="th" offlineCopy={saved} />)))
      .toContain("สำเนาออฟไลน์: บันทึกไฟล์ดาวน์โหลด 8 ไฟล์ไว้ในอุปกรณ์แล้วเช่นกัน");
    // A worker without a pack (an older build, or none listed) says nothing.
    const none = { cached: 22, failed: 0, total: 22, exports: { cached: 0, failed: 0, total: 0 } };
    expect(renderToStaticMarkup(<ExportDownloads manifest={manifest} language="en" offlineCopy={none} />)).not.toContain('data-testid="export-offline"');
    expect(renderToStaticMarkup(<ExportDownloads manifest={manifest} language="en" offlineCopy={{ cached: 22, failed: 0, total: 22 }} />)).not.toContain('data-testid="export-offline"');
    // The replay's own offline line still counts its data files only.
    const panel = text(renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={saved} />));
    expect(panel).toContain("Offline copy: this replay's 22 data files are saved on this device");
    expect(panel).toContain("the 8 download files are saved on this device too");
  });

  it("sits in the sources panel, and a manifest without a pack shows no downloads", () => {
    const html = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />);
    expect(html).toContain('data-testid="export-files"');
    expect(html.indexOf('data-testid="licences-by-input"')).toBeLessThan(html.indexOf('data-testid="export-files"'));
    expect(renderToStaticMarkup(<ExportDownloads manifest={r3} language="en" offlineCopy={null} />)).toBe("");
    expect(renderToStaticMarkup(<SourcesPanel manifest={r3} language="en" offlineCopy={null} />)).not.toContain('data-testid="export-files"');
    expect(renderToStaticMarkup(<ExportDownloads manifest={{ ...manifest, exports: { ...pack, files: [] } }} language="en" offlineCopy={null} />)).toBe("");
  });
});

describe("Mae Sai shelter-candidate check", () => {
  const check = shelters.verification!;

  it("says the check was not conducted and states no result, with the blank sheet to download", () => {
    expect(check.status).toBe("not_conducted");
    expect(check.checked).toEqual([]);
    expect(check.counts).toBeUndefined();
    expect(check.label_template).toBe("Checked by <role> on <date>; not an official shelter register");
    expect(check.candidates_listed).toBe(shelters.candidates.filter((candidate) => candidate.eligible).length);
    expect(sheet.name).toBe("shelter_candidate_verification_sheet.csv");
    expect(sheet.rows).toBe(check.candidates_listed);
    const html = renderToStaticMarkup(<ShelterVerificationBlock shelters={shelters} sheet={sheet} language="en" />);
    const plain = text(html);
    expect(html).toContain('data-status="not_conducted"');
    expect(plain).toContain("Local check of the candidates");
    expect(plain).toContain("Not conducted. No verification sheet has been returned, so no site on this page has been checked on the ground");
    expect(plain).toContain("every capacity is an unverified estimate and every site is a candidate to verify");
    expect(plain).toContain(`lists the ${check.candidates_listed} eligible candidates`);
    expect(plain).toContain("“Checked by <role> on <date>; not an official shelter register”");
    expect(plain).toContain("no names of people, phone numbers or ID numbers");
    expect(plain).toContain("Access notes are for the project team only and are never published.");
    // No check, so no confidence chip for one, no local-check line on any site and no sentence about using it.
    expect(html).not.toContain('data-testid="verification-provenance"');
    expect(html).not.toContain('data-testid="verification-not-used"');
    expect(localCheck(shelters, shelters.plan[0].candidate_id)).toBeNull();
    expect(html).toContain(`<a href="${sheet.href}" download="${sheet.name}"`);
    expect(plain).toContain(`Download the blank sheet (CSV, ${formatFileSize(sheet.bytes)})`);
    expect(html).not.toContain('data-testid="verification-rows"');
    // No candidate is called checked, usable or verified while no sheet has come back.
    expect(plain).not.toMatch(/usable as a shelter;|Checked by (a|an|the|staff|another) /);
    expect(findWordingViolations(visibleText(html), "ShelterVerificationBlock")).toEqual([]);
    const thaiHtml = renderToStaticMarkup(<ShelterVerificationBlock shelters={shelters} sheet={sheet} language="th" />);
    const thai = text(thaiHtml);
    expect(thai).toContain("การตรวจสอบสถานที่ในพื้นที่");
    expect(thai).toContain("ยังไม่ได้ดำเนินการ ยังไม่มีแบบตรวจสอบส่งกลับมา");
    expect(thai).toContain("“ตรวจสอบโดย <บทบาท> เมื่อ <วันที่> ไม่ใช่ทะเบียนที่พักพิงทางการ”");
    expect(thai).toContain("ดาวน์โหลดแบบตรวจสอบเปล่า");
    expect(thai).not.toContain("Not conducted");
    expect(findWordingViolations(visibleText(thaiHtml), "ShelterVerificationBlock th")).toEqual([]);
  });

  it("is part of the plan card, with or without the sheet's download file", () => {
    const withSheet = renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={shelters.knee_k} onPlanK={noop} language="en" onShowCandidate={noop} verificationSheet={sheet} />);
    expect(withSheet).toContain('data-testid="shelter-verification"');
    expect(withSheet).toContain('data-testid="verification-sheet-link"');
    expect(withSheet.indexOf('data-testid="what-if-levels"')).toBeLessThan(withSheet.indexOf('data-testid="shelter-verification"'));
    const without = renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={shelters.knee_k} onPlanK={noop} language="en" onShowCandidate={noop} />);
    expect(without).toContain('data-status="not_conducted"');
    expect(without).not.toContain('data-testid="verification-sheet-link"');
    // A manifest baked before the check existed shows nothing about it.
    const older = { ...shelters, verification: undefined } as ShelterInfo;
    expect(renderToStaticMarkup(<ShelterVerificationBlock shelters={older} sheet={sheet} language="en" />)).toBe("");
  });

  it("labels every row of a returned check by role and date, never as an official register (made-up rows)", () => {
    const [first, second] = shelters.candidates.filter((candidate) => candidate.eligible);
    const returned = conductedCheck(first.id, second.id);
    const data = { ...shelters, verification: returned };
    const html = renderToStaticMarkup(<ShelterVerificationBlock shelters={data} sheet={sheet} language="en" />);
    const plain = text(html);
    expect(html).toContain('data-status="conducted"');
    expect(plain).toContain(`A local check of 2 of the ${check.candidates_listed} eligible candidates was returned (imported 20 Oct 2026).`);
    expect(plain).toContain("It is reported by role and is not an official shelter register; a candidate that is not listed below was not checked.");
    // The checker's free-text note is never shown: only that one was given.
    expect(plain).toContain("usable as a shelter; capacity 150 people; access notes were given (not published). Checked by a village head or kamnan on 9 Oct 2026; not an official shelter register.");
    expect(JSON.stringify(returned)).not.toContain("access_notes\":\"");
    expect(plain).toContain("not usable as a shelter. Checked by a DDPM officer on 10 Oct 2026; not an official shelter register.");
    expect(plain).not.toContain("Not conducted.");
    expect(html.match(/data-testid="verification-label"/g)).toHaveLength(2);
    expect(findWordingViolations(visibleText(html), "ShelterVerificationBlock conducted")).toEqual([]);
    const thaiHtml = renderToStaticMarkup(<ShelterVerificationBlock shelters={data} sheet={sheet} language="th" />);
    const thai = text(thaiHtml);
    expect(thai).toContain("ใช้เป็นที่พักพิงได้ ความจุ 150 คน");
    expect(thai).toContain("ตรวจสอบโดยผู้ใหญ่บ้านหรือกำนัน เมื่อ");
    expect(thai).toContain("ไม่ใช่ทะเบียนที่พักพิงทางการ");
    expect(thai).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    expect(findWordingViolations(visibleText(thaiHtml), "ShelterVerificationBlock conducted th")).toEqual([]);
    expect(thai).toContain("มีหมายเหตุการเข้าถึง (ไม่เผยแพร่)");
    expect(checkLabel({ checked_by_role: "site_staff", checked_on: "2026-10-09" }, "en")).toBe("Checked by staff of the site on 9 Oct 2026; not an official shelter register");
    expect(checkLabel({ checked_by_role: "project_team", checked_on: "2026-10-09" }, "th")).toContain("ตรวจสอบโดยทีมโครงการ FloodGuard เมื่อ");
    // A "conducted" status without rows is shown as not conducted: the page never states a result it does not hold.
    const empty = { ...shelters, verification: { ...returned, checked: [] } };
    expect(renderToStaticMarkup(<ShelterVerificationBlock shelters={empty} sheet={sheet} language="en" />)).toContain('data-status="not_conducted"');
  });

  it("shows a returned check with its confidence, the reason and the dates of the checks (made-up rows)", () => {
    const [first, second] = shelters.candidates.filter((candidate) => candidate.eligible);
    const data = { ...shelters, verification: conductedCheck(first.id, second.id) };
    const html = renderToStaticMarkup(<ShelterVerificationBlock shelters={data} sheet={sheet} language="en" />);
    const start = html.indexOf('data-testid="verification-provenance"');
    expect(start).toBeGreaterThan(-1);
    const note = text(html.slice(start, html.indexOf("</details>", start)));
    expect(note).toContain("CONFIDENCE: LOW");
    expect(note).toContain("One local check per site, reported by role and not audited by the project team.");
    expect(note).toContain("One checker reported each site once; the project team did not audit the answers.");
    expect(note).toContain("Source timestamp: checks dated 2026-10-09/2026-10-10.");
    // The confidence sits above the rows, so no row is read as a bare fact.
    expect(start).toBeLessThan(html.indexOf('data-testid="verification-rows"'));
    const thaiHtml = renderToStaticMarkup(<ShelterVerificationBlock shelters={data} sheet={sheet} language="th" />);
    const thaiStart = thaiHtml.indexOf('data-testid="verification-provenance"');
    const thaiNote = thaiHtml.slice(thaiStart, thaiHtml.indexOf("</details>", thaiStart));
    expect(thaiNote).not.toContain('lang="en"');
    expect(text(thaiNote)).toContain("ความเชื่อมั่น: ต่ำ");
    expect(text(thaiNote)).toContain("ตรวจสอบในพื้นที่หนึ่งครั้งต่อสถานที่ รายงานตามบทบาท และทีมโครงการไม่ได้ตรวจทาน");
    expect(text(thaiNote)).toContain("เวลาของข้อมูลต้นทาง: ตรวจสอบระหว่าง 2026-10-09 ถึง 2026-10-10");
    expect(localizedText("checks dated 2026-10-09/2026-10-09", "th")).toEqual({ text: "ตรวจสอบเมื่อ 2026-10-09", lang: "th" });
    // A manifest baked before the block carried a confidence shows the rows without the chip, never a made-up one.
    const older = { ...data, verification: { ...data.verification, confidence: undefined } };
    expect(renderToStaticMarkup(<ShelterVerificationBlock shelters={older} sheet={sheet} language="en" />)).not.toContain('data-testid="verification-provenance"');
  });

  it("says the plans do not use a returned check and marks a site reported not usable where it is still ranked (made-up rows)", () => {
    // The made-up check calls the plan's first site not usable and gives the second one a capacity.
    const k = shelters.knee_k;
    const [unusable, usable] = shelters.plan.slice(0, 2).map((entry) => entry.candidate_id);
    const data = { ...shelters, verification: conductedCheck(usable, unusable) };
    expect(localCheck(data, unusable)).toMatchObject({ usable_as_shelter: false });
    expect(localCheck(data, usable)).toMatchObject({ usable_as_shelter: true, verified_capacity: 150 });
    expect(localCheck(data, shelters.plan[2].candidate_id)).toBeNull();
    const html = renderToStaticMarkup(<ShelterPlanCard shelters={data} k={k} onPlanK={noop} language="en" onShowCandidate={noop} verificationSheet={sheet} />);
    const plain = text(html);
    const notUsed = html.slice(html.indexOf('data-testid="verification-not-used"'));
    expect(text(notUsed.slice(0, notUsed.indexOf("</p>")))).toContain(
      "The ranking, the capacity figures and the download tables above were computed without this check: a site reported not usable is still ranked, and a reported capacity does not replace the footprint estimate.");
    // In the plan list the first site still has rank 1 and its robust-core badge, with the local check beside them.
    const list = html.slice(html.indexOf('class="' + html.match(/class="([^"]*planList[^"]*)"/)![1] + '"'));
    const firstItem = list.slice(0, list.indexOf("</li>"));
    expect(firstItem).toContain('data-testid="local-check"');
    expect(firstItem).toContain('data-usable="no"');
    expect(text(firstItem)).toContain("Local check: reported not usable as a shelter. The ranking and the capacity figures do not use the check, so the site is still listed.");
    expect(text(firstItem)).toContain("Checked by a DDPM officer on 10 Oct 2026; not an official shelter register.");
    expect(plain).toContain("Local check: reported usable, capacity 150 people. The figures here still use the footprint estimate.");
    // Both the plan list and the capacity-aware list mark a checked site that they hold.
    const marks = html.match(/data-testid="local-check"/g) ?? [];
    const ranked = new Set(data.capacitated!.plan.slice(0, k).map((row) => row.candidate_id));
    expect(marks).toHaveLength(2 + [unusable, usable].filter((id) => ranked.has(id)).length);
    expect(localCheckText({ usable_as_shelter: true, verified_capacity: null }, "en")).toBe("Local check: reported usable as a shelter (no capacity given).");
    expect(localCheckText({ usable_as_shelter: false, verified_capacity: null }, "th")).toContain("ผลตรวจในพื้นที่: รายงานว่าใช้เป็นที่พักพิงไม่ได้");
    expect(findWordingViolations(visibleText(html), "ShelterPlanCard conducted")).toEqual([]);
    const thaiHtml = renderToStaticMarkup(<ShelterPlanCard shelters={data} k={k} onPlanK={noop} language="th" onShowCandidate={noop} verificationSheet={sheet} />);
    expect(text(thaiHtml)).toContain("การจัดอันดับ ตัวเลขความจุ และตารางดาวน์โหลดด้านบนคำนวณโดยไม่ได้ใช้ผลตรวจนี้");
    expect(text(thaiHtml)).toContain("ผลตรวจในพื้นที่: รายงานว่าใช้ได้ ความจุ 150 คน");
    expect(findWordingViolations(visibleText(thaiHtml), "ShelterPlanCard conducted th")).toEqual([]);
    // Without a returned check no site carries the line.
    expect(renderToStaticMarkup(<ShelterPlanCard shelters={shelters} k={k} onPlanK={noop} language="en" onShowCandidate={noop} />)).not.toContain('data-testid="local-check"');
  });
});

/** A made-up returned check of two candidates: the first usable with a capacity and a note given, the second not usable. */
function conductedCheck(usableId: string, unusableId: string): ShelterVerification {
  return {
    ...shelters.verification!, status: "conducted", statement: "A made-up check for this test.",
    confidence: "low", confidence_reason: "One local check per site, reported by role and not audited by the project team.",
    assumptions: ["Each row is what one local checker reported for one candidate; it is not an official shelter register."],
    source_timestamp: "checks dated 2026-10-09/2026-10-10", imported_on: "2026-10-20", returned_file_sha256: "a".repeat(64),
    counts: { checked: 2, usable_yes: 1, usable_no: 1, with_verified_capacity: 1 },
    checked: [
      { candidate_id: usableId, usable_as_shelter: true, verified_capacity: 150, checked_by_role: "village_leader", checked_on: "2026-10-09",
        access_notes_given: true, label: "Checked by a village head or kamnan on 2026-10-09; not an official shelter register" },
      { candidate_id: unusableId, usable_as_shelter: false, verified_capacity: null, checked_by_role: "ddpm_officer", checked_on: "2026-10-10",
        access_notes_given: false, label: "Checked by a DDPM officer on 2026-10-10; not an official shelter register" },
    ],
  };
}
