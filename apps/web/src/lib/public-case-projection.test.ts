import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parsePublicCaseCatalog, parsePublicCaseProjection } from "./public-case-projection";

const app = process.cwd();
const catalog = parsePublicCaseCatalog(JSON.parse(readFileSync(resolve(app, "public/public-case-projections/catalog.json"), "utf8")));
const sourceCatalog = JSON.parse(readFileSync(resolve(app, "public/evidence-library/catalog.json"), "utf8"));
const bytes = (url: string) => readFileSync(resolve(app, "public", url.slice(1)));
const sha256 = (value: Buffer) => createHash("sha256").update(value).digest("hex");
const validCase = (reference: (typeof catalog.packages)[number]) => {
  const value = JSON.parse(bytes(reference.url).toString("utf8"));
  const sourceReference = sourceCatalog.packages.find((item: { id: string }) => item.id === reference.id);
  const source = JSON.parse(bytes(sourceReference.url).toString("utf8"));
  const mainRoad = { id: "main_road", status: "unavailable", reason: "Main-road access not qualified.", facilities: null, variants: [] };
  return { ...value, access: null, source_analysis_generated_at: source.decision_brief.finals_analysis?.generated_at ?? null,
    services: value.services.some((service: { id: string }) => service.id === "main_road") ? value.services : [...value.services, mainRoad] };
};

describe("public case projections", () => {
  it("binds every allowlisted public value to the same source case and service result", () => {
    expect(sha256(readFileSync(resolve(app, "public/evidence-library/catalog.json")))).toBe(catalog.source_catalog_sha256);
    for (const reference of catalog.packages) {
      const projectedBytes = bytes(reference.url);
      expect(sha256(projectedBytes)).toBe(reference.sha256);
      const projected = parsePublicCaseProjection(JSON.parse(projectedBytes.toString("utf8")), catalog, reference);
      const sourceReference = sourceCatalog.packages.find((item: { id: string }) => item.id === reference.id);
      expect(sourceReference.sha256).toBe(reference.source_package_sha256);
      const source = JSON.parse(bytes(sourceReference.url).toString("utf8"));
      expect(projected.id).toBe(source.id);
      expect(projected.fpps).toBeNull();
      expect(projected.action_class).toBeNull();
      expect(projected.affected_population).toBeNull();
      expect(projected.access).toBeNull();
      expect(projected.source_analysis_generated_at).toBe(source.decision_brief.finals_analysis?.generated_at ?? null);
      for (const service of projected.services) {
        if (service.id === "main_road") {
          expect(service.status).toBe("unavailable");
          expect(service.facilities).toBeNull();
          expect(service.variants).toEqual([]);
          continue;
        }
        const sourceService = source.decision_brief.finals_analysis.services.find((item: { id: string }) => item.id === service.id);
        for (const variant of service.variants) {
          const original = sourceService.variants.find((item: { id: string }) => item.id === variant.id);
          expect(variant.within_30_minutes_population).toBe(original.baseline.within_30_minutes_population);
          expect(variant.modelled_population).toBe(original.baseline.modelled_population);
        }
      }
    }
  });

  it("rejects accepted-looking data, injected private fields and mixed source identities", () => {
    const reference = catalog.packages[0];
    const value = validCase(reference);
    expect(() => parsePublicCaseProjection(value, catalog, reference)).not.toThrow();
    expect(() => parsePublicCaseProjection({ ...value, fpps: 72 }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, action_class: "A" }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, private_contact: "hidden" }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, source_package_sha256: "0".repeat(64) }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, source_analysis_generated_at: "2099-01-01T00:00:00Z" }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, access: { modelled_population: 1, within_30_minutes_population: 1, connected_without_route_population: 0, unknown_access_population: 0 } }, catalog, reference)).toThrow();
    const malformedService = structuredClone(value);
    malformedService.services[0].variants[0].within_30_minutes_population = -1;
    expect(() => parsePublicCaseProjection(malformedService, catalog, reference)).toThrow();
  });

  it("keeps main-road access explicit and unavailable until a qualified source result exists", () => {
    const reference = catalog.packages[0];
    const value = validCase(reference);
    const mainRoad = value.services.find((service: { id: string }) => service.id === "main_road");
    expect(() => parsePublicCaseProjection(value, catalog, reference)).not.toThrow();
    expect(() => parsePublicCaseProjection({ ...value, services: value.services.filter((service: { id: string }) => service.id !== "main_road") }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, services: value.services.map((service: { id: string }) => service.id === "main_road" ? { ...mainRoad, facilities: 0 } : service) }, catalog, reference)).toThrow();
    expect(() => parsePublicCaseProjection({ ...value, services: value.services.map((service: { id: string }) => service.id === "main_road" ? { ...mainRoad, status: "available" } : service) }, catalog, reference)).toThrow();
  });

  it("rejects unsafe catalog URLs and duplicate area-event bindings", () => {
    expect(() => parsePublicCaseCatalog({ ...catalog, packages: [{ ...catalog.packages[0], url: "/public-case-projections/../secrets.json" }] })).toThrow();
    expect(() => parsePublicCaseCatalog({ ...catalog, packages: [catalog.packages[0], catalog.packages[0]] })).toThrow();
  });
});
