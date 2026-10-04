import type { Metadata } from "next";

import { CommandWorkspace } from "@/components/command-workspace";

export const metadata: Metadata = {
  title: "Historical planning archive | FloodGuard",
  description: "Retained Mae Sai subdistrict research comparison. Its scores are not accepted event-response priorities.",
};

export default function CommandArchivePage() {
  return <CommandWorkspace />;
}
