import type { Metadata } from "next";

import { PipelineExplorer } from "@/components/pipeline-explorer";

// The proposal's five figures with the state of every box (owner request of 16 Oct 2026). It stands below /studio/, so
// the public-production build does not ship it.
export const metadata: Metadata = {
  title: "Pipeline progress | FloodGuard Studio",
  description: "The five figures of the FloodGuard proposal, with the state of every box (done, in progress, not started) and the evidence behind it. Planning guidance from modelled figures; not real-time and not an official warning.",
  robots: { index: false, follow: false },
};

export default function PipelinePage() {
  return <PipelineExplorer />;
}
