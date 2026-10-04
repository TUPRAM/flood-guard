import { afterEach, describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import * as THREE from "three";
import { sampleStory } from "@/lib/landing/sample-story";
import { applyStoryFrame, createTerrainScene, DISTRICT_PLAN, getSceneTelemetry, LANDMARK_ANCHORS, type TerrainRig } from "./terrain-scene";

let rig: TerrainRig | undefined;
afterEach(() => { rig?.dispose(); rig = undefined; });
const setup = () => { rig = createTerrainScene({ labels: false }); return { scene: rig, camera: new THREE.OrthographicCamera() }; };

describe("architectural district master", () => {
  it("contains a bounded varied district and four fixed reference landmarks", () => {
    expect(DISTRICT_PLAN.buildings.length + 1).toBeGreaterThanOrEqual(30);
    expect(DISTRICT_PLAN.buildings.length + 1).toBeLessThanOrEqual(60);
    expect(new Set(DISTRICT_PLAN.buildings.map(({ roof }) => roof)).size).toBe(3);
    expect(new Set(DISTRICT_PLAN.buildings.map(({ height }) => height)).size).toBeGreaterThan(8);
    expect(Object.keys(LANDMARK_ANCHORS)).toHaveLength(4);
    for (const building of DISTRICT_PLAN.buildings) {
      expect(building.x - building.width / 2).toBeGreaterThanOrEqual(DISTRICT_PLAN.bounds.minX);
      expect(building.x + building.width / 2).toBeLessThanOrEqual(DISTRICT_PLAN.bounds.maxX);
      expect(building.z - building.depth / 2).toBeGreaterThanOrEqual(DISTRICT_PLAN.bounds.minZ);
      expect(building.z + building.depth / 2).toBeLessThanOrEqual(DISTRICT_PLAN.bounds.maxZ);
    }
  });

  it.each(["poster", "reading-column"] as const)("preserves exact dry/flood registration for %s", (composition) => {
    const { scene, camera } = setup();
    const geometry = scene.terrain.getObjectByName("DistrictBuildings_47") as THREE.Mesh;
    const geometryChecksum = () => {
      const array = geometry.geometry.getAttribute("position").array;
      return createHash("sha256").update(new Uint8Array(array.buffer, array.byteOffset, array.byteLength)).digest("hex");
    };
    const original = geometryChecksum();
    applyStoryFrame(scene, camera, 1.6, sampleStory(.235), composition);
    const dry = getSceneTelemetry(scene, camera);
    applyStoryFrame(scene, camera, 1.6, sampleStory(.40), composition);
    const wet = getSceneTelemetry(scene, camera);
    expect(wet.cameraSignature).toBe(dry.cameraSignature);
    expect(wet.landmarks).toEqual(dry.landmarks);
    expect(wet.floodAmount).toBe(1);
    expect(scene.water.visible).toBe(true);
    expect(scene.water.position.y + .012).toBeLessThan(.245);
    expect(geometryChecksum()).toBe(original);
    expect(scene.scenarioRoute.visible).toBe(false);
    expect(scene.terrain.position.toArray()).toEqual([0, 0, 0]);
    expect(scene.terrain.scale.toArray()).toEqual([1, 1, 1]);
  });

  it("does not restore access or remove flood when a sample task is acknowledged", () => {
    const { scene, camera } = setup();
    for (const progress of [.475, .615, .775, .85, .945, 1]) {
      applyStoryFrame(scene, camera, 4 / 3, sampleStory(progress));
      expect(scene.floodAmount).toBe(1);
      expect(scene.water.visible).toBe(true);
      expect(scene.scenarioRoute.visible).toBe(true);
      expect(scene.primaryRoute.visible).toBe(false);
    }
  });

  it("restores all material and connection state on reverse seeking", () => {
    const { scene, camera } = setup();
    const state = () => ({ ...getSceneTelemetry(scene, camera), water: scene.water.visible, opacity: (scene.water.material as THREE.MeshStandardMaterial).opacity, route: scene.primaryRoute.visible, interruption: scene.scenarioRoute.visible, marker: scene.marker.visible });
    applyStoryFrame(scene, camera, 4 / 3, sampleStory(.235));
    const before = state();
    for (const progress of [.35, .8, 1, .45, .235]) applyStoryFrame(scene, camera, 4 / 3, sampleStory(progress));
    expect(state()).toEqual(before);
  });

  it("generates finite geometry without imported textures or a graphics context", () => {
    const { scene } = setup();
    let triangles = 0;
    scene.world.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const positions = object.geometry.getAttribute("position").array;
      expect(Array.from(positions).every(Number.isFinite)).toBe(true);
      triangles += positions.length / 9;
    });
    expect(triangles).toBeGreaterThan(20000);
    expect(triangles).toBeLessThan(50000);
  });
});
