import { describe, expect, it } from "vitest";

import { projectToFrame } from "./flood-timeline";
import { cellOutlines, frameToLatLng } from "./public-practice-outline";

/** Cells of a grid `width` wide from rows of text: "#" is in the set. */
function cellsOf(rows: string[]): { cells: Uint32Array; width: number; height: number } {
  const width = rows[0].length;
  const cells: number[] = [];
  rows.forEach((row, y) => [...row].forEach((mark, x) => {
    if (mark === "#") cells.push(y * width + x);
  }));
  return { cells: Uint32Array.from(cells), width, height: rows.length };
}

const corners = (loop: number[]): string[] => {
  const points: string[] = [];
  for (let index = 0; index < loop.length; index += 2) points.push(`${loop[index]},${loop[index + 1]}`);
  return points;
};

describe("cellOutlines", () => {
  it("draws one loop of four corners around a block of cells", () => {
    const { cells, width, height } = cellsOf([
      "....",
      ".##.",
      ".##.",
      "....",
    ]);
    const loops = cellOutlines(cells, width, height, 0);
    expect(loops).toHaveLength(1);
    expect(corners(loops[0]).sort()).toEqual(["1,1", "1,3", "3,1", "3,3"]);
  });

  it("keeps only the corners where the line turns", () => {
    const { cells, width, height } = cellsOf([
      "###.",
      "#...",
    ]);
    const [loop] = cellOutlines(cells, width, height, 0);
    // An L of four cells has six corners, however many cell edges lie along its sides.
    expect(corners(loop).sort()).toEqual(["0,0", "0,2", "1,1", "1,2", "3,0", "3,1"]);
  });

  it("draws a hole as a loop of its own", () => {
    const { cells, width, height } = cellsOf([
      "###",
      "#.#",
      "###",
    ]);
    const loops = cellOutlines(cells, width, height, 0);
    expect(loops).toHaveLength(2);
    expect(loops.map((loop) => corners(loop).sort().join(" ")).sort()).toEqual([
      "0,0 0,3 3,0 3,3",
      "1,1 1,2 2,1 2,2",
    ]);
  });

  it("closes every loop where two cells touch at a corner only", () => {
    const { cells, width, height } = cellsOf([
      "#.",
      ".#",
    ]);
    const loops = cellOutlines(cells, width, height, 0);
    // Eight cell edges in all, in one loop through the shared corner or in two: either way none is left over.
    const turns = loops.reduce((sum, loop) => sum + loop.length / 2, 0);
    expect(turns).toBe(8);
  });

  it("runs along the edge of the grid", () => {
    const { cells, width, height } = cellsOf(["##"]);
    const [loop] = cellOutlines(cells, width, height, 0);
    expect(corners(loop).sort()).toEqual(["0,0", "0,1", "2,0", "2,1"]);
  });

  it("leaves out loops shorter than the limit", () => {
    const { cells, width, height } = cellsOf([
      "#....",
      "..###",
      "..###",
      "..###",
    ]);
    // The single cell has four edges, the block twelve.
    expect(cellOutlines(cells, width, height, 5)).toHaveLength(1);
    expect(cellOutlines(cells, width, height, 13)).toEqual([]);
  });
});

describe("frameToLatLng", () => {
  const bounds: [[number, number], [number, number]] = [[20.255543, 99.808141], [20.491672, 100.039491]];

  it("puts the corners of the frame on the corners of the bounds", () => {
    const [north, west] = frameToLatLng(0, 0, bounds, 1610, 1753);
    const [south, east] = frameToLatLng(1610, 1753, bounds, 1610, 1753);
    expect(north).toBeCloseTo(20.491672, 9);
    expect(west).toBeCloseTo(99.808141, 9);
    expect(south).toBeCloseTo(20.255543, 9);
    expect(east).toBeCloseTo(100.039491, 9);
  });

  it("is the inverse of projectToFrame", () => {
    for (const [x, y] of [[12.5, 40], [805, 876.5], [1600, 1700]]) {
      const [latitude, longitude] = frameToLatLng(x, y, bounds, 1610, 1753);
      const [backX, backY] = projectToFrame(longitude, latitude, bounds, 1610, 1753);
      expect(backX).toBeCloseTo(x, 6);
      expect(backY).toBeCloseTo(y, 6);
    }
  });
});
