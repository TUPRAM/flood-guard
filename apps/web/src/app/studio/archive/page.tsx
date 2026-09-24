import type { Metadata } from "next";

import { StudioWorkspace } from "@/components/studio-workspace";

export const metadata: Metadata = {
  title: "Historical Mae Sai technical archive | FloodGuard Thailand",
  description: "Retained historical Mae Sai technical report with its own evidence context, separate from current candidate packages.",
};

export default function StudioArchivePage() {
  return <StudioWorkspace archive />;
}
