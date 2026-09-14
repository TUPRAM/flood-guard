import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BASEMAP_TILE_TIMEOUT_MS, loadBasemapTile } from "./basemap-tiles";

function imageStub() {
  return { alt: "", referrerPolicy: "", src: "", onload: null, onerror: null, removeAttribute: vi.fn() } as unknown as HTMLImageElement;
}

function tileResponse(type = "image/png", status = 200): Response {
  return { ok: status >= 200 && status < 300, status, blob: async () => new Blob(["tile"], { type }) } as Response;
}

describe("map background tile requests", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([403, 429, 503])("rejects a decodable image served with HTTP %i before assigning it", async (status) => {
    const response = tileResponse("image/png", status);
    const blob = vi.spyOn(response, "blob");
    const fetcher = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetcher);
    const tile = imageStub();
    const done = vi.fn();
    loadBasemapTile("https://tile.openstreetmap.org/9/398/226.png", tile, done);
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toHaveBeenCalledWith(expect.objectContaining({ message: `Map background HTTP ${status}` }), tile);
    expect(blob).not.toHaveBeenCalled();
    expect(tile.src).toBe("");
    expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ referrerPolicy: "strict-origin", credentials: "omit", mode: "cors" }));
    expect(fetcher.mock.calls[0][1]).not.toHaveProperty("cache");
  });

  it("only succeeds after image decoding and releases the temporary blob URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(tileResponse()));
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:map-test");
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    const tile = imageStub();
    const done = vi.fn();
    const cancel = loadBasemapTile("https://tile.openstreetmap.org/9/398/226.png", tile, done);
    await vi.advanceTimersByTimeAsync(0);
    expect(create).toHaveBeenCalledOnce();
    expect(tile.src).toBe("blob:map-test");
    expect(done).not.toHaveBeenCalled();
    tile.onload?.call(tile, new Event("load"));
    expect(done).toHaveBeenCalledWith(undefined, tile);
    expect(revoke).toHaveBeenCalledWith("blob:map-test");
    cancel();
    await vi.advanceTimersByTimeAsync(BASEMAP_TILE_TIMEOUT_MS);
    expect(done).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledOnce();
  });

  it.each(["fetch", "decode"])("bounds stalled %s and ignores a late completion", async (stage) => {
    let resolveResponse: (response: Response) => void = () => undefined;
    const response = new Promise<Response>((resolve) => { resolveResponse = resolve; });
    const fetcher = vi.fn().mockReturnValue(response);
    vi.stubGlobal("fetch", fetcher);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:stalled-map");
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    const tile = imageStub();
    const done = vi.fn();
    loadBasemapTile("https://tile.openstreetmap.org/9/398/226.png", tile, done);
    if (stage === "decode") resolveResponse(tileResponse());
    await vi.advanceTimersByTimeAsync(BASEMAP_TILE_TIMEOUT_MS);
    expect(done).toHaveBeenCalledWith(expect.objectContaining({ message: "Map background request timed out" }), tile);
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
    resolveResponse(tileResponse());
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toHaveBeenCalledOnce();
    if (stage === "decode") expect(revoke).toHaveBeenCalledWith("blob:stalled-map");
  });

  it("cancels removed tiles without reporting a failure or reviving old imagery", async () => {
    let resolveResponse: (response: Response) => void = () => undefined;
    const fetcher = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { resolveResponse = resolve; }));
    vi.stubGlobal("fetch", fetcher);
    const create = vi.spyOn(URL, "createObjectURL");
    const tile = imageStub();
    const done = vi.fn();
    const cancel = loadBasemapTile("https://tile.openstreetmap.org/9/398/226.png", tile, done);
    cancel();
    resolveResponse(tileResponse());
    await vi.advanceTimersByTimeAsync(BASEMAP_TILE_TIMEOUT_MS);
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
    expect(done).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });

  it.each(["text/html", "application/json"])("rejects a successful %s response", async (type) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(tileResponse(type)));
    const done = vi.fn();
    loadBasemapTile("https://tile.openstreetmap.org/9/398/226.png", imageStub(), done);
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toHaveBeenCalledWith(expect.objectContaining({ message: "Map background response is not an image" }), expect.anything());
  });
});
