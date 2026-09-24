import { describe, expect, it } from "vitest";

import {
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
  it("uses a generic greeting on first launch without creating an identifier", () => {
    const storage = memoryStorage();
    expect(resolveInitialDisplayName(storage)).toBe("");
    expect(storage.getItem(PUBLIC_DISPLAY_NAME_STORAGE_KEY)).toBeNull();
  });

  it("keeps a name the reader chose", () => {
    const storage = memoryStorage({
      [PUBLIC_DISPLAY_NAME_STORAGE_KEY]: "Nong Fah",
    });

    expect(resolveInitialDisplayName(storage)).toBe("Nong Fah");
  });

  it("removes a legacy generated guest handle", () => {
    const storage = memoryStorage({ [PUBLIC_DISPLAY_NAME_STORAGE_KEY]: "Username647" });
    expect(resolveInitialDisplayName(storage)).toBe("");
    expect(storage.getItem(PUBLIC_DISPLAY_NAME_STORAGE_KEY)).toBeNull();
  });

  it("still uses a generic greeting when storage is unavailable", () => {
    expect(resolveInitialDisplayName(null)).toBe("");
  });

  it("greets with the name in both languages", () => {
    expect(greetingText("Nong Fah", "en")).toBe("Hello, Nong Fah");
    expect(greetingText("Nong Fah", "th")).toBe("สวัสดี Nong Fah");
    expect(greetingText("", "en")).toBe("Hello");
  });
});
