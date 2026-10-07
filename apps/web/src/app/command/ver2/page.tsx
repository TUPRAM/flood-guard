import type { Metadata } from "next";

import { PlanningOverviewForward } from "@/components/command-archive-forward";

// The planning overview was served here from 5 to 7 Oct 2026 (decision log R19). It is at /command/planning/ since
// decision log R24, and this address only forwards to it.
export const metadata: Metadata = {
  title: "Moved to the planning overview · ย้ายไปที่ภาพรวมเพื่อการวางแผนแล้ว | FloodGuard",
  description: "This address forwards to the planning overview at /command/planning/. · ที่อยู่นี้ส่งต่อไปยังภาพรวมเพื่อการวางแผนที่ /command/planning/",
};

export default function PlanningOverviewForwardPage() {
  return <PlanningOverviewForward />;
}
