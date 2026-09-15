import manifest from "../../../public/landing/floodguard-v2/scene-manifest.json";

type Point = readonly [number, number];

function point(value: number[]): Point {
  if (value.length !== 2 || !value.every(Number.isFinite)) {
    throw new RangeError("Neighborhood anchors must contain two finite image coordinates.");
  }
  return [value[0], value[1]];
}

const { width, height } = manifest;
export const neighborhoodPosterSource = manifest.cameraFrames[0].src;
const route = manifest.anchors.route.map(point);
const [startIndex, endIndex] = manifest.anchors.affected;
const home = point(manifest.anchors.home);
const clinic = point(manifest.anchors.clinic);
const report = point(manifest.anchors.report);
const selection = manifest.anchors.selection.map(point);
const center = route[Math.round((startIndex + endIndex) / 2)];
const fullFrame = [0, 0, width, height] as const;
const selectionCenter: Point = [
  selection.reduce((sum, item) => sum + item[0], 0) / selection.length,
  selection.reduce((sum, item) => sum + item[1], 0) / selection.length,
];
const offset = ([x, y]: Point, dx: number, dy: number): Point => [
  Math.max(80, Math.min(width - 80, x + width * dx)),
  Math.max(80, Math.min(height - 80, y + height * dy)),
];

/** The rendered camera projects the same editable world into every water state. */
export const neighborhoodGeometry = {
  nativeSize: { width, height },
  viewports: { desktop: fullFrame, hero: fullFrame, mobile: fullFrame, heroMobile: fullFrame },
  points: { homeGate: home, clinicEntrance: clinic, affectedCenter: center, report },
  route,
  affectedSegment: { startIndex, endIndex },
  selectedAreaPath: `${selection.map(([x, y], index) => `${index ? "L" : "M"} ${x} ${y}`).join(" ")} Z`,
  selectedAreaMeaning: "Narrative selection only; not a flood extent, catchment, priority boundary, or measured polygon.",
  waterBoundaryPath: null,
  byState: Object.fromEntries(Object.keys(manifest.closeStates).map((state) => [state, {
    registration: "Shared Blender geometry and camera; only water height changes.",
    homeGate: home,
    clinicEntrance: clinic,
  }])),
  labelAnchors: {
    homes: offset(home, -.012, -.1),
    clinic: offset(clinic, .025, -.1),
    heroClinic: offset(clinic, .025, -.1),
    connection: offset(center, -.005, .045),
    report: offset(report, -.13, .17),
    selection: offset(selectionCenter, .2, .24),
  },
};

export function neighborhoodPlateSource(state: string) {
  if (!Object.hasOwn(manifest.closeStates, state)) {
    throw new RangeError(`Unknown neighborhood water state: ${state}`);
  }
  return manifest.closeStates[state as keyof typeof manifest.closeStates];
}

export function neighborhoodPlateSrcSet(state: string) {
  return `${neighborhoodPlateSource(state)} ${width}w`;
}

/** Align three projected ground points before blending neighboring camera renders. */
export function registerCameraTriangle(source: readonly number[][], target: readonly number[][]) {
  if ([source, target].some((triangle) => triangle.length !== 3 || triangle.some((point) => point.length !== 2 || !point.every(Number.isFinite)))) throw new RangeError("Camera registration needs three finite image points.");
  const [[x0, y0], [x1, y1], [x2, y2]] = source;
  const [[u0, v0], [u1, v1], [u2, v2]] = target;
  const determinant = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-9) throw new RangeError("Camera registration needs three non-collinear points.");
  const a = ((u1 - u0) * (y2 - y0) - (u2 - u0) * (y1 - y0)) / determinant;
  const c = ((x1 - x0) * (u2 - u0) - (x2 - x0) * (u1 - u0)) / determinant;
  const b = ((v1 - v0) * (y2 - y0) - (v2 - v0) * (y1 - y0)) / determinant;
  const d = ((x1 - x0) * (v2 - v0) - (x2 - x0) * (v1 - v0)) / determinant;
  const matrix = [a, b, c, d, u0 - a * x0 - c * y0, v0 - b * x0 - d * y0] as const;
  if (!matrix.every(Number.isFinite)) throw new RangeError("Camera registration produced an invalid transform.");
  return matrix;
}
