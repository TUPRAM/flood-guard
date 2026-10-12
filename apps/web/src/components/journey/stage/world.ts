import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import {
  BACK_STREET_Z,
  LAYOUT,
  ROAD_Z,
  SIDE_STREETS_X,
  floodedRoadRanges,
  riverZ,
  roadHeight,
  terrainHeight,
} from "@/lib/journey/terrain";

import {
  PALETTE,
  asphaltTexture,
  concreteTexture,
  contactShadowTexture,
  fbm,
  rippleNormalTexture,
  seeded,
  valueNoise,
  type Quality,
} from "./materials";
import { TERRAIN_GLSL } from "./terrain-glsl";

export { seeded, type Quality };

/**
 * The journey's illustrative landscape: painted terrain with close-range detail and wetness, a depth-aware water
 * surface, graded roads with kerbs, footpaths, markings, poles and wires, the household–clinic route overlay, the phone,
 * rain and the sky. Everything is procedural (no downloaded assets).
 */

const ROAD_HALF = 3.2;
const FOOTPATH = 1.6;

// --- Ground ----------------------------------------------------------------------------------------------------------

export interface GroundFeatures {
  /** Yards inside garden walls (rotated rectangles). */
  yards: Array<{ x: number; z: number; w: number; d: number; rotation: number }>;
  /** Concrete driveways and aprons (axis-aligned). */
  pads: Array<{ x: number; z: number; w: number; d: number }>;
}

const smooth = (t: number) => {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
};

/** Smooth ground fields sampled on a 1 m grid (the expensive part), interpolated per pixel when painting. */
interface GroundFields {
  size: number;
  step: number;
  h: Float32Array;
  mottle: Float32Array;
  dry: Float32Array;
  warp: Float32Array;
  tone: Float32Array;
  fine: Float32Array;
}

function groundFields(): GroundFields {
  const size = 281, step = 280 / (size - 1);
  const make = () => new Float32Array(size * size);
  const fields: GroundFields = { size, step, h: make(), mottle: make(), dry: make(), warp: make(), tone: make(), fine: make() };
  for (let j = 0; j < size; j += 1) {
    const z = -140 + j * step;
    for (let i = 0; i < size; i += 1) {
      const x = -140 + i * step;
      const k = j * size + i;
      fields.h[k] = terrainHeight(x, z);
      fields.mottle[k] = fbm(x / 24, z / 24, 3, 1 << 20, 11);
      fields.dry[k] = fbm(x / 52 + 7, z / 52, 2, 1 << 20, 13);
      fields.warp[k] = (fbm(x / 30, z / 30, 2, 1 << 20, 15) - 0.5) * 2.4;
      fields.tone[k] = fbm(x / 6, z / 6, 2, 1 << 20, 18);
      fields.fine[k] = fbm(x / 3, z / 3, 2, 1 << 20, 19);
    }
  }
  return fields;
}

function sampler(fields: GroundFields) {
  let k00 = 0, k10 = 0, k01 = 0, k11 = 0, fx = 0, fz = 0;
  return {
    at(x: number, z: number) {
      const gx = Math.min(fields.size - 1.001, Math.max(0, (x + 140) / fields.step));
      const gz = Math.min(fields.size - 1.001, Math.max(0, (z + 140) / fields.step));
      const i = Math.floor(gx), j = Math.floor(gz);
      fx = gx - i;
      fz = gz - j;
      k00 = j * fields.size + i;
      k10 = k00 + 1;
      k01 = k00 + fields.size;
      k11 = k01 + 1;
    },
    get(field: Float32Array) {
      return (field[k00] * (1 - fx) + field[k10] * fx) * (1 - fz) + (field[k01] * (1 - fx) + field[k11] * fx) * fz;
    },
  };
}

type RGB = [number, number, number];
const rgb = (c: THREE.Color): RGB => [c.r, c.g, c.b];
const mix = (out: RGB, c: RGB, t: number) => {
  if (t <= 0) return;
  const k = t >= 1 ? 1 : t;
  out[0] += (c[0] - out[0]) * k;
  out[1] += (c[1] - out[1]) * k;
  out[2] += (c[2] - out[2]) * k;
};

function paintGround(size: number, features: GroundFeatures): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d")!;
  const image = context.createImageData(size, size);
  const data = image.data;
  const texel = 280 / size;
  const f = groundFields();
  const s = sampler(f);
  // Linear → sRGB 8-bit lookup (the per-pixel pow would dominate the paint time).
  const lut = new Uint8ClampedArray(4096);
  for (let i = 0; i < 4096; i += 1) {
    const v = i / 4095;
    lut[i] = 255 * (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);
  }
  const P = {
    grass: rgb(PALETTE.grass), grassDeep: rgb(PALETTE.grassDeep), grassDry: rgb(PALETTE.grassDry), hill: rgb(PALETTE.hill),
    paddy: rgb(PALETTE.paddy), paddyYoung: rgb(PALETTE.paddyYoung), soil: rgb(PALETTE.soil), bund: rgb(PALETTE.bund),
    bank: rgb(PALETTE.bank), bankWet: rgb(PALETTE.bankWet), gravel: [0.33, 0.3, 0.25] as RGB,
  };
  const out: RGB = [0, 0, 0], field: RGB = [0, 0, 0];
  for (let row = 0; row < size; row += 1) {
    const z = -140 + (row + 0.5) * texel;
    const hillMix = z < -48 ? smooth((-48 - z) / 22) * 0.8 : 0;
    const dz = z - ROAD_Z;
    const shoulder = dz > ROAD_HALF - 0.2 && dz < ROAD_HALF + 1.4 ? 0.55 * (1 - smooth((dz - ROAD_HALF - 0.6) / 0.8)) : 0;
    for (let col = 0; col < size; col += 1) {
      const x = -140 + (col + 0.5) * texel;
      s.at(x, z);
      const h = s.get(f.h);
      out[0] = P.grass[0]; out[1] = P.grass[1]; out[2] = P.grass[2];
      mix(out, P.grassDeep, smooth((s.get(f.mottle) - 0.35) * 2.2));
      mix(out, P.grassDry, smooth((s.get(f.dry) - 0.55) * 4) * 0.6);
      mix(out, P.hill, hillMix);
      // Floodplain rice fields with bunds, south of the road.
      if (z > 13) {
        const river = riverZ(x);
        if (z < river - 6.5) {
          const warp = s.get(f.warp);
          const fx = (x + 140 + warp) / 21, fz = (z - 13 + warp * 0.5) / 9.6;
          const ix = Math.floor(fx), iz = Math.floor(fz);
          const pick = valueNoise(ix * 3.7 + 0.5, iz * 5.3 + 0.5, 1 << 20, 17);
          const base = pick < 0.4 ? P.paddy : pick < 0.78 ? P.paddyYoung : P.soil;
          field[0] = base[0]; field[1] = base[1]; field[2] = base[2];
          mix(field, P.grassDeep, (s.get(f.tone) - 0.5) * 0.4);
          const bx = Math.min(fx - ix, 1 - (fx - ix)) * 21, bz = Math.min(fz - iz, 1 - (fz - iz)) * 9.6;
          mix(field, P.bund, (1 - smooth((Math.min(bx, bz) - 0.18) / 0.3)) * 0.85);
          mix(out, field, smooth((z - 13) / 2.5) * smooth((river - 6.5 - z) / 2));
        }
      }
      // Swale bottom: greener and damper.
      if (z > -22 && z < 24) {
        const d = (x - 2) / 7;
        if (d * d < 9) mix(out, P.grassDeep, Math.exp(-d * d) * 0.45);
      }
      // Channel banks; gravel shoulder south of the road.
      if (h < 0.1) mix(out, P.bank, smooth((0.1 - h) / 0.8));
      if (h < -0.8) mix(out, P.bankWet, smooth((-0.8 - h) / 0.8));
      mix(out, P.gravel, shoulder);
      const shade = 0.96 + s.get(f.fine) * 0.08;
      const i = (row * size + col) * 4;
      data[i] = lut[Math.min(4095, (out[0] * shade * 4095) | 0)];
      data[i + 1] = lut[Math.min(4095, (out[1] * shade * 4095) | 0)];
      data[i + 2] = lut[Math.min(4095, (out[2] * shade * 4095) | 0)];
      data[i + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  const toPx = (value: number) => (value + 140) / texel;
  // Yards: packed earth and paving inside garden walls.
  for (const yard of features.yards) {
    context.save();
    context.translate(toPx(yard.x), toPx(yard.z));
    context.rotate(-yard.rotation);
    context.fillStyle = "rgba(184, 172, 146, 0.72)";
    context.fillRect(-yard.w / 2 / texel, -yard.d / 2 / texel, yard.w / texel, yard.d / texel);
    context.restore();
  }
  for (const pad of features.pads) {
    context.fillStyle = "rgba(200, 194, 182, 0.95)";
    context.fillRect(toPx(pad.x - pad.w / 2), toPx(pad.z - pad.d / 2), pad.w / texel, pad.d / texel);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

/** Uniforms shared with the stage: water level (for wet margins) and rain wetness. */
export interface WetUniforms {
  uLevel: { value: number };
  uWet: { value: number };
}

function groundDetail(): THREE.DataTexture {
  const size = 256;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const u = x / size, v = y / size;
      const n = fbm(u * 12, v * 12, 4, 12, 3) * 0.7 + valueNoise(u * 96, v * 96, 96, 9) * 0.3;
      const i = (y * size + x) * 4;
      data[i] = data[i + 1] = data[i + 2] = n * 255;
      data[i + 3] = 255;
    }
  }
  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  return texture;
}

export function buildTerrain(quality: Quality, features: GroundFeatures): { mesh: THREE.Mesh; uniforms: WetUniforms } {
  const size = 280;
  const segments = quality === "high" ? 240 : 140;
  const geometry = new THREE.PlaneGeometry(size, size, segments, segments);
  geometry.rotateX(-Math.PI / 2);
  const position = geometry.getAttribute("position") as THREE.BufferAttribute;
  for (let i = 0; i < position.count; i += 1) position.setY(i, terrainHeight(position.getX(i), position.getZ(i)));
  geometry.computeVertexNormals();
  const uniforms: WetUniforms = { uLevel: { value: -0.7 }, uWet: { value: 0 } };
  const detail = groundDetail();
  const material = new THREE.MeshStandardMaterial({ map: paintGround(quality === "high" ? 1536 : 1024, features), roughness: 0.97, metalness: 0 });
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms, { uDetail: { value: detail } });
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vFgWorld;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvFgWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vFgWorld;\nuniform float uLevel;\nuniform float uWet;\nuniform sampler2D uDetail;")
      .replace("#include <map_fragment>", `#include <map_fragment>
        float fgDist = length(vFgWorld - cameraPosition);
        float fgD1 = texture2D(uDetail, vFgWorld.xz / 2.6).r;
        float fgD2 = texture2D(uDetail, vFgWorld.xz / 13.0 + 0.37).r;
        diffuseColor.rgb *= mix((0.74 + 0.4 * fgD1) * (0.88 + 0.24 * fgD2), 1.0, smoothstep(35.0, 140.0, fgDist));
        float fgWet = 1.0 - smoothstep(uLevel - 0.02, uLevel + 0.5, vFgWorld.y);
        fgWet = clamp(max(fgWet, uWet * 0.5), 0.0, 1.0);
        diffuseColor.rgb *= 1.0 - 0.36 * fgWet;`)
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.45, fgWet);");
  };
  const mesh = new THREE.Mesh(geometry, material);
  mesh.receiveShadow = true;
  mesh.name = "Terrain";
  mesh.userData.detail = detail;
  return { mesh, uniforms };
}

// --- Water -----------------------------------------------------------------------------------------------------------

export interface WaterUniforms {
  uMud: { value: number };
  /** Rain on the surface: 0..1 (small expanding ripple rings). */
  uRain: { value: number };
  uTime: { value: number };
  uShallow: { value: THREE.Color };
  uDeep: { value: THREE.Color };
  uMudColor: { value: THREE.Color };
}

/** Water surface at y = level: depth-aware colour and opacity, soft shorelines, restrained ripples and reflections. */
export function buildWater(): { mesh: THREE.Mesh; normalMap: THREE.Texture; uniforms: WaterUniforms } {
  const normalMap = rippleNormalTexture();
  normalMap.repeat.set(56, 56);
  const uniforms: WaterUniforms = {
    uMud: { value: 0 },
    uRain: { value: 0 },
    uTime: { value: 0 },
    uShallow: { value: new THREE.Color("#7d7c62") },
    uDeep: { value: new THREE.Color("#3e534f") },
    uMudColor: { value: new THREE.Color("#86714f") },
  };
  const material = new THREE.MeshStandardMaterial({
    color: "#ffffff",
    roughness: 0.07,
    metalness: 0,
    transparent: true,
    normalMap,
    normalScale: new THREE.Vector2(0.16, 0.16),
    envMapIntensity: 1.35,
    depthWrite: true,
  });
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vFgWorld;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvFgWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
        varying vec3 vFgWorld;
        uniform float uMud;
        uniform float uRain;
        uniform float uTime;
        uniform vec3 uShallow;
        uniform vec3 uDeep;
        uniform vec3 uMudColor;
        ${TERRAIN_GLSL}`)
      .replace("#include <normal_fragment_maps>", `#include <normal_fragment_maps>
        normal = normalize(normal + fgRipple * 0.6 * mat3(viewMatrix) * normalize(vec3(fgLocal.x, 0.0, fgLocal.y)));`)
      .replace("#include <color_fragment>", `#include <color_fragment>
        float fgDepth = vFgWorld.y - fgTerrain(vFgWorld.x, vFgWorld.z);
        if (fgDepth < 0.0) discard;
        float fgDeep = smoothstep(0.0, 1.8, fgDepth);
        vec3 fgCol = mix(uShallow, uDeep, fgDeep);
        fgCol = mix(fgCol, uMudColor, uMud * (1.0 - fgDeep * 0.55));
        float fgEdge = 1.0 - smoothstep(0.0, 0.08, fgDepth);
        fgCol = mix(fgCol, fgCol * 1.18 + 0.03, fgEdge * 0.6);
        diffuseColor.rgb = fgCol;
        // Rain: sparse expanding rings perturb the normal (restrained; only while it rains).
        vec2 fgCell = floor(vFgWorld.xz * 1.6);
        vec2 fgLocal = fract(vFgWorld.xz * 1.6) - 0.5;
        float fgSeed = fract(sin(dot(fgCell, vec2(12.9898, 78.233))) * 43758.5453);
        float fgPhase = fract(uTime * 0.9 + fgSeed);
        float fgRing = length(fgLocal - (vec2(fgSeed, fract(fgSeed * 7.3)) - 0.5) * 0.4);
        float fgRipple = uRain * (1.0 - fgPhase) * smoothstep(0.05, 0.0, abs(fgRing - fgPhase * 0.45));
        // Shallow water stays see-through (the submerged road reads through it); depth makes it opaque.
        diffuseColor.a = smoothstep(0.0, 0.035, fgDepth) * mix(0.48, 0.94, smoothstep(0.0, 0.8, fgDepth));`);
  };
  // Only where the ground can be under water (the shader discards dry pixels, which defeats early depth rejection,
  // so a full-screen plane would shade every pixel of the frame).
  const cell = 2, half = 140, maxLevel = 1.1;
  const positions: number[] = [];
  for (let x = -half; x < half; x += cell) {
    for (let z = -half; z < half; z += cell) {
      const low = Math.min(terrainHeight(x, z), terrainHeight(x + cell, z), terrainHeight(x, z + cell), terrainHeight(x + cell, z + cell), terrainHeight(x + cell / 2, z + cell / 2));
      if (low > maxLevel) continue;
      positions.push(x, 0, z, x, 0, z + cell, x + cell, 0, z, x + cell, 0, z, x, 0, z + cell, x + cell, 0, z + cell);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const uvs = new Float32Array((positions.length / 3) * 2);
  for (let i = 0; i < positions.length / 3; i += 1) {
    uvs[i * 2] = (positions[i * 3] + half) / (half * 2);
    uvs[i * 2 + 1] = 1 - (positions[i * 3 + 2] + half) / (half * 2);
  }
  geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  geometry.computeVertexNormals();
  const mesh = new THREE.Mesh(geometry, material);
  mesh.receiveShadow = true;
  mesh.renderOrder = 2;
  mesh.name = "Water";
  return { mesh, normalMap, uniforms };
}

// --- Roads -----------------------------------------------------------------------------------------------------------

/** A ribbon following the terrain along a polyline of (x, z) points, with UVs: u across (m / uTile), v along (m / vTile). */
function strip(points: Array<[number, number]>, width: number, lift: number, step = 1, vTile = 4, uTile = width, height = terrainHeight): THREE.BufferGeometry {
  const samples: THREE.Vector2[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const [x0, z0] = points[i], [x1, z1] = points[i + 1];
    const count = Math.max(1, Math.ceil(Math.hypot(x1 - x0, z1 - z0) / step));
    for (let k = 0; k < count; k += 1) samples.push(new THREE.Vector2(x0 + ((x1 - x0) * k) / count, z0 + ((z1 - z0) * k) / count));
  }
  samples.push(new THREE.Vector2(...points[points.length - 1]));
  const positions: number[] = [], uvs: number[] = [], indices: number[] = [];
  let run = 0;
  samples.forEach((p, i) => {
    if (i > 0) run += p.distanceTo(samples[i - 1]);
    const prev = samples[Math.max(0, i - 1)], next = samples[Math.min(samples.length - 1, i + 1)];
    const tangent = next.clone().sub(prev).normalize();
    const normal = new THREE.Vector2(-tangent.y, tangent.x).multiplyScalar(width / 2);
    for (const side of [-1, 1]) {
      const x = p.x + normal.x * side, z = p.y + normal.y * side;
      positions.push(x, height(x, z) + lift, z);
      uvs.push(((side + 1) / 2) * (width / uTile), run / vTile);
    }
    if (i < samples.length - 1) {
      const a = i * 2;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** A vertical face along a straight east–west line at z, from the terrain up to `top` above it. */
function kerbFace(x0: number, x1: number, z: number, bottom: number, top: number, facing: 1 | -1): THREE.BufferGeometry {
  const positions: number[] = [], uvs: number[] = [], indices: number[] = [];
  const count = Math.max(1, Math.ceil(x1 - x0));
  for (let i = 0; i <= count; i += 1) {
    const x = x0 + ((x1 - x0) * i) / count;
    const ground = terrainHeight(x, z);
    positions.push(x, ground + bottom, z, x, ground + top, z);
    uvs.push(x / 1.6, 0, x / 1.6, (top - bottom) / 1.6);
    if (i < count) {
      const a = i * 2;
      if (facing > 0) indices.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
      else indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function withWetness(material: THREE.MeshStandardMaterial, uniforms: WetUniforms, puddles: boolean): THREE.MeshStandardMaterial {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vFgWorld;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvFgWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vFgWorld;\nuniform float uWet;\nuniform float uLevel;")
      .replace("#include <map_fragment>", `#include <map_fragment>
        float fgWet = clamp(max(uWet, 1.0 - smoothstep(uLevel - 0.02, uLevel + 0.35, vFgWorld.y)), 0.0, 1.0);
        float fgPuddle = ${puddles ? "smoothstep(0.56, 0.6, sin(vFgWorld.x * 0.37) * 0.25 + sin(vFgWorld.z * 0.9 + vFgWorld.x * 0.11) * 0.25 + 0.5) * fgWet" : "0.0"};
        diffuseColor.rgb *= 1.0 - 0.32 * fgWet - 0.12 * fgPuddle;`)
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.32, fgWet);\nroughnessFactor = mix(roughnessFactor, 0.06, fgPuddle);");
  };
  return material;
}

export interface Roads {
  group: THREE.Group;
}

export function buildRoads(quality: Quality, wet: WetUniforms): Roads {
  const group = new THREE.Group();
  group.name = "Roads";
  const asphaltMap = asphaltTexture();
  const concreteMap = concreteTexture();
  // Road surfaces sit a few centimetres over the terrain and are drawn with a depth offset, so the ground mesh (which
  // interpolates between its vertices) never pokes through them as green specks, even from high above.
  const surface = { polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 };
  const asphalt = withWetness(new THREE.MeshStandardMaterial({ color: "#8f8d86", map: asphaltMap, roughness: 0.9, ...surface }), wet, true);
  const concrete = withWetness(new THREE.MeshStandardMaterial({ color: "#d3cdc0", map: concreteMap, roughness: 0.93, ...surface }), wet, false);
  const marking = withWetness(new THREE.MeshStandardMaterial({ color: "#ece7da", roughness: 0.72, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -8 }), wet, false);

  const add = (geometries: THREE.BufferGeometry[], material: THREE.Material, name: string, shadows = true) => {
    const mesh = new THREE.Mesh(mergeGeometries(geometries)!, material);
    geometries.forEach((g) => g.dispose());
    mesh.receiveShadow = shadows;
    mesh.name = name;
    group.add(mesh);
    return mesh;
  };

  add([strip([[-140, ROAD_Z], [140, ROAD_Z]], ROAD_HALF * 2, 0.06, 1, 6.4, 6.4)], asphalt, "Road");

  // Markings: dashed centre line, solid edge lines.
  const marks: THREE.BufferGeometry[] = [];
  for (let x = -138; x < 138; x += 6) marks.push(strip([[x, ROAD_Z], [x + 3, ROAD_Z]], 0.13, 0.075, 1));
  for (const side of [-1, 1]) marks.push(strip([[-140, ROAD_Z + side * (ROAD_HALF - 0.25)], [140, ROAD_Z + side * (ROAD_HALF - 0.25)]], 0.12, 0.075, 1));
  add(marks, marking, "Markings");

  // Concrete side streets and back street.
  const streets: THREE.BufferGeometry[] = [];
  for (const x of SIDE_STREETS_X) streets.push(strip([[x, ROAD_Z - ROAD_HALF + 0.05], [x, -46]], 4.4, 0.09, 1, 4, 4.4));
  streets.push(strip([[-62, BACK_STREET_Z], [66, BACK_STREET_Z]], 4.4, 0.1, 1, 4, 4.4));
  streets.push(strip([[LAYOUT.operations.x, BACK_STREET_Z], [LAYOUT.operations.x, LAYOUT.operations.z + 7.5]], 5, 0.09, 1, 4, 5));
  add(streets, concrete, "Streets");

  // Raised footpath with kerbs on the north side through the town, broken at the side streets.
  const pathZ = ROAD_Z - ROAD_HALF - FOOTPATH / 2;
  const runs: Array<[number, number]> = [];
  let start = -74;
  for (const sx of [...SIDE_STREETS_X].sort((a, b) => a - b)) {
    runs.push([start, sx - 2.4]);
    start = sx + 2.4;
  }
  runs.push([start, 74]);
  const path: THREE.BufferGeometry[] = [];
  for (const [a, b] of runs) {
    if (b - a < 1) continue;
    path.push(strip([[a, pathZ], [b, pathZ]], FOOTPATH, 0.2, 1, 1.6, FOOTPATH));
    path.push(kerbFace(a, b, ROAD_Z - ROAD_HALF, 0.0, 0.2, 1));
    path.push(kerbFace(a, b, ROAD_Z - ROAD_HALF - FOOTPATH, -0.05, 0.2, -1));
  }
  add(path, concrete, "Footpath");

  // Concrete utility poles with crossarms, insulators and sagging wires; a street lamp on every other pole.
  const poleParts: THREE.BufferGeometry[] = [];
  const wireParts: THREE.BufferGeometry[] = [];
  const poleZ = ROAD_Z - ROAD_HALF - FOOTPATH + 0.3;
  const poleXs: number[] = [];
  for (let x = -118; x <= 118; x += 28) poleXs.push(x + (x === 2 ? 6 : 0));
  const tops: Array<Array<THREE.Vector3>> = [];
  poleXs.forEach((x, index) => {
    const y = terrainHeight(x, poleZ) + 0.2;
    const pole = new THREE.CylinderGeometry(0.1, 0.16, 8.6, 4);
    pole.rotateY(Math.PI / 4);
    pole.translate(x, y + 4.3, poleZ);
    poleParts.push(pole.toNonIndexed());
    const arm = new THREE.BoxGeometry(0.12, 0.12, 1.9);
    arm.translate(x, y + 8.1, poleZ);
    poleParts.push(arm.toNonIndexed());
    const anchors: THREE.Vector3[] = [];
    for (const ax of [-0.8, 0, 0.8]) {
      const insulator = new THREE.CylinderGeometry(0.035, 0.05, 0.16, 8);
      insulator.translate(x, y + 8.24, poleZ + ax);
      poleParts.push(insulator.toNonIndexed());
      anchors.push(new THREE.Vector3(x, y + 8.32, poleZ + ax));
    }
    anchors.push(new THREE.Vector3(x, y + 6.4, poleZ + 0.14)); // telecom bundle
    tops.push(anchors);
    if (index % 2 === 0) {
      const lampArm = new THREE.CylinderGeometry(0.035, 0.035, 2.2, 6);
      lampArm.rotateX(Math.PI / 2 - 0.25);
      lampArm.translate(x, y + 7.2, poleZ + 1.05);
      poleParts.push(lampArm.toNonIndexed());
      const head = new THREE.BoxGeometry(0.22, 0.1, 0.5);
      head.translate(x, y + 7.42, poleZ + 2.1);
      poleParts.push(head.toNonIndexed());
    }
  });
  for (let i = 0; i < tops.length - 1; i += 1) {
    for (let k = 0; k < tops[i].length; k += 1) {
      const a = tops[i][k], b = tops[i + 1][k];
      const sag = k === 3 ? 0.55 : 0.4;
      const points: THREE.Vector3[] = [];
      for (let s = 0; s <= 16; s += 1) {
        const t = s / 16;
        points.push(new THREE.Vector3().lerpVectors(a, b, t).add(new THREE.Vector3(0, -sag * 4 * t * (1 - t), 0)));
      }
      wireParts.push(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 16, k === 3 ? 0.022 : 0.011, 4, false));
    }
  }
  const fixedPoles = poleParts.map((g) => { g.deleteAttribute("uv"); return g; });
  const poleMesh = add(fixedPoles, new THREE.MeshStandardMaterial({ color: PALETTE.pole, roughness: 0.86 }), "Poles");
  poleMesh.castShadow = true;
  if (quality === "high" || wireParts.length) {
    const wires = add(wireParts.map((g) => { g.deleteAttribute("uv"); return g; }), new THREE.MeshStandardMaterial({ color: "#2c3133", roughness: 0.6 }), "Wires", false);
    wires.castShadow = quality === "high";
  }
  return { group };
}

// --- Contact shadows (static) ----------------------------------------------------------------------------------------

/** Soft ambient-occlusion shadows draped on the terrain around building footprints. */
export function buildContactShadows(rects: Array<{ x: number; z: number; w: number; d: number; rotation: number; strength?: number }>): THREE.Mesh {
  const texture = contactShadowTexture(0.2, 0.26);
  const parts: THREE.BufferGeometry[] = [];
  for (const rect of rects) {
    const g = new THREE.PlaneGeometry(rect.w, rect.d, 6, 6);
    g.rotateX(-Math.PI / 2);
    const c = Math.cos(rect.rotation), s = Math.sin(rect.rotation);
    const p = g.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < p.count; i += 1) {
      const lx = p.getX(i), lz = p.getZ(i);
      const x = rect.x + lx * c + lz * s, z = rect.z - lx * s + lz * c;
      p.setXYZ(i, x, terrainHeight(x, z) + 0.035, z);
    }
    const colors = new Float32Array(p.count * 3).fill(rect.strength ?? 1);
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    parts.push(g);
  }
  const material = new THREE.MeshBasicMaterial({ color: "#1d2219", alphaMap: texture, transparent: true, opacity: 0.5, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
  const mesh = new THREE.Mesh(mergeGeometries(parts)!, material);
  parts.forEach((g) => g.dispose());
  mesh.renderOrder = 1;
  mesh.name = "ContactShadows";
  return mesh;
}

// --- Route overlay ---------------------------------------------------------------------------------------------------

/**
 * The usual household–clinic connection: a flat, soft-edged teal band painted along the road lane (it follows the
 * ground), with ring markers at both ends. The stretch through the swale is a separate band that floats on the water
 * when the road is covered, and turns amber and dashed when the connection is affected.
 */
export interface Connection {
  group: THREE.Group;
  dryMaterial: THREE.MeshBasicMaterial;
  crossingMaterial: THREE.MeshBasicMaterial;
  crossingMid: THREE.Vector3;
  midDry: THREE.Vector3;
  /** Lift the crossing band onto the water surface (call when the water level changes). */
  setWaterLevel(level: number): void;
  setAffected(affected: number): void;
  tick(time: number): void;
}

function bandTexture(dashed: boolean): THREE.DataTexture {
  const w = 64, h = 64;
  const data = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const u = x / (w - 1), v = y / h;
      const edge = Math.min(u, 1 - u);
      let alpha = THREE.MathUtils.smoothstep(edge, 0.0, 0.22);
      const core = 1 - THREE.MathUtils.smoothstep(Math.abs(u - 0.5), 0.06, 0.16);
      if (dashed && v > 0.55) alpha = 0;
      const i = (y * w + x) * 4;
      data[i] = data[i + 1] = data[i + 2] = 255 * (0.82 + 0.18 * core);
      data[i + 3] = 255 * alpha * (0.72 + 0.28 * core);
    }
  }
  const texture = new THREE.DataTexture(data, w, h, THREE.RGBAFormat);
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

export function buildConnection(): Connection {
  const [crossStart, crossEnd] = floodedRoadRanges("affected")[0];
  const margin = 1.5;
  const lane = ROAD_Z - 1.6;
  const width = 1.05;
  const homeGateZ = LAYOUT.home.z + 3.3 + 3.0;
  const clinicStepZ = LAYOUT.clinic.z + 4.5 + 2.8 + 1.2;
  const roadLevel = (x: number, z: number) => {
    const dz = z - ROAD_Z;
    if (Math.abs(dz) < ROAD_HALF) return roadHeight(x);
    if (dz < -ROAD_HALF && dz > -ROAD_HALF - FOOTPATH) return terrainHeight(x, z) + 0.2;
    return terrainHeight(x, z);
  };
  const solid = bandTexture(false);
  const dashed = bandTexture(true);
  const dryMaterial = new THREE.MeshBasicMaterial({ color: PALETTE.teal, map: solid, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  const crossingMaterial = new THREE.MeshBasicMaterial({ color: PALETTE.teal, map: solid, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  const group = new THREE.Group();
  group.name = "Connection";
  const gx0 = LAYOUT.resident.x, gx1 = LAYOUT.clinicGate.x;
  // West: from the home gate down to the lane and east to the swale; east: from the swale to the clinic steps.
  const west = strip([[gx0, homeGateZ], [gx0, lane - 0.6], [gx0 + 0.6, lane], [crossStart - margin, lane]], width, 0.08, 0.5, 3, width, roadLevel);
  const east = strip([[crossEnd + margin, lane], [gx1 - 0.6, lane], [gx1, lane - 0.6], [gx1, clinicStepZ]], width, 0.08, 0.5, 3, width, roadLevel);
  group.add(new THREE.Mesh(west, dryMaterial), new THREE.Mesh(east, dryMaterial));
  const crossing = strip([[crossStart - margin, lane], [crossEnd + margin, lane]], width * 1.08, 0.08, 0.25, 2.2, width * 1.08, roadLevel);
  const crossingMesh = new THREE.Mesh(crossing, crossingMaterial);
  crossingMesh.renderOrder = 3;
  group.add(crossingMesh);
  const base = (crossing.getAttribute("position") as THREE.BufferAttribute).array.slice();
  for (const [x, z] of [[gx0, homeGateZ], [gx1, clinicStepZ]]) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.85, 40), dryMaterial);
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(x, terrainHeight(x, z) + (z < ROAD_Z - ROAD_HALF - FOOTPATH ? 0.09 : 0.29), z);
    group.add(ring);
  }
  group.traverse((object) => { object.renderOrder = Math.max(object.renderOrder, 3); });
  const mid = (crossStart + crossEnd) / 2;
  let lastLevel = Number.NaN;
  return {
    group,
    dryMaterial,
    crossingMaterial,
    crossingMid: new THREE.Vector3(mid, roadHeight(mid) + 0.6, lane),
    midDry: new THREE.Vector3(-10, roadHeight(-10) + 0.6, lane),
    setWaterLevel(level: number) {
      if (Math.abs(level - lastLevel) < 1e-3) return;
      lastLevel = level;
      const p = crossing.getAttribute("position") as THREE.BufferAttribute;
      for (let i = 0; i < p.count; i += 1) p.setY(i, Math.max(base[i * 3 + 1], level + 0.05));
      p.needsUpdate = true;
    },
    setAffected(affected: number) {
      crossingMaterial.color.copy(PALETTE.teal).lerp(PALETTE.amber, affected);
      const want = affected > 0.5 ? dashed : solid;
      if (crossingMaterial.map !== want) {
        crossingMaterial.map = want;
        crossingMaterial.needsUpdate = true;
      }
    },
    tick(time: number) {
      dashed.offset.y = -time * 0.25;
    },
  };
}

// --- Phone -----------------------------------------------------------------------------------------------------------

function roundedRect(w: number, h: number, r: number): THREE.Shape {
  const shape = new THREE.Shape();
  shape.moveTo(-w / 2 + r, -h / 2);
  shape.lineTo(w / 2 - r, -h / 2);
  shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  shape.lineTo(w / 2, h / 2 - r);
  shape.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  shape.lineTo(-w / 2 + r, h / 2);
  shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  shape.lineTo(-w / 2, -h / 2 + r);
  shape.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return shape;
}

export interface Phone {
  group: THREE.Group;
  /** Unit plane scaled to the screen size; the real page is projected onto it. */
  screen: THREE.Mesh;
  body: THREE.Mesh;
  /** Thickness of the body (m), for the grip. */
  thickness: number;
  resize(screenWidth: number, screenHeight: number): void;
  dispose(): void;
}

/** A modelled phone: rounded aluminium frame, glass front with a slim black border, camera module, side buttons. */
export function buildPhone(): Phone {
  const group = new THREE.Group();
  group.name = "Phone";
  const frameMaterial = new THREE.MeshStandardMaterial({ color: "#3a4144", roughness: 0.3, metalness: 0.75 });
  const glassMaterial = new THREE.MeshStandardMaterial({ color: "#07090a", roughness: 0.06, metalness: 0.1, envMapIntensity: 1.3 });
  const lensMaterial = new THREE.MeshStandardMaterial({ color: "#0d1012", roughness: 0.04, metalness: 0.4 });
  const body = new THREE.Mesh(new THREE.BufferGeometry(), frameMaterial);
  body.castShadow = true;
  const front = new THREE.Mesh(new THREE.BufferGeometry(), glassMaterial);
  const camera = new THREE.Group();
  const buttons = new THREE.Group();
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: "#0d1416", toneMapped: false }));
  group.add(body, front, camera, buttons, screen);
  const depth = 0.0062, bevel = 0.0012;
  const thickness = depth + 2 * bevel;
  const disposeChildren = (g: THREE.Group) => {
    g.children.forEach((child) => (child as THREE.Mesh).geometry.dispose());
    g.clear();
  };
  return {
    group,
    screen,
    body,
    thickness,
    resize(sw: number, sh: number) {
      const border = 0.0032;
      const w = sw + 2 * border + 0.0016, h = sh + 2 * border + 0.006;
      body.geometry.dispose();
      const shape = roundedRect(w, h, Math.min(w, h) * 0.13);
      const geometry = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 3, curveSegments: 10 });
      geometry.translate(0, 0, -depth / 2);
      body.geometry = geometry;
      front.geometry.dispose();
      front.geometry = new THREE.ShapeGeometry(roundedRect(w - 0.0012, h - 0.0012, Math.min(w, h) * 0.12), 10);
      front.position.z = depth / 2 + bevel + 0.0002;
      screen.scale.set(sw, sh, 1);
      screen.position.z = depth / 2 + bevel + 0.0005;
      disposeChildren(camera);
      const bump = new THREE.Mesh(new THREE.ExtrudeGeometry(roundedRect(w * 0.36, w * 0.36, w * 0.08), { depth: 0.0012, bevelEnabled: false, curveSegments: 6 }), frameMaterial);
      bump.position.set(w / 2 - w * 0.25, h / 2 - w * 0.25, -depth / 2 - bevel - 0.0012);
      camera.add(bump);
      for (const [lx, ly] of [[-0.25, 0.25], [-0.25, -0.25], [0.25, 0.25]] as const) {
        const lens = new THREE.Mesh(new THREE.CylinderGeometry(w * 0.055, w * 0.055, 0.0016, 18), lensMaterial);
        lens.rotation.x = Math.PI / 2;
        lens.position.set(bump.position.x + lx * w * 0.2 * 2, bump.position.y + ly * w * 0.2 * 2, -depth / 2 - bevel - 0.0016);
        camera.add(lens);
      }
      disposeChildren(buttons);
      for (const [y, len] of [[h * 0.22, h * 0.12], [h * 0.05, h * 0.07]] as const) {
        const button = new THREE.Mesh(new THREE.BoxGeometry(0.0014, len, 0.0034), frameMaterial);
        button.position.set(w / 2 + bevel + 0.0004, y, 0);
        buttons.add(button);
      }
    },
    dispose() {
      body.geometry.dispose();
      front.geometry.dispose();
      disposeChildren(camera);
      disposeChildren(buttons);
      [frameMaterial, glassMaterial, lensMaterial].forEach((m) => m.dispose());
    },
  };
}

// --- Weather and sky -------------------------------------------------------------------------------------------------

/** Rain streaks in a volume that follows the camera; intensity 0 hides them. */
export function buildRain(quality: Quality): { mesh: THREE.LineSegments; material: THREE.ShaderMaterial } {
  const count = quality === "high" ? 2600 : 1100;
  const random = seeded(31);
  const positions = new Float32Array(count * 2 * 3);
  const ends = new Float32Array(count * 2);
  for (let i = 0; i < count; i += 1) {
    const x = (random() - 0.5) * 60, y = random() * 40, z = (random() - 0.5) * 60;
    positions.set([x, y, z, x, y, z], i * 6);
    ends[i * 2] = 0;
    ends[i * 2 + 1] = 1;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aEnd", new THREE.BufferAttribute(ends, 1));
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { uTime: { value: 0 }, uCenter: { value: new THREE.Vector3() }, uIntensity: { value: 0 } },
    vertexShader: `
      attribute float aEnd;
      uniform float uTime;
      uniform vec3 uCenter;
      varying float vEnd;
      void main() {
        vec3 p = position;
        p.y = mod(p.y - uTime * 13.0, 40.0) - 12.0 + aEnd * 0.9;
        p.x += aEnd * 0.12;
        vEnd = aEnd;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p + vec3(uCenter.x, uCenter.y, uCenter.z), 1.0);
      }`,
    fragmentShader: `
      uniform float uIntensity;
      varying float vEnd;
      void main() { gl_FragColor = vec4(0.86, 0.9, 0.92, uIntensity * 0.36 * (1.0 - vEnd * 0.6)); }`,
  });
  const mesh = new THREE.LineSegments(geometry, material);
  mesh.frustumCulled = false;
  mesh.name = "Rain";
  return { mesh, material };
}

const SKY_GLSL = /* glsl */ `
  uniform vec3 uTop;
  uniform vec3 uHorizon;
  uniform vec3 uGround;
  uniform vec3 uSunDir;
  uniform float uCloud;
  uniform float uTime;
  varying vec3 vDir;
  float fgHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float fgNoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(fgHash(i), fgHash(i + vec2(1.0, 0.0)), u.x), mix(fgHash(i + vec2(0.0, 1.0)), fgHash(i + vec2(1.0, 1.0)), u.x), u.y);
  }
  float fgFbm(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * fgNoise(p); p *= 2.03; a *= 0.5; } return s; }
  vec3 fgSky(vec3 dir, bool clouds) {
    float h = clamp(dir.y, -1.0, 1.0);
    vec3 col = mix(uHorizon, uTop, smoothstep(0.0, 0.55, h));
    col = mix(col, uGround, smoothstep(0.0, -0.08, h));
    float sun = max(dot(dir, uSunDir), 0.0);
    col += vec3(1.0, 0.86, 0.66) * (pow(sun, 8.0) * 0.12 + pow(sun, 64.0) * 0.25);
    if (clouds && h > 0.0) {
      vec2 p = dir.xz / (h + 0.12) * 1.4 + vec2(uTime * 0.004, uTime * 0.002);
      float c = smoothstep(0.62 - uCloud * 0.3, 0.95, fgFbm(p));
      vec3 cloud = mix(vec3(0.96, 0.94, 0.9), vec3(0.7, 0.72, 0.72), uCloud * 0.7) * (0.92 + 0.08 * pow(sun, 4.0));
      col = mix(col, cloud, c * smoothstep(0.0, 0.12, h) * (0.55 + 0.4 * uCloud));
    }
    return col;
  }
`;

export function buildSky(): { mesh: THREE.Mesh; material: THREE.ShaderMaterial } {
  const material = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      uTop: { value: new THREE.Color("#b9cfd6") },
      uHorizon: { value: new THREE.Color("#efe9dc") },
      uGround: { value: new THREE.Color("#c9c7b4") },
      uSunDir: { value: new THREE.Vector3(-0.5, 0.62, 0.6).normalize() },
      uCloud: { value: 0.2 },
      uTime: { value: 0 },
    },
    vertexShader: `varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `${SKY_GLSL}
      void main() { gl_FragColor = vec4(fgSky(normalize(vDir), true), 1.0); }`,
  });
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(500, 48, 24), material);
  mesh.name = "Sky";
  mesh.frustumCulled = false;
  return { mesh, material };
}

/** An outdoor environment for image-based lighting: the same sky (without clouds), warm ground bounce and a sun disc. */
export function buildEnvironmentScene(sunDir: THREE.Vector3): THREE.Scene {
  const scene = new THREE.Scene();
  const material = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      uTop: { value: new THREE.Color("#a9c3cc") },
      uHorizon: { value: new THREE.Color("#f2ebdc") },
      uGround: { value: new THREE.Color("#8e8f72") },
      uSunDir: { value: sunDir.clone() },
      uCloud: { value: 0 },
      uTime: { value: 0 },
    },
    vertexShader: `varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `${SKY_GLSL}
      void main() { gl_FragColor = vec4(fgSky(normalize(vDir), false), 1.0); }`,
  });
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(10, 48, 24), material));
  const sun = new THREE.Mesh(new THREE.SphereGeometry(0.5, 16, 12), new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 0.92, 0.78).multiplyScalar(14) }));
  sun.position.copy(sunDir).multiplyScalar(9);
  scene.add(sun);
  return scene;
}

// --- Screen textures (shown before the real pages fade in) -------------------------------------------------------------

/** Canvas texture for the responder's monitor before the real case view fades in. */
export function alertTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 800;
  canvas.height = 500;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#f5f2ea";
  c.fillRect(0, 0, 800, 500);
  c.fillStyle = "#152b29";
  c.fillRect(0, 0, 800, 54);
  c.fillStyle = "#faf8f2";
  c.font = "600 24px Inter, sans-serif";
  c.fillText("FloodGuard", 28, 36);
  c.fillStyle = "#9a5d0c";
  c.fillRect(40, 110, 720, 150);
  c.fillStyle = "#fff7eb";
  c.fillRect(46, 116, 708, 138);
  c.fillStyle = "#9a5d0c";
  c.font = "700 20px Inter, sans-serif";
  c.fillText("STORY MODE · SIMULATED ALERT", 70, 160);
  c.fillStyle = "#152b29";
  c.font = "500 26px Inter, sans-serif";
  c.fillText("Household near the low road crossing", 70, 202);
  c.font = "400 19px Inter, sans-serif";
  c.fillStyle = "#53656d";
  c.fillText("Illustrative scenario. Nothing was sent.", 70, 236);
  c.fillStyle = "#d9dfdc";
  for (let i = 0; i < 4; i += 1) c.fillRect(40, 300 + i * 44, 720 - i * 90, 22);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** Canvas texture for the planning table before the real command page fades in: an abstract map in the site palette. */
export function tableTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 640;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#e9e6dc";
  c.fillRect(0, 0, 1024, 640);
  c.strokeStyle = "#6f9aa0";
  c.lineWidth = 34;
  c.beginPath();
  c.moveTo(0, 470);
  c.bezierCurveTo(260, 420, 520, 560, 1024, 480);
  c.stroke();
  c.strokeStyle = "#a8a297";
  c.lineWidth = 14;
  c.beginPath();
  c.moveTo(0, 330);
  c.lineTo(1024, 330);
  for (const x of [140, 300, 700, 860]) {
    c.moveTo(x, 330);
    c.lineTo(x, 60);
  }
  c.stroke();
  c.fillStyle = "#c9b79a";
  for (let i = 0; i < 40; i += 1) c.fillRect(60 + (i % 10) * 92, 90 + Math.floor(i / 10) * 52, 44, 30);
  c.strokeStyle = "#1f8a92";
  c.lineWidth = 8;
  c.setLineDash([22, 14]);
  c.beginPath();
  c.moveTo(220, 330);
  c.lineTo(780, 330);
  c.stroke();
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}
