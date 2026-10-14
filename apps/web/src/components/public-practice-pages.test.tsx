import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { parseTimelineManifest, TIMELINE_MANIFEST_URL, type GeoCollection, type LineGeometry, type RoadProps } from "@/lib/flood-timeline";
import { EXERCISE_FILE_URL, parseExerciseFile } from "@/lib/flood-timeline-command-incidents";
import { parseAccessNodes } from "@/lib/flood-timeline-evacuation";
import { createEmptyHouseholdPlan } from "@/lib/household-plan";
import { practiceView, type PracticeReplay, type PracticeView } from "@/lib/public-practice";
import { practiceScenario, type PracticeState } from "@/lib/public-practice-scenarios";
import { EMPTY_SHELTER_TRIP } from "@/lib/public-shelter-view";
import type { FeatureCollection } from "@/lib/types";

import { PublicPracticeStrip } from "./public-practice-strip";
import { PublicReportPage } from "./public-report-page";
import { PublicShelterPage } from "./public-shelter-page";
import { PublicSosPage } from "./public-sos-page";

// The scenarios are read from the published replay files themselves (revision r5) and the file of invented items.
const publicRoot = resolve(import.meta.dirname, "../../public");
const readPublic = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = parseTimelineManifest(JSON.parse(readPublic(TIMELINE_MANIFEST_URL).toString("utf8")));
const replay: PracticeReplay = {
  manifest,
  roads: JSON.parse(readPublic(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<LineGeometry, RoadProps>,
  nodes: parseAccessNodes(new Uint8Array(readPublic(manifest.access!.nodes.href)), manifest.access!),
};
const exercise = parseExerciseFile(JSON.parse(readPublic(EXERCISE_FILE_URL).toString("utf8")));
const view = (id: PracticeState, language: "en" | "th" = "en"): PracticeView => practiceView(replay, exercise.items, practiceScenario(id)!, language)!;

const emptyFeatures: FeatureCollection = { type: "FeatureCollection", name: "empty", features: [] };
const noLayers = () => () => {};

describe("the practice scenario from page to page", () => {
  it("carries the sentence and the tone of the Home banner on a page without a map, and says what the replay is not", () => {
    const scenario = view("cut_off");
    const html = renderToStaticMarkup(
      <PublicPracticeStrip view={scenario} prompt={scenario.pages.prepare.prompt} />,
    );
    expect(html).toContain('class="public-practice-strip" data-tone="danger"');
    expect(html).toContain(`Practice replay · ${scenario.moment}`);
    expect(html).toContain("Model · not real-time · not an official warning");
    expect(html).toContain("No shelter within walking reach");
    expect(html).toContain("Practise: what do you have upstairs for a day or more");
    // No button ends the practice (14 Oct 2026): the page leaves it when the reader looks for their own place.
    expect(html).not.toContain("<button");
  });

  it("lists on the Report page the invented items that have arrived, apart from the notes of this device", () => {
    const scenario = view("cut_off");
    const html = renderToStaticMarkup(
      <PublicReportPage language="en" areas={[]} onSelectArea={() => {}} practice={scenario} />,
    );
    expect(html).toContain("Practise: what would others need to know from this home now");
    // The form keeps working during the practice, and the strip says that what it saves is real.
    expect(html).toContain("A note you save on this page during the practice is a real note on this device.");
    expect(html).toContain(`Practice reports by this hour (${scenario.pages.report.items.length})`);
    expect(html).toContain("Invented for the exercise. Not real calls or reports, and none came from this device.");
    expect(html).toContain(scenario.pages.report.items[0].id);
    // The strip and the list stand above the form; the notes of the device keep their own section.
    expect(html.indexOf("public-practice-reports")).toBeLessThan(html.indexOf('class="public-report-form"'));
    expect(html).toContain("Reports saved on this device");
    // Without a scenario the page has neither.
    const plain = renderToStaticMarkup(<PublicReportPage language="en" areas={[]} onSelectArea={() => {}} />);
    expect(plain).not.toContain("public-practice-strip");
    expect(plain).not.toContain("public-practice-reports");
  });

  it("says on the Report page that no item has arrived on the day without water", () => {
    const html = renderToStaticMarkup(
      <PublicReportPage language="en" areas={[]} onSelectArea={() => {}} practice={view("normal")} />,
    );
    expect(html).toContain("Practice reports by this hour (0)");
    expect(html).toContain("No practice report has arrived by this hour.");
  });

  it("keeps the official numbers first on the SOS page and says that no call is placed", () => {
    const scenario = view("water_at_home");
    const html = renderToStaticMarkup(
      <PublicSosPage language="en" hotlines={[]} plan={createEmptyHouseholdPlan("")} selectedAreaName="" practice={scenario} />,
    );
    expect(html.indexOf("Official emergency hotlines")).toBeLessThan(html.indexOf("public-practice-strip"));
    expect(html.indexOf("public-practice-strip")).toBeLessThan(html.indexOf("Press and hold for 3 seconds"));
    expect(html).toContain('href="tel:1784"');
    expect(html).toContain("Water has reached this home");
    expect(html).toContain("Practise: say out loud what you would tell 1784 or 1669");
    expect(html).toContain("This is practice: no call is placed. In a real emergency, call the numbers above.");
  });

  it("shows the same hour on the Shelter map: the walk to a shelter in the banner, the replay in the note", () => {
    const shelter = (id: PracticeState) => renderToStaticMarkup(
      <PublicShelterPage
        language="en"
        selectedAreaName=""
        selectedAreaId=""
        areas={[]}
        areaFeatures={emptyFeatures}
        datasetMode="candidate"
        plan={createEmptyHouseholdPlan("")}
        onNavigatePrepare={() => {}}
        trip={EMPTY_SHELTER_TRIP}
        onTripChange={() => {}}
        practice={{ status: "ready", view: view(id), overlay: noLayers }}
      />,
    );
    const cut = shelter("cut_off");
    expect(cut).toMatch(/class="public-signal-banner" data-tone="danger"[^>]*>[\s\S]*?No shelter within walking reach/);
    const note = cut.match(/<p class="public-map-note"[\s\S]*?<\/p>/)?.[0] ?? "";
    expect(note).toContain('data-practice="true"');
    expect(note).toContain("Practice replay");
    expect(note).toContain("Model · not real-time · not an official warning");
    // The scenario without water is green on Home and grey here.
    const calm = shelter("normal");
    expect(calm).toMatch(/class="public-signal-banner" data-tone="neutral"[^>]*>[\s\S]*?A shelter reported in 2024 is within a 2 km walk/);
    expect(calm).not.toContain('data-tone="calm"');
  });

  it("keeps a destination the reader entered when they come back to the Shelter page", () => {
    const html = renderToStaticMarkup(
      <PublicShelterPage
        language="en"
        selectedAreaName=""
        selectedAreaId=""
        areas={[]}
        areaFeatures={emptyFeatures}
        datasetMode="candidate"
        plan={createEmptyHouseholdPlan("")}
        onNavigatePrepare={() => {}}
        trip={{ ...EMPTY_SHELTER_TRIP, draft: "Wat Tham Pha Chom", destination: "Wat Tham Pha Chom", authorityConfirmed: true }}
        onTripChange={() => {}}
      />,
    );
    expect(html).toContain('value="Wat Tham Pha Chom"');
    expect(html).toMatch(/class="public-signal-banner" data-tone="easing"[^>]*>[\s\S]*?Destination set: Wat Tham Pha Chom/);
  });

  it("speaks Thai on every page", () => {
    const scenario = view("roads_cut", "th");
    const html = renderToStaticMarkup(
      <PublicPracticeStrip view={scenario} prompt={scenario.pages.sos.prompt} note={scenario.copy.sosReal} />,
    );
    expect(html).toContain("ฝึกซ้อมด้วยภาพจำลอง");
    expect(html).toContain("ไม่ใช่คำเตือนทางการ");
    expect(html).toContain("ถนนใกล้บ้านนี้จมน้ำ");
  });
});
