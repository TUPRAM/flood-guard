import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import RootEntry, { generateMetadata } from "./page";

afterEach(() => vi.unstubAllEnvs());

describe("Landing root", () => {
  it("server-renders the artwork story and working role links", () => {
    const html = renderToStaticMarkup(<RootEntry />);
    const visibleText = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
    expect(html).toContain("data-fg-landing");
    expect(html).toContain('id="main-content"');
    expect(html).toContain('lang="en"');
    expect(visibleText).toMatch(/See the flood\.\s*Understand what it changes\./);
    for (const route of ["public", "command", "studio"]) expect(html).toContain(`href="/${route}/"`);
    expect(html).toContain("/landing/floodguard-v2/camera/approach-00.webp");
    expect(html).not.toContain("/landing/floodguard-v1/plates/");
    expect(html).not.toContain("/_next/image");
    expect(visibleText).toMatch(/illustrat/i);
  });

  it("keeps landing metadata out of the public-production profile", () => {
    vi.stubEnv("FLOODGUARD_APP_PROFILE", "public-production");
    expect(generateMetadata()).toEqual({});
    vi.stubEnv("FLOODGUARD_APP_PROFILE", "competition");
    expect(generateMetadata().description).toMatch(/illustrated neighborhood/);
  });
});
