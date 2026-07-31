import { describe, expect, it } from "vitest";

import { resolveDeploymentProfile } from "./deployment-profile";

describe("resolveDeploymentProfile", () => {
  it("defaults to the three-surface competition entry", () => {
    expect(resolveDeploymentProfile(undefined)).toBe("competition");
    expect(resolveDeploymentProfile("competition")).toBe("competition");
  });

  it("accepts the public-production profile and its short alias", () => {
    expect(resolveDeploymentProfile("public-production")).toBe("public-production");
    expect(resolveDeploymentProfile("public")).toBe("public-production");
  });

  it("rejects unknown profiles instead of silently broadening the deployment", () => {
    expect(() => resolveDeploymentProfile("staff")).toThrow("Unsupported FloodGuard deployment profile");
  });
});
