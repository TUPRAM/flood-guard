import * as THREE from "three";

import { PHONE_PAGE_FILL, type Quad } from "@/lib/journey/screen-projection";
import { BACK_STREET_Z, LAYOUT, ROAD_Z, SIDE_STREETS_X, WATER_LEVEL, terrainHeight, waterLevelBetween } from "@/lib/journey/terrain";
import { locate, type SegmentId } from "@/lib/journey/timeline";

import {
  Parts,
  architectureMaterials,
  architectureTextures,
  buildClinic,
  buildHouse,
  homeSpec,
  houseTopHeight,
  mergeParts,
  neighbourhoodSpecs,
  type HouseSpec,
} from "./architecture";
import {
  attachScreen,
  loadCharacter,
  poseResident as poseResidentModel,
  poseResponder as poseResponderModel,
  prepareResident,
  prepareResponder,
  type Character,
  type HeldScreen,
} from "./characters";
import { GRIPS, buildFigure, poseSeated, poseStanding, setGrip, solveArm, type Figure } from "./figure";
import { contactShadowTexture, type Quality } from "./materials";
import { buildOperations, type OperationsBuilding } from "./operations";
import { buildVegetation, type Vegetation } from "./vegetation";
import {
  alertTexture,
  buildConnection,
  buildContactShadows,
  buildEnvironmentScene,
  buildPhone,
  buildRain,
  buildRoads,
  buildSky,
  buildTerrain,
  buildWater,
  tableTexture,
  type Connection,
  type Phone,
  type WaterUniforms,
  type WetUniforms,
} from "./world";

export type ScreenId = "phone" | "monitor" | "table";

/** Compiled into this chunk so the offline installer treats the 3D stage as online-only (write-offline-assets.mjs). */
export const JOURNEY_CHUNK_MARKER = "data-floodguard-journey";

export interface ScreenFrame {
  quad: Quad | null;
  /** 0..1: how much of the real page is shown on this screen. */
  opacity: number;
}

export interface LabelFrame {
  id: string;
  x: number;
  y: number;
  visible: boolean;
}

export interface StageFrame {
  screens: Record<ScreenId, ScreenFrame>;
  labels: LabelFrame[];
}

export interface StageViewport {
  width: number;
  height: number;
}

/** Real-page CSS sizes are chosen by the host; the stage only needs each screen's aspect. */
export interface ScreenAspects {
  phone: number;
  monitor: number;
  table: number;
}

interface Key {
  at: number;
  pos: THREE.Vector3;
  target: THREE.Vector3;
  up?: THREE.Vector3;
  /** A waypoint the camera glides through without settling (it only shapes the path). */
  pass?: boolean;
}

const Y = new THREE.Vector3(0, 1, 0);
const NORTH = new THREE.Vector3(0, 0, -1);
const PHONE_SCREEN_HEIGHT = 0.15;
const MONITOR_WIDTH = 0.66;
const TABLE_WIDTH = 2.9;

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
/** 0→1 as `value` goes from a to b, smoothed. */
const ramp = (value: number, a: number, b: number) => {
  const t = clamp01((value - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

function catmull(p0: THREE.Vector3, p1: THREE.Vector3, p2: THREE.Vector3, p3: THREE.Vector3, t: number, out: THREE.Vector3): THREE.Vector3 {
  const t2 = t * t, t3 = t2 * t;
  return out.set(
    0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
    0.5 * (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
    0.5 * (2 * p1.z + (-p0.z + p2.z) * t + (2 * p0.z - 5 * p1.z + 4 * p2.z - p3.z) * t2 + (-p0.z + 3 * p1.z - 3 * p2.z + p3.z) * t3),
  );
}

/**
 * Camera pose along keyframes at segment progress p. Each glide between two keys eases in and out on its own, so the
 * camera settles on every shot (and a hold, two equal keys, lasts exactly as long as its keys say).
 */
function samplePath(keys: Key[], p: number, outPos: THREE.Vector3, outTarget: THREE.Vector3, outUp: THREE.Vector3): void {
  const x = clamp01(p);
  // Ease between the keys the camera settles on; pass-through waypoints keep the motion going.
  let s0 = 0;
  for (let k = 1; k < keys.length - 1; k += 1) if (!keys[k].pass && keys[k].at <= x) s0 = k;
  let s1 = keys.length - 1;
  for (let k = keys.length - 2; k > s0; k -= 1) if (!keys[k].pass) s1 = k;
  const span = Math.max(1e-6, keys[s1].at - keys[s0].at);
  const e = keys[s0].at + easeInOut(clamp01((x - keys[s0].at) / span)) * span;
  let i = s0;
  while (i < s1 - 1 && e > keys[i + 1].at) i += 1;
  const a = keys[i], b = keys[i + 1];
  const local = clamp01((e - a.at) / Math.max(1e-6, b.at - a.at));
  const k0 = keys[Math.max(0, i - 1)], k3 = keys[Math.min(keys.length - 1, i + 2)];
  catmull(k0.pos, a.pos, b.pos, k3.pos, local, outPos);
  catmull(k0.target, a.target, b.target, k3.target, local, outTarget);
  outUp.copy(a.up ?? Y).lerp(b.up ?? Y, local).normalize();
}

export interface StageOptions {
  quality: Quality;
}

export class JourneyStage {
  readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(40, 1, 0.01, 900);
  private readonly quality: Quality;
  private viewport: StageViewport = { width: 1, height: 1 };
  private aspects: ScreenAspects = { phone: 0.4615, monitor: 1.6, table: 1.6 };
  private readonly disposables: Array<{ dispose(): void }> = [];

  private readonly water: THREE.Mesh;
  private readonly waterNormal: THREE.Texture;
  private readonly waterUniforms: WaterUniforms;
  private readonly wet: WetUniforms;
  private readonly rain: ReturnType<typeof buildRain>;
  private readonly sky: ReturnType<typeof buildSky>;
  private readonly sun: THREE.DirectionalLight;
  private readonly sunDir = new THREE.Vector3(-0.52, 0.66, 0.54).normalize();
  private readonly hemi: THREE.HemisphereLight;
  private readonly connection: Connection;
  private readonly ops: OperationsBuilding;
  private vegetation!: Vegetation;
  private readonly resident: Figure;
  private readonly responder: Figure;
  private readonly residentShadow: THREE.Mesh;
  private readonly phone: Phone;
  private readonly signal: { tube: THREE.Mesh; head: THREE.Mesh; curve: THREE.QuadraticBezierCurve3; material: THREE.MeshBasicMaterial };
  private readonly anchors: Record<string, THREE.Vector3>;
  private shadowExtent = 0;
  private shadowKey = "";
  private residentCastsShadow = true;
  /** The page plane the real public app is projected onto: the procedural phone's until the rigged resident loads. */
  private phoneScreen!: THREE.Mesh;
  private residentModel: Character | null = null;
  private responderModel: Character | null = null;
  private heldScreen: HeldScreen | null = null;
  private disposed = false;
  /** Resolves when the rigged people are in the scene (or failed to load; the procedural figures then stay). */
  readonly charactersReady: Promise<void>;
  /** Adaptive resolution: the pixel ratio steps down on slow GPUs and back up when there is headroom. */
  private readonly maxPixelRatio: number;
  private pixelRatio: number;
  private frameAverage = 1 / 60;
  private sinceResize = 0;
  private time = 0;

  private readonly scratch = { pos: new THREE.Vector3(), target: new THREE.Vector3(), up: new THREE.Vector3(), v: new THREE.Vector3(), w: new THREE.Vector3(), q: new THREE.Quaternion(), m: new THREE.Matrix4() };

  constructor(canvas: HTMLCanvasElement, options: StageOptions) {
    this.quality = options.quality;
    const high = options.quality === "high";
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance", alpha: false });
    this.maxPixelRatio = Math.min(window.devicePixelRatio || 1, high ? 1.75 : 1.25);
    this.pixelRatio = Math.min(this.maxPixelRatio, 1.5);
    this.renderer.setPixelRatio(this.pixelRatio);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    // Neutral tone mapping keeps the brand palette's hues (ACES shifted the greens and creams).
    this.renderer.toneMapping = THREE.NeutralToneMapping;
    this.renderer.toneMappingExposure = 0.92;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;

    // Image-based light from an outdoor sky (warm ground bounce, sun disc) instead of a studio room.
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const envScene = buildEnvironmentScene(this.sunDir);
    const environment = pmrem.fromScene(envScene, 0.02).texture;
    envScene.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.geometry.dispose();
        (object.material as THREE.Material).dispose();
      }
    });
    this.scene.environment = environment;
    this.scene.environmentIntensity = 0.75;
    pmrem.dispose();
    this.disposables.push(environment);

    this.scene.userData.marker = JOURNEY_CHUNK_MARKER;
    this.scene.fog = new THREE.Fog("#e9e6dc", 90, 360);
    this.sky = buildSky();
    this.sky.material.uniforms.uSunDir.value.copy(this.sunDir);
    this.scene.add(this.sky.mesh);

    this.hemi = new THREE.HemisphereLight("#eef0ea", "#8a8466", 0.42);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight("#fff0d8", 3.1);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(high ? 2048 : 1024, high ? 2048 : 1024);
    this.sun.shadow.radius = high ? 3 : 2;
    this.sun.shadow.bias = -0.0003;
    this.sun.shadow.normalBias = 0.025;
    this.sun.shadow.camera.near = 1;
    this.sun.shadow.camera.far = 320;
    this.scene.add(this.sun, this.sun.target);

    // Architecture: houses (merged per material) and the clinic.
    const textures = architectureTextures();
    const materials = architectureMaterials(textures);
    Object.values(textures).forEach((texture) => this.disposables.push(texture));
    Object.values(materials).forEach((material) => this.disposables.push(material));
    const home = homeSpec();
    const avoid = (x: number, z: number) => {
      if (Math.abs(x - 2) < 12 && z > -12) return true; // the swale
      if (Math.abs(x - LAYOUT.clinic.x) < 13 && z > -12) return true;
      if (Math.abs(x - LAYOUT.home.x) < 10 && z > -12) return true;
      if (Math.abs(x - LAYOUT.operations.x) < 15 && z < -20) return true;
      return false;
    };
    const specs: HouseSpec[] = [...neighbourhoodSpecs(options.quality, avoid, SIDE_STREETS_X), home];
    const parts = new Parts();
    specs.forEach((spec) => buildHouse(parts, spec));
    this.scene.add(mergeParts(parts, materials, "Houses"));
    const clinic = buildClinic(materials, textures);
    this.scene.add(clinic.group);

    // Ground features: yards and driveways from the houses; footprints for vegetation and contact shadows.
    const yards = specs.filter((spec) => spec.fence).map((spec) => {
      const c = Math.cos(spec.rotation), s = Math.sin(spec.rotation);
      const lz = spec.d / 2 + spec.yard / 2;
      return { x: spec.x + lz * s, z: spec.z + lz * c, w: spec.w + 2.6, d: spec.yard, rotation: spec.rotation };
    });
    const pads = specs.filter((spec) => spec.fence).map((spec) => {
      const fence = spec.z + spec.d / 2 + spec.yard;
      const street = spec.z > -12 ? ROAD_Z - 3.2 - 1.6 : BACK_STREET_Z - 2.2;
      return { x: spec.x + spec.gateX, z: (fence + street) / 2, w: 3.0, d: Math.max(0.2, street - fence) };
    });
    pads.push({ x: LAYOUT.clinic.x, z: LAYOUT.clinic.z + 4.5 + 3.4, w: 9, d: 2.2 });
    const terrain = buildTerrain(options.quality, { yards, pads });
    this.wet = terrain.uniforms;
    this.scene.add(terrain.mesh);
    this.disposables.push(terrain.mesh.userData.detail as THREE.Texture);
    const water = buildWater();
    this.water = water.mesh;
    this.waterNormal = water.normalMap;
    this.waterUniforms = water.uniforms;
    this.water.position.y = WATER_LEVEL.dry;
    this.scene.add(this.water);
    this.scene.add(buildRoads(options.quality, this.wet).group);

    this.ops = buildOperations(alertTexture(), tableTexture());
    this.scene.add(this.ops.group);
    this.disposables.push(this.ops);

    const footprints = [
      ...specs.map((spec) => ({ x: spec.x, z: spec.z + (spec.fence ? spec.yard / 2 : 0), w: spec.w + 3, d: spec.d + (spec.fence ? spec.yard : 0) + 1.5 })),
      { x: LAYOUT.clinic.x + 2.6, z: LAYOUT.clinic.z + 1.6, w: 25, d: 13 },
      this.ops.footprint,
    ];
    this.scene.add(buildContactShadows([
      ...specs.map((spec) => ({ x: spec.x, z: spec.z, w: spec.w + 1.7, d: spec.d + 1.7, rotation: spec.rotation })),
      { x: LAYOUT.clinic.x, z: LAYOUT.clinic.z, w: 17.6, d: 10.6, rotation: 0 },
      { x: this.ops.footprint.x, z: this.ops.footprint.z, w: this.ops.footprint.w + 1.2, d: this.ops.footprint.d + 1.2, rotation: 0 },
    ]));

    this.connection = buildConnection();
    this.scene.add(this.connection.group);
    this.rain = buildRain(options.quality);
    this.scene.add(this.rain.mesh);

    // Resident at the garden gate, facing the road (+z), in clothes that suit a warm climate.
    this.resident = buildFigure({ skin: 0xc4957a, shirt: 0xa7644b, trousers: 0x4a4d45, hair: 0x221a16, shoes: 0xd9d4ca, sole: 0xf1eee8, hairStyle: "bun", build: "f" });
    this.resident.root.position.set(LAYOUT.resident.x, terrainHeight(LAYOUT.resident.x, LAYOUT.resident.z), LAYOUT.resident.z);
    this.resident.root.rotation.y = -0.18;
    this.scene.add(this.resident.root);
    this.phone = buildPhone();
    this.scene.add(this.phone.group);
    this.phoneScreen = this.phone.screen;
    this.disposables.push(this.phone);
    const blob = contactShadowTexture(0.1, 0.38);
    this.disposables.push(blob);
    const blobMaterial = new THREE.MeshBasicMaterial({ color: "#1b1f19", alphaMap: blob, transparent: true, opacity: 0.55, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
    this.residentShadow = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), blobMaterial);
    this.residentShadow.rotation.x = -Math.PI / 2;
    this.residentShadow.position.copy(this.resident.root.position).add(v(0, 0.02, 0.02));
    this.scene.add(this.residentShadow);

    // Responder seated at the desk, facing the monitor (+x).
    this.responder = buildFigure({ skin: 0xa77a5e, shirt: 0x3d6466, trousers: 0x2f3437, hair: 0x1f1a17, shoes: 0x2b2826, sole: 0x2b2826, hairStyle: "short", build: "m" });
    this.responder.root.position.copy(this.ops.seat);
    this.responder.root.rotation.y = Math.PI / 2;
    this.scene.add(this.responder.root);

    // Simulated SOS signal: an arc from the resident to the operations window.
    const start = this.resident.root.position.clone().add(v(0, 1.4, 0));
    const end = this.ops.window.clone().add(v(0, 0.2, 1));
    const control = start.clone().lerp(end, 0.5).add(v(0, 26, 6));
    const curve = new THREE.QuadraticBezierCurve3(start, control, end);
    const signalMaterial = new THREE.MeshBasicMaterial({ color: "#e7a54f", transparent: true, opacity: 0.9 });
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 160, 0.07, 6), signalMaterial);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.45, 20, 14), signalMaterial);
    tube.visible = head.visible = false;
    this.scene.add(tube, head);
    this.signal = { tube, head, curve, material: signalMaterial };

    const r = this.resident.root.position;
    this.anchors = {
      resident: r.clone(),
      home: v(LAYOUT.home.x, houseTopHeight(home) + 3.4, LAYOUT.home.z),
      clinic: v(LAYOUT.clinic.x, clinic.top + 1.6, LAYOUT.clinic.z),
      connection: this.connection.midDry.clone().add(v(0, 1.2, 0)),
      crossing: this.connection.crossingMid.clone().add(v(0, 1.2, 0)),
      operations: v(LAYOUT.operations.x, this.ops.floor + 7.6, LAYOUT.operations.z),
    };

    this.disposables.push(this.resident, this.responder);

    // Vegetation last: it keeps clear of the camera's actual path through the story.
    this.phone.resize(PHONE_SCREEN_HEIGHT * this.aspects.phone, PHONE_SCREEN_HEIGHT);
    this.ops.setMonitorSize(MONITOR_WIDTH, MONITOR_WIDTH / this.aspects.monitor);
    this.ops.setTableSize(TABLE_WIDTH, TABLE_WIDTH / this.aspects.table);
    this.poseResident(1, 0);
    this.vegetation = buildVegetation({ quality: options.quality, footprints, clearance: this.cameraSamples() });
    this.scene.add(this.vegetation.group);
    this.disposables.push(this.vegetation);
    this.charactersReady = this.loadCharacters().catch(() => {
      // Keep the procedural figures (offline, blocked or failed download).
    });
  }

  /**
   * The push-ins end where the person's eyes are (the phone) or in front of their face (the monitor). As the camera
   * gets there, the resident's head is folded away (a first-person view of her phone); the responder is hidden once
   * the camera is ahead of his shoulders, when he is already out of the frame, so neither fills the frame around the
   * real page.
   */
  private clearCloseUps(camera: THREE.Vector3): void {
    const woman = this.residentModel;
    if (woman) {
      const neck = woman.bones.get("Neck"), head = woman.bones.get("Head");
      if (neck && head) {
        const eyes = neck.getWorldPosition(this.scratch.v).add(v(0, 0.14, 0));
        head.scale.setScalar(camera.distanceTo(eyes) < 0.42 ? 0.001 : 1);
      }
    }
    const man = this.responderModel;
    const neck = man?.bones.get("Neck");
    if (man && neck) {
      const fromNeck = this.scratch.v.copy(camera).sub(neck.getWorldPosition(this.scratch.w));
      const ahead = fromNeck.dot(this.scratch.w.set(0, 0, 1).applyQuaternion(man.root.quaternion));
      if (ahead > 0.02 && fromNeck.length() < 0.9) man.root.visible = false;
    }
  }

  /**
   * Compile every material for both lighting states (interior lights on and off) up front, so switching them during
   * the story never stalls a frame on shader compilation.
   */
  precompile(): void {
    this.camera.position.set(0, 60, 80);
    this.camera.lookAt(0, 0, 0);
    this.camera.updateMatrixWorld(true);
    for (const on of [true, false]) {
      for (const light of this.ops.lights) light.visible = on;
      this.renderer.compile(this.scene, this.camera);
    }
  }

  /** Camera positions sampled along every segment (for keeping trees out of the shots). */
  private cameraSamples(): THREE.Vector3[] {
    const segments: SegmentId[] = ["opening", "everyday", "enter-phone", "conditions", "return-phone", "sos-signal", "enter-monitor", "aerial"];
    const samples: THREE.Vector3[] = [];
    const target = new THREE.Vector3(), up = new THREE.Vector3();
    for (const segment of segments) {
      const keys = this.keysFor(segment);
      for (let p = 0; p <= 1.0001; p += 0.01) {
        const pos = new THREE.Vector3();
        samplePath(keys, p, pos, target, up);
        samples.push(pos);
      }
    }
    return samples;
  }

  setViewport(viewport: StageViewport, aspects: ScreenAspects): void {
    this.viewport = viewport;
    this.aspects = aspects;
    this.renderer.setSize(viewport.width, viewport.height, false);
    this.camera.aspect = viewport.width / viewport.height;
    this.camera.fov = this.camera.aspect < 0.8 ? 54 : 40;
    this.camera.updateProjectionMatrix();
    const ph = PHONE_SCREEN_HEIGHT, pw = ph * aspects.phone;
    this.phone.resize(pw, ph);
    this.heldScreen?.fit(aspects.phone);
    this.ops.setMonitorSize(MONITOR_WIDTH, MONITOR_WIDTH / aspects.monitor);
    this.ops.setTableSize(TABLE_WIDTH, TABLE_WIDTH / aspects.table);
  }

  // --- Posing --------------------------------------------------------------------------------------------------------

  /** The rigged resident and responder (`characters.ts`) replace the procedural figures once loaded. */
  private async loadCharacters(): Promise<void> {
    const [woman, man] = await Promise.all([
      loadCharacter("/journey/characters/phone-woman.glb"),
      loadCharacter("/journey/characters/office-man.glb"),
    ]);
    if (this.disposed) {
      for (const character of [woman, man]) character.root.traverse((object) => (object as THREE.Mesh).geometry?.dispose());
      return;
    }
    // Fit both people to what they hold and touch before either joins the scene: if a model cannot be fitted, the
    // procedural figures stay as they are.
    prepareResident(woman);
    woman.root.position.copy(this.resident.root.position);
    woman.root.rotation.y = this.resident.root.rotation.y;
    man.root.position.copy(this.ops.seat);
    man.root.rotation.y = Math.PI / 2;
    prepareResponder(man, { keys: this.ops.keyboard, cushion: this.ops.cushion, floor: this.ops.floor });
    this.scene.add(woman.root);
    poseResidentModel(woman, 1, 0);
    woman.root.updateMatrixWorld(true);
    const head = woman.bones.get("Head")?.getWorldPosition(new THREE.Vector3()) ?? woman.root.position.clone().add(v(0, 1.55, 0));
    const held = attachScreen(woman, head.add(v(0, 0.08, 0)));
    if (!held) throw new Error("The resident model has no phone screen");
    held.fit(this.aspects.phone);
    this.heldScreen = held;
    this.phoneScreen = held.screen;
    this.resident.root.visible = false;
    this.phone.group.visible = false;
    this.residentModel = woman;
    this.residentCastsShadow = true;

    this.scene.add(man.root);
    this.responder.root.visible = false;
    this.responderModel = man;
  }

  /** Place the phone in the resident's hand (raise 0 = at the side, 1 = reading in front of the face). */
  private poseResident(raise: number, glow: number): void {
    if (this.residentModel) {
      poseResidentModel(this.residentModel, easeInOut(clamp01(raise)), this.time);
      this.residentModel.root.updateMatrixWorld(true);
      (this.phoneScreen.material as THREE.MeshBasicMaterial).color.set("#0d1416").lerp(new THREE.Color("#dfe7e2"), glow);
      return;
    }
    const figure = this.resident;
    const t = easeInOut(clamp01(raise));
    poseStanding(figure, 0.06 + 0.4 * t, this.time, 0.06 * t);
    figure.root.updateMatrixWorld(true);
    // Local (figure space) phone poses: n is the screen normal, u the phone's up.
    const hold = { pos: v(-0.25, 0.76, 0.07), n: v(0.88, 0.05, 0.46).normalize(), u: v(0.04, -1, 0.1).normalize() };
    const read = { pos: v(-0.07, 1.25, 0.31), n: v(0.14, 0.76, -0.63).normalize(), u: v(0.06, 0.62, 0.78).normalize() };
    const mid = v(-0.22, 1.0, 0.26);
    const pos = new THREE.Vector3()
      .copy(hold.pos).multiplyScalar((1 - t) * (1 - t))
      .addScaledVector(mid, 2 * (1 - t) * t)
      .addScaledVector(read.pos, t * t);
    const basis = (n: THREE.Vector3, u: THREE.Vector3) => {
      const x = u.clone().cross(n).normalize();
      const y = n.clone().cross(x).normalize();
      return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, n));
    };
    const q = basis(hold.n, hold.u).slerp(basis(read.n, read.u), t);
    const rootQuat = figure.root.getWorldQuaternion(new THREE.Quaternion());
    const worldPos = pos.applyMatrix4(figure.root.matrixWorld);
    const worldQuat = rootQuat.clone().multiply(q);
    this.phone.group.position.copy(worldPos);
    this.phone.group.quaternion.copy(worldQuat);
    this.phone.group.updateMatrixWorld(true);
    // Right hand behind the phone: the palm on its back, fingers across it toward the left edge (curling round it),
    // thumb along the right edge. Hand frame: fingers along local -y, palm normal +z (toward the phone).
    const px = v(1, 0, 0).applyQuaternion(worldQuat), py = v(0, 1, 0).applyQuaternion(worldQuat), pz = v(0, 0, 1).applyQuaternion(worldQuat);
    // Solved so the middle finger reaches the left edge and the thumb base sits just outside the right edge:
    // fingers on a 49 degree diagonal, the wrist at the lower-right corner, behind the phone.
    const fingers = px.clone().multiplyScalar(-0.656).addScaledVector(py, 0.755).normalize();
    const handY = fingers.clone().negate();
    const handX = handY.clone().cross(pz).normalize();
    const handQuat = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(handX, handY, pz));
    const wristTarget = worldPos.clone().addScaledVector(px, 0.036).addScaledVector(py, -0.081).addScaledVector(pz, -(this.phone.thickness / 2 + 0.0135));
    const j = figure.joints;
    const shoulder = j.shoulderR.getWorldPosition(new THREE.Vector3());
    const pole = shoulder.clone().add(v(-0.35, -0.55, -0.2).applyQuaternion(rootQuat));
    solveArm(j.shoulderR, j.elbowR, j.wristR, wristTarget, pole, handQuat);
    setGrip(figure, "R", GRIPS.phone);
    const material = this.phoneScreen.material as THREE.MeshBasicMaterial;
    material.color.set("#0d1416").lerp(new THREE.Color("#dfe7e2"), glow);
    this.residentShadow.visible = true;
  }

  private poseResponder(attention: number): void {
    if (this.responderModel) {
      poseResponderModel(this.responderModel, attention, this.time);
      return;
    }
    const figure = this.responder;
    poseSeated(figure, 0.24 - 0.18 * attention, this.time);
    figure.root.updateMatrixWorld(true);
    const j = figure.joints;
    const keys = this.ops.keyboard;
    const palmDown = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(v(0, 0, 1), v(-1, 0, 0), v(0, -1, 0)));
    const typing = Math.sin(this.time * 9) * 0.004 * attention;
    for (const [side, shoulder, elbow, wrist] of [[1, j.shoulderL, j.elbowL, j.wristL], [-1, j.shoulderR, j.elbowR, j.wristR]] as const) {
      // Figure faces +x; its left (+side) is world -z.
      const target = v(keys.x - 0.1, keys.y + 0.047 + typing * side, keys.z - side * 0.12);
      const s = shoulder.getWorldPosition(new THREE.Vector3());
      solveArm(shoulder, elbow, wrist, target, s.clone().add(v(-0.1, -0.5, -side * 0.45)), palmDown);
    }
    setGrip(figure, "L", GRIPS.typing);
    setGrip(figure, "R", GRIPS.typing);
  }

  // --- Screens -------------------------------------------------------------------------------------------------------

  private screenGeometry(mesh: THREE.Mesh): { center: THREE.Vector3; normal: THREE.Vector3; up: THREE.Vector3; width: number; height: number } {
    mesh.updateWorldMatrix(true, false);
    const center = mesh.getWorldPosition(new THREE.Vector3());
    const quat = mesh.getWorldQuaternion(new THREE.Quaternion());
    const scale = mesh.getWorldScale(new THREE.Vector3());
    return { center, normal: v(0, 0, 1).applyQuaternion(quat), up: v(0, 1, 0).applyQuaternion(quat), width: scale.x, height: scale.y };
  }

  /** Camera pose at which a screen exactly fills the viewport height (and width, when the aspects match). */
  /** Camera pose square-on to a screen, at which it fills `fill` of the viewport height (1 = exactly). */
  private endPose(mesh: THREE.Mesh, fill = 1): Key {
    const g = this.screenGeometry(mesh);
    const distance = g.height / 2 / Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2) / fill;
    return { at: 1, pos: g.center.clone().addScaledVector(g.normal, distance), target: g.center.clone(), up: g.up.clone() };
  }

  private project(point: THREE.Vector3): { x: number; y: number; inFront: boolean } {
    const camSpace = point.clone().applyMatrix4(this.camera.matrixWorldInverse);
    const ndc = point.clone().project(this.camera);
    return { x: ((ndc.x + 1) / 2) * this.viewport.width, y: ((1 - ndc.y) / 2) * this.viewport.height, inFront: camSpace.z < -this.camera.near };
  }

  private screenQuad(mesh: THREE.Mesh): Quad | null {
    const g = this.screenGeometry(mesh);
    // Hidden when the camera is behind the screen plane.
    if (this.camera.position.clone().sub(g.center).dot(g.normal) <= 0) return null;
    const right = g.normal.clone().cross(g.up).negate().normalize(); // up × normal
    const hw = g.width / 2, hh = g.height / 2;
    const corners = [
      g.center.clone().addScaledVector(right, -hw).addScaledVector(g.up, hh),
      g.center.clone().addScaledVector(right, hw).addScaledVector(g.up, hh),
      g.center.clone().addScaledVector(right, hw).addScaledVector(g.up, -hh),
      g.center.clone().addScaledVector(right, -hw).addScaledVector(g.up, -hh),
    ].map((corner) => this.project(corner));
    if (corners.some((corner) => !corner.inFront)) return null;
    return corners.map(({ x, y }) => ({ x, y })) as unknown as Quad;
  }

  // --- Choreography --------------------------------------------------------------------------------------------------

  private keysFor(segment: SegmentId): Key[] {
    const a = this.anchors;
    const R = a.resident;
    const ops = this.ops;
    const phoneC = this.screenGeometry(this.phoneScreen).center;
    const os = { at: 0, pos: R.clone().add(v(-0.78, 2.02, -0.5)), target: phoneC.clone() };
    const front = { at: 0, pos: R.clone().add(v(-1.9, 1.48, 3.6)), target: R.clone().add(v(0.2, 1.12, 0)) };
    const k = (at: number, base: { pos: THREE.Vector3; target: THREE.Vector3; up?: THREE.Vector3 }): Key => ({ at, pos: base.pos, target: base.target, up: base.up });
    const through = (at: number, base: { pos: THREE.Vector3; target: THREE.Vector3; up?: THREE.Vector3 }): Key => ({ ...k(at, base), pass: true });
    // Beside her, outside the garden wall: the way round to her shoulder that keeps clear of the gate post.
    const beside = { pos: R.clone().add(v(-1.05, 1.8, 1.35)), target: phoneC.clone() };
    const seat = ops.seat;
    const monitorC = this.screenGeometry(ops.monitorScreen).center;
    const tableC = this.screenGeometry(ops.tableScreen).center;
    const inside = { pos: v(seat.x - 3.6, ops.floor + 1.95, seat.z + 3.1), target: v(seat.x + 0.55, ops.floor + 1.0, seat.z) };
    // Over his right shoulder, with his hands on the keyboard and the screen both in frame; then past his shoulder
    // (he leaves the frame to the left, his hands below it) before the camera swings in front of the monitor.
    const overShoulder = { pos: seat.clone().add(v(-0.62, 1.42, 0.62)), target: monitorC.clone().lerp(ops.keyboard, 0.45) };
    const pastShoulder = { pos: seat.clone().add(v(0.2, 1.3, 0.4)), target: monitorC.clone() };
    const behind = { pos: seat.clone().add(v(-1.9, 1.75, 1.05)), target: overShoulder.target };
    // Simple camera language: a few clear shots, each reached by one smooth glide (no orbits or swoops). Holding a
    // shot is two keys with the same pose.
    const wide = { pos: v(-60, 35, 76), target: v(-6, 0, 3) };
    const road = { pos: v(-12, 9, 24), target: v(2, 0.4, 9) };
    const overview = { pos: v(-36, 42, 36), target: v(-6, 2, -10) };
    const windowFront = { pos: ops.window.clone().add(v(0, 0.9, 9)), target: ops.window.clone() };
    const roomView = { pos: tableC.clone().add(v(0, 3.4, 3.6)), target: tableC.clone() };
    const abovePlan = { pos: tableC.clone().add(v(0, 24, 0.02)), target: tableC.clone(), up: NORTH };
    const map = { pos: v(2, 92, -12.02), target: v(2, 0, -12), up: NORTH };
    const glide = (from: { pos: THREE.Vector3; target: THREE.Vector3 }, to: { pos: THREE.Vector3; target: THREE.Vector3 }, t: number) =>
      ({ pos: from.pos.clone().lerp(to.pos, t), target: from.target.clone().lerp(to.target, t) });
    switch (segment) {
      case "opening":
        return [k(0, { pos: v(-80, 46, 96), target: v(-2, 0, 4) }), k(1, wide)];
      case "everyday":
        // One straight descent from the neighbourhood to the resident at her gate.
        return [k(0, wide), k(0.5, glide(wide, front, 0.55)), k(1, front)];
      case "enter-phone":
        // Round her right shoulder, then straight onto the screen.
        return [k(0, front), through(0.3, beside), k(0.55, os), this.endPose(this.phoneScreen, PHONE_PAGE_FILL)];
      case "conditions":
        return [this.atKey(0, this.endPose(this.phoneScreen, PHONE_PAGE_FILL)), through(0.12, os), through(0.24, beside), k(0.6, road), k(1, road)];
      case "return-phone":
        return [k(0, road), through(0.4, front), through(0.58, beside), k(0.75, os), this.endPose(this.phoneScreen, PHONE_PAGE_FILL)];
      case "sos-signal":
        // Back to the road view and hold while the water crosses it; rise to see the signal reach the operations
        // building; glide in through its window.
        return [
          this.atKey(0, this.endPose(this.phoneScreen, PHONE_PAGE_FILL)),
          through(0.08, os),
          through(0.15, beside),
          k(0.26, road),
          k(0.48, road),
          k(0.66, overview),
          through(0.86, windowFront),
          k(1, inside),
        ];
      case "enter-monitor":
        return [k(0, inside), k(0.5, overShoulder), through(0.78, pastShoulder), this.endPose(ops.monitorScreen)];
      case "aerial":
        // Step back from the monitor, rise straight up through the skylight to a map view of the whole area, hold,
        // then come straight back down onto the planning table.
        return [
          this.atKey(0, this.endPose(ops.monitorScreen)),
          through(0.04, pastShoulder),
          through(0.08, overShoulder),
          through(0.12, behind),
          k(0.22, roomView),
          through(0.34, abovePlan),
          k(0.46, map),
          k(0.74, map),
          through(0.88, abovePlan),
          { ...this.endPose(ops.tableScreen), up: NORTH },
        ];
    }
  }

  private atKey(at: number, key: Key): Key {
    return { ...key, at };
  }

  // --- Frame ---------------------------------------------------------------------------------------------------------

  /** Advance the scene to timeline position `t` and render. */
  update(t: number, dt: number, render = true): StageFrame {
    this.time += dt;
    if (render && dt > 0) this.adaptResolution(dt);
    const { segment, progress: p } = locate(t);

    // Story state per segment.
    let raise = 0, glow = 0, phoneShow = 0, monitorShow = 0, tableShow = 0, rain = 0, affected = 0, attention = 0, signal = -1;
    // The connection line reads at neighbourhood scale; at human scale it would look like a pipe, so it fades out.
    let connection = 1;
    let water = WATER_LEVEL.dry, overcast = 0;
    const labels: Record<string, boolean> = {};
    switch (segment) {
      case "opening":
        labels.home = labels.clinic = labels.connection = p > 0.55;
        connection = ramp(p, 0.4, 0.6);
        break;
      case "everyday":
        raise = ramp(p, 0.62, 0.97);
        glow = ramp(p, 0.85, 1);
        phoneShow = ramp(p, 0.9, 1);
        labels.home = labels.clinic = labels.connection = p < 0.5;
        connection = 1 - ramp(p, 0.4, 0.56);
        break;
      case "enter-phone":
        raise = 1; glow = 1; phoneShow = 1; connection = 0;
        break;
      case "conditions":
        raise = 1 - 0.5 * ramp(p, 0.05, 0.3);
        glow = 1 - ramp(p, 0.16, 0.3);
        phoneShow = 1 - ramp(p, 0.1, 0.2);
        water = waterLevelBetween("dry", "rising", ramp(p, 0.18, 0.78));
        rain = ramp(p, 0.1, 0.45) * 0.75;
        overcast = ramp(p, 0.1, 0.6) * 0.6;
        labels.home = labels.clinic = p > 0.35;
        labels.connection = p > 0.35;
        connection = ramp(p, 0.22, 0.42);
        break;
      case "return-phone":
        raise = 0.5 + 0.5 * ramp(p, 0.35, 0.78);
        glow = ramp(p, 0.7, 0.85);
        phoneShow = ramp(p, 0.84, 0.98);
        water = WATER_LEVEL.rising;
        rain = 0.75;
        overcast = 0.6;
        connection = 1 - ramp(p, 0.2, 0.4);
        break;
      case "sos-signal": {
        raise = 1;
        glow = 1 - ramp(p, 0.1, 0.2);
        phoneShow = 1 - ramp(p, 0.06, 0.12);
        water = waterLevelBetween("rising", "affected", ramp(p, 0.16, 0.46));
        affected = ramp(p, 0.3, 0.48);
        rain = 0.9 - 0.4 * ramp(p, 0.7, 0.95);
        overcast = 0.75;
        signal = p > 0.48 && p < 0.86 ? ramp(p, 0.5, 0.8) : -1;
        attention = ramp(p, 0.84, 0.98);
        labels.home = labels.clinic = labels.crossing = p > 0.24 && p < 0.6;
        labels.signal = signal >= 0;
        labels.operations = p > 0.58 && p < 0.84;
        connection = ramp(p, 0.1, 0.22);
        break;
      }
      case "enter-monitor":
        water = WATER_LEVEL.affected; affected = 1; overcast = 0.75; rain = 0.5; attention = 1;
        monitorShow = ramp(p, 0.15, 0.5);
        raise = 1;
        break;
      case "aerial":
        water = WATER_LEVEL.affected; affected = 1; overcast = 0.75 - 0.35 * ramp(p, 0.3, 0.7); rain = 0.5 * (1 - ramp(p, 0.25, 0.5)); attention = 1;
        monitorShow = 1 - ramp(p, 0.22, 0.3);
        tableShow = ramp(p, 0.8, 0.96);
        raise = 1;
        labels.home = labels.clinic = labels.crossing = labels.operations = p > 0.42 && p < 0.78;
        break;
    }

    this.poseResident(raise, glow);
    this.poseResponder(attention);

    // Environment.
    this.water.position.y = water;
    this.waterNormal.offset.set(this.time * 0.006, this.time * 0.004);
    this.waterUniforms.uMud.value = clamp01((water - WATER_LEVEL.dry) / (WATER_LEVEL.affected - WATER_LEVEL.dry));
    this.waterUniforms.uRain.value = rain;
    this.waterUniforms.uTime.value = this.time;
    this.wet.uLevel.value = water;
    this.wet.uWet.value = clamp01(rain * 1.25 + overcast * 0.3);
    this.rain.material.uniforms.uTime.value = this.time;
    this.rain.material.uniforms.uIntensity.value = rain;
    this.rain.mesh.visible = rain > 0.01;
    const sky = this.sky.material.uniforms;
    sky.uTop.value.set("#b9cfd6").lerp(new THREE.Color("#9eaaad"), overcast);
    sky.uHorizon.value.set("#efe9dc").lerp(new THREE.Color("#d5d6d0"), overcast);
    sky.uCloud.value = 0.22 + 0.75 * overcast;
    sky.uTime.value = this.time;
    (this.scene.fog as THREE.Fog).color.set("#e9e6dc").lerp(new THREE.Color("#d2d4ce"), overcast);
    (this.scene.fog as THREE.Fog).near = 90 - 40 * overcast;
    this.sun.intensity = 3.1 - 1.9 * overcast;
    this.sun.color.set("#fff0d8").lerp(new THREE.Color("#e9eef0"), overcast);
    this.hemi.intensity = 0.42 + 0.25 * overcast;
    this.scene.environmentIntensity = 0.75 - 0.15 * overcast;
    this.connection.group.visible = connection > 0.01;
    this.connection.dryMaterial.opacity = 0.92 * connection;
    this.connection.crossingMaterial.opacity = 0.95 * connection;
    this.connection.setWaterLevel(water);
    this.connection.setAffected(affected);
    this.connection.tick(this.time);
    this.signal.tube.visible = this.signal.head.visible = signal >= 0;
    if (signal >= 0) {
      const total = (this.signal.tube.geometry.index?.count ?? 0);
      this.signal.tube.geometry.setDrawRange(Math.floor(total * Math.max(0, signal - 0.18)), Math.floor(total * Math.min(0.24, signal)));
      this.signal.head.position.copy(this.signal.curve.getPoint(signal));
      this.signal.head.scale.setScalar(0.8 + 0.25 * Math.sin(this.time * 8));
    }

    // Camera.
    const { pos, target, up } = this.scratch;
    samplePath(this.keysFor(segment), p, pos, target, up);
    this.camera.position.copy(pos);
    this.camera.up.copy(up);
    this.camera.lookAt(target);
    this.camera.updateMatrixWorld(true);
    this.rain.material.uniforms.uCenter.value.set(pos.x, Math.max(0, pos.y - 10), pos.z);
    const fp = this.ops.footprint;
    const indoors = Math.abs(pos.x - fp.x) < fp.w / 2 && Math.abs(pos.z - fp.z) < fp.d / 2 && pos.y < this.ops.floor + 5.6;
    if (indoors) this.rain.mesh.visible = false;
    this.followShadow(pos, target);
    // People cost dozens of draw calls: the responder is only drawn near the operations room, and the resident stops
    // casting a (sub-pixel) shadow from far away.
    const nearOps = pos.distanceTo(this.ops.seat) < 32;
    this.responder.root.visible = nearOps && !this.responderModel;
    if (this.responderModel) this.responderModel.root.visible = nearOps;
    this.clearCloseUps(pos);
    const opsLit = pos.distanceTo(this.ops.seat) < 48;
    for (const light of this.ops.lights) light.visible = opsLit;
    const residentCasts = pos.distanceTo(this.anchors.resident) < 45;
    if (residentCasts !== this.residentCastsShadow) {
      this.residentCastsShadow = residentCasts;
      (this.residentModel?.root ?? this.resident.root).traverse((object) => { object.castShadow = residentCasts; });
      this.phone.group.traverse((object) => { object.castShadow = residentCasts; });
    }

    // No post-processing: occlusion is baked (contact shadows, wall gradients, canopy tones), which measured several
    // times cheaper than screen-space AO on integrated graphics for a near-identical result.
    if (render) this.renderer.render(this.scene, this.camera);

    const frameLabels: LabelFrame[] = (["home", "clinic", "connection", "crossing", "operations", "signal"] as const).map((id) => {
      const anchor = id === "signal" ? this.signal.head.position.clone().add(v(0, 1.6, 0)) : this.anchors[id];
      const projected = this.project(anchor);
      const onScreen = projected.inFront && projected.x > -40 && projected.x < this.viewport.width + 40 && projected.y > -40 && projected.y < this.viewport.height + 40;
      return { id, x: projected.x, y: projected.y, visible: Boolean(labels[id]) && onScreen };
    });

    return {
      screens: {
        phone: { quad: phoneShow > 0 ? this.screenQuad(this.phoneScreen) : null, opacity: phoneShow },
        monitor: { quad: monitorShow > 0 ? this.screenQuad(this.ops.monitorScreen) : null, opacity: monitorShow },
        table: { quad: tableShow > 0 ? this.screenQuad(this.ops.tableScreen) : null, opacity: tableShow },
      },
      labels: frameLabels,
    };
  }

  private adaptResolution(dt: number): void {
    this.frameAverage += (Math.min(dt, 0.1) - this.frameAverage) * 0.05;
    this.sinceResize += dt;
    if (this.sinceResize < 1.5) return;
    let next = this.pixelRatio;
    const floor = Math.min(1, this.maxPixelRatio);
    if (this.frameAverage > 1 / 36) next = Math.max(floor, this.pixelRatio - 0.25);
    else if (this.frameAverage < 1 / 52 && this.pixelRatio < this.maxPixelRatio) next = Math.min(this.maxPixelRatio, this.pixelRatio + 0.125);
    if (next === this.pixelRatio) return;
    this.pixelRatio = next;
    this.sinceResize = 0;
    this.renderer.setPixelRatio(next);
    this.renderer.setSize(this.viewport.width, this.viewport.height, false);
  }

  /**
   * Keep the sun's shadow map on what the camera is looking at: a tight frustum for close shots (crisp contact
   * shadows under people and furniture), a wide one for aerial shots. The focus is snapped to shadow texels to avoid
   * shimmering while the camera moves.
   */
  private followShadow(position: THREE.Vector3, target: THREE.Vector3): void {
    const distance = position.distanceTo(target);
    const extent = THREE.MathUtils.clamp(distance * 0.95, 6, 95);
    const shadow = this.sun.shadow;
    const camera = shadow.camera as THREE.OrthographicCamera;
    if (Math.abs(extent - this.shadowExtent) > this.shadowExtent * 0.04) {
      this.shadowExtent = extent;
      camera.left = -extent;
      camera.right = extent;
      camera.top = extent;
      camera.bottom = -extent;
      camera.updateProjectionMatrix();
    }
    const texel = (2 * this.shadowExtent) / shadow.mapSize.x;
    const focus = this.scratch.v.copy(target).lerp(position, distance < 12 ? 0.15 : 0);
    // Close shots re-render the shadow map every frame (people move, the frustum is small and cheap). Wide shots
    // snap the frustum to steps of an eighth of its size and re-render only when it moves a step, so a moving aerial
    // camera does not redraw every shadow caster in the neighbourhood each frame.
    const close = this.shadowExtent < 20;
    const step = close ? texel : texel * Math.round(shadow.mapSize.x / 16);
    focus.set(Math.round(focus.x / step) * step, Math.round(focus.y / step) * step, Math.round(focus.z / step) * step);
    shadow.autoUpdate = close;
    if (!close) {
      const key = `${focus.x.toFixed(2)},${focus.y.toFixed(2)},${focus.z.toFixed(2)},${this.shadowExtent.toFixed(2)}`;
      if (key !== this.shadowKey) {
        this.shadowKey = key;
        shadow.needsUpdate = true;
      }
    } else {
      this.shadowKey = "";
    }
    this.sun.target.position.copy(focus);
    this.sun.position.copy(focus).addScaledVector(this.sunDir, 150);
    this.sun.target.updateMatrixWorld();
  }

  dispose(): void {
    this.disposed = true;
    this.scene.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.LineSegments || object instanceof THREE.InstancedMesh) {
        object.geometry.dispose();
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((material) => {
          Object.values(material).forEach((value) => {
            if (value instanceof THREE.Texture) value.dispose();
          });
          material.dispose();
        });
      }
    });
    this.disposables.forEach((item) => item.dispose());
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}
