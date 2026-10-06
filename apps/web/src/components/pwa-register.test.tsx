import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { autoHidesOn, PwaRegister, mapAvailabilityCopy, pwaAvailabilityCopy, requiredOfflinePaths } from "./pwa-register";

describe("PwaRegister", () => {
  it("keeps map availability distinct from online and saved-app readiness", () => {
    expect(mapAvailabilityCopy("unavailable", "en")).toBe("Map background unavailable");
    expect(mapAvailabilityCopy("partial", "en")).toBe("Map background incomplete");
    expect(mapAvailabilityCopy("hidden", "en")).toBe("Map background hidden");
    expect(mapAvailabilityCopy(null, "en")).toBe("No map background active");
    expect(mapAvailabilityCopy("offline", "th")).not.toMatch(/[A-Za-z]/);
  });
  it("renders a concise availability control before browser state is known", () => {
    const html = renderToStaticMarkup(<PwaRegister enabled />);

    expect(html).toContain("Checking connection");
    expect(html).toContain("App availability");
    expect(html).toContain("September 2024 · historical");
    expect(html).toContain("Household plan");
    expect(html).toContain("Cached planning snapshot");
    expect(html).toContain("Last successful update check");
    expect(html).toContain("Map backgrounds");
    expect(html).not.toMatch(/fixture|candidate|demo|synthetic/i);
  });

  it("stays hidden in the unprocessed development build", () => {
    expect(renderToStaticMarkup(<PwaRegister enabled={false} />)).toBe("");
  });

  it("provides complete Thai availability copy for the shared language preference", () => {
    const copy = pwaAvailabilityCopy("th");

    expect(copy.heading).toBe("สถานะแอป");
    expect(copy.availableOffline).toBe("พร้อมใช้งานแบบออฟไลน์");
    expect(copy.lastUpdateCheck).toBe("ตรวจสอบการอัปเดตสำเร็จล่าสุด");
    expect(copy.updateErrorWithoutCache).toContain("โปรดเชื่อมต่อและลองอีกครั้ง");
    expect(Object.values(copy).join(" ")).not.toMatch(/[A-Za-z]/);
  });

  it("requires only public-safe evidence in the public profile", () => {
    const publicPaths = requiredOfflinePaths("public-production");

    expect(publicPaths).toContain("/offline-demo/mae-sai/public-bundle.json");
    expect(publicPaths).toContain("/offline-demo/mae-sai/public-areas.json");
    expect(publicPaths).not.toContain("/command/");
    expect(publicPaths).not.toContain("/studio/");
    expect(publicPaths.join(" ")).not.toMatch(/roads\.json|facilities\.json|access-hotspots\.json/);
  });

  it("requires every role route before calling the competition app saved offline", () => {
    expect(requiredOfflinePaths("competition")).toEqual(expect.arrayContaining([
      "/public-cases/", "/command/", "/command/planning/", "/command/cases/", "/studio/archive/command-workspace/",
      // The three earlier addresses only forward; they are saved too, so that an old link opens without a connection.
      "/command/exercise/", "/command/ver2/", "/command/archive/",
      "/studio/", "/studio/brief/", "/studio/library/", "/studio/archive/",
    ]));
  });

  it("hides the app-status pill on the exercise page and not on the Planning pages below it", () => {
    const paths = ["/studio/cases/", "/command/$"];
    expect(autoHidesOn("/command/", paths)).toBe(true);
    expect(autoHidesOn("/command/planning/", paths)).toBe(false);
    expect(autoHidesOn("/command/cases/", paths)).toBe(false);
    expect(autoHidesOn("/studio/cases/mae-sai-2024/", paths)).toBe(true);
    expect(autoHidesOn("/studio/", paths)).toBe(false);
    expect(autoHidesOn(null, paths)).toBe(false);
    expect(autoHidesOn("/command/", ["$", ""])).toBe(false);
  });

  it("is compiled without the staff addresses when the site is built for the public profile", async () => {
    // The profile is a build-time constant, so the public bundle drops the list (the build's own artifact check then
    // fails on a Command address anywhere in the public build).
    vi.stubEnv("NEXT_PUBLIC_FLOODGUARD_APP_PROFILE", "public-production");
    vi.resetModules();
    try {
      const built = await import("./pwa-register");
      expect(built.requiredOfflinePaths("competition").join(" ")).not.toMatch(/\/command\/|\/studio\/|\/public-cases\//);
      expect(built.requiredOfflinePaths("public-production")).toEqual(requiredOfflinePaths("public-production"));
    } finally {
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });
});
