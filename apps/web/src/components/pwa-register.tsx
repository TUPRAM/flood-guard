"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { resolveDeploymentProfile } from "@/lib/deployment-profile";
import { HOUSEHOLD_PLAN_STORAGE_KEY, LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY } from "@/lib/household-plan";
import type { Language } from "@/lib/types";
import { useLanguage } from "@/lib/use-language";

import styles from "./pwa-register.module.css";

const OFFLINE_CACHE_PATTERN = /^floodguard-offline-[0-9a-f]{12}$/;
const LAST_REFRESH_KEY = "floodguard:last-saved-app-refresh";
const EXPECTED_PROFILE = resolveDeploymentProfile(process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE);

type AppProfile = "competition" | "public-production";
type CacheState = "checking" | "ready" | "unavailable";
type UpdateState = "current" | "checking" | "installing" | "available" | "error";

interface WorkerCacheStatus {
  cacheName: string;
  profile: AppProfile;
  cachedAt: string;
}

interface WorkerMessage {
  type?: string;
  cache_name?: string;
  profile?: AppProfile;
  cached_at?: string;
}

export interface PwaRegisterProps {
  /** Defaults to production builds; tests may opt in explicitly. */
  enabled?: boolean;
}

const PWA_AVAILABILITY_COPY = {
  en: {
    checkingConnection: "Checking connection",
    online: "Online",
    offline: "Offline",
    savedAppReady: "saved app ready",
    heading: "App availability",
    subtitle: "Mae Sai planning support",
    savedPlanningView: "Saved planning view",
    checking: "Checking…",
    availableOffline: "Available offline",
    openOnlineToSave: "Open once online to save",
    householdPlan: "Household plan",
    savedOnDevice: "Saved on this device",
    noPlanSaved: "No plan saved yet",
    floodContext: "Flood context",
    historicalContext: "September 2024 · historical",
    cachedSnapshot: "Cached planning snapshot",
    lastUpdateCheck: "Last successful update check",
    mapBackgrounds: "Map backgrounds",
    backgroundsOffline: "May be unavailable offline",
    backgroundsOnline: "Connection required",
    disclosure: "Saved planning overlays and this device’s household plan remain available offline. Current conditions still require official local information.",
    installUpdate: "Install available update",
    installing: "Installing…",
    checkUpdate: "Check for app update",
    updateErrorWithCache: "Update check is unavailable. The verified saved app remains available.",
    updateErrorWithoutCache: "Update check is unavailable and no complete saved app was verified. Connect and try again.",
    notChecked: "Not checked yet",
  },
  th: {
    checkingConnection: "กำลังตรวจสอบการเชื่อมต่อ",
    online: "ออนไลน์",
    offline: "ออฟไลน์",
    savedAppReady: "แอปที่บันทึกไว้พร้อมใช้งาน",
    heading: "สถานะแอป",
    subtitle: "เครื่องมือสนับสนุนการวางแผนแม่สาย",
    savedPlanningView: "มุมมองการวางแผนที่บันทึกไว้",
    checking: "กำลังตรวจสอบ…",
    availableOffline: "พร้อมใช้งานแบบออฟไลน์",
    openOnlineToSave: "เปิดหนึ่งครั้งขณะออนไลน์เพื่อบันทึก",
    householdPlan: "แผนครัวเรือน",
    savedOnDevice: "บันทึกไว้ในอุปกรณ์นี้",
    noPlanSaved: "ยังไม่ได้บันทึกแผน",
    floodContext: "บริบทน้ำท่วม",
    historicalContext: "กันยายน 2024 · ข้อมูลย้อนหลัง",
    cachedSnapshot: "ข้อมูลการวางแผนที่แคชไว้",
    lastUpdateCheck: "ตรวจสอบการอัปเดตสำเร็จล่าสุด",
    mapBackgrounds: "พื้นหลังแผนที่",
    backgroundsOffline: "อาจไม่พร้อมใช้งานเมื่อออฟไลน์",
    backgroundsOnline: "ต้องเชื่อมต่ออินเทอร์เน็ต",
    disclosure: "ชั้นข้อมูลการวางแผนที่บันทึกไว้และแผนครัวเรือนในอุปกรณ์นี้ยังใช้งานออฟไลน์ได้ สภาพปัจจุบันยังต้องยืนยันกับแหล่งข้อมูลท้องถิ่นที่เป็นทางการ",
    installUpdate: "ติดตั้งการอัปเดตที่พร้อมใช้",
    installing: "กำลังติดตั้ง…",
    checkUpdate: "ตรวจสอบการอัปเดตแอป",
    updateErrorWithCache: "ไม่สามารถตรวจสอบการอัปเดตได้ แอปที่บันทึกและตรวจสอบแล้วยังใช้งานได้",
    updateErrorWithoutCache: "ไม่สามารถตรวจสอบการอัปเดตได้ และยังไม่มีแอปที่บันทึกไว้ครบถ้วน โปรดเชื่อมต่อและลองอีกครั้ง",
    notChecked: "ยังไม่ได้ตรวจสอบ",
  },
} as const satisfies Record<Language, Record<string, string>>;

export function pwaAvailabilityCopy(language: Language) {
  return PWA_AVAILABILITY_COPY[language];
}

function readableTime(value: string | null, language: Language): string {
  const copy = pwaAvailabilityCopy(language);
  if (!value) return copy.notChecked;
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.valueOf())) return copy.notChecked;
  return new Intl.DateTimeFormat(language === "th" ? "th-TH" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(timestamp);
}

export function requiredOfflinePaths(profile: AppProfile): string[] {
  const publicPaths = [
    "/",
    "/public/",
    "/deployment-profile.json",
    "/offline-demo/mae-sai/public-bundle.json",
    "/offline-demo/mae-sai/public-areas.json",
  ];
  return profile === "public-production"
    ? publicPaths
    : [...publicPaths, "/command/", "/studio/", "/offline-demo/mae-sai/bundle.json"];
}

async function inspectOfflineCache(status: WorkerCacheStatus | null): Promise<CacheState> {
  if (
    !status
    || status.profile !== EXPECTED_PROFILE
    || !("caches" in window)
    || !OFFLINE_CACHE_PATTERN.test(status.cacheName)
  ) return "unavailable";
  const keys = await caches.keys();
  if (!keys.includes(status.cacheName)) return "unavailable";
  const cache = await caches.open(status.cacheName);
  const entries = await Promise.all(requiredOfflinePaths(status.profile).map((path) => cache.match(path)));
  return entries.every(Boolean) ? "ready" : "unavailable";
}

async function requestWorkerStatus(worker: ServiceWorker): Promise<WorkerCacheStatus> {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timeout = window.setTimeout(() => {
      channel.port1.close();
      reject(new Error("Saved-app status request timed out."));
    }, 2500);
    channel.port1.onmessage = (event: MessageEvent<WorkerMessage>) => {
      window.clearTimeout(timeout);
      channel.port1.close();
      const cacheName = event.data?.cache_name;
      const profile = event.data?.profile;
      const cachedAt = event.data?.cached_at;
      if (
        !cacheName
        || (profile !== "competition" && profile !== "public-production")
        || !cachedAt
        || Number.isNaN(new Date(cachedAt).valueOf())
      ) {
        reject(new Error("Saved-app status response is invalid."));
        return;
      }
      resolve({ cacheName, profile, cachedAt });
    };
    worker.postMessage({ type: "FLOODGUARD_STATUS_REQUEST" }, [channel.port2]);
  });
}

async function removeDevelopmentWorker(): Promise<boolean> {
  if (!("serviceWorker" in navigator)) return false;
  const wasControlled = Boolean(navigator.serviceWorker.controller);
  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations
    .filter((registration) => registration.active?.scriptURL.endsWith("/sw.js") || registration.installing?.scriptURL.endsWith("/sw.js") || registration.waiting?.scriptURL.endsWith("/sw.js"))
    .map((registration) => registration.unregister()));
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => OFFLINE_CACHE_PATTERN.test(key)).map((key) => caches.delete(key)));
  }
  return wasControlled;
}

export function PwaRegister({ enabled = process.env.NODE_ENV === "production" }: PwaRegisterProps = {}) {
  const pathname = usePathname();
  const defaultLanguage = EXPECTED_PROFILE === "public-production" || pathname?.startsWith("/public") ? "th" : "en";
  const [language] = useLanguage(defaultLanguage);
  const [online, setOnline] = useState<boolean | null>(null);
  const [cacheState, setCacheState] = useState<CacheState>("checking");
  const [updateState, setUpdateState] = useState<UpdateState>("current");
  const [householdPlanAvailable, setHouseholdPlanAvailable] = useState(false);
  const [cachedSnapshotAt, setCachedSnapshotAt] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const registrationRef = useRef<ServiceWorkerRegistration | null>(null);
  const workerStatusRef = useRef<WorkerCacheStatus | null>(null);
  const reloadOnControlRef = useRef(false);

  const refreshHouseholdPlanAvailability = useCallback(() => {
    try {
      setHouseholdPlanAvailable(Boolean(
        window.localStorage.getItem(HOUSEHOLD_PLAN_STORAGE_KEY)
        ?? window.localStorage.getItem(LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY),
      ));
    } catch {
      setHouseholdPlanAvailable(false);
    }
  }, []);

  const refreshAvailability = useCallback(async (status = workerStatusRef.current) => {
    setCacheState("checking");
    setCachedSnapshotAt(status?.cachedAt ?? null);
    try {
      const nextCacheState = await inspectOfflineCache(status);
      setCacheState(nextCacheState);
    } catch {
      setCacheState("unavailable");
    }
  }, []);

  const watchInstallingWorker = useCallback((worker: ServiceWorker | null): (() => void) => {
    if (!worker) return () => undefined;
    setUpdateState("installing");
    const handleStateChange = () => {
      if (worker.state === "installed") {
        setUpdateState(navigator.serviceWorker.controller ? "available" : "current");
      } else if (worker.state === "redundant") {
        setUpdateState("error");
      }
    };
    worker.addEventListener("statechange", handleStateChange);
    return () => worker.removeEventListener("statechange", handleStateChange);
  }, []);

  useEffect(() => {
    let active = true;
    let registration: ServiceWorkerRegistration | null = null;
    let stopWatchingWorker: () => void = () => undefined;
    let handleUpdateFound: (() => void) | null = null;

    if (!enabled) {
      void removeDevelopmentWorker().then((wasControlled) => {
        if (active && wasControlled) window.location.reload();
      }).catch(() => {
        // Development remains network-only if browser cleanup is restricted.
      });
      return () => { active = false; };
    }

    if (!("serviceWorker" in navigator)) {
      queueMicrotask(() => {
        if (!active) return;
        setOnline(navigator.onLine);
        setCacheState("unavailable");
        setUpdateState("error");
        refreshHouseholdPlanAvailability();
      });
      return () => { active = false; };
    }

    queueMicrotask(() => {
      if (!active) return;
      setOnline(navigator.onLine);
      try {
        setLastRefresh(window.localStorage.getItem(LAST_REFRESH_KEY));
      } catch {
        setLastRefresh(null);
      }
      refreshHouseholdPlanAvailability();
    });

    const synchronizeActiveWorker = async (currentRegistration: ServiceWorkerRegistration) => {
      const readyRegistration = await navigator.serviceWorker.ready;
      if (!active || readyRegistration.scope !== currentRegistration.scope) return;
      const worker = readyRegistration.active ?? navigator.serviceWorker.controller;
      if (!worker) throw new Error("Saved app has no active worker.");
      const status = await requestWorkerStatus(worker);
      if (!active) return;
      if (status.profile !== EXPECTED_PROFILE) {
        workerStatusRef.current = null;
        setCachedSnapshotAt(null);
        setCacheState("unavailable");
        setUpdateState(
          currentRegistration.waiting
            ? "available"
            : currentRegistration.installing
              ? "installing"
              : "error",
        );
        return;
      }
      workerStatusRef.current = status;
      await refreshAvailability(status);
    };
    const handleOnline = () => {
      setOnline(true);
      void refreshAvailability();
    };
    const handleOffline = () => setOnline(false);
    const handleStorage = (event: StorageEvent) => {
      if (event.key === HOUSEHOLD_PLAN_STORAGE_KEY || event.key === LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY) {
        setHouseholdPlanAvailable(Boolean(event.newValue));
      }
    };
    const handleControllerChange = () => {
      if (reloadOnControlRef.current) {
        window.location.reload();
        return;
      }
      const currentRegistration = registrationRef.current;
      if (currentRegistration) void synchronizeActiveWorker(currentRegistration).catch(() => setCacheState("unavailable"));
    };
    const handleWorkerMessage = (event: MessageEvent<WorkerMessage>) => {
      if (event.data?.type !== "FLOODGUARD_CACHE_READY") return;
      const cacheName = event.data.cache_name;
      const profile = event.data.profile;
      const cachedAt = event.data.cached_at;
      if (
        !cacheName
        || (profile !== "competition" && profile !== "public-production")
        || !cachedAt
        || Number.isNaN(new Date(cachedAt).valueOf())
      ) return;
      if (profile !== EXPECTED_PROFILE) {
        workerStatusRef.current = null;
        setCachedSnapshotAt(null);
        setCacheState("unavailable");
        const currentRegistration = registrationRef.current;
        setUpdateState(
          currentRegistration?.waiting
            ? "available"
            : currentRegistration?.installing
              ? "installing"
              : "error",
        );
        return;
      }
      const status = { cacheName, profile, cachedAt } satisfies WorkerCacheStatus;
      workerStatusRef.current = status;
      void refreshAvailability(status);
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("focus", refreshHouseholdPlanAvailability);
    window.addEventListener("storage", handleStorage);
    navigator.serviceWorker.addEventListener("controllerchange", handleControllerChange);
    navigator.serviceWorker.addEventListener("message", handleWorkerMessage);

    navigator.serviceWorker.register("/sw.js").then((nextRegistration) => {
      if (!active) return;
      registration = nextRegistration;
      registrationRef.current = nextRegistration;
      if (nextRegistration.waiting) setUpdateState("available");
      stopWatchingWorker = watchInstallingWorker(nextRegistration.installing);
      handleUpdateFound = () => {
        stopWatchingWorker();
        stopWatchingWorker = watchInstallingWorker(nextRegistration.installing);
      };
      nextRegistration.addEventListener("updatefound", handleUpdateFound);
      void synchronizeActiveWorker(nextRegistration).catch(() => {
        if (active) setCacheState("unavailable");
      });
    }).catch(() => {
      if (active) setUpdateState("error");
    });

    return () => {
      active = false;
      stopWatchingWorker();
      if (registration && handleUpdateFound) registration.removeEventListener("updatefound", handleUpdateFound);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("focus", refreshHouseholdPlanAvailability);
      window.removeEventListener("storage", handleStorage);
      navigator.serviceWorker.removeEventListener("controllerchange", handleControllerChange);
      navigator.serviceWorker.removeEventListener("message", handleWorkerMessage);
    };
  }, [enabled, refreshAvailability, refreshHouseholdPlanAvailability, watchInstallingWorker]);

  const checkForUpdate = useCallback(async () => {
    const registration = registrationRef.current;
    if (!registration) {
      setUpdateState("error");
      return;
    }
    setUpdateState("checking");
    try {
      await registration.update();
      setUpdateState(registration.waiting ? "available" : "current");
      await refreshAvailability();
      const checkedAt = new Date().toISOString();
      setLastRefresh(checkedAt);
      try {
        window.localStorage.setItem(LAST_REFRESH_KEY, checkedAt);
      } catch {
        // A successful network update check remains valid when persistence is restricted.
      }
    } catch {
      setUpdateState("error");
    }
  }, [refreshAvailability]);

  const applyUpdate = useCallback(() => {
    const waiting = registrationRef.current?.waiting;
    if (!waiting) return;
    reloadOnControlRef.current = true;
    setUpdateState("installing");
    waiting.postMessage({ type: "SKIP_WAITING" });
  }, []);

  if (!enabled) return null;

  const copy = pwaAvailabilityCopy(language);
  const connectionLabel = online === null ? copy.checkingConnection : online ? copy.online : copy.offline;
  const summaryLabel = cacheState === "ready"
    ? `${connectionLabel} · ${copy.savedAppReady}`
    : connectionLabel;

  return (
    <details
      className={styles.panel}
      data-pwa-availability="true"
      onToggle={(event) => {
        if (!event.currentTarget.open) return;
        refreshHouseholdPlanAvailability();
        void refreshAvailability();
      }}
    >
      <summary>
        <span className={`${styles.dot} ${online === false ? styles.offline : ""}`} aria-hidden="true" />
        <span role="status" aria-live="polite">{summaryLabel}</span>
      </summary>
      <div className={styles.body}>
        <div className={styles.heading}>
          <div>
            <strong>{copy.heading}</strong>
            <small>{copy.subtitle}</small>
          </div>
          <span className={online === false ? styles.warning : styles.good}>{connectionLabel}</span>
        </div>
        <dl className={styles.statusList}>
          <div>
            <dt>{copy.savedPlanningView}</dt>
            <dd>{cacheState === "checking" ? copy.checking : cacheState === "ready" ? copy.availableOffline : copy.openOnlineToSave}</dd>
          </div>
          <div>
            <dt>{copy.householdPlan}</dt>
            <dd>{householdPlanAvailable ? copy.savedOnDevice : copy.noPlanSaved}</dd>
          </div>
          <div>
            <dt>{copy.floodContext}</dt>
            <dd>{copy.historicalContext}</dd>
          </div>
          <div>
            <dt>{copy.cachedSnapshot}</dt>
            <dd>{readableTime(cachedSnapshotAt, language)}</dd>
          </div>
          <div>
            <dt>{copy.lastUpdateCheck}</dt>
            <dd>{readableTime(lastRefresh, language)}</dd>
          </div>
          <div>
            <dt>{copy.mapBackgrounds}</dt>
            <dd>{online === false ? copy.backgroundsOffline : copy.backgroundsOnline}</dd>
          </div>
        </dl>
        <p>{copy.disclosure}</p>
        {updateState === "available" ? (
          <button type="button" onClick={applyUpdate}>{copy.installUpdate}</button>
        ) : (
          <button type="button" onClick={() => void checkForUpdate()} disabled={updateState === "checking" || updateState === "installing"}>
            {updateState === "checking" ? copy.checking : updateState === "installing" ? copy.installing : copy.checkUpdate}
          </button>
        )}
        {updateState === "error" && (
          <small className={styles.error}>
            {cacheState === "ready"
              ? copy.updateErrorWithCache
              : copy.updateErrorWithoutCache}
          </small>
        )}
      </div>
    </details>
  );
}
