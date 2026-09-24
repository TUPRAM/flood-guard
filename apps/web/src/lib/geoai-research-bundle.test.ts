import { describe, expect, it } from "vitest";
import archive from "../../public/geoai/mae-sai-real.json";
import { parseGeoaiResearchBundle } from "./geoai-research-bundle";

describe("archived research display boundary", () => {
  it("preserves the actual archive without promoting its arithmetic", () => {
    const result = parseGeoaiResearchBundle(archive);
    expect(result).toBe(archive);
    expect(result.can_feed_decision_layer).toBe(false);
    expect(result.aggregation_status).toBe("report_only");
  });
  it.each(["can_feed_decision_layer", "official_warning", "evidence_tier", "aggregation_status"])("rejects absent or conflicting %s", (field) => {
    const absent = { ...archive } as Record<string, unknown>;
    delete absent[field];
    expect(() => parseGeoaiResearchBundle(absent)).toThrow(/provenance/);
    expect(() => parseGeoaiResearchBundle({ ...archive, [field]: true })).toThrow(/provenance/);
  });
  it("rejects a remote or traversing preview and malformed arithmetic", () => {
    for (const input of ["https://example.org/image.png", "/geoai/../secret.png"]) expect(() => parseGeoaiResearchBundle({ ...archive, components: [{ ...archive.components[0], input }] })).toThrow();
    expect(() => parseGeoaiResearchBundle({ ...archive, subdistricts: [{ ...archive.subdistricts[0], fpps: Number.NaN }] })).toThrow();
  });
});
