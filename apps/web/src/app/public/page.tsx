import type { Metadata } from "next";

import { PublicExperience } from "@/components/public-experience";

export const metadata: Metadata = {
  title: "Public preparedness",
  description: "Mae Sai household flood preparedness using a public-safe historical planning projection.",
};

export default function PublicPage() {
  return <div id="main-content"><PublicExperience /></div>;
}
