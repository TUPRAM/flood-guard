import type { Metadata } from "next";

import { CandidateCaseContext } from "@/components/candidate-case-context";
import { StudioCandidateReport } from "@/components/studio-candidate-report";

export const metadata: Metadata = {
  title: "Validation & evidence report",
  description: "Read-only candidate-package validation, provenance and decision boundaries for the selected FloodGuard case.",
};

export default function StudioPage() {
  return <>
    <CandidateCaseContext role="studio" />
    <StudioCandidateReport />
  </>;
}
