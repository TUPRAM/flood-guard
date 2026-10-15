/**
 * Camera paths of the journey: keyframes (where the camera is and what it looks at) turned into a smooth move.
 * No DOM; Three.js math only, so the rules are unit-tested.
 *
 * - Position follows a centripetal Catmull-Rom spline through the keys (no overshoot, no loops when keys are unevenly
 *   spaced, as a key 300 m up next to one in the street is).
 * - Orientation is interpolated as heading, tilt and roll, not as a point to look at: a move between two views that
 *   look in very different directions turns round the horizon instead of swinging through straight down, where a
 *   look-at target passing under the camera spun the picture.
 * - The camera settles on every key that is not a `pass` key. Each move from one settle key to the next eases in and
 *   out once (a sine ease), and its waypoints share its time by how fast the picture changes along them: travel
 *   relative to the height above the ground, plus the camera's rotation. A dive from 300 m slows as it nears the
 *   street; a turn gets the time it needs.
 */

import * as THREE from "three";

export interface CameraKey {
  at: number;
  pos: THREE.Vector3;
  target: THREE.Vector3;
  /** Screen-up for this key (default: level, world up). Gives top-down views their heading and screen poses their roll. */
  up?: THREE.Vector3;
  /** A waypoint the camera glides through without settling (it only shapes the path). */
  pass?: boolean;
  /** Field of view relative to the viewport's own (1 if not given): a wider lens where the camera cannot back off. */
  zoom?: number;
}

export type Ground = (x: number, z: number) => number;

const Y = new THREE.Vector3(0, 1, 0);
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** The ease of a move: sine in-out, whose peak speed is π/2 times its average (a cubic ease peaks at 3 times). */
export function easeMove(x: number): number {
  return 0.5 - 0.5 * Math.cos(Math.PI * clamp01(x));
}

/** Heading, tilt, roll (radians) and log of the distance to the aim of a key. */
interface Aim { yaw: number; pitch: number; roll: number; reach: number }

/** Right and level up of a view with heading `yaw` and tilt `pitch` (no roll). */
function levelFrame(yaw: number, pitch: number, forward: THREE.Vector3, right: THREE.Vector3, up: THREE.Vector3): void {
  forward.set(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
  // Screen-right of a camera facing `forward` (facing +z, right is -x).
  right.set(-Math.cos(yaw), 0, Math.sin(yaw));
  up.crossVectors(right, forward).normalize();
}

const scratch = { f: new THREE.Vector3(), r: new THREE.Vector3(), u: new THREE.Vector3(), w: new THREE.Vector3() };

export function aimOf(key: CameraKey): Aim {
  const f = key.target.clone().sub(key.pos);
  const reach = Math.max(1e-3, f.length());
  f.divideScalar(reach);
  const pitch = Math.asin(THREE.MathUtils.clamp(f.y, -1, 1));
  const keyUp = key.up ?? Y;
  let yaw: number;
  // Looking (almost) straight down with a screen-up given, the heading is where screen-up points (straight up:
  // opposite it); otherwise the view's own heading, however little of it there is.
  const s = f.y < 0 ? 1 : -1;
  if (Math.abs(f.y) > 0.996 && key.up) yaw = Math.atan2(keyUp.x * s, keyUp.z * s);
  else yaw = Math.atan2(f.x, f.z);
  const { f: lf, r, u, w } = scratch;
  levelFrame(yaw, pitch, lf, r, u);
  // Roll: from the level up to the key's up, about the view direction.
  w.copy(keyUp).addScaledVector(lf, -keyUp.dot(lf));
  let roll = 0;
  if (w.lengthSq() > 1e-8 && key.up) {
    w.normalize();
    roll = Math.atan2(w.dot(r.clone().negate()), w.dot(u));
  }
  return { yaw, pitch, roll, reach: Math.log(reach) };
}

/**
 * Catmull-Rom (Barry-Goldman) between v1 and v2 over arrays of numbers, on the given knot gaps (v0→v1, v1→v2,
 * v2→v3). Position, aim and target share one set of gaps, so all are smooth in the same parameter: at a waypoint the
 * balance of travel and turning carries on instead of jumping.
 */
function catmullArray(v0: number[], v1: number[], v2: number[], v3: number[], gaps: [number, number, number], t: number): number[] {
  const t0 = 0, t1 = t0 + gaps[0], t2 = t1 + gaps[1], t3 = t2 + gaps[2];
  const u = t1 + (t2 - t1) * t;
  const lerp = (a: number[], b: number[], ta: number, tb: number) => a.map((value, i) => (value * (tb - u) + b[i] * (u - ta)) / (tb - ta));
  const a1 = lerp(v0, v1, t0, t1), a2 = lerp(v1, v2, t1, t2), a3 = lerp(v2, v3, t2, t3);
  const b1 = lerp(a1, a2, t0, t2), b2 = lerp(a2, a3, t1, t3);
  return lerp(b1, b2, t1, t2);
}

const vec = (v: THREE.Vector3) => [v.x, v.y, v.z];

/** The neighbours a glide from keys[i] to keys[i + 1] uses: none from outside its move (settle key to settle key). */
function glideEnds(keys: CameraKey[], i: number, s0: number, s1: number): [CameraKey, CameraKey, CameraKey, CameraKey] {
  const a = keys[i], b = keys[i + 1];
  return [i === s0 ? a : keys[Math.max(0, i - 1)], a, b, i + 1 === s1 ? b : keys[Math.min(keys.length - 1, i + 2)]];
}

const isHold = (a: CameraKey, b: CameraKey) => a.pos.equals(b.pos) && a.target.equals(b.target) && (a.up ?? Y).equals(b.up ?? Y);

/** Wrap `angle` to within π of `reference`. */
function nearAngle(angle: number, reference: number): number {
  return angle + Math.round((reference - angle) / (2 * Math.PI)) * 2 * Math.PI;
}

/** Weight of rotation (radians) against travel (in heights above the ground) in a move's felt length. */
const TURN_WEIGHT = 3.5;

/** Centripetal knot gap between two keys: the square root of how much the picture changes from one to the other. */
function knotGap(a: CameraKey, b: CameraKey, A: Aim, B: Aim): number {
  const reach = Math.max(0.5, Math.min(Math.exp(A.reach), Math.exp(B.reach)));
  const da = a.target.clone().sub(a.pos).normalize(), db = b.target.clone().sub(b.pos).normalize();
  const turn = Math.acos(THREE.MathUtils.clamp(da.dot(db), -1, 1)) + Math.abs(B.roll - A.roll);
  return Math.max(1e-4, Math.sqrt(a.pos.distanceTo(b.pos) / reach + TURN_WEIGHT * turn));
}

/**
 * The pose at parameter u of the glide from keys[i] to keys[i + 1]: position, view direction, up and reach. Where the
 * glide's two keys look at (nearly) the same point, the camera keeps looking at it (a push in or an orbit round a
 * subject); where they look at different things, heading, tilt and roll turn the short way round.
 */
function glidePose(ends: [CameraKey, CameraKey, CameraKey, CameraKey], u: number, outPos: THREE.Vector3, outForward: THREE.Vector3, outUp: THREE.Vector3): number {
  const [k0, a, b, k3] = ends;
  const A0 = aimOf(k0), A1 = aimOf(a), A2 = aimOf(b), A3 = aimOf(k3);
  // Headings and rolls unwrapped along the chain, so each glide turns the short way.
  A0.yaw = nearAngle(A0.yaw, A1.yaw);
  A2.yaw = nearAngle(A2.yaw, A1.yaw);
  A3.yaw = nearAngle(A3.yaw, A2.yaw);
  A0.roll = nearAngle(A0.roll, A1.roll);
  A2.roll = nearAngle(A2.roll, A1.roll);
  A3.roll = nearAngle(A3.roll, A2.roll);
  const gaps: [number, number, number] = [knotGap(k0, a, A0, A1), knotGap(a, b, A1, A2), knotGap(b, k3, A2, A3)];
  const p = catmullArray(vec(k0.pos), vec(a.pos), vec(b.pos), vec(k3.pos), gaps, u);
  outPos.set(p[0], p[1], p[2]);
  const pack = (aim: Aim) => [aim.yaw, aim.pitch, aim.roll, aim.reach];
  // Each of heading, tilt, roll and distance stays between its values at the glide's two keys: the view never swings
  // past where it is going and back (the spline alone overshoots next to a close waypoint).
  const ends12 = [pack(A1), pack(A2)];
  const [yaw, pitch, roll, lnReach] = catmullArray(pack(A0), pack(A1), pack(A2), pack(A3), gaps, u)
    .map((value, i) => THREE.MathUtils.clamp(value, Math.min(ends12[0][i], ends12[1][i]), Math.max(ends12[0][i], ends12[1][i])));
  const { r, u: level, f: aimed } = scratch;
  levelFrame(yaw, THREE.MathUtils.clamp(pitch, -Math.PI / 2, Math.PI / 2), aimed, r, level);
  let reach = Math.exp(lnReach);
  outForward.copy(aimed);
  // Tracking a subject: blend toward looking at the interpolated target as the two keys' targets coincide.
  const apart = a.target.distanceTo(b.target) / Math.max(0.3, Math.min(Math.exp(A1.reach), Math.exp(A2.reach)));
  const track = 1 - THREE.MathUtils.smoothstep(apart, 0.02, 0.08);
  if (track > 0) {
    const t = catmullArray(vec(k0.target), vec(a.target), vec(b.target), vec(k3.target), gaps, u);
    const toTarget = new THREE.Vector3(t[0] - outPos.x, t[1] - outPos.y, t[2] - outPos.z);
    const distance = toTarget.length();
    if (distance > 1e-6) {
      outForward.lerp(toTarget.divideScalar(distance), track).normalize();
      reach = THREE.MathUtils.lerp(reach, distance, track);
    }
  }
  // Up: the level up of the final view direction, turned by the roll about it. Looking nearly straight down (or up)
  // the view's own heading is undefined and flips over the subject, so there the keys' heading takes over.
  const fy = THREE.MathUtils.clamp(outForward.y, -1, 1);
  const horizontal = Math.hypot(outForward.x, outForward.z);
  const own = horizontal > 1e-6 ? Math.atan2(outForward.x, outForward.z) : yaw;
  const vertical = THREE.MathUtils.smoothstep(Math.abs(fy), 0.95, 0.995);
  const heading = own + (nearAngle(yaw, own) - own) * vertical;
  levelFrame(heading, Math.asin(fy), scratch.w, r, level);
  outUp.copy(level).multiplyScalar(Math.cos(roll)).addScaledVector(r, -Math.sin(roll)).normalize();
  return reach;
}

const PACE_SAMPLES = 96;
const paceCache = new Map<string, { lengths: number[]; cumulative: Float32Array[] }>();

/** How much each glide of a move changes the picture, sampled along it (see the module comment). */
function paceTable(keys: CameraKey[], s0: number, s1: number, ground: Ground): { lengths: number[]; cumulative: Float32Array[] } {
  const round = (v: THREE.Vector3) => `${v.x.toFixed(2)},${v.y.toFixed(2)},${v.z.toFixed(2)}`;
  const signature = keys.slice(Math.max(0, s0 - 1), Math.min(keys.length, s1 + 2)).map((key) => `${round(key.pos)}>${round(key.target)}^${round(key.up ?? Y)}${key.pass ? "p" : ""}`).join("|") + `#${s0 > 0 ? 1 : 0}${s1 < keys.length - 1 ? 1 : 0}`;
  const cached = paceCache.get(signature);
  if (cached) return cached;
  const lengths: number[] = [], cumulative: Float32Array[] = [];
  const pos = new THREE.Vector3(), forward = new THREE.Vector3(), up = new THREE.Vector3();
  const prevPos = new THREE.Vector3();
  const q = new THREE.Quaternion(), prevQ = new THREE.Quaternion(), m = new THREE.Matrix4();
  for (let i = s0; i < s1; i += 1) {
    const ends = glideEnds(keys, i, s0, s1);
    const table = new Float32Array(PACE_SAMPLES + 1);
    if (!isHold(ends[1], ends[2])) {
      for (let j = 0; j <= PACE_SAMPLES; j += 1) {
        const reach = glidePose(ends, j / PACE_SAMPLES, pos, forward, up);
        m.lookAt(pos, pos.clone().add(forward), up);
        q.setFromRotationMatrix(m);
        if (j > 0) {
          // Travel counts against the camera's distance to what it is near: the ground, its aim, or the nearer key's
          // target (close to a person, a metre of travel is a lot).
          const near = Math.min(pos.distanceTo(ends[1].target), pos.distanceTo(ends[2].target));
          const height = Math.max(0.5, Math.min(reach, pos.y - ground(pos.x, pos.z) + 2, near));
          table[j] = table[j - 1] + pos.distanceTo(prevPos) / height + TURN_WEIGHT * prevQ.angleTo(q);
        }
        prevPos.copy(pos);
        prevQ.copy(q);
      }
    }
    lengths.push(table[PACE_SAMPLES]);
    cumulative.push(table);
  }
  if (paceCache.size > 64) paceCache.delete(paceCache.keys().next().value!);
  const result = { lengths, cumulative };
  paceCache.set(signature, result);
  return result;
}

/**
 * Camera pose along keyframes at progress p (0..1) of a segment: position, the point it looks at, and screen-up; returns
 * the field-of-view factor (`zoom`, 1 by default). `ground` gives the ground height for pacing (felt speed depends on
 * height).
 */
export function samplePath(keys: CameraKey[], p: number, outPos: THREE.Vector3, outTarget: THREE.Vector3, outUp: THREE.Vector3, ground: Ground = () => 0): number {
  const x = clamp01(p);
  let s0 = 0;
  for (let k = 1; k < keys.length - 1; k += 1) if (!keys[k].pass && keys[k].at <= x) s0 = k;
  let s1 = keys.length - 1;
  for (let k = keys.length - 2; k > s0; k -= 1) if (!keys[k].pass) s1 = k;
  if (s1 <= s0) {
    outPos.copy(keys[s0].pos); outTarget.copy(keys[s0].target); outUp.copy(keys[s0].up ?? Y);
    return keys[s0].zoom ?? 1;
  }
  const span = Math.max(1e-6, keys[s1].at - keys[s0].at);
  const eased = easeMove((x - keys[s0].at) / span);
  const { lengths, cumulative } = paceTable(keys, s0, s1, ground);
  const total = lengths.reduce((sum, length) => sum + length, 0);
  let i = s0, local = eased;
  if (total > 1e-9) {
    let left = eased * total;
    while (i < s1 - 1 && left > lengths[i - s0]) { left -= lengths[i - s0]; i += 1; }
    const table = cumulative[i - s0];
    let j = 1;
    while (j < PACE_SAMPLES && table[j] < left) j += 1;
    const step = table[j] - table[j - 1];
    local = clamp01((j - 1 + (step > 1e-12 ? (left - table[j - 1]) / step : 1)) / PACE_SAMPLES);
  }
  const ends = glideEnds(keys, i, s0, s1);
  // The lens changes once over the whole move, from one settle key's zoom to the next (waypoints do not reset it).
  const zoom = THREE.MathUtils.lerp(keys[s0].zoom ?? 1, keys[s1].zoom ?? 1, eased);
  if (isHold(ends[1], ends[2])) {
    outPos.copy(ends[1].pos); outTarget.copy(ends[1].target); outUp.copy(ends[1].up ?? Y);
    return zoom;
  }
  const forward = new THREE.Vector3();
  const reach = glidePose(ends, local, outPos, forward, outUp);
  outTarget.copy(outPos).addScaledVector(forward, reach);
  return zoom;
}
