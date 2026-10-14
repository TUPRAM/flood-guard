"use client";

import { useEffect, type RefObject } from "react";

const FOCUSABLE = "button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

/**
 * Keyboard handling of a sheet that lies over a Public map. While it is open the focus starts on `first`, Escape
 * closes the sheet and Tab stays inside `panel`. `onClose` must keep its identity between renders.
 */
export function useSheetKeyboard(
  open: boolean,
  panel: RefObject<HTMLElement | null>,
  first: RefObject<HTMLElement | null>,
  onClose: () => void,
): void {
  useEffect(() => {
    if (!open) return;
    first.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const focusable = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
        .filter((element) => !element.hasAttribute("disabled"));
      if (focusable.length === 0) return;
      const start = focusable[0];
      const end = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === start) {
        event.preventDefault();
        end.focus();
      } else if (!event.shiftKey && document.activeElement === end) {
        event.preventDefault();
        start.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [first, onClose, open, panel]);
}
