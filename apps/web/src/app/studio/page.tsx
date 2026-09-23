import type { Metadata } from "next";

import { CandidateCaseContext } from "@/components/candidate-case-context";
import { CaseRoleBody } from "@/components/case-role-body";

export const metadata: Metadata = {
  title: "Validation & evidence report",
  description: "Read-only validation, provenance, and authorization evidence for one immutable context.",
};

export default function StudioPage() {
  return <><CandidateCaseContext role="studio" /><CaseRoleBody role="studio" /></>;
}
