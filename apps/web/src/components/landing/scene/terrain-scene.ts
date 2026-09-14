import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { CAMERA_BY_CHAPTER, type StoryFrame } from "@/lib/landing/sample-story";

type Point = readonly [number, number, number];
type GroundPoint = readonly [number, number];
type Building = { id: string; x: number; z: number; width: number; depth: number; height: number; roof: "gable" | "flat" | "shed"; color: string; angle: number };
const C = {
  ground: "#e8edeb", section: "#d6ddda", pavement: "#f2f3ef", road: "#a3afaf", marking: "#f7f6ea",
  wall: "#f4f2e9", coolWall: "#d7e0df", edge: "#354445", glass: "#758d91", dark: "#3f4b4d",
  blue: "#386c92", red: "#986b5f", roof: "#768584", zinc: "#c2c9c6", green: "#7a8e75", leaf: "#657b63",
  field: "#bbc7ac", fieldDark: "#9cae93", water: "#819c98", foam: "#d8ded8", amber: "#b67d27", teal: "#286e69",
};

export const LANDMARK_ANCHORS = Object.freeze({
  Junction_A: [-3.6, .18, 4.6], Service_A: [-.9, .7, 3.6],
  Neighborhood_A: [-6.1, .65, .8], Field_A: [1.3, .1, -3.7],
} as const);
export const SCENE_ANCHORS = Object.freeze({
  TerrainRoot: [0, 0, 0], ...LANDMARK_ANCHORS,
  Community_A: LANDMARK_ANCHORS.Neighborhood_A, RoadSegment_A: LANDMARK_ANCHORS.Junction_A, Hospital_A: LANDMARK_ANCHORS.Service_A,
  ReportAnchor_R017: [-3.6, .42, 4.6], PhoneScreenAnchor: [-5.6, .32, 1.55],
  CommandScreenAnchor: [-1.45, .41, 3.45], StudioScreenAnchor: [.25, .25, 3.4],
} as const);

const mainRoad: readonly GroundPoint[] = [[-4.1,-6],[-3.5,-3.5],[-3,-1.1],[-3.15,1.1],[-3.9,3],[-3.6,4.6],[-3.15,6]];
const arterial: readonly GroundPoint[] = [[-9,5.4],[-3.6,4.6],[1.1,4.05],[5.5,3.25],[9,2.8]];
const eastStreet: readonly GroundPoint[] = [[-3.1,.7],[0,.45],[3.5,.25],[6.4,-.4],[9,-.65]];
const northStreet: readonly GroundPoint[] = [[-8.2,-2.65],[-3.5,-3.25],[-1.4,-2.2],[1,-1.55],[4.7,-1.9],[8.2,-2.8]];
const eastSpine: readonly GroundPoint[] = [[5.1,-6],[4.65,-3.7],[4.65,-1.9],[5.2,.15],[5.5,3.25],[6.8,6]];
const building = (id: string, x: number, z: number, width: number, depth: number, height: number, roof: Building["roof"], color: string, angle = 0): Building => ({ id,x,z,width,depth,height,roof,color,angle });
const buildings: readonly Building[] = [
  building("West_01",-6.6,-4.75,1,.75,.38,"gable",C.red,-.1),
  building("West_02",-5.25,-4.6,.85,1.1,.48,"shed",C.zinc,-.12),
  building("West_03",-7.3,-3.5,1.25,.62,.32,"gable",C.roof,-.15),
  building("West_04",-5.35,-3.4,.78,.68,.62,"flat",C.coolWall),
  building("West_05",-7.3,-1.7,1.45,.82,.38,"shed",C.zinc,-.1),
  building("West_06",-5.75,-1.65,1.15,.75,.6,"gable",C.red,-.06),
  building("West_07",-4.25,-1.6,.63,1,.57,"shed",C.blue,.05),
  building("West_08",-7.7,-.25,.75,.75,.46,"flat",C.roof),
  building("West_09",-6.3,-.15,1.25,.8,.38,"gable",C.zinc,-.12),
  building("Neighborhood_A_Building",-6.1,.8,1.3,.7,.48,"gable",C.red,-.12),
  building("West_11",-4.55,.35,.75,.85,.73,"flat",C.coolWall,.03),
  building("West_12",-7.55,1.4,.85,.85,.5,"gable",C.roof,.08),
  building("West_13",-7.2,2.95,1.45,.8,.34,"shed",C.zinc,-.12),
  building("West_14",-5.7,2.85,1.15,.8,.55,"shed",C.blue,-.08),
  building("West_15",-5.1,4.05,1,.52,.34,"gable",C.red,-.1),
  building("North_01",-2.5,-5.1,1.1,.85,.55,"flat",C.zinc),
  building("North_02",-1.15,-5.15,.85,.7,.38,"gable",C.red),
  building("North_03",2.8,-5.1,1.2,.68,.5,"gable",C.roof),
  building("North_04",3.6,-3.8,.62,.9,.6,"flat",C.coolWall,-.05),
  building("Center_01",-1.8,-1.05,1.15,.75,.65,"flat",C.zinc,-.08),
  building("Center_02",-.35,-1,1.1,.72,.42,"gable",C.roof,-.08),
  building("Center_03",1.3,-.6,1.15,.68,.56,"gable",C.red,-.08),
  building("Center_04",2.95,-.85,.9,.78,.74,"flat",C.coolWall,-.07),
  building("Center_05",-1.85,1.55,1.35,.85,.43,"shed",C.blue,-.06),
  building("Center_06",-.25,1.5,1.4,.8,.43,"gable",C.zinc,-.06),
  building("Center_07",1.35,1.4,1.15,.78,.54,"gable",C.red,-.06),
  building("Center_08",3.15,1.25,1.25,.8,.67,"flat",C.coolWall,-.06),
  building("Center_09",2.1,2.75,1.2,.72,.48,"gable",C.roof,-.1),
  building("Center_10",3.65,2.65,1.15,.65,.35,"shed",C.zinc,-.1),
  building("East_01",6.1,-4.9,1.1,.85,.55,"gable",C.red,.09),
  building("East_02",7.5,-4.75,.8,.85,.42,"flat",C.roof,.09),
  building("East_03",6.15,-3.45,1.4,.65,.48,"gable",C.zinc,.09),
  building("East_04",7.6,-3.25,.95,.7,.52,"shed",C.blue,.09),
  building("East_05",6.45,-1.8,1,.75,.43,"gable",C.red,-.1),
  building("East_06",7.95,-1.9,.85,.62,.57,"flat",C.coolWall,-.1),
  building("East_07",6.65,.55,1.1,.75,.62,"gable",C.zinc,-.14),
  building("East_08",8.1,.4,.8,.72,.4,"gable",C.roof,-.14),
  building("East_09",6.9,1.9,1.15,.62,.48,"shed",C.blue,-.14),
  building("East_10",8.3,1.75,.65,.68,.62,"flat",C.coolWall,-.14),
  building("South_01",-1.9,5.3,1.7,.72,.4,"shed",C.zinc,-.1),
  building("South_02",.15,5.05,1.45,.72,.57,"flat",C.coolWall,-.1),
  building("South_03",2,4.85,1.25,.72,.36,"gable",C.roof,-.1),
  building("South_04",3.7,4.65,1.25,.72,.6,"gable",C.red,-.1),
  building("South_05",4.3,5.65,1.1,.5,.4,"shed",C.zinc,-.1),
  building("South_06",7.8,4,1.1,.8,.56,"flat",C.coolWall,-.14),
  building("South_07",8.2,5.25,.9,.75,.4,"gable",C.red,-.14),
];

/** Visual reference only; illustrative units carry no real-world distance or geographic registration. */
export const DISTRICT_PLAN = Object.freeze({
  bounds: Object.freeze({minX:-9,maxX:9,minZ:-6,maxZ:6}),
  referenceSelection: Object.freeze({x:650,y:310,width:640,height:575,sourceWidth:1672,sourceHeight:941}),
  buildings: Object.freeze(buildings), roads: Object.freeze({mainRoad,arterial,eastStreet,northStreet,eastSpine}), landmarks: LANDMARK_ANCHORS,
});

class ArchitectureBatch {
  private pieces: THREE.BufferGeometry[] = [];
  add(geometry: THREE.BufferGeometry, color: string, position: Point = [0,0,0], rotation: Point = [0,0,0], scale: Point = [1,1,1]) {
    const expanded = geometry.index ? geometry.toNonIndexed() : geometry.clone(); geometry.dispose(); expanded.deleteAttribute("uv");
    expanded.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...position),new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation)),new THREE.Vector3(...scale)));
    const rgb = new THREE.Color(color), colors = new Float32Array(expanded.getAttribute("position").count * 3);
    for (let i=0;i<colors.length;i+=3) { colors[i]=rgb.r; colors[i+1]=rgb.g; colors[i+2]=rgb.b; }
    expanded.setAttribute("color",new THREE.BufferAttribute(colors,3)); this.pieces.push(expanded);
  }
  box(position: Point, size: Point, color: string, rotation: Point = [0,0,0]) { this.add(new THREE.BoxGeometry(...size),color,position,rotation); }
  line(points: readonly Point[], radius: number, color: string) {
    this.add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p))),Math.max(4,points.length*4),radius,4,false),color);
  }
  finish(name: string, material?: THREE.Material) {
    const geometry=mergeGeometries(this.pieces,false); this.pieces.forEach(p=>p.dispose()); this.pieces=[];
    if (!geometry) throw new Error(`Unable to assemble ${name}.`);
    geometry.computeBoundingSphere();
    const mesh=new THREE.Mesh(geometry,material??new THREE.MeshStandardMaterial({vertexColors:true,roughness:.86,metalness:.025}));
    mesh.name=name; mesh.castShadow=true; mesh.receiveShadow=true; return mesh;
  }
}
function footprint(points: readonly GroundPoint[], depth: number) {
  const shape=new THREE.Shape(points.map(([x,z])=>new THREE.Vector2(x,-z))); shape.closePath();
  const geometry=new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,steps:1}); geometry.rotateX(-Math.PI/2); return geometry;
}
function roof(width: number, depth: number, rise: number) {
  const shape=new THREE.Shape(); shape.moveTo(-width/2,0); shape.lineTo(0,rise); shape.lineTo(width/2,0); shape.closePath();
  const geometry=new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,steps:1}); geometry.translate(0,0,-depth/2); return geometry;
}
function addRoad(batch: ArchitectureBatch, points: readonly GroundPoint[], width: number, markings=false) {
  for (let i=1;i<points.length;i++) {
    const [ax,az]=points[i-1],[bx,bz]=points[i],length=Math.hypot(bx-ax,bz-az),angle=-Math.atan2(bz-az,bx-ax);
    batch.box([(ax+bx)/2,.061,(az+bz)/2],[length+.1,.018,width+.17],C.pavement,[0,angle,0]);
    batch.box([(ax+bx)/2,.073,(az+bz)/2],[length+.08,.014,width],C.road,[0,angle,0]);
    if(markings) for(let dash=0,count=Math.floor(length/.42);dash<count;dash++) {
      const t=(dash+.5)/count; batch.box([ax+(bx-ax)*t,.084,az+(bz-az)*t],[.21,.003,.018],C.marking,[0,angle,0]);
    }
  }
}
function addBuilding(batch: ArchitectureBatch,spec: Building) {
  const {x,z,width:w,depth:d,height:h,angle,color}=spec;
  const point=(px:number,py:number,pz:number):Point=>[x+px*Math.cos(angle)+pz*Math.sin(angle),py,z-px*Math.sin(angle)+pz*Math.cos(angle)];
  const box=(p:Point,size:Point,shade:string)=>batch.box(point(...p),size,shade,[0,angle,0]);
  box([0,.1,0],[w+.14,.08,d+.13],C.pavement); box([0,.14+h/2,0],[w,h,d],h>.6?C.coolWall:C.wall);
  box([0,.15,d/2+.018],[w,.04,.035],C.zinc);
  if(spec.roof==="gable") {
    const rise=Math.min(.23,w*.19); batch.add(roof(w+.15,d+.17,rise),color,point(0,h+.14,0),[0,angle,0]);
    box([0,h+.15+rise,0],[.025,.024,d+.2],C.zinc);
    for(const side of [-1,1]) for(let rib=1;rib<5;rib++) {
      const offset=side*w*rib/10;
      box([offset,h+.148+rise*(1-Math.abs(offset)/(w/2)),0],[.009,.012,d+.15],color===C.zinc?"#9eaaa9":"#a0abaa");
    }
  } else {
    box([0,h+.16,0],[w+.1,.05,d+.1],color);
    if(spec.roof==="flat") {
      box([0,h+.2,-d/2],[w+.08,.07,.035],C.wall);
      for(const side of [-1,1]) box([side*w/2,h+.2,0],[.035,.07,d],C.wall);
      box([w*.22,h+.23,-d*.17],[w*.2,.1,d*.22],C.zinc);
      batch.add(new THREE.CylinderGeometry(.065,.065,.16,9),C.dark,point(-w*.24,h+.26,-d*.23));
    }
  }
  const columns=Math.max(2,Math.floor(w/.3)),floors=h>.55?2:1;
  for(let row=0;row<floors;row++) for(let col=0;col<columns;col++) {
    const px=-w/2+(col+.5)*w/columns,py=.3+row*.25;
    box([px,py,d/2+.006],[w/columns*.55,.115,.018],C.glass);
    box([px,py-.065,d/2+.021],[w/columns*.65,.012,.045],C.zinc);
  }
  box([w*.22,.265,d/2+.022],[.12,.25,.025],C.dark);
  if(h>.5) {
    box([0,.44,d/2+.12],[w*.88,.032,.23],color);
    for(const side of [-1,1]) box([side*w*.4,.275,d/2+.18],[.019,.3,.019],C.zinc);
  }
  box([w/2+.006,.36,0],[.018,.12,d*.27],C.glass);
  if (["West_05","West_13","Center_05","Center_06","East_03","South_01"].includes(spec.id)) {
    box([0,.33,d/2+.12],[w+.08,.035,.28],color);
    for(let unit=0;unit<3;unit++) {
      const px=-w/2+(unit+.5)*w/3;
      box([px,.255,d/2+.018],[w/3*.86,.22,.019],unit%2?C.glass:C.zinc);
      box([px-w/6,.23,d/2+.032],[.025,.3,.035],C.wall);
      for(let slat=0;slat<4;slat++) box([px,.18+slat*.044,d/2+.032],[w/3*.83,.006,.01],C.roof);
    }
  }
}
function addTree(batch:ArchitectureBatch,x:number,z:number,size:number,seed:number) {
  batch.add(new THREE.CylinderGeometry(.018,.028,size*.6,5),C.dark,[x,.05+size*.3,z]);
  for(let cluster=0;cluster<4;cluster++) {
    const a=cluster*2.4+seed,r=size*.19;
    batch.add(new THREE.IcosahedronGeometry(size*(.23+cluster*.025),1),cluster%2?C.leaf:C.green,[x+Math.cos(a)*r,.07+size*(.66+cluster*.09),z+Math.sin(a)*r],[seed,a,.3],[1,.85,.92]);
  }
}
function addPerson(batch:ArchitectureBatch,x:number,z:number,shirt=C.blue,y=.14,seated=false) {
  const hip=seated?.10:.15;
  for(const side of [-1,1]) batch.box([x+side*.025,y+hip/2,z],[.03,hip,.035],C.dark);
  batch.add(new THREE.CylinderGeometry(.038,.03,.105,7),shirt,[x,y+hip+.05,z]);
  batch.add(new THREE.SphereGeometry(.029,8,6),"#bd9d89",[x,y+hip+.135,z]);
  for(const side of [-1,1]) batch.line([[x+side*.04,y+hip+.08,z],[x+side*.055,y+hip+.025,z+.025],[x+side*.01,y+hip+.02,z+.06]],.012,shirt);
  batch.box([x+.005,y+hip+.025,z+.067],[.024,.032,.005],C.dark,[-.35,0,0]);
}
function addDesk(batch:ArchitectureBatch,x:number,z:number,y:number,paper=false) {
  batch.box([x,y+.16,z],[.39,.022,.22],C.wall);
  for(const side of [-1,1]) batch.box([x+side*.16,y+.08,z],[.018,.15,.16],C.dark);
  if(paper) for(let i=0;i<4;i++) {
    const px=x+(i%2-.5)*.16,pz=z+(Math.floor(i/2)-.5)*.09;
    batch.box([px,y+.174,pz],[.13,.003,.07],C.wall); batch.box([px+.016,y+.177,pz],[.055,.002,.05],i===3?C.amber:C.water); batch.box([px-.025,y+.18,pz],[.013,.002,.06],C.roof);
  } else {
    batch.box([x,y+.235,z-.06],[.025,.14,.025],C.dark); batch.box([x,y+.29,z-.06],[.25,.16,.014],C.dark);
    batch.box([x,y+.29,z-.05],[.224,.136,.006],C.coolWall); batch.box([x-.015,y+.29,z-.046],[.07,.105,.002],C.water);
    batch.box([x+.025,y+.28,z-.043],[.16,.009,.002],C.teal); batch.box([x,y+.18,z+.05],[.21,.012,.06],C.zinc);
  }
  batch.box([x,y+.09,z+.22],[.12,.015,.12],C.blue); batch.box([x,y+.145,z+.275],[.12,.12,.015],C.blue);
  addPerson(batch,x,z+.2,paper?C.teal:C.blue,y+.06,true);
}
function outline(mesh:THREE.Mesh,opacity=.2) {
  const edges=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry,28),new THREE.LineBasicMaterial({color:C.edge,transparent:true,opacity}));
  edges.name=`${mesh.name}_ArchitecturalEdges`; return edges;
}
function landmarkLabel(title:string,point:Point,color:string) {
  const canvas=document.createElement("canvas"); canvas.width=768; canvas.height=112;
  const context=canvas.getContext("2d"); if(!context) throw new Error("Architectural annotation graphics are unavailable.");
  context.font="600 64px Arial, sans-serif"; canvas.width=Math.ceil(context.measureText(title).width+24);
  context.font="600 64px Arial, sans-serif"; context.textAlign="center"; context.textBaseline="middle";
  context.strokeStyle="#f5f7f3"; context.lineWidth=9; context.lineJoin="round"; context.strokeText(title,canvas.width/2,56);
  context.fillStyle=color; context.fillText(title,canvas.width/2,56);
  const texture=new THREE.CanvasTexture(canvas); texture.colorSpace=THREE.SRGBColorSpace;
  const mesh=new THREE.Mesh(new THREE.PlaneGeometry(.5*canvas.width/112,.5),new THREE.MeshBasicMaterial({map:texture,transparent:true,depthTest:false,depthWrite:false,toneMapped:false}));
  mesh.name=`Annotation_${title}`; mesh.position.set(...point); mesh.renderOrder=10; return mesh;
}

export interface TerrainRig {
  world:THREE.Group; terrain:THREE.Group; resident:THREE.Group; coordinator:THREE.Group; studio:THREE.Group;
  water:THREE.Mesh; waterDetails:THREE.Mesh; marker:THREE.Group; primaryRoute:THREE.Mesh; scenarioRoute:THREE.Mesh; floodAmount:number; dispose:()=>void;
  labels:readonly THREE.Mesh[];
}

/** One master serves every chapter. Buildings and human-scale workspaces never move or resize. */
export function createTerrainScene(options:{labels?:boolean}={}):TerrainRig {
  const world=new THREE.Group(); world.name="FloodGuardIllustrativeDistrict";
  const terrain=new THREE.Group(); terrain.name="TerrainRoot";
  for(const [name,camera] of Object.entries(CAMERA_BY_CHAPTER)) {
    const pose=new THREE.Object3D(); pose.name=`Camera_${name}`; pose.position.fromArray(camera.position);
    const target=new THREE.Object3D(); target.name=`Target_${name}`; target.position.fromArray(camera.target); world.add(pose,target);
  }
  const ground=new ArchitectureBatch();
  const boundary:readonly GroundPoint[]=[[-9,-6],[8.8,-6],[9,-3.6],[9,5.8],[5.8,6],[-8.6,6],[-9,3.8]];
  ground.add(footprint(boundary,.11),C.section,[0,-.08,0]); ground.add(footprint(boundary,.022),C.ground,[0,.03,0]);
  ground.add(footprint([[-1.8,-4.5],[1.8,-4.95],[3,-3.25],[.85,-2.15],[-1.1,-2.65]],.012),C.field,[0,.053,0]);
  for(let i=0;i<10;i++) ground.box([-.9+i*.32,.073,-3.65],[.025,.009,1.5],i%3?C.fieldDark:C.pavement,[0,.27,0]);
  ground.add(footprint([[6.7,4.4],[8.8,4.2],[8.8,5.8],[7.2,5.8]],.008),C.fieldDark,[0,.057,0]);
  ground.add(footprint([[-9,-6],[-7.25,-6],[-8,-4],[-8.1,-2.8],[-9,-2.4]],.13),"#c6d1bd",[0,.06,0]);
  for(let i=0;i<3;i++) ground.line([[-8.9+i*.25,.2,-5.8],[-8.25+i*.12,.2,-4.8],[-8.5+i*.14,.2,-3.7]],.009,"#9caf95");
  addRoad(ground,mainRoad,.56,true); addRoad(ground,arterial,.62,true); addRoad(ground,eastStreet,.31); addRoad(ground,northStreet,.28); addRoad(ground,eastSpine,.34,true);
  addRoad(ground,[[-7.9,-.85],[-6.8,1.85],[-5.4,2],[-3.6,2.3]],.18);
  addRoad(ground,[[-7.9,3.8],[-6,3.6],[-3.7,3.85]],.17); addRoad(ground,[[.8,.42],[1,2.65],[.8,4.05]],.2); addRoad(ground,[[6.3,-5.8],[6.9,-3]],.16);
  for(const [x,z,angle] of [[-3.2,4.55,-.12],[-3.78,4.1,1.25],[5.45,2.75,1.45]]) for(let i=0;i<6;i++) ground.box([x+(i-2.5)*.058,.087,z],[.032,.003,.35],C.marking,[0,angle,0]);
  terrain.add(ground.finish("DistrictGroundAndStreetNetwork"));

  const structures=new ArchitectureBatch(); buildings.forEach(spec=>addBuilding(structures,spec));
  // The long pale-roof landmark is a service complex in this illustrative, not surveyed, plan.
  structures.box([-.9,.15,3.23],[2.8,.19,1.4],C.pavement); structures.box([-1.1,.56,2.9],[2.3,.66,.67],C.wall);
  structures.box([-1.1,.915,2.9],[2.52,.07,.87],C.zinc);
  for(let i=0;i<20;i++) structures.box([-2.26+i*.122,.955,2.9],[.012,.009,.86],"#a5b2af");
  for(let i=0;i<6;i++) structures.box([-2.03+i*.35,.57,3.245],[.22,.25,.012],C.glass);
  structures.box([-.9,.3,3.82],[2.8,.06,.12],C.wall);
  for(const x of [-2.26,.47]) structures.box([x,.4,3.5],[.06,.42,.58],C.wall);
  for(const y of [.47,.61]) structures.box([-.9,y,3.86],[2.8,.018,.018],C.dark);
  for(let i=0;i<7;i++) structures.box([-2.25+i*.45,.445,3.86],[.016,.35,.016],C.dark);
  structures.box([-1.96,.27,4.04],[.5,.07,.4],C.section); structures.box([-1.96,.21,4.19],[.5,.05,.2],C.section);
  const buildingMesh=structures.finish(`DistrictBuildings_${buildings.length+1}`); terrain.add(buildingMesh,outline(buildingMesh,.23));

  const vegetation=new ArchitectureBatch();
  const trees=[[-8.3,-5.25],[-8.55,-4.45],[-8.65,-3.4],[-8.2,-2],[-8.4,.7],[-8.2,2.8],[-6.15,-5.65],[-5.6,-2.7],[-5,1.5],[-6.2,2],[-6.1,4.55],[-7.8,4.7],[-7.4,5.45],[-5.5,5.2],[-4.8,5.55],[-2.7,-4],[-1.85,-2.6],[2.4,-2.4],[3.5,-4.9],[4.1,-5.6],[5.2,-5.6],[7.8,-5.65],[8.6,-4],[8.5,-2.75],[5.85,-2.55],[4.35,-.7],[.75,2.65],[4.35,1.95],[5.7,4],[6.45,4.5],[6.3,5.45],[2.9,5.75]];
  trees.forEach(([x,z],i)=>addTree(vegetation,x,z,.5+(i%4)*.095,i*.7));
  for(let i=0;i<11;i++) vegetation.box([-.95+i*.28,.13,-2.65],[.2,.13,.13],i%2?C.leaf:C.green,[0,.16,0]);
  terrain.add(vegetation.finish("VegetationAndFieldBoundary"));
  const details=new ArchitectureBatch();
  for(const [x,z,angle,shade] of [[-3.4,-2,.16,C.wall],[-3.55,1.8,-.3,C.blue],[-1,4.47,1.43,C.wall],[3.8,3.65,1.43,C.red],[5.1,-3.1,-.08,C.zinc]] as const) {
    details.box([x,.135,z],[.14,.09,.32],shade,[0,angle,0]); details.box([x,.195,z],[.128,.075,.17],C.glass,[0,angle,0]);
  }
  for(const [x,z] of [[-4.1,3.75],[-3.8,-.75],[5.85,2.95],[3.9,-.1],[-2.35,4.55]]) {
    details.box([x,.38,z],[.021,.61,.021],C.dark); details.box([x+.08,.69,z],[.19,.016,.026],C.dark); details.box([x+.14,.676,z],[.075,.014,.036],C.wall);
  }
  addPerson(details,-3.97,3.73,C.dark,.08); addPerson(details,3.9,.64,C.red,.08); addPerson(details,-6.75,1.86,C.teal,.08); addPerson(details,-.75,-.42,C.dark,.08);
  terrain.add(details.finish("StreetFurnitureAndResidents"));
  const resident=new THREE.Group(); resident.name="ResidentRoot";
  const residentDetail=new ArchitectureBatch(); residentDetail.box([-5.6,.15,1.55],[.58,.13,.48],C.pavement); addPerson(residentDetail,-5.6,1.55,C.blue,.215);
  resident.add(residentDetail.finish("ResidentWithHandheldPhone")); terrain.add(resident);
  const coordinator=new THREE.Group(); coordinator.name="CoordinatorRoot";
  const commandDetail=new ArchitectureBatch(); addDesk(commandDetail,-1.45,3.45,.25); addDesk(commandDetail,-.75,3.45,.25);
  coordinator.add(commandDetail.finish("IntegratedServiceReviewDesks")); terrain.add(coordinator);
  const studio=new THREE.Group(); studio.name="StudioRoot";
  const studioDetail=new ArchitectureBatch(); addDesk(studioDetail,.03,3.45,.25,true); studio.add(studioDetail.finish("FourResearchEvidenceSheets")); terrain.add(studio);

  const floodBoundary:readonly GroundPoint[]=[[-4.4,5.8],[-4.5,3.45],[-3.82,2.3],[-3.65,.2],[-3.5,-1.8],[-2.15,-2.3],[-.65,-1.95],[.4,-1.4],[2.65,-1.55],[4.15,-2.5],[5,-3.25],[6.6,-2.5],[8.85,-2.55],[8.86,5.77],[6,5.96],[-3.4,5.96]];
  const floodBatch=new ArchitectureBatch(); floodBatch.add(footprint(floodBoundary,.012),C.water);
  const water=floodBatch.finish("IllustrativeInundationMask",new THREE.MeshStandardMaterial({vertexColors:true,roughness:.37,metalness:.14,transparent:true,opacity:.92,depthWrite:true}));
  water.castShadow=false; water.receiveShadow=true; water.renderOrder=1; terrain.add(water);
  const waterLines=new ArchitectureBatch();
  waterLines.line([[-4.39,.019,5.79],[-3.4,.019,5.94],[2,.019,5.94],[5.95,.019,5.94]],.012,C.foam);
  for(const [x,z,size] of [[-3.5,3.25,.3],[-2.4,4.6,.55],[.7,0,.5],[1.2,4.45,.6],[5.8,.05,.4],[7.6,2.8,.7],[3.9,-1.65,.4],[-2.6,-.2,.3],[4.8,4.5,.4],[7.3,-2.25,.45]]) {
    waterLines.line([[x-size,.019,z],[x,.019,z+.015],[x+size*.65,.019,z-.012]],.007,C.foam);
    waterLines.line([[x-size*.5,.019,z+.095],[x+size*.45,.019,z+.095]],.004,C.foam);
  }
  const waterDetails=waterLines.finish("QuietSurfaceTraces"); waterDetails.castShadow=false; terrain.add(waterDetails);
  const route=new ArchitectureBatch(); route.line([[-6.1,.24,1.86],[-5.4,.24,2],[-3.6,.24,2.3],[-3.9,.24,3],[-3.6,.24,4.6],[-2.1,.24,4.43],[-1.95,.24,4.01]],.045,C.teal);
  const primaryRoute=route.finish("DryAccessConnection"); primaryRoute.castShadow=false; terrain.add(primaryRoute);
  const disruption=new ArchitectureBatch(); disruption.line([[-6.1,.29,1.86],[-5.4,.29,2],[-3.75,.29,2.25]],.045,C.amber); disruption.line([[-2.1,.29,4.43],[-1.95,.29,4.01]],.04,C.teal);
  for(const sign of [-1,1]) disruption.line([[-3.93,.3,3.05+sign*.12],[-3.67,.3,3.3-sign*.12]],.025,C.amber);
  const scenarioRoute=disruption.finish("DisruptedAccessConnection"); scenarioRoute.castShadow=false; terrain.add(scenarioRoute);
  const marker=new THREE.Group(); marker.name="ReportAnchor_R017";
  const observation=new ArchitectureBatch(); observation.add(new THREE.TorusGeometry(.15,.011,4,32),C.amber,[-3.6,.285,4.6],[-Math.PI/2,0,0]);
  observation.box([-3.6,.4,4.6],[.016,.25,.016],C.amber); observation.add(new THREE.SphereGeometry(.055,10,8),C.amber,[-3.6,.55,4.6]);
  marker.add(observation.finish("SampleObservationLocation")); terrain.add(marker);
  const labels=options.labels===false?[]:[
    landmarkLabel("HOMES",[-6.1,1.28,.8],C.dark),
    landmarkLabel("SERVICE",[-.9,1.46,3.6],C.dark),
    landmarkLabel("INTERRUPTION",[-3.95,1.02,3.2],C.amber),
    landmarkLabel("REPORT",[-6.1,1.28,.8],C.teal),
    landmarkLabel("REVIEW",[-.9,1.46,3.6],C.teal),
    landmarkLabel("EVIDENCE",[-.9,1.46,3.6],C.teal),
  ];
  if(labels.length) terrain.add(...labels);
  for(const [name,point] of Object.entries(SCENE_ANCHORS)) {
    if(name==="TerrainRoot"||name==="ReportAnchor_R017") continue;
    const anchor=new THREE.Object3D(); anchor.name=name; anchor.position.set(point[0],point[1],point[2]); terrain.add(anchor);
  }
  world.add(terrain);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.ShadowMaterial({color:"#405652",opacity:.115}));
  floor.name="ContactShadowReceiver"; floor.rotation.x=-Math.PI/2; floor.position.y=-.092; floor.receiveShadow=true; world.add(floor);
  world.add(new THREE.AmbientLight("#ffffff",.9),new THREE.HemisphereLight("#eff7ff","#879184",1.15));
  const sun=new THREE.DirectionalLight("#fff8eb",2.45); sun.position.set(-10,18,9); sun.castShadow=true;
  sun.shadow.mapSize.set(2048,2048); sun.shadow.camera.left=-16; sun.shadow.camera.right=16; sun.shadow.camera.top=13; sun.shadow.camera.bottom=-13; sun.shadow.camera.near=.5; sun.shadow.camera.far=60;
  sun.shadow.normalBias=.018; sun.shadow.bias=-.00008; sun.shadow.radius=3; world.add(sun);
  return {world,terrain,resident,coordinator,studio,water,waterDetails,marker,primaryRoute,scenarioRoute,labels,floodAmount:0,
    dispose() {
      const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>();
      world.traverse(object=>{if(object instanceof THREE.Mesh||object instanceof THREE.LineSegments){geometries.add(object.geometry);for(const material of Array.isArray(object.material)?object.material:[object.material])materials.add(material);}});
      geometries.forEach(g=>g.dispose()); materials.forEach(m=>{if("map" in m&&m.map instanceof THREE.Texture)m.map.dispose();m.dispose();}); sun.shadow.map?.dispose();
    },
  };
}

/** Flood is presentation only. Report/task state never drains water or restores the route. */
export function applyStoryFrame(rig:TerrainRig,camera:THREE.OrthographicCamera,aspect:number,frame:StoryFrame,composition:"poster"|"reading-column"="poster") {
  rig.floodAmount=frame.floodAmount; rig.terrain.position.set(0,0,0); rig.terrain.scale.setScalar(1);
  rig.water.visible=frame.floodAmount>.001; rig.water.position.y=.075+frame.floodAmount*.145;
  (rig.water.material as THREE.MeshStandardMaterial).opacity=Math.min(.94,frame.floodAmount*1.8);
  rig.waterDetails.visible=frame.floodAmount>.7; rig.waterDetails.position.y=rig.water.position.y;
  rig.primaryRoute.visible=frame.chapterId!=="place"&&frame.routeState==="open";
  const accessOverlay=frame.routeState==="disrupted"&&frame.chapterId!=="flood";
  rig.scenarioRoute.visible=accessOverlay;
  rig.marker.visible=frame.floodAmount>.7&&(frame.sceneWeights.public>.05||frame.sceneWeights.command>.05||frame.sceneWeights.shared>.05);
  camera.position.set(...frame.camera.position); camera.lookAt(...frame.camera.target);
  const baseHeight=frame.camera.span/Math.max(1,aspect*.88);
  const readingWidth=frame.chapterId==="place"?35*frame.camera.span/21.5:35;
  const height=composition==="reading-column"?Math.max(baseHeight,readingWidth/aspect):baseHeight;
  const offset=composition==="reading-column"?-.17*height*aspect*frame.extractionAmount:0;
  camera.left=-height*aspect/2+offset; camera.right=height*aspect/2+offset; camera.top=height/2; camera.bottom=-height/2;
  camera.zoom=1; camera.near=.1; camera.far=120; camera.updateProjectionMatrix(); camera.updateMatrixWorld();
  rig.labels.forEach(label=>{
    label.quaternion.copy(camera.quaternion);
    const state:Record<string,boolean>={
      Annotation_HOMES:frame.chapterId!=="public", Annotation_SERVICE:frame.chapterId!=="command"&&frame.chapterId!=="studio",
      Annotation_INTERRUPTION:accessOverlay, Annotation_REPORT:frame.chapterId==="public",
      Annotation_REVIEW:frame.chapterId==="command", Annotation_EVIDENCE:frame.chapterId==="studio",
    };
    label.visible=state[label.name]??true;
  });
}

/** Derived from actual master anchors and camera, not duplicate test coordinates. */
export function getSceneTelemetry(rig:TerrainRig,camera:THREE.OrthographicCamera) {
  rig.world.updateMatrixWorld(true);
  const landmarks=Object.fromEntries(Object.keys(LANDMARK_ANCHORS).map(id=>{
    const p=rig.terrain.getObjectByName(id)!.getWorldPosition(new THREE.Vector3()).project(camera);
    return [id,{x:(p.x+1)/2,y:(1-p.y)/2}];
  }));
  return {floodAmount:rig.floodAmount,cameraSignature:[...camera.matrixWorld.elements,...camera.projectionMatrix.elements].map(v=>v.toFixed(6)).join(","),landmarks};
}
