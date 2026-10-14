import type { Metadata } from "next";

import { JourneyExperience } from "@/components/journey/journey-experience";

// A cinematic, scroll-driven story on the real map of Mae Sai (open building outlines, OpenStreetMap roads) with the
// water of the published replay (r5), told through fictional people and the real FloodGuard pages (public app, Mae Sai
// case view, command exercise). Staff-profile route: the public-production build removes it with the other staff
// routes because the story depends on /studio/ and /command/.
export const metadata: Metadata = {
  title: "FloodGuard journey: home dry, way cut off",
  description: "A 3D story of fictional people on the real map of Mae Sai, with the water of FloodGuard's model reconstruction of September 2024 (low confidence), connected to the real public app, case view and command exercise. Not a forecast, not real-time, not an official warning.",
};

export default function JourneyPage() {
  return <JourneyExperience />;
}
