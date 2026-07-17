const CACHE_NAME = "floodguard-offline-__BUILD__";
const PROPOSAL_EVIDENCE_ASSETS = []; /* __PROPOSAL_EVIDENCE_ASSETS__ */
const CORE_ASSETS = [
  "/public/",
  "/command/",
  "/studio/",
  "/manifest.webmanifest",
  "/icon.svg",
  "/offline-demo/bundle.json",
  "/offline-demo/areas.geojson",
  "/offline-demo/roads.geojson",
  ...PROPOSAL_EVIDENCE_ASSETS
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    Promise.all([
      caches.open(CACHE_NAME),
      fetch("/offline-assets.json").then((response) => {
        if (!response.ok) throw new Error("Offline asset manifest is unavailable");
        return response.json();
      })
    ]).then(([cache, generatedAssets]) => cache.addAll([...CORE_ASSETS, ...generatedAssets]))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (event.request.method !== "GET" || requestUrl.origin !== self.location.origin || requestUrl.pathname.startsWith("/api/")) {
    return;
  }
  const isMutableRequest =
    event.request.mode === "navigate" ||
    CORE_ASSETS.includes(requestUrl.pathname) ||
    requestUrl.pathname === "/offline-assets.json" ||
    requestUrl.pathname === "/sw.js";

  if (isMutableRequest) {
    event.respondWith(
      fetch(event.request)
        .then((response) => cacheSuccessfulResponse(event.request, response))
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(
      (cached) =>
        cached ||
        fetch(event.request).then((response) => cacheSuccessfulResponse(event.request, response))
    )
  );
});

function cacheSuccessfulResponse(request, response) {
  if (response.ok) {
    const copy = response.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
  }
  return response;
}
