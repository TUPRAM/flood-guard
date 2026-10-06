import type { Metadata } from "next";

import { CommandWorkspace } from "@/components/command-workspace";

// The map workspace is the default Planning page (owner request of 5 Oct 2026, decision log R19). It was served at
// /command/archive/ before; that address now forwards here. The page states, above its ranking, that the scores and
// classes it shows are retained research comparisons. The candidate planning overview is at /command/ver2/.
export const metadata: Metadata = {
  title: "Planning workspace (retained research comparison) | FloodGuard",
  description: "Mae Sai planning map workspace. Its ranking, scores and classes are retained research comparisons, not accepted event-response priorities.",
};

export default function CommandPage() {
  return <CommandWorkspace />;
}
