import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { candidateDecisionStages, StudioCandidateReport } from "./studio-candidate-report";
import { StudioWorkspace } from "./studio-workspace";

describe("Studio case-bound report", () => {
  it("keeps package integrity separate from scientific and downstream acceptance", () => {
    const stages = candidateDecisionStages();

    expect(stages.map((stage) => [stage.id, stage.state])).toEqual([
      ["integrity", "verified"],
      ["reference", "not_recorded"],
      ["evaluation", "not_recorded"],
      ["decision", "unavailable"],
      ["authorization", "blocked"],
    ]);
    expect(stages.find((stage) => stage.id === "integrity")?.meaning.en).toContain("not scientific acceptance");
    expect(stages.find((stage) => stage.id === "decision")?.meaning.en).toContain("Missing inputs are not zero");
  });

  it("renders the candidate report without a historical evidence context", () => {
    const html = renderToStaticMarkup(<StudioCandidateReport />);

    expect(html).toContain("Evidence status and decision boundary");
    expect(html).toContain("Loading case catalog");
    expect(html).not.toContain("mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1");
    expect(html).not.toContain("Exact match");
  });

  it("labels the retained Mae Sai technical report as a separate archive context", () => {
    const html = renderToStaticMarkup(<StudioWorkspace archive />);

    expect(html).toContain("Historical Mae Sai technical archive");
    expect(html).toContain("Historical Mae Sai report");
    expect(html).toContain("They do not validate or authorize the selected candidate study case.");
  });
});
