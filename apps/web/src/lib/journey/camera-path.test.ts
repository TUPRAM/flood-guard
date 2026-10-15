import * as THREE from "three";
import { describe, expect, it } from "vitest";

import { easeMove, samplePath, type CameraKey } from "./camera-path";

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const key = (at: number, pos: THREE.Vector3, target: THREE.Vector3, extra: Partial<CameraKey> = {}): CameraKey => ({ at, pos, target, ...extra });

function sample(keys: CameraKey[], p: number, ground?: (x: number, z: number) => number) {
  const pos = new THREE.Vector3(), target = new THREE.Vector3(), up = new THREE.Vector3();
  const zoom = samplePath(keys, p, pos, target, up, ground);
  const forward = target.clone().sub(pos).normalize();
  return { pos, target, up, zoom, forward, pitch: Math.asin(forward.y) };
}

/** Rotation (radians) between the camera orientations of two samples. */
function rotation(a: ReturnType<typeof sample>, b: ReturnType<typeof sample>): number {
  const q = (s: ReturnType<typeof sample>) => new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().lookAt(s.pos, s.target, s.up));
  return q(a).angleTo(q(b));
}

describe("camera paths", () => {
  it("eases in and out with a sine, peaking at π/2 times the average speed", () => {
    expect(easeMove(0)).toBe(0);
    expect(easeMove(1)).toBe(1);
    expect(easeMove(0.5)).toBeCloseTo(0.5, 12);
    const h = 1e-4;
    expect((easeMove(0.5 + h) - easeMove(0.5 - h)) / (2 * h)).toBeCloseTo(Math.PI / 2, 3);
  });

  it("stands exactly on every settle key and stays put through a hold", () => {
    const a = key(0, v(0, 10, 0), v(0, 0, 20));
    const b = key(0.4, v(30, 20, 10), v(0, 0, 0));
    const keys = [a, b, { ...b, at: 0.7 }, key(1, v(60, 5, -10), v(50, 1, -30))];
    expect(sample(keys, 0).pos.distanceTo(a.pos)).toBeLessThan(1e-9);
    for (const p of [0.4, 0.5, 0.6, 0.7]) expect(sample(keys, p).pos.distanceTo(b.pos), `p ${p}`).toBeLessThan(1e-6);
    expect(sample(keys, 1).pos.distanceTo(keys[3].pos)).toBeLessThan(1e-6);
    // Aim at the settle keys too.
    expect(sample(keys, 0.5).forward.angleTo(b.target.clone().sub(b.pos))).toBeLessThan(1e-6);
  });

  it("passes through pass keys and moves without jumps", () => {
    const keys = [
      key(0, v(0, 300, -260), v(-90, 0, 380)),
      key(0.3, v(0, 28, -40), v(0, 3, 0), { pass: true }),
      key(0.6, v(0, 4.5, -14), v(0, 1.4, -1), { pass: true }),
      key(1, v(7, 1.65, 0), v(-2, 2.6, 0)),
    ];
    let previous = sample(keys, 0);
    let nearPass = Infinity;
    for (let i = 1; i <= 2000; i += 1) {
      const s = sample(keys, i / 2000);
      expect(s.pos.distanceTo(previous.pos), `step ${i}`).toBeLessThan(2.5);
      nearPass = Math.min(nearPass, s.pos.distanceTo(keys[1].pos));
      previous = s;
    }
    expect(nearPass).toBeLessThan(0.5);
  });

  it("turns the short way round the horizon, never through straight down, between opposite headings", () => {
    // Looking north-north-east and down 45°, then south and down 45°: a look-at target swung under the camera here.
    const keys = [key(0, v(0, 300, 300), v(80, 0, 0)), key(1, v(0, 300, -300), v(0, 0, 0))];
    let steepest = 0, worstStep = 0;
    let previous = sample(keys, 0);
    for (let i = 1; i <= 400; i += 1) {
      const s = sample(keys, i / 400);
      steepest = Math.min(steepest, s.pitch);
      worstStep = Math.max(worstStep, rotation(previous, s));
      previous = s;
    }
    const endPitches = [sample(keys, 0).pitch, sample(keys, 1).pitch];
    expect(steepest).toBeGreaterThan(Math.min(...endPitches) - THREE.MathUtils.degToRad(3));
    // At most 1.5° of rotation per 1/400 of the move: no spin.
    expect(worstStep).toBeLessThan(THREE.MathUtils.degToRad(1.5));
  });

  it("does not tilt past the end of a dive and back", () => {
    const keys = [key(0, v(0, 120, 110), v(0, 0, -400)), key(1, v(0, 44, -34), v(0, 0, 0))];
    let previous = sample(keys, 0).pitch;
    for (let i = 1; i <= 400; i += 1) {
      const pitch = sample(keys, i / 400).pitch;
      expect(pitch, `p ${i / 400}`).toBeLessThanOrEqual(previous + 1e-9);
      previous = pitch;
    }
  });

  it("keeps a top-down key's heading from its screen-up and the horizon level elsewhere", () => {
    const north = v(0, 0, -1);
    const keys = [key(0, v(0, 500, 0.05), v(0, 0, 0), { up: north }), key(1, v(0, 200, 300), v(0, 0, 0))];
    expect(sample(keys, 0).up.dot(north)).toBeGreaterThan(0.999);
    const mid = sample(keys, 0.5);
    // No roll: screen-right stays horizontal.
    const right = mid.forward.clone().cross(mid.up);
    expect(Math.abs(right.y)).toBeLessThan(1e-6);
  });

  it("slows a dive as it nears the ground (paced by height)", () => {
    const keys = [key(0, v(0, 300, 0), v(0, 0, 300)), key(1, v(0, 3, 0), v(0, 2, 30))];
    const speedAt = (p: number) => sample(keys, p + 0.001, () => 0).pos.distanceTo(sample(keys, p, () => 0).pos);
    // Same ease phase (symmetric around the middle), different heights: far faster high up than near the ground.
    expect(speedAt(0.3)).toBeGreaterThan(3 * speedAt(0.7));
  });

  it("returns the keys' zoom, eased along the glide, and 1 without one", () => {
    const keys = [key(0, v(0, 2, 10), v(0, 1, 0)), key(1, v(0, 2, 7), v(0, 1, 0), { zoom: 1.25 })];
    expect(sample(keys, 0).zoom).toBe(1);
    expect(sample(keys, 1).zoom).toBeCloseTo(1.25, 12);
    expect(sample(keys, 0.5).zoom).toBeGreaterThan(1);
  });

  it("copes with coincident keys", () => {
    const a = key(0, v(1, 2, 3), v(1, 0, 10));
    const keys = [a, { ...a, at: 0.5, pass: true }, key(1, v(5, 2, 3), v(5, 0, 10))];
    for (const p of [0, 0.25, 0.5, 0.75, 1]) {
      const s = sample(keys, p);
      expect(Number.isFinite(s.pos.x) && Number.isFinite(s.target.z) && Number.isFinite(s.up.y), `p ${p}`).toBe(true);
    }
  });

  it("keeps looking at a subject both keys look at (a push in), within a degree", () => {
    const phone = v(0.3, 1.4, 0.4);
    const keys = [key(0, v(-0.8, 2.0, -0.6), phone.clone()), key(1, v(0.1, 1.45, 0.25), phone.clone())];
    for (let i = 0; i <= 200; i += 1) {
      const s = sample(keys, i / 200);
      const toPhone = phone.clone().sub(s.pos);
      if (toPhone.length() < 1e-3) continue;
      expect(THREE.MathUtils.radToDeg(s.forward.angleTo(toPhone)), `p ${i / 200}`).toBeLessThan(1);
    }
  });

  it("reaches a rolled key exactly and rolls the short way", () => {
    const pos = v(0, 1.5, 2), target = v(0, 1.5, 0);
    const forward = target.clone().sub(pos).normalize();
    const rolled = v(0, 1, 0).applyAxisAngle(forward, THREE.MathUtils.degToRad(59));
    const keys = [key(0, v(-2, 2, 4), v(0, 1.4, 0)), key(1, pos, target, { up: rolled })];
    const end = sample(keys, 1);
    expect(end.up.angleTo(rolled)).toBeLessThan(1e-6);
    let previous = sample(keys, 0);
    for (let i = 1; i <= 200; i += 1) {
      const s = sample(keys, i / 200);
      expect(rotation(previous, s), `p ${i / 200}`).toBeLessThan(THREE.MathUtils.degToRad(3));
      previous = s;
    }
  });

  it("keeps an even felt speed through a pass key (no kick between orbit and dolly)", () => {
    const keys = [
      key(0, v(0, 2, 7), v(0, 1.2, 0)),
      key(0.5, v(-1.2, 1.9, 1.5), v(0, 1.3, 0), { pass: true }),
      key(1, v(-0.8, 2.0, -0.5), v(0.2, 1.4, 0.4)),
    ];
    const felt = (a: ReturnType<typeof sample>, b: ReturnType<typeof sample>) => a.pos.distanceTo(b.pos) / 2 + 3.5 * rotation(a, b);
    let previous = sample(keys, 0.3), prevSpeed = -1;
    for (let i = 1; i <= 80; i += 1) {
      // The middle of the move, where the ease is near its peak and nearly flat.
      const s = sample(keys, 0.3 + (i / 80) * 0.4);
      const speed = felt(previous, s);
      if (prevSpeed > 0) expect(Math.abs(speed - prevSpeed) / prevSpeed, `step ${i}`).toBeLessThan(0.3);
      prevSpeed = speed;
      previous = s;
    }
  });
});

