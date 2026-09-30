import type { Metadata } from "next";
import { PolicyPage } from "@/components/policy-page";

export const metadata: Metadata = {
  title: "Policy & public value",
  description: "How FloodGuard turns flood evidence into preparedness priorities: FPPS, recommended actions, equitable access, and the fit with Thai policy.",
};

export default function PolicyRoute() {
  return <PolicyPage />;
}
