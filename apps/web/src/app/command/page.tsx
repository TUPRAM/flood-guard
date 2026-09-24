import type { Metadata } from "next";

import { CandidateCaseContext } from "@/components/candidate-case-context";
import { PlanningCandidateOverview } from "@/components/planning-candidate-overview";

export const metadata: Metadata = {
  title: "Planning overview | FloodGuard",
  description: "Candidate case access, services, road assumptions, equity limits, and verification priorities for non-operational planning.",
};

export default function CommandPage() {
  return <><CandidateCaseContext role="planning" /><PlanningCandidateOverview /></>;
}
