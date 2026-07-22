import { chromium } from "@playwright/test";

/**
 * Prefer the Playwright-managed browser so `playwright install chromium` is
 * sufficient on every platform. Fall back to the installed Chrome channel for
 * developer machines that have Chrome but have not downloaded Playwright's
 * pinned browser.
 */
export async function launchFloodGuardBrowser() {
  const executablePath = process.env.FLOODGUARD_BROWSER_EXECUTABLE;
  if (executablePath) {
    return chromium.launch({ executablePath, headless: true });
  }

  try {
    return await chromium.launch({ headless: true });
  } catch (playwrightError) {
    try {
      return await chromium.launch({ channel: "chrome", headless: true });
    } catch (chromeError) {
      throw new AggregateError(
        [playwrightError, chromeError],
        "Neither Playwright Chromium nor the installed Chrome channel could be launched. Run `pnpm exec playwright install chromium` or set FLOODGUARD_BROWSER_EXECUTABLE.",
      );
    }
  }
}
