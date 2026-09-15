#!/usr/bin/env node
/** Dry-run by default; never edits application code, profiles, service worker, or git. */
import {readFile,writeFile,mkdir,lstat,access,copyFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2);const get=k=>{const i=args.indexOf(k);return i<0?undefined:args[i+1]};
const apply=args.includes('--apply');const repoArg=get('--repo');
const hash=b=>createHash('sha256').update(b).digest('hex');
async function exists(p){try{await access(p);return true;}catch{return false;}}
async function denySymlinks(p){let q=p;while(q!==path.dirname(q)){if(await exists(q)){if((await lstat(q)).isSymbolicLink())throw new Error(`Refusing symlink destination component: ${q}`);}q=path.dirname(q);}}
try{
 if(!repoArg)throw new Error('Usage: node tools/install-assets.mjs --repo "<existing repository>" [--apply]');
 const repo=path.resolve(repoArg);const pkg=JSON.parse(await readFile(path.join(repo,'apps/web/package.json'),'utf8'));
 if(pkg.name!=='@floodguard/web')throw new Error(`Unexpected app package ${pkg.name}; inspect the actual repository manually.`);
 const dest=path.join(repo,'apps/web/public/landing/floodguard-v1');await denySymlinks(dest);
 const data=JSON.parse(await readFile(path.join(root,'data/assets.json'),'utf8'));
 const files=data.assets.map(a=>({relative:a.publicUrl.slice('/landing/floodguard-v1/'.length),source:path.join(root,a.file),sha:a.sha256}));
 for(const name of await readdir(path.join(root,'runtime/decor'))){if(!name.endsWith('.svg'))continue;files.push({relative:'decor/'+name,source:path.join(root,'runtime/decor',name)});}
 const index=Buffer.from(JSON.stringify({schemaVersion:1,scope:'illustrative landing artwork',assets:data.assets.map(({id,publicUrl,width,height,sha256})=>({id,url:publicUrl,width,height,sha256}))},null,2)+'\n');
 const plan=[];
 for(const f of [...files,{relative:'asset-index.json',buffer:index}]){
  if(f.relative.includes('..')||path.isAbsolute(f.relative))throw new Error('Unsafe output path');
  const target=path.join(dest,f.relative);await denySymlinks(target);
  const content=f.buffer??await readFile(f.source);if(f.sha&&hash(content)!==f.sha)throw new Error(`Source hash mismatch ${f.relative}`);
  if(await exists(target)){const current=await readFile(target);if(hash(current)!==hash(content))throw new Error(`Conflict: ${target}. Existing file differs; no files have been written. Inspect it before replacing anything.`);plan.push({target,status:'identical; keep',content});}
  else plan.push({target,status:apply?'copy':'would copy',content});
 }
 if(apply)for(const p of plan){if(p.status==='copy'){await mkdir(path.dirname(p.target),{recursive:true});await writeFile(p.target,p.content,{flag:'wx'});}}
 console.log(JSON.stringify({mode:apply?'APPLY':'DRY RUN',destination:dest,files:plan.map(({target,status,content})=>({file:path.relative(repo,target).split(path.sep).join('/'),status,bytes:content.length})),applicationCodeChanged:false,offlinePolicyChanged:false},null,2));
}catch(e){console.error(e.message);process.exitCode=1;}
