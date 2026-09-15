import content from "./story.json";
import { neighborhoodGeometry, neighborhoodPlateSource, neighborhoodPlateSrcSet } from "./neighborhood";
export { neighborhoodPosterSource as openingPlateSource } from "./neighborhood";

export type WaterState = "W0" | "W1" | "W2";
export type Scene = (typeof content.scenes)[number];
export type Point = readonly [number, number];
export type Crop = readonly [number, number, number, number];
export const story = content;
export const scenes = content.scenes;
export const beats = scenes.slice(1);
export const geometry = neighborhoodGeometry;
export const assetRoot = "/landing/floodguard-v1";
export const plateSizes = "(min-width: 1000px) 65vw, 100vw";

export function plateSource(state: string) {
  return neighborhoodPlateSource(state);
}

export function plateSrcSet(state: string) {
  return neighborhoodPlateSrcSet(state);
}

export function sceneAnchor(scene: Scene) {
  return story.chapters.find((chapter) => chapter.firstScene === scene.id)?.anchor ?? `scene-${scene.id.toLowerCase()}`;
}

export function sceneFromId(id: string | null | undefined) {
  return scenes.find((scene) => scene.id === id);
}

/** Pixel coordinates in the supplied illustration, never geographic road data. */
export function pathFromPoints(points: readonly Point[]) {
  if (points.length < 2 || points.some((point) => point.length !== 2 || !point.every(Number.isFinite))) {
    throw new RangeError("A route needs at least two finite illustration points.");
  }
  return points.map(([x, y], index) => `${index ? "L" : "M"} ${x} ${y}`).join(" ");
}

export function projectPoint([x, y]: Point, [cx, cy, width, height]: Crop) {
  if (![x, y, cx, cy, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
    throw new RangeError("Crop and point must be finite; dimensions must be positive.");
  }
  return [(x - cx) / width, (y - cy) / height] as const;
}

export function transitionKind(from: Scene, to: Scene, reducedMotion: boolean) {
  if (reducedMotion) return "instant";
  if (from.id === to.id) return "none";
  return from.waterState === to.waterState ? "overlay-only" : "fade-through-paper";
}
