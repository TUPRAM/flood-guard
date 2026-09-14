import type { Metadata } from "next";
import { RootExperience } from "@floodguard/root-entry";
import { resolveDeploymentProfile } from "@/lib/deployment-profile";
import copy from "@/lib/landing/copy.en.json";

function isPublicProfile() {
  return resolveDeploymentProfile(process.env.FLOODGUARD_APP_PROFILE ?? process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE) === "public-production";
}

export function generateMetadata(): Metadata {
  if (isPublicProfile()) return {};
  const deploymentOrigin = process.env.VERCEL_URL ? new URL(`https://${process.env.VERCEL_URL}`) : undefined;
  return { metadataBase: deploymentOrigin, title: { absolute: copy.metadata.title }, description: copy.metadata.description,
    openGraph: { title: copy.metadata.title, description: copy.metadata.description, images: deploymentOrigin ? [{ url: "/landing/desktop-v4/far.webp", width: 1600, height: 900, alt: "FloodGuard's illustrated connected terrain" }] : [] } };
}

export default function RootEntry() {
  return <RootExperience />;
}
