// Builds web versions of the journey's rigged characters from the delivered source models.
//
//   node scripts/build-journey-characters.mjs [name ...]
//
// Sources (not in git; paths from the repository root):
//   deliver/{phone_woman,office_man}/*_rigged.glb    Lalita and Narin (about 300k triangles and 8K textures, 40–47 MB)
//   assets/new-models/{mali,dao,pim}_rigged.glb      Mali, Dao and Pim (Meshy, 15 Oct 2026; 100–300k triangles, 20–25 MB)
// Output: public/journey/characters/<name>.glb. The skinned body mesh is simplified with meshoptimizer (UV seams,
// normals and skin weights kept; the phone hand is locked at full detail because the camera pushes in on it),
// textures are resized to JPEG, and the rig and any attached phone are copied unchanged. Skins with eight influences
// per vertex keep their four strongest (three.js reads four). Clips are kept or dropped per character. With `compact`,
// skin weights, bone indices and texture coordinates are stored in the smaller types core glTF allows.
// meshoptimizer and sharp are already in the workspace (via @types/three and next); nothing is downloaded.
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const only = new Set(process.argv.slice(2));
const outDir = path.join(appRoot, "public", "journey", "characters");

const require = createRequire(path.join(appRoot, "package.json"));
const sharp = createRequire(require.resolve("next/package.json"))("sharp");
const store = path.join(repoRoot, "node_modules", ".pnpm");
const meshoptDir = existsSync(store) ? readdirSync(store).find((name) => name.startsWith("meshoptimizer@")) : undefined;
if (!meshoptDir) throw new Error("meshoptimizer not found in node_modules/.pnpm (it is installed with @types/three).");
const { MeshoptSimplifier } = await import(pathToFileURL(path.join(store, meshoptDir, "node_modules", "meshoptimizer", "index.module.js")).href);
await MeshoptSimplifier.ready;
MeshoptSimplifier.useExperimentalFeatures = true;

const LARGE = { base: 2048, normal: 2048, roughness: 1024 };
const FAMILY = { base: 2048, normal: 1024, roughness: 512 };
const CHARACTERS = [
  { name: "phone-woman", source: "deliver/phone_woman/phone_woman_rigged.glb", triangles: 42000, lockBones: /^RightHand/, textures: LARGE, clips: true },
  { name: "office-man", source: "deliver/office_man/office_man_rigged.glb", triangles: 38000, lockBones: null, textures: LARGE, clips: true },
  // Seen at the gate and at the planning table, never as close as Lalita's phone: lighter, and without the test clips
  // (Walking, Running) the story does not use; their pose is built from the rest (A) pose.
  { name: "mali", source: "assets/new-models/mali_rigged.glb", triangles: 30000, lockBones: null, textures: FAMILY, clips: false, compact: true },
  { name: "dao", source: "assets/new-models/dao_rigged.glb", triangles: 50000, lockBones: null, textures: FAMILY, clips: false, compact: true, keepSeams: true },
  { name: "pim", source: "assets/new-models/pim_rigged.glb", triangles: 28000, lockBones: null, textures: FAMILY, clips: false, compact: true },
];

// --- GLB reading and writing -----------------------------------------------------------------------------------------

function readGlb(file) {
  const data = readFileSync(file);
  if (data.readUInt32LE(0) !== 0x46546c67) throw new Error(`${file} is not a GLB`);
  let offset = 12, json = null, bin = null;
  while (offset < data.length) {
    const length = data.readUInt32LE(offset), type = data.readUInt32LE(offset + 4);
    const chunk = data.subarray(offset + 8, offset + 8 + length);
    if (type === 0x4e4f534a) json = JSON.parse(chunk.toString("utf8"));
    if (type === 0x004e4942) bin = chunk;
    offset += 8 + length;
  }
  return { json, bin };
}

const COMPONENTS = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array };
const SIZES = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };

function readAccessor(gltf, index) {
  const accessor = gltf.json.accessors[index];
  const view = gltf.json.bufferViews[accessor.bufferView];
  const Type = COMPONENTS[accessor.componentType];
  const size = SIZES[accessor.type];
  if (view.byteStride && view.byteStride !== size * Type.BYTES_PER_ELEMENT) throw new Error("Interleaved attributes are not supported");
  const start = gltf.bin.byteOffset + (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
  const copy = new Uint8Array(gltf.bin.buffer.slice(start, start + accessor.count * size * Type.BYTES_PER_ELEMENT));
  return { array: new Type(copy.buffer), size, accessor };
}

function writeGlb(json, chunks) {
  // chunks: one Uint8Array per bufferView, in order.
  const pieces = [];
  let length = 0;
  json.bufferViews = json.bufferViews.map((view, i) => {
    const bytes = chunks[i];
    const padded = Math.ceil(bytes.byteLength / 4) * 4;
    const next = { ...view, byteOffset: length, byteLength: bytes.byteLength };
    delete next.byteStride;
    pieces.push(bytes);
    if (padded > bytes.byteLength) pieces.push(new Uint8Array(padded - bytes.byteLength));
    length += padded;
    return next;
  });
  json.buffers = [{ byteLength: length }];
  const bin = Buffer.concat(pieces.map((p) => Buffer.from(p.buffer, p.byteOffset, p.byteLength)));
  let text = Buffer.from(JSON.stringify(json), "utf8");
  const pad = (4 - (text.length % 4)) % 4;
  text = Buffer.concat([text, Buffer.from(" ".repeat(pad))]);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + text.length + 8 + bin.length, 8);
  const jsonHeader = Buffer.alloc(8);
  jsonHeader.writeUInt32LE(text.length, 0);
  jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(bin.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, jsonHeader, text, binHeader, bin]);
}

/**
 * Fold an eight-influence skin (JOINTS_0/1, WEIGHTS_0/1) into the four strongest influences of each vertex, weights
 * renormalised to sum to one. Writes JOINTS_0 (unsigned short) and WEIGHTS_0 (float) and drops the second set.
 */
function keepStrongestFour(json, primitive, attributes) {
  const scale = (accessor) => (accessor.componentType === 5126 ? 1 : accessor.componentType === 5121 ? 1 / 255 : 1 / 65535);
  const sets = [0, 1].map((k) => ({ joints: attributes[`JOINTS_${k}`], weights: attributes[`WEIGHTS_${k}`] }));
  const count = attributes.POSITION.accessor.count;
  const joints = new Uint16Array(count * 4), weights = new Float32Array(count * 4);
  const pairs = [];
  for (let v = 0; v < count; v += 1) {
    pairs.length = 0;
    for (const set of sets) {
      const s = scale(set.weights.accessor);
      for (let k = 0; k < 4; k += 1) pairs.push([set.joints.array[v * 4 + k], set.weights.array[v * 4 + k] * s]);
    }
    pairs.sort((a, b) => b[1] - a[1]);
    const total = pairs[0][1] + pairs[1][1] + pairs[2][1] + pairs[3][1] || 1;
    for (let k = 0; k < 4; k += 1) {
      joints[v * 4 + k] = pairs[k][1] > 0 ? pairs[k][0] : 0;
      weights[v * 4 + k] = pairs[k][1] / total;
    }
  }
  for (const [name, componentType] of [["JOINTS_0", 5123], ["WEIGHTS_0", 5126]]) {
    const accessor = json.accessors[primitive.attributes[name]];
    accessor.componentType = componentType;
    delete accessor.normalized;
  }
  attributes.JOINTS_0 = { ...attributes.JOINTS_0, array: joints };
  attributes.WEIGHTS_0 = { ...attributes.WEIGHTS_0, array: weights };
  for (const name of ["JOINTS_1", "WEIGHTS_1"]) {
    delete primitive.attributes[name];
    delete attributes[name];
  }
}

/**
 * Drop the accessors and buffer views nothing refers to any more (dropped clips, a folded skin's second set) and
 * renumber the rest, so the file carries only what is drawn.
 */
function prune(json, chunks) {
  const usedAccessors = new Set();
  for (const mesh of json.meshes) for (const primitive of mesh.primitives) {
    Object.values(primitive.attributes).forEach((index) => usedAccessors.add(index));
    if (primitive.indices !== undefined) usedAccessors.add(primitive.indices);
    for (const target of primitive.targets ?? []) Object.values(target).forEach((index) => usedAccessors.add(index));
  }
  for (const skin of json.skins ?? []) if (skin.inverseBindMatrices !== undefined) usedAccessors.add(skin.inverseBindMatrices);
  for (const clip of json.animations ?? []) for (const sampler of clip.samplers) {
    usedAccessors.add(sampler.input);
    usedAccessors.add(sampler.output);
  }
  const accessorMap = new Map([...usedAccessors].sort((a, b) => a - b).map((old, next) => [old, next]));
  const usedViews = new Set([...accessorMap.keys()].map((index) => json.accessors[index].bufferView));
  for (const image of json.images ?? []) if (image.bufferView !== undefined) usedViews.add(image.bufferView);
  const viewMap = new Map([...usedViews].sort((a, b) => a - b).map((old, next) => [old, next]));

  json.accessors = [...accessorMap.keys()].map((old) => ({ ...json.accessors[old], bufferView: viewMap.get(json.accessors[old].bufferView) }));
  const kept = [...viewMap.keys()].map((old) => chunks[old]);
  json.bufferViews = [...viewMap.keys()].map((old) => json.bufferViews[old]);
  chunks.length = 0;
  chunks.push(...kept);
  for (const mesh of json.meshes) for (const primitive of mesh.primitives) {
    for (const name of Object.keys(primitive.attributes)) primitive.attributes[name] = accessorMap.get(primitive.attributes[name]);
    if (primitive.indices !== undefined) primitive.indices = accessorMap.get(primitive.indices);
    for (const target of primitive.targets ?? []) for (const name of Object.keys(target)) target[name] = accessorMap.get(target[name]);
  }
  for (const skin of json.skins ?? []) if (skin.inverseBindMatrices !== undefined) skin.inverseBindMatrices = accessorMap.get(skin.inverseBindMatrices);
  for (const clip of json.animations ?? []) for (const sampler of clip.samplers) {
    sampler.input = accessorMap.get(sampler.input);
    sampler.output = accessorMap.get(sampler.output);
  }
  for (const image of json.images ?? []) if (image.bufferView !== undefined) image.bufferView = viewMap.get(image.bufferView);
}

/**
 * Smaller storage for a vertex attribute, in types core glTF 2.0 allows without an extension: skin weights as
 * normalised bytes (each vertex's four still sum to exactly 255), bone indices as bytes when there are fewer than 256
 * bones, and texture coordinates as normalised shorts when they lie within [0, 1]. Other attributes are returned as they are.
 */
function pack(attribute, values, size, accessor) {
  const count = values.length / size;
  if (attribute.startsWith("WEIGHTS_")) {
    const scale = accessor.componentType === 5126 ? 1 : accessor.componentType === 5121 ? 1 / 255 : 1 / 65535;
    const bytes = new Uint8Array(values.length);
    for (let v = 0; v < count; v += 1) {
      let sum = 0, lead = 0, total = 0;
      for (let k = 0; k < 4; k += 1) total += values[v * 4 + k] * scale;
      for (let k = 0; k < 4; k += 1) {
        bytes[v * 4 + k] = Math.round(((values[v * 4 + k] * scale) / (total || 1)) * 255);
        sum += bytes[v * 4 + k];
        if (bytes[v * 4 + k] > bytes[v * 4 + lead]) lead = k;
      }
      bytes[v * 4 + lead] += 255 - sum;
    }
    Object.assign(accessor, { componentType: 5121, normalized: true });
    return bytes;
  }
  if (attribute.startsWith("JOINTS_")) {
    let most = 0;
    for (const value of values) most = Math.max(most, value);
    if (most > 255) return values;
    accessor.componentType = 5121;
    return Uint8Array.from(values);
  }
  if (attribute.startsWith("TEXCOORD_") && accessor.componentType === 5126) {
    for (const value of values) if (value < 0 || value > 1) return values;
    Object.assign(accessor, { componentType: 5123, normalized: true });
    return Uint16Array.from(values, (value) => Math.round(value * 65535));
  }
  return values;
}

// --- Build -----------------------------------------------------------------------------------------------------------

async function buildCharacter({ name, source, triangles, lockBones, textures, clips, compact = false, keepSeams = false }) {
  const file = path.join(repoRoot, source);
  const out = `${name}.glb`;
  const gltf = readGlb(file);
  const { json } = gltf;
  const chunks = json.bufferViews.map((view) => {
    const start = gltf.bin.byteOffset + (view.byteOffset ?? 0);
    return new Uint8Array(gltf.bin.buffer.slice(start, start + view.byteLength));
  });
  // The body is the skinned mesh (named "Body" in the first two files, "Mesh_0" or "output_unwrapped" in the others).
  const meshIndex = json.nodes.find((node) => node.mesh !== undefined && node.skin !== undefined).mesh;
  json.meshes[meshIndex].name = "Body";
  const primitive = json.meshes[meshIndex].primitives[0];
  const attributes = Object.fromEntries(Object.entries(primitive.attributes).map(([attribute, index]) => [attribute, readAccessor(gltf, index)]));
  if (attributes.JOINTS_1) keepStrongestFour(json, primitive, attributes);
  const indices = readAccessor(gltf, primitive.indices);
  const index32 = Uint32Array.from(indices.array);
  const positions = attributes.POSITION.array;
  const vertexCount = attributes.POSITION.accessor.count;

  // Shading attributes guide the simplifier (normals and UVs), so seams and creases survive.
  const normals = attributes.NORMAL.array, uvs = attributes.TEXCOORD_0.array;
  const guide = new Float32Array(vertexCount * 5);
  for (let v = 0; v < vertexCount; v += 1) {
    guide.set([normals[v * 3], normals[v * 3 + 1], normals[v * 3 + 2], uvs[v * 2], uvs[v * 2 + 1]], v * 5);
  }
  // Lock the vertices driven mainly by the given bones (the phone hand keeps its full detail).
  let lock = null, locked = 0;
  if (lockBones) {
    const skin = json.skins[json.nodes.findIndex((node) => node.mesh === meshIndex) >= 0 ? json.nodes.find((node) => node.mesh === meshIndex).skin : 0];
    const jointNames = skin.joints.map((node) => json.nodes[node].name);
    const joints = attributes.JOINTS_0.array, weights = attributes.WEIGHTS_0.array;
    const weightScale = attributes.WEIGHTS_0.accessor.componentType === 5126 ? 1 : attributes.WEIGHTS_0.accessor.componentType === 5121 ? 1 / 255 : 1 / 65535;
    lock = new Uint8Array(vertexCount);
    for (let v = 0; v < vertexCount; v += 1) {
      let handWeight = 0;
      for (let k = 0; k < 4; k += 1) if (lockBones.test(jointNames[joints[v * 4 + k]])) handWeight += weights[v * 4 + k] * weightScale;
      if (handWeight > 0.35) {
        lock[v] = 1;
        locked += 1;
      }
    }
  }
  const [simplified, error] = MeshoptSimplifier.simplifyWithAttributes(index32, positions, 3, guide, 5, [0.6, 0.6, 0.6, keepSeams ? 6 : 1.4, keepSeams ? 6 : 1.4], lock, triangles * 3, 0.02, keepSeams ? ["LockBorder"] : []);
  const [remap, unique] = MeshoptSimplifier.compactMesh(simplified);
  // compactMesh rewrote `simplified` in place to the new vertex numbering; remap maps old vertex → new vertex.
  const IndexType = unique > 65535 ? Uint32Array : Uint16Array;
  chunks[json.accessors[primitive.indices].bufferView] = new Uint8Array(IndexType.from(simplified).buffer);
  Object.assign(json.accessors[primitive.indices], { count: simplified.length, componentType: IndexType === Uint32Array ? 5125 : 5123 });
  for (const [attribute, { array, size, accessor }] of Object.entries(attributes)) {
    const Type = array.constructor;
    const next = new Type(unique * size);
    for (let v = 0; v < vertexCount; v += 1) {
      const to = remap[v];
      if (to === 0xffffffff || to >= unique) continue;
      for (let k = 0; k < size; k += 1) next[to * size + k] = array[v * size + k];
    }
    const packed = compact ? pack(attribute, next, size, json.accessors[primitive.attributes[attribute]]) : next;
    chunks[json.accessors[primitive.attributes[attribute]].bufferView] = new Uint8Array(packed.buffer, packed.byteOffset, packed.byteLength);
    json.accessors[primitive.attributes[attribute]].count = unique;
    if (attribute === "POSITION") {
      const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      for (let v = 0; v < unique; v += 1) for (let k = 0; k < 3; k += 1) { min[k] = Math.min(min[k], next[v * 3 + k]); max[k] = Math.max(max[k], next[v * 3 + k]); }
      Object.assign(accessor, { min, max });
      Object.assign(json.accessors[primitive.attributes[attribute]], { min, max });
    }
  }

  // Textures, as JPEG: base colour, normal (high quality) and metallic-roughness, at the character's sizes.
  const material = json.materials[primitive.material ?? 0];
  const roles = new Map();
  const imageOf = (textureInfo) => (textureInfo ? json.textures[textureInfo.index].source : undefined);
  roles.set(imageOf(material.pbrMetallicRoughness?.baseColorTexture), { size: textures.base, quality: 86 });
  roles.set(imageOf(material.normalTexture), { size: textures.normal, quality: 92 });
  roles.set(imageOf(material.pbrMetallicRoughness?.metallicRoughnessTexture), { size: textures.roughness, quality: 88 });
  for (const [imageIndex, spec] of roles) {
    if (imageIndex === undefined) continue;
    const image = json.images[imageIndex];
    const bytes = chunks[image.bufferView];
    const resized = await sharp(Buffer.from(bytes)).resize(spec.size, spec.size, { fit: "inside" }).jpeg({ quality: spec.quality, mozjpeg: true }).toBuffer();
    chunks[image.bufferView] = new Uint8Array(resized);
    image.mimeType = "image/jpeg";
  }
  json.asset = { ...json.asset, generator: `${json.asset.generator}; FloodGuard build-journey-characters (meshoptimizer ${meshoptDir.split("@")[1]})` };
  if (!clips) delete json.animations;
  prune(json, chunks);
  mkdirSync(outDir, { recursive: true });
  const glb = writeGlb(json, chunks);
  writeFileSync(path.join(outDir, out), glb);
  console.log(`${out}: ${(index32.length / 3) | 0} → ${(simplified.length / 3) | 0} triangles (${locked} locked vertices, error ${error.toFixed(4)}), ${vertexCount} → ${unique} vertices, ${(readFileSync(file).length / 1e6).toFixed(1)} MB → ${(glb.length / 1e6).toFixed(2)} MB`);
}

for (const character of CHARACTERS) if (only.size === 0 || only.has(character.name)) await buildCharacter(character);
