import { LandingExperience } from "./landing-experience";
import { SupportingSections } from "./supporting-sections";

export function LandingPage() {
  return <LandingExperience reviewEnabled={process.env.NEXT_PUBLIC_FLOODGUARD_LANDING_REVIEW === "1"}><SupportingSections /></LandingExperience>;
}
