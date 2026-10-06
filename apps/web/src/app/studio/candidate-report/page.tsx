import type { Metadata } from "next";

import { CandidateCaseContext } from "@/components/candidate-case-context";
import { StudioCandidateReport } from "@/components/studio-candidate-report";

export const metadata: Metadata = {
  title: "Validation & evidence report",
  description: "Read-only candidate-package validation, provenance and decision boundaries for the selected FloodGuard case.",
};

// The study library owns /studio/; the candidate-package report is the page the scoring line had there.
// Its address is STUDIO_CANDIDATE_REPORT_ROUTE in @/lib/case-selection.
export default function StudioCandidateReportPage() {
  return <>
    <CandidateCaseContext role="studio" />
    <StudioCandidateReport />
  </>;
}
