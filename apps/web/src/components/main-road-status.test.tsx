import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MainRoadStatus } from "./main-road-status";

describe("main-road access boundary", () => {
  it("shows a distinct unavailable service category without a numeric or passability claim", () => {
    const en = renderToStaticMarkup(<MainRoadStatus th={false} />);
    const th = renderToStaticMarkup(<MainRoadStatus th />);
    expect(en).toContain('data-main-road-access="unavailable"');
    expect(en).toContain("Main-road access: unavailable as a separate qualified service result");
    expect(en).toContain("does not establish real main-road access or passability");
    expect(th).toContain("การเข้าถึงถนนสายหลัก: ยังไม่มีผลบริการแยก");
    expect(en).not.toMatch(/data-main-road-access="(?:available|0)"/);
  });
});
