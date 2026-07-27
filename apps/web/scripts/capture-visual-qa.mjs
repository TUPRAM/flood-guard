import { createReadStream, existsSync, mkdirSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const out = resolve(process.cwd(), "out");
const positionalArgs = process.argv.slice(2).filter((argument) => argument !== "--");
if (positionalArgs.length > 1) {
  throw new Error(`Expected at most one evidence directory, received: ${positionalArgs.join(", ")}`);
}
const evidenceDir = positionalArgs[0]
  ? resolve(positionalArgs[0])
  : resolve(process.cwd(), "..", "..", "docs", "visual-qa", "proposal-stage");
if (!existsSync(resolve(out, "public", "index.html"))) {
  throw new Error("Build output is missing; run the production build first.");
}
mkdirSync(evidenceDir, { recursive: true });

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

const server = createServer((request, response) => {
  const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
  const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
  let filePath = resolve(out, relativePath || "index.html");
  if (!filePath.startsWith(`${out}${sep}`) && filePath !== out) {
    response.writeHead(403).end("Forbidden");
    return;
  }
  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    filePath = resolve(filePath, "index.html");
  }
  if (!existsSync(filePath) || !statSync(filePath).isFile()) {
    response.writeHead(404).end("Not found");
    return;
  }
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": contentTypes[extname(filePath)] ?? "application/octet-stream",
    "Service-Worker-Allowed": "/",
  });
  createReadStream(filePath).pipe(response);
});

await new Promise((resolveListen, rejectListen) => {
  server.once("error", rejectListen);
  server.listen(0, "127.0.0.1", resolveListen);
});
const address = server.address();
if (!address || typeof address === "string") throw new Error("Static server did not bind.");
const baseUrl = `http://127.0.0.1:${address.port}`;

const browser = await launchFloodGuardBrowser();

const captures = [
  { route: "/public/", selector: "main.public-page", width: 390, height: 844, file: "public-home-390x844.png", publicTab: "home", readySelector: ".public-home-page .leaflet-container", selectArea: true, basemap: "satellite", cycleBasemaps: true },
  { route: "/public/", selector: "main.public-page", width: 390, height: 844, file: "public-report-390x844.png", publicTab: "report", readySelector: ".public-report-page", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 390, height: 844, file: "public-shelter-390x844.png", publicTab: "shelter", readySelector: ".public-shelter-page", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 390, height: 844, file: "public-prepare-390x844.png", publicTab: "prepare", readySelector: "#household-plan-builder", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 390, height: 844, file: "public-sos-390x844.png", publicTab: "sos", readySelector: ".public-sos-page", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 1440, height: 900, file: "public-home-1440x900.png", publicTab: "home", readySelector: ".public-home-page .leaflet-container", selectArea: true, basemap: "street" },
  { route: "/public/", selector: "main.public-page", width: 1280, height: 800, file: "public-report-1280x800.png", publicTab: "report", readySelector: ".public-report-page", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 1280, height: 800, file: "public-shelter-1280x800.png", publicTab: "shelter", readySelector: ".public-shelter-page", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 1280, height: 800, file: "public-prepare-1280x800.png", publicTab: "prepare", readySelector: "#household-plan-builder", selectArea: true },
  { route: "/public/", selector: "main.public-page", width: 1280, height: 800, file: "public-sos-1280x800.png", publicTab: "sos", readySelector: ".public-sos-page", selectArea: true },
  { route: "/command/", selector: "main.command-page", width: 1024, height: 768, file: "command-1024x768.png", basemap: "street", cycleBasemaps: true },
  { route: "/command/", selector: "main.command-page", width: 1440, height: 900, file: "command-1440x900.png", basemap: "street" },
  { route: "/command/", selector: "main.command-page", width: 1536, height: 1024, file: "command-1536x1024.png", basemap: "satellite" },
  { route: "/studio/", selector: "main.studio-page", width: 2048, height: 1152, file: "studio-2048x1152.png" },
];
const approvedBasemapOrigins = new Set([
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const approvedBasemapOriginsSeen = new Set();
const externalRequests = new Set();
const browserErrors = [];

try {
  for (const capture of captures) {
    const context = await browser.newContext({
      serviceWorkers: "block",
      viewport: { width: capture.width, height: capture.height },
    });
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== baseUrl) {
        if (approvedBasemapOrigins.has(url.origin)) {
          approvedBasemapOriginsSeen.add(url.origin);
          await route.continue();
          return;
        }
        externalRequests.add(url.href);
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => browserErrors.push(`${capture.file}: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(`${capture.file}: ${message.text()}`);
    });

    await page.goto(`${baseUrl}${capture.route}`, { waitUntil: "networkidle" });
    await page.locator(capture.selector).waitFor({ state: "visible" });
    if (capture.publicTab) {
      const manualLocationButton = page.locator(".public-location-consent-actions .secondary");
      if (await manualLocationButton.count() && await manualLocationButton.isVisible()) {
        await manualLocationButton.click();
      }
      if (capture.selectArea) {
        const search = page.locator("#public-area-search");
        await search.fill("TH570901");
        await search.press("Enter");
        await page.waitForFunction(() => (
          document.querySelector(".public-home-page .geo-map-shell")
            ?.getAttribute("data-selected-area") === "TH570901"
        ));
      }
      const tabButton = page.locator(`#public-tab-${capture.publicTab}`);
      if (capture.publicTab !== "home") {
        await page.locator(".public-app-content").evaluate((element) => {
          element.scrollTop = element.scrollHeight;
        });
      }
      await tabButton.click();
      const tabState = await tabButton.evaluate((element) => ({
        current: element.getAttribute("aria-current"),
        pressed: element.getAttribute("aria-pressed"),
        selected: element.getAttribute("aria-selected"),
      }));
      if (tabState.current !== "page" && tabState.pressed !== "true" && tabState.selected !== "true") {
        throw new Error(`${capture.file} did not activate the ${capture.publicTab} public tab.`);
      }
      await page.locator(capture.readySelector).waitFor({ state: "visible" });
      await page.waitForFunction(() => document.querySelector(".public-app-content")?.scrollTop === 0);
    } else if (capture.route === "/command/") {
      await page.locator(".map-workspace .leaflet-container").waitFor({ state: "visible" });
    }

    if (capture.route !== "/public/") {
      await page.locator('.language-toggle button[lang="th"]').click();
      if (await page.locator("html").getAttribute("lang") !== "th") {
        throw new Error(`${capture.file} did not update the document language to Thai.`);
      }
      if (await page.locator('.language-toggle button[lang="th"]').getAttribute("aria-pressed") !== "true") {
        throw new Error(`${capture.file} did not expose the Thai toggle as selected.`);
      }
      const thaiBody = await page.locator("body").innerText();
      if (!/[\u0e00-\u0e7f]/u.test(thaiBody)) {
        throw new Error(`${capture.file} did not render Thai text after switching language.`);
      }
      await page.locator('.language-toggle button[lang="en"]').click();
    }

    if (capture.route === "/command/") {
      await page.waitForFunction(() => (
        document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-road-feature-count") === "4458"
        && document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-facility-feature-count") === "42"
        && document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-access-feature-count") === "8"
      ));
      if (!(await page.locator('select[aria-label="Select scenario"]').isDisabled())) {
        throw new Error(`${capture.file} enabled a planning scenario without the validated analysis service.`);
      }
    }

    const mapScope = capture.route === "/command/"
      ? ".map-workspace"
      : capture.route === "/public/" && capture.publicTab === "home"
        ? ".public-home-page"
        : null;
    if (mapScope) {
      await assertMaeSaiMap(
        page,
        mapScope,
        capture.file,
        capture.route === "/command/",
        capture.route !== "/public/",
        capture.route !== "/public/",
      );
      if (capture.cycleBasemaps) {
        await exerciseOnlineBasemaps(page, mapScope, capture.file);
      }
      await selectOnlineBasemap(page, mapScope, capture.basemap ?? "street", capture.file, true);
    }

    if (capture.route === "/command/" && await page.locator(".ranked-areas button").count() === 0) {
      throw new Error(`${capture.file} is missing the FPPS ranked list.`);
    }
    if (capture.route === "/studio/" && await page.locator("#evidence-context-title").count() !== 1) {
      throw new Error(`${capture.file} is missing the active evidence-context panel.`);
    }

    const pageAudit = await page.evaluate(() => {
      const bodyText = document.body.innerText;
      const mapControls = [...document.querySelectorAll(".leaflet-control-container .leaflet-control, .map-basemap-switcher, .map-basemap-menu, .map-text-alternative")]
        .filter((element) => element instanceof HTMLElement && element.offsetParent !== null)
        .map((element) => {
          const rect = element.getBoundingClientRect();
          return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
        });
      const interactiveElements = [...document.querySelectorAll(
        "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), summary",
      )];
      const measuredElements = [];
      const seenElements = new Set();
      for (const element of interactiveElements) {
        const compositeTarget = element instanceof HTMLInputElement
          && (element.type === "checkbox" || element.type === "radio")
          ? element.closest("label") ?? element
          : element;
        if (
          !(compositeTarget instanceof HTMLElement)
          || compositeTarget.offsetParent === null
          || seenElements.has(compositeTarget)
          || compositeTarget.closest(".leaflet-control-attribution")
        ) {
          continue;
        }
        seenElements.add(compositeTarget);
        measuredElements.push(compositeTarget);
      }
      const touchTargets = measuredElements.map((element) => {
          const rect = element.getBoundingClientRect();
          const accessibleName = element.getAttribute("aria-label")
            ?? element.textContent?.trim().replace(/\s+/gu, " ").slice(0, 80)
            ?? "";
          return {
            selector: element.id
              ? `#${element.id}`
              : element.classList.length > 0
                ? `${element.tagName.toLowerCase()}.${[...element.classList].join(".")}`
                : element.tagName.toLowerCase(),
            accessibleName,
            width: rect.width,
            height: rect.height,
          };
        });
      const publicContent = document.querySelector(".public-app-content")?.getBoundingClientRect();
      const publicHeader = document.querySelector(".public-app-header")?.getBoundingClientRect();
      const publicNavigation = document.querySelector(".public-bottom-nav")?.getBoundingClientRect();
      const publicHomeMap = document.querySelector(".public-home-page .leaflet-container")?.getBoundingClientRect();
      const publicHomeShell = document.querySelector(".public-home-page .geo-map-shell");
      const publicHomeShellStyle = publicHomeShell ? getComputedStyle(publicHomeShell) : null;
      const publicRiskIndicator = document.querySelector(".public-risk-indicator")?.getBoundingClientRect();
      const publicHazardButton = document.querySelector(".public-hazard-button")?.getBoundingClientRect();
      const publicProfileTrigger = document.querySelector(".public-profile-trigger")?.getBoundingClientRect();
      const publicNavigationTargets = [...document.querySelectorAll(".public-bottom-nav button")]
        .map((element) => element.getBoundingClientRect());
      const publicTabIds = [...document.querySelectorAll('.public-bottom-nav [id^="public-tab-"]')]
        .map((element) => element.id);
      const commandWorkspace = document.querySelector(".command-workspace");
      const commandColumnCount = commandWorkspace
        ? getComputedStyle(commandWorkspace).gridTemplateColumns.split(" ").filter(Boolean).length
        : null;
      const proofImages = document.querySelector(".proof-images")?.getBoundingClientRect();
      const proofFigure = document.querySelector(".proof-images figure:only-child")?.getBoundingClientRect();
      const tabletEvidenceDrawer = document.querySelector(".tablet-evidence-drawer")?.getBoundingClientRect();
      return {
        bodyText,
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        mapControls,
        touchTargets,
        publicNavigationOverlap:
          publicContent && publicNavigation
            ? Math.max(0, publicContent.bottom - publicNavigation.top)
            : 0,
        publicHeader: publicHeader
          ? { top: publicHeader.top, bottom: publicHeader.bottom, height: publicHeader.height }
          : null,
        publicNavigation: publicNavigation
          ? { top: publicNavigation.top, bottom: publicNavigation.bottom }
          : null,
        publicHomeMap: publicHomeMap
          ? {
              top: publicHomeMap.top,
              right: publicHomeMap.right,
              bottom: publicHomeMap.bottom,
              left: publicHomeMap.left,
            }
          : null,
        publicHomeAreaFeatureCount: publicHomeShell?.getAttribute("data-area-feature-count") ?? null,
        publicHomeFrame: publicHomeShellStyle
          ? {
              borderWidth: publicHomeShellStyle.borderWidth,
              borderRadius: publicHomeShellStyle.borderRadius,
            }
          : null,
        publicCustomAttributionCount: document.querySelectorAll(".public-home-page p.map-attribution").length,
        publicNativeAttributionVisible: Boolean(
          document.querySelector(".public-home-page .leaflet-control-attribution")?.getClientRects().length,
        ),
        publicLowerControls: publicRiskIndicator && publicHazardButton
          ? {
              risk: {
                left: publicRiskIndicator.left,
                right: publicRiskIndicator.right,
                bottom: publicRiskIndicator.bottom,
              },
              hazard: {
                left: publicHazardButton.left,
                right: publicHazardButton.right,
                bottom: publicHazardButton.bottom,
              },
            }
          : null,
        publicProfileTrigger: publicProfileTrigger
          ? { width: publicProfileTrigger.width, height: publicProfileTrigger.height }
          : null,
        publicNavigationTargets: publicNavigationTargets.map(({ width, height }) => ({ width, height })),
        publicTabIds,
        publicRemovedChromeCount: document.querySelectorAll(".public-brand-mark, .public-boundary-banner").length,
        commandColumnCount,
        proofSingleFigureCoverage:
          proofImages && proofFigure ? proofFigure.width / proofImages.width : null,
        tabletEvidenceDrawer: tabletEvidenceDrawer
          ? {
              left: tabletEvidenceDrawer.left,
              right: tabletEvidenceDrawer.right,
              top: tabletEvidenceDrawer.top,
              bottom: tabletEvidenceDrawer.bottom,
            }
          : null,
      };
    });
    if (pageAudit.documentWidth > pageAudit.viewportWidth + 1) {
      throw new Error(
        `${capture.file} has horizontal overflow: ${pageAudit.documentWidth}px > ${pageAudit.viewportWidth}px.`,
      );
    }
    for (const control of pageAudit.mapControls) {
      if (
        control.left < -1
        || control.right > capture.width + 1
        || control.top < -1
        || control.bottom > capture.height + 1
      ) {
        throw new Error(`${capture.file} has a clipped map control: ${JSON.stringify(control)}.`);
      }
    }
    for (const target of pageAudit.touchTargets) {
      if (target.width < 43.5 || target.height < 43.5) {
        throw new Error(
          `${capture.file} has a touch target below 44px: ${JSON.stringify(target)}.`,
        );
      }
    }
    if (pageAudit.publicNavigationOverlap > 1) {
      throw new Error(
        `${capture.file} bottom navigation overlaps public content by ${pageAudit.publicNavigationOverlap}px.`,
      );
    }
    if (
      capture.route === "/command/"
      && capture.width === 1024
      && pageAudit.commandColumnCount !== 2
    ) {
      throw new Error(
        `${capture.file} must use the two-column tablet command layout.`,
      );
    }
    if (capture.route === "/public/") {
      const expectedTabs = [
        "public-tab-home",
        "public-tab-report",
        "public-tab-shelter",
        "public-tab-prepare",
        "public-tab-sos",
      ];
      if (pageAudit.publicTabIds.join("|") !== expectedTabs.join("|")) {
        throw new Error(`${capture.file} has incorrect Public navigation: ${pageAudit.publicTabIds.join("|")}.`);
      }
      if (pageAudit.publicRemovedChromeCount !== 0) {
        throw new Error(`${capture.file} retains the removed Public logo or historical banner.`);
      }
      if (!pageAudit.publicHeader || pageAudit.publicHeader.height > 58) {
        throw new Error(`${capture.file} is missing the compact header: ${JSON.stringify(pageAudit.publicHeader)}.`);
      }
      if (
        !pageAudit.publicProfileTrigger
        || pageAudit.publicProfileTrigger.width < 43.5
        || pageAudit.publicProfileTrigger.height < 43.5
      ) {
        throw new Error(`${capture.file} has an undersized profile trigger: ${JSON.stringify(pageAudit.publicProfileTrigger)}.`);
      }
      if (pageAudit.publicNavigationTargets.some(({ width, height }) => width < 43.5 || height < 43.5)) {
        throw new Error(`${capture.file} has an undersized Public navigation target.`);
      }
      if (/Public preparedness|Historical preparedness information/iu.test(pageAudit.bodyText)) {
        throw new Error(`${capture.file} retains removed Public chrome copy.`);
      }
      const developmentCopy = pageAudit.bodyText.match(
        /(?:^|[^\p{L}\p{N}])(?:demos?|prototypes?|mocks?|samples?|illustrative|placeholders?)(?=$|[^\p{L}\p{N}])|coming soon|under construction|not ready|work in progress/iu,
      );
      if (developmentCopy) {
        throw new Error(`${capture.file} exposes development-state copy: ${developmentCopy[0]}.`);
      }
    }
    if (capture.route === "/public/" && capture.publicTab === "home") {
      const header = pageAudit.publicHeader;
      const navigation = pageAudit.publicNavigation;
      const map = pageAudit.publicHomeMap;
      if (
        !header
        || !navigation
        || !map
        || Math.abs(map.top - header.bottom) > 2
        || Math.abs(map.bottom - navigation.top) > 2
        || map.left > 1
        || map.right < capture.width - 1
      ) {
        throw new Error(`${capture.file} does not keep Home full-bleed between the shared navigation bars.`);
      }
      const lowerControls = pageAudit.publicLowerControls;
      const lowerGap = lowerControls && map
        ? Math.min(
            map.bottom - lowerControls.risk.bottom,
            map.bottom - lowerControls.hazard.bottom,
          )
        : -1;
      if (
        pageAudit.publicHomeAreaFeatureCount !== "0"
        || pageAudit.publicHomeFrame?.borderWidth !== "0px"
        || pageAudit.publicHomeFrame?.borderRadius !== "0px"
        || pageAudit.publicCustomAttributionCount !== 0
        || !pageAudit.publicNativeAttributionVisible
        || !lowerControls
        || Math.abs(lowerControls.risk.bottom - lowerControls.hazard.bottom) > 1
        || lowerControls.risk.right > lowerControls.hazard.left
        || lowerGap < 10
        || lowerGap > 24
      ) {
        throw new Error(`${capture.file} failed the borderless Home map or lower-control spacing contract: ${JSON.stringify({
          areaFeatureCount: pageAudit.publicHomeAreaFeatureCount,
          frame: pageAudit.publicHomeFrame,
          customAttributionCount: pageAudit.publicCustomAttributionCount,
          nativeAttributionVisible: pageAudit.publicNativeAttributionVisible,
          lowerControls,
          lowerGap,
        })}.`);
      }
    }
    if (capture.route === "/public/" && capture.publicTab === "shelter") {
      if (!/Safety disclaimer|ข้อควรระวังด้านความปลอดภัย/iu.test(pageAudit.bodyText)) {
        throw new Error(`${capture.file} is missing the Shelter safety disclaimer.`);
      }
    }
    if (capture.route === "/public/" && capture.publicTab === "sos") {
      if (await page.locator('.public-sos-page a[href^="tel:"]').count() < 3) {
        throw new Error(`${capture.file} is missing the three direct emergency call actions.`);
      }
    }
    if (capture.route === "/command/" && capture.width === 1024) {
      const drawer = pageAudit.tabletEvidenceDrawer;
      if (!drawer || drawer.left < 0 || drawer.right > capture.width || drawer.top < 0 || drawer.bottom > capture.height) {
        throw new Error(`${capture.file} has a missing or clipped persistent evidence drawer: ${JSON.stringify(drawer)}.`);
      }
    }
    if (capture.route === "/command/") {
      const mapScenario = await page.locator(".map-workspace .geo-map-shell").getAttribute("data-scenario-id");
      const panelScenario = await page.locator(".decision-panel").getAttribute("data-scenario-id");
      if (mapScenario !== "baseline" || panelScenario !== mapScenario) {
        throw new Error(`${capture.file} did not keep the unavailable planning scenario at baseline.`);
      }
      if (!await page.locator('select[aria-label="Select scenario"]').isDisabled()) {
        throw new Error(`${capture.file} enabled an unavailable planning scenario.`);
      }
      if (await page.locator(".command-release-panel .scenario-evidence-comparison, .scenario-delta-strip").count() !== 0) {
        throw new Error(`${capture.file} renders a baseline comparison without a reviewed non-baseline scenario.`);
      }
    }
    if (capture.route === "/studio/") {
      const body = pageAudit.bodyText;
      const normalizedBody = body.toLocaleLowerCase("en-US");
      for (const scope of ["Technical verification", "Observed-data validation", "Operational authorization"]) {
        if (!normalizedBody.includes(scope.toLocaleLowerCase("en-US"))) {
          throw new Error(`${capture.file} is missing the ${scope} scope.`);
        }
      }
    }
    if (
      capture.route === "/studio/"
      && pageAudit.proofSingleFigureCoverage !== null
      && pageAudit.proofSingleFigureCoverage < 0.95
    ) {
      throw new Error(`${capture.file} leaves the single proof image in a half-width grid cell.`);
    }
    if (/[A-Za-z]:[\\/](?:Users|Documents)|file:\/\//u.test(pageAudit.bodyText)) {
      throw new Error(`${capture.file} exposes a private local path.`);
    }
    if (/updated every 2 minutes|critical now|rescue count/iu.test(pageAudit.bodyText)) {
      throw new Error(`${capture.file} contains an unsupported live-state claim.`);
    }
    assertPolishedRouteCopy(pageAudit.bodyText, capture.route, capture.file);

    await page.screenshot({ path: resolve(evidenceDir, capture.file), fullPage: false });

    await page.locator(".skip-link").focus();
    await page.keyboard.press("Tab");
    const focusAudit = await page.evaluate(() => {
      const element = document.activeElement;
      if (!(element instanceof HTMLElement) || element === document.body) return null;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return {
        visible: rect.width > 0 && rect.height > 0,
        styled:
          (style.outlineStyle !== "none" && style.outlineWidth !== "0px")
          || style.boxShadow !== "none",
      };
    });
    if (!focusAudit?.visible || !focusAudit.styled) {
      throw new Error(`${capture.file} did not expose a visible keyboard focus treatment.`);
    }
    await page.evaluate(() => {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    });

    await context.close();
    console.log(`visual QA: ${capture.file} ${capture.width}x${capture.height} PASS`);
  }

  if (externalRequests.size > 0) {
    throw new Error(`Unapproved external requests were attempted: ${[...externalRequests].join(", ")}`);
  }
  for (const origin of approvedBasemapOrigins) {
    if (!approvedBasemapOriginsSeen.has(origin)) {
      throw new Error(`Visual QA never loaded approved basemap provider ${origin}.`);
    }
  }
  if (browserErrors.length > 0) {
    throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  }
  console.log(`visual QA: ${captures.length} captures, three approved basemap providers, no unapproved external requests, all checks PASS`);
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => {
    server.close((error) => error ? rejectClose(error) : resolveClose());
  });
}

async function exerciseOnlineBasemaps(page, scopeSelector, file) {
  for (const basemap of ["street", "satellite", "terrain"]) {
    await selectOnlineBasemap(page, scopeSelector, basemap, file, false);
  }
}

async function selectOnlineBasemap(page, scopeSelector, basemap, file, requireFullCoverage) {
  const basemaps = ["street", "satellite", "terrain"];
  const index = basemaps.indexOf(basemap);
  if (index === -1) throw new Error(`${file} requested an unsupported map background: ${basemap}.`);
  const menu = page.locator(`${scopeSelector} .map-basemap-menu`);
  if (await menu.count() && await menu.getAttribute("open") === null) {
    await menu.locator("summary").click();
  }
  const buttons = page.locator(
    `${scopeSelector} .map-basemap-switcher button, ${scopeSelector} .map-basemap-menu button`,
  );
  if (await buttons.count() !== 3) {
    throw new Error(`${file} must expose Street, Satellite, and Terrain map backgrounds.`);
  }
  const labels = (await buttons.allTextContents()).map((label) => label.trim()).join("|");
  if (labels !== "Street|Satellite|Terrain" && labels !== "ถนน|ดาวเทียม|ภูมิประเทศ") {
    throw new Error(`${file} map backgrounds are mislabeled: ${labels}.`);
  }
  await buttons.nth(index).click();
  try {
    await page.waitForFunction(
      ({ scope, expectedBasemap, requireComplete }) => {
        const element = document.querySelector(`${scope} .geo-map-shell`);
        const allTiles = [...document.querySelectorAll(`${scope} .leaflet-tile-pane img.leaflet-tile`)];
        const loadedTiles = allTiles.filter((tile) => tile.classList.contains("leaflet-tile-loaded"));
        return element?.getAttribute("data-basemap") === expectedBasemap
          && element?.getAttribute("data-basemap-state") === "ready"
          && loadedTiles.some((tile) => tile instanceof HTMLImageElement
            && tile.complete
            && tile.naturalWidth > 0)
          && (!requireComplete || (allTiles.length > 0 && allTiles.every((tile) => (
            tile instanceof HTMLImageElement
            && tile.complete
            && tile.naturalWidth > 0
            && tile.classList.contains("leaflet-tile-loaded")
          ))));
      },
      { scope: scopeSelector, expectedBasemap: basemap, requireComplete: requireFullCoverage },
      { timeout: 30_000 },
    );
  } catch (error) {
    const diagnostic = await page.evaluate(({ scope }) => {
      const shell = document.querySelector(`${scope} .geo-map-shell`);
      const tiles = [...document.querySelectorAll(`${scope} .leaflet-tile-pane img.leaflet-tile`)]
        .filter((tile) => tile instanceof HTMLImageElement)
        .map((tile) => ({
          complete: tile.complete,
          loaded: tile.classList.contains("leaflet-tile-loaded"),
          naturalWidth: tile.naturalWidth,
          opacity: getComputedStyle(tile).opacity,
          src: tile.src,
        }));
      return {
        basemap: shell?.getAttribute("data-basemap"),
        state: shell?.getAttribute("data-basemap-state"),
        tiles,
      };
    }, { scope: scopeSelector });
    throw new Error(`${file} ${basemap} background did not settle: ${JSON.stringify(diagnostic)}`, { cause: error });
  }
  await page.waitForTimeout(750);
  if (await buttons.nth(index).getAttribute("aria-pressed") !== "true") {
    throw new Error(`${file} did not expose ${basemap} as the selected map background.`);
  }
  const publicHome = scopeSelector.includes("public-home");
  const attributionSelector = publicHome
    ? `${scopeSelector} .leaflet-control-attribution`
    : `${scopeSelector} .map-attribution`;
  const attribution = await page.locator(attributionSelector).innerText();
  const expectedAttribution = basemap === "street"
    ? "OpenStreetMap"
    : basemap === "satellite"
      ? "Esri"
      : "OpenTopoMap";
  if (!attribution.includes(expectedAttribution)) {
    throw new Error(`${file} ${basemap} background is missing ${expectedAttribution} attribution.`);
  }
}

async function assertMaeSaiMap(page, scopeSelector, file, expectRoads, expectTextAlternative = true, expectBoundary = true) {
  await page.waitForFunction(
    ({ scope, requireRoads, requireBoundary }) => {
      const shell = document.querySelector(`${scope} .geo-map-shell`);
      const audience = shell?.getAttribute("data-map-audience");
      const visibleFacilityCount = shell?.getAttribute("data-facility-feature-count");
      const facilityDatasetCount = shell?.getAttribute("data-facility-dataset-count");
      const clusterCount = document.querySelectorAll(`${scope} .facility-cluster-marker`).length;
      const rendererCount = document.querySelectorAll(`${scope} .leaflet-overlay-pane canvas, ${scope} .leaflet-overlay-pane path`).length;
      const roads = Number(shell?.getAttribute("data-road-feature-count") ?? 0);
      const facilitiesReady = audience === "public"
        ? facilityDatasetCount === "0" && visibleFacilityCount === "0" && clusterCount === 0
        : visibleFacilityCount === "42" && clusterCount > 0 && shell?.getAttribute("data-facility-presentation") === "clusters";
      return facilitiesReady
        && (!requireBoundary || rendererCount > 0)
        && (!requireRoads || roads >= 4_458);
    },
    { scope: scopeSelector, requireRoads: expectRoads, requireBoundary: expectBoundary },
    { timeout: 30_000 },
  );
  const shell = page.locator(`${scopeSelector} .geo-map-shell`);
  const audience = await shell.getAttribute("data-map-audience");
  const expectedFacilityCount = audience === "public" ? "0" : "42";
  if (await shell.getAttribute("data-facility-dataset-count") !== expectedFacilityCount) {
    throw new Error(`${file} did not retain its role-approved facility projection.`);
  }
  if (expectTextAlternative) {
    const alternativeText = await page.locator(`${scopeSelector} .map-text-alternative`).textContent();
    if (!/(?:Selected area|พื้นที่ที่เลือก)/iu.test(alternativeText ?? "") || !/(?:Road network context|โครงข่ายถนน)/iu.test(alternativeText ?? "") || !/(?:Assumptions|สมมติฐาน)/iu.test(alternativeText ?? "")) {
      throw new Error(`${file} map results list does not describe its selected area, roads, and access assumptions.`);
    }
  }
  const boundaryRendererCount = await page.locator(`${scopeSelector} .leaflet-overlay-pane canvas, ${scopeSelector} .leaflet-overlay-pane path`).count();
  if (expectBoundary && (boundaryRendererCount === 0 || !await shell.getAttribute("data-selected-area"))) {
    throw new Error(`${file} did not render its highlighted AOI boundary overlay.`);
  }
  if (!expectBoundary && await shell.getAttribute("data-area-feature-count") !== "0") {
    throw new Error(`${file} retained a Public administrative boundary layer.`);
  }
  if (audience === "public" && await page.locator(`${scopeSelector} .facility-type-marker, ${scopeSelector} .facility-cluster-marker`).count() !== 0) {
    throw new Error(`${file} exposed unverified facilities on the public map.`);
  }
  if (audience === "staff" && await page.locator(`${scopeSelector} .facility-cluster-marker`).count() === 0) {
    throw new Error(`${file} did not cluster staff facilities at regional zoom.`);
  }
  const roads = Number(await shell.getAttribute("data-road-feature-count"));
  if (expectRoads && roads < 4_458) {
    throw new Error(`${file} did not retain the full Mae Sai road evidence layer.`);
  }
}

function assertPolishedRouteCopy(body, route, file) {
  const requirements = route === "/public/"
    ? [
        /FloodGuard/iu,
        /SOS/iu,
      ]
    : route === "/command/"
      ? [
          /Planning intelligence|ข้อมูลเพื่อการวางแผน/iu,
          /Source time|เวลาข้อมูล/iu,
          /Confidence|ความเชื่อมั่น/iu,
          /DDPM|ปภ\./iu,
          /local-authority|หน่วยงานท้องถิ่น/iu,
        ]
      : [
          /Validation & evidence report/iu,
          /Source time/iu,
          /Confidence/iu,
          /Technical verification/iu,
          /Observed-data validation/iu,
          /Operational authorization/iu,
          /immutable evidence context/iu,
        ];
  for (const requirement of requirements) {
    if (!requirement.test(body)) {
      throw new Error(`${file} is missing polished final copy matching ${requirement}.`);
    }
  }
  const forbidden = route === "/studio/"
    ? /(?:^|[^\p{L}\p{N}])(?:rehearsals?|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula|ฝึกซ้อม/iu
    : route === "/public/"
      ? /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|prototypes?|mocks?|samples?|illustrative|placeholders?|fixtures?|candidates?|synthetic|non[-_ ]?operational|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|coming soon|under construction|not ready|work in progress|developer note|no browser formula|processing_scope|can_feed_decision_layer|ฝึกซ้อม|สาธิต|ผู้สมัคร/iu
      : /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|fixtures?|candidates?|synthetic|non[-_ ]?operational|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula|processing_scope|can_feed_decision_layer|ฝึกซ้อม|สาธิต|ผู้สมัคร/iu;
  const match = body.match(forbidden);
  if (match) {
    throw new Error(`${file} exposes forbidden internal copy: ${match[0]}.`);
  }
}
