// Builds web versions of the journey's rigged characters from the delivered source models.
//
//   node scripts/build-journey-characters.mjs [deliverDir]
//
// Source: <repo>/deliver/<name>/<name>_rigged.glb (100k–300k triangles, 2K–8K textures, 20–47 MB). A character whose
// source is not in deliverDir is skipped, so one person can be rebuilt without the others' sources.
// Output: public/journey/characters/<out>.glb. The body mesh is simplified with meshoptimizer (UV seams, normals and
// skin weights kept; the phone hand is locked at full detail because the camera pushes in on it), textures are resized
// to 2K/1K JPEG, and the rig, the clips and the attached phone are copied unchanged.
// Mali, Dao and Pim come from Meshy's auto-rig ("meshy" below): their spine and neck bones are renamed to the names the
// other two use (Spine, Spine1, Spine2, Neck, from the hips up), and Meshy's sample Walking/Running clips are dropped;
// their story poses are fitted in the scene (`characters.ts`), from the bind (A) pose.
// meshoptimizer and sharp are already in the workspace (via @types/three and next); nothing is downloaded.
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const deliver = path.resolve(process.argv[2] ?? path.join(repoRoot, "deliver"));
const outDir = path.join(appRoot, "public", "journey", "characters");

const require = createRequire(path.join(appRoot, "package.json"));
const sharp = createRequire(require.resolve("next/package.json"))("sharp");
const store = path.join(repoRoot, "node_modules", ".pnpm");
const meshoptDir = existsSync(store) ? readdirSync(store).find((name) => name.startsWith("meshoptimizer@")) : undefined;
if (!meshoptDir) throw new Error("meshoptimizer not found in node_modules/.pnpm (it is installed with @types/three).");
const { MeshoptSimplifier } = await import(pathToFileURL(path.join(store, meshoptDir, "node_modules", "meshoptimizer", "index.module.js")).href);
await MeshoptSimplifier.ready;
MeshoptSimplifier.useExperimentalFeatures = true;

const CHARACTERS = [
  { source: "phone_woman/phone_woman_rigged.glb", out: "phone-woman.glb", triangles: 42000, lockBones: /^RightHand/ },
  { source: "office_man/office_man_rigged.glb", out: "office-man.glb", triangles: 38000, lockBones: null },
  { source: "mali/mali_rigged.glb", out: "mali.glb", triangles: 30000, lockBones: null, rig: "meshy" },
  { source: "dao/dao_rigged.glb", out: "dao.glb", triangles: 22000, lockBones: null, lockSeams: true, rig: "meshy" },
  { source: "pim/pim_rigged.glb", out: "pim.glb", triangles: 30000, lockBones: null, lockSeams: true, rig: "meshy" },
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

// --- Meshy rigs ------------------------------------------------------------------------------------------------------

/** Rename Meshy's spine and neck (Spine02 → Spine01 → Spine → neck, from the hips up) to Spine, Spine1, Spine2, Neck. */
function renameMeshyRig(json) {
  const childNamed = (index, pattern) => (json.nodes[index].children ?? []).find((child) => pattern.test(json.nodes[child].name));
  let node = json.nodes.findIndex((n) => n.name === "Hips");
  if (node < 0) throw new Error("The Meshy rig has no Hips bone");
  for (const name of ["Spine", "Spine1", "Spine2"]) {
    node = childNamed(node, /^Spine\d*$/);
    if (node === undefined) throw new Error(`The Meshy rig has no bone for ${name}`);
    json.nodes[node].name = name;
  }
  const neck = childNamed(node, /^neck$/i);
  if (neck === undefined) throw new Error("The Meshy rig has no neck bone");
  json.nodes[neck].name = "Neck";
}

/**
 * three.js skins with four influences per vertex (JOINTS_0/WEIGHTS_0) and ignores a second set, so a vertex weighted
 * to eight bones would lose part of its weight and pull toward the origin. Keep each vertex's four strongest bones,
 * scaled to sum to one, and drop JOINTS_1/WEIGHTS_1.
 */
function keepFourInfluences(json, primitive, chunks, remapped, count) {
  const sets = [0, 1].map((k) => ({ joints: remapped[`JOINTS_${k}`], weights: remapped[`WEIGHTS_${k}`] }));
  if (sets.some((set) => !(set.weights instanceof Float32Array))) throw new Error("Only float skin weights can be merged");
  const joints = new sets[0].joints.constructor(count * 4), weights = new Float32Array(count * 4);
  for (let v = 0; v < count; v += 1) {
    const all = sets.flatMap(({ joints: j, weights: w }) => [0, 1, 2, 3].map((k) => [j[v * 4 + k], w[v * 4 + k]]));
    all.sort((a, b) => b[1] - a[1]);
    const total = all[0][1] + all[1][1] + all[2][1] + all[3][1] || 1;
    for (let k = 0; k < 4; k += 1) {
      joints[v * 4 + k] = all[k][0];
      weights[v * 4 + k] = all[k][1] / total;
    }
  }
  chunks[json.accessors[primitive.attributes.JOINTS_0].bufferView] = new Uint8Array(joints.buffer);
  chunks[json.accessors[primitive.attributes.WEIGHTS_0].bufferView] = new Uint8Array(weights.buffer);
  delete primitive.attributes.JOINTS_1;
  delete primitive.attributes.WEIGHTS_1;
}

/** Drop the animation clips; `pruneUnused` then removes the data only they used. */
function dropClips(json) {
  delete json.animations;
}

/** Remove the accessors and buffer views nothing refers to any more. */
function pruneUnused(json, chunks) {
  const usedAccessors = new Set();
  for (const animation of json.animations ?? []) for (const sampler of animation.samplers) usedAccessors.add(sampler.input).add(sampler.output);
  for (const mesh of json.meshes) {
    for (const primitive of mesh.primitives) {
      Object.values(primitive.attributes).forEach((index) => usedAccessors.add(index));
      if (primitive.indices !== undefined) usedAccessors.add(primitive.indices);
      for (const target of primitive.targets ?? []) Object.values(target).forEach((index) => usedAccessors.add(index));
    }
  }
  for (const skin of json.skins ?? []) if (skin.inverseBindMatrices !== undefined) usedAccessors.add(skin.inverseBindMatrices);
  const accessorOrder = [...usedAccessors].sort((a, b) => a - b);
  const usedViews = new Set([...accessorOrder.map((index) => json.accessors[index].bufferView), ...(json.images ?? []).map((image) => image.bufferView)]);
  const viewOrder = [...usedViews].filter((index) => index !== undefined).sort((a, b) => a - b);
  const accessorMap = new Map(accessorOrder.map((old, index) => [old, index]));
  const viewMap = new Map(viewOrder.map((old, index) => [old, index]));
  json.accessors = accessorOrder.map((old) => ({ ...json.accessors[old], bufferView: viewMap.get(json.accessors[old].bufferView) }));
  const keptChunks = viewOrder.map((old) => chunks[old]);
  json.bufferViews = viewOrder.map((old) => json.bufferViews[old]);
  chunks.splice(0, chunks.length, ...keptChunks);
  for (const mesh of json.meshes) {
    for (const primitive of mesh.primitives) {
      for (const name of Object.keys(primitive.attributes)) primitive.attributes[name] = accessorMap.get(primitive.attributes[name]);
      if (primitive.indices !== undefined) primitive.indices = accessorMap.get(primitive.indices);
      for (const target of primitive.targets ?? []) for (const name of Object.keys(target)) target[name] = accessorMap.get(target[name]);
    }
  }
  for (const skin of json.skins ?? []) if (skin.inverseBindMatrices !== undefined) skin.inverseBindMatrices = accessorMap.get(skin.inverseBindMatrices);
  for (const animation of json.animations ?? []) {
    for (const sampler of animation.samplers) Object.assign(sampler, { input: accessorMap.get(sampler.input), output: accessorMap.get(sampler.output) });
  }
  for (const image of json.images ?? []) if (image.bufferView !== undefined) image.bufferView = viewMap.get(image.bufferView);
}

// --- Build -----------------------------------------------------------------------------------------------------------

async function buildCharacter({ source, out, triangles, lockBones, lockSeams = false, rig }) {
  const file = path.join(deliver, source);
  if (!existsSync(file)) {
    console.log(`${out}: skipped (no ${source} in ${deliver})`);
    return;
  }
  const gltf = readGlb(file);
  const { json } = gltf;
  const chunks = json.bufferViews.map((view) => {
    const start = gltf.bin.byteOffset + (view.byteOffset ?? 0);
    return new Uint8Array(gltf.bin.buffer.slice(start, start + view.byteLength));
  });
  // The body is the mesh named Body, or (Meshy) the one skinned mesh.
  let meshIndex = json.meshes.findIndex((mesh) => mesh.name === "Body");
  if (meshIndex < 0) meshIndex = json.nodes.find((node) => node.skin !== undefined && node.mesh !== undefined)?.mesh ?? -1;
  if (meshIndex < 0) throw new Error(`${source} has no body mesh`);
  const primitive = json.meshes[meshIndex].primitives[0];
  const attributes = Object.fromEntries(Object.entries(primitive.attributes).map(([name, index]) => [name, readAccessor(gltf, index)]));
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
  // Lock every vertex on a UV seam (a position shared by more than one vertex). Meshy's remeshed models are unwrapped
  // into many small islands; collapsing their edges drags texels from one island into another, which shows as patches
  // of the wrong colour (white streaks on Dao's skirt, navy on her blouse). Inside an island the mesh still simplifies.
  if (lockSeams) {
    lock ??= new Uint8Array(vertexCount);
    const first = new Map();
    for (let v = 0; v < vertexCount; v += 1) {
      const key = `${positions[v * 3]},${positions[v * 3 + 1]},${positions[v * 3 + 2]}`;
      const other = first.get(key);
      if (other === undefined) first.set(key, v);
      else {
        if (!lock[other]) { lock[other] = 1; locked += 1; }
        if (!lock[v]) { lock[v] = 1; locked += 1; }
      }
    }
  }
  const [simplified, error] = MeshoptSimplifier.simplifyWithAttributes(index32, positions, 3, guide, 5, [0.6, 0.6, 0.6, 1.4, 1.4], lock, triangles * 3, 0.02, []);
  const [remap, unique] = MeshoptSimplifier.compactMesh(simplified);
  // compactMesh rewrote `simplified` in place to the new vertex numbering; remap maps old vertex → new vertex.
  const IndexType = unique > 65535 ? Uint32Array : Uint16Array;
  chunks[json.accessors[primitive.indices].bufferView] = new Uint8Array(IndexType.from(simplified).buffer);
  Object.assign(json.accessors[primitive.indices], { count: simplified.length, componentType: IndexType === Uint32Array ? 5125 : 5123 });
  const remapped = {};
  for (const [name, { array, size, accessor }] of Object.entries(attributes)) {
    const Type = array.constructor;
    const next = new Type(unique * size);
    remapped[name] = next;
    for (let v = 0; v < vertexCount; v += 1) {
      const to = remap[v];
      if (to === 0xffffffff || to >= unique) continue;
      for (let k = 0; k < size; k += 1) next[to * size + k] = array[v * size + k];
    }
    chunks[json.accessors[primitive.attributes[name]].bufferView] = new Uint8Array(next.buffer);
    json.accessors[primitive.attributes[name]].count = unique;
    if (name === "POSITION") {
      const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      for (let v = 0; v < unique; v += 1) for (let k = 0; k < 3; k += 1) { min[k] = Math.min(min[k], next[v * 3 + k]); max[k] = Math.max(max[k], next[v * 3 + k]); }
      Object.assign(accessor, { min, max });
      Object.assign(json.accessors[primitive.attributes[name]], { min, max });
    }
  }
  if (primitive.attributes.JOINTS_1 !== undefined) keepFourInfluences(json, primitive, chunks, remapped, unique);

  // Textures: base colour 2048 (JPEG), normal 2048 (JPEG, high quality), metallic-roughness 1024.
  const material = json.materials[primitive.material ?? 0];
  const roles = new Map();
  const imageOf = (textureInfo) => (textureInfo ? json.textures[textureInfo.index].source : undefined);
  roles.set(imageOf(material.pbrMetallicRoughness?.baseColorTexture), { size: 2048, quality: 86 });
  roles.set(imageOf(material.normalTexture), { size: 2048, quality: 92 });
  roles.set(imageOf(material.pbrMetallicRoughness?.metallicRoughnessTexture), { size: 1024, quality: 88 });
  for (const [imageIndex, spec] of roles) {
    if (imageIndex === undefined) continue;
    const image = json.images[imageIndex];
    const bytes = chunks[image.bufferView];
    const resized = await sharp(Buffer.from(bytes)).resize(spec.size, spec.size, { fit: "inside" }).jpeg({ quality: spec.quality, mozjpeg: true }).toBuffer();
    chunks[image.bufferView] = new Uint8Array(resized);
    image.mimeType = "image/jpeg";
  }
  if (rig === "meshy") {
    renameMeshyRig(json);
    dropClips(json);
  }
  pruneUnused(json, chunks);
  json.asset = { ...json.asset, generator: `${json.asset.generator}; FloodGuard build-journey-characters (meshoptimizer ${meshoptDir.split("@")[1]})` };
  mkdirSync(outDir, { recursive: true });
  const glb = writeGlb(json, chunks);
  writeFileSync(path.join(outDir, out), glb);
  console.log(`${out}: ${(index32.length / 3) | 0} → ${(simplified.length / 3) | 0} triangles (${locked} locked vertices, error ${error.toFixed(4)}), ${vertexCount} → ${unique} vertices, ${(readFileSync(file).length / 1e6).toFixed(1)} MB → ${(glb.length / 1e6).toFixed(2)} MB`);
}

for (const character of CHARACTERS) await buildCharacter(character);
