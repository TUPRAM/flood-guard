import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import * as THREE from "three";
import { describe, expect, it } from "vitest";

import {
  poseAtRest,
  poseResident,
  poseResponder,
  prepareLeaning,
  prepareResident,
  prepareResponder,
  prepareStanding,
  type Character,
  type Workstation,
} from "./characters";

/**
 * The rigged people, checked against what they hold and touch: the resident's hand around her phone (nothing over
 * the screen the real page is drawn on) and the responder's fingertips on the keyboard. The stage loads the models
 * with GLTFLoader, which needs a browser to decode textures; the rig, the skin and the held poses are enough here, so
 * this reads them straight from the files.
 */

const COMPONENTS = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array } as const;
const SIZES = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 } as const;

interface Gltf {
  accessors: Array<{ bufferView: number; byteOffset?: number; componentType: keyof typeof COMPONENTS; count: number; type: keyof typeof SIZES }>;
  bufferViews: Array<{ byteOffset?: number }>;
  nodes: Array<{ name: string; children?: number[]; mesh?: number; skin?: number; translation?: number[]; rotation?: number[]; scale?: number[] }>;
  meshes: Array<{ primitives: Array<{ attributes: Record<string, number>; indices: number }> }>;
  skins: Array<{ joints: number[]; inverseBindMatrices: number }>;
  animations?: Array<{ name: string; channels: Array<{ sampler: number; target: { node: number; path: string } }>; samplers: Array<{ output: number }> }>;
  scenes: Array<{ nodes: number[] }>;
}

function readCharacter(file: string): Character {
  const data = readFileSync(fileURLToPath(new URL(`../../../../public/journey/characters/${file}`, import.meta.url)));
  const jsonLength = data.readUInt32LE(12);
  const json = JSON.parse(data.subarray(20, 20 + jsonLength).toString("utf8")) as Gltf;
  const bin = data.subarray(20 + jsonLength + 8);
  const read = (index: number) => {
    const accessor = json.accessors[index];
    const Type = COMPONENTS[accessor.componentType];
    const length = accessor.count * SIZES[accessor.type];
    const start = (json.bufferViews[accessor.bufferView].byteOffset ?? 0) + (accessor.byteOffset ?? 0);
    return new Type(new Uint8Array(bin.subarray(start, start + length * Type.BYTES_PER_ELEMENT)).buffer);
  };

  const joints = new Set(json.skins.flatMap((skin) => skin.joints));
  const nodes = json.nodes.map((node, index) => {
    let object: THREE.Object3D;
    if (joints.has(index)) object = new THREE.Bone();
    else if (node.skin !== undefined && node.mesh !== undefined) {
      const { attributes, indices } = json.meshes[node.mesh].primitives[0];
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(read(attributes.POSITION), 3));
      geometry.setAttribute("skinIndex", new THREE.BufferAttribute(Uint16Array.from(read(attributes.JOINTS_0)), 4));
      const weights = read(attributes.WEIGHTS_0);
      const unit = weights instanceof Float32Array ? 1 : weights instanceof Uint8Array ? 1 / 255 : 1 / 65535;
      geometry.setAttribute("skinWeight", new THREE.BufferAttribute(Float32Array.from(weights, (weight) => weight * unit), 4));
      geometry.setIndex(new THREE.BufferAttribute(read(indices), 1));
      object = new THREE.SkinnedMesh(geometry);
    } else if (node.mesh !== undefined) {
      // A rigid part (the phone): its outline is all that is needed.
      const positions = json.meshes[node.mesh].primitives.flatMap((primitive) => Array.from(read(primitive.attributes.POSITION)));
      object = new THREE.Mesh(new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(Float32Array.from(positions), 3)));
    } else object = new THREE.Group();
    object.name = node.name;
    if (node.translation) object.position.fromArray(node.translation);
    if (node.rotation) object.quaternion.fromArray(node.rotation);
    if (node.scale) object.scale.fromArray(node.scale);
    return object;
  });
  json.nodes.forEach((node, index) => node.children?.forEach((child) => nodes[index].add(nodes[child])));
  const root = new THREE.Group();
  json.scenes[0].nodes.forEach((index) => root.add(nodes[index]));
  root.updateMatrixWorld(true);
  json.nodes.forEach((node, index) => {
    if (node.skin === undefined) return;
    const skin = json.skins[node.skin];
    const inverses = read(skin.inverseBindMatrices);
    const mesh = nodes[index] as THREE.SkinnedMesh;
    mesh.bind(new THREE.Skeleton(skin.joints.map((joint) => nodes[joint] as THREE.Bone), skin.joints.map((_, k) => new THREE.Matrix4().fromArray(inverses, k * 16))), mesh.matrixWorld);
  });

  const bones = new Map<string, THREE.Bone>();
  const meshes: THREE.Mesh[] = [];
  root.traverse((object) => {
    if ((object as THREE.Bone).isBone) bones.set(object.name, object as THREE.Bone);
    if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh);
  });
  const poses: Character["poses"] = {};
  const posed: Record<string, THREE.Vector3> = {};
  for (const clip of json.animations ?? []) {
    const pose = new Map<string, THREE.Quaternion>();
    for (const channel of clip.channels) {
      const name = json.nodes[channel.target.node].name;
      const values = read(clip.samplers[channel.sampler].output);
      if (channel.target.path === "rotation") pose.set(name, new THREE.Quaternion().fromArray(values, 0));
      if (channel.target.path === "translation" && name === "Hips") posed[clip.name] = new THREE.Vector3().fromArray(values, 0);
    }
    poses[clip.name] = pose;
  }
  if (!poses.APose) poses.APose = new Map([...bones].map(([name, bone]) => [name, bone.quaternion.clone()]));
  return { root, bones, poses, hips: { bind: bones.get("Hips")!.position.clone(), posed }, meshes };
}

/** World positions, in the current pose, of the skin's vertices that follow the chosen bones most. */
function skinPoints(character: Character, follows: (bone: string) => boolean): THREE.Vector3[] {
  const skin = character.meshes.find((mesh): mesh is THREE.SkinnedMesh => (mesh as THREE.SkinnedMesh).isSkinnedMesh)!;
  character.root.updateMatrixWorld(true);
  const bone = skin.geometry.getAttribute("skinIndex"), weight = skin.geometry.getAttribute("skinWeight");
  const points: THREE.Vector3[] = [];
  for (let i = 0; i < bone.count; i += 1) {
    let lead = 0;
    for (let k = 1; k < 4; k += 1) if (weight.getComponent(i, k) > weight.getComponent(i, lead)) lead = k;
    if (follows(skin.skeleton.bones[bone.getComponent(i, lead)].name)) points.push(skin.getVertexPosition(i, new THREE.Vector3()).applyMatrix4(skin.matrixWorld));
  }
  return points;
}

const lowest = (points: THREE.Vector3[]) => Math.min(...points.map((point) => point.y));
const MM = 0.001;

describe("the resident's hand on her phone", () => {
  const woman = readCharacter("phone-woman.glb");
  woman.root.position.set(-12, 1.4, 6);
  woman.root.rotation.y = -0.18;
  const phone = woman.root.getObjectByName("Phone")!;

  // Where the delivered pose reads the phone, before the grip is rebuilt.
  for (const [name, q] of woman.poses.PhoneHold) woman.bones.get(name)?.quaternion.copy(q);
  woman.root.updateMatrixWorld(true);
  const deliveredPosition = phone.getWorldPosition(new THREE.Vector3());
  const deliveredRotation = phone.getWorldQuaternion(new THREE.Quaternion());
  prepareResident(woman);

  // The phone's body and glass, from its own meshes (in the phone's space).
  const body = new THREE.Box3(), glass = new THREE.Box3();
  phone.updateMatrixWorld(true);
  const toPhone = phone.matrixWorld.clone().invert();
  phone.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh) return;
    const box = new THREE.Box3().setFromBufferAttribute(mesh.geometry.getAttribute("position") as THREE.BufferAttribute).applyMatrix4(toPhone.clone().multiply(mesh.matrixWorld));
    if (mesh.name === "Phone_Body") body.copy(box);
    if (mesh.name === "Phone_Screen") glass.copy(box);
  });
  const hand = (digit = "") => skinPoints(woman, (name) => name.startsWith(`RightHand${digit}`)).map((point) => point.applyMatrix4(phone.matrixWorld.clone().invert()));
  /** Distance from a point (phone space) to the phone's body: negative inside it. */
  const toBody = (point: THREE.Vector3) => {
    const centre = body.getCenter(new THREE.Vector3()), half = body.getSize(new THREE.Vector3()).multiplyScalar(0.5);
    const d = point.clone().sub(centre);
    d.set(Math.abs(d.x) - half.x, Math.abs(d.y) - half.y, Math.abs(d.z) - half.z);
    const outside = Math.hypot(Math.max(d.x, 0), Math.max(d.y, 0), Math.max(d.z, 0));
    return outside > 0 ? outside : Math.max(d.x, d.y, d.z);
  };

  it("reads the phone exactly where the delivered pose holds it", () => {
    poseResident(woman, 1, 0);
    woman.root.updateMatrixWorld(true);
    expect(phone.getWorldPosition(new THREE.Vector3()).distanceTo(deliveredPosition)).toBeLessThan(0.5 * MM);
    expect(phone.getWorldQuaternion(new THREE.Quaternion()).angleTo(deliveredRotation)).toBeLessThan(0.002);
  });

  it("keeps her hand off the front of the phone and out of its body, raised or at her side", () => {
    expect(body.getSize(new THREE.Vector3()).x).toBeGreaterThan(0.05);
    for (const raise of [0, 0.5, 1]) {
      poseResident(woman, raise, 1.3);
      const points = hand();
      expect(points.length).toBeGreaterThan(1000);
      // The real page is drawn over the screen: anything in front of the phone, inside its outline, would be cut off.
      const inFront = points.filter((point) => point.z > body.max.z && point.x > body.min.x && point.x < body.max.x && point.y > body.min.y && point.y < body.max.y);
      expect(inFront).toHaveLength(0);
      expect(Math.min(...points.map(toBody))).toBeGreaterThan(-1 * MM);
    }
    expect(glass.max.z).toBeCloseTo(body.max.z, 3);
  });

  it("holds it: thumb beside the near edge, three fingertips hooked on the far edge", () => {
    poseResident(woman, 1, 0);
    for (const digit of ["Thumb", "Middle", "Ring", "Pinky"]) {
      const tip = hand(`${digit}3`);
      expect(Math.min(...tip.map(toBody)), digit).toBeLessThan(2 * MM);
      const side = tip.reduce((sum, point) => sum + point.x, 0) / tip.length;
      if (digit === "Thumb") expect(side).toBeGreaterThan(body.max.x);
      else expect(side).toBeLessThan(body.min.x);
    }
  });
});

describe("the responder at his desk", () => {
  const FINGERS = ["Index", "Middle", "Ring", "Pinky"];
  /** A workstation like the operations room's, placed in the world: he faces +x. */
  const workstation = (keysAhead: number, keyTop: number): Workstation => ({
    keys: new THREE.Vector3(40 + keysAhead, 3 + keyTop, -20),
    cushion: new THREE.Vector3(40.1, 3.48, -20),
    floor: 3,
  });
  const seated = (desk: Workstation) => {
    const man = readCharacter("office-man.glb");
    man.root.position.set(40, 3, -20);
    man.root.rotation.y = Math.PI / 2;
    man.root.updateMatrixWorld(true);
    prepareResponder(man, desk);
    return man;
  };
  const tips = (man: Character, digit: string) => ["Left", "Right"].map((side) => lowest(skinPoints(man, (name) => name === `${side}Hand${digit}3`)));

  const desk = workstation(0.45, 0.7975);
  const man = seated(desk);

  it("rests every fingertip on the keys, thumbs over the space bar", () => {
    poseResponder(man, 0, 0);
    for (const finger of FINGERS) {
      for (const tip of tips(man, finger)) {
        expect(tip - desk.keys.y, finger).toBeGreaterThan(-0.5 * MM);
        expect(tip - desk.keys.y, finger).toBeLessThan(3 * MM);
      }
    }
    for (const tip of tips(man, "Thumb")) {
      expect(tip - desk.keys.y).toBeGreaterThan(0);
      expect(tip - desk.keys.y).toBeLessThan(12 * MM);
    }
  });

  it("keeps his hands on the keyboard while he breathes, and taps without going through the keys", () => {
    for (let time = 0; time < 9; time += 0.37) {
      poseResponder(man, 0, time);
      for (const tip of tips(man, "Middle")) expect(Math.abs(tip - desk.keys.y)).toBeLessThan(2.5 * MM);
      poseResponder(man, 1, time);
      for (const finger of FINGERS) {
        for (const tip of tips(man, finger)) {
          expect(tip - desk.keys.y).toBeGreaterThan(-0.5 * MM);
          expect(tip - desk.keys.y).toBeLessThan(16 * MM);
        }
      }
    }
  });

  it("sits on the cushion with his feet on the floor and his knees under the desk", () => {
    poseResponder(man, 1, 2);
    expect(Math.abs(lowest(skinPoints(man, (name) => /Foot|ToeBase/.test(name))) - desk.floor)).toBeLessThan(5 * MM);
    const hips = man.bones.get("Hips")!.getWorldPosition(new THREE.Vector3());
    // What he sits on: the underside of his pelvis and thighs, near his hip joints.
    const seat = lowest(skinPoints(man, (name) => name === "Hips" || name.endsWith("UpLeg")).filter((point) => Math.hypot(point.x - hips.x, point.z - hips.z) < 0.15));
    expect(seat - desk.cushion.y).toBeGreaterThan(-25 * MM);
    expect(seat - desk.cushion.y).toBeLessThan(10 * MM);
    expect(Math.hypot(hips.x - desk.cushion.x, hips.z - desk.cushion.z)).toBeLessThan(0.15);
    for (const side of ["Left", "Right"]) {
      const knee = man.bones.get(`${side}Leg`)!.getWorldPosition(new THREE.Vector3());
      expect(knee.y).toBeLessThan(desk.keys.y - 0.12);
      expect(knee.x).toBeGreaterThan(hips.x + 0.3);
    }
  });

  it("follows the furniture: a higher, farther keyboard is still reached", () => {
    const other = workstation(0.5, 0.83);
    const moved = seated(other);
    poseResponder(moved, 0, 0);
    for (const finger of FINGERS) {
      for (const tip of tips(moved, finger)) expect(Math.abs(tip - other.keys.y), finger).toBeLessThan(3 * MM);
    }
  });
});

describe("Mali, Dao and Pim (Meshy rigs)", () => {
  const people = { mali: 1.52, dao: 1.28, pim: 1.58 } as const;
  const placed = (id: keyof typeof people) => {
    const person = readCharacter(`${id}.glb`);
    person.root.position.set(-11, 1.4, 5);
    person.root.rotation.y = -0.75;
    person.root.updateMatrixWorld(true);
    return person;
  };
  const top = (person: Character) => Math.max(...skinPoints(person, () => true).map((point) => point.y));

  it("stand at their heights on the ground, with the bone names the stage reads", () => {
    for (const [id, height] of Object.entries(people) as Array<[keyof typeof people, number]>) {
      const person = placed(id);
      expect(Math.abs(lowest(skinPoints(person, () => true)) - 1.4), id).toBeLessThan(10 * MM);
      expect(Math.abs(top(person) - 1.4 - height), id).toBeLessThan(20 * MM);
      for (const bone of ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftArm", "RightForeArm", "LeftHandMiddle1", "RightHandPinky1"]) {
        expect(person.bones.has(bone), `${id} ${bone}`).toBe(true);
      }
    }
  });

  it("let their arms hang at their sides and keep their feet on the ground while they breathe", () => {
    for (const id of ["mali", "dao"] as const) {
      const person = placed(id);
      prepareStanding(person, { stoop: 0.12 });
      for (const time of [0, 1.1, 2.7]) {
        poseAtRest(person, "Standing", time);
        expect(Math.abs(lowest(skinPoints(person, (name) => /Foot|Toe/.test(name))) - 1.4), id).toBeLessThan(15 * MM);
        const hips = person.bones.get("Hips")!.getWorldPosition(new THREE.Vector3());
        for (const side of ["Left", "Right"]) {
          const at = (bone: string) => person.bones.get(`${side}${bone}`)!.getWorldPosition(new THREE.Vector3());
          const wrist = at("Hand"), shoulder = at("Arm");
          const length = shoulder.distanceTo(at("ForeArm")) + at("ForeArm").distanceTo(wrist);
          // Hanging: the wrist almost an arm's length below the shoulder, close to the body.
          expect(shoulder.y - wrist.y, `${id} ${side}`).toBeGreaterThan(0.9 * length);
          expect(Math.hypot(wrist.x - hips.x, wrist.z - hips.z), `${id} ${side}`).toBeLessThan(0.3);
        }
      }
    }
  });

  it("turns Dao's face up toward her mother", () => {
    const dao = placed("dao");
    const head = dao.bones.get("Head")!;
    const restFace = new THREE.Vector3(0, 0, 1).applyQuaternion(dao.root.quaternion);
    const rest = head.getWorldQuaternion(new THREE.Quaternion());
    const mother = dao.root.position.clone().add(new THREE.Vector3(-0.5, 1.5, 0.3));
    prepareStanding(dao, { lookAt: mother });
    poseAtRest(dao, "Standing", 0);
    const face = restFace.clone().applyQuaternion(head.getWorldQuaternion(new THREE.Quaternion()).multiply(rest.clone().invert()));
    const toMother = mother.clone().sub(head.getWorldPosition(new THREE.Vector3())).normalize();
    expect(face.y).toBeGreaterThan(0.2);
    expect(face.angleTo(toMother)).toBeLessThan(0.35);
  });

  it("rests Pim's palms on the table's rim", () => {
    const pim = readCharacter("pim.glb");
    pim.root.position.set(30, 3, -9.2);
    pim.root.updateMatrixWorld(true);
    const rim = { y: 3.92, z: -8.92 };
    const palms = { Left: new THREE.Vector3(30.24, rim.y, rim.z), Right: new THREE.Vector3(29.76, rim.y, rim.z) };
    prepareLeaning(pim, palms, new THREE.Vector3(29.6, rim.y, -8.3));
    for (const time of [0, 1.7]) {
      poseAtRest(pim, "Leaning", time, 0);
      for (const side of ["Left", "Right"] as const) {
        const hand = skinPoints(pim, (name) => name.startsWith(`${side}Hand`));
        expect(Math.abs(lowest(hand) - rim.y), side).toBeLessThan(3 * MM);
        const centre = hand.reduce((sum, point) => sum.add(point), new THREE.Vector3()).divideScalar(hand.length);
        expect(Math.hypot(centre.x - palms[side].x, centre.z - palms[side].z), side).toBeLessThan(0.1);
      }
      expect(Math.abs(lowest(skinPoints(pim, (name) => /Foot|Toe/.test(name))) - 3), "feet").toBeLessThan(15 * MM);
    }
  });
});
