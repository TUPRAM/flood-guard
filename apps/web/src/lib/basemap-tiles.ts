import type { DoneCallback } from "leaflet";

export const BASEMAP_TILE_TIMEOUT_MS = 12_000;

/** Load one requested tile, rejecting HTTP error images before they can cover the map. */
export function loadBasemapTile(url: string, tile: HTMLImageElement, done: DoneCallback): () => void {
  const controller = new AbortController();
  let objectUrl: string | undefined;
  let settled = false;
  const releaseImage = () => {
    tile.onload = null;
    tile.onerror = null;
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = undefined;
    }
  };
  const finish = (error?: Error) => {
    if (settled) return;
    settled = true;
    clearTimeout(timeout);
    releaseImage();
    if (error) tile.removeAttribute("src");
    done(error, tile);
  };
  const timeout = setTimeout(() => {
    controller.abort();
    finish(new Error("Map background request timed out"));
  }, BASEMAP_TILE_TIMEOUT_MS);
  tile.alt = "";
  tile.referrerPolicy = "strict-origin";
  tile.onload = () => finish();
  tile.onerror = () => finish(new Error("Map background image could not be decoded"));

  // Keep normal browser caching. No provider probes, prefetching, or offline tile store.
  void fetch(url, {
    signal: controller.signal,
    referrerPolicy: "strict-origin",
    credentials: "omit",
    mode: "cors",
  }).then(async (response) => {
    if (!response.ok) throw new Error(`Map background HTTP ${response.status}`);
    const blob = await response.blob();
    if (!blob.type.startsWith("image/") || blob.size === 0) {
      throw new Error("Map background response is not an image");
    }
    if (settled) return;
    objectUrl = URL.createObjectURL(blob);
    tile.src = objectUrl;
  }).catch((error: unknown) => {
    finish(error instanceof Error ? error : new Error("Map background request failed"));
  });

  return () => {
    settled = true;
    clearTimeout(timeout);
    controller.abort();
    releaseImage();
    tile.removeAttribute("src");
  };
}
