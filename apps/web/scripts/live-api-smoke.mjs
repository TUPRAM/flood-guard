import { chromium } from "@playwright/test";

const webBase = process.env.FLOODGUARD_WEB_URL ?? "http://127.0.0.1:3000";
const apiBase = process.env.FLOODGUARD_API_URL ?? "http://127.0.0.1:8000";
const allowedOrigins = new Set([new URL(webBase).origin, new URL(apiBase).origin]);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(180_000);
page.setDefaultNavigationTimeout(180_000);
const browserErrors = [];
const unexpectedRequests = [];

page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("request", (request) => {
  const url = new URL(request.url());
  if (!allowedOrigins.has(url.origin)) unexpectedRequests.push(request.url());
});
page.on("requestfailed", (request) => {
  browserErrors.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText ?? "failed"}`);
});

try {
  await page.goto(`${webBase}/command/`, { waitUntil: "domcontentloaded" });
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
  assertIncludesIgnoreCase(await page.getByLabel("Data status").innerText(), "Candidate data", "candidate disclosure");
  assertIncludesIgnoreCase(await page.getByLabel("Data status").innerText(), "Stale data", "stale disclosure");
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

  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "TH570906"
    && document.querySelector(".geo-map-shell")?.getAttribute("data-road-detail-state") === "ready"
  ));
  const defaultDetailFeatureCount = Number(await map.getAttribute("data-road-feature-count"));
  if (!Number.isInteger(defaultDetailFeatureCount) || defaultDetailFeatureCount <= 750) {
    throw new Error(`Default selected-area road detail was not merged: ${defaultDetailFeatureCount}`);
  }

  await page.getByLabel("Select reporting area").selectOption("TH570903");
  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "TH570903"
    && document.querySelector(".geo-map-shell")?.getAttribute("data-road-detail-state") === "ready"
  ));
  const selectedRoadFeatureCount = Number(await map.getAttribute("data-road-feature-count"));
  if (!Number.isInteger(selectedRoadFeatureCount) || selectedRoadFeatureCount < 750) {
    throw new Error(`Selected-area road detail produced an invalid merged count: ${selectedRoadFeatureCount}`);
  }
  assertIncludes(await page.getByLabel("Select scenario").locator("option").nth(1).innerText(), "Temporary facility candidate", "candidate scenario label");
  await page.getByLabel("Select scenario").selectOption("add_temporary_shelter");
  await waitForScenario(page, "add_temporary_shelter");
  const shelterStrip = await page.locator(".scenario-delta-strip").innerText();
  const shelterPanel = await page.locator(".scenario-evidence-comparison").innerText();
  assertIncludes(shelterStrip, "13 people lose 30-min access", "temporary-facility result");
  assertSignedDelta(shelterStrip, -177, "temporary-facility delta");
  assertSignedDelta(shelterPanel, -177, "temporary-facility evidence panel");
  assertEqual(await map.getAttribute("data-scenario-tone"), "improves", "temporary-facility map tone");

  await page.getByLabel("Select scenario").selectOption("close_road");
  await waitForScenario(page, "close_road");
  const roadStrip = await page.locator(".scenario-delta-strip").innerText();
  const roadPanel = await page.locator(".scenario-evidence-comparison").innerText();
  assertIncludes(roadStrip, "219 people lose 30-min access", "road-stress result");
  assertSignedDelta(roadStrip, 29, "road-stress delta");
  assertSignedDelta(roadPanel, 29, "road-stress evidence panel");
  assertEqual(await map.getAttribute("data-scenario-tone"), "worsens", "road-stress map tone");

  if (unexpectedRequests.length > 0) {
    throw new Error(`Unexpected external requests: ${[...new Set(unexpectedRequests)].join(", ")}`);
  }
  if (browserErrors.length > 0) {
    throw new Error(`Browser errors: ${[...new Set(browserErrors)].join(" | ")}`);
  }
  console.log("Live API smoke passed: 8 areas, 750 bounded regional roads / 4,458 total, selected-area detail, 42 facilities, 8 access points.");
  console.log("Server scenarios passed: temporary facility -177; road stress +29; map and evidence panel synchronized.");
} finally {
  await browser.close();
}

async function waitForScenario(page, scenarioId) {
  await page.waitForFunction((expected) => (
    document.querySelector('aside[aria-label="Decision evidence"]')?.getAttribute("data-scenario-id") === expected
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
