import { scenes, type Scene } from "./story";

export const opening = {
  camera: [0.65, 2.15],
  window: [2.15, 3.05],
  background: [3.05, 3.5],
  portrait: [3.55, 3.95],
  text: [3.85, 4.25],
} as const;

export type TimelineStop = { scene: Scene; enter: number; hold: number; leave: number };
const firstHold = opening.text[1];
let cursor: number = firstHold;
export const timelineStops: readonly TimelineStop[] = scenes.map((scene, index) => {
  if (index === 0) return { scene, enter: 0, hold: 0, leave: opening.camera[0] };
  const enter = index === 1 ? opening.background[0] : cursor;
  const hold = index === 1 ? firstHold : enter + 0.65;
  const leave = hold + Math.max(1.15, scene.weight / 75);
  cursor = leave;
  return { scene, enter, hold, leave };
});
export const timelineLength = cursor;

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const mix = (from: number, to: number, amount: number) => from + (to - from) * amount;
/** Smooth reversible interpolation; there is no timer or remembered playback direction. */
export function ramp(position: number, start: number, end: number) {
  const t = clamp((position - start) / (end - start));
  return t * t * (3 - 2 * t);
}
const water = (scene: Scene) => Number(scene.waterState.slice(1));
const flag = (scene: Scene, key: "report" | "selection") => scene[key] ? 1 : 0;
const actor = (scene: Scene, name: string) => scene.character === name ? 1 : 0;

export function timelinePosition(sceneId: string) {
  return timelineStops.find((stop) => stop.scene.id === sceneId)?.hold ?? 0;
}

/** Sample the whole story in viewport-height units, including its explicit reading holds. */
export function sampleTimeline(rawPosition: number) {
  const position = Number.isFinite(rawPosition) ? Math.max(0, Math.min(timelineLength, rawPosition)) : 0;
  let stop = timelineStops[0];
  for (const candidate of timelineStops) if (position >= candidate.enter) stop = candidate;
  const index = scenes.indexOf(stop.scene);
  const previous = scenes[Math.max(0, index - 1)];
  const entering = index > 1 && position < stop.hold;
  const transition = entering ? clamp((position - stop.enter) / (stop.hold - stop.enter)) : 1;
  const blend = ramp(transition, 0, 1);
  const scene = entering && transition < 0.5 ? previous : stop.scene;
  const textOpacity = index <= 1
    ? ramp(position, ...opening.text)
    : entering ? transition < 0.5 ? 1 - ramp(transition, 0, 0.43) : ramp(transition, 0.57, 1) : 1;
  const sameNarrative = previous.title === stop.scene.title && previous.body === stop.scene.body && previous.question === stop.scene.question;
  const portraitEntry = ramp(position, ...opening.portrait);
  const portraitOpacity = (name: string) => index <= 1 ? (name === "resident" ? portraitEntry : 0)
    : mix(actor(previous, name), actor(stop.scene, name), blend);
  const waterProgress = index <= 1 ? 0 : mix(water(previous), water(stop.scene), blend);
  const routeOpacity = ramp(position, opening.text[0], opening.text[1]);
  return {
    position,
    progress: position / timelineLength,
    scene,
    targetScene: stop.scene,
    camera: ramp(position, ...opening.camera),
    window: ramp(position, ...opening.window),
    background: ramp(position, ...opening.background),
    heroOpacity: 1 - ramp(position, 0.45, 1.15),
    textOpacity,
    narrativeOpacity: index > 1 && sameNarrative ? 1 : textOpacity,
    residentOpacity: portraitOpacity("resident"),
    plannerOpacity: portraitOpacity("planner"),
    water: waterProgress,
    routeOpacity,
    affectedOpacity: ramp(waterProgress, 1.15, 1.85),
    reportOpacity: index <= 1 ? 0 : mix(flag(previous, "report"), flag(stop.scene, "report"), blend),
    selectionOpacity: index <= 1 ? 0 : mix(flag(previous, "selection"), flag(stop.scene, "selection"), blend),
    readingHold: index === 0 ? position <= opening.camera[0] : position >= stop.hold,
    contentInteractive: textOpacity > 0.97,
  };
}

export type TimelineFrame = ReturnType<typeof sampleTimeline>;

/** Unit-sum weights preserve a rendered plate's alpha in an isolated additive cross-fade. */
export function artworkWeights(waterProgress: number, cameraBlend: number, ready: boolean) {
  if (!ready) return { poster: 1, camera: 0, next: 0, w1: 0, w2: 0 };
  const water = Math.max(0, Math.min(2, waterProgress));
  const camera = clamp(cameraBlend);
  const dry = 1 - Math.min(1, water);
  return {
    poster: 0,
    camera: dry * (1 - camera),
    next: dry * camera,
    w1: Math.max(0, 1 - Math.abs(water - 1)),
    w2: Math.max(0, water - 1),
  };
}
