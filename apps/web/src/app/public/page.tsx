import type { Metadata } from "next";

import { PublicExperience } from "@/components/public-experience";

export const metadata: Metadata = { title: "Public preparedness" };

export default function PublicPage() {
  return <div id="main-content"><PublicExperience /></div>;
}
