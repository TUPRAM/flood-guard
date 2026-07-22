import type { Metadata } from "next";

import { StudioWorkspace } from "@/components/studio-workspace";

export const metadata: Metadata = {
  title: "Validation & evidence report",
  description: "Read-only validation, provenance, and authorization evidence for one immutable context.",
};

export default function StudioPage() {
  return <div id="main-content"><StudioWorkspace /></div>;
}
