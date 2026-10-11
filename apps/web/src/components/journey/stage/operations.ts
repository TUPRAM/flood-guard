import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { LAYOUT, terrainHeight } from "@/lib/journey/terrain";

import { PALETTE, box, normalise, paint, plasterTexture, seeded, woodFloorTexture, worldUV } from "./materials";

/**
 * The illustrative operations room: a modest planning office, not a sci-fi control room. Its window, desk, monitor,
 * seat, planning table and skylight keep the positions the camera choreography is built on; the room itself is
 * furnished and lit as a real workspace (timber floor, framed map board, task chair, desk with monitor, keyboard,
 * lamp and papers, shelving, whiteboard, clock).
 */

export interface OperationsBuilding {
  group: THREE.Group;
  /** World-space centre of the south window opening. */
  window: THREE.Vector3;
  /** Floor height inside. */
  floor: number;
  /** Desk monitor screen (unit plane, scaled to size), facing -x toward the responder. */
  monitorScreen: THREE.Mesh;
  /** Planning table display (unit plane, scaled), facing up. */
  tableScreen: THREE.Mesh;
  /** Where the seated responder sits (figure origin) and faces (+x). */
  seat: THREE.Vector3;
  skylight: THREE.Vector3;
  light: THREE.PointLight;
  /** Interior lights (switched off away from the building: every lit pixel in the scene pays for them). */
  lights: THREE.Light[];
  /** Outer footprint, for contact shadows. */
  footprint: { x: number; z: number; w: number; d: number };
  setMonitorSize(width: number, height: number): void;
  setTableSize(width: number, height: number): void;
  dispose(): void;
}

function keyboardTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 160;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#2a2f31";
  c.fillRect(0, 0, 512, 160);
  c.fillStyle = "#3d4346";
  const rows = [14, 14, 13, 12, 9];
  rows.forEach((count, row) => {
    const keyW = 480 / 14;
    for (let i = 0; i < count; i += 1) {
      const w = row === 4 && i === 4 ? keyW * 5.5 : keyW - 4;
      const x = 16 + i * keyW + (row === 4 && i > 4 ? keyW * 4.5 : 0) + row * 4;
      c.fillRect(x, 10 + row * 29, w, 25);
    }
  });
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function whiteboardTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 320;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#f7f6f2";
  c.fillRect(0, 0, 512, 320);
  c.strokeStyle = "#2f6f73";
  c.lineWidth = 4;
  c.beginPath();
  c.moveTo(40, 230);
  c.bezierCurveTo(120, 120, 220, 260, 300, 150);
  c.lineTo(460, 110);
  c.stroke();
  c.fillStyle = "#3b4648";
  c.font = "600 26px Inter, sans-serif";
  c.fillText("Review · coordinate", 40, 60);
  c.font = "400 20px Inter, sans-serif";
  for (let i = 0; i < 3; i += 1) c.fillRect(40, 90 + i * 24, 140 - i * 30, 3);
  c.strokeStyle = "#b5651d";
  c.lineWidth = 3;
  c.strokeRect(330, 180, 120, 80);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export function buildOperations(monitorTexture: THREE.Texture, tableTexture: THREE.Texture): OperationsBuilding {
  const group = new THREE.Group();
  group.name = "Operations";
  const { x: cx, z: cz } = LAYOUT.operations;
  const floor = terrainHeight(cx, cz) + 0.35;
  const W = 18, D = 12, H = 5.4, t = 0.3;
  const disposables: Array<{ dispose(): void }> = [];
  const own = <T extends { dispose(): void }>(item: T): T => {
    disposables.push(item);
    return item;
  };
  const plasterMap = own(plasterTexture());
  const floorMap = own(woodFloorTexture());
  const mat = {
    exterior: own(new THREE.MeshStandardMaterial({ color: "#ebe5d8", map: plasterMap, roughness: 0.92 })),
    interior: own(new THREE.MeshStandardMaterial({ color: "#ece7dd", roughness: 0.94 })),
    lining: own(new THREE.MeshStandardMaterial({ color: "#ebe5da", vertexColors: true, roughness: 0.94 })),
    ceiling: own(new THREE.MeshStandardMaterial({ color: "#dcd7cd", roughness: 0.95 })),
    floor: own(new THREE.MeshStandardMaterial({ map: floorMap, roughness: 0.52 })),
    plinth: own(new THREE.MeshStandardMaterial({ color: "#aea697", roughness: 0.92 })),
    frame: own(new THREE.MeshStandardMaterial({ color: "#3f4a4b", roughness: 0.42, metalness: 0.45 })),
    deskTop: own(new THREE.MeshStandardMaterial({ color: "#bfa27c", roughness: 0.5 })),
    steel: own(new THREE.MeshStandardMaterial({ color: "#2d3335", roughness: 0.38, metalness: 0.6 })),
    plastic: own(new THREE.MeshStandardMaterial({ color: "#1d2224", roughness: 0.42 })),
    fabric: own(new THREE.MeshStandardMaterial({ color: "#3a4244", roughness: 0.95 })),
    paper: own(new THREE.MeshStandardMaterial({ color: "#f4f1e8", roughness: 0.9 })),
    ceramic: own(new THREE.MeshStandardMaterial({ color: "#e9e4d8", roughness: 0.35 })),
    rug: own(new THREE.MeshStandardMaterial({ color: "#8d9a91", roughness: 1 })),
    colored: own(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75 })),
    panel: own(new THREE.MeshStandardMaterial({ color: "#fff8ea", emissive: "#fff1d6", emissiveIntensity: 1.1, roughness: 0.6 })),
  };
  const add = (geometry: THREE.BufferGeometry, material: THREE.Material, x: number, y: number, z: number, rotation?: [number, number, number], parent: THREE.Object3D = group) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(cx + x, floor + y, cz + z);
    if (rotation) mesh.rotation.set(...rotation);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  };
  const rbox = (w: number, h: number, d: number, r: number) => new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2 - 1e-4, h / 2 - 1e-4, d / 2 - 1e-4));

  // Shell: plinth, timber floor, walls (exterior plaster), skirting.
  add(worldUV(box(W + 1, 1.2, D + 1), 2.2), mat.plinth, 0, -0.6, 0);
  add(worldUV(box(W - t, 0.05, D - t), 2.4), mat.floor, 0, 0.02, 0);
  const wall = (w: number, h: number, d: number, x: number, y: number, z: number) => {
    const outer = add(worldUV(box(w, h, d), 2.2), mat.exterior, x, y, z);
    return outer;
  };
  wall(W, H, t, 0, H / 2, -D / 2);
  wall(t, H, D, W / 2, H / 2, 0);
  wall(t, H, D, -W / 2, H / 2, 0);
  const openW = 7.2, openH = 2.8, sill = 0.9;
  const sideW = (W - openW) / 2;
  wall(sideW, H, t, -(openW / 2 + sideW / 2), H / 2, D / 2);
  wall(sideW, H, t, openW / 2 + sideW / 2, H / 2, D / 2);
  wall(openW, sill, t, 0, sill / 2, D / 2);
  wall(openW, H - sill - openH, t, 0, H - (H - sill - openH) / 2, D / 2);
  // Interior faces in a calmer paint (thin linings so the exterior keeps its plaster), with soft occlusion baked
  // toward the floor, the ceiling and the room's corners so the room does not read flat.
  const lining = (w: number, d: number, x: number, z: number) => {
    const along = Math.max(w, d);
    const g = new THREE.BoxGeometry(w, H - 0.05, d, w > d ? 24 : 1, 10, w > d ? 1 : 24);
    const p = g.getAttribute("position") as THREE.BufferAttribute;
    const colors = new Float32Array(p.count * 3);
    for (let i = 0; i < p.count; i += 1) {
      const y = p.getY(i) + (H - 0.05) / 2;
      const a = (w > d ? p.getX(i) : p.getZ(i)) / (along / 2);
      const floorAO = THREE.MathUtils.smoothstep(y, 0, 1.1);
      const ceilingAO = 1 - 0.35 * THREE.MathUtils.smoothstep(y, H - 1.2, H);
      const cornerAO = 1 - 0.22 * THREE.MathUtils.smoothstep(Math.abs(a), 0.8, 1);
      const shade = (0.78 + 0.22 * floorAO) * ceilingAO * cornerAO;
      colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = shade;
    }
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return add(g, mat.lining, x, H / 2, z);
  };
  lining(W - 2 * t, 0.02, 0, -D / 2 + t / 2 + 0.011);
  lining(0.02, D - 2 * t, W / 2 - t / 2 - 0.011, 0);
  lining(0.02, D - 2 * t, -W / 2 + t / 2 + 0.011, 0);
  // A west window (glazed) for side light and a view out.
  add(box(0.06, 1.5, 2.6), new THREE.MeshStandardMaterial({ color: "#9fb3b5", roughness: 0.05, metalness: 0.1, transparent: true, opacity: 0.35 }), -W / 2 - 0.02, 2.05, -1.2);
  for (const [h, d, y, z] of [[0.07, 2.74, 2.83, -1.2], [0.07, 2.74, 1.27, -1.2], [1.5, 0.07, 2.05, -2.53], [1.5, 0.07, 2.05, 0.13], [1.5, 0.05, 2.05, -1.2]] as const) {
    add(box(t + 0.06, h, d), mat.frame, -W / 2, y, z);
  }
  for (const [w, d, x, z] of [[W - 2 * t, 0.03, 0, -D / 2 + t / 2 + 0.03], [0.03, D - 2 * t, W / 2 - t / 2 - 0.03, 0], [0.03, D - 2 * t, -W / 2 + t / 2 + 0.03, 0]] as const) {
    add(box(w, 0.1, d), mat.frame, x, 0.1, z);
  }
  // Window: aluminium frame, deep sill; left open (the camera passes through it).
  for (const [w, h, x, y] of [[openW + 0.16, 0.08, 0, sill + openH + 0.04], [openW + 0.16, 0.08, 0, sill - 0.04], [0.08, openH, -openW / 2 - 0.04, sill + openH / 2], [0.08, openH, openW / 2 + 0.04, sill + openH / 2]] as const) {
    add(box(w, h, t + 0.04), mat.frame, x, y, D / 2);
  }
  add(box(openW + 0.4, 0.06, 0.62), mat.plinth, 0, sill - 0.08, D / 2 + 0.12);
  // Entrance door with a small canopy, beside the window.
  add(box(1.1, 2.2, 0.06), new THREE.MeshStandardMaterial({ color: PALETTE.wood, roughness: 0.6 }), -6.4, 1.1, D / 2 + t / 2 + 0.02);
  add(box(1.3, 0.08, 0.06), mat.frame, -6.4, 2.24, D / 2 + t / 2 + 0.03);
  add(box(1.8, 0.1, 1.0), mat.plinth, -6.4, 2.6, D / 2 + 0.6);
  add(box(1.6, 0.18, 1.2), mat.plinth, -6.4, -0.09, D / 2 + 0.9);

  // Roof slabs (light underside) around a skylight above the planning table; parapet; a rooftop water tank.
  const sky = { x: -1.5, z: 0.5, w: 5.2, d: 3.8 };
  const roofY = H + 0.15;
  add(box(W + 0.6, 0.3, (D + 0.6) / 2 - sky.d / 2 + sky.z), mat.ceiling, 0, roofY, -(D + 0.6) / 4 - sky.d / 4 + sky.z / 2);
  add(box(W + 0.6, 0.3, (D + 0.6) / 2 - sky.d / 2 - sky.z), mat.ceiling, 0, roofY, (D + 0.6) / 4 + sky.d / 4 + sky.z / 2);
  const leftW = (W + 0.6) / 2 + sky.x - sky.w / 2, rightW = (W + 0.6) / 2 - sky.x - sky.w / 2;
  add(box(leftW, 0.3, sky.d), mat.ceiling, -(W + 0.6) / 2 + leftW / 2, roofY, sky.z);
  add(box(rightW, 0.3, sky.d), mat.ceiling, (W + 0.6) / 2 - rightW / 2, roofY, sky.z);
  for (const [w, d, x, z] of [[W + 0.6, 0.2, 0, -(D + 0.6) / 2 + 0.1], [W + 0.6, 0.2, 0, (D + 0.6) / 2 - 0.1], [0.2, D + 0.6, -(W + 0.6) / 2 + 0.1, 0], [0.2, D + 0.6, (W + 0.6) / 2 - 0.1, 0]] as const) {
    add(box(w, 0.42, d), mat.exterior, x, roofY + 0.36, z);
  }
  for (const [w, d, x, z] of [[sky.w + 0.3, 0.15, sky.x, sky.z - sky.d / 2 - 0.075], [sky.w + 0.3, 0.15, sky.x, sky.z + sky.d / 2 + 0.075], [0.15, sky.d, sky.x - sky.w / 2 - 0.075, sky.z], [0.15, sky.d, sky.x + sky.w / 2 + 0.075, sky.z]] as const) {
    add(box(w, 0.28, d), mat.frame, x, roofY + 0.29, z);
  }
  add(new THREE.CylinderGeometry(0.6, 0.6, 1.4, 20), new THREE.MeshStandardMaterial({ color: PALETTE.metal, roughness: 0.32, metalness: 0.75 }), W / 2 - 1.8, roofY + 0.9, -D / 2 + 1.8);
  for (const lx of [-5, 0, 5]) for (const lz of [-3.2, 3.4]) add(box(1.5, 0.05, 0.5), mat.panel, lx, H - 0.03, lz);

  // Back wall: framed map board; a rug under the planning table.
  const boardMap = add(new THREE.PlaneGeometry(5.6, 1.9), new THREE.MeshBasicMaterial({ map: tableTexture, toneMapped: false }), -2, 2.4, -D / 2 + 0.2);
  boardMap.castShadow = false;
  for (const [w, h, x, y] of [[5.8, 0.08, -2, 3.39], [5.8, 0.08, -2, 1.41], [0.08, 2.06, -4.86, 2.4], [0.08, 2.06, 0.86, 2.4]] as const) {
    add(box(w, h, 0.05), mat.frame, x, y, -D / 2 + 0.2);
  }
  add(box(4.6, 0.012, 3.4), mat.rug, sky.x, 0.05, sky.z);

  // Desk along the east wall: top, steel frame, modesty panel, drawer pedestal.
  const deskX = W / 2 - 1.2, deskZ = 1.6;
  add(rbox(1.0, 0.035, 2.4, 0.01), mat.deskTop, deskX, 0.7625, deskZ);
  for (const dz of [-1.12, 1.12]) {
    for (const dx of [-0.42, 0.42]) add(box(0.05, 0.745, 0.05), mat.steel, deskX + dx, 0.3725, deskZ + dz);
    add(box(0.9, 0.04, 0.06), mat.steel, deskX, 0.02, deskZ + dz);
    add(box(0.9, 0.05, 0.05), mat.steel, deskX, 0.72, deskZ + dz);
  }
  add(box(0.02, 0.38, 2.2), mat.steel, deskX + 0.44, 0.5, deskZ);
  add(rbox(0.5, 0.6, 0.42, 0.01), mat.interior, deskX + 0.18, 0.31, deskZ + 0.82);
  for (const y of [0.18, 0.42]) add(box(0.005, 0.005, 0.3), mat.frame, deskX - 0.07, y, deskZ + 0.82);

  // Monitor (rebuilt to the real page's aspect): slim bezel, back housing, stand.
  const monitor = new THREE.Group();
  monitor.position.set(cx + deskX + 0.12, floor + 1.2, cz + deskZ);
  monitor.rotation.y = -Math.PI / 2; // local +z faces -x (toward the responder)
  group.add(monitor);
  const monitorParts = new THREE.Group();
  monitor.add(monitorParts);
  const monitorScreen = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: monitorTexture, toneMapped: false }));
  monitor.add(monitorScreen);

  // Keyboard, mouse, mug, notepad, lamp, papers.
  const keys = own(keyboardTexture());
  add(rbox(0.16, 0.016, 0.44, 0.004), new THREE.MeshStandardMaterial({ color: "#2a2f31", roughness: 0.5 }), deskX - 0.25, 0.789, deskZ);
  const keyTop = add(new THREE.PlaneGeometry(0.42, 0.14), new THREE.MeshStandardMaterial({ map: keys, roughness: 0.6 }), deskX - 0.25, 0.7975, deskZ, [-Math.PI / 2, 0, Math.PI / 2]);
  keyTop.castShadow = false;
  const mouse = add(new THREE.CapsuleGeometry(0.028, 0.05, 4, 10), mat.plastic, deskX - 0.24, 0.792, deskZ + 0.36, [0, 0, Math.PI / 2]);
  mouse.scale.set(0.5, 1, 1);
  add(new THREE.CylinderGeometry(0.04, 0.036, 0.095, 20), mat.ceramic, deskX - 0.02, 0.83, deskZ - 0.72);
  add(new THREE.TorusGeometry(0.025, 0.007, 8, 16, Math.PI), mat.ceramic, deskX - 0.02, 0.835, deskZ - 0.762, [0, Math.PI / 2, -Math.PI / 2]);
  add(box(0.22, 0.008, 0.3), mat.paper, deskX - 0.12, 0.786, deskZ - 0.42, [0, 0.18, 0]);
  add(new THREE.CylinderGeometry(0.004, 0.004, 0.14, 6), mat.steel, deskX - 0.1, 0.792, deskZ - 0.42, [Math.PI / 2, 0.4, 0]);
  for (let i = 0; i < 5; i += 1) add(box(0.21, 0.004, 0.297), mat.paper, deskX + 0.12, 0.784 + i * 0.004, deskZ + 0.72, [0, 0.05 * i, 0]);
  // Desk lamp: base, two arms through explicit joints, a shade pointing at the desk.
  const rod = (a: THREE.Vector3, b: THREE.Vector3, r: number) => {
    const g = new THREE.CylinderGeometry(r, r, a.distanceTo(b), 8);
    g.translate(0, a.distanceTo(b) / 2, 0);
    g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize()));
    return add(g, mat.steel, a.x, a.y, a.z);
  };
  const lampBase = new THREE.Vector3(deskX + 0.32, 0.8, deskZ - 1.0);
  const lampElbow = new THREE.Vector3(deskX + 0.36, 1.18, deskZ - 0.98);
  const lampHead = new THREE.Vector3(deskX + 0.06, 1.24, deskZ - 0.92);
  add(new THREE.CylinderGeometry(0.07, 0.08, 0.02, 20), mat.steel, lampBase.x, 0.79, lampBase.z);
  rod(lampBase, lampElbow, 0.009);
  rod(lampElbow, lampHead, 0.008);
  add(new THREE.SphereGeometry(0.016, 10, 8), mat.steel, lampElbow.x, lampElbow.y, lampElbow.z);
  add(new THREE.ConeGeometry(0.07, 0.11, 20, 1, true), mat.steel, lampHead.x - 0.02, lampHead.y - 0.05, lampHead.z, [0, 0, -0.35]);

  // Task chair: five-star base with castors, gas column, cushioned seat and backrest, armrests.
  const chairX = deskX - 0.86;
  for (let i = 0; i < 5; i += 1) {
    const a = (i / 5) * Math.PI * 2;
    add(box(0.3, 0.035, 0.05), mat.steel, chairX + Math.cos(a) * 0.15, 0.075, deskZ + Math.sin(a) * 0.15, [0, -a, 0]);
    add(new THREE.SphereGeometry(0.028, 10, 8), mat.plastic, chairX + Math.cos(a) * 0.29, 0.028, deskZ + Math.sin(a) * 0.29);
  }
  add(new THREE.CylinderGeometry(0.026, 0.03, 0.34, 12), mat.steel, chairX, 0.26, deskZ);
  add(rbox(0.5, 0.08, 0.48, 0.035), mat.fabric, chairX, 0.47, deskZ);
  add(box(0.04, 0.32, 0.06), mat.steel, chairX - 0.27, 0.62, deskZ);
  add(rbox(0.07, 0.56, 0.46, 0.03), mat.fabric, chairX - 0.29, 0.92, deskZ, [0, 0, 0.12]);
  for (const side of [-1, 1]) {
    add(box(0.04, 0.2, 0.04), mat.steel, chairX - 0.02, 0.6, deskZ + side * 0.27);
    add(rbox(0.28, 0.035, 0.07, 0.015), mat.plastic, chairX + 0.02, 0.7, deskZ + side * 0.27);
  }

  // Planning table (rebuilt to the real page's aspect): framed display on a two-leg base.
  const tableParts = new THREE.Group();
  group.add(tableParts);
  const tableScreen = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: tableTexture, toneMapped: false }));
  tableScreen.rotation.x = -Math.PI / 2; // face up, local +y → world -z (north up)
  tableScreen.position.set(cx + sky.x, floor + 0.925, cz + sky.z);
  group.add(tableScreen);

  // West wall: shelving with binders and boxes; a second workstation with a laptop; a plant; whiteboard and clock.
  const random = seeded(77);
  const shelf: THREE.BufferGeometry[] = [];
  const shelfX = -W / 2 + t / 2 + 0.25;
  const put = (g: THREE.BufferGeometry, color: THREE.Color, x: number, y: number, z: number) => {
    const n = normalise(g);
    paint(n, color);
    n.translate(cx + x, floor + y, cz + z);
    shelf.push(n);
  };
  const shelfColor = new THREE.Color("#c9b79a");
  for (const z0 of [1.4, 3.9]) {
    for (const y of [0.05, 0.6, 1.15, 1.7, 2.2]) put(box(0.42, 0.03, 2.2), shelfColor, shelfX, y, z0);
    for (const dz of [-1.1, 1.1]) put(box(0.42, 2.2, 0.03), shelfColor, shelfX, 1.1, z0 + dz);
    for (const y of [0.08, 0.63, 1.18, 1.73]) {
      let z = z0 - 1.05;
      while (z < z0 + 1.0) {
        const w = 0.05 + random() * 0.04, h = 0.28 + random() * 0.12;
        const tone = [new THREE.Color("#4d7d7b"), new THREE.Color("#e6dccb"), new THREE.Color("#8b8f88"), new THREE.Color("#b88a4a"), new THREE.Color("#5a6466")][Math.floor(random() * 5)];
        if (random() < 0.85) put(box(0.3, h, w), tone, shelfX, y + h / 2, z + w / 2);
        z += w + 0.004 + (random() < 0.1 ? 0.15 : 0);
      }
    }
  }
  const secondX = -6.2, secondZ = -3.6;
  put(box(2.4, 0.04, 1.0), new THREE.Color("#bfa27c"), secondX, 0.76, secondZ);
  for (const [dx, dz] of [[-1.1, -0.42], [1.1, -0.42], [-1.1, 0.42], [1.1, 0.42]]) put(box(0.05, 0.74, 0.05), new THREE.Color("#2d3335"), secondX + dx, 0.37, secondZ + dz);
  put(box(0.34, 0.012, 0.24), new THREE.Color("#2b3033"), secondX - 0.2, 0.787, secondZ + 0.05);
  const lid = normalise(box(0.34, 0.24, 0.01));
  paint(lid, new THREE.Color("#2b3033"));
  lid.rotateX(-0.32);
  lid.translate(cx + secondX - 0.2, floor + 0.9, cz + secondZ - 0.1);
  shelf.push(lid);
  put(box(0.5, 0.03, 0.5), new THREE.Color("#3a4244"), secondX + 0.1, 0.47, secondZ + 0.8);
  put(box(0.5, 0.5, 0.05), new THREE.Color("#3a4244"), secondX + 0.1, 0.75, secondZ + 1.05);
  put(new THREE.CylinderGeometry(0.2, 0.16, 0.42, 16), new THREE.Color("#b8653f"), W / 2 - 0.6, 0.21, D / 2 - 1.1);
  const shelfMesh = new THREE.Mesh(mergeGeometries(shelf)!, mat.colored);
  shelf.forEach((g) => g.dispose());
  shelfMesh.castShadow = shelfMesh.receiveShadow = true;
  group.add(shelfMesh);
  const leaves = new THREE.MeshStandardMaterial({ color: "#5f7d45", roughness: 0.8 });
  own(leaves);
  for (let i = 0; i < 7; i += 1) {
    const a = (i / 7) * Math.PI * 2;
    const leaf = add(new THREE.SphereGeometry(0.2, 10, 8), leaves, W / 2 - 0.6 + Math.cos(a) * 0.14, 0.75 + (i % 3) * 0.12, D / 2 - 1.1 + Math.sin(a) * 0.14, [0.6 * Math.sin(a), a, 0.6 * Math.cos(a)]);
    leaf.scale.set(0.45, 1.2, 0.2);
  }
  const board = add(new THREE.PlaneGeometry(1.6, 1.0), new THREE.MeshStandardMaterial({ map: own(whiteboardTexture()), roughness: 0.3 }), W / 2 - t / 2 - 0.03, 2.0, -2.2, [0, -Math.PI / 2, 0]);
  board.castShadow = false;
  for (const [h, d, y, z] of [[0.04, 1.66, 2.52, -2.2], [0.04, 1.66, 1.48, -2.2], [1.04, 0.04, 2.0, -3.03], [1.04, 0.04, 2.0, -1.37]] as const) {
    add(box(0.03, h, d), mat.frame, W / 2 - t / 2 - 0.03, y, z);
  }
  const clock = add(new THREE.CylinderGeometry(0.17, 0.17, 0.03, 32), mat.ceramic, W / 2 - t / 2 - 0.03, 3.25, deskZ, [0, 0, Math.PI / 2]);
  clock.castShadow = false;
  add(new THREE.TorusGeometry(0.17, 0.012, 8, 32), mat.frame, W / 2 - t / 2 - 0.035, 3.25, deskZ, [0, Math.PI / 2, 0]);
  add(box(0.005, 0.12, 0.012), mat.plastic, W / 2 - t / 2 - 0.05, 3.29, deskZ, [0.5, 0, 0]);
  add(box(0.005, 0.08, 0.012), mat.plastic, W / 2 - t / 2 - 0.05, 3.25, deskZ + 0.03, [-1.2, 0, 0]);

  // Warm interior light (the ceiling panels are emissive).
  const light = new THREE.PointLight("#ffe2bd", 20, 18, 1.4);
  light.position.set(cx, floor + 3.8, cz + 0.5);
  group.add(light);
  const fill = new THREE.PointLight("#fff0dc", 5, 7, 1.6);
  fill.position.set(cx + deskX - 1.6, floor + 2.6, cz + deskZ + 0.6);
  group.add(fill);

  // Merge every static part into one mesh per material (about 150 parts become about 20 draw calls, in both the main
  // pass and the shadow pass). The monitor and table parts stay separate: they are rebuilt to the pages' aspects.
  const buckets = new Map<string, { material: THREE.Material; cast: boolean; parts: THREE.BufferGeometry[] }>();
  for (const child of [...group.children]) {
    if (!(child instanceof THREE.Mesh) || child === tableScreen) continue;
    child.updateMatrix();
    const part = normalise(child.geometry.clone());
    part.applyMatrix4(child.matrix);
    const material = child.material as THREE.Material;
    const key = `${material.uuid}:${child.castShadow}`;
    if (!buckets.has(key)) buckets.set(key, { material, cast: child.castShadow, parts: [] });
    buckets.get(key)!.parts.push(part);
    group.remove(child);
    child.geometry.dispose();
  }
  buckets.forEach(({ material, cast, parts }) => {
    const merged = new THREE.Mesh(mergeGeometries(parts)!, material);
    parts.forEach((part) => part.dispose());
    merged.castShadow = cast;
    merged.receiveShadow = true;
    group.add(merged);
    disposables.push(merged.geometry, material);
  });

  const clearGroup = (g: THREE.Group) => {
    g.children.forEach((child) => (child as THREE.Mesh).geometry?.dispose());
    g.clear();
  };

  return {
    group,
    window: new THREE.Vector3(cx, floor + sill + openH / 2, cz + D / 2),
    floor,
    monitorScreen,
    tableScreen,
    seat: new THREE.Vector3(cx + deskX - 0.82, floor, cz + deskZ),
    skylight: new THREE.Vector3(cx + sky.x, floor + roofY, cz + sky.z),
    light,
    lights: [light, fill],
    footprint: { x: cx, z: cz, w: W + 1, d: D + 1 },
    setMonitorSize(w: number, h: number) {
      clearGroup(monitorParts);
      const part = (geometry: THREE.BufferGeometry, material: THREE.Material, x: number, y: number, z: number, rx = 0) => {
        const m = new THREE.Mesh(geometry, material);
        m.position.set(x, y, z);
        m.rotation.x = rx;
        m.castShadow = m.receiveShadow = true;
        monitorParts.add(m);
        return m;
      };
      part(rbox(w + 0.022, h + 0.022, 0.016, 0.005), mat.plastic, 0, 0, 0);
      part(rbox(w * 0.72, h * 0.62, 0.036, 0.012), mat.plastic, 0, -h * 0.02, -0.022);
      const neckTop = -0.02, neckBottom = -(1.2 - 0.79);
      part(box(0.05, neckTop - neckBottom, 0.024), mat.steel, 0, (neckTop + neckBottom) / 2, -0.05);
      part(rbox(0.24, 0.012, 0.19, 0.005), mat.steel, 0, neckBottom + 0.006, -0.05);
      monitorScreen.scale.set(w, h, 1);
      monitorScreen.position.set(0, 0, 0.0085);
    },
    setTableSize(w: number, h: number) {
      clearGroup(tableParts);
      const part = (geometry: THREE.BufferGeometry, material: THREE.Material, x: number, y: number, z: number) => {
        const m = new THREE.Mesh(geometry, material);
        m.position.set(cx + sky.x + x, floor + y, cz + sky.z + z);
        m.castShadow = m.receiveShadow = true;
        tableParts.add(m);
        return m;
      };
      part(rbox(w + 0.26, 0.11, h + 0.26, 0.03), mat.steel, 0, 0.865, 0);
      for (const side of [-1, 1]) {
        part(box(0.12, 0.8, h * 0.62), mat.steel, side * (w / 2 - 0.35), 0.4, 0);
        part(box(0.5, 0.04, h * 0.7), mat.steel, side * (w / 2 - 0.35), 0.02, 0);
      }
      part(box(w - 0.7, 0.08, 0.08), mat.steel, 0, 0.25, 0);
      tableScreen.scale.set(w, h, 1);
    },
    dispose() {
      clearGroup(monitorParts);
      clearGroup(tableParts);
      disposables.forEach((d) => d.dispose());
    },
  };
}
