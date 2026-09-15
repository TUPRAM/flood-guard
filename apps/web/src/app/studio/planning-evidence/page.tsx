import type { Metadata } from "next";

import { StudioWorkspace } from "@/components/studio-workspace";

export const metadata: Metadata = {
  title: "Planning evidence — Studio",
  description: "Read-only Mae Sai validation, provenance, qualification and authorization records for the current evidence context.",
};

export default function PlanningEvidencePage() {
  return <div id="main-content"><StudioWorkspace /></div>;
}
