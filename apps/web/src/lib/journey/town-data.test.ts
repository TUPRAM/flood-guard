import { readFileSync } from "node:fs";
import { inflateSync } from "node:zlib";

import { beforeAll, describe, expect, it } from "vitest";

import { cellDepth, decodePng, stageAt } from "@/lib/flood-timeline";
import { PRACTICE_HOMES } from "@/lib/public-practice-scenarios";

import { STOP_HOURS, storyHours } from "./timeline";
import { FloodField, decodeTownPack, stageAtHour, type Pixels, type TownPack } from "./town-data";

const TOWN = new URL("../../../public/journey/town/", import.meta.url);
const read = (name: string) => new Uint8Array(readFileSync(new URL(name, TOWN)));
const inflate = (data: Uint8Array) => new Uint8Array(inflateSync(data));

let pack: TownPack;
let field: FloodField;

beforeAll(async () => {
  const manifestText = new TextDecoder().decode(read("mae-sai-town.json"));
  const manifest = JSON.parse(manifestText) as { cells: { href: string }; relief: { href: string }; cover: { href: string }; backdrop: { href: string } };
  const png = async (href: string): Promise<Pixels> => decodePng(read(href.split("/").pop()!), inflate);
  const [cells, relief, cover, backdrop] = await Promise.all([manifest.cells.href, manifest.relief.href, manifest.cover.href, manifest.backdrop.href].map(png));
  pack = decodeTownPack(manifestText, { cells, relief, cover, backdrop });
  field = new FloodField(pack);
});

const place = (id: string) => pack.manifest.places.find((entry) => entry.id === id)!;

describe("the journey's town (the bake of Mae Sai)", () => {
  it("is a historical reconstruction with low confidence, credited", () => {
    const manifest = pack.manifest as unknown as Record<string, unknown>;
    expect(manifest.real_time).toBe(false);
    expect(manifest.official_warning).toBe(false);
    expect(pack.manifest.confidence).toBe("low");
    expect(pack.manifest.source_timestamp).toBeTruthy();
    for (const credit of ["Open Buildings", "OpenStreetMap", "Copernicus"]) expect(pack.manifest.credits.en).toContain(credit);
  });

  it("puts Lalita's home at the Public app's dry example home and her neighbour at the flooded one", () => {
    const home = place("home"), neighbour = place("neighbour");
    expect(home.x).toBeCloseTo(0, 6);
    expect(home.z).toBeCloseTo(0, 6);
    const cos = Math.cos((PRACTICE_HOMES.dry.latitude * Math.PI) / 180);
    expect(neighbour.x).toBeCloseTo((PRACTICE_HOMES.flooded.longitude - PRACTICE_HOMES.dry.longitude) * 111320 * cos, 1);
    expect(neighbour.z).toBeCloseTo((PRACTICE_HOMES.dry.latitude - PRACTICE_HOMES.flooded.latitude) * 110540, 1);
    expect(home.cell?.code).toBe(76);
    expect(neighbour.cell?.code).toBe(55);
  });

  it("decodes thousands of real outlines, the roads and the trees inside the box", () => {
    expect(pack.buildings.length).toBeGreaterThan(5000);
    expect(pack.roads.length).toBeGreaterThan(200);
    expect(pack.trees.length).toBeGreaterThan(500);
    for (const index of [pack.special.home, pack.special.neighbour, pack.special.office]) expect(pack.buildings[index]).toBeDefined();
    const home = pack.buildings[pack.special.home];
    expect(Math.hypot(home.obb.cx, home.obb.cz)).toBeLessThan(25);
  });

  it("reads the replay's cells exactly: the home is dry at every hour of the story, the neighbour has 0.75 m at the peak", () => {
    const home = field.cellIndex(place("home").x, place("home").z);
    const neighbour = field.cellIndex(place("neighbour").x, place("neighbour").z);
    for (const hour of [...storyHours(), ...Object.values(STOP_HOURS)]) {
      expect(field.cellDepth(home, stageAtHour(pack.manifest, hour)), `hour ${hour}`).toBeNull();
    }
    const peak = stageAtHour(pack.manifest, 84);
    expect(peak).toBe(3.5);
    expect(field.cellDepth(neighbour, peak)).toBeCloseTo(0.75, 9);
    // The same rule as the replay's own cellDepth.
    expect(field.cellDepth(neighbour, peak)).toBeCloseTo(cellDepth(pack.cells.code[neighbour], peak, 0.05, pack.cells.kByte[neighbour], 0, 255, 2.5)!, 12);
  });

  it("uses the replay's stages at the beat hours", () => {
    for (const beat of pack.manifest.beats) expect(beat.stage_m).toBe(stageAt(beat.hour / 24, pack.manifest.replay.stage_anchors));
  });

  it("draws the home on its cell's height, so it stays dry in the 3D scene at the peak", () => {
    const home = pack.buildings[pack.special.home];
    const homeCell = field.cellIndex(place("home").x, place("home").z);
    field.addPad({ x: home.obb.cx, z: home.obb.cz, radius: 9, blend: 7, height: field.ground[homeCell] });
    const peak = stageAtHour(pack.manifest, 84);
    for (const [dx, dz] of [[0, 0], [4, 0], [-4, 0], [0, 4], [0, -4]]) {
      expect(field.depthAt(home.obb.cx + dx, home.obb.cz + dz, peak)).toBe(0);
    }
  });

  it("draws the model's depth on its drainage lines and keeps cells that never flood dry, without cliffs at their edge", () => {
    const { cols, rows } = field;
    const peak = Math.max(...pack.manifest.replay.stage_anchors.map((anchor) => anchor.stage_m));
    let channel = 0, never = 0, worstStep = 0;
    for (let r = 0; r < rows; r += 1) for (let c = 0; c < cols; c += 1) {
      const i = r * cols + c;
      if (field.code[i] === 0) {
        channel += 1;
        expect(field.ground[i]).toBe(0);
      }
      if (field.code[i] !== 255) continue;
      never += 1;
      const x = field.x0 + (c + 0.5) * field.dx, z = field.z0 + (r + 0.5) * field.dz;
      expect(field.depthAt(x, z, peak), `never-flood cell ${c},${r} wet when drawn`).toBe(0);
      // The bank over the highest floodable neighbour (its ground or its highest water: a bank must clear the water).
      let highest = -Infinity;
      for (const [cc, rr] of [[c - 1, r], [c + 1, r], [c, r - 1], [c, r + 1]]) {
        if (cc < 0 || rr < 0 || cc >= cols || rr >= rows || field.code[rr * cols + cc] === 255) continue;
        const j = rr * cols + cc;
        highest = Math.max(highest, field.ground[j], field.kSmooth[j] * peak);
      }
      if (highest > -Infinity) worstStep = Math.max(worstStep, field.ground[i] - highest);
    }
    expect(channel).toBeGreaterThan(50);
    expect(never).toBeGreaterThan(1000);
    // Before the ramp the step at these edges reached about 29 m (median 6.8 m).
    expect(worstStep).toBeLessThan(3);
  });

  it("walks to a reported shelter in use in 2024, open at midnight on 11 September and cut by 1:00", () => {
    const route = pack.route;
    const shelter = place(route.destination);
    expect(shelter.in_access_set).toBe(true);
    expect(route.length).toBeLessThanOrEqual(2000);
    expect(route.cutStage).toBeGreaterThan(stageAtHour(pack.manifest, 48));
    expect(route.cutStage).toBeLessThanOrEqual(stageAtHour(pack.manifest, 49));
    expect(Math.min(...route.edges.map((edge) => edge.closure))).toBeCloseTo(route.cutStage, 3);
    // The labels' low point: under 30 cm at midnight (hour 48), 30 cm or more at 1:00 (hour 49), in the model.
    const low = field.cellIndex(route.lowPoint.x, route.lowPoint.z);
    expect(field.cellDepth(low, stageAtHour(pack.manifest, 48))!).toBeGreaterThan(0);
    expect(field.cellDepth(low, stageAtHour(pack.manifest, 48))!).toBeLessThan(0.3);
    expect(field.cellDepth(low, stageAtHour(pack.manifest, 49))!).toBeGreaterThanOrEqual(0.3);
    expect(Math.hypot(route.lowPoint.x, route.lowPoint.z)).toBeCloseTo(110, -1);
  });

  it("keeps Wat Mueang Daeng out of the walk: the record says it was itself flooded", () => {
    expect(pack.route.destination).not.toBe("R04");
    expect(String(place("R04").first_use)).toBe("2024-09-21");
  });
});
