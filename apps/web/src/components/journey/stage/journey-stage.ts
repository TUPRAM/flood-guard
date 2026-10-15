import * as THREE from "three";

import { LANDSCAPE_PAGE_FILL, PHONE_PAGE_FILL, type Quad } from "@/lib/journey/screen-projection";
import { samplePath, type CameraKey } from "@/lib/journey/camera-path";
import { skyAt } from "@/lib/journey/sky";
import { SEGMENT_IDS, locate, replayHourAt, segmentRange, veilAt, type SegmentId } from "@/lib/journey/timeline";
import { stageAtHour, type TownBuilding, type TownPack } from "@/lib/journey/town-data";

import { Parts, architectureMaterials, architectureTextures, buildHouse, houseTopHeight, mergeParts, porchSurfaceAt, setArchitectureGround, type HouseSpec } from "./architecture";
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
import { PALETTE, contactShadowTexture, type Quality } from "./materials";
import { buildOperations, type OperationsBuilding } from "./operations";
import { buildTown, type Town } from "./town";
import { buildTrees, type Vegetation } from "./vegetation";
import { alertTexture, buildEnvironmentScene, buildPhone, buildRain, buildSky, tableTexture, type Phone } from "./world";

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
  /** The replay hour shown (whole hours since 9 Sep 2024 00:00 ICT, fractional between beats). */
  hour: number;
  /** 0..1: darkness over the scene for a cut in time. */
  veil: number;
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

type Key = CameraKey;

interface Pose { pos: THREE.Vector3; target: THREE.Vector3; up?: THREE.Vector3; zoom?: number }

/** Where Mali and Dao stand, relative to Lalita at her gate, in the house's frame (x along the front, z toward the street). */
const LAYOUT_FAMILY = { mali: { x: 1.05, z: -0.05, turn: -0.3 }, dao: { x: 0.52, z: 0.5, turn: -0.2 } } as const;
type PersonId = "lalita" | "mali" | "dao" | "narin" | "pim";
const NORTH = new THREE.Vector3(0, 0, -1);
const PHONE_SCREEN_HEIGHT = 0.15;
const MONITOR_WIDTH = 0.66;
const TABLE_WIDTH = 2.9;
/** The labels the stage places (the keys of LABELS in journey-copy.ts). */
export const LABEL_IDS = ["home", "neighbour", "neighbourPeak", "shelter", "route", "low", "cut", "river", "office", "wat", "signal", "lalita", "mali", "dao", "narin", "pim"] as const;
type LabelId = (typeof LABEL_IDS)[number];

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const clamp01 = (value: number) => Math.min(1, Math.max(0, value));
/** 0→1 as `value` goes from a to b, smoothed. */
const ramp = (value: number, a: number, b: number) => {
  const t = clamp01((value - a) / (b - a));
  return t * t * (3 - 2 * t);
};
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Point in a ring of x/z pairs (even-odd rule). */
/** Distance (m) from a point to a ring's nearest edge. */
function ringDistance(ring: Float32Array, x: number, z: number): number {
  let best = Infinity;
  const n = ring.length / 2;
  for (let i = 0; i < n; i += 1) {
    const ax = ring[i * 2], az = ring[i * 2 + 1], bx = ring[((i + 1) % n) * 2], bz = ring[((i + 1) % n) * 2 + 1];
    const l2 = (bx - ax) ** 2 + (bz - az) ** 2 || 1;
    const t = Math.max(0, Math.min(1, ((x - ax) * (bx - ax) + (z - az) * (bz - az)) / l2));
    best = Math.min(best, Math.hypot(ax + t * (bx - ax) - x, az + t * (bz - az) - z));
  }
  return best;
}

function insideRing(ring: Float32Array, x: number, z: number): boolean {
  let inside = false;
  const n = ring.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i, i += 1) {
    const xi = ring[i * 2], zi = ring[i * 2 + 1], xj = ring[j * 2], zj = ring[j * 2 + 1];
    if ((zi > z) !== (zj > z) && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

// The sky (night, rain, overcast by replay hour) is in lib/journey/sky.ts.

export interface StageOptions {
  quality: Quality;
  town: TownPack;
}

export class JourneyStage {
  readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(40, 1, 0.01, 9000);
  private readonly quality: Quality;
  private viewport: StageViewport = { width: 1, height: 1 };
  private aspects: ScreenAspects = { phone: 0.4615, monitor: 1.6, table: 1.6 };
  private readonly disposables: Array<{ dispose(): void }> = [];

  private readonly town: Town;
  private readonly pack: TownPack;
  private readonly rain: ReturnType<typeof buildRain>;
  private readonly sky: ReturnType<typeof buildSky>;
  private readonly sun: THREE.DirectionalLight;
  // Late morning from the east-south-east: Lalita's house faces east, so its front is lit in the family shots.
  private readonly sunDir = new THREE.Vector3(0.42, 0.78, 0.46).normalize();
  private readonly hemi: THREE.HemisphereLight;
  private readonly porch: THREE.PointLight;
  private readonly fog: THREE.FogExp2;
  private readonly ops: OperationsBuilding;
  private vegetation!: Vegetation;
  private readonly resident: Figure;
  private readonly responder: Figure;
  /** Lalita's mother and daughter, and the district coordinator: simpler stand-in figures (no rigged models yet). */
  private readonly mali: Figure;
  private readonly dao: Figure;
  private readonly pim: Figure;
  private readonly familyShadows: THREE.Mesh[] = [];
  private readonly pimShadow: THREE.Mesh;
  private readonly residentShadow: THREE.Mesh;
  private readonly phone: Phone;
  private readonly signal: { tube: THREE.Mesh; head: THREE.Mesh; curve: THREE.QuadraticBezierCurve3; material: THREE.MeshBasicMaterial };
  /** House frame: where Lalita stands (R), the street-ward normal (F) and the along-front axis (S). */
  private readonly frame: { R: THREE.Vector3; F: THREE.Vector3; S: THREE.Vector3; rotation: number; homeTop: number };
  /** The clearest way to look at Lalita from her street (real outlines around her), and how far it is clear. */
  private street!: { dir: THREE.Vector3; clear: number };
  /** The nearest river channel to the home (replay cells), for the shot toward the river. */
  private river!: THREE.Vector3;
  /** Where the water was deepest at the peak among the lanes near the home (for the tide lines). */
  private deep!: THREE.Vector3;
  /** The steep view of the home at the peak: the bearing with nothing taller in the way and the most water beyond. */
  private islandPose!: Pose;
  /** Low along a lane where the water stood deep, for the tide lines after it has gone down. */
  private tidePose!: Pose;
  private readonly anchors: Record<string, THREE.Vector3>;
  /** The town's drawn ground, for pacing camera moves by height. */
  private readonly groundAt: (x: number, z: number) => number;
  /** The replay cell of the app's flooded example home (Lalita's neighbours). */
  private readonly neighbourCell: number;
  private shadowExtent = 0;
  private sunUp = true;
  /** The viewport's own vertical field of view (degrees); a camera key may widen it (`zoom`). */
  private baseFov = 40;
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
  private readonly maxPixelRatio: number;
  private pixelRatio: number;
  private frameAverage = 1 / 60;
  private sinceResize = 0;
  private time = 0;
  private readonly peakStage: number;

  private readonly scratch = { pos: new THREE.Vector3(), target: new THREE.Vector3(), up: new THREE.Vector3(), v: new THREE.Vector3(), w: new THREE.Vector3() };

  constructor(canvas: HTMLCanvasElement, options: StageOptions) {
    this.quality = options.quality;
    this.pack = options.town;
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
    this.fog = new THREE.FogExp2("#e9e6dc", 0.0003);
    this.scene.fog = this.fog;
    this.sky = buildSky();
    this.sky.mesh.scale.setScalar(12);
    this.sky.material.fog = false;
    this.sky.material.uniforms.uSunDir.value.copy(this.sunDir);
    this.scene.add(this.sky.mesh);

    this.hemi = new THREE.HemisphereLight("#eef0ea", "#8a8466", 0.42);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight("#fff0d8", 3.1);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(high ? 2048 : 1024, high ? 2048 : 1024);
    this.sun.shadow.radius = high ? 3 : 2;
    this.sun.shadow.bias = -0.0003;
    this.sun.shadow.normalBias = 0.03;
    this.sun.shadow.camera.near = 1;
    this.sun.shadow.camera.far = 1600;
    this.scene.add(this.sun, this.sun.target);

    // The town: the real outlines, roads and land cover of Mae Sai, with the replay's water.
    this.town = buildTown(this.pack, { quality: options.quality });
    this.scene.add(this.town.group);
    this.disposables.push(this.town);
    const field = this.town.field;
    this.groundAt = field.groundAt.bind(field);
    this.peakStage = Math.max(...this.pack.manifest.replay.stage_anchors.map((anchor) => anchor.stage_m));

    // Lalita's home: the house kit on the real outline's box, facing its street.
    // Bound to the field alone: an arrow here would share the constructor's closure context and keep the stage alive.
    setArchitectureGround(field.groundAt.bind(field));
    const textures = architectureTextures();
    const materials = architectureMaterials(textures);
    Object.values(textures).forEach((texture) => this.disposables.push(texture));
    Object.values(materials).forEach((material) => this.disposables.push(material));
    const home = this.town.home;
    const { plot } = home;
    const gateX = plot.gateX;
    // The house faces its street behind a small yard; the wall, the gate, the spirit house and the pots are in the kit.
    // No water tank beside it: the plot has no room on either side.
    const spec: HouseSpec = {
      x: home.x, z: home.z, w: home.w, d: home.d, storeys: 2, roof: "hip", pitch: THREE.MathUtils.degToRad(27), rotation: home.rotation,
      wall: new THREE.Color("#efe7d6"), roofColor: new THREE.Color("#a35f45"), trim: PALETTE.trim, porch: true, hoods: true, tank: false, ac: true,
      fence: true, yard: home.yard, gateX, doorX: plot.doorX, seed: 4242, fenceFrom: plot.fence.from, fenceTo: plot.fence.to, yardLife: true,
    };
    const parts = new Parts();
    buildHouse(parts, spec);
    // The one-storey back wing on the rest of the real outline, its door onto the lane beside it.
    if (plot.annex) {
      const a = plot.annex;
      buildHouse(parts, {
        x: a.x, z: a.z, w: a.d, d: a.w, storeys: 1, roof: "gable", pitch: THREE.MathUtils.degToRad(16), rotation: a.rotation + Math.PI / 2,
        wall: new THREE.Color("#e6dccb"), roofColor: new THREE.Color("#8a8f88"), trim: PALETTE.trim, porch: false, hoods: false, tank: false, ac: false,
        fence: false, yard: 0, gateX: 0, doorX: 0, seed: 4243, eaves: 0.3,
      });
    }
    this.scene.add(mergeParts(parts, materials, "Home"));
    const F = v(Math.sin(home.rotation), 0, Math.cos(home.rotation));
    const S = v(Math.cos(home.rotation), 0, -Math.sin(home.rotation));
    const R = v(home.x, 0, home.z).addScaledVector(S, gateX).addScaledVector(F, home.d / 2 + home.yard + 0.2);
    R.y = field.groundAt(R.x, R.z);
    this.frame = { R, F, S, rotation: home.rotation, homeTop: houseTopHeight(spec) };
    this.street = this.clearView(spec);
    // Toward the Sai River (its label's place), else the nearest of the replay's channel cells.
    const riverPlace = this.pack.manifest.places.find((entry) => entry.id === "sai_river");
    this.river = riverPlace ? v(riverPlace.x, 0, riverPlace.z) : this.nearestChannel();
    this.deep = this.deepestNear(170);
    this.islandPose = this.islandView();
    this.tidePose = this.tideView();

    // The District Office: the operations room in the office's outline (exterior on its place; interior illustrative).
    this.ops = buildOperations(alertTexture(), tableTexture(), this.town.office);
    this.scene.add(this.ops.group);
    this.disposables.push(this.ops);

    this.rain = buildRain(options.quality);
    this.scene.add(this.rain.mesh);

    // A porch light at Lalita's home (on at night only; both states are compiled up front).
    this.porch = new THREE.PointLight("#ffcf94", 0, 14, 1.6);
    this.porch.position.copy(R).addScaledVector(F, -home.yard - 0.6).add(v(0, 2.7, 0));
    this.scene.add(this.porch);

    // Resident at the garden gate, facing the street, in clothes that suit a warm climate.
    this.resident = buildFigure({ skin: 0xc4957a, shirt: 0xa7644b, trousers: 0x4a4d45, hair: 0x221a16, shoes: 0xd9d4ca, sole: 0xf1eee8, hairStyle: "bun", build: "f" });
    this.resident.root.position.copy(R);
    this.resident.root.rotation.y = home.rotation - 0.18;
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
    this.residentShadow.position.copy(R).add(v(0, 0.02, 0));
    this.scene.add(this.residentShadow);
    const footShadow = (position: THREE.Vector3, size: number) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), blobMaterial);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.copy(position).add(v(0, 0.02, 0));
      this.scene.add(mesh);
      return mesh;
    };

    // Mali and Dao in the gate opening beside Lalita (on her left, clear of the camera's way round her right shoulder).
    this.mali = buildFigure({ skin: 0xb8876b, shirt: 0x6f8068, trousers: 0x54463f, hair: 0xb9b3aa, shoes: 0x4a3f38, sole: 0x3b332e, hairStyle: "bun", build: "f" });
    this.dao = buildFigure({ skin: 0xc99c80, shirt: 0xf1eee6, trousers: 0x2d3b5c, hair: 0x1c1512, shoes: 0x2a2a2e, sole: 0xe9e5dc, hairStyle: "short", build: "f" });
    this.dao.root.scale.setScalar(0.74);
    this.dao.joints.head.scale.setScalar(1.2);
    for (const [figure, offset] of [[this.mali, LAYOUT_FAMILY.mali], [this.dao, LAYOUT_FAMILY.dao]] as const) {
      const p = this.rel(offset.x, 0, offset.z);
      // On the porch step or slab where they stand on it, not inside it.
      p.y = Math.max(field.groundAt(p.x, p.z), porchSurfaceAt(spec, p.x, p.z) ?? -Infinity);
      figure.root.position.copy(p);
      figure.root.rotation.y = home.rotation + offset.turn;
      this.scene.add(figure.root);
      this.familyShadows.push(footShadow(figure.root.position, figure === this.dao ? 0.7 : 0.9));
    }

    // Pim stands at the north side of the planning table, facing the room (+z), her hands on its edge.
    this.pim = buildFigure({ skin: 0xb58266, shirt: 0x5d5478, trousers: 0x33363b, hair: 0x1d1714, shoes: 0x2b2826, sole: 0x2b2826, hairStyle: "bun", build: "f" });
    this.scene.add(this.pim.root);
    this.pimShadow = footShadow(new THREE.Vector3(), 0.9);

    // Responder seated at the desk, facing the monitor (+x).
    this.responder = buildFigure({ skin: 0xa77a5e, shirt: 0x3d6466, trousers: 0x2f3437, hair: 0x1f1a17, shoes: 0x2b2826, sole: 0x2b2826, hairStyle: "short", build: "m" });
    this.responder.root.position.copy(this.ops.seat);
    this.responder.root.rotation.y = Math.PI / 2;
    this.scene.add(this.responder.root);

    // Simulated call to the hotline: an arc from Lalita's home to the District Office (about 1.4 km), drawn at town
    // scale so it reads from the overview.
    const start = R.clone().add(v(0, 3, 0));
    const end = this.ops.window.clone().add(v(0, 4, 2));
    const control = start.clone().lerp(end, 0.5).add(v(0, start.distanceTo(end) * 0.28, 0));
    const curve = new THREE.QuadraticBezierCurve3(start, control, end);
    const signalMaterial = new THREE.MeshBasicMaterial({ color: "#f0a64a", transparent: true, opacity: 0.95, toneMapped: false, fog: false });
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 240, 2.2, 8), signalMaterial);
    const head = new THREE.Mesh(new THREE.SphereGeometry(9, 20, 14), signalMaterial);
    tube.visible = head.visible = false;
    this.scene.add(tube, head);
    this.signal = { tube, head, curve, material: signalMaterial };

    const place = (id: string) => this.pack.manifest.places.find((entry) => entry.id === id);
    const at = (id: string, lift: number) => {
      const p = place(id);
      return p ? v(p.x, field.groundAt(p.x, p.z) + lift, p.z) : v(0, lift, 0);
    };
    const neighbourPlace = place("neighbour");
    this.neighbourCell = neighbourPlace ? field.cellIndex(neighbourPlace.x, neighbourPlace.z) : -1;
    this.anchors = {
      home: v(home.x, this.frame.homeTop + 3.2, home.z),
      neighbour: this.town.anchors.neighbour,
      neighbourPeak: this.town.anchors.neighbour,
      shelter: this.town.anchors.shelter,
      route: this.routePoint(0.45).add(v(0, 4, 0)),
      cut: this.town.anchors.cut,
      low: this.town.anchors.cut,
      river: at("sai_river", 8),
      office: v(this.town.office.x, this.ops.floor + 9, this.town.office.z),
      wat: at("R04", 18),
    };

    this.disposables.push(this.resident, this.responder, this.mali, this.dao, this.pim);

    this.phone.resize(PHONE_SCREEN_HEIGHT * this.aspects.phone, PHONE_SCREEN_HEIGHT);
    this.ops.setMonitorSize(MONITOR_WIDTH, MONITOR_WIDTH / this.aspects.monitor);
    this.ops.setTableSize(TABLE_WIDTH, TABLE_WIDTH / this.aspects.table);
    this.poseResident(1, 0);
    // Trees last: they keep clear of the camera's actual path through the story.
    this.vegetation = buildTrees({
      quality: options.quality,
      trees: this.pack.trees,
      height: (x, z) => field.groundAt(x, z),
      clearance: this.cameraSamples(),
      focus: [{ x: R.x, z: R.z, r: 260 }, { x: this.town.office.x, z: this.town.office.z, r: 160 }],
    });
    this.scene.add(this.vegetation.group);
    this.disposables.push(this.vegetation);
    this.charactersReady = this.loadCharacters().catch(() => {
      // Keep the procedural figures (offline, blocked or failed download).
    });
  }

  /**
   * Mae Sai's lanes are narrow: a camera a few metres in front of Lalita can end up inside the building across the
   * lane. Look along directions around her street-ward normal and keep the one that stays clear of every outline (and
   * of her own house and yard) the longest, preferring directions that face her.
   */
  private clearView(house: HouseSpec): { dir: THREE.Vector3; clear: number } {
    const { R, F, S } = this.frame;
    const H = v(house.x, 0, house.z);
    const near = this.pack.buildings.filter((b) => b.index !== this.pack.special.home && Math.hypot(b.obb.cx - R.x, b.obb.cz - R.z) < 50);
    const blocked = (x: number, z: number) => {
      const lx = (x - H.x) * S.x + (z - H.z) * S.z, lz = (x - H.x) * F.x + (z - H.z) * F.z;
      if (Math.abs(lx) < house.w / 2 + 1.2 && lz < house.d / 2 + house.yard + 0.15) return true;
      return near.some((b) => insideRing(b.ring, x, z));
    };
    let best = { dir: F.clone(), clear: 0, score: -Infinity };
    for (let deg = -105; deg <= 105; deg += 5) {
      const a = THREE.MathUtils.degToRad(deg);
      const dir = F.clone().multiplyScalar(Math.cos(a)).addScaledVector(S, Math.sin(a)).normalize();
      let clear = 0.5;
      while (clear < 14 && !blocked(R.x + dir.x * clear, R.z + dir.z * clear)) clear += 0.25;
      const score = Math.min(clear, 7) - Math.abs(deg) / 60;
      if (score > best.score) best = { dir, clear, score };
    }
    return { dir: best.dir, clear: best.clear };
  }

  /** The replay channel cell nearest the home (the Sai River and its branches). */
  private nearestChannel(): THREE.Vector3 {
    const field = this.town.field;
    const { R } = this.frame;
    let best = v(R.x, 0, R.z - 220), bestD = Infinity;
    for (let r = 0; r < field.rows; r += 1) for (let c = 0; c < field.cols; c += 1) {
      if (field.code[r * field.cols + c] !== 0) continue;
      const x = field.x0 + (c + 0.5) * field.dx, z = field.z0 + (r + 0.5) * field.dz;
      const d = Math.hypot(x - R.x, z - R.z);
      if (d < bestD) { bestD = d; best = v(x, 0, z); }
    }
    return best;
  }

  /**
   * A steep view down onto the home at the replay's peak (about 60°): of the bearings around it, one where no outline
   * standing taller than the line of sight hides the house, preferring the sun behind the camera and the most water in
   * the far half of the frame.
   */
  private islandView(): Pose {
    const field = this.town.field;
    const H = v(this.town.home.x, this.frame.R.y, this.town.home.z);
    const roof = v(H.x, this.frame.homeTop, H.z);
    const near = this.pack.buildings.filter((b) => b.index !== this.pack.special.home && Math.hypot(b.obb.cx - H.x, b.obb.cz - H.z) < 90);
    const topOf = (b: TownBuilding) => field.groundAt(b.obb.cx, b.obb.cz) + b.floors * 3.4 + 2;
    let best: { score: number; pose: Pose } = { score: -Infinity, pose: { pos: H.clone().add(v(-70, 120, 110)), target: H.clone() } };
    for (let deg = 0; deg < 360; deg += 15) {
      const a = THREE.MathUtils.degToRad(deg);
      const dir = v(Math.sin(a), 0, -Math.cos(a));
      const pos = H.clone().addScaledVector(dir, -70).add(v(0, 120, 0));
      let hidden = 0;
      for (let i = 1; i < 24; i += 1) {
        const q = pos.clone().lerp(roof, i / 24);
        if (near.some((b) => insideRing(b.ring, q.x, q.z) && topOf(b) > q.y)) hidden += 1;
      }
      let wet = 0, all = 0;
      for (let r = 30; r <= 110; r += 10) for (let side = -60; side <= 60; side += 15) {
        const s = THREE.MathUtils.degToRad(side);
        const x = H.x + (dir.x * Math.cos(s) - dir.z * Math.sin(s)) * r, z = H.z + (dir.z * Math.cos(s) + dir.x * Math.sin(s)) * r;
        all += 1;
        if (field.cellDepth(field.cellIndex(x, z), this.peakStage) !== null) wet += 1;
      }
      // With the sun behind the camera: looking into it, the sunlit water flares white and stops reading as water.
      const intoSun = Math.max(0, dir.x * this.sunDir.x + dir.z * this.sunDir.z) / Math.hypot(this.sunDir.x, this.sunDir.z);
      const score = -hidden * 10 + wet / Math.max(1, all) - 1.5 * intoSun;
      if (score > best.score) best = { score, pose: { pos, target: H.clone().add(v(0, 2, 0)) } };
    }
    return best.pose;
  }

  /**
   * A lane near the home where the water stood deep at the replay's peak (about 0.8 to 2 m) with houses close on
   * both sides, so their walls carry the line of the highest water once it has gone down.
   */
  private deepestNear(radius: number): THREE.Vector3 {
    const field = this.town.field;
    const { R } = this.frame;
    const near = this.pack.buildings.filter((b) => Math.hypot(b.obb.cx - R.x, b.obb.cz - R.z) < radius + 20);
    let best = v(R.x, 0, R.z - 60), bestScore = -Infinity;
    for (let r = 0; r < field.rows; r += 1) for (let c = 0; c < field.cols; c += 1) {
      const x = field.x0 + (c + 0.5) * field.dx, z = field.z0 + (r + 0.5) * field.dz;
      if (Math.hypot(x - R.x, z - R.z) > radius) continue;
      const depth = field.cellDepth(r * field.cols + c, this.peakStage);
      if (depth === null || depth < 0.8 || depth > 2) continue;
      if (near.some((b) => insideRing(b.ring, x, z))) continue;
      const walls = near.filter((b) => Math.hypot(b.obb.cx - x, b.obb.cz - z) < 16).length;
      const score = Math.min(walls, 8) + depth;
      if (score > bestScore) { bestScore = score; best = v(x, field.groundAt(x, z), z); }
    }
    return best;
  }

  /**
   * Low over that lane, looking along it: of the bearings around it, one whose camera stands clear of every outline,
   * with nothing taller in the way, the most walls close to the line of sight, and the sun not in front.
   */
  private tideView(): Pose {
    const field = this.town.field;
    const D = this.deep;
    const near = this.pack.buildings.filter((b) => Math.hypot(b.obb.cx - D.x, b.obb.cz - D.z) < 60);
    const topOf = (b: TownBuilding) => field.groundAt(b.obb.cx, b.obb.cz) + b.floors * 3.4 + 2;
    const look = D.clone().add(v(0, 1.4, 0));
    let best: { score: number; pose: Pose } = { score: -Infinity, pose: { pos: D.clone().add(v(-18, 12, 18)), target: look } };
    for (let deg = 0; deg < 360; deg += 10) {
      const a = THREE.MathUtils.degToRad(deg);
      const dir = v(Math.sin(a), 0, -Math.cos(a));
      const pos = D.clone().addScaledVector(dir, -22).add(v(0, 4.5, 0));
      // Clear of every wall by 1.5 m, so the hold does not hug a building (nor clip it on the way out).
      if (near.some((b) => insideRing(b.ring, pos.x, pos.z) || ringDistance(b.ring, pos.x, pos.z) < 1.5)) continue;
      let hidden = 0;
      for (let i = 1; i < 20; i += 1) {
        const q = pos.clone().lerp(look, i / 20);
        if (near.some((b) => insideRing(b.ring, q.x, q.z) && topOf(b) > q.y)) hidden += 1;
      }
      // Walls beside the line of sight, within 12 m of it.
      const walls = near.filter((b) => {
        const t = THREE.MathUtils.clamp((b.obb.cx - pos.x) * dir.x + (b.obb.cz - pos.z) * dir.z, 0, 40);
        return Math.hypot(pos.x + dir.x * t - b.obb.cx, pos.z + dir.z * t - b.obb.cz) < 12;
      }).length;
      const intoSun = Math.max(0, dir.x * this.sunDir.x + dir.z * this.sunDir.z) / Math.hypot(this.sunDir.x, this.sunDir.z);
      const score = -hidden * 10 + Math.min(walls, 8) - 2 * intoSun;
      if (score > best.score) best = { score, pose: { pos, target: look } };
    }
    return best.pose;
  }

  /** A point in the house's frame around Lalita: x along the front, y up, z toward the street. */
  private rel(x: number, y: number, z: number): THREE.Vector3 {
    const { R, S, F } = this.frame;
    return R.clone().addScaledVector(S, x).addScaledVector(F, z).add(v(0, y, 0));
  }

  /** A point a share of the way along the walk to the shelter (on the ground). */
  private routePoint(share: number): THREE.Vector3 {
    const pts = this.town.route.points;
    const lengths = [0];
    for (let i = 1; i < pts.length; i += 1) lengths.push(lengths[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    const goal = lengths[lengths.length - 1] * clamp01(share);
    let i = 1;
    while (i < pts.length - 1 && lengths[i] < goal) i += 1;
    const t = (goal - lengths[i - 1]) / Math.max(1e-6, lengths[i] - lengths[i - 1]);
    const x = lerp(pts[i - 1][0], pts[i][0], t), z = lerp(pts[i - 1][1], pts[i][1], t);
    return v(x, this.town.field.groundAt(x, z), z);
  }

  /**
   * The push-ins end where the person's eyes are (the phone) or in front of their face (the monitor). As the camera
   * gets there, the resident's head is folded away (a first-person view of her phone); the responder is hidden once
   * the camera is ahead of his shoulders, when he is already out of the frame.
   */
  private clearCloseUps(camera: THREE.Vector3): void {
    const woman = this.residentModel;
    if (woman) {
      const neck = woman.bones.get("Neck"), head = woman.bones.get("Head");
      if (neck && head) {
        const eyes = neck.getWorldPosition(this.scratch.v).add(v(0, 0.14, 0));
        // Folded at the neck, so nothing of the face is left squashed in view while the camera is inside her head.
        head.scale.setScalar(1);
        neck.scale.setScalar(camera.distanceTo(eyes) < 0.42 ? 0.001 : 1);
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
   * Compile every material for every lighting state (interior and porch lights on and off) up front, so switching them
   * during the story never stalls a frame on shader compilation.
   */
  precompile(): void {
    this.camera.position.copy(this.frame.R).add(v(0, 220, 380));
    this.camera.lookAt(this.frame.R);
    this.camera.updateMatrixWorld(true);
    // Everything hidden for now (night lamps, rain, the call's arc, people swapped later) is shown while compiling:
    // the compiler skips hidden objects, which then compiled mid-story the first time they appeared.
    const hidden: THREE.Object3D[] = [];
    this.scene.traverse((object) => { if (!object.visible && !(object instanceof THREE.Light)) hidden.push(object); });
    hidden.forEach((object) => { object.visible = true; });
    for (const opsOn of [true, false]) {
      for (const porchOn of [true, false]) {
        for (const light of this.ops.lights) light.visible = opsOn;
        this.porch.visible = porchOn;
        this.renderer.compile(this.scene, this.camera);
      }
    }
    hidden.forEach((object) => { object.visible = false; });
    // Draw a few views of every segment once, shadows included, behind the loading screen: the town's tiles upload
    // to the GPU and the shadow pass builds its programs the first time they are drawn, which mid-move was a stall.
    const started = performance.now();
    const shares = this.quality === "high" ? [0.05, 0.4, 0.75, 1] : [0.5, 1];
    for (const segment of SEGMENT_IDS) {
      const { start, end } = segmentRange(segment);
      for (const share of shares) {
        if (performance.now() - started > 2500) break;
        this.update(start + (end - start) * share, 0, false);
        this.sun.shadow.needsUpdate = true;
        this.renderer.render(this.scene, this.camera);
        this.renderer.getContext().flush();
      }
    }
  }

  /** Camera positions sampled along every segment (for keeping trees out of the shots). */
  private cameraSamples(): THREE.Vector3[] {
    const samples: THREE.Vector3[] = [];
    const target = new THREE.Vector3(), up = new THREE.Vector3();
    for (const segment of SEGMENT_IDS) {
      const keys = this.keysFor(segment);
      for (let p = 0; p <= 1.0001; p += 0.005) {
        const pos = new THREE.Vector3();
        samplePath(keys, p, pos, target, up, this.groundAt);
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
    this.baseFov = this.camera.aspect < 0.8 ? 54 : 40;
    this.camera.fov = this.baseFov;
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
    const px = v(1, 0, 0).applyQuaternion(worldQuat), py = v(0, 1, 0).applyQuaternion(worldQuat), pz = v(0, 0, 1).applyQuaternion(worldQuat);
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
      const target = v(keys.x - 0.1, keys.y + 0.047 + typing * side, keys.z - side * 0.12);
      const s = shoulder.getWorldPosition(new THREE.Vector3());
      solveArm(shoulder, elbow, wrist, target, s.clone().add(v(-0.1, -0.5, -side * 0.45)), palmDown);
    }
    setGrip(figure, "L", GRIPS.typing);
    setGrip(figure, "R", GRIPS.typing);
  }

  /** Mali and Dao stand with Lalita: breathing, Mali a little stooped, Dao looking up at her mother. */
  private poseFamily(): void {
    poseStanding(this.mali, 0.12, this.time + 1.3, 0.07);
    poseStanding(this.dao, -0.16, this.time + 2.1, 0);
  }

  /** Pim leans over the planning table with her hands on its near (north) edge, looking down at it. */
  private posePim(): void {
    const table = this.screenGeometry(this.ops.tableScreen);
    const edge = table.center.z - table.height / 2 - 0.13;
    const figure = this.pim;
    figure.root.position.set(table.center.x + 0.45, this.ops.floor, edge - 0.2);
    figure.root.rotation.y = 0;
    this.pimShadow.position.copy(figure.root.position).add(v(0, 0.02, 0));
    poseStanding(figure, 0.5, this.time + 0.7, 0.2);
    figure.root.updateMatrixWorld(true);
    const j = figure.joints;
    const palmDown = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(v(-1, 0, 0), v(0, 0, -1), v(0, -1, 0)));
    for (const [side, shoulder, elbow, wrist] of [[1, j.shoulderL, j.elbowL, j.wristL], [-1, j.shoulderR, j.elbowR, j.wristR]] as const) {
      const target = v(figure.root.position.x + side * 0.27, this.ops.floor + 0.975, edge + 0.07);
      const s = shoulder.getWorldPosition(new THREE.Vector3());
      solveArm(shoulder, elbow, wrist, target, s.clone().add(v(side * 0.45, -0.5, -0.1)), palmDown);
    }
    setGrip(figure, "L", GRIPS.relaxed);
    setGrip(figure, "R", GRIPS.relaxed);
  }

  /** A point just above a person's head, for their name label. */
  private headAnchor(id: PersonId): THREE.Vector3 {
    const model = id === "lalita" ? this.residentModel : id === "narin" ? this.responderModel : null;
    const bone = model?.bones.get("Head");
    if (bone) return bone.getWorldPosition(new THREE.Vector3()).add(v(0, 0.32, 0));
    const figure = { lalita: this.resident, mali: this.mali, dao: this.dao, narin: this.responder, pim: this.pim }[id];
    return figure.joints.head.getWorldPosition(new THREE.Vector3()).add(v(0, id === "dao" ? 0.26 : 0.34, 0));
  }

  // --- Screens -------------------------------------------------------------------------------------------------------

  private screenGeometry(mesh: THREE.Mesh): { center: THREE.Vector3; normal: THREE.Vector3; up: THREE.Vector3; width: number; height: number } {
    mesh.updateWorldMatrix(true, false);
    const center = mesh.getWorldPosition(new THREE.Vector3());
    const quat = mesh.getWorldQuaternion(new THREE.Quaternion());
    const scale = mesh.getWorldScale(new THREE.Vector3());
    return { center, normal: v(0, 0, 1).applyQuaternion(quat), up: v(0, 1, 0).applyQuaternion(quat), width: scale.x, height: scale.y };
  }

  /** Camera pose square-on to a screen, at which it fills `fill` of the viewport height (1 = exactly). */
  private endPose(mesh: THREE.Mesh, fill = 1): Key {
    const g = this.screenGeometry(mesh);
    const distance = g.height / 2 / Math.tan(THREE.MathUtils.degToRad(this.baseFov) / 2) / fill;
    return { at: 1, pos: g.center.clone().addScaledVector(g.normal, distance), target: g.center.clone(), up: g.up.clone() };
  }

  private project(point: THREE.Vector3): { x: number; y: number; inFront: boolean } {
    const camSpace = point.clone().applyMatrix4(this.camera.matrixWorldInverse);
    const ndc = point.clone().project(this.camera);
    return { x: ((ndc.x + 1) / 2) * this.viewport.width, y: ((1 - ndc.y) / 2) * this.viewport.height, inFront: camSpace.z < -this.camera.near };
  }

  private screenQuad(mesh: THREE.Mesh): Quad | null {
    const g = this.screenGeometry(mesh);
    if (this.camera.position.clone().sub(g.center).dot(g.normal) <= 0) return null;
    const right = g.normal.clone().cross(g.up).negate().normalize();
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
    const R = this.frame.R;
    const ops = this.ops;
    const rel = (x: number, y: number, z: number) => this.rel(x, y, z);
    const phoneC = this.screenGeometry(this.phoneScreen).center;
    const k = (at: number, base: Pose): Key => ({ at, pos: base.pos, target: base.target, up: base.up, zoom: base.zoom });
    const portraitView = this.camera.aspect < 0.8;
    const through = (at: number, base: Pose): Key => ({ ...k(at, base), pass: true });
    const os: Pose = { pos: rel(-0.78, 2.02, -0.5), target: phoneC.clone() };
    // Out of the phone: first back along the push-in's own line (the head stays out of view), then over the shoulder.
    const phoneEnd = this.endPose(this.phoneScreen, PHONE_PAGE_FILL);
    const backOut: Pose = { pos: phoneEnd.pos.clone().add(os.pos.clone().sub(phoneEnd.pos).normalize().multiplyScalar(0.55)), target: phoneC.clone() };
    // Then up over the street in front of her, still looking at the phone: the camera turns to the town only once it
    // has some height, and stays clear of the porch roof and the building behind the house.
    const riseOut: Pose = { pos: rel(-0.6, 4.2, 1.6), target: rel(0.2, 1.3, 0.4) };
    // In front of the family along the clearest line of the street; higher and looking down where the lane is tight.
    const { dir: look, clear } = this.street;
    const reachFront = Math.max(3.2, Math.min(7.0, clear - 0.8));
    const reachFamily = Math.max(1.8, Math.min(4.8, clear - 0.5));
    const lift = (reach: number) => Math.max(0, 3.2 - reach) * 0.4;
    const { S, F } = this.frame;
    // From the street in front of the gate: the three of them full length and the house behind them up to the eaves.
    // The street is too narrow to back off, so this shot widens the lens a little (zoom). On a wide screen the family
    // stands right of centre, clear of the caption (bottom left); on a tall one the camera is higher and looks down so
    // the family stands above the caption.
    const portrait = this.camera.aspect < 0.8;
    // Below about 3:2 the wider lens brings the family toward the middle, under the caption: shift the shot along -S.
    const squarish = this.camera.aspect < 1.45 ? 1 : 0;
    const front: Pose = portrait
      ? { pos: R.clone().addScaledVector(look, reachFront).addScaledVector(S, 0.5).add(v(0, 3.2, 0)), target: rel(0.5, -0.6, -1.6) }
      : { pos: R.clone().addScaledVector(look, reachFront).addScaledVector(S, -0.3 - 0.6 * squarish).add(v(0, 1.65, 0)), target: rel(-0.5 - 0.6 * squarish, 2.4, -2.2), zoom: 1.3 };
    const beside: Pose = { pos: rel(-1.05, 1.8, 1.35), target: phoneC.clone() };
    // Closer, at the gate: on a tall screen higher and looking down, so the family stands above the caption; on a wide
    // one shifted so Lalita stands clear of it.
    const family: Pose = this.camera.aspect < 0.8
      ? { pos: R.clone().addScaledVector(look, reachFamily + 0.6).addScaledVector(S, 0.5).add(v(0, 3.8, 0)), target: rel(0.5, -1.6, -0.6), zoom: 1.3 }
      : { pos: R.clone().addScaledVector(look, reachFamily).addScaledVector(S, -0.1 - 0.4 * squarish).add(v(0, 1.6 + lift(reachFamily), 0)), target: rel(-0.05 - 0.4 * squarish, 1.0, -0.4) };
    // Above the street in front of the family (not over the hall across it), looking down on the family shot's heading:
    // the way to and from them is a descent or a climb, not a turn.
    const overFamily: Pose = { pos: R.clone().addScaledVector(look, 8).add(v(0, 22, 0)), target: R.clone() };
    const seat = ops.seat;
    const monitorC = this.screenGeometry(ops.monitorScreen).center;
    const tableC = this.screenGeometry(ops.tableScreen).center;
    const inside: Pose = { pos: v(seat.x - 3.6, ops.floor + 1.95, seat.z + 3.1), target: v(seat.x + 0.55, ops.floor + 1.0, seat.z) };
    const overShoulder: Pose = { pos: seat.clone().add(v(-0.62, 1.42, 0.62)), target: monitorC.clone().lerp(ops.keyboard, 0.45) };
    const pastShoulder: Pose = { pos: seat.clone().add(v(0.2, 1.3, 0.4)), target: monitorC.clone() };
    const behind: Pose = { pos: seat.clone().add(v(-1.9, 1.75, 1.05)), target: overShoulder.target };
    const roomView: Pose = { pos: tableC.clone().add(v(0, 3.4, 3.6)), target: tableC.clone().add(v(0, 0.3, -0.5)) };
    const abovePlan: Pose = { pos: tableC.clone().add(v(0, 24, 0.02)), target: tableC.clone(), up: NORTH };
    const windowFront: Pose = { pos: ops.window.clone().add(v(0, 0.9, 9)), target: ops.window.clone() };
    const H = v(this.town.home.x, R.y, this.town.home.z);
    const O = v(this.town.office.x, ops.floor, this.town.office.z);
    const cut = this.town.firstCut.point.clone().setY(this.town.field.groundAt(this.town.firstCut.point.x, this.town.firstCut.point.z));
    // Town shots.
    const wide: Pose = { pos: H.clone().add(v(-260, 260, 520)), target: H.clone().add(v(40, 0, -170)) };
    const opening: Pose = { pos: H.clone().add(v(-520, 520, 1040)), target: H.clone().add(v(30, 0, -120)) };
    // Over the house toward the river, where the low streets fill first.
    const toRiver = this.river.clone().sub(H).setY(0).normalize();
    const riverReach = this.river.distanceTo(v(H.x, this.river.y, H.z));
    const riverView: Pose = { pos: H.clone().addScaledVector(toRiver, -110).add(v(0, 120, 0)), target: H.clone().addScaledVector(toRiver, riverReach * 0.75) };
    // Down onto the walk at its low point, steep enough to see into the lane.
    const toCut = cut.clone().sub(H).setY(0).normalize();
    const across = v(-toCut.z, 0, toCut.x);
    const walkView: Pose = { pos: cut.clone().addScaledVector(toCut, -48).addScaledVector(across, 12).add(v(0, 62, 0)), target: cut.clone().addScaledVector(toCut, 10) };
    // The low point in the middle of the frame, clear of the caption (bottom left).
    const lowPoint: Pose = { pos: cut.clone().addScaledVector(toCut, -34).addScaledVector(across, 14).add(v(0, 44, 0)), target: cut.clone() };
    // Behind the home, toward the river: the house in the lower third, the streets toward the river ahead.
    const nightStreet: Pose = { pos: H.clone().addScaledVector(toRiver, -90).add(v(0, 70, 0)), target: H.clone().addScaledVector(toRiver, 60) };
    const island = this.islandPose;
    // North of the home, looking south along the walk to the shelter.
    // High enough, and a little wider, for the home near the bottom and the shelter near the top of the same frame.
    // On a tall screen the caption is too tall for the shelter as well: the home is kept, above the caption.
    const walkSouth: Pose = portraitView
      ? { pos: H.clone().add(v(60, 480, -420)), target: H.clone().add(v(20, 0, -150)) }
      : { pos: H.clone().add(v(60, 480, -420)), target: H.clone().add(v(100, 0, 420)), zoom: 1.25 };
    // Down onto Lalita's street from along it (the street runs along the house front, S), then low in the street.
    const streetMid = R.clone().addScaledVector(F, 3.1);
    const streetHigh: Pose = { pos: streetMid.clone().addScaledVector(S, 40).add(v(0, 28, 0)), target: H.clone().add(v(0, 3, 0)) };
    const streetLow: Pose = { pos: streetMid.clone().addScaledVector(S, 14).add(v(0, 4.5, 0)), target: rel(0.4, 1.4, -1) };
    const mid = H.clone().lerp(O, 0.42);
    const overview: Pose = { pos: mid.clone().add(v(980, 760, -260)), target: mid.clone().add(v(-60, 0, -120)) };
    // Over the deepest lane near the home: the walls carry the line of the highest water.
    const tide = this.tidePose;
    const alongTide = tide.target.clone().sub(tide.pos).setY(0).normalize();
    // South of the office, on the window's side: the descent arrives already facing the window.
    // An arc round to the window side (two waypoints): one waypoint south of the office made the path double back.
    const officeArc1: Pose = { pos: O.clone().add(v(130, 150, 10)), target: O.clone() };
    const officeArc2: Pose = { pos: O.clone().add(v(60, 80, 100)), target: O.clone() };
    // Through the middle of the window opening (7.2 m wide), half a metre inside the wall.
    const inWindow: Pose = { pos: ops.window.clone().add(v(0, -0.1, -0.5)), target: v(seat.x, ops.floor + 1.1, seat.z) };
    // Under the skylight, so the climb out of the room passes through the opening, not the roof slab.
    const underSky: Pose = { pos: v(ops.skylight.x, ops.skylight.y - 0.6, ops.skylight.z + 0.3), target: tableC.clone(), up: NORTH };
    const map: Pose = { pos: H.clone().lerp(cut, 0.5).add(v(0, 520, 0.05)), target: H.clone().lerp(cut, 0.5), up: NORTH };
    switch (segment) {
      case "opening":
        return [k(0, opening), k(1, wide)];
      case "everyday":
        // The walk from above, then a slow move down the street and round in front of the family.
        return [k(0, wide), k(0.34, walkSouth), k(0.46, walkSouth), through(0.64, streetHigh), through(0.82, streetLow), k(0.96, front), k(1, front)];
      case "enter-phone":
        return [k(0, front), through(0.3, beside), k(0.55, os), this.endPose(this.phoneScreen, PHONE_PAGE_FILL)];
      case "conditions":
        // Out of the phone over her shoulder and straight up and back (no orbit round her on the way out).
        return [this.atKey(0, this.endPose(this.phoneScreen, PHONE_PAGE_FILL)), through(0.08, backOut), through(0.2, riseOut), k(0.42, riverView), k(0.54, riverView), k(0.88, walkView), k(1, walkView)];
      case "return-phone":
        return [k(0, walkView), through(0.24, overFamily), k(0.42, family), k(0.55, family), k(0.82, os), this.endPose(this.phoneScreen, PHONE_PAGE_FILL)];
      case "night":
        return [
          this.atKey(0, this.endPose(this.phoneScreen, PHONE_PAGE_FILL)),
          k(0.06, this.endPose(this.phoneScreen, PHONE_PAGE_FILL * 0.8)),
          through(0.14, backOut),
          through(0.24, riseOut),
          k(0.38, nightStreet),
          k(0.44, nightStreet),
          k(0.64, lowPoint),
          k(0.72, lowPoint),
          k(0.86, walkView),
          k(1, walkView),
        ];
      case "cut-off":
        return [
          k(0, family),
          k(0.18, family),
          through(0.26, overFamily),
          k(0.34, island),
          k(0.44, island),
          k(0.54, overview),
          k(0.64, overview),
          through(0.73, officeArc1),
          through(0.79, officeArc2),
          through(0.88, windowFront),
          through(0.95, inWindow),
          k(1, inside),
        ];
      case "enter-monitor":
        return [k(0, inside), k(0.5, overShoulder), through(0.78, pastShoulder), this.endPose(ops.monitorScreen, LANDSCAPE_PAGE_FILL)];
      case "aerial":
        return [
          this.atKey(0, this.endPose(ops.monitorScreen, LANDSCAPE_PAGE_FILL)),
          through(0.04, pastShoulder),
          through(0.08, overShoulder),
          through(0.12, behind),
          k(0.22, roomView),
          through(0.28, underSky),
          through(0.34, abovePlan),
          k(0.5, map),
          k(0.74, map),
          through(0.88, abovePlan),
          through(0.94, underSky),
          { ...this.endPose(ops.tableScreen, LANDSCAPE_PAGE_FILL), up: NORTH },
        ];
      case "after": {
        // Two days later, behind a dip to dark (veilAt): down onto the lane where the water stood deepest, then up out
        // of it before turning back to the family at the gate.
        const establish: Pose = { pos: tide.pos.clone().add(v(0, 36, 0)).addScaledVector(alongTide, -36), target: tide.target.clone() };
        const tideUp: Pose = { pos: tide.pos.clone().add(v(0, 16, 0)), target: tide.target.clone().addScaledVector(alongTide, 10) };
        // A small step back along the lane at the end, never up into the eaves.
        const stepBack: Pose = { pos: family.pos.clone().addScaledVector(look, Math.max(0, Math.min(2.5, clear - reachFamily - 0.4))).add(v(0, 0.6, 0)), target: family.target };
        // The table's page shrinks back and the screen dips to dark (veilAt, p 0-0.04); the camera crosses town under it.
        const tableEnd: Key = { ...this.endPose(ops.tableScreen, LANDSCAPE_PAGE_FILL), up: NORTH };
        return [{ ...tableEnd, at: 0 }, { ...tableEnd, at: 0.02 }, k(0.04, establish), k(0.1, establish), k(0.34, tide), k(0.56, tide), through(0.66, tideUp), through(0.76, overFamily), k(0.9, family), k(1, stepBack)];
      }
    }
  }

  private atKey(at: number, key: Key): Key {
    return { ...key, at };
  }

  // --- Frame ---------------------------------------------------------------------------------------------------------

  /** Highest stage reached at or before a replay hour. */
  private maxStageUpTo(hour: number): number {
    let max = stageAtHour(this.pack.manifest, hour);
    for (const anchor of this.pack.manifest.replay.stage_anchors) if (anchor.t * 24 <= hour) max = Math.max(max, anchor.stage_m);
    return Math.min(max, this.peakStage);
  }

  /** Advance the scene to timeline position `t` and render. */
  update(t: number, dt: number, render = true): StageFrame {
    this.time += dt;
    if (render && dt > 0) this.adaptResolution(dt);
    const { segment, progress: p } = locate(t);
    const hour = replayHourAt(t);
    const stage = stageAtHour(this.pack.manifest, hour);
    // The sky follows the clock, except just after a page, where its light and weather change over a moment.
    const skyNow = skyAt(t);
    const night = skyNow.night;
    const weather = { rain: skyNow.rain, overcast: skyNow.overcast };

    // Story state per segment.
    let raise = 0, glow = 0, phoneShow = 0, monitorShow = 0, tableShow = 0, attention = 0, signal = -1, route = 0;
    const labels: Partial<Record<LabelId, boolean>> = {};
    switch (segment) {
      case "opening":
        labels.river = labels.home = p > 0.55;
        labels.shelter = labels.office = p > 0.7;
        route = ramp(p, 0.5, 0.75);
        break;
      case "everyday":
        raise = ramp(p, 0.88, 0.99);
        glow = ramp(p, 0.92, 1);
        phoneShow = ramp(p, 0.94, 1);
        labels.home = labels.route = labels.shelter = p > 0.3 && p < 0.5;
        labels.mali = labels.dao = p > 0.9;
        if (this.camera.aspect < 0.8) labels.dao = false;
        route = 1 - ramp(p, 0.48, 0.62);
        break;
      case "enter-phone":
        raise = 1; glow = 1; phoneShow = 1;
        break;
      case "conditions":
        raise = 1 - 0.5 * ramp(p, 0.05, 0.3);
        glow = 1 - ramp(p, 0.16, 0.3);
        phoneShow = 1 - ramp(p, 0.1, 0.2);
        labels.river = p > 0.36 && p < 0.56;
        labels.low = labels.route = p > 0.74;
        route = ramp(p, 0.62, 0.78);
        break;
      case "return-phone":
        raise = 0.5 + 0.5 * ramp(p, 0.55, 0.85);
        glow = ramp(p, 0.76, 0.88);
        phoneShow = ramp(p, 0.86, 0.98);
        labels.lalita = labels.mali = labels.dao = p > 0.38 && p < 0.58;
        route = 1 - ramp(p, 0.1, 0.3);
        break;
      case "night":
        raise = 1 - 0.5 * ramp(p, 0.1, 0.3);
        glow = 1 - ramp(p, 0.14, 0.3);
        phoneShow = 1 - ramp(p, 0.12, 0.22);
        labels.home = p > 0.34 && p < 0.5;
        labels.neighbour = p > 0.36 && p < 0.5;
        labels.low = p > 0.58 && stage < this.town.firstCut.stage;
        labels.cut = p > 0.58 && stage >= this.town.firstCut.stage;
        route = ramp(p, 0.5, 0.6);
        break;
      case "cut-off":
        labels.lalita = labels.mali = labels.dao = p > 0.06 && p < 0.26;
        if (this.camera.aspect < 0.8) labels.dao = false;
        // Only while the island shot holds: on the way out they flashed past.
        labels.home = labels.neighbour = p > 0.3 && p < 0.44;
        labels.cut = p > 0.3 && p < 0.44;
        signal = p > 0.5 && p < 0.78 ? ramp(p, 0.52, 0.72) : -1;
        labels.signal = signal >= 0;
        labels.office = p >= 0.56 && p < 0.8;
        labels.wat = p > 0.52 && p < 0.7;
        labels.narin = p > 0.96;
        attention = ramp(p, 0.84, 0.98);
        route = p > 0.3 && p < 0.7 ? 1 : 0;
        break;
      case "enter-monitor":
        attention = 1;
        monitorShow = ramp(p, 0.15, 0.5);
        labels.narin = p < 0.3;
        break;
      case "aerial":
        attention = 1;
        monitorShow = 1 - ramp(p, 0.22, 0.3);
        tableShow = ramp(p, 0.8, 0.96);
        labels.home = labels.cut = labels.shelter = labels.river = p > 0.46 && p < 0.78;
        labels.pim = p > 0.15 && p < 0.26;
        route = p > 0.36 && p < 0.84 ? 1 : 0;
        break;
      case "after":
        tableShow = 1 - ramp(p, 0, 0.02);
        labels.neighbourPeak = p > 0.36 && p < 0.58;
        labels.lalita = labels.mali = labels.dao = p > 0.88 && p < 0.98;
        if (this.camera.aspect < 0.8) labels.dao = false;
        raise = 0.4;
        route = ramp(p, 0.85, 0.95);
        break;
    }

    // "Water at home" only while the model has water at the neighbours' cell.
    if (labels.neighbour && this.town.field.cellDepth(this.neighbourCell, stage) === null) labels.neighbour = false;

    this.poseResident(raise, glow);
    this.poseResponder(attention);

    // Replay water, light and weather.
    const u = this.town.uniforms;
    u.uStage.value = stage;
    u.uMaxStage.value = Math.max(stage, this.maxStageUpTo(hour));
    u.uTime.value = this.time;
    u.uRain.value = weather.rain;
    u.uNight.value = night;
    u.uWetness.value = clamp01(weather.rain * 1.3 + (hour > 84 && hour < 140 ? 0.35 : 0));
    this.town.route.setOpacity(route);
    this.town.lamps.setNight(night);
    const day = 1 - night;
    const overcast = weather.overcast;
    this.rain.material.uniforms.uTime.value = this.time;
    this.rain.material.uniforms.uIntensity.value = weather.rain;
    this.rain.mesh.visible = weather.rain > 0.01;
    const sky = this.sky.material.uniforms;
    const dayTop = new THREE.Color("#b9cfd6").lerp(new THREE.Color("#9eaaad"), overcast);
    const dayHorizon = new THREE.Color("#efe9dc").lerp(new THREE.Color("#d5d6d0"), overcast);
    sky.uTop.value.copy(dayTop).lerp(new THREE.Color("#0d1420"), night);
    sky.uHorizon.value.copy(dayHorizon).lerp(new THREE.Color("#2a2a2c"), night);
    sky.uGround.value.set("#c9c7b4").lerp(new THREE.Color("#141412"), night);
    sky.uCloud.value = 0.22 + 0.75 * overcast;
    sky.uTime.value = this.time;
    this.fog.color.copy(dayHorizon).lerp(new THREE.Color("#22252b"), night);
    // Haze thins as the camera climbs, so the flood still reads from the aerial shots.
    const altitude = Math.max(0, this.camera.position.y - 40);
    this.fog.density = (0.00022 + 0.0011 * weather.rain + 0.0004 * night) / (1 + altitude / 140);
    // Under heavy cloud the sun is nearly gone (it glinted off the wet ground in the rain).
    this.sun.intensity = 3.1 * (1 - 0.8 * overcast) * day;
    this.sun.color.set("#fff0d8").lerp(new THREE.Color("#e9eef0"), overcast);
    // The sun stays in the scene at night with no light and a frozen shadow map: hiding it would change every lit
    // material's light count and recompile them all on the first night frame (a stall of a second or more).
    this.sunUp = day > 0.02;
    this.hemi.intensity = (0.42 + 0.25 * overcast) * (0.22 + 0.78 * day);
    this.hemi.color.set("#eef0ea").lerp(new THREE.Color("#7486a6"), night);
    this.hemi.groundColor.set("#8a8466").lerp(new THREE.Color("#3a3326"), night);
    this.scene.environmentIntensity = (0.75 - 0.15 * overcast) * (0.16 + 0.84 * day);
    this.porch.intensity = 18 * night;
    this.porch.visible = night > 0.02;
    this.signal.tube.visible = this.signal.head.visible = signal >= 0;
    if (signal >= 0) {
      const total = (this.signal.tube.geometry.index?.count ?? 0);
      this.signal.tube.geometry.setDrawRange(Math.floor(total * Math.max(0, signal - 0.22)), Math.floor(total * Math.min(0.28, signal)));
      this.signal.head.position.copy(this.signal.curve.getPoint(signal));
      this.signal.head.scale.setScalar(0.8 + 0.25 * Math.sin(this.time * 8));
    }

    // Camera.
    const { pos, target, up } = this.scratch;
    const zoom = samplePath(this.keysFor(segment), p, pos, target, up, this.groundAt);
    this.camera.position.copy(pos);
    this.camera.up.copy(up);
    this.camera.lookAt(target);
    const reach = pos.distanceTo(target);
    const near = THREE.MathUtils.clamp(reach * 0.004, 0.01, 2);
    const fov = this.baseFov * zoom;
    if (Math.abs(near - this.camera.near) > this.camera.near * 0.1 || Math.abs(fov - this.camera.fov) > 0.01) {
      this.camera.near = near;
      this.camera.fov = fov;
      this.camera.updateProjectionMatrix();
    }
    this.camera.updateMatrixWorld(true);
    this.sky.mesh.position.copy(pos);
    this.rain.material.uniforms.uCenter.value.set(pos.x, pos.y - 10, pos.z);
    const fp = this.ops.footprint;
    const indoors = Math.abs(pos.x - fp.x) < fp.w / 2 && Math.abs(pos.z - fp.z) < fp.d / 2 && pos.y < this.ops.floor + 5.6;
    if (indoors) this.rain.mesh.visible = false;
    this.followShadow(pos, target);
    // People cost dozens of draw calls: each is drawn only near their place.
    const nearOps = pos.distanceTo(this.ops.seat) < 32;
    this.responder.root.visible = nearOps && !this.responderModel;
    if (this.responderModel) this.responderModel.root.visible = nearOps;
    const nearHome = pos.distanceTo(this.frame.R) < 90;
    for (const figure of [this.mali, this.dao]) figure.root.visible = nearHome;
    for (const shadow of this.familyShadows) shadow.visible = nearHome;
    if (nearHome) this.poseFamily();
    this.pim.root.visible = this.pimShadow.visible = nearOps;
    if (nearOps) this.posePim();
    this.clearCloseUps(pos);
    const opsLit = pos.distanceTo(this.ops.seat) < 48;
    for (const light of this.ops.lights) light.visible = opsLit;
    const residentCasts = pos.distanceTo(this.frame.R) < 45;
    if (residentCasts !== this.residentCastsShadow) {
      this.residentCastsShadow = residentCasts;
      (this.residentModel?.root ?? this.resident.root).traverse((object) => { object.castShadow = residentCasts; });
      this.phone.group.traverse((object) => { object.castShadow = residentCasts; });
    }

    if (render) {
      this.renderer.render(this.scene, this.camera);
      // Hand the frame's GPU commands over now. Left to the end of the task, the town's large command batches made
      // Chrome on Direct3D stall for 300-400 ms every second or two while the camera moved (measured; a flush, which
      // does not wait, removes the stalls).
      this.renderer.getContext().flush();
    }

    const frameLabels: LabelFrame[] = LABEL_IDS.map((id) => {
      const anchor = id === "signal" ? this.signal.head.position.clone().add(v(0, 16, 0)) : this.anchors[id] ?? this.headAnchor(id as PersonId);
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
      hour,
      veil: veilAt(t),
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
    const extent = THREE.MathUtils.clamp(distance * 0.95, 6, 320);
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
    const close = this.shadowExtent < 20;
    const step = close ? texel : texel * Math.round(shadow.mapSize.x / 16);
    focus.set(Math.round(focus.x / step) * step, Math.round(focus.y / step) * step, Math.round(focus.z / step) * step);
    shadow.autoUpdate = close && this.sunUp;
    if (!this.sunUp) {
      this.shadowKey = "";
    } else if (!close) {
      const key = `${focus.x.toFixed(2)},${focus.y.toFixed(2)},${focus.z.toFixed(2)},${this.shadowExtent.toFixed(2)}`;
      if (key !== this.shadowKey) {
        this.shadowKey = key;
        shadow.needsUpdate = true;
      }
    } else {
      this.shadowKey = "";
    }
    this.sun.target.position.copy(focus);
    this.sun.position.copy(focus).addScaledVector(this.sunDir, 700);
    this.sun.target.updateMatrixWorld();
  }

  dispose(): void {
    this.disposed = true;
    setArchitectureGround();
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
