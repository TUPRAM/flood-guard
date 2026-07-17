"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

import type { Language } from "./types";

export const LANGUAGE_STORAGE_KEY = "floodguard:language:v1";
const LANGUAGE_CHANGE_EVENT = "floodguard:language-change";
let memoryPreference: Language | null = null;

interface LanguageStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export function readStoredLanguage(
  storage: Pick<LanguageStorage, "getItem"> | null,
  fallback: Language,
): Language {
  if (!storage) return fallback;
  try {
    const stored = storage.getItem(LANGUAGE_STORAGE_KEY);
    return stored === "th" || stored === "en" ? stored : fallback;
  } catch {
    return fallback;
  }
}

export function writeStoredLanguage(
  storage: Pick<LanguageStorage, "setItem"> | null,
  language: Language,
): void {
  if (!storage) return;
  try {
    storage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Language persistence is an enhancement. Storage restrictions must not
    // prevent the bilingual interface from remaining usable.
  }
}

export function useLanguage(defaultLanguage: Language) {
  const subscribe = useCallback((notify: () => void) => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === LANGUAGE_STORAGE_KEY) notify();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener(LANGUAGE_CHANGE_EVENT, notify);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(LANGUAGE_CHANGE_EVENT, notify);
    };
  }, []);

  const getSnapshot = useCallback(
    () => readStoredLanguage(window.localStorage, memoryPreference ?? defaultLanguage),
    [defaultLanguage],
  );

  const getServerSnapshot = useCallback(() => defaultLanguage, [defaultLanguage]);
  const language = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const changeLanguage = useCallback((next: Language) => {
    memoryPreference = next;
    document.documentElement.lang = next;
    writeStoredLanguage(window.localStorage, next);
    window.dispatchEvent(new Event(LANGUAGE_CHANGE_EVENT));
  }, []);

  return [language, changeLanguage] as const;
}
