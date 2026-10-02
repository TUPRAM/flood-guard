import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/studio/cases/mae-sai-2024/" }));

import { autoHidesOn, keepHidden, pillStaysHidden, pillStatus, PWA_AUTO_HIDE_MS, PwaRegister, pwaAvailabilityCopy } from "./pwa-register";

describe("PwaRegister auto-hide option", () => {
  it("matches only the listed path prefixes", () => {
    expect(autoHidesOn("/studio/cases/mae-sai-2024/", ["/studio/cases/"])).toBe(true);
    expect(autoHidesOn("/studio/", ["/studio/cases/"])).toBe(false);
    expect(autoHidesOn("/public/", ["/studio/cases/"])).toBe(false);
    expect(autoHidesOn(null, ["/studio/cases/"])).toBe(false);
    expect(autoHidesOn("/studio/cases/x/", [])).toBe(false);
    expect(autoHidesOn("/studio/cases/x/", [""])).toBe(false);
    expect(PWA_AUTO_HIDE_MS).toBeGreaterThanOrEqual(3000);
  });

  it("adds a dismiss button next to the pill on an auto-hide page", () => {
    const html = renderToStaticMarkup(<PwaRegister enabled autoHidePaths={["/studio/cases/"]} />);
    expect(html).toContain('data-pwa-auto-hide="true"');
    expect(html).toContain('data-pwa-availability="true"');
    expect(html).toContain(`aria-label="${pwaAvailabilityCopy("en").dismiss}"`);
    expect(pwaAvailabilityCopy("th").dismiss).not.toMatch(/[A-Za-z]/);
  });

  it("brings a hidden pill back when the connection status changes, or after navigating elsewhere", () => {
    const page = "/studio/cases/mae-sai-2024/";
    const online = pillStatus(true, false, false);
    const offline = pillStatus(false, false, false);
    // Never hidden: it shows.
    expect(pillStaysHidden(null, page, online)).toBe(false);
    // Hidden while online: it stays hidden until the page goes offline, then returns.
    const hiddenOnline = { path: page, status: online };
    expect(pillStaysHidden(hiddenOnline, page, online)).toBe(true);
    expect(pillStaysHidden(hiddenOnline, page, offline)).toBe(false);
    // Hidden again while offline: it stays hidden until the connection comes back.
    const hiddenOffline = { path: page, status: offline };
    expect(pillStaysHidden(hiddenOffline, page, offline)).toBe(true);
    expect(pillStaysHidden(hiddenOffline, page, online)).toBe(false);
    // As before, navigating to another page shows it again.
    expect(pillStaysHidden(hiddenOnline, "/studio/cases/other/", online)).toBe(false);
    expect(pillStaysHidden(hiddenOnline, null, online)).toBe(false);
  });

  it("brings a hidden pill back when the app becomes saved for offline use or an update is waiting", () => {
    const page = "/studio/cases/mae-sai-2024/";
    // The status is everything the pill's summary and its update button change with.
    expect(new Set([pillStatus(null, false, false), pillStatus(true, false, false), pillStatus(false, false, false),
      pillStatus(true, true, false), pillStatus(true, true, true), pillStatus(false, true, false)]).size).toBe(6);
    // First visit on a slow connection: hidden as "Online", then the service worker finishes saving the app.
    const hiddenBeforeSaved = { path: page, status: pillStatus(true, false, false) };
    expect(pillStaysHidden(hiddenBeforeSaved, page, pillStatus(true, false, false))).toBe(true);
    expect(pillStaysHidden(hiddenBeforeSaved, page, pillStatus(true, true, false))).toBe(false);
    // Hidden as "Online · saved app ready", then an update is waiting.
    const hiddenSaved = { path: page, status: pillStatus(true, true, false) };
    expect(pillStaysHidden(hiddenSaved, page, pillStatus(true, true, false))).toBe(true);
    expect(pillStaysHidden(hiddenSaved, page, pillStatus(true, true, true))).toBe(false);
  });

  it("forgets a hidden record that no longer applies, so a status that flips back is shown for a full period", () => {
    const page = "/studio/cases/mae-sai-2024/";
    const online = pillStatus(true, false, false);
    const offline = pillStatus(false, false, false);
    const hiddenOnline = { path: page, status: online };
    expect(keepHidden(hiddenOnline, page, online)).toBe(hiddenOnline);
    // The connection drops: the record is dropped with it ...
    expect(keepHidden(hiddenOnline, page, offline)).toBeNull();
    // ... so when it returns two seconds later nothing says "already hidden as Online", and the pill shows "Online".
    expect(pillStaysHidden(keepHidden(hiddenOnline, page, offline), page, online)).toBe(false);
    expect(keepHidden(hiddenOnline, "/studio/", online)).toBeNull();
    expect(keepHidden(null, page, online)).toBeNull();
  });

  it("keeps the pill unchanged where the option does not apply", () => {
    const plain = renderToStaticMarkup(<PwaRegister enabled />);
    expect(plain).not.toContain("data-pwa-auto-hide");
    expect(plain).toContain('data-pwa-availability="true"');
    expect(renderToStaticMarkup(<PwaRegister enabled autoHidePaths={["/public/"]} />)).not.toContain("data-pwa-auto-hide");
    expect(renderToStaticMarkup(<PwaRegister enabled={false} autoHidePaths={["/studio/cases/"]} />)).toBe("");
  });
});
