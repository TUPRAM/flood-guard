import { createReadStream, existsSync, mkdirSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { chromium } from "@playwright/test";

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

const browser = await chromium.launch(
  process.env.FLOODGUARD_BROWSER_EXECUTABLE
    ? { executablePath: process.env.FLOODGUARD_BROWSER_EXECUTABLE, headless: true }
    : process.platform === "win32"
      ? { channel: "chrome", headless: true }
      : { headless: true },
);

const captures = [
  { route: "/public/", selector: "main.public-page", width: 390, height: 844, file: "public-390x844.png" },
  { route: "/public/", selector: "main.public-page", width: 430, height: 932, file: "public-map-430x932.png", publicTab: 2 },
  { route: "/command/", selector: "main.command-page", width: 1024, height: 768, file: "command-1024x768.png" },
  { route: "/command/", selector: "main.command-page", width: 1440, height: 900, file: "command-1440x900.png" },
  { route: "/command/", selector: "main.command-page", width: 1536, height: 1024, file: "command-1536x1024.png" },
  { route: "/studio/", selector: "main.studio-page", width: 2048, height: 1152, file: "studio-2048x1152.png" },
];
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
      await page.locator(`.public-bottom-nav button:nth-child(${capture.publicTab})`).click();
      await page.locator(".public-map-view .leaflet-container").waitFor({ state: "visible" });
      await page.locator(".map-selection-sheet.open").waitFor({ state: "visible" });
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
      await page.locator('select[aria-label="Select scenario"]').selectOption("add_temporary_shelter");
      await page.waitForFunction(() => (
        document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-scenario-id") === "add_temporary_shelter"
        && document.querySelector(".decision-panel")?.getAttribute("data-scenario-id") === "add_temporary_shelter"
      ));
    }

    if (capture.route === "/command/" && await page.locator(".ranked-areas button").count() === 0) {
      throw new Error(`${capture.file} is missing the FPPS ranked list.`);
    }
    if (capture.route === "/studio/" && await page.locator(".geoai-proof").count() !== 1) {
      throw new Error(`${capture.file} is missing the above-fold GeoAI proof panel.`);
    }

    const pageAudit = await page.evaluate(() => {
      const bodyText = document.body.innerText;
      const mapControls = [...document.querySelectorAll(".leaflet-control-container .leaflet-control")]
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
      const publicContent = document.querySelector(".public-content")?.getBoundingClientRect();
      const publicNavigation = document.querySelector(".public-bottom-nav")?.getBoundingClientRect();
      const commandWorkspace = document.querySelector(".command-workspace");
      const commandColumnCount = commandWorkspace
        ? getComputedStyle(commandWorkspace).gridTemplateColumns.split(" ").filter(Boolean).length
        : null;
      const proofImages = document.querySelector(".proof-images")?.getBoundingClientRect();
      const proofFigure = document.querySelector(".proof-images figure:only-child")?.getBoundingClientRect();
      const publicPlanAction = document.querySelector('[data-action="build-household-plan"]')?.getBoundingClientRect();
      const publicOfficialHelp = document.querySelector('[data-testid="public-official-help"]')?.getBoundingClientRect();
      const selectedAreaSheet = document.querySelector(".map-selection-sheet")?.getBoundingClientRect();
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
        commandColumnCount,
        proofSingleFigureCoverage:
          proofImages && proofFigure ? proofFigure.width / proofImages.width : null,
        publicPlanActionBottom: publicPlanAction?.bottom ?? null,
        publicOfficialHelpTop: publicOfficialHelp?.top ?? null,
        selectedAreaSheetVisible: Boolean(selectedAreaSheet && selectedAreaSheet.width > 0 && selectedAreaSheet.height > 0),
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
    if (capture.route === "/public/" && !capture.publicTab) {
      if (pageAudit.publicPlanActionBottom === null || pageAudit.publicPlanActionBottom > capture.height) {
        throw new Error(`${capture.file} does not keep the household-plan action in the first viewport.`);
      }
      if (pageAudit.publicOfficialHelpTop === null || pageAudit.publicOfficialHelpTop >= capture.height) {
        throw new Error(`${capture.file} does not introduce official help in the first viewport.`);
      }
    }
    if (capture.route === "/public/" && capture.publicTab && !pageAudit.selectedAreaSheetVisible) {
      throw new Error(`${capture.file} is missing the selected-area bottom sheet.`);
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
      if (mapScenario !== "add_temporary_shelter" || panelScenario !== mapScenario) {
        throw new Error(`${capture.file} did not synchronize server scenario state across map and evidence.`);
      }
      if (await page.locator('.map-workspace path[fill="#0f8a7b"]').count() === 0) {
        throw new Error(`${capture.file} does not visibly encode the server-produced improvement delta.`);
      }
    }
    if (capture.route === "/studio/") {
      const body = pageAudit.bodyText;
      const normalizedBody = body.toLocaleLowerCase("en-US");
      for (const scope of ["Integration smoke", "Qualified real-data evaluation", "Decision eligibility"]) {
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
    if (!/fixture demo|ชุดข้อมูลสาธิต/iu.test(pageAudit.bodyText)) {
      throw new Error(`${capture.file} is missing the fixture-demo disclosure.`);
    }
    if (!/non-operational|ไม่ใช่ระบบปฏิบัติการ/iu.test(pageAudit.bodyText)) {
      throw new Error(`${capture.file} is missing the non-operational disclosure.`);
    }
    if (!/source time|เวลาข้อมูล/iu.test(pageAudit.bodyText)) {
      throw new Error(`${capture.file} is missing the source timestamp label.`);
    }
    if (!/confidence|ความเชื่อมั่น/iu.test(pageAudit.bodyText)) {
      throw new Error(`${capture.file} is missing the confidence label.`);
    }

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

    await page.screenshot({ path: resolve(evidenceDir, capture.file), fullPage: false });
    await context.close();
    console.log(`visual QA: ${capture.file} ${capture.width}x${capture.height} PASS`);
  }

  if (externalRequests.size > 0) {
    throw new Error(`External requests were attempted: ${[...externalRequests].join(", ")}`);
  }
  if (browserErrors.length > 0) {
    throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  }
  console.log(`visual QA: ${captures.length} captures, 0 external requests, all checks PASS`);
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => {
    server.close((error) => error ? rejectClose(error) : resolveClose());
  });
}
