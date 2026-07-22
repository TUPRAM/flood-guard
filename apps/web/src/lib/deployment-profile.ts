export type DeploymentProfile = "competition" | "public-production";

export function resolveDeploymentProfile(value: string | undefined): DeploymentProfile {
  const normalized = value?.trim().toLowerCase();
  if (!normalized || normalized === "competition") return "competition";
  if (normalized === "public" || normalized === "public-production") return "public-production";
  throw new Error(`Unsupported FloodGuard deployment profile: ${value}`);
}
