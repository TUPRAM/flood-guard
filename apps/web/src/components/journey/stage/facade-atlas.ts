import * as THREE from "three";

import { seeded } from "./materials";

/**
 * A painted atlas of facade bays for the town's buildings, in the manner of a northern Thai town: shophouse fronts
 * with roller shutters, open shops and sign bands; upper floors with grilles, balconies and air conditioners; house
 * walls; plastered side walls; market sheds; temple and government fronts; school corridors and sheds.
 *
 * Each tile is one bay of one storey. The walls' shader picks a row by facade type and floor, a column by a hash of
 * the bay, and repeats the tile along the wall. Two textures share the layout:
 * - colour (sRGB);
 * - mask: R = how much the building's plaster tint applies (1 on plaster, 0 on glass, metal and signs), G = where a
 *   lit interior shows at night, B = where the wall is glass or metal (glossy when wet).
 *
 * Nothing here is drawn from the real buildings: the outlines are real, the looks are illustrative. Signs carry no
 * words, so they name no real shop.
 */

export const ATLAS_TILES = 8;
const TILE = 256;
const SIZE = ATLAS_TILES * TILE;

/** Rows of the atlas (top to bottom on the canvas). */
export const ATLAS_ROW = {
  shopGround: 0,
  shopUpper: 1,
  houseGround: 2,
  houseUpper: 3,
  side: 4,
  large: 5,
  /** Columns 0-3 temple, 4-7 government. */
  civic: 6,
  /** Columns 0-3 school, 4-7 shed. */
  utility: 7,
} as const;

type Ctx = CanvasRenderingContext2D;

interface Painter {
  color: Ctx;
  mask: Ctx;
  random: () => number;
}

/** Fill a rectangle on both layers: colour, and mask (tint, glow, gloss as 0..1). */
function rect(p: Painter, x: number, y: number, w: number, h: number, color: string, tint = 0, glow = 0, gloss = 0): void {
  p.color.fillStyle = color;
  p.color.fillRect(x, y, w, h);
  p.mask.fillStyle = `rgb(${Math.round(tint * 255)},${Math.round(glow * 255)},${Math.round(gloss * 255)})`;
  p.mask.fillRect(x, y, w, h);
}

function plaster(p: Painter, x: number, y: number, w: number, h: number, base = 232): void {
  rect(p, x, y, w, h, `rgb(${base},${base},${base})`, 1);
  // Soft rain streaks and a darker band of splash at the foot of the wall.
  const g = p.color;
  for (let i = 0; i < 7; i += 1) {
    const sx = x + p.random() * w;
    const len = h * (0.2 + p.random() * 0.5);
    const grad = g.createLinearGradient(0, y, 0, y + len);
    grad.addColorStop(0, "rgba(90,90,85,0.10)");
    grad.addColorStop(1, "rgba(90,90,85,0)");
    g.fillStyle = grad;
    g.fillRect(sx, y, 3 + p.random() * 6, len);
  }
}

function footGrime(p: Painter, x: number, y: number, w: number, h: number): void {
  const g = p.color;
  const grad = g.createLinearGradient(0, y + h * 0.82, 0, y + h);
  grad.addColorStop(0, "rgba(70,62,50,0)");
  grad.addColorStop(1, "rgba(70,62,50,0.22)");
  g.fillStyle = grad;
  g.fillRect(x, y + h * 0.82, w, h * 0.18);
}

/** Horizontal corrugations of a roller shutter. */
function shutter(p: Painter, x: number, y: number, w: number, h: number, base: [number, number, number], open = 0): void {
  const closedH = h * (1 - open);
  if (open > 0) interior(p, x, y + closedH, w, h - closedH, "shop");
  for (let row = 0; row < closedH; row += 6) {
    const shade = row % 12 === 0 ? 1.08 : 0.9;
    rect(p, x, y + row, w, Math.min(6, closedH - row), `rgb(${Math.round(base[0] * shade)},${Math.round(base[1] * shade)},${Math.round(base[2] * shade)})`, 0, 0, 0.8);
  }
  rect(p, x, y + closedH - 6, w, 6, "rgb(70,72,72)", 0, 0, 0.6);
  // Guide rails.
  rect(p, x - 4, y, 4, h, "rgb(110,112,110)", 0, 0, 0.7);
  rect(p, x + w, y, 4, h, "rgb(110,112,110)", 0, 0, 0.7);
}

const GOODS = ["#d9534f", "#f0ad4e", "#5bc0de", "#5cb85c", "#e8e1cf", "#9b59b6", "#f7dc6f", "#e67e22", "#3b7dd8"];

/** A dark, lit-at-night interior: shelves of goods, tables, or a garage. */
function interior(p: Painter, x: number, y: number, w: number, h: number, kind: "shop" | "food" | "garage"): void {
  rect(p, x, y, w, h, "rgb(42,40,36)", 0, 1);
  if (kind === "shop") {
    for (let shelf = 0; shelf < 4; shelf += 1) {
      const sy = y + h * 0.15 + shelf * h * 0.18;
      rect(p, x + 6, sy + h * 0.13, w - 12, 3, "rgb(90,80,66)", 0, 0.6);
      for (let item = x + 8; item < x + w - 12; item += 9 + p.random() * 6) {
        const ih = h * (0.06 + p.random() * 0.06);
        rect(p, item, sy + h * 0.13 - ih, 6 + p.random() * 4, ih, GOODS[Math.floor(p.random() * GOODS.length)], 0, 0.7);
      }
    }
  } else if (kind === "food") {
    rect(p, x, y + h * 0.1, w, h * 0.08, "rgb(220,200,150)", 0, 1); // menu board
    for (let t = 0; t < 3; t += 1) {
      const tx = x + 12 + t * (w / 3);
      rect(p, tx, y + h * 0.62, w / 4, 5, "rgb(200,60,50)", 0, 0.5); // red stools and tables
      rect(p, tx + w / 10, y + h * 0.66, 4, h * 0.3, "rgb(150,150,150)", 0, 0.3);
    }
  } else {
    rect(p, x + w * 0.2, y + h * 0.55, w * 0.55, h * 0.25, "rgb(25,25,25)", 0, 0.2); // a motorbike's bulk
    for (const cx of [x + w * 0.27, x + w * 0.68]) {
      p.color.beginPath();
      p.color.arc(cx, y + h * 0.83, h * 0.09, 0, Math.PI * 2);
      p.color.fillStyle = "rgb(15,15,15)";
      p.color.fill();
    }
  }
}

/** A sign band above a shop front: coloured board with abstract lettering bars (no words). */
function signBand(p: Painter, x: number, y: number, w: number, h: number): void {
  const palette = ["#c0392b", "#1f6aa5", "#f2c94c", "#27ae60", "#ffffff", "#e67e22", "#8e44ad", "#16a085"];
  const bg = palette[Math.floor(p.random() * palette.length)];
  rect(p, x + 2, y, w - 4, h, bg, 0, 0.35);
  const fg = bg === "#ffffff" || bg === "#f2c94c" ? "#2b2b2b" : "#ffffff";
  let cx = x + 12;
  while (cx < x + w - 24) {
    const bw = 8 + p.random() * 26;
    rect(p, cx, y + h * 0.32, Math.min(bw, x + w - 16 - cx), h * (0.22 + p.random() * 0.18), fg, 0, 0.35);
    cx += bw + 5 + p.random() * 8;
  }
}

/** A window with a frame, glass and optionally a decorative steel grille. */
function windowPane(p: Painter, x: number, y: number, w: number, h: number, options: { frame?: string; grille?: boolean; curtain?: boolean; louvre?: boolean } = {}): void {
  const frame = options.frame ?? "#e9e5dc";
  rect(p, x - 5, y - 5, w + 10, h + 10, frame, 0.2, 0, 0.3);
  rect(p, x, y, w, h, "rgb(54,66,70)", 0, 1, 1);
  if (options.louvre) for (let ly = y + 4; ly < y + h; ly += 7) rect(p, x, ly, w, 3, "rgb(150,160,160)", 0, 0.5, 0.8);
  if (options.curtain) rect(p, x + w * 0.55, y, w * 0.45, h, "rgb(210,190,160)", 0, 0.8);
  rect(p, x + w / 2 - 2, y, 4, h, frame, 0.2, 0, 0.3);
  rect(p, x, y + h * 0.45, w, 3, frame, 0.2, 0, 0.3);
  if (options.grille) {
    p.color.strokeStyle = "rgba(40,40,40,0.9)";
    p.color.lineWidth = 2;
    for (let gx = x + 8; gx < x + w; gx += 12) {
      p.color.beginPath();
      p.color.moveTo(gx, y);
      p.color.lineTo(gx, y + h);
      p.color.stroke();
    }
    for (let gy = y + 14; gy < y + h; gy += 26) {
      p.color.beginPath();
      p.color.moveTo(x, gy);
      p.color.quadraticCurveTo(x + w / 2, gy - 8, x + w, gy);
      p.color.stroke();
    }
  }
  // Sill.
  rect(p, x - 8, y + h + 5, w + 16, 6, "rgb(205,200,190)", 0.3);
}

function door(p: Painter, x: number, y: number, w: number, h: number, wood = "#7a5233"): void {
  rect(p, x - 5, y - 5, w + 10, h + 5, "#e6e0d4", 0.2);
  rect(p, x, y, w, h, wood, 0, 0, 0.2);
  rect(p, x + w * 0.15, y + h * 0.1, w * 0.7, h * 0.35, "rgba(0,0,0,0.15)", 0, 0.4);
  rect(p, x + w * 0.78, y + h * 0.5, 5, 10, "#c9b37a", 0, 0, 0.8);
}

function balcony(p: Painter, x: number, y: number, w: number, h: number): void {
  windowPane(p, x + w * 0.12, y + h * 0.08, w * 0.76, h * 0.62, { curtain: p.random() < 0.6 });
  rect(p, x, y + h * 0.68, w, 5, "rgb(60,62,60)", 0, 0, 0.6);
  for (let rx = x + 4; rx < x + w; rx += 10) rect(p, rx, y + h * 0.68, 2, h * 0.28, "rgb(60,62,60)", 0, 0, 0.6);
  rect(p, x, y + h * 0.95, w, 6, "rgb(150,148,142)", 0.3);
  // Pots with plants, and sometimes laundry.
  for (let i = 0; i < 3; i += 1) {
    const px = x + 14 + p.random() * (w - 40);
    rect(p, px, y + h * 0.84, 14, 12, "#b5653d", 0);
    p.color.fillStyle = "#4f7a3a";
    p.color.beginPath();
    p.color.arc(px + 7, y + h * 0.82, 11, 0, Math.PI * 2);
    p.color.fill();
  }
  if (p.random() < 0.5) {
    p.color.strokeStyle = "rgba(60,60,60,0.8)";
    p.color.beginPath();
    p.color.moveTo(x + 6, y + h * 0.3);
    p.color.lineTo(x + w - 6, y + h * 0.3);
    p.color.stroke();
    for (let lx = x + 14; lx < x + w - 20; lx += 22) rect(p, lx, y + h * 0.3, 14, 22 + p.random() * 18, GOODS[Math.floor(p.random() * GOODS.length)], 0);
  }
}

function acUnit(p: Painter, x: number, y: number): void {
  rect(p, x, y, 46, 32, "rgb(222,222,216)", 0, 0, 0.5);
  p.color.strokeStyle = "rgba(120,120,120,0.9)";
  p.color.beginPath();
  p.color.arc(x + 30, y + 16, 11, 0, Math.PI * 2);
  p.color.stroke();
}

function corrugated(p: Painter, x: number, y: number, w: number, h: number, base: [number, number, number], vertical = true): void {
  const step = 8;
  for (let i = 0; i < (vertical ? w : h); i += step) {
    const shade = (i / step) % 2 === 0 ? 1.06 : 0.9;
    const c = `rgb(${Math.round(base[0] * shade)},${Math.round(base[1] * shade)},${Math.round(base[2] * shade)})`;
    if (vertical) rect(p, x + i, y, step, h, c, 0, 0, 0.9);
    else rect(p, x, y + i, w, step, c, 0, 0, 0.9);
  }
  // Rust streaks.
  for (let i = 0; i < 5; i += 1) rect(p, x + p.random() * w, y + p.random() * h * 0.4, 3, h * (0.2 + p.random() * 0.4), "rgba(140,80,40,0.35)", 0);
}

function paintTile(p: Painter, row: number, col: number): void {
  const x = col * TILE, y = row * TILE;
  const random = p.random;
  p.color.save();
  p.mask.save();
  p.color.beginPath();
  p.color.rect(x, y, TILE, TILE);
  p.color.clip();
  p.mask.beginPath();
  p.mask.rect(x, y, TILE, TILE);
  p.mask.clip();
  switch (row) {
    case ATLAS_ROW.shopGround: {
      plaster(p, x, y, TILE, TILE, 228);
      signBand(p, x, y + 10, TILE, 46);
      const fx = x + 10, fy = y + 66, fw = TILE - 20, fh = TILE - 72;
      const variant = col;
      if (variant <= 1 || variant === 6) shutter(p, fx, fy, fw, fh, variant === 0 ? [150, 152, 150] : variant === 1 ? [96, 132, 112] : [168, 150, 120]);
      else if (variant === 2) shutter(p, fx, fy, fw, fh, [92, 120, 150], 0.55);
      else if (variant === 3) interior(p, fx, fy, fw, fh, "shop");
      else if (variant === 4) interior(p, fx, fy, fw, fh, "food");
      else if (variant === 5) {
        rect(p, fx, fy, fw, fh, "rgb(60,74,78)", 0, 1, 1);
        for (let mx = fx; mx < fx + fw; mx += fw / 3) rect(p, mx, fy, 5, fh, "rgb(200,200,196)", 0, 0, 0.8);
        rect(p, fx, fy + fh * 0.1, fw, 4, "rgb(200,200,196)", 0, 0, 0.8);
      } else interior(p, fx, fy, fw, fh, "garage");
      footGrime(p, x, y, TILE, TILE);
      break;
    }
    case ATLAS_ROW.shopUpper: {
      plaster(p, x, y, TILE, TILE, 230);
      const v = col;
      if (v === 0 || v === 4) windowPane(p, x + 40, y + 46, TILE - 80, 120, { grille: true });
      else if (v === 1 || v === 5) balcony(p, x + 10, y + 30, TILE - 20, TILE - 46);
      else if (v === 2) { windowPane(p, x + 36, y + 50, TILE - 72, 110, { louvre: true }); acUnit(p, x + 150, y + 180); }
      else if (v === 3) { windowPane(p, x + 30, y + 50, 80, 110, { curtain: true }); windowPane(p, x + 146, y + 50, 80, 110, { grille: true }); }
      else if (v === 6) { windowPane(p, x + 70, y + 60, TILE - 140, 90, {}); acUnit(p, x + 24, y + 170); }
      else windowPane(p, x + 50, y + 56, TILE - 100, 104, { grille: random() < 0.5, curtain: true });
      // Floor band between storeys.
      rect(p, x, y + TILE - 14, TILE, 14, "rgb(215,210,200)", 0.6);
      break;
    }
    case ATLAS_ROW.houseGround: {
      plaster(p, x, y, TILE, TILE, 234);
      const v = col;
      if (v === 0 || v === 5) windowPane(p, x + 44, y + 70, TILE - 88, 100, { grille: true });
      else if (v === 1) door(p, x + 88, y + 60, 80, TILE - 60);
      else if (v === 2) { windowPane(p, x + 24, y + 74, 96, 96, { grille: true }); door(p, x + 150, y + 60, 72, TILE - 60, "#8a6240"); }
      else if (v === 3) { windowPane(p, x + 24, y + 74, 90, 96, {}); windowPane(p, x + 142, y + 74, 90, 96, { curtain: true }); }
      else if (v === 4) { rect(p, x + 110, y + 90, 36, 22, "rgb(120,120,116)", 0.2); }
      else if (v === 6) { rect(p, x + 20, y + 60, TILE - 40, TILE - 60, "rgb(130,134,130)", 0, 0, 0.8); corrugated(p, x + 20, y + 60, TILE - 40, TILE - 60, [140, 144, 140], false); }
      else windowPane(p, x + 60, y + 76, TILE - 120, 96, { louvre: true });
      // Plinth.
      rect(p, x, y + TILE - 18, TILE, 18, "rgb(190,184,174)", 0.4);
      footGrime(p, x, y, TILE, TILE);
      break;
    }
    case ATLAS_ROW.houseUpper: {
      plaster(p, x, y, TILE, TILE, 236);
      const v = col % 4;
      if (v === 0) windowPane(p, x + 50, y + 60, TILE - 100, 110, { curtain: true });
      else if (v === 1) windowPane(p, x + 40, y + 60, TILE - 80, 100, { grille: true });
      else if (v === 2) { windowPane(p, x + 70, y + 64, TILE - 140, 96, {}); acUnit(p, x + 170, y + 176); }
      else windowPane(p, x + 56, y + 60, TILE - 112, 106, { louvre: true });
      rect(p, x, y + TILE - 12, TILE, 12, "rgb(214,208,198)", 0.6);
      break;
    }
    case ATLAS_ROW.side: {
      plaster(p, x, y, TILE, TILE, 222 + Math.floor(random() * 14));
      if (col === 1) rect(p, x + 110, y + 70, 30, 30, "rgb(70,76,78)", 0, 0.6, 0.8);
      if (col === 2) for (let i = 0; i < 4; i += 1) rect(p, x + random() * TILE, y + random() * TILE, 30 + random() * 40, 20 + random() * 30, "rgba(110,120,90,0.25)", 0); // damp patches
      if (col === 3) rect(p, x + 40, y, 8, TILE, "rgb(130,132,130)", 0, 0, 0.7); // a down pipe
      if (col === 4) for (let by = y + 120; by < y + 200; by += 14) for (let bx = x + 60 + ((by / 14) % 2) * 12; bx < x + 180; bx += 24) rect(p, bx, by, 22, 12, "rgb(176,96,70)", 0); // bare brick
      footGrime(p, x, y, TILE, TILE);
      break;
    }
    case ATLAS_ROW.large: {
      const metal: [number, number, number] = col % 3 === 0 ? [168, 172, 170] : col % 3 === 1 ? [120, 140, 150] : [170, 150, 120];
      if (col < 4) {
        corrugated(p, x, y, TILE, TILE, metal);
        if (col % 2 === 0) interior(p, x + 30, y + 90, TILE - 60, TILE - 90, col === 0 ? "shop" : "garage");
      } else {
        plaster(p, x, y, TILE, TILE, 226);
        windowPane(p, x + 30, y + 40, TILE - 60, 60, { louvre: true });
        if (col % 2 === 1) interior(p, x + 40, y + 130, TILE - 80, TILE - 130, "shop");
      }
      footGrime(p, x, y, TILE, TILE);
      break;
    }
    case ATLAS_ROW.civic: {
      if (col < 4) {
        // Temple hall: white walls, tall shuttered windows with red and gold frames.
        rect(p, x, y, TILE, TILE, "rgb(243,240,232)", 0.15);
        rect(p, x + 70, y + 40, TILE - 140, TILE - 70, "#9b2d20", 0, 0.4);
        rect(p, x + 82, y + 52, TILE - 164, TILE - 94, "#c9a227", 0, 0, 0.9);
        rect(p, x + 92, y + 62, TILE - 184, TILE - 114, "#7e2418", 0, 0.5);
        rect(p, x, y + TILE - 22, TILE, 22, "#d8c9a4", 0);
        rect(p, x, y, TILE, 12, "#c9a227", 0, 0, 0.9);
      } else {
        // Government office: cream walls, tall windows, a pilaster.
        plaster(p, x, y, TILE, TILE, 238);
        windowPane(p, x + 60, y + 40, TILE - 120, 150, { louvre: col % 2 === 0, frame: "#f6f1e6" });
        rect(p, x, y, 16, TILE, "rgb(226,220,206)", 0.5);
        rect(p, x, y + TILE - 16, TILE, 16, "rgb(200,194,182)", 0.4);
      }
      break;
    }
    case ATLAS_ROW.utility: {
      if (col < 4) {
        // School corridor: open walkway with a railing, classroom windows behind.
        plaster(p, x, y, TILE, TILE, 236);
        windowPane(p, x + 40, y + 40, TILE - 80, 90, { louvre: true });
        rect(p, x, y + 150, TILE, 6, "rgb(60,90,120)", 0, 0, 0.6);
        for (let rx = x; rx < x + TILE; rx += 16) rect(p, rx, y + 150, 3, 70, "rgb(60,90,120)", 0, 0, 0.6);
        rect(p, x, y + TILE - 18, TILE, 18, "rgb(180,176,166)", 0.4);
      } else {
        // Shed: timber planks or sheet metal.
        if (col % 2 === 0) for (let px = x; px < x + TILE; px += 22) rect(p, px, y, 20, TILE, `rgb(${120 + Math.floor(random() * 30)},${92 + Math.floor(random() * 20)},${64 + Math.floor(random() * 16)})`, 0);
        else corrugated(p, x, y, TILE, TILE, [150, 152, 148]);
        if (col === 5) door(p, x + 90, y + 70, 76, TILE - 70, "#6d5a46");
      }
      break;
    }
  }
  p.color.restore();
  p.mask.restore();
}

export interface FacadeAtlas {
  color: THREE.CanvasTexture;
  mask: THREE.CanvasTexture;
  dispose(): void;
}

/** Paint the atlas (about 2048 px square; 1024 on the low-quality path). */
export function buildFacadeAtlas(lowQuality = false): FacadeAtlas {
  const colorCanvas = document.createElement("canvas");
  const maskCanvas = document.createElement("canvas");
  colorCanvas.width = colorCanvas.height = SIZE;
  maskCanvas.width = maskCanvas.height = SIZE;
  const color = colorCanvas.getContext("2d")!;
  const mask = maskCanvas.getContext("2d")!;
  const painter: Painter = { color, mask, random: seeded(919) };
  for (let row = 0; row < ATLAS_TILES; row += 1) for (let col = 0; col < ATLAS_TILES; col += 1) paintTile(painter, row, col);
  const finish = (canvas: HTMLCanvasElement, srgb: boolean) => {
    let source: HTMLCanvasElement = canvas;
    if (lowQuality) {
      source = document.createElement("canvas");
      source.width = source.height = SIZE / 2;
      source.getContext("2d")!.drawImage(canvas, 0, 0, SIZE / 2, SIZE / 2);
    }
    const texture = new THREE.CanvasTexture(source);
    texture.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    texture.anisotropy = 4;
    texture.generateMipmaps = true;
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    return texture;
  };
  const colorTexture = finish(colorCanvas, true);
  const maskTexture = finish(maskCanvas, false);
  return {
    color: colorTexture,
    mask: maskTexture,
    dispose() {
      colorTexture.dispose();
      maskTexture.dispose();
    },
  };
}
