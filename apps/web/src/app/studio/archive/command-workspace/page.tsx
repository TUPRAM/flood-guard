import type { Metadata } from "next";

import { CommandWorkspace } from "@/components/command-workspace";

// The older map workspace, kept as historical research in Studio's archive since 7 Oct 2026 (decision log R24). It was
// the default Planning page at /command/ before. The page states, above its ranking, that the scores and classes it
// shows are retained research comparisons from before the signed protocol.
export const metadata: Metadata = {
  title: "Historical Planning map workspace (retained research comparison) | FloodGuard",
  description: "Mae Sai planning map workspace. Its ranking, scores and classes are retained research comparisons, not accepted event-response priorities.",
};

export default function ResearchWorkspacePage() {
  return <CommandWorkspace />;
}
