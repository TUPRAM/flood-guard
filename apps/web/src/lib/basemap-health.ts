export type BasemapState = "loading" | "ready" | "partial" | "unavailable" | "offline" | "hidden";
export type BasemapTileState = "loading" | "ready" | "error";

/** A background is ready only when every requested visible tile has loaded. */
export function basemapStateForTiles(tiles: Iterable<BasemapTileState>): BasemapState {
  const states = [...tiles];
  if (states.includes("loading") || states.length === 0) return "loading";
  if (states.every((state) => state === "ready")) return "ready";
  return states.includes("ready") ? "partial" : "unavailable";
}

const maps = new Map<string, BasemapState>();
const listeners = new Set<() => void>();

/** Summarize mounted maps without conflating background availability with connectivity. */
export function getBasemapHealth(): BasemapState | null {
  const states = [...maps.values()];
  for (const state of ["offline", "unavailable", "partial", "loading", "ready", "hidden"] as const) {
    if (states.includes(state)) return state;
  }
  return null;
}

/** Subscribe to map health; suitable for React's useSyncExternalStore. */
export function subscribeBasemapHealth(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Publish one mounted map's state, or remove it when that map unmounts. */
export function publishBasemapHealth(id: string, state: BasemapState | null): void {
  if (state === null ? !maps.has(id) : maps.get(id) === state) return;
  if (state === null) maps.delete(id);
  else maps.set(id, state);
  for (const listener of listeners) listener();
}
