import * as THREE from "three";

import type { FloodField } from "@/lib/journey/town-data";

import { ATLAS_TILES, type FacadeAtlas } from "./facade-atlas";

/**
 * Materials of the real-map town. Every surface that water can reach reads the same field: a texture of the replay's
 * cells (smoothed depth factor k_s, effective HAND h, ground height, low-confidence flag) and the replay stage of the
 * moment. The water surface is k_s × stage and a place is wet exactly when stage > h (the model's own rule, at the
 * cell centres), so walls, ground, roads and the water mesh agree on where the water is and how deep.
 *
 * Night is a uniform: windows of a building whose ground floor is dry may be lit; street lamps glow; the sky darkens.
 */

export interface TownUniforms {
  uStage: { value: number };
  /** The highest stage reached so far in the story (for tide lines and mud once the water goes down). */
  uMaxStage: { value: number };
  uTime: { value: number };
  uRain: { value: number };
  /** 0 = day, 1 = night. */
  uNight: { value: number };
  /** General surface wetness from rain (0..1). */
  uWetness: { value: number };
  uFlood: { value: THREE.Texture };
  /** x0, z0 of the field's first cell edge and 1/width, 1/depth in metres. */
  uFloodXform: { value: THREE.Vector4 };
}

/** The flood field as a half-float RGBA texture (R k_s, G h, B ground, A low confidence), linearly filtered. */
export function floodTexture(field: FloodField): { texture: THREE.DataTexture; xform: THREE.Vector4 } {
  const { cols, rows } = field;
  const data = new Uint16Array(cols * rows * 4);
  const toHalf = THREE.DataUtils.toHalfFloat;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const i = r * cols + c;
      // Row 0 of the texture is the field's first row (smallest z).
      data[i * 4] = toHalf(field.kSmooth[i]);
      data[i * 4 + 1] = toHalf(field.hand[i]);
      data[i * 4 + 2] = toHalf(field.ground[i]);
      data[i * 4 + 3] = toHalf(field.low[i]);
    }
  }
  const texture = new THREE.DataTexture(data, cols, rows, THREE.RGBAFormat, THREE.HalfFloatType);
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearFilter;
  texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.needsUpdate = true;
  // Cell centres sit at x0 + (c + 0.5) dx; texel centres at (c + 0.5) / cols.
  const xform = new THREE.Vector4(field.x0, field.z0, 1 / (cols * field.dx), 1 / (rows * field.dz));
  return { texture, xform };
}

export function createTownUniforms(field: FloodField): TownUniforms {
  const { texture, xform } = floodTexture(field);
  return {
    uStage: { value: 0 },
    uMaxStage: { value: 0 },
    uTime: { value: 0 },
    uRain: { value: 0 },
    uNight: { value: 0 },
    uWetness: { value: 0 },
    uFlood: { value: texture },
    uFloodXform: { value: xform },
  };
}

/** Uniform declarations and helpers shared by every town shader. */
export const FLOOD_GLSL = /* glsl */ `
uniform sampler2D uFlood;
uniform vec4 uFloodXform;
uniform float uStage;
uniform float uMaxStage;
uniform float uTime;
uniform float uRain;
uniform float uNight;
uniform float uWetness;
vec4 floodAt(vec2 xz) {
  return texture2D(uFlood, (xz - uFloodXform.xy) * uFloodXform.zw);
}
float fgHash(vec3 p) {
  p = fract(p * vec3(0.1031, 0.1030, 0.0973));
  p += dot(p, p.yxz + 33.33);
  return fract((p.x + p.y) * p.z);
}
`;

function bindUniforms(shader: THREE.WebGLProgramParametersWithUniforms, uniforms: TownUniforms): void {
  Object.assign(shader.uniforms, uniforms);
}

const WORLD_VARYING_VERTEX = /* glsl */ `
#include <project_vertex>
vTownWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
`;

// --- Facades ---------------------------------------------------------------------------------------------------------

/**
 * Facade types: which atlas rows a wall uses for its ground floor and upper floors, the storey height and the bay
 * width (metres), and which columns of the row it may pick from.
 */
export const FACADE = {
  shopFront: 0,
  shopSide: 1,
  house: 2,
  largeMetal: 3,
  temple: 4,
  government: 5,
  school: 6,
  shed: 7,
  largePlaster: 8,
} as const;

export const FACADE_STOREY: Record<number, number> = { 0: 3.4, 1: 3.4, 2: 3.0, 3: 4.4, 4: 5.6, 5: 3.6, 6: 3.5, 7: 2.6, 8: 4.0 };

const FACADE_GLSL = /* glsl */ `
// x ground row, y upper row, z storey (m), w bay (m)
vec4 facadeSpec(float type) {
  if (type < 0.5) return vec4(0.0, 1.0, 3.4, 4.0);
  if (type < 1.5) return vec4(4.0, 4.0, 3.4, 4.0);
  if (type < 2.5) return vec4(2.0, 3.0, 3.0, 3.2);
  if (type < 3.5) return vec4(5.0, 5.0, 4.4, 5.0);
  if (type < 4.5) return vec4(6.0, 6.0, 5.6, 4.0);
  if (type < 5.5) return vec4(6.0, 6.0, 3.6, 4.0);
  if (type < 6.5) return vec4(7.0, 7.0, 3.5, 4.0);
  if (type < 7.5) return vec4(7.0, 7.0, 2.6, 3.0);
  return vec4(5.0, 5.0, 4.0, 5.0);
}
// x first column, y column count
vec2 facadeCols(float type) {
  if (type > 2.5 && type < 3.5) return vec2(0.0, 4.0);
  if (type > 3.5 && type < 4.5) return vec2(0.0, 4.0);
  if (type > 4.5 && type < 5.5) return vec2(4.0, 4.0);
  if (type > 5.5 && type < 6.5) return vec2(0.0, 4.0);
  if (type > 6.5 && type < 7.5) return vec2(4.0, 4.0);
  if (type > 7.5) return vec2(4.0, 4.0);
  return vec2(0.0, 8.0);
}
`;

export interface FacadeMaterial extends THREE.MeshStandardMaterial {
  userData: { kind: "facade" };
}

/**
 * Walls: vertex colour = the building's plaster tint; attribute aWall = (metres along the wall, facade type, seed,
 * storeys); attribute aBase = height of the ground floor. Depth of water at the wall comes from the flood field.
 */
export function facadeMaterial(atlas: FacadeAtlas, uniforms: TownUniforms): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.86, metalness: 0, envMapIntensity: 0.7 });
  material.onBeforeCompile = (shader) => {
    bindUniforms(shader, uniforms);
    shader.uniforms.uAtlas = { value: atlas.color };
    shader.uniforms.uAtlasMask = { value: atlas.mask };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute vec4 aWall;\nattribute float aBase;\nvarying vec4 vWall;\nvarying float vBase;\nvarying vec3 vTownWorld;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvWall = aWall;\nvBase = aBase;")
      .replace("#include <project_vertex>", WORLD_VARYING_VERTEX);
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>\n${FLOOD_GLSL}\n${FACADE_GLSL}\nuniform sampler2D uAtlas;\nuniform sampler2D uAtlasMask;\nvarying vec4 vWall;\nvarying float vBase;\nvarying vec3 vTownWorld;\nfloat fgGloss = 0.0;\nfloat fgGlow = 0.0;\nfloat fgWater = 0.0;`,
      )
      .replace(
        "#include <color_fragment>",
        /* glsl */ `
        vec4 spec = facadeSpec(vWall.y);
        vec2 cols = facadeCols(vWall.y);
        float h = vTownWorld.y - vBase;
        float storey = spec.z;
        float top = vWall.w * storey;
        float floorIndex = floor(clamp(h, 0.0, top - 0.01) / storey);
        float bayIndex = floor(vWall.x / spec.w);
        float row = floorIndex < 0.5 ? spec.x : spec.y;
        float pick = fgHash(vec3(vWall.z * 17.0, bayIndex, floorIndex));
        float col = cols.x + floor(pick * cols.y);
        // Above the top storey (parapet) and below the floor (plinth skirt): plain plaster of the side row.
        bool plain = h > top || h < 0.0;
        if (plain) { row = 4.0; col = 0.0; }
        vec2 cont = vec2(vWall.x / spec.w, h / storey);
        vec2 local = clamp(fract(cont), 0.004, 0.996);
        vec2 tileUv = (vec2(col, ${ATLAS_TILES.toFixed(1)} - 1.0 - row) + local) / ${ATLAS_TILES.toFixed(1)};
        vec2 gx = dFdx(cont) / ${ATLAS_TILES.toFixed(1)};
        vec2 gy = dFdy(cont) / ${ATLAS_TILES.toFixed(1)};
        vec3 atlas = textureGrad(uAtlas, tileUv, gx, gy).rgb;
        vec3 mask = textureGrad(uAtlasMask, tileUv, gx, gy).rgb;
        vec3 tinted = mix(atlas, atlas * vColor.rgb * 1.1, mask.r);
        diffuseColor.rgb *= tinted;
        fgGloss = mask.b;
        // Night: a share of the windows lit, but not in a building whose ground floor is under water.
        vec4 f = floodAt(vTownWorld.xz);
        float water = f.r * uStage;
        float flooded = step(vBase + 0.15, water);
        float lit = step(0.6 - 0.25 * step(floorIndex, 0.5), fgHash(vec3(vWall.z * 3.1, bayIndex + 11.0, floorIndex + 5.0)));
        fgGlow = mask.g * lit * uNight * (1.0 - flooded) * (plain ? 0.0 : 1.0);
        // Water against the wall, the wet band above it and, once it has gone down, the mud it left.
        float tide = f.r * uMaxStage;
        float wetBand = smoothstep(water + 0.45, water, vTownWorld.y) * step(vBase - 0.6, water);
        float under = step(vTownWorld.y, water);
        float mudZone = step(vTownWorld.y, tide) * step(water + 0.05, tide) * step(vBase - 0.6, tide);
        diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * vec3(0.52, 0.45, 0.34), mudZone);
        diffuseColor.rgb *= 1.0 - 0.32 * max(wetBand, under) - 0.12 * uWetness;
        float line = mudZone * (1.0 - smoothstep(0.0, 0.05, tide - vTownWorld.y));
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.22, 0.18, 0.12), line * 0.85);
        fgWater = max(wetBand, uWetness * 0.6);
        `,
      )
      .replace(
        "#include <roughnessmap_fragment>",
        "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.35, fgGloss);\nroughnessFactor = mix(roughnessFactor, roughnessFactor * 0.5, fgWater);",
      )
      .replace(
        "#include <emissivemap_fragment>",
        "#include <emissivemap_fragment>\ntotalEmissiveRadiance += vec3(1.0, 0.78, 0.48) * fgGlow * 1.6;",
      );
  };
  material.customProgramCacheKey = () => "fg-facade-v1";
  return material;
}

// --- Roofs -----------------------------------------------------------------------------------------------------------

/** Pitched and flat roofs: vertex colour per building, a ridged texture in metre UVs, darker and glossier when wet. */
export function roofMaterial(map: THREE.Texture, uniforms: TownUniforms, roughness = 0.62): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ vertexColors: true, map, roughness, metalness: 0.1 });
  material.onBeforeCompile = (shader) => {
    bindUniforms(shader, uniforms);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\n${FLOOD_GLSL}`)
      .replace("#include <color_fragment>", "#include <color_fragment>\ndiffuseColor.rgb *= 1.0 - 0.18 * uWetness;")
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.22, uWetness);");
  };
  material.customProgramCacheKey = () => `fg-roof-v1-${roughness}`;
  return material;
}

// --- Ground ------------------------------------------------------------------------------------------------------------

/**
 * Ground: colour from the land cover (4 m cells: open ground, water bed, road, building, green, field), a near-camera
 * detail, rain wetness, and the replay's water: wet where it is under water, mud where the water has been.
 */
export function groundMaterial(cover: THREE.Texture, coverXform: THREE.Vector4, detail: THREE.Texture, uniforms: TownUniforms): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.95, metalness: 0 });
  material.onBeforeCompile = (shader) => {
    bindUniforms(shader, uniforms);
    shader.uniforms.uCover = { value: cover };
    shader.uniforms.uCoverXform = { value: coverXform };
    shader.uniforms.uDetail = { value: detail };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vTownWorld;")
      .replace("#include <project_vertex>", WORLD_VARYING_VERTEX);
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>\n${FLOOD_GLSL}\nuniform sampler2D uCover;\nuniform vec4 uCoverXform;\nuniform sampler2D uDetail;\nvarying vec3 vTownWorld;\nfloat fgWet = 0.0;`,
      )
      .replace(
        "#include <color_fragment>",
        /* glsl */ `
        vec2 cuv = (vTownWorld.xz - uCoverXform.xy) * uCoverXform.zw;
        float cls = floor(texture2D(uCover, cuv).r * 255.0 + 0.5);
        float n = texture2D(uDetail, vTownWorld.xz / 2.6).r;
        float n2 = texture2D(uDetail, vTownWorld.xz / 23.0).r;
        vec3 open = mix(vec3(0.56, 0.54, 0.48), vec3(0.63, 0.61, 0.55), n2);      // concrete yards and packed earth
        open = mix(open, vec3(0.44, 0.48, 0.32), 0.35 * smoothstep(0.45, 0.8, n2)); // weeds and lawns
        vec3 bed = vec3(0.43, 0.40, 0.33);                                          // river bed, banks
        vec3 road = vec3(0.46, 0.46, 0.44);
        vec3 pad = vec3(0.62, 0.61, 0.58);
        vec3 green = mix(vec3(0.33, 0.43, 0.22), vec3(0.42, 0.50, 0.27), n2);
        vec3 field = mix(vec3(0.46, 0.55, 0.28), vec3(0.55, 0.53, 0.33), n2);
        vec3 base = cls < 0.5 ? open : cls < 1.5 ? bed : cls < 2.5 ? road : cls < 3.5 ? pad : cls < 4.5 ? green : field;
        base *= 0.86 + 0.28 * n;
        // Hills and fields beyond the cover (outside the detail box) read as green.
        if (cuv.x < 0.0 || cuv.y < 0.0 || cuv.x > 1.0 || cuv.y > 1.0) base = mix(vec3(0.36, 0.44, 0.27), vec3(0.45, 0.50, 0.32), n2);
        vec4 f = floodAt(vTownWorld.xz);
        float water = f.r * uStage;
        float tide = f.r * uMaxStage;
        float under = smoothstep(vTownWorld.y - 0.02, vTownWorld.y + 0.06, water);
        float mud = step(vTownWorld.y, tide - 0.02) * (1.0 - under) * step(0.05, uMaxStage - uStage);
        base = mix(base, vec3(0.33, 0.26, 0.17) * (0.85 + 0.3 * n), mud * 0.92);
        fgWet = max(max(under, mud * 0.7), uWetness);
        base *= 1.0 - 0.3 * fgWet;
        diffuseColor.rgb *= base;
        `,
      )
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.32, fgWet);");
  };
  material.customProgramCacheKey = () => "fg-ground-v1";
  return material;
}

// --- Roads -----------------------------------------------------------------------------------------------------------

/** Roads: asphalt or concrete, puddles and a sheen in the rain (the water itself is drawn by the water mesh). */
export function roadMaterial(map: THREE.Texture, uniforms: TownUniforms, color: string): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({
    color, map, roughness: 0.9, metalness: 0, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4,
  });
  material.onBeforeCompile = (shader) => {
    bindUniforms(shader, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vTownWorld;")
      .replace("#include <project_vertex>", WORLD_VARYING_VERTEX);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\n${FLOOD_GLSL}\nvarying vec3 vTownWorld;\nfloat fgWet = 0.0;`)
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        vec4 f = floodAt(vTownWorld.xz);
        float tide = f.r * uMaxStage;
        float mud = step(vTownWorld.y, tide - 0.02) * step(0.05, uMaxStage - uStage) * step(f.r * uStage, vTownWorld.y);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.36, 0.29, 0.2), mud * 0.85);
        float puddle = smoothstep(0.55, 0.75, fgHash(vec3(floor(vTownWorld.xz * 0.45), 3.0)) * 0.6 + 0.4 * sin(vTownWorld.x * 0.7) * sin(vTownWorld.z * 0.9));
        fgWet = max(uWetness, mud * 0.6);
        diffuseColor.rgb *= 1.0 - 0.28 * fgWet - 0.15 * puddle * uWetness;
        `,
      )
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.25, fgWet);");
  };
  material.customProgramCacheKey = () => `fg-road-v1-${color}`;
  return material;
}

// --- Water -----------------------------------------------------------------------------------------------------------

export interface WaterMaterialOptions {
  normalMap: THREE.Texture;
}

/**
 * Flood water: each vertex carries k_s (aFlood.x), the ground height (aFlood.y), the river flag and its normal level
 * (aRiver), and the low-confidence flag (aFlood.z). The surface rises to k_s × stage; where it is below the ground it
 * is discarded, so the shore is where the replay's water meets the ground. Muddy brown, deeper is darker; rain rings;
 * low-confidence water is hatched, as on the 2D maps.
 */
export function waterMaterial(uniforms: TownUniforms, options: WaterMaterialOptions): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({
    color: "#ffffff", roughness: 0.3, metalness: 0, transparent: true, normalMap: options.normalMap, envMapIntensity: 0.18, depthWrite: true,
  });
  material.normalScale.set(0.35, 0.35);
  material.onBeforeCompile = (shader) => {
    bindUniforms(shader, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        `#include <common>\n${FLOOD_GLSL}\nattribute vec3 aFlood;\nattribute vec2 aRiver;\nvarying float vDepth;\nvarying float vLow;\nvarying vec3 vTownWorld;`,
      )
      .replace("#include <beginnormal_vertex>", "vec3 objectNormal = vec3(0.0, 1.0, 0.0);")
      .replace(
        "#include <begin_vertex>",
        /* glsl */ `#include <begin_vertex>
        float surface = aFlood.x * uStage;
        if (aRiver.x > 0.5) surface = max(surface, aRiver.y);
        transformed.y = surface;
        vDepth = surface - aFlood.y;
        vLow = aFlood.z;`,
      )
      .replace("#include <project_vertex>", WORLD_VARYING_VERTEX);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\n${FLOOD_GLSL}\nvarying float vDepth;\nvarying float vLow;\nvarying vec3 vTownWorld;`)
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        if (vDepth < 0.01) discard;
        float deep = smoothstep(0.0, 2.2, vDepth);
        // Mud-laden flood water: ochre where shallow, dark brown where deep, with slow drifting streaks of silt.
        vec3 shallow = vec3(0.43, 0.32, 0.18);
        vec3 deepColor = vec3(0.24, 0.17, 0.10);
        vec3 col = mix(shallow, deepColor, deep);
        // Soft drifting blotches of silt (no regular pattern: stripes mean low confidence on these maps).
        vec2 drift = vTownWorld.xz / 23.0 + vec2(uTime * 0.01, -uTime * 0.006);
        vec2 cellId = floor(drift), f = fract(drift);
        vec2 u = f * f * (3.0 - 2.0 * f);
        float blotch = mix(mix(fgHash(vec3(cellId, 7.0)), fgHash(vec3(cellId + vec2(1.0, 0.0), 7.0)), u.x),
                           mix(fgHash(vec3(cellId + vec2(0.0, 1.0), 7.0)), fgHash(vec3(cellId + vec2(1.0, 1.0), 7.0)), u.x), u.y);
        col *= 0.9 + 0.22 * blotch;
        // Foam and a lighter rim where the water meets the ground.
        float rim = 1.0 - smoothstep(0.0, 0.12, vDepth);
        col = mix(col, vec3(0.72, 0.66, 0.55), rim * 0.55);
        // Low-confidence water, hatched in diagonal stripes as on the 2D maps.
        float stripe = step(0.8, fract((vTownWorld.x + vTownWorld.z) / 6.0));
        col = mix(col, col * 1.25 + 0.05, step(0.5, vLow) * stripe * 0.45);
        diffuseColor.rgb = col;
        diffuseColor.a = mix(0.78, 0.98, smoothstep(0.0, 0.5, vDepth)) * smoothstep(0.01, 0.05, vDepth);
        `,
      )
      .replace(
        "#include <opaque_fragment>",
        /* glsl */ `
        // A capped, stylised reflection of the sky: physically the pale overcast sky would wash brown water out to
        // the colour of the dry ground at a glancing angle, and the flood would stop reading as water.
        vec3 toEye = normalize(cameraPosition - vTownWorld);
        float facing = clamp(dot(toEye, vec3(0.0, 1.0, 0.0)), 0.0, 1.0);
        float fres = pow(1.0 - facing, 4.0);
        vec3 skyTint = mix(vec3(0.58, 0.60, 0.60), vec3(0.06, 0.07, 0.10), uNight);
        outgoingLight = mix(outgoingLight, skyTint, min(0.32, fres * 0.6));
        // At night: dark slate water that still reads as water, the town's orange glow caught at a glancing angle.
        vec3 nightWater = vec3(0.075, 0.085, 0.11) + vec3(0.22, 0.15, 0.08) * fres + outgoingLight * 0.35;
        outgoingLight = mix(outgoingLight, nightWater, uNight);
        #include <opaque_fragment>`,
      )
      .replace(
        "#include <normal_fragment_maps>",
        /* glsl */ `#include <normal_fragment_maps>
        // Rain rings on the surface.
        vec2 cell = floor(vTownWorld.xz / 0.7);
        float seed = fgHash(vec3(cell, 9.0));
        float phase = fract(uTime * 0.9 + seed);
        vec2 centre = (cell + 0.5 + (vec2(fgHash(vec3(cell, 1.0)), fgHash(vec3(cell, 2.0))) - 0.5) * 0.6) * 0.7;
        float d = length(vTownWorld.xz - centre);
        float ring = exp(-pow((d - phase * 0.45) * 26.0, 2.0)) * (1.0 - phase);
        vec2 dir = normalize(vTownWorld.xz - centre + 1e-4);
        vec3 tilt = (viewMatrix * vec4(dir.x, 0.0, dir.y, 0.0)).xyz;
        normal = normalize(normal + tilt * ring * uRain * 0.9);
        `,
      );
  };
  material.customProgramCacheKey = () => "fg-water-v1";
  return material;
}
