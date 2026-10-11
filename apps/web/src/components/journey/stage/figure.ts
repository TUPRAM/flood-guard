import * as THREE from "three";

/**
 * Articulated people for the journey (about 1.7 m tall, facing +z). Bodies are sculpted from lofted cross-sections
 * (torso, limbs, shoes) and a shaped head with restrained facial features and a hair shell, dressed in layered
 * clothing (sleeves and hems over skin). Joints are groups, posed by forward kinematics; arms use a two-bone IK solver
 * so a hand stays on a held object, and each hand has jointed fingers and a thumb that can grip.
 * Procedural on purpose: no downloaded assets, no licence questions, and it stays light (a few thousand triangles).
 */

export interface FigureStyle {
  skin: number;
  shirt: number;
  trousers: number;
  hair: number;
  shoes: number;
  sole?: number;
  hairStyle: "bun" | "short";
  build: "f" | "m";
}

type Finger = [THREE.Group, THREE.Group];

export interface FigureJoints {
  hips: THREE.Group;
  chest: THREE.Group;
  head: THREE.Group;
  shoulderL: THREE.Group;
  shoulderR: THREE.Group;
  elbowL: THREE.Group;
  elbowR: THREE.Group;
  wristL: THREE.Group;
  wristR: THREE.Group;
  hipL: THREE.Group;
  hipR: THREE.Group;
  kneeL: THREE.Group;
  kneeR: THREE.Group;
  fingersL: Finger[];
  fingersR: Finger[];
  thumbL: Finger;
  thumbR: Finger;
}

export interface Figure {
  root: THREE.Group;
  joints: FigureJoints;
  dispose(): void;
}

export const UPPER_ARM = 0.29;
export const FOREARM = 0.26;
const HIP_HEIGHT = 0.92;
const THIGH = 0.415;
const SHIN = 0.415;
const REST = new THREE.Vector3(0, -1, 0);

// --- Lofted geometry -------------------------------------------------------------------------------------------------

interface Ring {
  y: number;
  rx: number;
  rz: number;
  cx?: number;
  cz?: number;
  /** Superellipse exponent: 2 = ellipse, larger = squarer. */
  n?: number;
}

function catmull(a: number, b: number, c: number, d: number, t: number): number {
  const t2 = t * t, t3 = t2 * t;
  return 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
}

function smoothRings(rings: Ring[], sub: number): Ring[] {
  const out: Ring[] = [];
  const keys: Array<keyof Ring> = ["y", "rx", "rz", "cx", "cz", "n"];
  for (let i = 0; i < rings.length - 1; i += 1) {
    const r0 = rings[Math.max(0, i - 1)], r1 = rings[i], r2 = rings[i + 1], r3 = rings[Math.min(rings.length - 1, i + 2)];
    for (let s = 0; s < sub; s += 1) {
      const t = s / sub;
      const ring = {} as Ring;
      for (const key of keys) {
        const fallback = key === "n" ? 2 : 0;
        (ring as unknown as Record<string, number>)[key] = catmull(r0[key] ?? fallback, r1[key] ?? fallback, r2[key] ?? fallback, r3[key] ?? fallback, t);
      }
      out.push(ring);
    }
  }
  out.push({ ...rings[rings.length - 1] });
  return out;
}

/** A closed surface through elliptical (superelliptical) rings stacked along y. Angle 0 is the front (+z). */
function loft(input: Ring[], segments = 22, sub = 3, caps: [boolean, boolean] = [true, true]): THREE.BufferGeometry {
  const rings = smoothRings(input, sub);
  const positions: number[] = [];
  const indices: number[] = [];
  for (const ring of rings) {
    const e = 2 / (ring.n ?? 2);
    for (let k = 0; k < segments; k += 1) {
      const a = (k / segments) * Math.PI * 2;
      const s = Math.sin(a), c = Math.cos(a);
      const x = (ring.cx ?? 0) + ring.rx * Math.sign(s) * Math.abs(s) ** e;
      const z = (ring.cz ?? 0) + ring.rz * Math.sign(c) * Math.abs(c) ** e;
      positions.push(x, ring.y, z);
    }
  }
  const descending = rings[rings.length - 1].y < rings[0].y;
  for (let r = 0; r < rings.length - 1; r += 1) {
    for (let k = 0; k < segments; k += 1) {
      const a = r * segments + k, b = r * segments + ((k + 1) % segments);
      const c = a + segments, d = b + segments;
      if (descending) indices.push(a, c, b, b, c, d);
      else indices.push(a, b, c, b, d, c);
    }
  }
  const cap = (ringIndex: number, upward: boolean) => {
    const ring = rings[ringIndex];
    const centre = positions.length / 3;
    positions.push(ring.cx ?? 0, ring.y, ring.cz ?? 0);
    for (let k = 0; k < segments; k += 1) {
      const a = ringIndex * segments + k, b = ringIndex * segments + ((k + 1) % segments);
      if (upward) indices.push(centre, a, b);
      else indices.push(centre, b, a);
    }
  };
  // Each end cap faces away from the rest of the surface.
  if (caps[0]) cap(0, descending);
  if (caps[1]) cap(rings.length - 1, !descending);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function mesh(geometry: THREE.BufferGeometry, material: THREE.Material, parent: THREE.Object3D, position?: [number, number, number], scale?: [number, number, number]): THREE.Mesh {
  const m = new THREE.Mesh(geometry, material);
  m.castShadow = true;
  m.receiveShadow = true;
  if (position) m.position.set(...position);
  if (scale) m.scale.set(...scale);
  parent.add(m);
  return m;
}

// --- Head ------------------------------------------------------------------------------------------------------------

/** Shape a unit-sphere direction into a head surface point (metres, head-local, centre at origin). */
function headPoint(u: THREE.Vector3, out: THREE.Vector3): THREE.Vector3 {
  let x = u.x * 0.077, z = u.z * 0.094;
  const y = u.y * 0.106;
  if (u.y < 0) {
    const low = -u.y;
    x *= 1 - 0.3 * low ** 1.4;
    z *= u.z > 0 ? 1 - 0.1 * low : 1 - 0.42 * low ** 1.2;
  } else if (u.z < 0) {
    z *= 1.07;
  }
  if (u.z > 0) {
    // Slightly flatter face plane; brow ridge and cheekbones.
    z *= 1 - 0.05 * (1 - Math.abs(u.x));
    const brow = Math.exp(-(((u.y - 0.27) / 0.08) ** 2)) * Math.exp(-((u.x / 0.5) ** 2));
    z += 0.004 * brow * u.z;
    for (const side of [-1, 1]) {
      const socket = Math.exp(-(((u.x - side * 0.33) ** 2 + (u.y - 0.12) ** 2) / 0.018));
      z -= 0.009 * socket * u.z;
      const cheek = Math.exp(-(((u.x - side * 0.5) ** 2 + (u.y + 0.08) ** 2) / 0.04));
      x += side * 0.003 * cheek;
    }
  }
  return out.set(x, y, z);
}

function headGeometry(): THREE.BufferGeometry {
  const g = new THREE.SphereGeometry(1, 44, 32);
  const p = g.getAttribute("position") as THREE.BufferAttribute;
  const u = new THREE.Vector3(), out = new THREE.Vector3();
  for (let i = 0; i < p.count; i += 1) {
    u.fromBufferAttribute(p, i);
    headPoint(u, out);
    p.setXYZ(i, out.x, out.y, out.z);
  }
  g.deleteAttribute("uv");
  g.computeVertexNormals();
  return g;
}

/**
 * Hair: a shell over the skull bounded by a smooth hairline that runs around the head (high at the forehead, above
 * the ears, down to the nape). Near the hairline the shell tapers onto the skin, so the edge reads as hair, not a cap.
 */
function hairGeometry(style: "bun" | "short"): THREE.BufferGeometry {
  const g = new THREE.SphereGeometry(1, 72, 54).toNonIndexed();
  const p = g.getAttribute("position") as THREE.BufferAttribute;
  const smooth = (e0: number, e1: number, x: number) => THREE.MathUtils.smoothstep(x, e0, e1);
  const hairline = (x: number, z: number) => {
    const phi = Math.abs(Math.atan2(x, z)); // 0 at the front, PI at the back
    if (style === "bun") return 0.5 - 0.36 * smooth(0.3, 1.25, phi) - 0.62 * smooth(1.9, 2.75, phi);
    return 0.56 - 0.34 * smooth(0.35, 1.3, phi) - 0.52 * smooth(1.95, 2.8, phi);
  };
  const keep: number[] = [];
  const u = new THREE.Vector3(), out = new THREE.Vector3();
  const maxLift = style === "short" ? 0.09 : 0.05;
  for (let i = 0; i < p.count; i += 3) {
    let cx = 0, cy = 0, cz = 0;
    for (let k = 0; k < 3; k += 1) {
      cx += p.getX(i + k) / 3;
      cy += p.getY(i + k) / 3;
      cz += p.getZ(i + k) / 3;
    }
    // Keep triangles that touch the hair region; vertices below the hairline are snapped onto it, so the edge is a
    // smooth curve rather than a staircase of triangles.
    let any = false;
    for (let k = 0; k < 3; k += 1) if (p.getY(i + k) >= hairline(p.getX(i + k), p.getZ(i + k))) any = true;
    if (!any || cy < hairline(cx, cz) - 0.12) continue;
    for (let k = 0; k < 3; k += 1) {
      u.set(p.getX(i + k), p.getY(i + k), p.getZ(i + k));
      const line = hairline(u.x, u.z);
      if (u.y < line) {
        const ring = Math.hypot(u.x, u.z) || 1;
        const r = Math.sqrt(Math.max(0, 1 - line * line));
        u.set((u.x / ring) * r, line, (u.z / ring) * r);
      }
      headPoint(u, out);
      const above = u.y - hairline(u.x, u.z);
      const crown = style === "short" ? 0.04 * Math.max(0, u.y) : 0.012 * Math.max(0, u.y);
      const lift = 1.006 + (maxLift + crown) * smooth(0, 0.16, above);
      out.multiplyScalar(lift);
      // Fine strands combed back from the hairline.
      out.addScaledVector(u, 0.0012 * Math.sin(Math.atan2(u.x, u.z) * 46 + u.y * 3) * smooth(0, 0.1, above));
      keep.push(out.x, out.y, out.z);
    }
  }
  const hair = new THREE.BufferGeometry();
  hair.setAttribute("position", new THREE.Float32BufferAttribute(keep, 3));
  hair.computeVertexNormals();
  g.dispose();
  return hair;
}

function frontZ(geometry: THREE.BufferGeometry, x: number, y: number): number {
  const p = geometry.getAttribute("position") as THREE.BufferAttribute;
  let best = Infinity, z = 0;
  for (let i = 0; i < p.count; i += 1) {
    if (p.getZ(i) <= 0) continue;
    const d = (p.getX(i) - x) ** 2 + (p.getY(i) - y) ** 2;
    if (d < best) {
      best = d;
      z = p.getZ(i);
    }
  }
  return z;
}

// --- Figure ----------------------------------------------------------------------------------------------------------

export function buildFigure(style: FigureStyle): Figure {
  const female = style.build === "f";
  const fabric = (color: number, sheen: number) => new THREE.MeshPhysicalMaterial({
    color, roughness: 0.86, sheen: 0.7, sheenRoughness: 0.75, sheenColor: new THREE.Color(color).lerp(new THREE.Color("#ffffff"), sheen),
  });
  const materials = {
    skin: new THREE.MeshPhysicalMaterial({ color: style.skin, roughness: 0.56, sheen: 0.3, sheenRoughness: 0.5, sheenColor: new THREE.Color("#ffb592") }),
    shirt: fabric(style.shirt, 0.35),
    trousers: fabric(style.trousers, 0.25),
    hair: new THREE.MeshPhysicalMaterial({ color: style.hair, roughness: 0.46, sheen: 0.55, sheenRoughness: 0.4, sheenColor: new THREE.Color(style.hair).lerp(new THREE.Color("#b9a796"), 0.45), side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }),
    shoes: new THREE.MeshStandardMaterial({ color: style.shoes, roughness: 0.62 }),
    sole: new THREE.MeshStandardMaterial({ color: style.sole ?? 0xe9e5dc, roughness: 0.8 }),
    eye: new THREE.MeshStandardMaterial({ color: 0x1b1714, roughness: 0.25 }),
    lip: new THREE.MeshStandardMaterial({ color: new THREE.Color(style.skin).lerp(new THREE.Color("#8a4a40"), 0.32), roughness: 0.5 }),
  };
  const geometries: THREE.BufferGeometry[] = [];
  const keep = <T extends THREE.BufferGeometry>(g: T): T => {
    geometries.push(g);
    return g;
  };

  const root = new THREE.Group();
  root.name = "Figure";
  const hips = new THREE.Group();
  hips.position.y = HIP_HEIGHT;
  root.add(hips);

  // Torso: trousers (pelvis) under an untucked shirt whose hem overlaps the waistband.
  const w = female ? 1 : 1.06;
  mesh(keep(loft([
    { y: -0.12, rx: 0.06, rz: 0.06 },
    { y: -0.08, rx: 0.14 * w, rz: 0.098 },
    { y: -0.01, rx: (female ? 0.166 : 0.155) * w, rz: 0.112, cz: -0.006 },
    { y: 0.06, rx: 0.152 * w, rz: 0.104, cz: -0.003 },
    { y: 0.1, rx: 0.144 * w, rz: 0.1 },
  ], 24)), materials.trousers, hips);
  mesh(keep(loft([
    { y: 0.0, rx: (female ? 0.166 : 0.162) * w, rz: 0.118, n: 2.2 },
    { y: 0.005, rx: (female ? 0.172 : 0.168) * w, rz: 0.122, n: 2.2 },
    { y: 0.07, rx: 0.158 * w, rz: 0.112, n: 2.3 },
    { y: 0.17, rx: (female ? 0.136 : 0.148) * w, rz: 0.102, n: 2.4 },
    { y: 0.27, rx: (female ? 0.146 : 0.16) * w, rz: female ? 0.11 : 0.106, cz: 0.005, n: 2.4 },
    { y: 0.34, rx: (female ? 0.154 : 0.17) * w, rz: female ? 0.12 : 0.11, cz: female ? 0.016 : 0.008, n: 2.4 },
    { y: 0.4, rx: (female ? 0.162 : 0.18) * w, rz: 0.104, cz: 0.006, n: 2.6 },
    { y: 0.445, rx: (female ? 0.15 : 0.168) * w, rz: 0.084, n: 2.6 },
    { y: 0.475, rx: 0.09, rz: 0.064 },
    { y: 0.49, rx: 0.062, rz: 0.054, cz: -0.004 },
  ], 26, 3, [false, true])), materials.shirt, hips);

  const chest = new THREE.Group();
  chest.position.y = 0.45;
  hips.add(chest);
  mesh(keep(loft([
    { y: 0.0, rx: female ? 0.056 : 0.062, rz: female ? 0.056 : 0.06, cz: -0.004 },
    { y: 0.05, rx: female ? 0.05 : 0.056, rz: female ? 0.052 : 0.056, cz: 0.002 },
    { y: 0.12, rx: female ? 0.047 : 0.052, rz: female ? 0.05 : 0.054, cz: 0.008 },
  ], 16)), materials.skin, chest);

  const head = new THREE.Group();
  head.position.set(0, 0.098, 0.01);
  chest.add(head);
  const skull = keep(headGeometry());
  const headCentre: [number, number, number] = [0, 0.1, 0.012];
  mesh(skull, materials.skin, head, headCentre);
  const face = new THREE.Group();
  face.position.set(...headCentre);
  head.add(face);
  const fz = (x: number, y: number) => frontZ(skull, x, y);
  // Nose, eyes, brows, lips and ears: restrained, so they read at story distances without looking uncanny.
  const nose = mesh(keep(loft([
    { y: 0.026, rx: 0.005, rz: 0.004 },
    { y: 0.0, rx: 0.009, rz: 0.009, cz: 0.005 },
    { y: -0.016, rx: 0.013, rz: 0.01, cz: 0.009 },
    { y: -0.023, rx: 0.01, rz: 0.006, cz: 0.006 },
  ], 12, 2)), materials.skin, face);
  nose.position.set(0, -0.006, fz(0, -0.01) - 0.008);
  for (const side of [-1, 1]) {
    const ex = side * 0.026, ey = 0.012;
    mesh(keep(new THREE.SphereGeometry(1, 14, 10)), materials.eye, face, [ex, ey, fz(ex, ey) - 0.0025], [0.0085, 0.0058, 0.004]);
    const brow = mesh(keep(new THREE.CapsuleGeometry(0.0028, 0.022, 3, 6)), materials.hair, face, [side * 0.029, 0.03, fz(side * 0.029, 0.03) + 0.001]);
    brow.rotation.z = Math.PI / 2 + side * 0.12;
    mesh(keep(new THREE.SphereGeometry(1, 12, 10)), materials.skin, face, [side * 0.077, 0.0, -0.006], [0.011, 0.026, 0.017]);
  }
  mesh(keep(new THREE.CapsuleGeometry(0.004, 0.016, 3, 8)), materials.lip, face, [0, -0.052, fz(0, -0.052) - 0.0015]).rotation.z = Math.PI / 2;
  const hairShell = mesh(keep(hairGeometry(style.hairStyle)), materials.hair, head, headCentre);
  hairShell.castShadow = true;
  if (style.hairStyle === "bun") {
    const bun = keep(new THREE.SphereGeometry(0.046, 18, 14));
    const bp = bun.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < bp.count; i += 1) {
      const a = Math.atan2(bp.getX(i), bp.getZ(i));
      const k = 1 + 0.06 * Math.sin(a * 6 + bp.getY(i) * 60);
      bp.setXYZ(i, bp.getX(i) * k, bp.getY(i), bp.getZ(i) * k);
    }
    bun.computeVertexNormals();
    mesh(bun, materials.hair, head, [0, headCentre[1] + 0.07, headCentre[2] - 0.098], [1, 0.9, 0.85]);
  }

  // Arms: deltoid cap and short sleeve over a skin upper arm, forearm, hand with jointed fingers.
  const hands: { fingers: Finger[]; thumb: Finger }[] = [];
  const makeArm = (side: 1 | -1) => {
    const shoulder = new THREE.Group();
    shoulder.position.set((female ? 0.166 : 0.184) * side, -0.014, -0.004);
    chest.add(shoulder);
    // Shoulder cap blends from the torso into the sleeve (flattened on top so it does not read as a ball).
    mesh(keep(new THREE.SphereGeometry(0.052, 18, 14)), materials.shirt, shoulder, [-side * 0.006, -0.012, 0], [female ? 1.0 : 1.08, 0.92, 1.02]);
    mesh(keep(loft([
      { y: 0.01, rx: 0.052, rz: 0.056 },
      { y: -0.05, rx: 0.054, rz: 0.057 },
      { y: -0.13, rx: 0.053, rz: 0.055 },
      { y: -0.145, rx: 0.047, rz: 0.049 },
    ], 18)), materials.shirt, shoulder);
    const upper = female ? 1.06 : 1.16;
    mesh(keep(loft([
      { y: -0.02, rx: 0.043 * upper, rz: 0.046 * upper },
      { y: -0.1, rx: 0.042 * upper, rz: 0.045 * upper },
      { y: -0.2, rx: 0.037 * upper, rz: 0.04 * upper },
      { y: -UPPER_ARM, rx: 0.031, rz: 0.033 },
    ], 16)), materials.skin, shoulder);
    const elbow = new THREE.Group();
    elbow.position.y = -UPPER_ARM;
    shoulder.add(elbow);
    mesh(keep(new THREE.SphereGeometry(0.032, 14, 10)), materials.skin, elbow);
    mesh(keep(loft([
      { y: 0.0, rx: 0.032, rz: 0.033 },
      { y: -0.05, rx: 0.037 * upper, rz: 0.034 },
      { y: -0.16, rx: 0.029, rz: 0.025 },
      { y: -FOREARM + 0.005, rx: 0.025, rz: 0.017 },
    ], 16)), materials.skin, elbow);
    const wrist = new THREE.Group();
    wrist.position.y = -FOREARM;
    elbow.add(wrist);
    // Palm (palm normal +z, fingers along -y).
    mesh(keep(loft([
      { y: 0.006, rx: 0.024, rz: 0.016 },
      { y: -0.02, rx: 0.033, rz: 0.016, cz: 0.001 },
      { y: -0.055, rx: 0.038, rz: 0.014 },
      { y: -0.082, rx: 0.037, rz: 0.012 },
      { y: -0.09, rx: 0.033, rz: 0.01 },
    ], 16, 2)), materials.skin, wrist);
    const fingers: Finger[] = [];
    const lengths = [0.068, 0.076, 0.072, 0.058];
    for (let i = 0; i < 4; i += 1) {
      // Index finger on the thumb side: the thumb sits at local x = side * 0.03.
      const fx = side * (0.026 - i * 0.017);
      const knuckle = new THREE.Group();
      knuckle.position.set(fx, -0.084, 0.001);
      wrist.add(knuckle);
      const l1 = lengths[i] * 0.55, l2 = lengths[i] * 0.45;
      const r = i === 3 ? 0.0068 : 0.0078;
      mesh(keep(new THREE.CapsuleGeometry(r, l1 - r * 2 + 0.006, 4, 12)), materials.skin, knuckle, [0, -l1 / 2, 0]);
      const mid = new THREE.Group();
      mid.position.y = -l1;
      knuckle.add(mid);
      mesh(keep(new THREE.CapsuleGeometry(r * 0.88, l2 - r * 1.76 + 0.004, 4, 12)), materials.skin, mid, [0, -l2 / 2, 0]);
      fingers.push([knuckle, mid]);
    }
    const thumbBase = new THREE.Group();
    thumbBase.position.set(side * 0.03, -0.022, 0.008);
    thumbBase.rotation.set(0, 0, side * 0.55);
    wrist.add(thumbBase);
    mesh(keep(new THREE.CapsuleGeometry(0.0102, 0.03, 4, 12)), materials.skin, thumbBase, [0, -0.022, 0]);
    const thumbTip = new THREE.Group();
    thumbTip.position.y = -0.044;
    thumbBase.add(thumbTip);
    mesh(keep(new THREE.CapsuleGeometry(0.009, 0.018, 4, 12)), materials.skin, thumbTip, [0, -0.016, 0]);
    hands.push({ fingers, thumb: [thumbBase, thumbTip] });
    return { shoulder, elbow, wrist };
  };
  const armL = makeArm(1);
  const armR = makeArm(-1);

  // Legs: straight-cut trousers over the knee, a slight hem break, and low shoes with a contrasting sole.
  const makeLeg = (side: 1 | -1) => {
    const hip = new THREE.Group();
    hip.position.set(0.088 * side, -0.04, 0);
    hips.add(hip);
    mesh(keep(loft([
      { y: 0.07, rx: 0.084, rz: 0.088 },
      { y: -0.04, rx: 0.084, rz: 0.088, cz: -0.004 },
      { y: -0.2, rx: 0.071, rz: 0.075 },
      { y: -0.35, rx: 0.06, rz: 0.062 },
      { y: -THIGH, rx: 0.056, rz: 0.058 },
    ], 18)), materials.trousers, hip);
    const knee = new THREE.Group();
    knee.position.y = -THIGH;
    hip.add(knee);
    mesh(keep(new THREE.SphereGeometry(0.056, 16, 12)), materials.trousers, knee);
    mesh(keep(loft([
      { y: 0.0, rx: 0.054, rz: 0.056 },
      { y: -0.1, rx: 0.053, rz: 0.058, cz: -0.006 },
      { y: -0.3, rx: 0.049, rz: 0.05 },
      { y: -SHIN + 0.035, rx: 0.052, rz: 0.054 },
      { y: -SHIN + 0.02, rx: 0.046, rz: 0.048 },
    ], 18)), materials.trousers, knee);
    // Shoe: a lofted last along +z, flattened underneath, on a sole.
    const shoe = keep(loft([
      { y: -0.055, rx: 0.036, rz: 0.03 },
      { y: -0.035, rx: 0.042, rz: 0.04 },
      { y: 0.04, rx: 0.046, rz: 0.042, cz: 0.004 },
      { y: 0.12, rx: 0.046, rz: 0.03, cz: 0.012 },
      { y: 0.165, rx: 0.036, rz: 0.019, cz: 0.016 },
      { y: 0.18, rx: 0.02, rz: 0.01, cz: 0.019 },
    ], 18, 2));
    shoe.rotateX(Math.PI / 2);
    const sp = shoe.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < sp.count; i += 1) if (sp.getY(i) < -0.028) sp.setY(i, -0.028);
    shoe.computeVertexNormals();
    mesh(shoe, materials.shoes, knee, [0, -SHIN - 0.004, 0.02]);
    const sole = keep(new THREE.CapsuleGeometry(0.044, 0.15, 4, 12));
    sole.rotateX(Math.PI / 2);
    mesh(sole, materials.sole, knee, [0, -SHIN - 0.04, 0.06], [1.02, 0.17, 1.02]);
    return { hip, knee };
  };
  const legL = makeLeg(1);
  const legR = makeLeg(-1);

  const joints: FigureJoints = {
    hips, chest, head,
    shoulderL: armL.shoulder, shoulderR: armR.shoulder,
    elbowL: armL.elbow, elbowR: armR.elbow,
    wristL: armL.wrist, wristR: armR.wrist,
    hipL: legL.hip, hipR: legR.hip,
    kneeL: legL.knee, kneeR: legR.knee,
    fingersL: hands[0].fingers, fingersR: hands[1].fingers,
    thumbL: hands[0].thumb, thumbR: hands[1].thumb,
  };

  return {
    root,
    joints,
    dispose() {
      geometries.forEach((g) => g.dispose());
      Object.values(materials).forEach((material) => material.dispose());
    },
  };
}

// --- Hands -----------------------------------------------------------------------------------------------------------

export interface Grip {
  /** Knuckle and middle-joint flexion (radians); positive curls the fingertips toward the palm (+z). */
  base: number;
  mid: number | readonly [number, number, number, number];
  /** Thumb flexion (radians) and how far it swings away from the fingers (radians). */
  thumb: number;
  thumbSpread: number;
  /** Fan between fingers (radians). */
  spread?: number;
}

export const GRIPS = {
  relaxed: { base: 0.3, mid: 0.45, thumb: 0.15, thumbSpread: 0.5, spread: 0.05 },
  // Fingers lie diagonally across the phone's back; only those reaching past its left edge wrap round it.
  phone: { base: 0.1, mid: [0.2, 0.85, 1.4, 1.5], thumb: 0.36, thumbSpread: 0.8, spread: 0.03 },
  typing: { base: 0.38, mid: 0.6, thumb: 0.25, thumbSpread: 0.6, spread: 0.06 },
} satisfies Record<string, Grip>;

/** Pose the fingers and thumb of one hand. */
export function setGrip(figure: Figure, side: "L" | "R", grip: Grip): void {
  const j = figure.joints;
  const fingers = side === "L" ? j.fingersL : j.fingersR;
  const s = side === "L" ? 1 : -1;
  fingers.forEach(([knuckle, mid], i) => {
    knuckle.rotation.set(-grip.base * (1 + i * 0.06), 0, s * (grip.spread ?? 0.04) * (i - 1.5));
    mid.rotation.set(-(typeof grip.mid === "number" ? grip.mid * (1 + i * 0.04) : grip.mid[i]), 0, 0);
  });
  const [base, tip] = side === "L" ? j.thumbL : j.thumbR;
  base.rotation.set(-grip.thumb * 0.6, 0, s * grip.thumbSpread);
  tip.rotation.set(-grip.thumb * 0.9, 0, 0);
}

// --- IK and poses ----------------------------------------------------------------------------------------------------

const tmp = {
  s: new THREE.Vector3(), d: new THREE.Vector3(), e: new THREE.Vector3(), pole: new THREE.Vector3(), t: new THREE.Vector3(),
  q: new THREE.Quaternion(), q2: new THREE.Quaternion(),
};

/**
 * Two-bone IK in world space: places the wrist at `targetWorld` (clamped to reach), bends the elbow toward `poleWorld`,
 * and, when given, orients the wrist to `handWorldQuat`.
 */
export function solveArm(
  shoulder: THREE.Group,
  elbow: THREE.Group,
  wrist: THREE.Group,
  targetWorld: THREE.Vector3,
  poleWorld: THREE.Vector3,
  handWorldQuat?: THREE.Quaternion,
): void {
  const a = UPPER_ARM, b = FOREARM;
  shoulder.parent!.updateWorldMatrix(true, false);
  const S = shoulder.getWorldPosition(tmp.s);
  const toTarget = tmp.d.copy(targetWorld).sub(S);
  const distance = Math.min(Math.max(toTarget.length(), 0.08), a + b - 1e-3);
  const dir = toTarget.normalize();
  const cosA = (a * a + distance * distance - b * b) / (2 * a * distance);
  const along = a * cosA;
  const h = Math.sqrt(Math.max(0, a * a - along * along));
  const pole = tmp.pole.copy(poleWorld).sub(S);
  pole.addScaledVector(dir, -pole.dot(dir));
  if (pole.lengthSq() < 1e-8) pole.set(0, -1, 0).addScaledVector(dir, -dir.y);
  pole.normalize();
  const E = tmp.e.copy(S).addScaledVector(dir, along).addScaledVector(pole, h);
  const T = tmp.t.copy(S).addScaledVector(dir, distance);

  const parentQuat = shoulder.parent!.getWorldQuaternion(tmp.q).invert();
  const upper = E.clone().sub(S).normalize().applyQuaternion(parentQuat);
  shoulder.quaternion.setFromUnitVectors(REST, upper);
  shoulder.updateWorldMatrix(false, false);
  const shoulderQuat = shoulder.getWorldQuaternion(tmp.q2).invert();
  const fore = T.clone().sub(E).normalize().applyQuaternion(shoulderQuat);
  // Keep the forearm's twist continuous with the upper arm (setFromUnitVectors picks the shortest arc).
  elbow.quaternion.setFromUnitVectors(REST, fore);
  if (handWorldQuat) {
    elbow.updateWorldMatrix(false, false);
    const elbowQuat = elbow.getWorldQuaternion(new THREE.Quaternion()).invert();
    wrist.quaternion.copy(elbowQuat.multiply(handWorldQuat));
  }
}

/**
 * Natural standing pose: weight on the left leg (slight contrapposto), relaxed arms with the palms toward the body,
 * a faint breathing motion. `look` pitches the head down (radians); `lean` brings the upper body forward.
 */
export function poseStanding(figure: Figure, look = 0, time = 0, lean = 0): void {
  const j = figure.joints;
  const breath = Math.sin(time * 1.5) * 0.008;
  j.hips.position.set(0.01, HIP_HEIGHT - 0.004, 0);
  j.hips.rotation.set(0, 0.02, 0.022);
  j.chest.rotation.set(0.03 + lean + breath, -0.02, -0.03);
  j.head.rotation.set(look - lean * 0.5 + breath * 0.5, 0.03 + Math.sin(time * 0.37) * 0.015, 0.02);
  j.shoulderL.rotation.set(0.06, 0, 0.17);
  j.elbowL.rotation.set(-0.3, 0, 0);
  j.wristL.rotation.set(0.05, -Math.PI / 2, 0.08);
  j.shoulderR.rotation.set(0.04, 0, -0.17);
  j.elbowR.rotation.set(-0.24, 0, 0);
  j.wristR.rotation.set(0.05, Math.PI / 2, -0.08);
  j.hipL.rotation.set(-0.01, 0, -0.012);
  j.kneeL.rotation.set(0.03, 0, 0);
  j.hipR.rotation.set(-0.13, 0.1, -0.035);
  j.kneeR.rotation.set(0.21, 0, 0);
  setGrip(figure, "L", GRIPS.relaxed);
  setGrip(figure, "R", GRIPS.relaxed);
}

/** Seated pose (chair seat about 0.48 m), leaning slightly toward the desk; arms are left for IK. */
export function poseSeated(figure: Figure, look = 0.12, time = 0): void {
  const j = figure.joints;
  const breath = Math.sin(time * 1.4) * 0.006;
  j.hips.position.set(0, 0.52, 0);
  j.hips.rotation.set(-0.08, 0, 0);
  j.chest.rotation.set(0.14 + breath, 0, 0);
  j.head.rotation.set(look - 0.08, 0, 0);
  j.hipL.rotation.set(-1.42, 0, 0.1);
  j.hipR.rotation.set(-1.46, 0, -0.08);
  j.kneeL.rotation.set(1.5, 0, 0);
  j.kneeR.rotation.set(1.36, 0, 0);
}
