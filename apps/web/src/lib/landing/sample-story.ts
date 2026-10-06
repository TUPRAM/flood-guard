export const STORY_CHAPTERS = [
  { id: "place", start: 0, end: 0.18, scene: "neighborhood-extraction" },
  { id: "dry", start: 0.18, end: 0.29, scene: "dry-neighborhood" },
  { id: "flood", start: 0.29, end: 0.42, scene: "flooded-neighborhood" },
  { id: "access", start: 0.42, end: 0.55, scene: "route-access" },
  { id: "public", start: 0.55, end: 0.68, scene: "resident" },
  { id: "command", start: 0.68, end: 0.8, scene: "coordinator" },
  { id: "studio", start: 0.8, end: 0.9, scene: "researcher" },
  { id: "shared", start: 0.9, end: 1, scene: "shared-world" },
] as const;

export type ChapterId = (typeof STORY_CHAPTERS)[number]["id"];
export type SceneId = (typeof STORY_CHAPTERS)[number]["scene"];
export type StoryBeat =
  | "photo-context" | "neighborhood-selection" | "neighborhood-extraction"
  | "dry-neighborhood" | "rising-flood" | "route-access"
  | "local-report" | "coordination" | "evidence-review" | "shared-context";
export type DemoPresentationStatus =
  | "none" | "sample_draft" | "sample_received" | "sample_under_review"
  | "sample_task_assigned" | "sample_task_acknowledged";
type Vec3 = readonly [number, number, number];
interface CameraPose { readonly position: Vec3; readonly target: Vec3; readonly span: number }

const NEIGHBORHOOD_CAMERA: CameraPose = { position: [14, 19, 22], target: [0, 0.2, 0], span: 21.5 };
const ROLE_CAMERA: CameraPose = { position: [11, 15, 19], target: [0, 0.25, 1], span: 20 };

/** Semantic poses share one registered neighborhood, in illustrative +Y-up units. */
export const CAMERA_BY_CHAPTER: Readonly<Record<ChapterId, CameraPose>> = {
  place: { position: [14, 19, 22], target: [0, 0.2, 0], span: 18 },
  dry: NEIGHBORHOOD_CAMERA,
  flood: NEIGHBORHOOD_CAMERA,
  access: NEIGHBORHOOD_CAMERA,
  public: ROLE_CAMERA,
  command: ROLE_CAMERA,
  studio: ROLE_CAMERA,
  shared: NEIGHBORHOOD_CAMERA,
};

export const CAMERA_FRAMES = STORY_CHAPTERS.map(({ id }) => CAMERA_BY_CHAPTER[id]);
export const OPENING_PLACE_PROGRESS = 0.28;

export interface StoryFrame {
  readonly progress: number;
  readonly chapterId: ChapterId;
  readonly chapterIndex: number;
  readonly chapterProgress: number;
  readonly phase: "entry" | "hold" | "exit";
  readonly beat: StoryBeat;
  readonly scene: SceneId;
  readonly nextScene: SceneId;
  readonly blendToNext: number;
  readonly selectionAmount: number;
  readonly extractionAmount: number;
  readonly photoOpacity: number;
  readonly architectureAmount: number;
  readonly floodAmount: number;
  readonly routeState: "open" | "disrupted";
  readonly reportId: `DEMO-${string}`;
  readonly taskId: `DEMO-${string}`;
  readonly reportStatus: DemoPresentationStatus;
  readonly origin: "synthetic_illustration";
  readonly photoBasis: "unverified_illustrative_concept";
  readonly operationalWriteAllowed: false;
  readonly currentConditionClaim: false;
  readonly newModelAutoPublished: false;
  readonly sceneWeights: Readonly<Record<ChapterId, number>>;
  readonly camera: CameraPose;
}

interface Chapter { id: ChapterId; start: number; end: number; scene: SceneId }
interface StoryManifest {
  origin: string;
  fictional_report_id: string;
  fictional_task_id: string;
  chapters: readonly Chapter[];
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));
const smooth = (start: number, end: number, value: number) => {
  const t = clamp((value - start) / (end - start));
  return t * t * (3 - 2 * t);
};
const interpolate = (a: Vec3, b: Vec3, t: number): Vec3 => Object.freeze([
  a[0] + (b[0] - a[0]) * t,
  a[1] + (b[1] - a[1]) * t,
  a[2] + (b[2] - a[2]) * t,
]);

function presentationStatus(id: ChapterId, local: number): DemoPresentationStatus {
  if (id === "public") return local < 0.18 ? "none" : local < 0.65 ? "sample_draft" : "sample_received";
  if (id === "command") return local < 0.2 ? "sample_received" : local < 0.48 ? "sample_under_review"
    : local < 0.78 ? "sample_task_assigned" : "sample_task_acknowledged";
  return id === "studio" || id === "shared" ? "sample_task_acknowledged" : "none";
}

function storyBeat(id: ChapterId, local: number): StoryBeat {
  if (id === "place") return local < 0.06 ? "photo-context" : local < OPENING_PLACE_PROGRESS
    ? "neighborhood-selection" : local < 0.78 ? "neighborhood-extraction" : "dry-neighborhood";
  const beats = {
    dry: "dry-neighborhood", flood: "rising-flood", access: "route-access", public: "local-report",
    command: "coordination", studio: "evidence-review", shared: "shared-context",
  } as const;
  return beats[id];
}

/** Validate and snapshot a presentation manifest; sampling never reads or writes application data. */
export function createStorySampler(value: unknown): (progress: unknown) => StoryFrame {
  const manifest = value as Partial<StoryManifest> | null;
  if (!manifest || !Array.isArray(manifest.chapters) || manifest.chapters.length !== STORY_CHAPTERS.length) {
    throw new TypeError("The complete semantic story chapter manifest is required.");
  }
  if (manifest.origin !== "synthetic_illustration") {
    throw new TypeError("Only a synthetic illustration manifest is accepted.");
  }
  if (typeof manifest.fictional_report_id !== "string" || !manifest.fictional_report_id.startsWith("DEMO-")
    || typeof manifest.fictional_task_id !== "string" || !manifest.fictional_task_id.startsWith("DEMO-")) {
    throw new TypeError("Presentation records must use explicit DEMO-prefixed identifiers.");
  }
  const chapters: Chapter[] = manifest.chapters.map((chapter) => ({ ...chapter }));
  let previousEnd = 0;
  for (const [index, chapter] of chapters.entries()) {
    const authored = STORY_CHAPTERS[index];
    if (chapter.id !== authored.id || chapter.scene !== authored.scene) {
      throw new TypeError("Chapters must retain the authored semantic sequence and named scenes.");
    }
    if (!Number.isFinite(chapter.start) || !Number.isFinite(chapter.end) || chapter.end <= chapter.start
      || Math.abs(chapter.start - previousEnd) > 1e-9) {
      throw new RangeError("Chapter ranges must be finite, ordered and contiguous.");
    }
    previousEnd = chapter.end;
  }
  if (Math.abs(previousEnd - 1) > 1e-9) throw new RangeError("Chapters must cover [0,1].");
  const reportId = manifest.fictional_report_id as `DEMO-${string}`;
  const taskId = manifest.fictional_task_id as `DEMO-${string}`;

  return (rawProgress: unknown): StoryFrame => {
    const progress = typeof rawProgress === "number" && !Number.isNaN(rawProgress) ? clamp(rawProgress) : 0;
    const found = chapters.findIndex((chapter) => progress < chapter.end);
    const chapterIndex = found < 0 ? chapters.length - 1 : found;
    const chapter = chapters[chapterIndex];
    const chapterProgress = clamp((progress - chapter.start) / (chapter.end - chapter.start));
    const nextChapter = chapters[chapterIndex + 1] ?? chapter;
    const blendToNext = chapterIndex < chapters.length - 1 ? smooth(0.78, 1, chapterProgress) : 0;
    const currentCamera = CAMERA_BY_CHAPTER[chapter.id];
    const nextCamera = CAMERA_BY_CHAPTER[nextChapter.id];
    const placeProgress = chapter.id === "place" ? chapterProgress : 1;
    const floodAmount = chapter.id === "place" || chapter.id === "dry" ? 0
      : chapter.id === "flood" ? smooth(0.05, 0.68, chapterProgress) : 1;
    const sceneWeights = Object.fromEntries(chapters.map(({ id }, index) => [id,
      index === chapterIndex ? 1 - blendToNext : index === chapterIndex + 1 ? blendToNext : 0,
    ])) as Record<ChapterId, number>;
    // The photo-to-model camera move finishes with extraction, before the dry/flood comparison.
    const cameraBlend = chapter.id === "place" ? smooth(0.3, 0.78, placeProgress) : blendToNext;
    return Object.freeze({
      progress, chapterId: chapter.id, chapterIndex, chapterProgress,
      phase: chapterProgress < 0.18 ? "entry" : chapterProgress < 0.78 ? "hold" : "exit",
      beat: storyBeat(chapter.id, chapterProgress),
      scene: chapter.scene, nextScene: nextChapter.scene, blendToNext,
      selectionAmount: smooth(0.06, 0.23, placeProgress),
      extractionAmount: smooth(0.28, 0.78, placeProgress),
      photoOpacity: 1 - smooth(0.34, 0.72, placeProgress),
      architectureAmount: smooth(0.3, 0.75, placeProgress),
      floodAmount, routeState: floodAmount > 0.15 ? "disrupted" : "open",
      reportId, taskId, reportStatus: presentationStatus(chapter.id, chapterProgress),
      origin: "synthetic_illustration", photoBasis: "unverified_illustrative_concept",
      operationalWriteAllowed: false, currentConditionClaim: false, newModelAutoPublished: false,
      sceneWeights: Object.freeze(sceneWeights),
      camera: Object.freeze({
        position: interpolate(currentCamera.position, nextCamera.position, cameraBlend),
        target: interpolate(currentCamera.target, nextCamera.target, cameraBlend),
        span: currentCamera.span + (nextCamera.span - currentCamera.span) * cameraBlend,
      }),
    });
  };
}

export const sampleStory = createStorySampler({
  origin: "synthetic_illustration",
  fictional_report_id: "DEMO-R017",
  fictional_task_id: "DEMO-T004",
  chapters: STORY_CHAPTERS,
});
