import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { ILLUSTRATIVE_SCENARIO, ILLUSTRATIVE_FINDING, evaluateIllustrativeScenario, type ScenarioPoint } from "../../../lib/landing/illustrative-scenario";

type Point = readonly [number, number, number];
type GroundPoint = readonly [number, number];
type Building = { x: number; z: number; width: number; depth: number; height: number; angle: number; roof: number; color: string };
export interface DroneFrame { flight: number; flood: number; network?: number; result?: number; pointer?: readonly [number, number] }
export const DRONE_WORLD_ID = "original-mae-sai-inspired-access-world-v4";
export const DRONE_LANDMARKS = Object.freeze({
  Neighborhood_A: [-9, 1.3, -5], Junction_A: [-4.3, .4, .075],
  Service_A: [2.6, 1.1, 4.3], Field_A: [7.5, .12, -5.5],
} as const);
export const DRONE_CAMERA = Object.freeze({
  far: { position: [25, 38, 43] as Point, target: [-2, 0, -1] as Point, verticalViewOffset: .23 },
  close: { position: [12, 20, 23] as Point, target: [-1, .2, -.5] as Point },
  fov: 34,
});
const C = {
  ground: "#aeb5a4", hill: "#82957b", bank: "#99ac90", grass: "#819b73", field: "#b3ba94", fieldDark: "#99aa8b",
  pavement: "#bfc3b7", road: "#717c78", line: "#deddd0", wall: "#e1dfce", wallCool: "#cbd2cc",
  zinc: "#aab3af", darkRoof: "#657777", red: "#a06d57", blue: "#477c96", glass: "#5c7478",
  dark: "#354946", leaf: "#4d704e", lightLeaf: "#708957", river: "#6d9590", flood: "#968776", waterLine: "#ded8c8",
};
const roofColors = [C.zinc, C.zinc, C.darkRoof, C.red, C.zinc, C.blue, C.red];
const clamp = (value: number) => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
const smooth = (value: number) => { const t = clamp(value); return t * t * t * (t * (t * 6 - 15) + 10); };
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const hash = (x: number, z: number, salt = 0) => {
  let value = Math.imul(x + 1931, 73856093) ^ Math.imul(z + 7919, 19349663) ^ Math.imul(salt + 17, 83492791);
  value = Math.imul(value ^ value >>> 16, 2246822519); value = Math.imul(value ^ value >>> 13, 3266489917);
  return ((value ^ value >>> 16) >>> 0) / 4294967296;
};
const riverX = (z: number) => 17 + Math.sin(z * .043) * 6 + Math.sin(z * .13) * 1.3;
const mainX = (z: number) => -2.5 + Math.sin(z * .048) * 1.8;
const arterialZ = (x: number) => 5.8 - x * .1 + Math.sin(x * .045) * 1.5;

/** Authored terrain units are illustrative, not a DEM, survey or inferred flood depth. */
export function droneHeightAt(x: number, z: number): number {
  const mountain = smooth((-x - 48) / 72);
  const ridge = 10 + 15 * Math.pow(.5 + .5 * Math.sin(z * .037 + x * .021), 2);
  const rolling = Math.sin(x * .039) * Math.sin(z * .027) * .38;
  const valley = Math.max(0, mountain * ridge + rolling * smooth((Math.abs(x) - 25) / 30));
  const channel = 1 - smooth((Math.abs(x - riverX(z)) - 1.8) / 1.3);
  return .04 + valley - channel * .6;
}

function makeTexture(kind: "terrain" | "roof" | "wall" | "water") {
  const size = kind === "terrain" || kind === "water" ? 256 : 128, pixels = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const index = (y * size + x) * 4;
    const noise = (hash(x, y, 3) - .5) * (kind === "terrain" ? 19 : 9);
    const stripe = kind === "roof" && x % 12 < 2 ? -26 : 0;
    const window = kind === "wall" && ((x > 15 && x < 48) || (x > 77 && x < 110)) && ((y > 24 && y < 51) || (y > 79 && y < 106));
    const ripple = kind === "water" ? Math.sin(y*.36+Math.sin(x*.028)*2)*6+Math.sin(y*.12+x*.02)*3 : 0;
    const value = Math.round(window ? 132 : 239 + noise + stripe + ripple);
    pixels[index] = value; pixels[index + 1] = window ? 157 : value; pixels[index + 2] = window ? 155 : value; pixels[index + 3] = 255;
  }
  const texture = new THREE.DataTexture(pixels, size, size, THREE.RGBAFormat);
  texture.name = `OriginalProcedural_${kind}`; texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping; texture.wrapT = THREE.RepeatWrapping;
  texture.generateMipmaps = true; texture.minFilter = THREE.LinearMipmapLinearFilter; texture.magFilter = THREE.LinearFilter;
  texture.anisotropy = 4; texture.needsUpdate = true; return texture;
}

class Batch {
  private geometries: THREE.BufferGeometry[] = [];
  add(source: THREE.BufferGeometry, color: string, position: Point = [0, 0, 0], rotation: Point = [0, 0, 0], scale: Point = [1, 1, 1]) {
    const geometry = source.index ? source.toNonIndexed() : source.clone(); source.dispose(); geometry.deleteAttribute("uv");
    geometry.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...position), new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation)), new THREE.Vector3(...scale)));
    const rgb = new THREE.Color(color), colors = new Float32Array(geometry.getAttribute("position").count * 3);
    for (let i = 0; i < colors.length; i += 3) { colors[i] = rgb.r; colors[i + 1] = rgb.g; colors[i + 2] = rgb.b; }
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3)); this.geometries.push(geometry);
  }
  box(position: Point, size: Point, color: string, rotation: Point = [0, 0, 0]) { this.add(new THREE.BoxGeometry(...size), color, position, rotation); }
  line(points: readonly Point[], radius: number, color: string) {
    const curve = new THREE.CatmullRomCurve3(points.map(point => new THREE.Vector3(...point)));
    this.add(new THREE.TubeGeometry(curve, Math.max(3, points.length * 3), radius, 4, false), color);
  }
  finish(name: string) {
    const geometry = mergeGeometries(this.geometries, false);
    this.geometries.forEach(item => item.dispose()); this.geometries = [];
    if (!geometry) throw new Error(`Unable to assemble ${name}.`);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .87, metalness: .015 }));
    mesh.name = name; mesh.castShadow = true; mesh.receiveShadow = true; return mesh;
  }
}

function surface(points: readonly GroundPoint[]) {
  const shape = new THREE.Shape(points.map(([x, z]) => new THREE.Vector2(x, -z))); shape.closePath();
  const geometry = new THREE.ShapeGeometry(shape); geometry.rotateX(-Math.PI / 2); return geometry;
}
function gableGeometry() {
  const shape = new THREE.Shape(); shape.moveTo(-.5, 0); shape.lineTo(0, .28); shape.lineTo(.5, 0); shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: 1, bevelEnabled: false, steps: 1 }); geometry.translate(0, 0, -.5); return geometry;
}
function addRoad(batch: Batch, points: readonly GroundPoint[], width: number, markings = false, bridge = false) {
  for (let i = 1; i < points.length; i++) {
    const [ax, az] = points[i - 1], [bx, bz] = points[i], length = Math.hypot(bx - ax, bz - az);
    const x = (ax + bx) / 2, z = (az + bz) / 2, angle = -Math.atan2(bz - az, bx - ax);
    const y = bridge ? .25 : Math.max(.04, droneHeightAt(x, z));
    batch.box([x, y + .021, z], [length + .12, .035, width + .19], C.pavement, [0, angle, 0]);
    batch.box([x, y + .043, z], [length + .13, .018, width], C.road, [0, angle, 0]);
    if (markings) for (let dash = 0, count = Math.max(1, Math.floor(length / .55)); dash < count; dash++) {
      const t = (dash + .5) / count;
      batch.box([mix(ax, bx, t), y + .055, mix(az, bz, t)], [.24, .004, .025], C.line, [0, angle, 0]);
    }
  }
}

function createContextPlan(): readonly Building[] {
  const result: Building[] = [];
  for (let row = 0; row < 44; row++) for (let column = 0; column < 48; column++) {
    const x = (column - 23.5) * 3.7 + (hash(column, row, 1) - .5) * .7 + Math.sin(row * .47) * .65;
    const z = (row - 21.5) * 4.05 + (hash(column, row, 2) - .5) * .7 + Math.sin(column * .37) * .6;
    if (x < -64 || Math.abs(x - riverX(z)) < 4.4 || (x > 52 && z < -19) || (Math.abs(x) < 15 && Math.abs(z) < 13)) continue;
    if (Math.abs(x - mainX(z)) < 2 || Math.abs(z - arterialZ(x)) < 1.45 || row % 8 === 0 || column % 10 === 0) continue;
    const large = hash(column, row, 6) > .83;
    result.push({ x, z, width: large ? 3.65 : 2.3 + hash(column, row, 4) * 1.1, depth: 2.35 + hash(column, row, 5) * 1.1,
      height: .5 + hash(column, row, 7) * (large ? .7 : 1.25), angle: (hash(column, row, 8) - .5) * .24 + Math.sin(row * .4) * .07,
      roof: Math.floor(hash(column, row, 9) * 3), color: roofColors[Math.floor(hash(column, row, 10) * roofColors.length)] });
  }
  for (let row = 0; row < 16; row++) for (let column = 0; column < 26; column++) {
    const x = -50 + column * 3.7 + (hash(column, row, 31) - .5) * .65, z = -153 + row * 3.7;
    if (row % 6 === 0 || Math.abs(x - riverX(z)) < 4.5 || Math.abs(x - mainX(z)) < 2) continue;
    result.push({ x,z,width:2.2+hash(column,row,32)*1.15,depth:2.25+hash(column,row,33)*1.1,height:.6+hash(column,row,34)*1.15,
      angle:(hash(column,row,35)-.5)*.15,roof:(row+column)%3,color:roofColors[(row*2+column)%roofColors.length] });
  }
  return result;
}
function createNeighborhoodPlan(): readonly Building[] {
  const result: Building[] = [];
  const append = (x: number, z: number, id: number) => result.push({ x, z, width: 1.75 + hash(id, 1) * .65, depth: 1.3 + hash(id, 2) * .45,
    height: .58 + hash(id, 3) * .55, angle: (hash(id, 4) - .5) * .11, roof: id % 3, color: roofColors[id % roofColors.length] });
  for (const x of [-12, -9, -6]) for (const z of [-8, -5, -2, 1, 3.5, 8.3]) append(x, z, result.length);
  for (const x of [.8, 3.8, 6.8, 9.8]) for (const z of [-8, -5, -1.8, 1.1, 8.1]) {
    if (x > 6 && z < -2) continue; append(x, z, result.length);
  }
  for (const x of [-12, -9, -6, .8, 3.8, 6.8, 9.8]) append(x, -11, result.length);
  return result.filter(building=>!(building.z===-2&&building.x>-12&&building.x<0));
}
export const DRONE_PLAN = Object.freeze({
  context: Object.freeze(createContextPlan()), neighborhood: Object.freeze(createNeighborhoodPlan()),
  sourceStatus: "original_illustrative_geography_not_surveyed", seed: 19317919,
});

function addDetailedBuilding(batch: Batch, building: Building, index: number) {
  const { x, z, width: w, depth: d, height: h, angle, color } = building;
  const ground = Math.max(.04, droneHeightAt(x, z));
  const p = (px: number, y: number, pz: number): Point => [x + px * Math.cos(angle) + pz * Math.sin(angle), ground + y, z - px * Math.sin(angle) + pz * Math.cos(angle)];
  const box = (position: Point, size: Point, shade: string) => batch.box(p(...position), size, shade, [0, angle, 0]);
  box([0, .08, 0], [w + .16, .16, d + .15], C.pavement); box([0, .15 + h / 2, 0], [w, h, d], index % 4 ? C.wall : C.wallCool);
  if (building.roof === 0) {
    batch.add(gableGeometry(), color, p(0, h + .15, 0), [0, angle, 0], [w + .18, 1, d + .18]);
    box([0, h + .445, 0], [.027, .025, d + .22], C.zinc);
    for (const side of [-1, 1]) for (let rib = 1; rib < 7; rib++) {
      const offset = side * w * rib / 14; box([offset, h + .16 + .28 * (1 - Math.abs(offset) / ((w + .18) / 2)), 0], [.011, .014, d + .17], C.zinc);
    }
  } else {
    box([0, h + .18, 0], [w + .15, .065, d + .16], color);
    if (building.roof === 1) {
      box([0, h + .25, -d / 2], [w + .15, .09, .04], C.wall);
      for (const side of [-1, 1]) box([side * w / 2, h + .25, 0], [.04, .09, d], C.wall);
      box([-.3, h + .28, -.25], [.33, .17, .3], C.zinc);
      batch.add(new THREE.CylinderGeometry(.09, .09, .19, 9), C.dark, p(w * .25, h + .31, -d * .23));
    } else for (let rib = 0; rib < 15; rib++) box([-w / 2 + rib * w / 14, h + .22, 0], [.013, .008, d + .14], C.zinc);
  }
  const units = Math.max(3, Math.floor(w / .4));
  for (let unit = 0; unit < units; unit++) {
    const px = -w / 2 + (unit + .5) * w / units;
    box([px, .35, d / 2 + .009], [w / units * .79, .36, .02], unit % 3 ? C.glass : C.zinc);
    box([px - w / units / 2, .38, d / 2 + .025], [.025, .44, .035], C.wall);
    if (h > .85) box([px, .84, d / 2 + .009], [w / units * .62, .23, .021], C.glass);
  }
  box([0, .62, d / 2 + .16], [w + .05, .032, .33], color);
  for (const side of [-1, 1]) box([side * w * .44, .35, d / 2 + .25], [.022, .55, .022], C.zinc);
  box([w / 2 + .009, .54, 0], [.02, .26, d * .36], C.glass);
}

function addTreeInstances(world: THREE.Group) {
  const positions: { x: number; z: number; height: number; size: number }[] = [];
  for (let row = 0; row < 62; row++) for (let column = 0; column < 35; column++) {
    const x = -173 + column * 4.4 + hash(column, row, 20) * 3.8, z = -151 + row * 4.9 + hash(column, row, 21) * 3.8;
    if (x > -65 && hash(column, row, 22) > .13) continue;
    positions.push({ x, z, height: droneHeightAt(x, z), size: 1.3 + hash(column, row, 23) * 2.6 });
  }
  for (let i = 0; i < 100; i++) {
    const z = -150 + i * 3, x = riverX(z) + (i % 2 ? 3.7 : -4);
    positions.push({ x, z, height: Math.max(.04, droneHeightAt(x, z)), size: .8 + hash(i, 5) * .7 });
  }
  const near = [[-13, -9.7], [-10.4, -6.4], [-10.9, -1.6], [-12.9, .1], [-10.7, 5.5], [-7.2, 6.6], [-4.4, 8], [-4.3, -10], [-3.7, -6.8], [5.2, -10], [6.4, -3.1], [11.6, -6], [11.6, -3.6], [11.9, 2.5], [5.4, 6.8], [.1, 6.9], [8.4, 6.7]];
  near.forEach(([x, z], index) => positions.push({ x, z, height: .04, size: .8 + index % 3 * .12 }));
  const closeCount=positions.filter(({x,z})=>Math.hypot(x,z)<50).length;
  const canopyMaterial=new THREE.MeshStandardMaterial({ roughness: 1, color: "#ffffff" });
  const farCanopy=new THREE.IcosahedronGeometry(1,0);
  const farPositions=farCanopy.getAttribute("position"),farNormals=farCanopy.getAttribute("normal"),normal=new THREE.Vector3();
  for(let i=0;i<farPositions.count;i++){normal.fromBufferAttribute(farPositions,i).normalize();farNormals.setXYZ(i,normal.x,normal.y,normal.z);}
  const farClumps=positions.reduce((count,{x,z})=>count+(Math.hypot(x,z)<50?0:Math.hypot(x,z)>140?1:2),0);
  const crown = new THREE.InstancedMesh(farCanopy, canopyMaterial, farClumps);
  const closeCrown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 1), canopyMaterial, closeCount * 3);
  const trunks = new THREE.InstancedMesh(new THREE.CylinderGeometry(.055, .075, 1, 5), new THREE.MeshStandardMaterial({ color: "#5b6851", roughness: 1 }), positions.length);
  const matrix = new THREE.Matrix4(), rotation = new THREE.Quaternion();
  let farIndex=0,closeIndex=0;
  positions.forEach(({ x, z, height, size }, index) => {
    matrix.compose(new THREE.Vector3(x, height + size * .35, z), rotation, new THREE.Vector3(size * .45, size * .7, size * .45)); trunks.setMatrixAt(index, matrix);
    const near=Math.hypot(x,z)<50;
    for (let clump = 0; clump < (near?3:Math.hypot(x,z)>140?1:2); clump++) {
      const a = clump * 2.4 + index;
      rotation.setFromEuler(new THREE.Euler(.25, a, .1));
      matrix.compose(new THREE.Vector3(x + Math.cos(a) * size * .2, height + size * (.67 + clump * .11), z + Math.sin(a) * size * .2), rotation, new THREE.Vector3(size * .39, size * .46, size * .4));
      const mesh=near?closeCrown:crown,instance=near?closeIndex++:farIndex++;
      mesh.setMatrixAt(instance, matrix); mesh.setColorAt(instance, new THREE.Color(clump % 2 ? C.leaf : C.lightLeaf));
    }
  });
  crown.name = "InstancedForestCanopy"; closeCrown.name="DetailedNeighborhoodCanopy"; trunks.name = "InstancedTreeTrunks";
  crown.castShadow = true; crown.receiveShadow = true; trunks.castShadow = true;
  closeCrown.castShadow=true;closeCrown.receiveShadow=true;
  world.add(crown, closeCrown, trunks); return positions.length;
}

export interface DroneRig {
  world: THREE.Group; landmarks: Readonly<Record<keyof typeof DRONE_LANDMARKS, THREE.Object3D>>;
  water: THREE.Mesh; waterTraces: THREE.Mesh; sun: THREE.DirectionalLight;
  route: THREE.Group; affectedRoute: THREE.Group; analyticalNodes: THREE.Mesh; endpointRings: THREE.Mesh; findingHome: THREE.Mesh;
  contextMaterials: { material: THREE.MeshStandardMaterial; color: THREE.Color }[];
  networkAmount: number; resultAmount: number;
  flight: number; floodAmount: number; contextBuildingCount: number; buildingCount: number; treeCount: number;
  dispose: () => void;
}

/** One synchronous master, with original generated textures and no network asset dependency. */
export function createDroneScene(): DroneRig {
  const world = new THREE.Group(); world.name = DRONE_WORLD_ID;
  const terrainTexture = makeTexture("terrain"), roofTexture = makeTexture("roof"), wallTexture=makeTexture("wall"), waterTexture=makeTexture("water");
  terrainTexture.repeat.set(64, 64);
  const terrainGeometry = new THREE.PlaneGeometry(640, 640, 128, 128); terrainGeometry.rotateX(-Math.PI / 2);
  const vertex = terrainGeometry.getAttribute("position"), colors = new Float32Array(vertex.count * 3);
  const grass = new THREE.Color(C.ground), hill = new THREE.Color(C.hill), tint = new THREE.Color();
  for (let i = 0; i < vertex.count; i++) {
    const x = vertex.getX(i), z = vertex.getZ(i); vertex.setY(i, droneHeightAt(x, z));
    tint.copy(grass).lerp(hill, smooth((-x - 42) / 70)); tint.multiplyScalar(.97 + hash(i, 5) * .065);
    colors[i * 3] = tint.r; colors[i * 3 + 1] = tint.g; colors[i * 3 + 2] = tint.b;
  }
  terrainGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3)); terrainGeometry.computeVertexNormals();
  const terrain = new THREE.Mesh(terrainGeometry, new THREE.MeshStandardMaterial({ map: terrainTexture, vertexColors: true, roughness: 1 }));
  terrain.name = "ContinuousTerrain_NoVisibleBoundary"; terrain.receiveShadow = true; world.add(terrain);

  const fields = new Batch();
  for (let row = 0; row < 9; row++) for (let column = 0; column < 7; column++) {
    const x = 58 + column * 9, z = -116 + row * 10, w = 7.9, d = 8.8;
    const y = Math.max(.04, droneHeightAt(x, z)) + .07;
    fields.box([x, y, z], [w, .024, d], (column + row) % 3 ? C.field : C.fieldDark, [0, .04, 0]);
    for (let stripe = 0; stripe < 8; stripe++) fields.box([x - w / 2 + stripe * w / 8, y + .017, z], [.035, .01, d * .94], C.grass, [0, .04, 0]);
  }
  fields.add(surface([[6,-9.5],[11.6,-9.5],[11.6,-3.4],[6.2,-3.7]]), C.field, [0, .09, 0]);
  for (let stripe = 0; stripe < 11; stripe++) fields.box([6.5 + stripe * .43, .105, -6.5], [.025, .012, 5.2], C.fieldDark);
  const fieldMesh = fields.finish("CultivatedParcels"); fieldMesh.castShadow = false; world.add(fieldMesh);
  const yards=new Batch();
  DRONE_PLAN.context.forEach((building,index)=>{
    if(Math.abs(building.x)>52||Math.abs(building.z)>86)return;
    const geometry=new THREE.PlaneGeometry(building.width+.7,building.depth+.75);geometry.rotateX(-Math.PI/2);
    yards.add(geometry,["#aab0a4","#9da896","#b6b9ad"][index%3],[building.x,Math.max(.04,droneHeightAt(building.x,building.z))+.008,building.z],[0,building.angle,0]);
  });
  const yardMesh=yards.finish("FlushHardstandingAndCourtyards");yardMesh.castShadow=false;world.add(yardMesh);

  const infrastructure = new Batch();
  const northSouth = Array.from({ length: 101 }, (_, index): GroundPoint => { const z = -300 + index * 6; return [mainX(z), z]; });
  const eastWest = Array.from({ length: 101 }, (_, index): GroundPoint => { const x = -150 + index * 3; return [x, arterialZ(x)]; });
  addRoad(infrastructure, northSouth, 1.05, true); addRoad(infrastructure, eastWest, 1.2, true, true);
  for (let row = 1; row < 6; row++) {
    const z = (row * 8 - 21.5) * 4.05;
    addRoad(infrastructure, [[-65,z],[riverX(z)-3.2,z]], .6);
    addRoad(infrastructure, [[riverX(z)+3.2,z],[92,z]], .6);
  }
  for (const column of [10, 20, 30, 40]) {
    const x = (column - 23.5) * 3.7;
    if (Math.abs(x) < 15) continue;
    addRoad(infrastructure, [[x,-94],[x,94]], .62);
  }
  addRoad(infrastructure, [[-14,2.9],[-8.7,2.9],[-4.3,2.7],[-2.25,2.3],[.2,2.4],[5.5,2.6],[12,2.4]], .39);
  addRoad(infrastructure, [[-14,-3.65],[-7,-3.65],[-2.6,-3.2],[3.8,-3.1],[6,-2.9]], .31);
  addRoad(infrastructure, [[-4.3,-12],[-4.3,3],[-4.1,8.7]], .39);
  addRoad(infrastructure, [[5.5,-11],[5.5,2.6],[5.8,7]], .27);
  addRoad(infrastructure, [[-14,6.7],[-8,6.7],[-2.2,6.5],[1.6,6.4],[6,6.4],[12,6.2]], .32);
  const bridgeX = riverX(4), bridgeZ = arterialZ(bridgeX);
  for (const side of [-1, 1]) {
    infrastructure.box([bridgeX, .55, bridgeZ + side * .8], [8, .07, .06], C.dark, [0, .05, 0]);
    for (let post = 0; post < 13; post++) infrastructure.box([bridgeX - 3.6 + post * .6, .43, bridgeZ + side * .8], [.04, .25, .04], C.dark);
  }
  const nodePositions = new Map<string, ScenarioPoint>(ILLUSTRATIVE_SCENARIO.nodes.map(node => [node.id, node.position]));
  for (const link of ILLUSTRATIVE_SCENARIO.links) addRoad(infrastructure, [nodePositions.get(link.from)!, nodePositions.get(link.to)!], .29);
  world.add(infrastructure.finish("ContinuousStreetNetworkAndRiverCrossing"));

  const riverPoints = Array.from({ length: 181 }, (_, i) => -280 + i * 560 / 180);
  const riverShape: GroundPoint[] = [...riverPoints.map((z): GroundPoint => [riverX(z) - 2.25, z]), ...riverPoints.slice().reverse().map((z): GroundPoint => [riverX(z) + 2.25, z])];
  const river = new THREE.Mesh(surface(riverShape), new THREE.MeshStandardMaterial({ color: C.river, roughness: .5, metalness: .05 }));
  river.name = "ContinuousRiver"; river.position.y = .065; river.receiveShadow = true; world.add(river);
  const banks = new Batch();
  for (const side of [-1, 1]) banks.line(riverPoints.map((z): Point => [riverX(z) + side * 2.35, .095, z]), .065, C.bank);
  const bankMesh = banks.finish("ContinuousRiverBanks"); bankMesh.castShadow = false; world.add(bankMesh);

  const wallMaterial = new THREE.MeshStandardMaterial({ color: C.wall, map:wallTexture, roughness: .92 });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: "#ffffff", map: roofTexture, roughness: .77, metalness: .035 });
  const walls = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), wallMaterial, DRONE_PLAN.context.length);
  walls.name = "InstancedLowRiseTownWalls";
  const roofMeshes = [0, 1, 2].map(kind => {
    const count = DRONE_PLAN.context.filter(building => building.roof === kind).length;
    const mesh = new THREE.InstancedMesh(kind === 0 ? gableGeometry() : new THREE.BoxGeometry(1, .07, 1), roofMaterial, count);
    mesh.name = `InstancedTownRoofs_${kind}`; mesh.castShadow = true; mesh.receiveShadow = true; return mesh;
  });
  const matrix = new THREE.Matrix4(), quaternion = new THREE.Quaternion(), roofIndices = [0, 0, 0];
  DRONE_PLAN.context.forEach((building, index) => {
    const { x, z, width, depth, height, angle, roof, color } = building, y = Math.max(.04, droneHeightAt(x, z));
    quaternion.setFromEuler(new THREE.Euler(0, angle, 0));
    matrix.compose(new THREE.Vector3(x, y + height / 2, z), quaternion, new THREE.Vector3(width, height, depth)); walls.setMatrixAt(index, matrix);
    walls.setColorAt(index, new THREE.Color(index % 5 ? "#ffffff" : "#c7d0ca"));
    matrix.compose(new THREE.Vector3(x, y + height + .035, z), quaternion, new THREE.Vector3(width + .18, 1, depth + .18));
    roofMeshes[roof].setMatrixAt(roofIndices[roof], matrix); roofMeshes[roof].setColorAt(roofIndices[roof]++, new THREE.Color(color).lerp(new THREE.Color("#b2bab6"), .65));
  });
  walls.castShadow = true; walls.receiveShadow = true; world.add(walls, ...roofMeshes);
  const annexes=DRONE_PLAN.context.filter((_,index)=>hash(index,17,41)>.74);
  const annexWalls=new THREE.InstancedMesh(new THREE.BoxGeometry(1,1,1),wallMaterial,annexes.length);
  const annexRoofs=new THREE.InstancedMesh(new THREE.BoxGeometry(1,.055,1),roofMaterial,annexes.length);
  annexWalls.name="AttachedCourtyardWings";annexRoofs.name="AttachedLowerRoofs";
  annexes.forEach((building,index)=>{
    const {x,z,width,depth,height,angle,color}=building,side=index%2?1:-1;
    const px=side*width*.42,pz=depth*.4,wx=x+px*Math.cos(angle)+pz*Math.sin(angle),wz=z-px*Math.sin(angle)+pz*Math.cos(angle);
    const y=Math.max(.04,droneHeightAt(wx,wz)),h=height*.65;
    quaternion.setFromEuler(new THREE.Euler(0,angle,0));
    matrix.compose(new THREE.Vector3(wx,y+h/2,wz),quaternion,new THREE.Vector3(width*.57,h,depth*.58));annexWalls.setMatrixAt(index,matrix);
    matrix.compose(new THREE.Vector3(wx,y+h+.035,wz),quaternion,new THREE.Vector3(width*.57+.12,1,depth*.58+.12));annexRoofs.setMatrixAt(index,matrix);annexRoofs.setColorAt(index,new THREE.Color(color).lerp(new THREE.Color("#b2bab6"),.65));
  });
  annexWalls.castShadow=true;annexWalls.receiveShadow=true;annexRoofs.castShadow=true;annexRoofs.receiveShadow=true;world.add(annexWalls,annexRoofs);

  const architecture = new Batch(); DRONE_PLAN.neighborhood.forEach((building, index) => addDetailedBuilding(architecture, { ...building, color: (Math.abs(building.x + 9) < .1 && Math.abs(building.z + 5) < 3.1) || (building.x === -12 && building.z === -5) ? "#426e88" : new THREE.Color(building.color).lerp(new THREE.Color("#b4bdb7"), .45).getStyle() }, index));
  architecture.box([2.6, .21, 4.3], [4.6, .34, 2.25], C.pavement);
  architecture.box([2.6, .89, 3.76], [4.1, 1.03, 1.02], C.wall); architecture.box([2.6, 1.455, 3.76], [4.4, .1, 1.3], "#335f78");
  for (let rib = 0; rib < 36; rib++) architecture.box([.48 + rib * .121, 1.515, 3.76], [.014, .01, 1.28], C.darkRoof);
  for (let bay = 0; bay < 9; bay++) architecture.box([.92 + bay * .42, .96, 4.28], [.29, .43, .02], C.glass);
  architecture.box([2.6, .49, 5.37], [4.6, .035, .06], C.wall);
  for (let post = 0; post < 13; post++) architecture.box([.4 + post * .365, .69, 5.36], [.022, .43, .022], C.dark);
  architecture.box([2.6, .9, 5.36], [4.6, .022, .022], C.dark);
  architecture.box([1.1, .26, 5.6], [.9, .12, .58], C.pavement);
  const architectureMesh = architecture.finish("EmbeddedDetailedNeighborhood"); world.add(architectureMesh);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(architectureMesh.geometry, 32), new THREE.LineBasicMaterial({ color: C.dark, opacity: .18, transparent: true }));
  edges.name = "NeighborhoodArchitecturalEdges"; world.add(edges);
  const streetDetails = new Batch();
  for (const [x, z, color] of [[-3.05,-7,C.zinc],[-1.9,-.4,C.blue],[-7,5.3,C.red],[5.4,5.1,C.wall],[7.3,2.1,C.zinc]] as const) {
    streetDetails.box([x,.2,z],[.2,.15,.44],color); streetDetails.box([x,.3,z],[.18,.09,.22],C.glass);
  }
  for (const [x, z] of [[-3.25,3.8],[-4,1.9],[.1,5.3],[6,6.6],[-7.6,2.5],[-11,6.2]]) {
    streetDetails.box([x,.6,z],[.027,1.12,.027],C.dark); streetDetails.box([x+.13,1.16,z],[.29,.022,.036],C.dark);
  }
  for (const [x,z] of [[-8.4,2.1],[-6.7,6.2],[1.2,4.8],[3.5,4.8],[5.8,2.1]]) {
    streetDetails.add(new THREE.CylinderGeometry(.044,.035,.15,7),C.blue,[x,.36,z]);
    streetDetails.add(new THREE.SphereGeometry(.035,8,6),"#bca18b",[x,.475,z]);
    for(const side of [-1,1]) streetDetails.box([x+side*.025,.2,z],[.033,.2,.04],C.dark);
  }
  world.add(streetDetails.finish("NeighborhoodStreetDetails"));
  const treeCount = addTreeInstances(world);

  const floodShape = ILLUSTRATIVE_SCENARIO.floodFootprint;
  waterTexture.repeat.set(.75,.75);
  const water = new THREE.Mesh(surface(floodShape), new THREE.MeshStandardMaterial({ color: C.flood, map:waterTexture, bumpMap:waterTexture, bumpScale:.018, transparent: true, opacity: .92, roughness: .29, metalness: 0, depthWrite: true }));
  water.name = "ConnectedIllustrativeInundation"; water.receiveShadow = true; water.renderOrder = 1; world.add(water);
  const shore = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(floodShape.map(([x,z])=>new THREE.Vector3(x,.008,z))),new THREE.LineBasicMaterial({color:"#c7c0ad",transparent:true,opacity:.45}));
  shore.name="AuthoredWaterContactEdge";shore.renderOrder=2;water.add(shore);
  const traces = new Batch();
  for (const [x,z,length] of [[-4.3,.2,.45],[-1.3,-.2,.65],[6.7,-.8,.6],[9.3,.2,.7],[13,-.7,.9],[3,-.6,.7]]) {
    traces.line([[x-length,.009,z],[x,.009,z+.025],[x+length*.7,.009,z]],.009,C.waterLine);
    traces.line([[x-length*.45,.009,z+.13],[x+length*.35,.009,z+.13]],.005,C.waterLine);
  }
  const waterTraces = traces.finish("InundationSurfaceTraces"); waterTraces.castShadow = false; waterTraces.renderOrder = 2; world.add(waterTraces);
  const route = new THREE.Group(); route.name = "SYN-BASELINE-PATH";
  const affectedRoute = new THREE.Group(); affectedRoute.name = ILLUSTRATIVE_SCENARIO.assumedDisruptedLinkId;
  const routeMaterial = new THREE.MeshBasicMaterial({ color: "#0f4c81", depthTest: true, depthWrite: false, transparent: true, toneMapped: false });
  const disruptedMaterial = new THREE.MeshBasicMaterial({ color: "#9b5f08", depthTest: false, depthWrite: false, transparent: true, toneMapped: false });
  const casingMaterial = new THREE.MeshBasicMaterial({ color: "#ffffff", depthTest: true, depthWrite: false, transparent: true });
  const makeRouteSegment = (a: ScenarioPoint, b: ScenarioPoint, parent: THREE.Group, material: THREE.Material, radius: number, order: number) => {
    const curve = new THREE.LineCurve3(new THREE.Vector3(a[0], .37, a[1]), new THREE.Vector3(b[0], .37, b[1]));
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 1, radius, 5, false), material); mesh.renderOrder = order; parent.add(mesh); return mesh;
  };
  const baseline = evaluateIllustrativeScenario().baselinePath!;
  for (const link of ILLUSTRATIVE_SCENARIO.links) {
    if (!baseline.includes(link.id)) continue;
    const a = nodePositions.get(link.from)!, b = nodePositions.get(link.to)!;
    const casing = makeRouteSegment(a, b, route, casingMaterial, .095, 10); casing.name = `${link.id}-casing`;
    const segment = makeRouteSegment(a, b, route, routeMaterial, .057, 11); segment.name = link.id;
    if (link.id === ILLUSTRATIVE_SCENARIO.assumedDisruptedLinkId) {
      casing.userData.affected = segment.userData.affected = true;
      const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      for (let distance = 0; distance < length; distance += .37) {
        const from = distance / length, to = Math.min(length, distance + .22) / length;
        makeRouteSegment([mix(a[0],b[0],from),mix(a[1],b[1],from)], [mix(a[0],b[0],to),mix(a[1],b[1],to)], affectedRoute, disruptedMaterial, .082, 12);
      }
    }
  }
  for (const affected of [false,true]) for (const material of [casingMaterial,routeMaterial]) {
    const parts = route.children.filter((object): object is THREE.Mesh => object instanceof THREE.Mesh && object.material === material && Boolean(object.userData.affected) === affected);
    const combined = new THREE.Mesh(mergeGeometries(parts.map(part=>part.geometry),false)!,material);
    combined.name=affected?`${ILLUSTRATIVE_SCENARIO.assumedDisruptedLinkId}-${material===casingMaterial?"casing":"solid"}`:`SyntheticBaseline-${material===casingMaterial?"casing":"solid"}`;
    combined.userData.affected=affected;combined.renderOrder=material===casingMaterial?10:11;
    for(const part of parts){route.remove(part);part.geometry.dispose();}route.add(combined);
  }
  const dashedParts=affectedRoute.children as THREE.Mesh[];
  const dashedMesh=new THREE.Mesh(mergeGeometries(dashedParts.map(part=>part.geometry),false)!,disruptedMaterial);dashedMesh.renderOrder=12;
  for(const part of [...dashedParts]){affectedRoute.remove(part);part.geometry.dispose();}affectedRoute.add(dashedMesh);
  world.add(route, affectedRoute);
  const nodes = new Batch();
  for (const node of ILLUSTRATIVE_SCENARIO.nodes) nodes.add(new THREE.CylinderGeometry(.115,.115,.018,12),"#0f4c81",[node.position[0],.4,node.position[1]]);
  for(const link of ILLUSTRATIVE_SCENARIO.links)if(!baseline.includes(link.id)){
    const a=nodePositions.get(link.from)!,b=nodePositions.get(link.to)!;
    nodes.line([[a[0],.37,a[1]],[b[0],.37,b[1]]],.03,"#8198a6");
  }
  const analyticalNodes = nodes.finish("SyntheticNetworkNodes"); analyticalNodes.renderOrder = 13;
  (analyticalNodes.material as THREE.MeshStandardMaterial).depthTest = false; world.add(analyticalNodes);
  const endpointBatch = new Batch();
  for (const [x,z] of [[-9,-5],[2.6,3.76]]) endpointBatch.add(new THREE.TorusGeometry(.68,.025,5,28),"#0f4c81",[x,.42,z],[Math.PI/2,0,0]);
  const endpointRings = endpointBatch.finish("SyntheticOriginDestinationRings"); endpointRings.renderOrder=14;
  (endpointRings.material as THREE.MeshStandardMaterial).depthTest=false;world.add(endpointRings);
  const findingHome = new THREE.Mesh(new THREE.TorusGeometry(.87,.034,5,32),new THREE.MeshBasicMaterial({color:"#9b5f08",transparent:true,depthTest:false,depthWrite:false,toneMapped:false}));
  findingHome.name="SYN-HOME-A-AccessFinding";findingHome.rotation.x=Math.PI/2;findingHome.position.set(-9,.43,-5);findingHome.renderOrder=15;world.add(findingHome);
  const landmarks = Object.fromEntries(Object.entries(DRONE_LANDMARKS).map(([id, point]) => {
    const object = new THREE.Object3D(); object.name = id; object.position.set(point[0],point[1],point[2]); world.add(object); return [id,object];
  })) as Record<keyof typeof DRONE_LANDMARKS, THREE.Object3D>;
  world.add(new THREE.HemisphereLight("#d8e9f5","#697b69",1.35),new THREE.AmbientLight("#ffffff",.45));
  const sun = new THREE.DirectionalLight("#fff8ee",2.65); sun.name="DistrictDaylight"; sun.position.set(-65,125,65); sun.castShadow=true;
  sun.shadow.mapSize.set(2048,2048); sun.shadow.camera.near=.5; sun.shadow.camera.far=350; sun.shadow.normalBias=.035; sun.shadow.bias=-.00007; sun.shadow.radius=2;
  world.add(sun,sun.target);
  const contextMaterials = [terrain.material,wallMaterial,roofMaterial,fieldMesh.material,yardMesh.material].map(material => ({ material: material as THREE.MeshStandardMaterial, color: (material as THREE.MeshStandardMaterial).color.clone() }));
  return {world,landmarks,water,waterTraces,sun,route,affectedRoute,analyticalNodes,endpointRings,findingHome,contextMaterials,networkAmount:0,resultAmount:0,flight:0,floodAmount:0,contextBuildingCount:DRONE_PLAN.context.length,buildingCount:DRONE_PLAN.context.length+DRONE_PLAN.neighborhood.length+1,treeCount,
    dispose() {
      const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>(),textures=new Set<THREE.Texture>();
      world.traverse(object=>{if(object instanceof THREE.Mesh||object instanceof THREE.Line){geometries.add(object.geometry);for(const material of Array.isArray(object.material)?object.material:[object.material]){materials.add(material);if("map" in material&&material.map instanceof THREE.Texture)textures.add(material.map);}}});
      geometries.forEach(item=>item.dispose());materials.forEach(item=>item.dispose());textures.forEach(item=>item.dispose());sun.shadow.map?.dispose();
    },
  };
}

/** Direct state application: no clocks, accumulated transforms or hidden scene substitutions. */
export function applyDroneFrame(rig:DroneRig,camera:THREE.PerspectiveCamera,aspect:number,frame:DroneFrame) {
  const flight=clamp(frame.flight),flood=clamp(frame.flood),t=smooth(flight),ratio=Number.isFinite(aspect)&&aspect>0?aspect:16/9;
  const network=clamp(frame.network??0),result=clamp(frame.result??0);
  rig.flight=flight;rig.floodAmount=flood;rig.networkAmount=network;rig.resultAmount=result;
  const target=new THREE.Vector3(...DRONE_CAMERA.far.target).lerp(new THREE.Vector3(...DRONE_CAMERA.close.target),t);
  const position=new THREE.Vector3(...DRONE_CAMERA.far.position).lerp(new THREE.Vector3(...DRONE_CAMERA.close.position),t);
  position.y+=Math.sin(Math.PI*t)*3;
  position.sub(target).multiplyScalar(Math.max(1,(16/9)/ratio)).add(target);
  const pointer=frame.pointer??[0,0],pointerX=Number.isFinite(pointer[0])?Math.max(-1,Math.min(1,pointer[0])):0,pointerY=Number.isFinite(pointer[1])?Math.max(-1,Math.min(1,pointer[1])):0;
  position.x+=pointerX*mix(1.25,.28,t);position.y+=pointerY*mix(.7,.17,t);
  camera.position.copy(position);camera.lookAt(target);camera.fov=DRONE_CAMERA.fov;camera.aspect=ratio;camera.near=.15;camera.far=900;
  camera.setViewOffset(ratio*1000,1000,-ratio*1000*.16,-1000*DRONE_CAMERA.far.verticalViewOffset*(1-t),ratio*1000,1000);camera.updateProjectionMatrix();camera.updateMatrixWorld();
  rig.water.visible=flood>.001;rig.water.position.y=.075+flood*.225;
  (rig.water.material as THREE.MeshStandardMaterial).opacity=Math.min(.94,flood*1.8);
  rig.waterTraces.visible=flood>.7;rig.waterTraces.position.y=rig.water.position.y+.005;
  rig.route.children.forEach(segment=>{if(segment.userData.affected)segment.visible=network<.5;});
  rig.affectedRoute.visible=network>=.5;
  rig.analyticalNodes.visible=network>.05;
  rig.findingHome.visible=result>.001;(rig.findingHome.material as THREE.MeshBasicMaterial).opacity=result;
  for(const {material,color} of rig.contextMaterials)material.color.copy(color).lerp(new THREE.Color("#e4e9e7"),network*.58);
  const shadowHalf=mix(145,30,t);rig.sun.shadow.camera.left=-shadowHalf;rig.sun.shadow.camera.right=shadowHalf;rig.sun.shadow.camera.top=shadowHalf;rig.sun.shadow.camera.bottom=-shadowHalf;rig.sun.shadow.camera.updateProjectionMatrix();
}

export function getDroneTelemetry(rig:DroneRig,camera:THREE.PerspectiveCamera) {
  rig.world.updateMatrixWorld(true);
  const landmarks=Object.fromEntries(Object.entries(rig.landmarks).map(([id,object])=>{const p=object.getWorldPosition(new THREE.Vector3()).project(camera);return[id,{x:(p.x+1)/2,y:(1-p.y)/2}];}));
  const annotations=Object.fromEntries(Object.entries(ILLUSTRATIVE_SCENARIO.annotationAnchors).map(([id,point])=>{const p=new THREE.Vector3(...point).project(camera);return[id,{x:(p.x+1)/2,y:(1-p.y)/2}];}));
  return {worldId:DRONE_WORLD_ID,flight:rig.flight,floodAmount:rig.floodAmount,waterHeight:rig.water.position.y,buildingCount:rig.buildingCount,contextBuildingCount:rig.contextBuildingCount,
    networkAmount:rig.networkAmount,resultAmount:rig.resultAmount,annotations,baselineReachable:ILLUSTRATIVE_FINDING.baseline.reachable,scenarioReachable:ILLUSTRATIVE_FINDING.scenario.reachable,
    cameraSignature:[...camera.matrixWorld.elements,...camera.projectionMatrix.elements].map(value=>value.toFixed(6)).join(","),landmarks};
}
