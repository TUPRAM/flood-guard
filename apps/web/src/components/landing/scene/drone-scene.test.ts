import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import * as THREE from "three";
import { applyDroneFrame, createDroneScene, DRONE_CAMERA, DRONE_PLAN, getDroneTelemetry, type DroneRig } from "./drone-scene";

let rig: DroneRig;
const camera = new THREE.PerspectiveCamera();
const geometryHash = () => {
  const hash = createHash("sha256");
  rig.world.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const positions = object.geometry.getAttribute("position").array;
    hash.update(new Uint8Array(positions.buffer, positions.byteOffset, positions.byteLength));
    if (object instanceof THREE.InstancedMesh) {
      const matrices = object.instanceMatrix.array;
      hash.update(new Uint8Array(matrices.buffer, matrices.byteOffset, matrices.byteLength));
    }
  });
  return hash.digest("hex");
};

beforeAll(() => { rig = createDroneScene(); });
afterAll(() => { rig.dispose(); });

describe("continuous desktop drone world", () => {
  it("embeds a detailed neighborhood inside a deterministic low-rise context", () => {
    expect(DRONE_PLAN.context.length).toBeGreaterThanOrEqual(1000);
    expect(DRONE_PLAN.context.length).toBeLessThanOrEqual(1500);
    expect(DRONE_PLAN.neighborhood.length + 1).toBeGreaterThanOrEqual(40);
    expect(DRONE_PLAN.neighborhood.length + 1).toBeLessThanOrEqual(50);
    expect(Object.keys(rig.landmarks)).toHaveLength(4);
    expect(rig.world.getObjectByName("ContinuousTerrain_NoVisibleBoundary")).toBeDefined();
    expect(rig.world.getObjectByName("EmbeddedDetailedNeighborhood")).toBeDefined();
    expect(rig.world.getObjectByName("AttachedCourtyardWings")).toBeDefined();
  });

  it.each([1920 / 1080, 1366 / 768, 1100 / 900])("preserves all four close dry/flood anchors at aspect %s", aspect => {
    applyDroneFrame(rig, camera, aspect, { flight: 1, flood: 0 });
    const dry = getDroneTelemetry(rig, camera);
    applyDroneFrame(rig, camera, aspect, { flight: 1, flood: 1 });
    const flooded = getDroneTelemetry(rig, camera);
    expect(flooded.cameraSignature).toBe(dry.cameraSignature);
    expect(flooded.landmarks).toEqual(dry.landmarks);
    expect(camera.fov).toBe(DRONE_CAMERA.fov);
    expect(rig.water.visible).toBe(true);
    expect(rig.water.position.y).toBeLessThan(.38);
    for (const point of Object.values(flooded.landmarks)) {
      expect(point.x).toBeGreaterThan(0);
      expect(point.x).toBeLessThan(1);
      expect(point.y).toBeGreaterThan(0);
      expect(point.y).toBeLessThan(1);
    }
  });

  it("changes no building or terrain geometry throughout the flight and flood", () => {
    const original = geometryHash();
    for (const flight of [0, .2, .55, .8, 1]) {
      applyDroneFrame(rig, camera, 16 / 9, { flight, flood: flight === 1 ? 1 : 0 });
      expect(geometryHash()).toBe(original);
    }
  });

  it("restores exact camera, water and pointer state on a reverse seek", () => {
    applyDroneFrame(rig, camera, 16 / 9, { flight: 0, flood: 0 });
    const initial = getDroneTelemetry(rig, camera);
    applyDroneFrame(rig, camera, 16 / 9, { flight: 1, flood: 1, pointer: [.8, -.9] });
    applyDroneFrame(rig, camera, 16 / 9, { flight: .5, flood: .6, pointer: [-.2, .5] });
    applyDroneFrame(rig, camera, 16 / 9, { flight: 0, flood: 0 });
    expect(getDroneTelemetry(rig, camera)).toEqual(initial);
    expect(rig.water.visible).toBe(false);
    expect(rig.waterTraces.visible).toBe(false);
  });

  it("keeps the terrain beyond the full camera frame throughout supported desktop framing", () => {
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -.04), ray = new THREE.Raycaster(), point = new THREE.Vector3();
    for (const aspect of [1100 / 900, 16 / 9, 2.4]) for (const flight of [0, .25, .6, 1]) {
      applyDroneFrame(rig, camera, aspect, { flight, flood: 0, pointer: [1, 1] });
      for (const x of [-1, 1]) for (const y of [-1, 1]) {
        ray.setFromCamera(new THREE.Vector2(x, y), camera);
        expect(ray.ray.intersectPlane(plane, point)).not.toBeNull();
        expect(Math.abs(point.x)).toBeLessThan(320);
        expect(Math.abs(point.z)).toBeLessThan(320);
      }
    }
  });

  it("contains only finite geometry and self-generated textures without browser image loading", () => {
    const textures = new Set<THREE.Texture>();
    rig.world.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      expect(Array.from(object.geometry.getAttribute("position").array).every(Number.isFinite)).toBe(true);
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        if ("map" in material && material.map instanceof THREE.Texture) textures.add(material.map);
      }
    });
    expect(textures.size).toBe(4);
    for (const texture of textures) expect(texture).toBeInstanceOf(THREE.DataTexture);
  });

  it("clamps invalid inputs without producing a non-finite camera", () => {
    applyDroneFrame(rig, camera, NaN, { flight: Infinity, flood: NaN, pointer: [Infinity, NaN] });
    expect(camera.matrixWorld.elements.every(Number.isFinite)).toBe(true);
    expect(camera.projectionMatrix.elements.every(Number.isFinite)).toBe(true);
    expect(rig.flight).toBe(0);
    expect(rig.floodAmount).toBe(0);
  });

  it.each([1920/1080,1366/768,1100/900])("keeps the three analytical annotations clear of the reading column at aspect %s", aspect=>{
    for(const network of [0,.5,1]){
      applyDroneFrame(rig,camera,aspect,{flight:1,flood:1,network,result:1});
      for(const point of Object.values(getDroneTelemetry(rig,camera).annotations)){
        expect(point.x).toBeGreaterThan(.36);expect(point.x).toBeLessThan(.93);
        expect(point.y).toBeGreaterThan(.23);expect(point.y).toBeLessThan(.78);
      }
    }
  });

  it("positions both opening endpoints inside the lower hero window without changing the close projection",()=>{
    applyDroneFrame(rig,camera,1366/768,{flight:0,flood:0});
    const opening=getDroneTelemetry(rig,camera);
    expect(opening.annotations.home.y).toBeGreaterThan(.59);expect(opening.annotations.home.y).toBeLessThan(.63);
    expect(opening.annotations.facility.y).toBeGreaterThan(.78);expect(opening.annotations.facility.y).toBeLessThan(.83);
    applyDroneFrame(rig,camera,1366/768,{flight:1,flood:0});
    expect(Math.abs(camera.view!.offsetY)).toBe(0);
  });

  it("changes the link style only for the explicit analytical stage and preserves registered geometry",()=>{
    applyDroneFrame(rig,camera,16/9,{flight:1,flood:1});
    const flooded=getDroneTelemetry(rig,camera),original=geometryHash();
    expect(rig.affectedRoute.visible).toBe(false);
    expect(rig.route.children.filter(child=>child.userData.affected).every(child=>child.visible)).toBe(true);
    applyDroneFrame(rig,camera,16/9,{flight:1,flood:1,network:1,result:1});
    const finding=getDroneTelemetry(rig,camera);
    expect(finding.cameraSignature).toBe(flooded.cameraSignature);expect(finding.annotations).toEqual(flooded.annotations);
    expect(geometryHash()).toBe(original);expect(rig.affectedRoute.visible).toBe(true);
    expect(rig.route.children.filter(child=>child.userData.affected).every(child=>!child.visible)).toBe(true);
    expect(rig.findingHome.visible).toBe(true);expect(finding.baselineReachable).toBe(true);expect(finding.scenarioReachable).toBe(false);
    applyDroneFrame(rig,camera,16/9,{flight:1,flood:1});
    expect(getDroneTelemetry(rig,camera)).toEqual(flooded);expect(rig.findingHome.visible).toBe(false);
  });
});
