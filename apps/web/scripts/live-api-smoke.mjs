import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const webBase = process.env.FLOODGUARD_WEB_URL ?? "http://127.0.0.1:3000";
const apiBase = process.env.FLOODGUARD_API_URL ?? "http://127.0.0.1:8000";
const timeoutMs = Number(process.env.FLOODGUARD_SMOKE_TIMEOUT_MS ?? 180_000);
const basemapOrigins = new Set([
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const allowedOrigins = new Set([new URL(webBase).origin, new URL(apiBase).origin, ...basemapOrigins]);
const basemapOriginsSeen = new Set();
const browser = await launchFloodGuardBrowser();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(timeoutMs);
page.setDefaultNavigationTimeout(timeoutMs);
const browserErrors = [];
const unexpectedRequests = [];
const apiRequestsBySurface = new Map([
  ["public", []],
  ["command", []],
  ["studio", []],
]);
let activeSurface = "startup";

page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("request", (request) => {
  const url = new URL(request.url());
  if (basemapOrigins.has(url.origin)) basemapOriginsSeen.add(url.origin);
  if (url.origin === new URL(apiBase).origin && apiRequestsBySurface.has(activeSurface)) {
    apiRequestsBySurface.get(activeSurface).push(url);
  }
  if (!allowedOrigins.has(url.origin)) unexpectedRequests.push(request.url());
});
page.on("requestfailed", (request) => {
  const errorText = request.failure()?.errorText ?? "failed";
  const origin = new URL(request.url()).origin;
  // Leaflet cancels tiles that leave the viewport or belong to the previous
  // basemap while a layer switch is in progress. A loaded tile is asserted for
  // every provider below, so these expected cancellations are not availability
  // failures.
  if (basemapOrigins.has(origin) && errorText === "net::ERR_ABORTED") return;
  browserErrors.push(`${request.method()} ${request.url()}: ${errorText}`);
});

try {
  const publicLayerResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.origin === new URL(apiBase).origin
      && url.pathname.endsWith("/api/v1/layer-data/public_preparedness_areas")
      && url.searchParams.get("role") === "public";
  });
  const publicContext = await openSurfaceWithContext(page, "public", "/public/", "main.public-page");
  const publicLayerResponse = await publicLayerResponsePromise;
  if (!publicLayerResponse.ok()) {
    throw new Error(`Public preparedness layer returned ${publicLayerResponse.status()}.`);
  }
  await page.waitForFunction(() => (
    document.querySelectorAll("#public-area-select option").length === 9
    && document.querySelector(".public-boundary-detail") === null
  ));
  assertRoleProjectionRequests("public", apiRequestsBySurface.get("public"));

  const commandContextTuple = await openSurfaceWithContext(page, "command", "/command/", "main.command-page");
  await page.waitForFunction(() => {
    const scenario = document.querySelector('select[aria-label="Select scenario"]');
    return scenario instanceof HTMLSelectElement
      && !scenario.disabled
      && scenario.options.length === 3;
  }, undefined, { timeout: 180_000 });

  const map = page.locator(".geo-map-shell");
  assertEqual(await map.getAttribute("data-regional-road-count"), "750", "bounded regional road count");
  assertEqual(await map.getAttribute("data-road-dataset-total"), "4458", "road dataset total");
  assertEqual(await map.getAttribute("data-facility-feature-count"), "42", "facility feature count");
  assertEqual(await map.getAttribute("data-access-feature-count"), "8", "access evidence count");
  const commandContext = await page.locator(".command-context-bar").innerText();
  assertIncludesIgnoreCase(commandContext, "Planning intelligence", "planning context");
  assertIncludesIgnoreCase(commandContext, "Source time", "source timestamp label");
  assertIncludesIgnoreCase(commandContext, "Confidence", "confidence label");
  assertIncludesIgnoreCase(commandContext, "DDPM", "official verification boundary");
  const liveAttribution = page.getByLabel("Map data attribution");
  const liveAttributionText = await liveAttribution.innerText();
  for (const requiredAttribution of ["HDX", "FloodGuard", "© OpenStreetMap contributors", "Geofabrik"]) {
    assertIncludes(liveAttributionText, requiredAttribution, "live map attribution");
  }
  assertEqual(
    await liveAttribution.locator('a[href="https://www.openstreetmap.org/copyright"]').count(),
    1,
    "OpenStreetMap copyright link",
  );
  await exerciseOnlineBasemaps(page, ".map-workspace");

  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "TH570903"
    && document.querySelector(".geo-map-shell")?.getAttribute("data-road-detail-state") === "ready"
  ));
  const defaultDetailFeatureCount = Number(await map.getAttribute("data-road-feature-count"));
  // The default Ko Chang area already contributes all 451 of its roads to the
  // 750-road regional overview. Replacing that subset with the selected-area
  // response therefore preserves the total rather than increasing it.
  if (!Number.isInteger(defaultDetailFeatureCount) || defaultDetailFeatureCount < 750) {
    throw new Error(`Default selected-area road detail was not merged: ${defaultDetailFeatureCount}`);
  }

  assertIncludes(await page.getByLabel("Select scenario").locator("option").nth(1).innerText(), "Temporary facility option", "temporary-facility scenario label");
  await page.getByLabel("Select scenario").selectOption("add_temporary_shelter");
  await waitForScenario(page, "add_temporary_shelter");
  await page.getByRole("tab", { name: "Scenario" }).click();
  const shelterStrip = await page.locator(".scenario-delta-strip").innerText();
  const shelterPanel = await page.locator(".command-release-panel .scenario-evidence-comparison").innerText();
  assertIncludes(shelterStrip, "4,877 people lose 30-min access", "temporary-facility result");
  assertSignedDelta(shelterStrip, -917, "temporary-facility delta");
  assertSignedDelta(shelterPanel, -917, "temporary-facility evidence panel");
  assertEqual(await map.getAttribute("data-scenario-tone"), "improves", "temporary-facility map tone");

  await page.locator(".ranked-areas button").filter({ hasText: "Mae Sai" }).first().click();
  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "TH570901"
    && document.querySelector(".geo-map-shell")?.getAttribute("data-road-detail-state") === "ready"
  ));
  const maeSaiDetailFeatureCount = Number(await map.getAttribute("data-road-feature-count"));
  if (!Number.isInteger(maeSaiDetailFeatureCount) || maeSaiDetailFeatureCount <= 750) {
    throw new Error(`Mae Sai selected-area road detail was not merged: ${maeSaiDetailFeatureCount}`);
  }
  await page.getByLabel("Select scenario").selectOption("close_road");
  await waitForScenario(page, "close_road");
  const roadStrip = await page.locator(".scenario-delta-strip").innerText();
  const roadPanel = await page.locator(".command-release-panel .scenario-evidence-comparison").innerText();
  assertIncludes(roadStrip, "172 people lose 30-min access", "road-stress result");
  assertSignedDelta(roadStrip, 98, "road-stress delta");
  assertSignedDelta(roadPanel, 98, "road-stress evidence panel");
  assertEqual(await map.getAttribute("data-scenario-tone"), "worsens", "road-stress map tone");

  const bodyText = await page.locator("body").innerText();
  const forbidden = /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|fixtures?|candidates?|synthetic|non[-_ ]?operational|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula|processing_scope|can_feed_decision_layer/iu;
  const forbiddenMatch = bodyText.match(forbidden);
  if (forbiddenMatch) {
    throw new Error(`Command surface exposes forbidden internal copy: ${forbiddenMatch[0]}.`);
  }
  assertRoleProjectionRequests("command", apiRequestsBySurface.get("command"));

  const studioModelResponsesPromise = Promise.all([
    "/api/v1/model-registry",
    "/api/v1/model-evaluations",
    "/api/v1/observation-products",
  ].map((path) => page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.origin === new URL(apiBase).origin
      && url.pathname === path
      && url.searchParams.get("study_area") === "mae_sai_candidate_v1";
  })));
  const studioContext = await openSurfaceWithContext(page, "studio", "/studio/", "main.studio-page");
  const studioModelResponses = await studioModelResponsesPromise;
  for (const response of studioModelResponses) {
    if (!response.ok()) {
      throw new Error(`Studio model evidence request returned ${response.status()}: ${response.url()}`);
    }
  }
  await page.locator("#evidence-context-title").waitFor({ state: "visible" });
  await page.waitForFunction((contextId) => (
    document.querySelector("main.studio-page")?.textContent?.includes(contextId)
    && document.querySelector(".fallback-reason") === null
  ), studioContext.evidence_context_id);
  assertRoleProjectionRequests("studio", apiRequestsBySurface.get("studio"));
  await page.getByRole("tab", { name: "Models & evaluation" }).click();
  await page.locator("#model-registry-title").waitFor({ state: "visible" });
  const registryText = await page.locator("#studio-tab-panel").innerText();
  for (const required of [
    "No model evaluation is bound to this evidence context",
    "External algorithmic baseline",
    "No real-event evaluation",
    "Report only",
    "No controlled evaluation was executed",
    "Remain unknown; never treated as dry",
    "Browser cryptographic status: not verified",
    "The API and repository are the authority for cryptographic verification.",
    "0%",
    "100%",
  ]) {
    assertIncludes(registryText, required, `Studio live model registry ${required}`);
  }
  if (registryText.includes("Signature authority")) {
    throw new Error("Studio live model registry overstates browser signature authority.");
  }
  assertContextTupleEqual(publicContext, commandContextTuple, "Public and Command");
  assertContextTupleEqual(publicContext, studioContext, "Public and Studio");
  for (const origin of basemapOrigins) {
    if (!basemapOriginsSeen.has(origin)) {
      throw new Error(`Command basemap selector never requested approved provider ${origin}.`);
    }
  }

  if (unexpectedRequests.length > 0) {
    throw new Error(`Unexpected external requests: ${[...new Set(unexpectedRequests)].join(", ")}`);
  }
  if (browserErrors.length > 0) {
    throw new Error(`Browser errors: ${[...new Set(browserErrors)].join(" | ")}`);
  }
  console.log("Live API smoke passed: Public, Command, and Studio share one immutable Mae Sai evidence context; Public uses only its reduced role projection.");
  console.log("Command API smoke passed: 8 areas, 750 bounded regional roads / 4,458 total, selected-area detail, 42 categorized facilities, 8 access points, and three basemap providers.");
  console.log("Server scenarios passed: TH570903 temporary facility -917; TH570901 road stress +98; map and evidence panel synchronized.");
} finally {
  await browser.close();
}

async function openSurfaceWithContext(page, surface, route, selector) {
  activeSurface = surface;
  const contextResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.origin === new URL(apiBase).origin
      && url.pathname.endsWith("/api/v1/evidence-context")
      && url.searchParams.get("study_area") === "mae_sai_candidate_v1";
  });
  await page.goto(`${webBase}${route}`, { waitUntil: "domcontentloaded" });
  await page.locator(selector).waitFor({ state: "visible" });
  let contextResponse;
  try {
    contextResponse = await contextResponsePromise;
  } catch (error) {
    const requests = (apiRequestsBySurface.get(surface) ?? []).map((url) => url.href);
    throw new Error(
      `${surface} did not receive its evidence-context response. `
      + `API requests: ${requests.length > 0 ? requests.join(", ") : "none"}. `
      + `Browser errors: ${browserErrors.length > 0 ? browserErrors.join(" | ") : "none"}.`,
      { cause: error },
    );
  }
  if (!contextResponse.ok()) {
    throw new Error(`${surface} evidence-context request returned ${contextResponse.status()}.`);
  }
  const context = await contextResponse.json();
  if (
    context?.study_area_id !== "mae_sai_candidate_v1"
    || typeof context?.evidence_context_id !== "string"
    || typeof context?.data_version !== "string"
    || typeof context?.evidence_package_id !== "string"
    || typeof context?.evidence_package_sha256 !== "string"
  ) {
    throw new Error(`${surface} returned an incomplete or incorrect evidence context: ${JSON.stringify(context)}`);
  }
  return context;
}

function assertRoleProjectionRequests(surface, requests = []) {
  const apiRequests = requests.filter((url) => url.pathname.includes("/api/v1/"));
  const modelEvidencePaths = [
    "/api/v1/model-registry",
    "/api/v1/model-evaluations",
    "/api/v1/observation-products",
  ];
  const requiredPaths = [
    "/api/v1/status",
    "/api/v1/evidence-context",
    "/api/v1/public-areas",
    "/api/v1/layers",
  ];
  if (surface !== "public") requiredPaths.push("/api/v1/areas");
  for (const required of requiredPaths) {
    if (!apiRequests.some((url) => url.pathname.endsWith(required))) {
      throw new Error(`${surface} did not request required context artifact ${required}.`);
    }
  }
  const layerCatalogRequest = apiRequests.find((url) => url.pathname.endsWith("/api/v1/layers"));
  if (layerCatalogRequest?.searchParams.get("role") !== surface) {
    throw new Error(`${surface} layer catalog request did not enforce role=${surface}.`);
  }
  if (!apiRequests.some((url) => url.pathname.includes("/api/v1/evidence-records/"))) {
    throw new Error(`${surface} did not request its context-bound evidence record.`);
  }
  if (surface === "studio") {
    for (const required of modelEvidencePaths) {
      const request = apiRequests.find((url) => url.pathname === required);
      if (!request) {
        throw new Error(`Studio did not request required model evidence ${required}.`);
      }
      if (request.searchParams.get("study_area") !== "mae_sai_candidate_v1") {
        throw new Error(`Studio model evidence request was not study-area scoped: ${request.href}`);
      }
    }
  } else {
    const forbiddenModelRequest = apiRequests.find((url) => (
      modelEvidencePaths.includes(url.pathname)
    ));
    if (forbiddenModelRequest) {
      throw new Error(
        `${surface} requested Studio-only model evidence: ${forbiddenModelRequest.href}`,
      );
    }
  }
  if (surface === "public") {
    const forbidden = apiRequests.find((url) => (
      url.pathname.endsWith("/api/v1/areas")
      || /\/(?:road_risk|facilities|access_hotspots)(?:\/|$)/u.test(url.pathname)
      || url.pathname.includes("/api/v1/scenario")
    ));
    if (forbidden) throw new Error(`Public requested staff-only API data: ${forbidden.href}`);
  }
}

function assertContextTupleEqual(left, right, label) {
  const tupleKeys = [
    "evidence_context_id",
    "study_area_id",
    "data_version",
    "evidence_package_id",
    "evidence_package_sha256",
    "model_run_id",
    "dataset_mode",
    "operational_status",
  ];
  const leftTuple = Object.fromEntries(tupleKeys.map((key) => [key, left[key] ?? null]));
  const rightTuple = Object.fromEntries(tupleKeys.map((key) => [key, right[key] ?? null]));
  if (JSON.stringify(leftTuple) !== JSON.stringify(rightTuple)) {
    throw new Error(`${label} evidence-context tuple mismatch: ${JSON.stringify({ left: leftTuple, right: rightTuple })}`);
  }
}

async function exerciseOnlineBasemaps(page, scopeSelector) {
  const buttons = page.locator(`${scopeSelector} .map-basemap-switcher button`);
  if (await buttons.count() !== 3) {
    throw new Error("Command map must expose Street, Satellite, and Terrain backgrounds.");
  }
  const labels = await buttons.allTextContents();
  if (labels.map((label) => label.trim()).join("|") !== "Street|Satellite|Terrain") {
    throw new Error(`Command map backgrounds are mislabeled: ${labels.join(", ")}.`);
  }
  for (const [index, basemap] of ["street", "satellite", "terrain"].entries()) {
    await buttons.nth(index).click();
    await page.waitForFunction(
      ({ scope, expectedBasemap }) => {
        const element = document.querySelector(`${scope} .geo-map-shell`);
        const tiles = [...document.querySelectorAll(`${scope} .leaflet-tile-pane img.leaflet-tile-loaded`)];
        return element?.getAttribute("data-basemap") === expectedBasemap
          && element?.getAttribute("data-basemap-state") === "ready"
          && tiles.some((tile) => tile instanceof HTMLImageElement
            && tile.complete
            && tile.naturalWidth > 0);
      },
      { scope: scopeSelector, expectedBasemap: basemap },
      { timeout: 30_000 },
    );
    await page.waitForTimeout(750);
    if (await buttons.nth(index).getAttribute("aria-pressed") !== "true") {
      throw new Error(`Command map did not expose ${basemap} as selected.`);
    }
    const attribution = await page.locator(`${scopeSelector} .map-attribution`).innerText();
    const expectedAttribution = basemap === "street"
      ? "OpenStreetMap contributors"
      : basemap === "satellite"
        ? "Esri World Imagery"
        : "OpenTopoMap";
    if (!attribution.includes(expectedAttribution)) {
      throw new Error(`Command ${basemap} background is missing ${expectedAttribution} attribution.`);
    }
  }
  await buttons.first().click();
  await page.waitForFunction(
    (scope) => {
      const element = document.querySelector(`${scope} .geo-map-shell`);
      return element?.getAttribute("data-basemap") === "street"
        && element?.getAttribute("data-basemap-state") === "ready";
    },
    scopeSelector,
    { timeout: 30_000 },
  );
}

async function waitForScenario(page, scenarioId) {
  await page.waitForFunction((expected) => (
    document.querySelector(".command-release-panel")?.getAttribute("data-scenario-id") === expected
    && document.querySelector(".geo-map-shell")?.getAttribute("data-scenario-id") === expected
  ), scenarioId);
}

function assertIncludes(actual, expected, label) {
  if (!actual.includes(expected)) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)} in ${JSON.stringify(actual)}`);
  }
}

function assertIncludesIgnoreCase(actual, expected, label) {
  assertIncludes(actual.toLocaleLowerCase("en-US"), expected.toLocaleLowerCase("en-US"), label);
}

function assertSignedDelta(actual, expected, label) {
  const expectedText = expected > 0 ? `+${expected}` : String(expected);
  assertIncludes(actual, expectedText, label);
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
  }
}
