import type { Metadata } from "next";

import { PublicExperience } from "@/components/public-experience";

export const metadata: Metadata = {
  title: "FloodGuard",
  description: "Mae Sai flood planning, household preparation, official contacts, and community reporting.",
};

export default function PublicPage() {
  return <div id="main-content"><PublicExperience /></div>;
}
