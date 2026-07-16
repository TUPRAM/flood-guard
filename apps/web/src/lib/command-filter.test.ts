import { describe, expect, it } from "vitest";

import { toggleCommandClass } from "./command-filter";

const areas = [
  { area_id: "area-b", action_class: "B" },
  { area_id: "area-d", action_class: "D" },
  { area_id: "area-e", action_class: "E" },
] as const;

describe("command class filtering", () => {
  it("moves selection to a visible polygon when its class is hidden", () => {
    const result = toggleCommandClass(
      new Set(["B", "D", "E"]),
      "B",
      "area-b",
      areas,
    );

    expect([...result.activeClasses]).toEqual(["D", "E"]);
    expect(result.selectedId).toBe("area-d");
  });

  it("keeps a selection whose class remains visible", () => {
    const result = toggleCommandClass(
      new Set(["B", "D", "E"]),
      "E",
      "area-b",
      areas,
    );

    expect(result.selectedId).toBe("area-b");
  });

  it("does not allow the final visible class to be removed", () => {
    const result = toggleCommandClass(new Set(["B"]), "B", "area-b", areas);

    expect([...result.activeClasses]).toEqual(["B"]);
    expect(result.selectedId).toBe("area-b");
  });
});
