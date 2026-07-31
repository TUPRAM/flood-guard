import { describe, expect, it } from "vitest";

import {
  generateGuestDisplayName,
  greetingText,
  PUBLIC_DISPLAY_NAME_STORAGE_KEY,
  resolveInitialDisplayName,
} from "./public-display-name";

function memoryStorage(seed: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(seed));
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => void map.delete(key),
    setItem: (key: string, value: string) => void map.set(key, value),
  } as Storage;
}

describe("public display name", () => {
  it("assigns a guest handle on first launch and keeps it afterwards", () => {
    const storage = memoryStorage();
    const first = resolveInitialDisplayName(storage);

    expect(first).toMatch(/^Username\d{3}$/);
    expect(storage.getItem(PUBLIC_DISPLAY_NAME_STORAGE_KEY)).toBe(first);
    // A second visit must greet the same reader, not rename them.
    expect(resolveInitialDisplayName(storage)).toBe(first);
  });

  it("keeps a name the reader chose", () => {
    const storage = memoryStorage({
      [PUBLIC_DISPLAY_NAME_STORAGE_KEY]: "Nong Fah",
    });

    expect(resolveInitialDisplayName(storage)).toBe("Nong Fah");
  });

  it("still returns a usable handle when storage is unavailable", () => {
    expect(resolveInitialDisplayName(null)).toMatch(/^Username\d{3}$/);
  });

  it("generates handles inside the three-digit range", () => {
    for (let attempt = 0; attempt < 200; attempt += 1) {
      const suffix = Number(generateGuestDisplayName().replace("Username", ""));
      expect(suffix).toBeGreaterThanOrEqual(100);
      expect(suffix).toBeLessThanOrEqual(999);
    }
  });

  it("greets with the name in both languages", () => {
    expect(greetingText("Username123", "en")).toBe("Hello, Username123");
    expect(greetingText("Username123", "th")).toBe("สวัสดี Username123");
    expect(greetingText("", "en")).toBe("Hello");
  });
});
