import type { Metadata } from "next";

import { TechnicalFollowUp } from "@/components/technical-follow-up";

// The "Follow-up on technical mentoring" segment of Mentoring Session II (owner request of 16 Oct 2026). It stands
// below /studio/, so the public-production build does not ship it.
export const metadata: Metadata = {
  title: "Technical follow-up | FloodGuard Studio",
  description: "Mentoring Session II, 0:10 to 0:25: pipeline status with the evidence behind every stage, GeoAI decisions, uncertainty and open blockers. Planning guidance from modelled figures; not real-time and not an official warning.",
  robots: { index: false, follow: false },
};

export default function TechnicalFollowUpPage() {
  return <TechnicalFollowUp />;
}
