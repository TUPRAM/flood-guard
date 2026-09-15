import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  beats, geometry, openingPlateSource, pathFromPoints, plateSource, plateSrcSet, projectPoint,
  sceneAnchor, sceneFromId, scenes, story, transitionKind, type Crop, type Point,
} from "./story";

const suppliedStory = JSON.parse(readFileSync(new URL("../../../../../handoff/floodguard-landing-v1/data/story.json", import.meta.url), "utf8"));
const neighborhoodManifest = JSON.parse(readFileSync(new URL("../../../public/landing/floodguard-v2/scene-manifest.json", import.meta.url), "utf8"));
const sceneIds = ["H-01", "S1-01", "S2-01", "S3A-01", "S3B-OBS", "S3B-01", "S4-01", "S4-PUBLIC", "S4-END"];
const distance = ([ax, ay]: Point, [bx, by]: Point) => Math.hypot(bx - ax, by - ay);
const length = (points: readonly Point[]) => points.slice(1).reduce((sum, point, index) => sum + distance(points[index], point), 0);

describe("the supplied landing story contract", () => {
  it("retains every supplied narrative beat and its exact qualifications", () => {
    expect(scenes.map((scene) => scene.id)).toEqual(sceneIds);
    expect(story).toEqual(suppliedStory);
    expect(beats.map((scene) => scene.id)).toEqual(sceneIds.slice(1));
    for (const scene of scenes) expect(sceneFromId(scene.id)).toBe(scene);
    for (const invalid of [null, "", "S3B", "s3b-obs", "S5-01"]) expect(sceneFromId(invalid)).toBeUndefined();
  });

  it("keeps observations and household/closing steps inside four named chapters", () => {
    expect(story.chapters.map(({ id, firstScene }) => [id, firstScene])).toEqual([
      ["01", "S1-01"], ["02", "S2-01"], ["03", "S3A-01"], ["04", "S4-01"],
    ]);
    const destinations = beats.map(sceneAnchor);
    expect(new Set(destinations).size).toBe(beats.length);
    for (const chapter of story.chapters) {
      const first = sceneFromId(chapter.firstScene)!;
      expect(first.chapter).toBe(chapter.id);
      expect(sceneAnchor(first)).toBe(chapter.anchor);
      expect(chapter.label.length).toBeGreaterThan(8);
    }
    for (const [id, chapter] of [["S3B-OBS", "03"], ["S3B-01", "03"], ["S4-PUBLIC", "04"], ["S4-END", "04"]]) {
      const scene = sceneFromId(id)!;
      expect(scene.chapter).toBe(chapter);
      expect(sceneAnchor(scene)).toBe(`scene-${id.toLowerCase()}`);
    }
  });

  it("shows the consequence before evidence selection and keeps unverified reports qualified", () => {
    expect(sceneFromId("S3A-01")).toMatchObject({ character: "resident", route: "affected", card: null, report: false, selection: false });
    expect(sceneFromId("S3B-OBS")).toMatchObject({ character: "resident", route: "affected", card: "observation", report: true, selection: false });
    expect(sceneFromId("S3B-01")).toMatchObject({ character: "planner", route: "affected", card: "analysis", report: true, selection: true });
    expect(sceneFromId("S4-01")).toMatchObject({ character: "planner", card: "brief", selection: true });
    expect(sceneFromId("S4-PUBLIC")).toMatchObject({ character: "resident", card: "public", selection: false, report: false });
    expect(sceneFromId("S4-END")).toMatchObject({ character: null, waterState: "W2", route: "affected", card: "brief" });
    expect(story.cards.observation.status).toBe("Not verified.");
    expect(story.cards.observation.interactionScope).toContain("No report is submitted.");
    expect(story.cards.analysis.rows.find((row) => row.label === "Local input")?.value).toContain("Not verified");
    expect(story.cards.brief.rows.find((row) => row.label === "Still unknown")?.value).toBe("Clinic operating status.");
  });

  it("stops physical water progression at W2 through every remaining planning step", () => {
    expect(scenes.map((scene) => scene.waterState)).toEqual(["W0", "W0", "W1", "W2", "W2", "W2", "W2", "W2", "W2"]);
    const floodedScenes = scenes.slice(3);
    expect(new Set(floodedScenes.map((scene) => plateSource(scene.waterState))).size).toBe(1);
    expect(new Set(floodedScenes.map((scene) => plateSrcSet(scene.waterState))).size).toBe(1);
    for (const scene of scenes) {
      expect(plateSource(scene.waterState)).toBe(neighborhoodManifest.closeStates[scene.waterState]);
      expect(plateSource(scene.waterState)).toMatch(/^\/landing\/floodguard-v2\/plates\/w[012]\.webp$/);
      expect(plateSrcSet(scene.waterState)).toBe(`${plateSource(scene.waterState)} ${neighborhoodManifest.width}w`);
    }
    for (let index = 1; index < floodedScenes.length; index++) {
      expect(transitionKind(floodedScenes[index - 1], floodedScenes[index], false)).toBe("overlay-only");
      expect(transitionKind(floodedScenes[index], floodedScenes[index - 1], false)).toBe("overlay-only");
    }
    expect(transitionKind(scenes[1], scenes[2], false)).toBe("fade-through-paper");
    expect(transitionKind(scenes[3], scenes[2], false)).toBe("fade-through-paper");
    expect(transitionKind(scenes[0], scenes[0], false)).toBe("none");
    for (const from of scenes) for (const to of scenes) expect(transitionKind(from, to, true)).toBe("instant");
  });

  it("uses the first drone image for the opening and rejects unknown physical states", () => {
    expect(openingPlateSource).toBe(neighborhoodManifest.cameraFrames[0].src);
    expect(openingPlateSource).not.toBe(plateSource("W0"));
    for (const state of ["W3", "w0", "", "toString"]) {
      expect(() => plateSource(state)).toThrow(RangeError);
      expect(() => plateSrcSet(state)).toThrow(RangeError);
    }
  });
});

describe("registered illustration geometry", () => {
  const route = geometry.route.map(([x, y]) => [x, y] as const);
  const { startIndex, endIndex } = geometry.affectedSegment;

  it("joins the household gate to the clinic entrance inside the native art", () => {
    expect(geometry.nativeSize).toEqual({ width: neighborhoodManifest.width, height: neighborhoodManifest.height });
    expect(geometry.nativeSize.width / geometry.nativeSize.height).toBeCloseTo(4 / 3);
    expect(route).toEqual(neighborhoodManifest.anchors.route);
    expect(geometry.points.homeGate).toEqual(neighborhoodManifest.anchors.home);
    expect(geometry.points.clinicEntrance).toEqual(neighborhoodManifest.anchors.clinic);
    expect(route[0]).toEqual(geometry.points.homeGate);
    expect(route.at(-1)).toEqual(geometry.points.clinicEntrance);
    for (const point of [...route, ...Object.values(geometry.points), ...Object.values(geometry.labelAnchors)]) {
      expect(point.every(Number.isFinite)).toBe(true);
      expect(point[0]).toBeGreaterThanOrEqual(0);
      expect(point[0]).toBeLessThanOrEqual(geometry.nativeSize.width);
      expect(point[1]).toBeGreaterThanOrEqual(0);
      expect(point[1]).toBeLessThanOrEqual(geometry.nativeSize.height);
    }
    for (const state of Object.values(geometry.byState)) {
      expect(state.homeGate).toEqual(route[0]);
      expect(state.clinicEntrance).toEqual(route.at(-1));
    }
  });

  it("retains both dry endpoints and the affected center in each registered crop", () => {
    for (const crop of Object.values(geometry.viewports)) {
      expect(crop).toEqual([0, 0, geometry.nativeSize.width, geometry.nativeSize.height]);
      for (const point of [geometry.points.homeGate, geometry.points.clinicEntrance, geometry.points.affectedCenter]) {
        const projected = projectPoint(point as unknown as Point, crop as unknown as Crop);
        expect(projected.every((coordinate) => coordinate >= 0 && coordinate <= 1)).toBe(true);
      }
    }
    expect(geometry.waterBoundaryPath).toBeNull();
    expect(geometry.selectedAreaMeaning).toMatch(/Narrative selection only/);
    expect(geometry.selectedAreaMeaning).toMatch(/not a flood extent/);
  });

  it("uses the modeled affected span while preserving both dry approach segments", () => {
    expect([startIndex, endIndex]).toEqual(neighborhoodManifest.anchors.affected);
    expect(Number.isInteger(startIndex) && Number.isInteger(endIndex)).toBe(true);
    expect(startIndex).toBeGreaterThan(0);
    expect(endIndex).toBeGreaterThan(startIndex);
    expect(endIndex).toBeLessThan(route.length - 1);
    const affected = route.slice(startIndex, endIndex + 1);
    expect(length(affected) / length(route)).toBeGreaterThan(.2);
    expect(length(route.slice(0, startIndex + 1))).toBeGreaterThan(0);
    expect(length(route.slice(endIndex))).toBeGreaterThan(0);
  });

  it("uses the crop origin and extent consistently without hiding clipped coordinates", () => {
    expect(projectPoint([300, 190], [300, 190, 1190, 830])).toEqual([0, 0]);
    expect(projectPoint([1490, 1020], [300, 190, 1190, 830])).toEqual([1, 1]);
    expect(projectPoint([150, 75], [50, 25, 200, 100])).toEqual([.5, .5]);
    expect(projectPoint([0, 0], [50, 25, 200, 100])).toEqual([-.25, -.25]);
  });

  it("rejects unusable route points or crop dimensions before producing SVG geometry", () => {
    expect(pathFromPoints([[2, 3], [7, 11]])).toBe("M 2 3 L 7 11");
    for (const points of [[], [[1, 2]], [[1, 2], [NaN, 3]], [[1, 2], [3, Infinity]]]) {
      expect(() => pathFromPoints(points as unknown as Point[])).toThrow(RangeError);
    }
    for (const crop of [[0, 0, 0, 10], [0, 0, 10, -1], [0, NaN, 10, 10], [0, 0, Infinity, 10]]) {
      expect(() => projectPoint([1, 2], crop as unknown as Crop)).toThrow(RangeError);
    }
    expect(() => projectPoint([NaN, 2], [0, 0, 10, 10])).toThrow(RangeError);
  });
});
