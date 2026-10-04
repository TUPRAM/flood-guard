import { describe, expect, it } from "vitest";
import { createStorySampler, sampleStory, STORY_CHAPTERS, type ChapterId } from "./sample-story";

const manifest = {
  origin: "synthetic_illustration",
  fictional_report_id: "DEMO-R017",
  fictional_task_id: "DEMO-T004",
  chapters: STORY_CHAPTERS,
};

const positionIn = (id: ChapterId, local: number) => {
  const chapter = STORY_CHAPTERS.find((entry) => entry.id === id)!;
  return chapter.start + local * (chapter.end - chapter.start);
};

describe("landing story presentation", () => {
  it("clamps invalid inputs and resolves every exact boundary to the next chapter", () => {
    for (const value of [undefined, null, "0.5", NaN, -Infinity, -8]) expect(sampleStory(value).progress).toBe(0);
    for (const value of [Infinity, 2]) expect(sampleStory(value).progress).toBe(1);
    for (const [index, chapter] of STORY_CHAPTERS.entries()) {
      expect(sampleStory(chapter.start).chapterId).toBe(chapter.id);
      if (index) expect(sampleStory(chapter.start - 1e-7).chapterId).toBe(STORY_CHAPTERS[index - 1].id);
    }
    expect(sampleStory(1).chapterProgress).toBe(1);
  });

  it("supports deterministic arbitrary seeks and reverse playback with immutable, nonoperational state", () => {
    const positions = Array.from({ length: 1001 }, (_, index) => index / 1000);
    const frames = positions.map(sampleStory);
    expect([...positions].reverse().map(sampleStory).reverse()).toEqual(frames);
    for (const frame of frames) {
      expect(frame.origin).toBe("synthetic_illustration");
      expect(frame.operationalWriteAllowed).toBe(false);
      expect(frame.currentConditionClaim).toBe(false);
      expect(frame.newModelAutoPublished).toBe(false);
      expect(Object.isFrozen(frame)).toBe(true);
      expect(Object.isFrozen(frame.camera.position)).toBe(true);
      expect(Object.values(frame.sceneWeights).reduce((total, weight) => total + weight, 0)).toBeCloseTo(1);
      expect(Object.keys(frame.sceneWeights)).toEqual(STORY_CHAPTERS.map(({ id }) => id));
      expect(frame.camera.position.every(Number.isFinite)).toBe(true);
      expect(frame.photoBasis).toBe("unverified_illustrative_concept");
      for (const amount of [frame.selectionAmount, frame.extractionAmount, frame.photoOpacity, frame.architectureAmount, frame.floodAmount]) {
        expect(amount).toBeGreaterThanOrEqual(0);
        expect(amount).toBeLessThanOrEqual(1);
      }
    }
  });

  it("keeps receipt, review, assignment and acknowledgment distinct", () => {
    expect(sampleStory(positionIn("access", 0.9)).reportStatus).toBe("none");
    expect(sampleStory(positionIn("public", 0.4)).reportStatus).toBe("sample_draft");
    expect(sampleStory(positionIn("public", 0.8)).reportStatus).toBe("sample_received");
    expect(sampleStory(positionIn("command", 0.3)).reportStatus).toBe("sample_under_review");
    expect(sampleStory(positionIn("command", 0.6)).reportStatus).toBe("sample_task_assigned");
    expect(sampleStory(positionIn("command", 0.9)).reportStatus).toBe("sample_task_acknowledged");
    expect(sampleStory(positionIn("shared", 0.5)).taskId).toBe("DEMO-T004");
  });

  it("keeps workflow status tied to semantic chapter timing when chapter ranges change", () => {
    const chapters = STORY_CHAPTERS.map((chapter, index) => ({ ...chapter, start: index / 8, end: (index + 1) / 8 }));
    const sample = createStorySampler({ ...manifest, chapters });
    expect(sample((4 + 0.8) / 8).reportStatus).toBe("sample_received");
    expect(sample((5 + 0.3) / 8).reportStatus).toBe("sample_under_review");
    expect(sample((5 + 0.6) / 8).reportStatus).toBe("sample_task_assigned");
  });

  it("reveals one neighborhood before flooding it without a camera reset", () => {
    expect(sampleStory(0)).toMatchObject({ beat: "photo-context", photoOpacity: 1, architectureAmount: 0, floodAmount: 0 });
    expect(sampleStory(positionIn("place", 0.25))).toMatchObject({ beat: "neighborhood-selection", selectionAmount: 1, photoOpacity: 1 });
    expect(sampleStory(positionIn("place", 0.5)).beat).toBe("neighborhood-extraction");
    const dry = sampleStory(positionIn("dry", 0.5));
    expect(dry).toMatchObject({ extractionAmount: 1, photoOpacity: 0, architectureAmount: 1, floodAmount: 0, routeState: "open" });
    for (const local of [0, 0.2, 0.5, 0.9, 0.999]) {
      expect(sampleStory(positionIn("flood", local)).camera).toEqual(dry.camera);
    }
    expect(sampleStory(positionIn("access", 0.5)).camera).toEqual(dry.camera);
  });

  it("pulls back during extraction without orbiting or changing the dry comparison camera", () => {
    const frames = Array.from({ length: 51 }, (_, index) => sampleStory(positionIn("place", index / 50)));
    const dry = sampleStory(positionIn("dry", 0.5));
    expect(frames[0].camera.span).toBeLessThan(dry.camera.span);
    frames.forEach((frame, index) => {
      expect(frame.camera.position).toEqual(dry.camera.position);
      expect(frame.camera.target).toEqual(dry.camera.target);
      if (index) expect(frame.camera.span).toBeGreaterThanOrEqual(frames[index - 1].camera.span);
    });
    expect(frames.at(-1)!.camera).toEqual(dry.camera);
  });

  it("raises the flood monotonically and never restores dry geometry during the solutions or closing", () => {
    const floodFrames = Array.from({ length: 101 }, (_, index) => sampleStory(positionIn("flood", index / 100)));
    floodFrames.forEach((frame, index) => {
      if (index) expect(frame.floodAmount).toBeGreaterThanOrEqual(floodFrames[index - 1].floodAmount);
    });
    for (const id of ["access", "public", "command", "studio", "shared"] as const) {
      for (const local of [0, 0.5, 0.999]) expect(sampleStory(positionIn(id, local))).toMatchObject({ floodAmount: 1, routeState: "disrupted" });
    }
    expect(sampleStory(1).floodAmount).toBe(1);
  });

  it("keeps camera poses continuous across chapter boundaries", () => {
    for (const chapter of STORY_CHAPTERS.slice(1)) {
      const before = sampleStory(chapter.start - 1e-8).camera;
      const after = sampleStory(chapter.start).camera;
      expect(before.span).toBeCloseTo(after.span, 5);
      before.position.forEach((position, index) => expect(position).toBeCloseTo(after.position[index], 5));
      before.target.forEach((position, index) => expect(position).toBeCloseTo(after.target[index], 5));
    }
  });

  it("rejects operational, duplicate, incomplete or discontinuous manifests", () => {
    expect(() => createStorySampler({})).toThrow(TypeError);
    expect(() => createStorySampler({ ...manifest, origin: "observed" })).toThrow(TypeError);
    expect(() => createStorySampler({ ...manifest, fictional_report_id: "real-123" })).toThrow(TypeError);
    expect(() => createStorySampler({ ...manifest, chapters: [...STORY_CHAPTERS, STORY_CHAPTERS[0]] })).toThrow();
    expect(() => createStorySampler({ ...manifest, chapters: STORY_CHAPTERS.map((chapter, index) => index === 1 ? { ...chapter, id: "unknown" } : chapter) })).toThrow(TypeError);
    expect(() => createStorySampler({ ...manifest, chapters: STORY_CHAPTERS.map((chapter, index) => index === 2 ? { ...chapter, start: 0.34 } : chapter) })).toThrow(RangeError);
    expect(() => createStorySampler({ ...manifest, chapters: STORY_CHAPTERS.map((chapter, index) => index === 5 ? { ...chapter, end: 0.99 } : chapter) })).toThrow(RangeError);
  });

  it("snapshots the source manifest so later input mutations cannot change playback", () => {
    const editable = { ...manifest, chapters: STORY_CHAPTERS.map((chapter) => ({ ...chapter, end: Number(chapter.end) })) };
    const sample = createStorySampler(editable);
    editable.chapters[0].end = 0.8;
    expect(sample(0.2).chapterId).toBe("dry");
  });
});
