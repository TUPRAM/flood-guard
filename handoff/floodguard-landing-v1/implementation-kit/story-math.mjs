/** Pure helpers: illustration geometry only, never geographic or navigation data. */
function positive(value, name) {
  if (!Number.isFinite(value) || value <= 0) throw new RangeError(`${name} must be positive and finite`);
}
function finitePoint(p) {
  if (!Array.isArray(p) || p.length !== 2 || !p.every(Number.isFinite)) throw new TypeError('Expected a finite [x,y] point');
}
export function validateCrop(crop) {
  if (!Array.isArray(crop) || crop.length !== 4 || !crop.every(Number.isFinite)) throw new TypeError('Expected finite [x,y,width,height]');
  positive(crop[2], 'crop width'); positive(crop[3], 'crop height');
  return crop;
}
/** Width/height are the displayed crop; preserve its aspect ratio in the DOM. */
export function projectCropPoint(point, crop, width, height) {
  finitePoint(point); validateCrop(crop); positive(width, 'width'); positive(height, 'height');
  return [(point[0] - crop[0]) / crop[2] * width, (point[1] - crop[1]) / crop[3] * height];
}
export function unprojectCropPoint(point, crop, width, height) {
  finitePoint(point); validateCrop(crop); positive(width, 'width'); positive(height, 'height');
  return [crop[0] + point[0] / width * crop[2], crop[1] + point[1] / height * crop[3]];
}
export function cropImageStyle(crop, nativeWidth = 1536, nativeHeight = 1024) {
  validateCrop(crop); positive(nativeWidth, 'nativeWidth'); positive(nativeHeight, 'nativeHeight');
  return {width:`${nativeWidth/crop[2]*100}%`,height:`${nativeHeight/crop[3]*100}%`,left:`${-crop[0]/crop[2]*100}%`,top:`${-crop[1]/crop[3]*100}%`};
}
/** Used only when explicitly choosing object-fit instead of crop projection. */
export function fitRect(nativeWidth, nativeHeight, width, height, mode = 'contain', posX = .5, posY = .5) {
  for (const [v,n] of [[nativeWidth,'nativeWidth'],[nativeHeight,'nativeHeight'],[width,'width'],[height,'height']]) positive(v,n);
  if (!['contain','cover'].includes(mode)) throw new TypeError('mode must be contain or cover');
  if (![posX,posY].every(v=>Number.isFinite(v) && v>=0 && v<=1)) throw new RangeError('object position must be in [0,1]');
  const scale=(mode==='contain'?Math.min:Math.max)(width/nativeWidth,height/nativeHeight);
  return {scale,width:nativeWidth*scale,height:nativeHeight*scale,x:(width-nativeWidth*scale)*posX,y:(height-nativeHeight*scale)*posY};
}
export function polylinePath(points) {
  if (!Array.isArray(points) || points.length < 2) throw new TypeError('At least two points required');
  points.forEach(finitePoint);
  return points.map((p,i)=>`${i?'L':'M'} ${p[0]} ${p[1]}`).join(' ');
}
export function routeSegments(points,start,end) {
  polylinePath(points);
  if (!Number.isInteger(start)||!Number.isInteger(end)||start<0||end>=points.length||end<=start) throw new RangeError('Invalid affected indices');
  return {before:start>0?points.slice(0,start+1):[],affected:points.slice(start,end+1),after:end<points.length-1?points.slice(end):[]};
}
export function findScene(scenes,id) {
  const scene=scenes.find(s=>s.id===id);
  if(!scene) throw new RangeError(`Unknown scene: ${id}`);
  return scene;
}
/** Identical W2 artwork must not be transitioned as different environments. */
export function transitionKind(from,to,reducedMotion=false) {
  if (reducedMotion) return 'instant';
  if (from.id===to.id) return 'none';
  return from.waterState===to.waterState?'overlay-only':'fade-through-paper';
}
export function resolveProgress(scenes,progress) {
  if(!Number.isFinite(progress)) throw new TypeError('progress must be finite');
  if(scenes.some(s=>!Number.isFinite(s.weight)||s.weight<0)) throw new RangeError('Invalid scene weight');
  const weighted=scenes.filter(s=>s.weight>0);
  if(!weighted.length) throw new RangeError('No weighted scenes');
  if(weighted.some(s=>!Number.isFinite(s.weight))) throw new RangeError('Invalid scene weight');
  const p=Math.min(1,Math.max(0,progress));
  const total=weighted.reduce((a,s)=>a+s.weight,0);
  const position=p*total;
  let sum=0;
  for(const scene of weighted){sum+=scene.weight;if(position<sum)return scene;}
  return weighted.at(-1);
}
