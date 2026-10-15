import { readFileSync } from "node:fs";
import { inflateSync } from "node:zlib";

import { beforeAll, describe, expect, it } from "vitest";

import { decodePng } from "@/lib/flood-timeline";

import { STOP_HOURS, storyHours } from "./timeline";
import { ROOF_OVERHANG, homePad, homePlot, onPlot, rectCorners, rectHitsRing, type HomePlot } from "./home-plot";
import { FloodField, decodeTownPack, stageAtHour, type Pixels, type TownPack } from "./town-data";

const TOWN = new URL("../../../public/journey/town/", import.meta.url);
const read = (name: string) => new Uint8Array(readFileSync(new URL(name, TOWN)));

let pack: TownPack;
let plot: HomePlot;

beforeAll(async () => {
  const manifestText = new TextDecoder().decode(read("mae-sai-town.json"));
  const manifest = JSON.parse(manifestText) as { cells: { href: string }; relief: { href: string }; cover: { href: string }; backdrop: { href: string } };
  const png = async (href: string): Promise<Pixels> => decodePng(read(href.split("/").pop()!), (data) => new Uint8Array(inflateSync(data)));
  const [cells, relief, cover, backdrop] = await Promise.all([manifest.cells.href, manifest.relief.href, manifest.cover.href, manifest.backdrop.href].map(png));
  pack = decodeTownPack(manifestText, { cells, relief, cover, backdrop });
  plot = homePlot(pack);
});

const homePlace = () => pack.manifest.places.find((place) => place.id === "home")!;

describe("Lalita's plot on the real outline", () => {
  it("faces the street the walk starts from, behind a yard and a garden wall short of the street", () => {
    const { house, F, street } = plot;
    const toStreet = [street.x - house.x, street.z - house.z];
    const length = Math.hypot(toStreet[0], toStreet[1]);
    expect((F[0] * toStreet[0] + F[1] * toStreet[1]) / length).toBeGreaterThan(0.9);
    expect(Math.hypot(street.x - homePlace().x, street.z - homePlace().z)).toBeLessThan(10);
    // The wall stands before the street's edge: front wall + yard, measured along F.
    const fFront = F[0] * house.x + F[1] * house.z + house.d / 2;
    const fStreet = F[0] * street.x + F[1] * street.z;
    expect(fStreet - (fFront + plot.yard)).toBeGreaterThanOrEqual(street.width / 2);
    expect(plot.yard).toBeGreaterThanOrEqual(2.8);
  });

  it("is a two-storey house of a believable size, its gate near the home place", () => {
    expect(plot.house.w).toBeGreaterThanOrEqual(5.4);
    expect(plot.house.w).toBeLessThanOrEqual(7.2);
    expect(plot.house.d).toBeGreaterThanOrEqual(7);
    expect(plot.house.d).toBeLessThanOrEqual(9);
    const { house, F, S, yard, gateX } = plot;
    const gate = [house.x + S[0] * gateX + F[0] * (house.d / 2 + yard), house.z + S[1] * gateX + F[1] * (house.d / 2 + yard)];
    expect(Math.hypot(gate[0] - homePlace().x, gate[1] - homePlace().z)).toBeLessThan(6);
    expect(Math.abs(plot.doorX)).toBeLessThanOrEqual(house.w / 2 - 0.9);
  });

  it("touches no other outline: the roof, the garden wall and the back wing all stand clear", () => {
    const others = pack.buildings.filter((b) => b.index !== pack.special.home);
    for (const rect of plot.footprint) for (const b of others) expect(rectHitsRing(rect, b.ring), `outline ${b.index}`).toBe(false);
    // The roof rect really covers the walls and their overhang.
    expect(plot.footprint[0].w).toBeGreaterThanOrEqual(plot.house.w + 2 * ROOF_OVERHANG);
  });

  it("keeps the back wing on the rest of the real outline", () => {
    expect(plot.annex).not.toBeNull();
    const ring = pack.buildings[pack.special.home].ring;
    const inside = (x: number, z: number) => {
      let hit = false;
      for (let i = 0, j = ring.length / 2 - 1; i < ring.length / 2; j = i, i += 1) {
        const xi = ring[i * 2], zi = ring[i * 2 + 1], xj = ring[j * 2], zj = ring[j * 2 + 1];
        if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) hit = !hit;
      }
      return hit;
    };
    for (const [x, z] of rectCorners(plot.annex!)) expect(inside(x, z)).toBe(true);
  });

  it("puts the house on ground the model keeps dry at the peak", () => {
    const field = new FloodField(pack);
    const peak = stageAtHour(pack.manifest, 84);
    const { house, F, S } = plot;
    for (let a = -0.5; a <= 0.5; a += 0.125) for (let b = -0.5; b <= 0.5; b += 0.125) {
      const x = house.x + S[0] * a * house.w + F[0] * b * house.d, z = house.z + S[1] * a * house.w + F[1] * b * house.d;
      expect(field.cellDepth(field.cellIndex(x, z), peak), `${x.toFixed(1)},${z.toFixed(1)}`).toBeNull();
    }
  });

  it("knows its own ground: the yard is on the plot, the street is not", () => {
    const { house, F, street } = plot;
    expect(onPlot(plot, house.x, house.z)).toBe(true);
    expect(onPlot(plot, house.x + F[0] * (house.d / 2 + 1.5), house.z + F[1] * (house.d / 2 + 1.5))).toBe(true);
    expect(onPlot(plot, street.x, street.z)).toBe(false);
  });

  it("holds the house, yard and gate dry at every hour of the story with the pad the scene builds", () => {
    const field = new FloodField(pack);
    const homeCell = field.cellIndex(homePlace().x, homePlace().z);
    const homeGround = field.ground[homeCell];
    const bare = (x: number, z: number) => field.groundAt(x, z);
    const far = { x: plot.house.x - plot.F[0] * 20, z: plot.house.z - plot.F[1] * 20 };
    const before = bare(far.x, far.z);
    field.addPad(homePad(plot, homeGround));
    const { house, F, S, yard, gateX } = plot;
    const at = (a: number, b: number) => [house.x + S[0] * a + F[0] * b, house.z + S[1] * a + F[1] * b] as const;
    const points = [
      at(-house.w / 2, -house.d / 2), at(house.w / 2, -house.d / 2), at(-house.w / 2, house.d / 2), at(house.w / 2, house.d / 2),
      at(0, house.d / 2 + yard / 2), at(gateX, house.d / 2 + yard + 0.2),
    ];
    for (const hour of [...storyHours(), ...Object.values(STOP_HOURS)]) {
      const stage = stageAtHour(pack.manifest, hour);
      for (const [x, z] of points) expect(field.depthAt(x, z, stage), `hour ${hour} at ${x.toFixed(1)},${z.toFixed(1)}`).toBe(0);
    }
    // Flat on top at the home cell's height; the model's ground well beyond the pad.
    for (const [x, z] of points.slice(0, 4)) expect(field.groundAt(x, z)).toBeCloseTo(homeGround, 9);
    expect(field.groundAt(far.x, far.z)).toBe(before);
  });
});
