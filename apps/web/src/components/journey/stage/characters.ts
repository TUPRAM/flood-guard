import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { solveReach } from "@/lib/journey/reach";

/**
 * The two people of the story as rigged models (built from the delivered characters by
 * `scripts/build-journey-characters.mjs`): the resident holding her phone and the responder typing at the desk.
 * Each file carries its bind (A) pose and one held pose (`PhoneHold`, `Typing`). The held poses were made without the
 * scene, so this module fits them to it: the responder is seated on the room's chair with his feet on the floor and
 * his fingertips on the keyboard, and the resident's hand is closed around the phone it holds (fingers behind it,
 * thumb along its edge, nothing over the screen the real page is projected on). The story then blends between poses
 * and adds a little life (breathing, glances, tapping fingers) without baked animation.
 */

export type Pose = Map<string, THREE.Quaternion>;
type Side = "Left" | "Right";

export interface Character {
  root: THREE.Group;
  bones: Map<string, THREE.Bone>;
  poses: Record<string, Pose>;
  hips: { bind: THREE.Vector3; posed: Record<string, THREE.Vector3> };
  meshes: THREE.Mesh[];
  /** Where the seated responder's wrists stay and how his palms are turned, in his own space (`prepareResponder`). */
  hands?: Record<Side, { wrist: THREE.Vector3; palm: THREE.Quaternion }>;
}

const loader = new GLTFLoader();
// Embedded textures are decoded through image elements rather than `fetch(blob:)`: the site's Content-Security-Policy
// allows blob: images but not blob: connections, so the default ImageBitmap path would leave the people untextured.
loader.register((parser) => {
  parser.textureLoader = new THREE.TextureLoader(parser.options.manager);
  return { name: "floodguard_image_element_textures" };
});

export async function loadCharacter(url: string): Promise<Character> {
  const gltf = await loader.loadAsync(url);
  const root = gltf.scene as THREE.Group;
  const bones = new Map<string, THREE.Bone>();
  const meshes: THREE.Mesh[] = [];
  root.traverse((object) => {
    if ((object as THREE.Bone).isBone) bones.set(object.name, object as THREE.Bone);
    if ((object as THREE.Mesh).isMesh) {
      const mesh = object as THREE.Mesh;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      // Posed limbs leave the bind-pose bounds; two meshes are cheap to always draw.
      mesh.frustumCulled = false;
      const material = mesh.material as THREE.MeshStandardMaterial;
      if (material.isMeshStandardMaterial) material.envMapIntensity = 0.85;
      meshes.push(mesh);
    }
  });
  const poses: Record<string, Pose> = {};
  const posed: Record<string, THREE.Vector3> = {};
  for (const clip of gltf.animations) {
    const pose: Pose = new Map();
    for (const track of clip.tracks) {
      const [name, property] = track.name.split(".");
      if (property === "quaternion") pose.set(name, new THREE.Quaternion().fromArray(track.values, 0));
      if (property === "position" && name === "Hips") posed[clip.name] = new THREE.Vector3().fromArray(track.values, 0);
    }
    poses[clip.name] = pose;
  }
  const hipsBone = bones.get("Hips");
  return { root, bones, poses, hips: { bind: hipsBone ? hipsBone.position.clone() : new THREE.Vector3(), posed }, meshes };
}

// --- Rig helpers -----------------------------------------------------------------------------------------------------
// The rig's conventions: every bone runs along its local +y; fingers curl about +x; a hand's palm faces its +z.

const SIDES: readonly Side[] = ["Left", "Right"];
const FINGERS = ["Index", "Middle", "Ring", "Pinky"] as const;
type Digit = (typeof FINGERS)[number] | "Thumb";
const RADIANS = Math.PI / 180;

const tmp = new THREE.Quaternion();
const parentQuat = new THREE.Quaternion();
const turn = new THREE.Quaternion();
const axisX = new THREE.Vector3(1, 0, 0);
const axisY = new THREE.Vector3(0, 1, 0);
const axisZ = new THREE.Vector3(0, 0, 1);
const pointA = new THREE.Vector3(), pointB = new THREE.Vector3(), pointC = new THREE.Vector3();
const from = new THREE.Vector3(), to = new THREE.Vector3();

function need(character: Character, name: string): THREE.Bone {
  const bone = character.bones.get(name);
  if (!bone) throw new Error(`The character has no ${name} bone`);
  return bone;
}

/** Mirror a bone-local rotation from one side to the other (the rig's sides are mirror images across x). */
function mirror(q: THREE.Quaternion): THREE.Quaternion {
  return new THREE.Quaternion(q.x, -q.y, -q.z, q.w);
}

/** Set every bone from a blend of two poses (t = 0 → a, 1 → b). */
function applyBlend(character: Character, a: Pose, b: Pose, t: number): void {
  for (const [name, bone] of character.bones) {
    const qa = a.get(name), qb = b.get(name);
    if (qa && qb) bone.quaternion.slerpQuaternions(qa, qb, t);
    else if (qb ?? qa) bone.quaternion.copy((qb ?? qa)!);
  }
}

function snapshot(character: Character): Pose {
  const pose: Pose = new Map();
  for (const [name, bone] of character.bones) pose.set(name, bone.quaternion.clone());
  return pose;
}

function bend(character: Character, name: string, radians: number, axis = axisX): void {
  const bone = character.bones.get(name);
  if (bone) bone.quaternion.multiply(tmp.setFromAxisAngle(axis, radians));
}

/** Turn a bone to a rotation given in world space. */
function setWorldQuaternion(bone: THREE.Object3D, world: THREE.Quaternion): void {
  bone.quaternion.copy(bone.parent!.getWorldQuaternion(parentQuat).invert().multiply(world));
}

/** Turn a bone, in world space, by the shortest rotation that takes direction `a` to direction `b`. */
function swing(bone: THREE.Object3D, a: THREE.Vector3, b: THREE.Vector3): void {
  turn.setFromUnitVectors(a.normalize(), b.normalize());
  setWorldQuaternion(bone, bone.getWorldQuaternion(tmp).premultiply(turn));
}

/**
 * Two-bone reach: turns `upper` and `lower` so `end` (a wrist or an ankle) arrives at `target`, the middle joint
 * bending toward `pole` (both in world space). The bones keep the roll of the pose they start from.
 */
function reach(upper: THREE.Bone, lower: THREE.Bone, end: THREE.Bone, target: THREE.Vector3, pole: THREE.Vector3): void {
  upper.getWorldPosition(pointA);
  lower.getWorldPosition(pointB);
  end.getWorldPosition(pointC);
  const { joint, end: arrival } = solveReach(pointA, target, pole, pointA.distanceTo(pointB), pointB.distanceTo(pointC));
  swing(upper, from.subVectors(pointB, pointA), to.set(joint.x, joint.y, joint.z).sub(pointA));
  lower.getWorldPosition(pointB);
  end.getWorldPosition(pointC);
  swing(lower, from.subVectors(pointC, pointB), to.set(arrival.x, arrival.y, arrival.z).sub(pointB));
}

/** Share the hand's twist along the forearm (the rig's two twist bones turn a third and two thirds of it). */
function spreadTwist(character: Character, side: Side): void {
  const hand = character.bones.get(`${side}Hand`);
  if (!hand) return;
  tmp.set(0, hand.quaternion.y, 0, hand.quaternion.w);
  if (tmp.lengthSq() < 1e-10) tmp.identity();
  else tmp.normalize();
  if (tmp.w < 0) tmp.set(0, -tmp.y, 0, -tmp.w);
  character.bones.get(`${side}ForeArmTwist1`)?.quaternion.identity().slerp(tmp, 1 / 3);
  character.bones.get(`${side}ForeArmTwist2`)?.quaternion.identity().slerp(tmp, 2 / 3);
}

/**
 * Bend a finger or thumb from its straight bind pose: `flex` degrees at its three joints (toward the palm), and
 * `splay` degrees sideways at its base (toward the thumb's side of the hand; a thumb moves away from the fingers).
 */
function curl(character: Character, side: Side, digit: Digit, flex: readonly [number, number, number], splay = 0): void {
  const bind = character.poses.APose;
  flex.forEach((degrees, joint) => {
    const name = `${side}Hand${digit}${joint + 1}`;
    const bone = character.bones.get(name), rest = bind?.get(name);
    if (!bone || !rest) return;
    bone.quaternion.copy(rest);
    if (joint === 0 && splay) bone.quaternion.multiply(tmp.setFromAxisAngle(axisZ, (side === "Left" ? splay : -splay) * RADIANS));
    bone.quaternion.multiply(tmp.setFromAxisAngle(axisX, degrees * RADIANS));
  });
}

/** A rotation whose +y runs along `fingers` and whose +z faces `palm` (made square to it). */
function handRotation(fingers: THREE.Vector3, palm: THREE.Vector3): THREE.Quaternion {
  const y = fingers.clone().normalize();
  const z = palm.clone().addScaledVector(y, -palm.dot(y)).normalize();
  const x = new THREE.Vector3().crossVectors(y, z);
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
}

/** The skin's vertices that follow one of the chosen bones more than any other bone. */
function skinVertices(character: Character, follows: (bone: string) => boolean): { skin: THREE.SkinnedMesh; indices: number[] } {
  const skin = character.meshes.find((mesh): mesh is THREE.SkinnedMesh => (mesh as THREE.SkinnedMesh).isSkinnedMesh);
  if (!skin) throw new Error("The character has no skinned body");
  const bone = skin.geometry.getAttribute("skinIndex"), weight = skin.geometry.getAttribute("skinWeight");
  const indices: number[] = [];
  for (let i = 0; i < bone.count; i += 1) {
    let lead = 0;
    for (let k = 1; k < 4; k += 1) if (weight.getComponent(i, k) > weight.getComponent(i, lead)) lead = k;
    if (follows(skin.skeleton.bones[bone.getComponent(i, lead)].name)) indices.push(i);
  }
  return { skin, indices };
}

/** The lowest point (world space) of some of the skin's vertices in the current pose. */
function lowestPoint(character: Character, { skin, indices }: { skin: THREE.SkinnedMesh; indices: number[] }, out: THREE.Vector3): THREE.Vector3 {
  character.root.updateMatrixWorld(true);
  out.set(0, Infinity, 0);
  for (const index of indices) {
    skin.getVertexPosition(index, pointC).applyMatrix4(skin.matrixWorld);
    if (pointC.y < out.y) out.copy(pointC);
  }
  return out;
}

// --- The resident ----------------------------------------------------------------------------------------------------

const RIGHT_ARM_CHAIN = ["Shoulder", "Arm", "ForeArm", "ForeArmTwist1", "ForeArmTwist2", "Hand"];

/**
 * How the resident holds her phone (right hand), fitted to the model's hand and its 72 x 150 x 10 mm phone: her hand
 * is arched behind it, three fingers hook its far edge with their tips, her index finger lies along its back and her
 * thumb rests beside its near edge. Nothing crosses the front of the phone, because the real page is drawn over the
 * whole screen and would cut through anything in front of it. Angles in degrees, lengths in metres.
 */
const PHONE_GRIP = {
  /** Her wrist in the phone's space (x across the screen, y up it, z out of the glass toward the reader). */
  wrist: [0.044, -0.08, -0.032] as const,
  /** Her fingers point up and across the back of the phone, this far from its long axis. */
  across: 42,
  digits: {
    Thumb: { flex: [-24, 19, 27], splay: 8 },
    Index: { flex: [-19, 28, 25], splay: 2 },
    Middle: { flex: [-10, 60, 43], splay: 4 },
    Ring: { flex: [-6, 71, 56], splay: 10 },
    Pinky: { flex: [7, 63, 48], splay: 20 },
  } as Record<Digit, { flex: readonly [number, number, number]; splay: number }>,
};

/**
 * Builds the resident's two story poses from the delivered one. `Reading` keeps the phone exactly where the delivered
 * pose reads it (the camera work is built on that), re-seats it in her hand with the grip above and brings her arm
 * to it. `Relaxed` lets the same hand hang at her side like her relaxed left arm, mirrored, still holding the phone;
 * the head and upper back come up from the screen.
 */
export function prepareResident(character: Character): void {
  const held = character.poses.PhoneHold;
  const bind = character.poses.APose;
  const phone = character.root.getObjectByName("Phone");
  if (!held || !bind || !phone) throw new Error("The resident model has no phone pose");
  const upper = need(character, "RightArm"), lower = need(character, "RightForeArm"), hand = need(character, "RightHand");

  // Where the delivered pose reads the phone.
  applyBlend(character, held, held, 1);
  character.root.updateMatrixWorld(true);
  const phonePosition = phone.getWorldPosition(new THREE.Vector3());
  const phoneRotation = phone.getWorldQuaternion(new THREE.Quaternion());

  // The hand around the phone, in the phone's space; then the phone goes into the hand the other way round.
  const grip = PHONE_GRIP;
  const across = grip.across * RADIANS;
  const fingers = new THREE.Vector3(-Math.sin(across), Math.cos(across), 0);
  const handInPhone = new THREE.Matrix4().compose(new THREE.Vector3(...grip.wrist), handRotation(fingers, axisZ), new THREE.Vector3(1, 1, 1));
  handInPhone.clone().invert().decompose(phone.position, phone.quaternion, phone.scale);
  for (const digit of ["Thumb", ...FINGERS] as const) curl(character, "Right", digit, grip.digits[digit].flex, grip.digits[digit].splay);

  // Bring the arm to it: the wrist where the grip puts it, the elbow low and a little out from her side.
  const handWorld = new THREE.Matrix4().compose(phonePosition, phoneRotation, new THREE.Vector3(1, 1, 1)).multiply(handInPhone);
  const wrist = new THREE.Vector3(), handRotationWorld = new THREE.Quaternion();
  handWorld.decompose(wrist, handRotationWorld, new THREE.Vector3());
  const pole = upper.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(-0.35, -0.8, -0.25).applyQuaternion(character.root.getWorldQuaternion(new THREE.Quaternion())));
  reach(upper, lower, hand, wrist, pole);
  setWorldQuaternion(hand, handRotationWorld);
  spreadTwist(character, "Right");
  const reading = snapshot(character);
  character.poses.Reading = reading;

  const relaxed: Pose = new Map();
  for (const [name, q] of reading) relaxed.set(name, q.clone());
  for (const part of RIGHT_ARM_CHAIN) {
    const left = reading.get(`Left${part}`);
    if (left) relaxed.set(`Right${part}`, mirror(left));
  }
  for (const [name, amount] of [["Head", 0.7], ["Neck", 0.6], ["Spine2", 0.5]] as const) {
    const p = reading.get(name), r = bind.get(name);
    if (p && r) relaxed.set(name, p.clone().slerp(r, amount));
  }
  character.poses.Relaxed = relaxed;
}

/** raise 0 = phone at her side, 1 = reading it. */
export function poseResident(character: Character, raise: number, time: number): void {
  applyBlend(character, character.poses.Relaxed, character.poses.Reading, raise);
  const breath = Math.sin(time * 1.5);
  bend(character, "Spine2", breath * 0.012);
  bend(character, "Neck", -breath * 0.006);
  // Small reading movements of the head while she looks at the screen.
  bend(character, "Head", Math.sin(time * 0.6) * 0.015 * raise, axisY);
  bend(character, "Head", Math.sin(time * 0.43 + 1) * 0.01 * raise);
}

// --- The responder ---------------------------------------------------------------------------------------------------

/** The responder's place of work, in world space. */
export interface Workstation {
  /** The middle of the keyboard's home row, on the key tops. */
  keys: THREE.Vector3;
  /** The middle of the chair's cushion, on its top. */
  cushion: THREE.Vector3;
  /** Floor height under the desk. */
  floor: number;
}

/**
 * How the responder sits and types. Lengths in metres in his own space (x to his left, z ahead of him), angles in
 * degrees. Hands rest on the home row: fingers curved, palms turned a little toward each other, thumbs just clear of
 * the space bar's row.
 */
const TYPING = {
  /** His hip joints sit this far behind the middle of the cushion, which gives a little under him. */
  hipsBack: 0.1,
  cushionGive: 0.015,
  /** Feet: this far apart (each side of his middle) and this far ahead of his hips. */
  feetApart: 0.13,
  feetAhead: 0.4,
  /** Middle fingertips on the home row, this far each side of its middle; a hair above the keys at rest. */
  homeApart: 0.052,
  hover: 0.001,
  /** Hands point inward, rise a little toward the knuckles, and roll thumb-side up. */
  inward: 20,
  rise: 16,
  roll: 10,
  digits: {
    Thumb: { flex: [10, 12, 16], splay: -22 },
    Index: { flex: [28, 26, 18], splay: -2 },
    Middle: { flex: [24, 26, 18], splay: 4 },
    Ring: { flex: [24, 26, 18], splay: 8 },
    Pinky: { flex: [28, 24, 16], splay: 14 },
  } as Record<Digit, { flex: readonly [number, number, number]; splay: number }>,
  /** A tap lifts a fingertip by about this much before it comes back down on the key. */
  tap: 5,
};

/**
 * Seats the responder at his workstation and builds his `AtDesk` pose from the delivered `Typing` pose: hips on the
 * chair's cushion, feet flat on the floor, and each fingertip brought down onto the keyboard's home row (the knuckle
 * of each finger is bent until its tip meets the keys). His wrists are then held there every frame (`poseResponder`),
 * so breathing does not lift his hands off the keyboard. Call once the model stands at its seat.
 */
export function prepareResponder(character: Character, desk: Workstation): void {
  const typing = character.poses.Typing;
  const bind = character.poses.APose;
  if (!typing || !bind) throw new Error("The responder model has no typing pose");
  const { root } = character;
  const hips = need(character, "Hips");
  root.updateMatrixWorld(true);
  const rootRotation = root.getWorldQuaternion(new THREE.Quaternion());
  const own = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).applyMatrix4(root.matrixWorld);
  const keys = root.worldToLocal(desk.keys.clone());
  const cushion = root.worldToLocal(desk.cushion.clone());
  const floor = root.worldToLocal(new THREE.Vector3(desk.keys.x, desk.floor, desk.keys.z)).y;

  // Standing in the bind pose: how high the ankles are above the soles, and how a foot flat on the ground is turned.
  applyBlend(character, bind, bind, 1);
  hips.position.copy(character.hips.bind);
  const feet = SIDES.map((side) => {
    const foot = need(character, `${side}Foot`);
    const sole = lowestPoint(character, skinVertices(character, (name) => name === `${side}Foot` || name === `${side}ToeBase`), new THREE.Vector3());
    return { side, foot, ankle: foot.getWorldPosition(new THREE.Vector3()).y - sole.y, flat: foot.getWorldQuaternion(new THREE.Quaternion()) };
  });

  // Seated: the delivered pose, lowered until the underside of the pelvis and thighs is on the cushion.
  applyBlend(character, typing, typing, 1);
  const under = lowestPoint(character, skinVertices(character, (name) => name === "Hips" || name.endsWith("UpLeg")), new THREE.Vector3());
  const pelvisDepth = hips.getWorldPosition(new THREE.Vector3()).y - under.y;
  hips.position.set(0, cushion.y + pelvisDepth - TYPING.cushionGive, cushion.z - TYPING.hipsBack);

  // Feet flat on the floor, knees ahead.
  for (const { side, foot, ankle, flat } of feet) {
    const sign = side === "Left" ? 1 : -1;
    const thigh = need(character, `${side}UpLeg`), shin = need(character, `${side}Leg`);
    const target = own(sign * TYPING.feetApart, floor + ankle, hips.position.z + TYPING.feetAhead);
    const knee = thigh.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(sign * 0.04, 0.3, 1).applyQuaternion(rootRotation));
    reach(thigh, shin, foot, target, knee);
    setWorldQuaternion(foot, flat);
  }

  // Hands: palms down over the home row, then each finger lowered onto the keys.
  const hands = {} as Record<Side, { wrist: THREE.Vector3; palm: THREE.Quaternion }>;
  const tip = new THREE.Vector3(), wrist = new THREE.Vector3();
  const keyTop = desk.keys.y + TYPING.hover;
  for (const side of SIDES) {
    const sign = side === "Left" ? 1 : -1;
    const upper = need(character, `${side}Arm`), lower = need(character, `${side}ForeArm`), hand = need(character, `${side}Hand`);
    const inward = TYPING.inward * RADIANS, rise = TYPING.rise * RADIANS, roll = TYPING.roll * RADIANS;
    const fingers = new THREE.Vector3(-sign * Math.sin(inward) * Math.cos(rise), Math.sin(rise), Math.cos(inward) * Math.cos(rise));
    const palm = handRotation(fingers, new THREE.Vector3(-sign * Math.sin(roll), -Math.cos(roll), 0));
    const palmWorld = rootRotation.clone().multiply(palm);
    const elbow = () => upper.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(sign * 0.3, -1, -0.35).applyQuaternion(rootRotation));
    for (const digit of ["Thumb", ...FINGERS] as const) curl(character, side, digit, TYPING.digits[digit].flex, TYPING.digits[digit].splay);
    const tips = Object.fromEntries((["Thumb", ...FINGERS] as const).map((digit) => [digit, skinVertices(character, (name) => name === `${side}Hand${digit}3`)]));

    // Place the wrist so the middle fingertip is on its home key (the hand keeps its turn, so this is exact).
    const home = own(keys.x + sign * TYPING.homeApart, 0, keys.z).setY(keyTop);
    hand.getWorldPosition(wrist);
    for (let pass = 0; pass < 2; pass += 1) {
      reach(upper, lower, hand, wrist, elbow());
      setWorldQuaternion(hand, palmWorld);
      wrist.add(home).sub(lowestPoint(character, tips.Middle, tip));
    }
    reach(upper, lower, hand, wrist, elbow());
    setWorldQuaternion(hand, palmWorld);
    spreadTwist(character, side);

    // Lower every other fingertip onto the keys by its knuckle (the thumb onto the space bar's row, just clear of it).
    for (const digit of ["Thumb", "Index", "Ring", "Pinky"] as const) {
      const { flex, splay } = TYPING.digits[digit];
      const height = digit === "Thumb" ? keyTop + 0.004 : keyTop;
      let open = flex[0] - 30, closed = flex[0] + 30;
      for (let step = 0; step < 14; step += 1) {
        const middle = (open + closed) / 2;
        curl(character, side, digit, [middle, flex[1], flex[2]], splay);
        if (lowestPoint(character, tips[digit], tip).y > height) open = middle;
        else closed = middle;
      }
      curl(character, side, digit, [open, flex[1], flex[2]], splay);
    }
    hands[side] = { wrist: root.worldToLocal(hand.getWorldPosition(new THREE.Vector3())), palm };
  }
  character.poses.AtDesk = snapshot(character);
  character.hands = hands;
}

/** Typing at the keyboard: the seated pose plus breathing, a glance at the screen and light, alternating taps. */
export function poseResponder(character: Character, attention: number, time: number): void {
  const seated = character.poses.AtDesk ?? character.poses.Typing;
  applyBlend(character, seated, seated, 1);
  const breath = Math.sin(time * 1.4);
  bend(character, "Spine2", breath * 0.01);
  bend(character, "Head", -0.03 * attention + Math.sin(time * 0.5) * 0.01);
  if (!character.hands) return;
  // Breathing moves his shoulders; his wrists stay where the keys are.
  const rootRotation = character.root.getWorldQuaternion(new THREE.Quaternion());
  for (const side of SIDES) {
    const sign = side === "Left" ? 1 : -1;
    const upper = character.bones.get(`${side}Arm`), lower = character.bones.get(`${side}ForeArm`), hand = character.bones.get(`${side}Hand`);
    if (!upper || !lower || !hand) continue;
    const { wrist, palm } = character.hands[side];
    const pole = upper.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(sign * 0.3, -1, -0.35).applyQuaternion(rootRotation));
    reach(upper, lower, hand, character.root.localToWorld(wrist.clone()), pole);
    setWorldQuaternion(hand, rootRotation.clone().multiply(palm));
    spreadTwist(character, side);
    FINGERS.forEach((finger, i) => {
      const phase = time * 9 + i * 1.7 + (side === "Left" ? 0 : 2.3);
      const lift = Math.max(0, Math.sin(phase)) ** 6 * TYPING.tap * RADIANS * attention;
      bend(character, `${side}Hand${finger}1`, -lift);
    });
  }
}

// --- The held phone's screen -----------------------------------------------------------------------------------------

export interface HeldScreen {
  /** Unit plane scaled to the page size, on the phone's glass. */
  screen: THREE.Mesh;
  /** Fit the page (aspect = width / height) inside the phone's screen. */
  fit(aspect: number): void;
}

/**
 * Puts a page plane on the screen of the phone the model holds. The plane faces the reader and its up axis runs along
 * the phone's long side, so the projected page is upright on the device.
 */
export function attachScreen(character: Character, faceTarget: THREE.Vector3): HeldScreen | null {
  let glass: THREE.Mesh | null = null;
  character.root.traverse((object) => {
    if (object.name === "Phone_Screen" && (object as THREE.Mesh).isMesh) glass = object as THREE.Mesh;
  });
  if (!glass) return null;
  const mesh = glass as THREE.Mesh;
  character.root.updateMatrixWorld(true);
  mesh.geometry.computeBoundingBox();
  const box = mesh.geometry.boundingBox!;
  const size = box.getSize(new THREE.Vector3());
  const centre = box.getCenter(new THREE.Vector3());
  const axes = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
  const order = [0, 1, 2].sort((a, b) => size.getComponent(a) - size.getComponent(b));
  const normal = axes[order[0]].clone(), across = axes[order[1]].clone(), along = axes[order[2]].clone();
  const width = size.getComponent(order[1]), height = size.getComponent(order[2]);
  // Face the reader; keep the phone's top up.
  const worldQuat = mesh.getWorldQuaternion(new THREE.Quaternion());
  const worldCentre = mesh.localToWorld(centre.clone());
  if (normal.clone().applyQuaternion(worldQuat).dot(faceTarget.clone().sub(worldCentre)) < 0) normal.negate();
  if (along.clone().applyQuaternion(worldQuat).y < 0) along.negate();
  across.crossVectors(along, normal); // x = y × z
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: "#0d1416", toneMapped: false }));
  screen.name = "PhonePage";
  screen.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(across, along, normal));
  screen.position.copy(centre).addScaledVector(normal, size.getComponent(order[0]) / 2 + 0.0004);
  mesh.add(screen);
  return {
    screen,
    fit(aspect: number) {
      // Inset from the glass so a black border shows all round the page, as on a real phone.
      const inset = 0.88;
      const h = Math.min(height * inset, (width * inset) / aspect);
      screen.scale.set(h * aspect, h, 1);
    },
  };
}
