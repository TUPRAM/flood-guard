/**
 * Two-bone reach for the journey's people (shoulder–elbow–wrist, hip–knee–ankle): where the middle joint goes so the
 * end of the limb arrives at a target. Pure: no DOM, no Three.js, so the rule is unit-tested; the stage turns the
 * bones to match (`components/journey/stage/characters.ts`).
 */

export interface Point {
  x: number;
  y: number;
  z: number;
}

export interface Reach {
  /** Where the middle joint (elbow or knee) goes. */
  joint: Point;
  /** Where the end (wrist or ankle) arrives: the target, or the nearest point the limb can reach. */
  end: Point;
  /** False when the target was out of reach (too far, or closer than the limb can fold). */
  reached: boolean;
}

const sub = (a: Point, b: Point): Point => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
const add = (a: Point, b: Point, scale = 1): Point => ({ x: a.x + b.x * scale, y: a.y + b.y * scale, z: a.z + b.z * scale });
const dot = (a: Point, b: Point): number => a.x * b.x + a.y * b.y + a.z * b.z;
const length = (a: Point): number => Math.sqrt(dot(a, a));
const cross = (a: Point, b: Point): Point => ({ x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x });

/**
 * Solves a limb rooted at `root` with bone lengths `upper` and `lower` so its end arrives at `target`. The middle
 * joint lies on the side of `pole` (a point the elbow or knee should bend toward). A limb never straightens fully
 * (`slack` of its length is kept), so a far target is approached along the same line without the joint snapping.
 */
export function solveReach(root: Point, target: Point, pole: Point, upper: number, lower: number, slack = 0.001): Reach {
  const toTarget = sub(target, root);
  const wanted = length(toTarget);
  const nearest = Math.abs(upper - lower) + 1e-6, farthest = (upper + lower) * (1 - slack);
  const distance = Math.min(farthest, Math.max(nearest, wanted));
  // A target on the root itself has no direction: fall back to straight down.
  const direction = wanted > 1e-9 ? { x: toTarget.x / wanted, y: toTarget.y / wanted, z: toTarget.z / wanted } : { x: 0, y: -1, z: 0 };

  // The joint sits on a circle around the root–end line: `along` the line, `out` from it.
  const along = (upper * upper + distance * distance - lower * lower) / (2 * distance);
  const out = Math.sqrt(Math.max(0, upper * upper - along * along));

  // Bend toward the pole: its direction from the root, with the part along the limb's line removed.
  const toPole = sub(pole, root);
  let bend = add(toPole, direction, -dot(toPole, direction));
  if (length(bend) < 1e-9) {
    // The pole is on the line itself: any perpendicular will do, as long as it is stable.
    bend = cross(direction, Math.abs(direction.y) < 0.9 ? { x: 0, y: 1, z: 0 } : { x: 1, y: 0, z: 0 });
  }
  const bendLength = length(bend);
  bend = { x: bend.x / bendLength, y: bend.y / bendLength, z: bend.z / bendLength };

  return {
    joint: add(add(root, direction, along), bend, out),
    end: add(root, direction, distance),
    reached: Math.abs(wanted - distance) < 1e-6,
  };
}
