// Builds web versions of the journey's two rigged characters from the delivered source models.
//
//   node scripts/build-journey-characters.mjs [deliverDir]
//
// Source: <repo>/deliver/{phone_woman,office_man}/*_rigged.glb (about 300k triangles and 8K textures each, 40–47 MB).
// Output: public/journey/characters/{phone-woman,office-man}.glb. The body mesh is simplified with meshoptimizer
// (UV seams, normals and skin weights kept; the phone hand is locked at full detail because the camera pushes in on
// it), textures are resized to 2K/1K JPEG, and the rig, the clips and the attached phone are copied unchanged.
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

// --- Build -----------------------------------------------------------------------------------------------------------

async function buildCharacter({ source, out, triangles, lockBones }) {
  const file = path.join(deliver, source);
  const gltf = readGlb(file);
  const { json } = gltf;
  const chunks = json.bufferViews.map((view) => {
    const start = gltf.bin.byteOffset + (view.byteOffset ?? 0);
    return new Uint8Array(gltf.bin.buffer.slice(start, start + view.byteLength));
  });
  const meshIndex = json.meshes.findIndex((mesh) => mesh.name === "Body");
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
  const [simplified, error] = MeshoptSimplifier.simplifyWithAttributes(index32, positions, 3, guide, 5, [0.6, 0.6, 0.6, 1.4, 1.4], lock, triangles * 3, 0.02, []);
  const [remap, unique] = MeshoptSimplifier.compactMesh(simplified);
  // compactMesh rewrote `simplified` in place to the new vertex numbering; remap maps old vertex → new vertex.
  const IndexType = unique > 65535 ? Uint32Array : Uint16Array;
  chunks[json.accessors[primitive.indices].bufferView] = new Uint8Array(IndexType.from(simplified).buffer);
  Object.assign(json.accessors[primitive.indices], { count: simplified.length, componentType: IndexType === Uint32Array ? 5125 : 5123 });
  for (const [name, { array, size, accessor }] of Object.entries(attributes)) {
    const Type = array.constructor;
    const next = new Type(unique * size);
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
  json.asset = { ...json.asset, generator: `${json.asset.generator}; FloodGuard build-journey-characters (meshoptimizer ${meshoptDir.split("@")[1]})` };
  mkdirSync(outDir, { recursive: true });
  const glb = writeGlb(json, chunks);
  writeFileSync(path.join(outDir, out), glb);
  console.log(`${out}: ${(index32.length / 3) | 0} → ${(simplified.length / 3) | 0} triangles (${locked} locked vertices, error ${error.toFixed(4)}), ${vertexCount} → ${unique} vertices, ${(readFileSync(file).length / 1e6).toFixed(1)} MB → ${(glb.length / 1e6).toFixed(2)} MB`);
}

for (const character of CHARACTERS) await buildCharacter(character);
