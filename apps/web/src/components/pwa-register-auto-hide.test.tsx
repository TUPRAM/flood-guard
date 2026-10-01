import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/studio/cases/mae-sai-2024/" }));

import { autoHidesOn, pillStaysHidden, PWA_AUTO_HIDE_MS, PwaRegister, pwaAvailabilityCopy } from "./pwa-register";

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
    // Never hidden: it shows.
    expect(pillStaysHidden(null, page, true)).toBe(false);
    // Hidden while online: it stays hidden until the page goes offline, then returns.
    const hiddenOnline = { path: page, online: true };
    expect(pillStaysHidden(hiddenOnline, page, true)).toBe(true);
    expect(pillStaysHidden(hiddenOnline, page, false)).toBe(false);
    // Hidden again while offline: it stays hidden until the connection comes back.
    const hiddenOffline = { path: page, online: false };
    expect(pillStaysHidden(hiddenOffline, page, false)).toBe(true);
    expect(pillStaysHidden(hiddenOffline, page, true)).toBe(false);
    // As before, navigating to another page shows it again.
    expect(pillStaysHidden(hiddenOnline, "/studio/cases/other/", true)).toBe(false);
    expect(pillStaysHidden(hiddenOnline, null, true)).toBe(false);
  });

  it("keeps the pill unchanged where the option does not apply", () => {
    const plain = renderToStaticMarkup(<PwaRegister enabled />);
    expect(plain).not.toContain("data-pwa-auto-hide");
    expect(plain).toContain('data-pwa-availability="true"');
    expect(renderToStaticMarkup(<PwaRegister enabled autoHidePaths={["/public/"]} />)).not.toContain("data-pwa-auto-hide");
    expect(renderToStaticMarkup(<PwaRegister enabled={false} autoHidePaths={["/studio/cases/"]} />)).toBe("");
  });
});
