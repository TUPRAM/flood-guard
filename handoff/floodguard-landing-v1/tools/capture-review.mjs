#!/usr/bin/env node
/** Run after Codex implements the review hook. Uses the actual project's Playwright package. */
import {createRequire} from 'node:module';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2);const get=(k,d)=>{const i=args.indexOf(k);return i<0?d:args[i+1]};
const repo=get('--repo');const base=get('--url','http://127.0.0.1:3000/');
let browser;
try{
 if(!repo)throw new Error('Usage: node tools/capture-review.mjs --repo "<repository>" --url http://127.0.0.1:3000/ [--out path]');
 const req=createRequire(path.join(path.resolve(repo),'apps/web/package.json'));
 const {chromium}=req('@playwright/test');
 const launchOptions={headless:true};if(get('--channel'))launchOptions.channel=get('--channel');
 browser=await chromium.launch(launchOptions);
 const story=JSON.parse(await readFile(path.join(root,'data/story.json'),'utf8'));
 const out=path.resolve(get('--out',path.join(repo,'outputs/landing-v1-review')));await mkdir(out,{recursive:true});
 const variants=[{name:'reference-desktop',width:1672,height:941},{name:'desktop',width:1920,height:1080},{name:'laptop',width:1440,height:900},{name:'tablet',width:1024,height:768},{name:'mobile',width:390,height:844},{name:'mobile-small',width:360,height:800}];
 const selected=get('--scene');const frames=selected?story.scenes.filter(s=>s.id===selected):story.scenes;
 if(!frames.length)throw new Error('Unknown --scene');
 const captures=[];
 for(const v of variants){const context=await browser.newContext({viewport:{width:v.width,height:v.height},deviceScaleFactor:1,reducedMotion:'reduce'});const page=await context.newPage();
  for(const s of frames){const errors=[];page.removeAllListeners('pageerror');page.on('pageerror',e=>errors.push(e.message));
   const u=new URL(base);u.searchParams.set('fgReview',s.id);u.searchParams.set('fgStill','1');
   await page.goto(u.href,{waitUntil:'domcontentloaded'});
   const frame=page.locator('[data-testid="fg-review-frame"][data-fg-ready="true"]');
   await frame.waitFor({state:'visible',timeout:15000});
   await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].filter(i=>i.getBoundingClientRect().width>0).map(i=>i.decode().catch(()=>{})));});
   const broken=await frame.locator('img').evaluateAll(imgs=>imgs.filter(i=>!i.complete||i.naturalWidth===0).map(i=>i.currentSrc||i.src));
   if(broken.length||errors.length)throw new Error(`${s.id}/${v.name}: broken images ${broken.join(',')} errors ${errors.join(',')}`);
   const file=`${s.id}--${v.name}.png`;await frame.screenshot({path:path.join(out,file),animations:'disabled'});
   captures.push({scene:s.id,viewport:v,file,scope:'settled shared-component review; not production scroll test'});
  }await context.close();
 }
 await writeFile(path.join(out,'captures.json'),JSON.stringify({baseUrl:base,captures},null,2)+'\n');
 console.log(`Captured ${captures.length} review frames in ${out}. Inspect them against originals; run production-flow tests separately.`);
}catch(e){console.error(e.message);process.exitCode=1;}finally{if(browser)await browser.close();}
