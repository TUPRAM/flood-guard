import { describe, expect, it } from "vitest";

import {
  LANGUAGE_STORAGE_KEY,
  readStoredLanguage,
  writeStoredLanguage,
} from "./use-language";

describe("language preference", () => {
  it("uses each surface default until a valid preference exists", () => {
    const storage = { getItem: () => null };

    expect(readStoredLanguage(storage, "th")).toBe("th");
    expect(readStoredLanguage(storage, "en")).toBe("en");
  });

  it("accepts only supported persisted values", () => {
    expect(readStoredLanguage({ getItem: () => "en" }, "th")).toBe("en");
    expect(readStoredLanguage({ getItem: () => "th" }, "en")).toBe("th");
    expect(readStoredLanguage({ getItem: () => "fr" }, "th")).toBe("th");
  });

  it("writes the shared preference without throwing when storage is blocked", () => {
    const values = new Map<string, string>();
    writeStoredLanguage({ setItem: (key, value) => values.set(key, value) }, "en");
    expect(values.get(LANGUAGE_STORAGE_KEY)).toBe("en");

    expect(() => writeStoredLanguage({ setItem: () => { throw new Error("blocked"); } }, "th")).not.toThrow();
  });
});
