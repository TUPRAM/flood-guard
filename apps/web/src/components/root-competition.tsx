import { LandingPage } from "./landing-v1/landing-page";
import { LandingArtworkCache } from "./landing-artwork-cache.client";

export function RootExperience() {
  return <><LandingPage /><LandingArtworkCache /></>;
}
