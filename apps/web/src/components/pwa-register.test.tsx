import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PwaRegister, pwaAvailabilityCopy, requiredOfflinePaths } from "./pwa-register";

describe("PwaRegister", () => {
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
});
