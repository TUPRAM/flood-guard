/**
 * The outline of a set of grid cells, for the furthest water of the practice replay on the Public home map: closed
 * loops along the edges of the cells, so the area can be drawn as a crisp line at any zoom. A raster hatch of the same
 * cells blurs into dots when the map is zoomed in.
 *
 * Pure functions; no DOM access. The cells are those of the replay's terrain grid that are wet at its highest stage:
 * a T1 scenario (model) with low confidence.
 */

/** Loops shorter than this many cell edges are left out: islands and holes a few cells across only clutter the line. */
export const OUTLINE_MIN_EDGES = 24;

/**
 * Closed loops around `cells` (indices `row * width + column`) of a grid `width` by `height` cells. Each loop is a flat
 * list of corner positions `x0, y0, x1, y1, …` in cell units (a cell spans x … x + 1, y … y + 1), holding only the
 * corners where the line turns; the last corner joins the first. The area lies to the right of the direction of
 * travel, so holes run the other way round. Loops of fewer than `minEdges` cell edges are dropped.
 */
export function cellOutlines(cells: Uint32Array, width: number, height: number, minEdges = OUTLINE_MIN_EDGES): number[][] {
  const inside = new Uint8Array(width * height);
  for (let index = 0; index < cells.length; index += 1) inside[cells[index]] = 1;
  const stride = width + 1;
  // One directed edge per cell side that faces a cell outside the set. A corner where two cells of the set touch
  // diagonally has two edges leaving it.
  const first = new Map<number, number>();
  const second = new Map<number, number>();
  const add = (from: number, to: number) => {
    if (first.has(from)) second.set(from, to);
    else first.set(from, to);
  };
  for (let index = 0; index < cells.length; index += 1) {
    const cell = cells[index];
    const column = cell % width;
    const row = (cell - column) / width;
    const topLeft = row * stride + column;
    const bottomLeft = topLeft + stride;
    if (row === 0 || !inside[cell - width]) add(topLeft, topLeft + 1);
    if (column === width - 1 || !inside[cell + 1]) add(topLeft + 1, bottomLeft + 1);
    if (row === height - 1 || !inside[cell + width]) add(bottomLeft + 1, bottomLeft);
    if (column === 0 || !inside[cell - 1]) add(bottomLeft, topLeft);
  }
  const take = (from: number): number | undefined => {
    const later = second.get(from);
    if (later !== undefined) {
      second.delete(from);
      return later;
    }
    const next = first.get(from);
    if (next !== undefined) first.delete(from);
    return next;
  };
  const loops: number[][] = [];
  for (const start of [...first.keys()]) {
    if (!first.has(start)) continue;
    const loop: number[] = [];
    let at = start;
    let edges = 0;
    let lastDx = 0;
    let lastDy = 0;
    for (;;) {
      const to = take(at);
      if (to === undefined) break;
      const x = at % stride;
      const y = (at - x) / stride;
      const dx = (to % stride) - x;
      const dy = Math.floor(to / stride) - y;
      if (dx !== lastDx || dy !== lastDy) loop.push(x, y);
      lastDx = dx;
      lastDy = dy;
      edges += 1;
      at = to;
      if (at === start) break;
    }
    if (edges >= minEdges && loop.length >= 6) loops.push(loop);
  }
  return loops;
}

const mercatorY = (latitude: number): number => Math.log(Math.tan(Math.PI / 4 + (latitude * Math.PI) / 360));

/**
 * Latitude and longitude of a position `x`, `y` in a frame `width` by `height` spanning `bounds`
 * ([[south, west], [north, east]]): the inverse of `projectToFrame`, linear in Web Mercator like the rasters the map
 * stretches over the same bounds.
 */
export function frameToLatLng(
  x: number,
  y: number,
  bounds: readonly [readonly [number, number], readonly [number, number]],
  width: number,
  height: number,
): [number, number] {
  const [[south, west], [north, east]] = bounds;
  const top = mercatorY(north);
  const bottom = mercatorY(south);
  const mercator = top - (y / height) * (top - bottom);
  const latitude = ((2 * Math.atan(Math.exp(mercator)) - Math.PI / 2) * 180) / Math.PI;
  return [latitude, west + (x / width) * (east - west)];
}
