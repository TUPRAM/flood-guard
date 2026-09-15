import type { Metadata } from "next";
import { RootExperience } from "@floodguard/root-entry";
import { resolveDeploymentProfile } from "@/lib/deployment-profile";

export function generateMetadata(): Metadata {
  const profile = resolveDeploymentProfile(process.env.FLOODGUARD_APP_PROFILE ?? process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE);
  if (profile === "public-production") return {};
  return {
    title: { absolute: "FloodGuard — See the flood. Understand what it changes." },
    description: "Follow one illustrated neighborhood from changing flood conditions to the connections and preparedness questions that matter.",
  };
}

export default function RootEntry() {
  return <RootExperience />;
}
