import { describe, expect, it } from "vitest";

import { commandRankPositions, rankVisibleAreas, resolveCommandSelection, searchRankedAreas, toggleCommandClass } from "./command-filter";

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

  it("moves a hidden selection to the highest-ranked remaining area", () => {
    const result = toggleCommandClass(
      new Set(["B", "D", "E"]),
      "B",
      "area-b",
      [
        { area_id: "area-b", action_class: "B", fpps_0_100: 80 },
        { area_id: "area-d", action_class: "D", fpps_0_100: 20 },
        { area_id: "area-e", action_class: "E", fpps_0_100: 60 },
      ],
    );

    expect(result.selectedId).toBe("area-e");
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

  it("keeps a valid persisted selection and otherwise selects the highest FPPS area", () => {
    const input = [
      { area_id: "area-low", action_class: "E", fpps_0_100: 12 },
      { area_id: "area-high", action_class: "E", fpps_0_100: 82 },
    ] as const;

    expect(resolveCommandSelection(input, "area-low")?.area_id).toBe("area-low");
    expect(resolveCommandSelection(input, "removed-area")?.area_id).toBe("area-high");
    expect(resolveCommandSelection(input)?.area_id).toBe("area-high");
  });

  it("searches the ranked selector by identifier and either localized name", () => {
    const input = [
      { area_id: "TH570903", area_name_en: "Ko Chang", area_name_th: "เกาะช้าง", action_class: "E", fpps_0_100: 53.6 },
      { area_id: "TH570905", area_name_en: "Si Mueang Chum", area_name_th: "ศรีเมืองชุม", action_class: "E", fpps_0_100: 50.4 },
    ];

    expect(searchRankedAreas(input, new Set(["E"]), "570903").map((area) => area.area_id)).toEqual(["TH570903"]);
    expect(searchRankedAreas(input, new Set(["E"]), "ศรีเมือง").map((area) => area.area_id)).toEqual(["TH570905"]);
    expect(commandRankPositions(input).get("TH570905")).toBe(2);
  });
});
