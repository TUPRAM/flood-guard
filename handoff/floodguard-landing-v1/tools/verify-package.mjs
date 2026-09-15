#!/usr/bin/env node
import {readFile,stat,lstat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const readJson=async p=>JSON.parse(await readFile(path.join(root,p),'utf8'));
function safe(p){if(typeof p!=='string'||p.includes('\\')||p.startsWith('/')||p.split('/').some(s=>s==='..')||/^[A-Za-z]:/.test(p))throw new Error(`Unsafe relative path ${p}`);const q=path.resolve(root,p);if(!q.startsWith(root+path.sep))throw new Error('Path escaped package');return q;}
let checked=0;
try{
 const manifest=await readJson('package-manifest.json');
 for(const f of manifest.files){const p=safe(f.file);if((await lstat(p)).isSymbolicLink())throw new Error(`Symlink not allowed ${f.file}`);const data=await readFile(p);if(data.length!==f.bytes||createHash('sha256').update(data).digest('hex')!==f.sha256)throw new Error(`Integrity mismatch ${f.file}`);checked++;}
 const assets=await readJson('data/assets.json');
 if(assets.assets.length!==15)throw new Error('Expected 15 responsive raster derivatives');
 for(const a of assets.assets){const d=await readFile(safe(a.file));if(d.length!==a.bytes||createHash('sha256').update(d).digest('hex')!==a.sha256)throw new Error(`Asset mismatch ${a.id}`);if(!a.publicUrl.startsWith('/landing/floodguard-v1/')||a.publicUrl.includes('..'))throw new Error('Unsafe public asset path');}
 const story=await readJson('data/story.json');
 if(story.scenes.length!==9||story.chapters.length!==4)throw new Error('Expected nine states / four chapters');
 if(new Set(story.scenes.map(s=>s.id)).size!==9)throw new Error('Duplicate scene IDs');
 for(const s of story.scenes){for(const f of Object.values(s.reference))await stat(safe(f));if(s.card&&!story.cards[s.card])throw new Error(`Missing card ${s.card}`);}
 const anchors=await readJson('data/anchors.json');
 for(const [name,c] of Object.entries(anchors.viewports)){if(c.length!==4||!c.every(Number.isFinite)||c[0]<0||c[1]<0||c[2]<=0||c[3]<=0||c[0]+c[2]>1536||c[1]+c[3]>1024)throw new Error(`Invalid crop ${name}`);}
 const end=story.scenes.slice(story.scenes.findIndex(s=>s.id==='S3A-01'));if(!end.every(s=>s.waterState==='W2'))throw new Error('W2 continuity broken');
 console.log(JSON.stringify({ok:true,filesHashed:checked,originalPngs:24,runtimeRasterVariants:15,storyStates:9,chapters:4,websiteBuildTested:false,note:'Checks integrity and data structure only. No proof of visual alignment or website functionality.'},null,2));
}catch(e){console.error(e.message);process.exitCode=1;}
