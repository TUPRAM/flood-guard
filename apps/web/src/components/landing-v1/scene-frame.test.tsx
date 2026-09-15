import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { geometry, openingPlateSource, plateSource, sceneAnchor, sceneFromId, scenes, story } from "@/lib/landing-v1/story";
import { LandingExperience } from "./landing-experience";
import { ChapterNav, Header, SceneFrame } from "./scene-frame";

const text = (html: string) => html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
const frame = (id: string) => renderToStaticMarkup(<SceneFrame scene={sceneFromId(id)!} />);
const visibleFrame = (id: string) => frame(id).replace(/<dialog\b[\s\S]*?<\/dialog>/g, "");

describe("server-rendered landing scenes", () => {
  it("provides the complete story, one h1, and real anchor destinations before JavaScript", () => {
    const html = renderToStaticMarkup(<LandingExperience reviewEnabled={false}><section id="workspaces">Existing workspaces</section></LandingExperience>);
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toContain('<main id="main-content" lang="en"');
    expect(html).toContain('data-fg-mode="flow"');
    expect(html).toContain('href="#workspaces"');
    expect(html).not.toContain("Skip to workspaces");
    for (const scene of scenes) {
      expect(html).toContain(`data-fg-scene="${scene.id}"`);
      expect(text(html)).toContain(scene.title.replace(/\n/g, " "));
      expect(html).toContain(scene.imageDescription);
      if (scene.chapter) expect(html).toContain(`id="${sceneAnchor(scene)}"`);
    }
    for (const chapter of story.chapters) expect(html).toContain(`href="#${chapter.anchor}"`);
    expect(html).not.toContain('aria-live=');
  });

  it("renders readable landmark descriptions and reserved responsive art, not complete reference screenshots", () => {
    for (const scene of scenes) {
      const html = frame(scene.id);
      const figure = html.match(/<figure\b[\s\S]*?<\/figure>/)?.[0] ?? "";
      expect(figure).toContain(`data-fg-water="${scene.waterState}"`);
      expect(figure).toMatch(/aria-describedby="[^"]+-description"/);
      expect(figure).toContain(scene.imageDescription);
      expect(figure).not.toContain(story.illustrationCaption);
      expect(figure).toContain('data-fg-artwork="same-world-v2"');
      expect(figure).toContain('width="1536" height="1152"');
      expect(figure).toMatch(/srcSet="\/landing\/floodguard-v2\/[^\"]+ 1536w"/);
      expect(figure).toContain('--plate-ratio:1536 / 1152');
      expect(figure).toContain('--plate-width:100%');
      expect(figure).toContain('--plate-height:100%');
      if (scene.id === "H-01") {
        expect(figure).not.toContain('<svg');
        expect(figure).not.toContain(">Homes<");
        expect(figure).not.toContain(">Clinic<");
      } else {
        expect(figure).toContain(">Homes<");
        expect(figure).toContain(">Clinic<");
        expect(figure).toContain('viewBox="0 0 1536 1152" aria-hidden="true" focusable="false"');
      }
      expect(html).not.toMatch(/storyboard-original|FG_H01|FG_S|\/_next\/image/);
      expect(html).not.toContain('role="application"');
    }
  });

  it("keeps every W2 beat on the same art URL and registered crop", () => {
    const signatures = scenes.filter((scene) => scene.waterState === "W2").map((scene) => {
      const html = frame(scene.id);
      const image = [...html.matchAll(/<img\b[^>]*data-fg-plate-image[^>]*>/g)].map((match) => match[0]).find((tag) => /\ssrc=/.test(tag)) ?? "";
      return [image.match(/\ssrc="([^"]+)"/)?.[1], html.match(/data-fg-crop="([^"]+)"/)?.[1]];
    });
    expect(signatures).toHaveLength(6);
    expect(signatures[0]).toEqual([plateSource("W2"), "registered"]);
    expect(new Set(signatures.map((signature) => JSON.stringify(signature))).size).toBe(1);
  });

  it("defers later plate URLs for scripts while preserving native no-JavaScript image fallbacks", () => {
    for (const id of ["S2-01", "S3A-01", "S3B-01"]) {
      const html = frame(id);
      const scriptEnabled = html.replace(/<noscript\b[\s\S]*?<\/noscript>/g, "");
      expect(scriptEnabled).not.toMatch(/<img\b[^>]*\ssrc(?:Set)?="[^\"]*\/(?:plates|characters)\//);
      const nativeFallbacks = [...html.matchAll(/<noscript\b[^>]*>([\s\S]*?)<\/noscript>/g)].map((match) => match[1]).join("");
      expect(nativeFallbacks).toContain(plateSource(sceneFromId(id)!.waterState));
      expect(nativeFallbacks).toContain('width="1536" height="1152"');
      expect(nativeFallbacks).toContain("1536w");
    }
    const eagerHero = renderToStaticMarkup(<SceneFrame scene={scenes[0]} eager />);
    expect(eagerHero).toContain(`src="${openingPlateSource}"`);
    expect(eagerHero).toContain('fetchPriority="high"');
  });

  it("keeps the hero and closing portrait-free and gives all other beats grounded portrait sources", () => {
    for (const id of ["H-01", "S4-END"]) expect(frame(id)).not.toContain("/characters/");
    for (const scene of scenes.filter((item) => item.character)) {
      expect(frame(scene.id)).toContain(`/characters/${scene.character}-800.webp`);
      const portrait = frame(scene.id).match(/<img\b[^>]*width="1374"[^>]*>/)?.[0] ?? "";
      expect(portrait).toContain('height="1145"');
      expect(portrait).toContain('alt=""');
    }
    for (const href of ["/command/", "/public/", "/studio/"]) expect(frame("S4-END")).toContain(`href="${href}"`);
    expect(frame("H-01")).not.toContain('href="/command/"');
    expect(frame("H-01")).not.toContain('href="#story-everyday"');
    expect(frame("H-01")).not.toContain(story.status);
    expect(frame("H-01")).not.toContain(story.scenes[0].eyebrow);
  });

  it("reveals the affected connection before adding the local report or analytical selection", () => {
    const consequence = visibleFrame("S3A-01");
    expect(consequence).toContain("Affected connection");
    expect(consequence.match(/Outside the illustrated flood/g)).toHaveLength(2);
    expect(consequence).toContain(story.scenes[3].question);
    expect(consequence).not.toContain("DEMO-R01");
    expect(consequence).not.toContain("ILLUSTRATIVE ACCESS FINDING");
    expect(consequence).not.toContain("Selected for review");
    const observation = visibleFrame("S3B-OBS");
    expect(observation).toContain("DEMO-R01");
    expect(observation).toContain("Not verified");
    expect(observation).not.toContain("Selected for review");
    const analysis = visibleFrame("S3B-01");
    expect(analysis).toContain("Selected for review");
    expect(analysis).toContain(geometry.selectedAreaMeaning);
    for (const row of story.cards.analysis.rows) {
      expect(analysis).toContain(`<dt>${row.label}</dt>`);
      expect(analysis).toContain(`<dd>${row.value}</dd>`);
    }
  });

  it("makes the observation an explicitly local, unverified explanation with a named dismissible dialog", () => {
    const html = frame("S3B-OBS");
    expect(html).toMatch(/<button[^>]+aria-label="Inspect sample observation DEMO-R01"/);
    expect(html).toContain(story.cards.observation.interactionLabel);
    expect(html).toContain(`<noscript><p>${story.cards.observation.interactionScope}</p></noscript>`);
    const dialog = html.match(/<dialog\b[\s\S]*?<\/dialog>/)?.[0] ?? "";
    const labelledBy = dialog.match(/aria-labelledby="([^"]+)"/)?.[1];
    expect(labelledBy).toBeTruthy();
    expect(dialog).toContain(`id="${labelledBy}"`);
    expect(dialog).toContain('aria-label="Close sample observation"');
    expect(dialog).toContain('<form method="dialog">');
    expect(dialog).toContain("Local example only. No report is submitted.");
    expect(dialog).toContain("Not verified.");
    expect(html).not.toMatch(/<form[^>]+(?:method="post"|action=)|type="file"/i);
  });

  it("keeps the finding readable without map interaction and exposes a native no-JS review brief", () => {
    const analysis = visibleFrame("S3B-01");
    expect(analysis).toContain(story.cards.analysis.title);
    expect(analysis).toContain(story.cards.analysis.body);
    for (const id of ["S4-01", "S4-END"]) {
      const html = visibleFrame(id);
      const details = html.match(/<details\b[\s\S]*?<\/details>/)?.[0] ?? "";
      expect(details).toMatch(/<summary>/);
      expect(details).toContain(story.cards.brief.actionLabel);
      expect(details).toContain(story.cards.brief.details);
      expect(html).toContain("Still unknown");
      expect(html).toContain("Clinic operating status.");
      expect(html).not.toContain('download=');
    }
  });
});

describe("chapter and motion controls", () => {
  it("keeps four named chapter links current across microstates and gives every next step a real destination", () => {
    for (const scene of scenes.slice(1)) {
      const html = renderToStaticMarkup(<ChapterNav scene={scene} />);
      const chapters = html.match(/<ol>[\s\S]*?<\/ol>/)?.[0] ?? "";
      expect(chapters.match(/<li>/g)).toHaveLength(4);
      expect(chapters.match(/aria-current="step"/g)).toHaveLength(1);
      const active = story.chapters.find((chapter) => chapter.id === scene.chapter)!;
      expect(chapters).toContain(`href="#${active.anchor}" aria-current="step"`);
      for (const chapter of story.chapters) expect(chapters).toContain(chapter.label);
      const index = scenes.indexOf(scene);
      if (index < scenes.length - 1) expect(html).toContain(`href="#${sceneAnchor(scenes[index + 1])}" aria-label="Next story step"`);
      else expect(html).toContain('href="#workspaces"');
      expect(html).toContain('aria-label="Previous story step"');
    }
  });

  it("keeps deterministic review links separate from production chapter anchors", () => {
    const html = renderToStaticMarkup(<ChapterNav scene={sceneFromId("S3B-OBS")!} review />);
    expect(html).toContain('href="?fgReview=S3A-01&amp;fgStill=1"');
    expect(html).toContain('href="?fgReview=S3B-01&amp;fgStill=1"');
    expect(html).toContain('href="?fgReview=S4-01&amp;fgStill=1"');
  });

  it("offers an explicit motion preference independently of primary navigation", () => {
    const html = renderToStaticMarkup(<Header motion onMotion={() => undefined} />);
    expect(html).toContain('aria-label="Main navigation"');
    expect(html).toContain('type="button" aria-pressed="true"');
    expect(html).toContain("Motion reduced");
    for (const href of ["#story-everyday", "#evidence", "#workspaces", "/command/"]) expect(html).toContain(`href="${href}"`);
    const initial = renderToStaticMarkup(<Header />);
    expect(initial).not.toContain("<button");
  });
});
