import type { Metadata } from "next";

import { CandidateCaseContext } from "@/components/candidate-case-context";
import { CaseRoleBody } from "@/components/case-role-body";

export const metadata: Metadata = {
  title: "Planning workspace",
  description: "Mae Sai area planning, evidence review, and verification workspace.",
};

export default function CommandPage() {
  return <><CandidateCaseContext role="planning" /><CaseRoleBody role="planning" /></>;
}
