import type { Metadata } from "next";

import { JourneyExperience } from "@/components/journey/journey-experience";

// A cinematic, scroll-driven story that moves through an illustrative 3D neighbourhood and into the real FloodGuard
// pages (public app, Mae Sai case view, command exercise). Staff-profile route: the public-production build removes it
// with the other staff routes because the story depends on /studio/ and /command/.
export const metadata: Metadata = {
  title: "FloodGuard journey: from a phone to a coordinated response",
  description: "An illustrative 3D story of one household, one road and one clinic, connected to the real FloodGuard public app, case view and command exercise. Not real-time, not an official warning.",
};

export default function JourneyPage() {
  return <JourneyExperience />;
}
