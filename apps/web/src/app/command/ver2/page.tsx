import type { Metadata } from "next";

import { CandidateCaseContext } from "@/components/candidate-case-context";
import { PlanningCandidateOverview } from "@/components/planning-candidate-overview";

// The candidate planning overview, served at /command/ until the owner's request of 5 Oct 2026 (decision log R19)
// made the map workspace the default Planning page. Its address is PLANNING_OVERVIEW_ROUTE in @/lib/case-selection.
// It shows no research score and no research class.
export const metadata: Metadata = {
  title: "Planning overview | FloodGuard",
  description: "Candidate case access, services, road assumptions, equity limits, and verification priorities for non-operational planning.",
};

export default function CommandOverviewPage() {
  return <><CandidateCaseContext role="planning" /><PlanningCandidateOverview /></>;
}
