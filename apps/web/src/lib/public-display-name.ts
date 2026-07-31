import type { Language } from "./types";

export const PUBLIC_DISPLAY_NAME_STORAGE_KEY = "floodguard:display-name:v1";

/** Keeps the greeting short and prevents storing an essay in local storage. */
export const PUBLIC_DISPLAY_NAME_MAX_LENGTH = 24;

export function normalizeDisplayName(value: string): string {
  return value.replace(/\s+/g, " ").trim().slice(0, PUBLIC_DISPLAY_NAME_MAX_LENGTH);
}

/**
 * Reads the optional greeting name. The name never leaves the device: it is
 * not sent with reports and is not part of the household plan artifact.
 */
export function readStoredDisplayName(storage: Storage | null): string {
  if (!storage) return "";
  try {
    return normalizeDisplayName(storage.getItem(PUBLIC_DISPLAY_NAME_STORAGE_KEY) ?? "");
  } catch {
    return "";
  }
}

export function writeStoredDisplayName(storage: Storage | null, value: string): void {
  if (!storage) return;
  const normalized = normalizeDisplayName(value);
  try {
    if (normalized) {
      storage.setItem(PUBLIC_DISPLAY_NAME_STORAGE_KEY, normalized);
    } else {
      storage.removeItem(PUBLIC_DISPLAY_NAME_STORAGE_KEY);
    }
  } catch {
    /* Storage can be unavailable in private mode; the greeting stays generic. */
  }
}

/**
 * Assigns a throwaway handle so the greeting has a name to use on first launch.
 * It is generated on the device, stored beside the chosen name, and carries no
 * personal information — the reader can replace it from the profile drawer.
 */
export function generateGuestDisplayName(): string {
  const suffix = Math.floor(Math.random() * 900) + 100;
  return `Username${suffix}`;
}

/**
 * Returns the name to greet with, assigning and storing a guest handle the
 * first time. Storing it on assignment is what keeps the greeting stable
 * between visits instead of renaming the reader on every load.
 */
export function resolveInitialDisplayName(storage: Storage | null): string {
  const stored = readStoredDisplayName(storage);
  if (stored) return stored;
  const guest = generateGuestDisplayName();
  writeStoredDisplayName(storage, guest);
  return guest;
}

export function greetingText(displayName: string, language: Language): string {
  const th = language === "th";
  if (!displayName) return th ? "สวัสดี" : "Hello";
  return th ? `สวัสดี ${displayName}` : `Hello, ${displayName}`;
}
