import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

/**
 * The two people of the story as rigged models (built from the delivered characters by
 * `scripts/build-journey-characters.mjs`): the resident holding her phone and the responder typing at the desk.
 * Each file carries its bind (A) pose and one held pose (`PhoneHold`, `Typing`); this module reads those poses as
 * per-bone rotations and blends between them, so the story can raise the phone gradually and add a little life
 * (breathing, glances, typing fingers) without baked animation.
 */

export type Pose = Map<string, THREE.Quaternion>;

export interface Character {
  root: THREE.Group;
  bones: Map<string, THREE.Bone>;
  poses: Record<string, Pose>;
  hips: { bind: THREE.Vector3; posed: Record<string, THREE.Vector3> };
  meshes: THREE.Mesh[];
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

/** Mirror a bone-local rotation from one side to the other (the rig's sides are mirror images across x). */
function mirror(q: THREE.Quaternion): THREE.Quaternion {
  return new THREE.Quaternion(q.x, -q.y, -q.z, q.w);
}

const tmp = new THREE.Quaternion();
const axisX = new THREE.Vector3(1, 0, 0);
const axisY = new THREE.Vector3(0, 1, 0);

/** Set every bone from a blend of two poses (t = 0 → a, 1 → b). */
function applyBlend(character: Character, a: Pose, b: Pose, t: number): void {
  for (const [name, bone] of character.bones) {
    const qa = a.get(name), qb = b.get(name);
    if (qa && qb) bone.quaternion.slerpQuaternions(qa, qb, t);
    else if (qb ?? qa) bone.quaternion.copy((qb ?? qa)!);
  }
}

function bend(character: Character, name: string, radians: number, axis = axisX): void {
  const bone = character.bones.get(name);
  if (bone) bone.quaternion.multiply(tmp.setFromAxisAngle(axis, radians));
}

// --- The resident ----------------------------------------------------------------------------------------------------

const RIGHT_ARM_CHAIN = ["Shoulder", "Arm", "ForeArm", "ForeArmTwist1", "ForeArmTwist2", "Hand"];

/**
 * Builds the resident's relaxed pose from her phone pose: the right arm hangs like her (relaxed) left arm, mirrored,
 * while the right fingers keep their grip on the phone; the head and upper back come up from the screen.
 */
export function prepareResident(character: Character): void {
  const phone = character.poses.PhoneHold;
  const bind = character.poses.APose;
  const relaxed: Pose = new Map();
  for (const [name, q] of phone) relaxed.set(name, q.clone());
  for (const part of RIGHT_ARM_CHAIN) {
    const left = phone.get(`Left${part}`);
    if (left) relaxed.set(`Right${part}`, mirror(left));
  }
  for (const [name, amount] of [["Head", 0.7], ["Neck", 0.6], ["Spine2", 0.5]] as const) {
    const p = phone.get(name), r = bind.get(name);
    if (p && r) relaxed.set(name, p.clone().slerp(r, amount));
  }
  character.poses.Relaxed = relaxed;
}

/** raise 0 = phone at her side, 1 = reading it. */
export function poseResident(character: Character, raise: number, time: number): void {
  applyBlend(character, character.poses.Relaxed, character.poses.PhoneHold, raise);
  const breath = Math.sin(time * 1.5);
  bend(character, "Spine2", breath * 0.012);
  bend(character, "Neck", -breath * 0.006);
  // Small reading movements of the head while she looks at the screen.
  bend(character, "Head", Math.sin(time * 0.6) * 0.015 * raise, axisY);
  bend(character, "Head", Math.sin(time * 0.43 + 1) * 0.01 * raise);
}

// --- The responder ---------------------------------------------------------------------------------------------------

const FINGERS = ["Index", "Middle", "Ring", "Pinky"];

/** Typing at the keyboard: the held pose plus breathing and light, alternating finger presses. */
export function poseResponder(character: Character, attention: number, time: number): void {
  const typing = character.poses.Typing;
  applyBlend(character, typing, typing, 1);
  const breath = Math.sin(time * 1.4);
  bend(character, "Spine2", breath * 0.01);
  bend(character, "Head", -0.03 * attention + Math.sin(time * 0.5) * 0.01);
  FINGERS.forEach((finger, i) => {
    for (const side of ["Left", "Right"]) {
      const phase = time * 9 + i * 1.7 + (side === "Left" ? 0 : 2.3);
      const press = Math.max(0, Math.sin(phase)) ** 6 * 0.22 * attention;
      bend(character, `${side}Hand${finger}1`, press);
      bend(character, `${side}Hand${finger}2`, press * 0.6);
    }
  });
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
      const h = Math.min(height * 0.985, (width * 0.985) / aspect);
      screen.scale.set(h * aspect, h, 1);
    },
  };
}
