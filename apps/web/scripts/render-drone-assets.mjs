import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { chromium } from "@playwright/test";

const require = createRequire(import.meta.url);
const requireVite = createRequire(createRequire(require.resolve("vitest/package.json")).resolve("vite/package.json"));
const { build } = requireVite("esbuild");
const sharp = createRequire(require.resolve("next/package.json"))("sharp");
const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const preview = process.argv.includes("--preview");
const destination = resolve(webRoot, preview ? "test-results/drone-v4-art-preview" : "public/landing/desktop-v4");
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const bundle = await build({
  stdin: { contents: `
    import * as THREE from 'three';
    import {createDroneScene,applyDroneFrame,getDroneTelemetry,DRONE_PLAN,DRONE_CAMERA} from './src/components/landing/scene/drone-scene.ts';
    import {ILLUSTRATIVE_SCENARIO,ILLUSTRATIVE_FINDING} from './src/lib/landing/illustrative-scenario.ts';
    const renderer=new THREE.WebGLRenderer({alpha:false,antialias:true,preserveDrawingBuffer:true});
    renderer.setPixelRatio(1.5);renderer.setClearColor('#acbca4',1);
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.02;
    document.body.appendChild(renderer.domElement);
    const scene=new THREE.Scene();const rig=createDroneScene();scene.add(rig.world);
    const camera=new THREE.PerspectiveCamera();
    window.renderDrone=({width,height,flight,flood,network,result,pointer})=>{
      renderer.setSize(width,height);applyDroneFrame(rig,camera,width/height,{flight,flood,network,result,pointer});
      renderer.render(scene,camera);
      return {...getDroneTelemetry(rig,camera),triangles:renderer.info.render.triangles,drawCalls:renderer.info.render.calls,textures:renderer.info.memory.textures,geometries:renderer.info.memory.geometries,treeCount:rig.treeCount};
    };
    window.dronePlan={contextBuildings:DRONE_PLAN.context.length,neighborhoodBuildings:DRONE_PLAN.neighborhood.length+1,seed:DRONE_PLAN.seed,sourceStatus:DRONE_PLAN.sourceStatus,camera:DRONE_CAMERA,finalHorizontalViewOffset:.16,toneMappingExposure:1.02,scenario:ILLUSTRATIVE_SCENARIO,finding:ILLUSTRATIVE_FINDING};
    window.droneReady=true;
  `, resolveDir: webRoot, sourcefile: "drone-art-capture.ts", loader: "ts" },
  absWorkingDir: webRoot, bundle: true, write: false, format: "iife", platform: "browser", tsconfig: resolve(webRoot, "tsconfig.json"),
});
const server = createServer((request,response)=>{
  if(request.url==="/scene.js"){response.writeHead(200,{"Content-Type":"text/javascript"});response.end(bundle.outputFiles[0].contents);}
  else{response.writeHead(200,{"Content-Type":"text/html"});response.end('<!doctype html><html><head><style>html,body{margin:0}canvas{display:block}</style></head><body><script src="/scene.js"></script></body></html>');}
});
await new Promise(resolveReady=>server.listen(0,"127.0.0.1",resolveReady));
const browser=await chromium.launch({headless:true,args:["--use-angle=swiftshader","--enable-unsafe-swiftshader"]});
const manifest={revision:"desktop-access-world-v4",worldId:"original-mae-sai-inspired-access-world-v4",status:"generated_and_browser_rendered_not_geographically_validated",
  provenance:"Original authored continuous Three.js terrain, low-rise town, neighborhood, river, fields, procedural DataTextures and lighting. Mae Sai-inspired illustrative geography, not surveyed terrain, photogrammetry, documentary imagery, measured flooding or current conditions. No external image, NYC asset or aerial texture is used.",
  generator:"node scripts/render-drone-assets.mjs",editableSources:[],assets:[]};
try {
  await mkdir(destination,{recursive:true});
  for(const path of ["src/components/landing/scene/drone-scene.ts","src/lib/landing/illustrative-scenario.ts","scripts/render-drone-assets.mjs"]){const bytes=await readFile(resolve(webRoot,path));manifest.editableSources.push({path,bytes:bytes.length,sha256:hash(bytes)});}
  const errors=[];
  const page=await browser.newPage({viewport:{width:1600,height:900}});page.on("pageerror",error=>errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>window.droneReady===true);
  manifest.plan=await page.evaluate(()=>window.dronePlan);
  const frames=[{id:"far",flight:0,flood:0},{id:"connected",flight:1,flood:0},{id:"flood",flight:1,flood:1},{id:"access",flight:1,flood:1,network:1},{id:"finding",flight:1,flood:1,network:1,result:1}];
  for(const frame of frames){
    const width=1600,height=900;const telemetry=await page.evaluate(settings=>window.renderDrone(settings),{...frame,width,height});
    if(errors.length)throw new Error(errors.join("\n"));
    const png=await page.locator("canvas").screenshot();
    const bytes=await sharp(png).webp({quality:frame.id==="far"?82:86,effort:6}).toBuffer();
    await writeFile(resolve(destination,`${frame.id}.webp`),bytes);
    manifest.assets.push({id:frame.id,path:`/landing/desktop-v4/${frame.id}.webp`,width,height,bytes:bytes.length,sha256:hash(bytes),...telemetry});
    console.log(`${frame.id}: ${bytes.length} bytes; ${telemetry.contextBuildingCount}+${manifest.plan.neighborhoodBuildings} buildings; ${telemetry.triangles} triangles; ${telemetry.drawCalls} draws`);
  }
  if(!preview)await writeFile(resolve(destination,"scene-manifest.json"),`${JSON.stringify(manifest,null,2)}\n`);
} finally {await browser.close();await new Promise(resolveClosed=>server.close(resolveClosed));}
