import { describe, expect, it, vi } from "vitest";

import { basemapStateForTiles, getBasemapHealth, publishBasemapHealth, subscribeBasemapHealth } from "./basemap-health";

describe("map background health", () => {
  it("does not report success on the first tile or mask partial failures", () => {
    expect(basemapStateForTiles([])).toBe("loading");
    expect(basemapStateForTiles(["ready", "loading"])).toBe("loading");
    expect(basemapStateForTiles(["error", "loading"])).toBe("loading");
    expect(basemapStateForTiles(["ready", "error"])).toBe("partial");
    expect(basemapStateForTiles(["error", "error"])).toBe("unavailable");
    expect(basemapStateForTiles(["ready", "ready"])).toBe("ready");
  });

  it("keeps multiple map statuses independent and removes unmounted maps", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeBasemapHealth(listener);
    try {
      expect(getBasemapHealth()).toBeNull();
      publishBasemapHealth("map-a", "ready");
      expect(getBasemapHealth()).toBe("ready");
      publishBasemapHealth("map-b", "unavailable");
      expect(getBasemapHealth()).toBe("unavailable");
      publishBasemapHealth("map-a", "ready");
      expect(listener).toHaveBeenCalledTimes(2);
      publishBasemapHealth("map-b", "hidden");
      expect(getBasemapHealth()).toBe("ready");
      publishBasemapHealth("map-a", null);
      expect(getBasemapHealth()).toBe("hidden");
      publishBasemapHealth("map-b", "offline");
      expect(getBasemapHealth()).toBe("offline");
    } finally {
      unsubscribe();
      publishBasemapHealth("map-a", null);
      publishBasemapHealth("map-b", null);
    }
    const calls = listener.mock.calls.length;
    publishBasemapHealth("map-c", "loading");
    publishBasemapHealth("map-c", null);
    expect(listener).toHaveBeenCalledTimes(calls);
    expect(getBasemapHealth()).toBeNull();
  });
});
