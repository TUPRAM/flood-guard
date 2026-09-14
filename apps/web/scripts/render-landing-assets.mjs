import { createRequire } from "node:module";
import { createServer } from "node:http";
import { mkdir, readFile, writeFile, readdir } from "node:fs/promises";
import { resolve, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { chromium } from "@playwright/test";

const require = createRequire(import.meta.url);
const requireVite = createRequire(createRequire(require.resolve("vitest/package.json")).resolve("vite/package.json"));
const { build } = requireVite("esbuild");
const sharp = createRequire(require.resolve("next/package.json"))("sharp");
const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const preview = process.argv.includes("--preview");
const destination = resolve(webRoot, preview ? "test-results/landing-art-preview" : "public/landing");
const contextIndex = process.argv.indexOf("--context-image");
const contextPath = contextIndex < 0 ? process.env.FLOODGUARD_CONTEXT_IMAGE : process.argv[contextIndex + 1];
if (!preview && (!contextPath || contextPath.startsWith("--"))) {
  throw new Error("Full asset generation requires --context-image <user-supplied aerial path> (or FLOODGUARD_CONTEXT_IMAGE). This records source provenance and prevents retaining an unrelated hero. Use --preview only for non-authoritative dry/flood previews.");
}

const bundle = await build({
  stdin: {
    contents: `
      import * as THREE from 'three';
      import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
      import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
      import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
      import { createTerrainScene, applyStoryFrame, getSceneTelemetry, DISTRICT_PLAN } from './src/components/landing/scene/terrain-scene.ts';
      import { sampleStory } from './src/lib/landing/sample-story.ts';
      const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true, preserveDrawingBuffer:true});
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.08;
      renderer.setClearColor('#f2f6f1', 0); renderer.setPixelRatio(2);
      document.body.appendChild(renderer.domElement);
      const scene = new THREE.Scene(); const rig = createTerrainScene(); scene.add(rig.world);
      const camera = new THREE.OrthographicCamera();
      window.renderIllustration = ({progress,width,height,composition}) => {
        renderer.setSize(width,height); const frame = sampleStory(progress);
        applyStoryFrame(rig,camera,width/height,frame,composition);
        renderer.render(scene,camera);
        return {triangles:renderer.info.render.triangles,drawCalls:renderer.info.render.calls,...getSceneTelemetry(rig,camera)};
      };
      window.exportIllustration = async (name) => {
        applyStoryFrame(rig,camera,4/3,sampleStory(name==='flood'?0.40:0.23));
        const parts = {terrain:rig.terrain,flood:rig.terrain,resident:rig.resident,coordinator:rig.coordinator,researcher:rig.studio};
        const root = parts[name].clone(true); root.visible = true;
        root.scale.setScalar(1); root.position.set(0,0,0);
        if (name === 'terrain' || name === 'flood') {
          for (const anchor of rig.world.children.filter(object => object.name.startsWith('Camera_') || object.name.startsWith('Target_'))) root.add(anchor.clone());
        }
        const geometries = [];
        root.traverse(object => {
          if (object.isMesh) {object.geometry=mergeVertices(object.geometry,0.00001); geometries.push(object.geometry);}
        });
        const result = await new GLTFExporter().parseAsync(root,{binary:true,onlyVisible:true,maxTextureSize:768});
        const imported = await new GLTFLoader().parseAsync(result,'');
        const nodes = []; imported.scene.traverse(object => {if(object.name) nodes.push(object.name);});
        geometries.forEach(geometry=>geometry.dispose());
        return {bytes:Array.from(new Uint8Array(result)),nodes};
      };
      window.illustrationReady = true;
      window.districtPlan = {buildingCount:DISTRICT_PLAN.buildings.length+1,landmarks:Object.keys(DISTRICT_PLAN.landmarks),referenceSelection:DISTRICT_PLAN.referenceSelection};
    `,
    resolveDir: webRoot,
    sourcefile: "landing-art-capture.ts",
    loader: "ts",
  },
  absWorkingDir: webRoot, bundle: true, write: false, format: "iife", platform: "browser",
  tsconfig: resolve(webRoot, "tsconfig.json"),
});

const server = createServer((request, response) => {
  if (request.url === "/scene.js") {
    response.writeHead(200, { "Content-Type": "text/javascript" }); response.end(bundle.outputFiles[0].contents);
  } else {
    response.writeHead(200, { "Content-Type": "text/html" });
    response.end('<!doctype html><html><head><style>html,body{margin:0;background:transparent}canvas{display:block}</style></head><body><script src="/scene.js"></script></body></html>');
  }
});
await new Promise((resolveReady) => server.listen(0, "127.0.0.1", resolveReady));
const address = server.address();
const browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const manifest = {
  revision: "architectural-district-v2", origin: "original_design_with_unverified_context_reference",
  source: "src/components/landing/scene/terrain-scene.ts",
  provenance: "Original authored Three.js district geometry and materials. The supplied aerial is unverified photo-style context, not documentary Mae Sai imagery or a verified before/after pair. Its selected road/field/roof region informed an illustrative plan only. No third-party 3D assets or Illoca artwork are used. Flood extent, building functions and people are illustrative, not surveyed or hydraulically modeled.",
  generator: "node scripts/render-landing-assets.mjs",
  status: "generated_and_browser_rendered_not_geographically_validated",
  assets: [],
};
const sourceBytes = await readFile(resolve(webRoot, manifest.source));
manifest.editableMaster = {path:manifest.source,bytes:sourceBytes.length,sha256:createHash("sha256").update(sourceBytes).digest("hex")};
manifest.editableSources = [];
for (const path of [manifest.source,"src/lib/landing/sample-story.ts","scripts/render-landing-assets.mjs"]) {
  const bytes=await readFile(resolve(webRoot,path));
  manifest.editableSources.push({path,bytes:bytes.length,sha256:createHash("sha256").update(bytes).digest("hex")});
}
try {
  await mkdir(destination, { recursive: true });
  await mkdir(resolve(destination, "models"), { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 });
  page.on("pageerror", (error) => { throw error; });
  await page.goto(`http://127.0.0.1:${address.port}/`);
  await page.waitForFunction(() => window.illustrationReady === true);
  manifest.district = await page.evaluate(() => window.districtPlan);
  const frames = [
    { id: "dry", progress: 0.235 }, { id: "flood", progress: 0.40 },
    { id: "place", progress: 0.15 }, { id: "access", progress: 0.475 },
    { id: "public", progress: 0.615 }, { id: "command", progress: 0.74 },
    { id: "studio", progress: 0.85 }, { id: "shared", progress: 0.945 },
  ];
  for (const frame of frames) {
    const width = frame.width ?? 1200, height = frame.height ?? 900;
    await page.setViewportSize({ width, height });
    const stats = await page.evaluate((settings) => window.renderIllustration(settings), { ...frame, width, height });
    const png = await page.locator("canvas").screenshot({ omitBackground: true });
    const bytes = await sharp(png).webp({ quality: 88, alphaQuality: 95, effort: 6 }).toBuffer();
    await writeFile(resolve(destination, `${frame.id}.webp`), bytes);
    manifest.assets.push({ id: frame.id, path: `/landing/${frame.id}.webp`, width, height, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex"), ...stats });
    if (!preview) {
      const small = await sharp(png).resize(640, 480).webp({ quality: 85, alphaQuality: 90, effort: 6 }).toBuffer();
      await writeFile(resolve(destination, `${frame.id}-small.webp`), small);
      manifest.assets.push({ id: `${frame.id}-small`, path: `/landing/${frame.id}-small.webp`, width: 640, height: 480, bytes: small.length, sha256: createHash("sha256").update(small).digest("hex") });
    }
    console.log(`${frame.id}: ${(bytes.length / 1024).toFixed(1)} KiB, ${stats.triangles} triangles, ${stats.drawCalls} draws`);
    if (preview && frame.id === "flood") break;
  }
  for (const id of preview ? [] : ["terrain", "flood", "resident", "coordinator", "researcher"]) {
    const result = await page.evaluate((name) => window.exportIllustration(name), id);
    const bytes = Buffer.from(result.bytes);
    await writeFile(resolve(destination, "models", `${id}-v2.glb`), bytes);
    manifest.assets.push({ id: `${id}-model`, path: `/landing/models/${id}-v2.glb`, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex"), validation: "Reimported successfully with GLTFLoader", nodes: result.nodes });
    console.log(`${id}-v2.glb: ${(bytes.length / 1024).toFixed(1)} KiB; verified ${result.nodes.length} named nodes`);
  }
  if (!preview && contextPath) {
    const source = await readFile(contextPath);
    manifest.contextSource = { filename: basename(contextPath), sha256: createHash("sha256").update(source).digest("hex"), bytes: source.length, status: "user_supplied_unverified_photo_style_concept", manipulation: "resize and WebP encoding only; no synthetic image editing or claimed geographic registration" };
    for (const [id,width] of [["hero-desktop",1672],["hero-mobile",900]]) {
      const {data:bytes,info}=await sharp(source).resize({width,withoutEnlargement:true}).webp({quality:id==="hero-desktop"?82:88,effort:6}).toBuffer({resolveWithObject:true});
      await writeFile(resolve(destination,`${id}.webp`),bytes);
      manifest.assets.push({id,path:`/landing/${id}.webp`,width:info.width,height:info.height,bytes:bytes.length,sha256:createHash("sha256").update(bytes).digest("hex"),origin:"user_supplied_unverified_context"});
    }
  }
  try {
    const contours = await readFile(resolve(destination, "contours.svg"));
    manifest.assets.push({ id: "contours", path: "/landing/contours.svg", bytes: contours.length, sha256: createHash("sha256").update(contours).digest("hex"), origin: "original_design" });
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  if (!preview) {
    for (const filename of (await readdir(resolve(destination,"models"))).filter(name=>name.endsWith("-v1.glb"))) {
      const bytes=await readFile(resolve(destination,"models",filename));
      manifest.assets.push({id:`legacy-${filename}`,path:`/landing/models/${filename}`,bytes:bytes.length,sha256:createHash("sha256").update(bytes).digest("hex"),status:"retained_unreferenced_v1_artifact",origin:"prior_original_procedural_illustration"});
    }
  }
  if (!preview) await writeFile(resolve(destination, "assets-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
} finally {
  await browser.close();
  await new Promise((resolveClosed) => server.close(resolveClosed));
}
