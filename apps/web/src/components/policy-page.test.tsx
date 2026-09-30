import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { POLICY_EVIDENCE } from "@/lib/policy-evidence";
import { PolicyPage } from "./policy-page";

describe("policy mentoring brief", () => {
  const html = renderToStaticMarkup(<PolicyPage />);
  const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");

  it("renders the full explanation and anchor destinations before JavaScript", () => {
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toContain('id="main-content"');
    for (const id of ["purpose", "evidence", "priorities", "access", "thailand", "responsibility"]) {
      expect(html).toContain(`id="${id}"`);
      expect(html).toContain(`href="#${id}"`);
    }
    expect(html).toContain('aria-label="Use English"');
    expect(html).toContain('aria-label="ใช้ภาษาไทย"');
    expect(text).toContain("Class E does not mean safe.");
    expect(text).toContain("PROPOSED GOVERNANCE");
  });

  it("binds every displayed result to the reproduced study and its scenario", () => {
    expect(text).toContain("Ko Chang");
    expect(text).toContain("76.38");
    expect(text).not.toMatch(/53\.6|44\.0/);
    expect(html).toContain(POLICY_EVIDENCE.sourceUrl);
    expect(html).toContain(POLICY_EVIDENCE.sourceSha256);
    expect(html).toContain(POLICY_EVIDENCE.scenario.timestamp);
    expect(POLICY_EVIDENCE.rankings).toHaveLength(8);
    expect(POLICY_EVIDENCE.rankings.every((row) => row.actionClass === "E")).toBe(true);
    expect(text).toContain("does not contain this FPPS update");
    expect(text).toContain("not observed impacts or operational approval");
    expect(POLICY_EVIDENCE.generatedAt).toBeNull();
    expect(POLICY_EVIDENCE.acceptedFpps).toBeNull();
    expect(POLICY_EVIDENCE.acceptedActionClass).toBeNull();
    expect(POLICY_EVIDENCE.officialWarning).toBe(false);
  });

  it("explains the low-confidence gate before the ordered action conditions", () => {
    const rules = text.slice(text.indexOf("Evaluate in this order."));
    expect(rules.indexOf("Low confidence OR FPPS &lt;35")).toBeLessThan(rules.indexOf("Exposure ≥70"));
    expect(rules).toContain("Exposure ≥70 and access gap ≥70");
    expect(rules).toContain("Road criticality ≥75 and access gap ≥55");
    expect(rules).toContain("Exposure ≥65 and access gap ≥50");
    expect(text).toContain("not Thai warning levels");
    expect(text).toContain("Proposed fit, not agency adoption");
  });
});
