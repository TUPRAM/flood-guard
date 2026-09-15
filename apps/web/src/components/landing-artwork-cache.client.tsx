"use client";

import { useEffect } from "react";

/** Save optional illustration variants after the first rendered page is ready. */
export function LandingArtworkCache() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    let disposed = false;
    let frame = 0;
    let idle = 0;
    let timer = 0;
    const requestCache = () => {
      void navigator.serviceWorker.ready.then((registration) => {
        if (!disposed) registration.active?.postMessage({ type: "FLOODGUARD_CACHE_LANDING_ARTWORK" });
      }).catch(() => undefined);
    };
    const schedule = () => {
      frame = window.requestAnimationFrame(() => {
        frame = window.requestAnimationFrame(() => {
          if ("requestIdleCallback" in window) idle = window.requestIdleCallback(requestCache, { timeout: 5000 });
          else timer = globalThis.setTimeout(requestCache, 2000) as unknown as number;
        });
      });
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
    return () => {
      disposed = true;
      window.removeEventListener("load", schedule);
      window.cancelAnimationFrame(frame);
      if (idle) window.cancelIdleCallback(idle);
      window.clearTimeout(timer);
    };
  }, []);
  return null;
}
