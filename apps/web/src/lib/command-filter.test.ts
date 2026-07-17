import { describe, expect, it } from "vitest";

import { rankVisibleAreas, toggleCommandClass } from "./command-filter";

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

describe("command ranked list", () => {
  it("orders visible engine outputs without changing their scores", () => {
    const input = [
      { area_id: "area-c", action_class: "C", fpps_0_100: 61.2 },
      { area_id: "area-a", action_class: "A", fpps_0_100: 82.4 },
      { area_id: "area-b", action_class: "B", fpps_0_100: 70.1 },
    ] as const;

    const ranked = rankVisibleAreas(input, new Set(["A", "C"]));

    expect(ranked.map((area) => area.area_id)).toEqual(["area-a", "area-c"]);
    expect(ranked.map((area) => area.fpps_0_100)).toEqual([82.4, 61.2]);
    expect(input.map((area) => area.area_id)).toEqual(["area-c", "area-a", "area-b"]);
  });
});
