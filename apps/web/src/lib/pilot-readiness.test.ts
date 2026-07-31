import { describe, expect, it } from "vitest";

import { getOfflineData } from "./data-provider";
import { pilotReadinessCopy } from "./pilot-readiness";

describe("pilot readiness presentation", () => {
  it("keeps offline fixture state visibly non-operational in both languages", () => {
    const readiness = getOfflineData().pilot_readiness;
    const english = pilotReadinessCopy(readiness, "en");
    const thai = pilotReadinessCopy(readiness, "th");

    expect(readiness.operational_status).toBe("non_operational");
    expect(readiness.agency_operational_allowed).toBe(false);
    expect(english.status).toBe("Not authorized for operation");
    expect(english.boundary).toMatch(/API rechecks every protected request/);
    expect(thai.status).toContain("ยังไม่อนุญาต");
    expect(thai.boundary).toContain("API");
  });
});
