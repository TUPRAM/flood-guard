import type { NextConfig } from "next";
import { fileURLToPath } from "node:url";
import { resolveDeploymentProfile } from "./src/lib/deployment-profile";

const profile = resolveDeploymentProfile(process.env.FLOODGUARD_APP_PROFILE ?? process.env.NEXT_PUBLIC_FLOODGUARD_APP_PROFILE);
// Resolve the entry before bundling so Public never includes landing animation code.
const rootEntry = profile === "public-production"
  ? "./src/components/root-public.tsx"
  : "./src/components/landing/root-competition.tsx";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  devIndicators: false,
  turbopack: { root: fileURLToPath(new URL("../..", import.meta.url)), resolveAlias: { "@floodguard/root-entry": rootEntry } },
  webpack(config) {
    config.resolve.alias["@floodguard/root-entry"] = fileURLToPath(new URL(rootEntry, import.meta.url));
    return config;
  },
};

export default nextConfig;
