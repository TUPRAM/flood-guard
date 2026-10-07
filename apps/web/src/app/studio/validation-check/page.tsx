import type { Metadata } from "next";

import { ValidationCheck } from "@/components/validation-check";

// A page for the three team members (owner request of 7 Oct 2026, decision log R27). It lists what they are asked to
// check and lets each hand a record over. It stands below /studio/, so the public-production build does not ship it.
export const metadata: Metadata = {
  title: "Validation check (team page) | FloodGuard",
  description: "What the FloodGuard team is asked to check before a result goes on a page, and a way to record each team member's word. Not a review by an independent expert and not an official approval.",
  robots: { index: false, follow: false },
};

export default function ValidationCheckPage() {
  return <ValidationCheck />;
}
