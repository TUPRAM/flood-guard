import { describe, expect, it } from "vitest";
import { evaluateIllustrativeScenario, findScenarioPath, ILLUSTRATIVE_SCENARIO as scenario, insideIllustrativeFlood } from "./illustrative-scenario";

describe("controlled illustrative access scenario", () => {
  it("has unique stable IDs and valid graph endpoints", () => {
    expect(new Set(scenario.nodes.map(node => node.id)).size).toBe(scenario.nodes.length);
    expect(new Set(scenario.links.map(link => link.id)).size).toBe(scenario.links.length);
    for (const link of scenario.links) for (const endpoint of [link.from, link.to]) expect(scenario.nodes.some(node => node.id === endpoint)).toBe(true);
  });
  it("computes the baseline connection and loss after the explicit crossing assumption", () => {
    expect(evaluateIllustrativeScenario()).toMatchObject({ baselineReachable: true, scenarioReachable: false, scenarioPath: null, removedLinkId: "SYN-LINK-CROSSING", origin: "synthetic_illustration", currentConditionClaim: false, operationalWriteAllowed: false });
    expect(evaluateIllustrativeScenario().baselinePath).toContain(scenario.assumedDisruptedLinkId);
  });
  it("does not claim a loss for an unrelated spur removal or infer it from water alone", () => {
    expect(findScenarioPath(scenario.nodes, scenario.links, scenario.homeId, scenario.facilityId, new Set(["SYN-LINK-SPUR"]))).toEqual(evaluateIllustrativeScenario().baselinePath);
    expect(findScenarioPath(scenario.nodes, scenario.links, scenario.homeId, scenario.facilityId)).not.toBeNull();
  });
  it("leaves the selected homes and facility physically outside the flood while intersecting the crossing", () => {
    for (const point of [[-9,-5],[-10.3,-6.0],[-7.7,-4.0],[.3,3.175],[4.9,5.425]] as const) expect(insideIllustrativeFlood(point)).toBe(false);
    expect(insideIllustrativeFlood([-4.3,.075])).toBe(true);
  });
  it("supports an explicitly supplied alternate connection rather than hardcoding unavailability", () => {
    const links = [...scenario.links, { id: "SYN-TEST-ALTERNATIVE", from: scenario.homeId, to: scenario.facilityId }];
    expect(findScenarioPath(scenario.nodes, links, scenario.homeId, scenario.facilityId, new Set([scenario.assumedDisruptedLinkId]))).toEqual(["SYN-TEST-ALTERNATIVE"]);
  });
  it("handles cycles, reversed endpoints, identical endpoints and unknown nodes deterministically", () => {
    expect(findScenarioPath(scenario.nodes, scenario.links, scenario.facilityId, scenario.homeId)).toEqual([...evaluateIllustrativeScenario().baselinePath!].reverse());
    expect(findScenarioPath(scenario.nodes, scenario.links, scenario.homeId, scenario.homeId)).toEqual([]);
    expect(findScenarioPath(scenario.nodes, scenario.links, "unknown", scenario.homeId)).toBeNull();
    expect(() => findScenarioPath(scenario.nodes, [{ id: "bad", from: "unknown", to: scenario.homeId }], scenario.homeId, scenario.facilityId)).toThrow("Unknown endpoint");
    for (let i = 0; i < 5; i++) expect(evaluateIllustrativeScenario()).toEqual(evaluateIllustrativeScenario());
  });
});
