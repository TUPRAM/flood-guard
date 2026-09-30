import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CASE_REPLAY_ROUTE } from "../../scripts/case-replay-inventory.mjs";
import { MAE_SAI_TIMELINE_ROUTE, MaeSaiFloodTimeline } from "../components/mae-sai-flood-timeline";
import { MAE_SAI_REPLAY_ROUTE as STUDIO_REPLAY_ROUTE } from "../components/studio-library";
import { competitionPagesAvailable, MAE_SAI_REPLAY_ROUTE, POLICY_ROUTE } from "./policy-links";

describe("policy and replay cross-links", () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  it("points at the replay's own route and at the policy route", () => {
    expect(MAE_SAI_REPLAY_ROUTE).toBe(MAE_SAI_TIMELINE_ROUTE);
    expect(MAE_SAI_REPLAY_ROUTE).toBe(STUDIO_REPLAY_ROUTE);
    expect(MAE_SAI_REPLAY_ROUTE).toBe(CASE_REPLAY_ROUTE);
    expect(POLICY_ROUTE).toBe("/policy/");
  });

  it("treats only the competition profile (the default) as shipping /policy/ and /studio/", () => {
    expect(competitionPagesAvailable(undefined)).toBe(true);
    expect(competitionPagesAvailable("competition")).toBe(true);
    expect(competitionPagesAvailable("public")).toBe(false);
    expect(competitionPagesAvailable("public-production")).toBe(false);
  });

  it("adds a policy link to the replay footer sentence about FPPS and action classes", () => {
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    const footer = /<footer[^>]*>([\s\S]*?)<\/footer>/.exec(html)?.[1] ?? "";
    expect(footer).toContain("computes no Flood Preparedness Priority Score and assigns no action class (A–E)");
    expect(footer).toMatch(new RegExp(`<a href="${POLICY_ROUTE}" data-testid="replay-policy-link">How FPPS and the A–E classes work, and why this replay assigns neither</a>`));
  });

  it("leaves the policy link out where the profile does not ship the policy page", () => {
    vi.stubEnv("NEXT_PUBLIC_FLOODGUARD_APP_PROFILE", "public-production");
    const html = renderToStaticMarkup(<MaeSaiFloodTimeline />);
    expect(html).toContain("assigns no action class (A–E)");
    expect(html).not.toContain('data-testid="replay-policy-link"');
    expect(html).not.toContain(`href="${POLICY_ROUTE}"`);
  });

  // Offline caching of both targets is checked on the built service worker, not on script source:
  // profile-artifact-smoke.mjs requires "/policy/" and the replay route in the competition CORE_ASSETS and rejects
  // any page under /policy/, /studio/ or /command/ in the public one; policy-browser-smoke.mjs follows both links offline.
});
